"""Training and evaluation driver for the ICA 2026 paper experiments.

One protocol, three backbones, two corpora. Everything that varies between runs
lives in a YAML config under ``experiments/ica26/configs``; nothing about an
experiment is hardcoded here.

A run refuses to start unless the experiment dataset lock validates, so a
checkpoint can always be traced back to an exact, digest-bound corpus.
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader
from torchvision import transforms

from . import calibration as calib
from . import data as dmod
from . import metrics as mmod
from . import models as models_mod
from .mapping import CrossDomainMapping, load_mapping

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


@dataclass
class ExperimentConfig:
    experiment_id: str
    dataset: str                      # plantvillage | plantdoc_core
    model: str                        # resnet50 | efficientnet_b0 | mobilenet_v3_small
    seed: int = 42
    image_size: int = 224
    batch_size: int = 64
    eval_batch_size: int = 128
    epochs: int = 15
    early_stopping_patience: int = 3
    lr: float = 3e-4
    weight_decay: float = 1e-4
    label_smoothing: float = 0.1
    val_fraction: float = 0.1
    scheduler: str = "cosine"
    optimizer: str = "adamw"
    amp: bool = True
    num_workers: int = 6
    pretrained: bool = True
    class_weighting: str = "none"     # none | inverse_frequency
    cross_domain_eval: bool = False
    calibrate: bool = True
    limit_train_batches: Optional[int] = None   # smoke tests only
    subset_per_class: Optional[int] = None      # smoke tests only
    notes: str = ""

    @staticmethod
    def from_yaml(path: str | Path) -> "ExperimentConfig":
        payload = yaml.safe_load(Path(path).read_text())
        known = {f for f in ExperimentConfig.__dataclass_fields__}
        unknown = set(payload) - known
        if unknown:
            raise ValueError(f"{path}: unknown config keys {sorted(unknown)}")
        return ExperimentConfig(**payload)

    def to_dict(self) -> dict:
        return asdict(self)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_transforms(image_size: int) -> tuple:
    """Moderate, symptom-preserving augmentation.

    Hue jitter is deliberately tiny: chlorosis and necrosis are diagnosed by
    colour, so shifting hue would destroy the signal the task depends on.
    Rotation and crop scale stay conservative for the same reason.
    """
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0), ratio=(0.8, 1.25)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.02),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize(int(image_size * 256 / 224)),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    return train_tf, eval_tf


def _subset_per_class(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Deterministic per-class head sample, for smoke runs only."""
    return (
        df.sort_values("relpath")
        .groupby("class_label", group_keys=False, sort=True)
        .head(n)
        .reset_index(drop=True)
    )


@dataclass
class PreparedData:
    spec: dmod.DatasetSpec
    class_to_idx: dict
    classes: list
    train_df: pd.DataFrame
    val_df: pd.DataFrame
    test_df: pd.DataFrame
    group_column: Optional[str] = None
    counts: dict = field(default_factory=dict)


def prepare_data(cfg: ExperimentConfig, repo_root: str | Path = ".") -> PreparedData:
    if cfg.dataset == "plantvillage":
        spec = dmod.load_plantvillage(repo_root)
        group_column = "leaf_id"
    elif cfg.dataset == "plantdoc_core":
        spec = dmod.load_plantdoc_core(repo_root)
        group_column = None
    else:
        raise ValueError(f"unknown dataset {cfg.dataset!r}")

    frame = spec.frame
    class_to_idx = dmod.build_class_index(frame["class_label"])
    classes = sorted(class_to_idx, key=lambda k: class_to_idx[k])

    full_train = frame[frame["split"] == "train"].reset_index(drop=True)
    test_df = frame[frame["split"] == "test"].reset_index(drop=True)

    if cfg.subset_per_class:
        full_train = _subset_per_class(full_train, cfg.subset_per_class, cfg.seed)
        test_df = _subset_per_class(test_df, max(2, cfg.subset_per_class // 2), cfg.seed)

    train_df, val_df = dmod.grouped_validation_split(
        full_train, cfg.val_fraction, cfg.seed, group_column=group_column
    )

    return PreparedData(
        spec=spec,
        class_to_idx=class_to_idx,
        classes=classes,
        train_df=train_df,
        val_df=val_df,
        test_df=test_df,
        group_column=group_column,
        counts={
            "n_classes": len(classes),
            "n_train_total_manifest": int((frame["split"] == "train").sum()),
            "n_test_total_manifest": int((frame["split"] == "test").sum()),
            "n_train_used": len(train_df),
            "n_val_used": len(val_df),
            "n_test_used": len(test_df),
            "validation_grouped_by": group_column or "none (stratified by class)",
        },
    )


def class_weights(train_df: pd.DataFrame, class_to_idx: dict, mode: str) -> Optional[torch.Tensor]:
    """Inverse-frequency weights normalised to mean 1, so the effective learning
    rate does not change when weighting is switched on."""
    if mode == "none":
        return None
    if mode != "inverse_frequency":
        raise ValueError(f"unknown class_weighting {mode!r}")
    counts = np.zeros(len(class_to_idx), dtype=np.float64)
    for label in train_df["class_label"]:
        counts[class_to_idx[str(label)]] += 1
    counts = np.maximum(counts, 1.0)
    w = counts.sum() / (len(counts) * counts)
    w = w / w.mean()
    return torch.tensor(w, dtype=torch.float32)


def make_loader(dataset, batch_size, shuffle, num_workers, device) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=(device == "cuda"),
        persistent_workers=num_workers > 0,
        drop_last=False,
    )


def _autocast(device: str, enabled: bool):
    """AMP context. CUDA uses fp16 with a gradient scaler; MPS uses fp16
    autocast without one (the MPS backend keeps master weights in fp32)."""
    if not enabled or device == "cpu":
        return torch.autocast(device_type="cpu", enabled=False)
    return torch.autocast(device_type=device, dtype=torch.float16)


@torch.no_grad()
def collect_logits(model, loader, device, amp: bool) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    logits_all, labels_all = [], []
    for x, y in loader:
        x = x.to(device, non_blocking=True)
        with _autocast(device, amp):
            out = model(x)
        logits_all.append(out.detach().float().cpu().numpy())
        labels_all.append(y.numpy())
    return np.concatenate(logits_all, axis=0), np.concatenate(labels_all, axis=0)


def measure_inference(model, device: str, image_size: int, batch_size: int) -> dict:
    """Single-image latency and batched throughput, after warm-up."""
    model.eval()
    out: dict = {}
    with torch.no_grad():
        x1 = torch.randn(1, 3, image_size, image_size, device=device)
        for _ in range(10):
            model(x1)
        _sync(device)
        t0 = time.perf_counter()
        reps = 50
        for _ in range(reps):
            model(x1)
        _sync(device)
        out["inference_latency_ms_batch1"] = round((time.perf_counter() - t0) / reps * 1000, 3)

        xb = torch.randn(batch_size, 3, image_size, image_size, device=device)
        for _ in range(5):
            model(xb)
        _sync(device)
        t0 = time.perf_counter()
        reps = 20
        for _ in range(reps):
            model(xb)
        _sync(device)
        dt = time.perf_counter() - t0
        out["inference_throughput_img_per_s"] = round(reps * batch_size / dt, 2)
        out["inference_batch_size"] = batch_size
    return out


def _sync(device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()
    elif device == "mps":
        torch.mps.synchronize()


def gradient_norm(model) -> torch.Tensor:
    """Total gradient norm, computed without modifying any gradient.

    ``clip_grad_norm_`` with an infinite threshold computes the norm through the
    same fused path the optimiser would use, then scales by a coefficient that
    clamps to exactly 1.0 -- an IEEE-exact no-op. That gives one fused pass and
    one device synchronisation instead of a per-tensor check.
    """
    return torch.nn.utils.clip_grad_norm_(model.parameters(), float("inf"))


def assert_finite_state(model, context: str) -> None:
    """Refuse to report anything computed from a model containing NaN or Inf."""
    bad = [name for name, p in model.state_dict().items()
           if p.dtype.is_floating_point and not torch.isfinite(p).all()]
    if bad:
        raise RuntimeError(
            f"{context}: {len(bad)} parameter tensor(s) contain NaN or Inf "
            f"(first: {bad[:3]}). A model in this state predicts a constant class "
            "and would report a plausible-looking accuracy near the majority-class "
            "rate. Refusing to write a result."
        )


def train_one_run(
    cfg: ExperimentConfig,
    repo_root: str | Path = ".",
    out_root: str | Path = "experiments/ica26",
    device_pref: str = "auto",
    lock_digest: Optional[str] = None,
    git_commit: Optional[str] = None,
) -> dict:
    repo_root = Path(repo_root)
    out_root = Path(out_root)
    run_dir = out_root / "runs" / cfg.experiment_id
    run_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir = out_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    set_seed(cfg.seed)
    hw = models_mod.select_device(device_pref)
    device = hw.device
    print(f"[{cfg.experiment_id}] device={device} backend={hw.backend}", flush=True)

    prepared = prepare_data(cfg, repo_root)
    train_tf, eval_tf = build_transforms(cfg.image_size)

    train_ds = dmod.ManifestImageDataset(prepared.train_df, prepared.spec.root, prepared.class_to_idx, train_tf)
    val_ds = dmod.ManifestImageDataset(prepared.val_df, prepared.spec.root, prepared.class_to_idx, eval_tf)
    test_ds = dmod.ManifestImageDataset(prepared.test_df, prepared.spec.root, prepared.class_to_idx, eval_tf)

    train_loader = make_loader(train_ds, cfg.batch_size, True, cfg.num_workers, device)
    val_loader = make_loader(val_ds, cfg.eval_batch_size, False, cfg.num_workers, device)
    test_loader = make_loader(test_ds, cfg.eval_batch_size, False, cfg.num_workers, device)

    model = models_mod.build_model(cfg.model, len(prepared.classes), cfg.pretrained).to(device)
    param_counts = models_mod.count_parameters(model)

    weights = class_weights(prepared.train_df, prepared.class_to_idx, cfg.class_weighting)
    criterion = nn.CrossEntropyLoss(
        label_smoothing=cfg.label_smoothing,
        weight=weights.to(device) if weights is not None else None,
    )
    optimiser = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps_per_epoch = len(train_loader) if cfg.limit_train_batches is None else min(len(train_loader), cfg.limit_train_batches)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimiser, T_max=max(1, cfg.epochs * steps_per_epoch)
    )
    scaler = torch.amp.GradScaler("cuda") if (cfg.amp and device == "cuda") else None

    models_mod.reset_peak_memory(device)
    history: list[dict] = []
    best = {"macro_f1": -1.0, "epoch": -1}
    ckpt_path = run_dir / "best.pt"
    patience_left = cfg.early_stopping_patience
    t_start = time.perf_counter()
    epochs_run = 0
    skipped_steps = 0      # optimiser steps skipped for non-finite gradients
    total_steps = 0

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        running, seen, correct = 0.0, 0, 0
        t_epoch = time.perf_counter()
        for i, (x, y) in enumerate(train_loader):
            if cfg.limit_train_batches is not None and i >= cfg.limit_train_batches:
                break
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            optimiser.zero_grad(set_to_none=True)
            with _autocast(device, cfg.amp):
                out = model(x)
                loss = criterion(out, y)
            total_steps += 1
            if scaler is not None:
                # CUDA: GradScaler already inspects gradients for Inf/NaN and
                # skips the step when it finds them.
                scaler.scale(loss).backward()
                scaler.step(optimiser)
                scaler.update()
            else:
                loss.backward()
                # MPS/CPU have no scaler, so the same inf-check is done here.
                # Without it, one fp16 gradient overflowing to Inf enters AdamW,
                # whose update m/sqrt(v) becomes Inf/Inf = NaN, and the parameter
                # is dead for the rest of the run -- while training accuracy,
                # computed from batch statistics, still looks healthy. Seed 42
                # never overflowed; seed 1337 did, on the first epoch.
                #
                # This is a no-op for a run whose gradients stay finite: the
                # norm is computed without modifying any gradient, so a healthy
                # run follows exactly the trajectory it followed before.
                if torch.isfinite(gradient_norm(model)):
                    optimiser.step()
                else:
                    skipped_steps += 1
                    optimiser.zero_grad(set_to_none=True)
            scheduler.step()
            running += float(loss.detach()) * y.size(0)
            correct += int((out.detach().argmax(1) == y).sum())
            seen += y.size(0)

        # Fail fast at the epoch boundary, before the validation pass. The
        # broken seed-1337 run trained on dead weights and surfaced only as an
        # implausible validation number, which is a slow and ambiguous way to
        # learn that the model died in the first epoch.
        assert_finite_state(model, f"{cfg.experiment_id}: end of epoch {epoch}")

        val_logits, val_labels = collect_logits(model, val_loader, device, cfg.amp)
        val_pred = val_logits.argmax(1)
        val_macro_f1 = mmod.classification_metrics(
            val_labels, val_pred, prepared.classes, labels=sorted(set(val_labels.tolist()))
        )["macro_f1"]
        val_acc = float((val_pred == val_labels).mean())
        epochs_run = epoch

        record = {
            "epoch": epoch,
            "train_loss": round(running / max(seen, 1), 6),
            "train_accuracy": round(correct / max(seen, 1), 6),
            "val_accuracy": round(val_acc, 6),
            "val_macro_f1": round(val_macro_f1, 6),
            "lr": round(scheduler.get_last_lr()[0], 8),
            "epoch_seconds": round(time.perf_counter() - t_epoch, 2),
            # Cumulative, so a run that starts overflowing is visible in the
            # history rather than only in the final total.
            "skipped_nonfinite_steps": skipped_steps,
        }
        history.append(record)
        print(f"[{cfg.experiment_id}] {record}", flush=True)

        if val_macro_f1 > best["macro_f1"]:
            best = {"macro_f1": val_macro_f1, "epoch": epoch, "val_accuracy": val_acc}
            torch.save(
                {"model_state": model.state_dict(), "epoch": epoch,
                 "class_to_idx": prepared.class_to_idx, "config": cfg.to_dict()},
                ckpt_path,
            )
            patience_left = cfg.early_stopping_patience
        else:
            patience_left -= 1
            if patience_left <= 0:
                print(f"[{cfg.experiment_id}] early stop at epoch {epoch}", flush=True)
                break

    train_seconds = time.perf_counter() - t_start

    # A run that skipped a large share of its steps did not follow the protocol,
    # whatever its final metrics look like. The threshold is deliberately low:
    # occasional overflow is survivable, sustained overflow means the run should
    # be diagnosed rather than reported.
    skip_fraction = skipped_steps / max(total_steps, 1)
    if skip_fraction > 0.01:
        raise RuntimeError(
            f"{cfg.experiment_id}: {skipped_steps} of {total_steps} optimiser steps "
            f"({skip_fraction:.1%}) were skipped for non-finite gradients. The run "
            "did not train under the intended protocol; refusing to write a result."
        )
    if skipped_steps:
        print(f"[{cfg.experiment_id}] skipped {skipped_steps}/{total_steps} steps "
              f"({skip_fraction:.3%}) for non-finite gradients", flush=True)

    # Restore the selected checkpoint before any reported evaluation.
    state = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(state["model_state"])
    model.to(device)
    # The last line of defence: a NaN model predicts one constant class and
    # would report an accuracy near the majority-class rate, which looks like a
    # weak result rather than a broken one.
    assert_finite_state(model, f"{cfg.experiment_id}: selected checkpoint")

    inference = measure_inference(model, device, cfg.image_size, cfg.eval_batch_size)
    peak_mem = models_mod.peak_memory_bytes(device)

    results: dict = {
        "experiment_id": cfg.experiment_id,
        "schema": "ica26.experiment_result/1",
        "config": cfg.to_dict(),
        "git_commit": git_commit,
        "experiment_lock_digest": lock_digest,
        "hardware": hw.to_dict(),
        "dataset": {
            "name": prepared.spec.name,
            "manifest": prepared.spec.manifest_path,
            "classes": prepared.classes,
            "class_to_idx_digest": dmod.class_index_digest(prepared.class_to_idx),
            **prepared.counts,
        },
        "training": {
            "best_epoch": best["epoch"],
            "best_val_macro_f1": best["macro_f1"],
            "epochs_run": epochs_run,
            "early_stopped": epochs_run < cfg.epochs,
            "class_weighting": cfg.class_weighting,
            "optimiser_steps": total_steps,
            "skipped_nonfinite_steps": skipped_steps,
            "history": history,
        },
        "efficiency": mmod.efficiency_metrics(
            param_counts["total_parameters"], param_counts["trainable_parameters"],
            train_seconds, epochs_run, inference, peak_mem,
        ),
        "evaluations": {},
    }

    # ---- in-domain test -----------------------------------------------------
    test_logits, test_labels = collect_logits(model, test_loader, device, cfg.amp)
    val_logits, val_labels = collect_logits(model, val_loader, device, cfg.amp)

    results["evaluations"]["in_domain_test"] = _evaluate(
        test_logits, test_labels, prepared.classes, temperature=None
    )

    temperature_info = None
    if cfg.calibrate:
        temperature_info = calib.fit_temperature(val_logits, val_labels)
        results["calibration"] = temperature_info
        results["evaluations"]["in_domain_test_temperature_scaled"] = _evaluate(
            test_logits, test_labels, prepared.classes,
            temperature=temperature_info["temperature"],
        )

    np.savez_compressed(
        run_dir / "predictions_in_domain_test.npz",
        logits=test_logits.astype(np.float32), labels=test_labels,
    )
    np.savez_compressed(
        run_dir / "predictions_validation.npz",
        logits=val_logits.astype(np.float32), labels=val_labels,
    )

    # ---- cross-domain -------------------------------------------------------
    if cfg.cross_domain_eval:
        mapping = load_mapping(repo_root)
        cd, cd_scaled = evaluate_cross_domain(
            model, mapping, prepared.class_to_idx, eval_tf, device, cfg,
            repo_root=repo_root, temperature=(temperature_info or {}).get("temperature"),
            run_dir=run_dir,
        )
        results["evaluations"]["cross_domain_plantdoc_core"] = cd
        if cd_scaled is not None:
            results["evaluations"]["cross_domain_plantdoc_core_temperature_scaled"] = cd_scaled

    _assert_reportable(results, cfg.experiment_id)

    _write_json(run_dir / "result.json", results)
    _write_json(metrics_dir / f"{cfg.experiment_id}.json", results)
    _write_json(run_dir / "history.json", {"experiment_id": cfg.experiment_id, "history": history})
    _write_json(run_dir / "config.resolved.json", cfg.to_dict())
    print(f"[{cfg.experiment_id}] wrote {metrics_dir / (cfg.experiment_id + '.json')}", flush=True)
    return results


def _evaluate(logits: np.ndarray, labels: np.ndarray, classes, temperature: Optional[float]) -> dict:
    probs = calib.apply_temperature(logits, temperature) if temperature else calib.softmax(logits)
    out = mmod.evaluate_classification(labels, probs.argmax(1), classes)
    out["probabilistic"] = mmod.probabilistic_metrics(labels, probs)
    out["selective_prediction"] = mmod.confidence_abstention_curve(labels, probs)
    out["temperature"] = temperature
    return out


def evaluate_cross_domain(
    model, mapping: CrossDomainMapping, source_class_to_idx: dict, eval_tf,
    device: str, cfg: ExperimentConfig, repo_root: str | Path, temperature: Optional[float],
    run_dir: Path,
) -> tuple[dict, Optional[dict]]:
    """Evaluate a PlantVillage-trained model on the shared-class PlantDoc subset.

    Only the frozen shared classes take part. Source logits are restricted to the
    PlantVillage columns that appear in the mapping and then grouped onto
    canonical class ids; PlantDoc rows outside the mapping are excluded from the
    evaluation set entirely rather than counted as errors.
    """
    spec = dmod.load_plantdoc_core(repo_root)
    frame = spec.frame.copy()
    frame["canonical_class_id"] = frame["class_label"].map(mapping.plantdoc_to_canonical)
    eligible = frame[frame["canonical_class_id"].notna()].reset_index(drop=True)

    excluded = frame[frame["canonical_class_id"].isna()]
    canon_classes = mapping.canonical_classes
    canon_to_idx = {c: i for i, c in enumerate(canon_classes)}

    ds = dmod.ManifestImageDataset(
        eligible, spec.root, canon_to_idx, eval_tf, label_column="canonical_class_id"
    )
    loader = make_loader(ds, cfg.eval_batch_size, False, cfg.num_workers, device)
    logits, labels = collect_logits(model, loader, device, cfg.amp)

    def _grouped(t: Optional[float]) -> tuple[np.ndarray, float]:
        """Group source-class probability mass onto canonical classes."""
        probs_src = calib.apply_temperature(logits, t) if t else calib.softmax(logits)
        g = np.zeros((probs_src.shape[0], len(canon_classes)), dtype=np.float64)
        for canonical, source_labels in mapping.canonical_to_plantvillage.items():
            cols = [source_class_to_idx[s] for s in source_labels if s in source_class_to_idx]
            if cols:
                g[:, canon_to_idx[canonical]] = probs_src[:, cols].sum(axis=1)
        mass = g.sum(axis=1, keepdims=True)
        return g / np.maximum(mass, 1e-12), float(mass.mean())

    grouped, retained_mass = _grouped(None)

    out = mmod.evaluate_classification(labels, grouped.argmax(1), canon_classes)
    out["probabilistic"] = mmod.probabilistic_metrics(labels, grouped)
    out["selective_prediction"] = mmod.confidence_abstention_curve(labels, grouped)
    out["temperature"] = None
    out["protocol"] = {
        "description": (
            "Restricted-label-space evaluation over the frozen shared classes. "
            "Source probabilities are summed within each canonical class and "
            "renormalised over the shared classes only."
        ),
        "n_shared_classes": len(canon_classes),
        "shared_classes": canon_classes,
        "n_evaluated_samples": int(len(eligible)),
        "n_plantdoc_core_total": int(len(frame)),
        "n_excluded_unmapped_samples": int(len(excluded)),
        "excluded_unmapped_classes": sorted(set(excluded["class_label"].astype(str))),
        "mean_retained_probability_mass_before_renormalisation": round(retained_mass, 6),
        "per_class_support": {
            str(k): int(v) for k, v in
            eligible["canonical_class_id"].value_counts().sort_index().items()
        },
        "split_composition": {
            str(k): int(v) for k, v in eligible["split"].value_counts().sort_index().items()
        },
    }
    np.savez_compressed(
        run_dir / "predictions_cross_domain.npz",
        probs_canonical=grouped.astype(np.float32), labels=labels,
    )

    # The same predictions under the in-domain-fitted temperature. Temperature
    # does not move the argmax, so accuracy and F1 are identical; only the
    # confidence metrics differ. Reporting both is what makes it possible to say
    # whether an in-domain calibration fix survives the domain shift.
    scaled = None
    if temperature:
        grouped_t, _ = _grouped(temperature)
        scaled = mmod.evaluate_classification(labels, grouped_t.argmax(1), canon_classes)
        scaled["probabilistic"] = mmod.probabilistic_metrics(labels, grouped_t)
        scaled["selective_prediction"] = mmod.confidence_abstention_curve(labels, grouped_t)
        scaled["temperature"] = temperature
        scaled["protocol"] = dict(out["protocol"])
        scaled["protocol"]["temperature_source"] = (
            "fitted on the in-domain validation split, applied unchanged out of domain"
        )
    return out, scaled


def _assert_reportable(results: dict, experiment_id: str) -> None:
    """Refuse to write a result containing a non-finite reported metric.

    A NaN model still produces *finite* accuracy and F1 -- it predicts one
    constant class, which scores near the majority-class rate rather than zero.
    So this is not the primary guard (``assert_finite_state`` is); it catches
    the probabilistic metrics, where NaN logits do propagate into NaN
    log-likelihood, and any future metric that behaves the same way.
    """
    bad: list[str] = []
    for eval_name, block in results.get("evaluations", {}).items():
        for key in ("accuracy", "macro_f1", "weighted_f1", "balanced_accuracy"):
            value = block.get(key)
            if value is not None and not math.isfinite(value):
                bad.append(f"{eval_name}.{key}={value}")
        for key, value in (block.get("probabilistic") or {}).items():
            if isinstance(value, float) and not math.isfinite(value):
                bad.append(f"{eval_name}.probabilistic.{key}={value}")
    if bad:
        raise RuntimeError(
            f"{experiment_id}: {len(bad)} reported metric(s) are not finite "
            f"({bad[:4]}). Refusing to write a result file that would be pooled "
            "into a paper mean."
        )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
