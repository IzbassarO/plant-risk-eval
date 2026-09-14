#!/usr/bin/env python3
"""In-domain performance restricted to the shared cross-domain label space.

    python scripts/ica26_shared_space_control.py
    python scripts/ica26_shared_space_control.py --check

The paper's headline drop compares a 38-way in-domain task with a 21-way
cross-domain one, so it mixes domain shift with a change in task difficulty.
This control removes the second term: PlantVillage test images are scored
through *exactly* the cross-domain pipeline --- the same canonical-class
summation, the same renormalisation over the shared classes, the same fixed
label space --- and only the images whose class falls in the shared space are
kept. The comparison then becomes 21-way to 21-way, and what remains between it
and the cross-domain number is domain shift alone.

No training is involved. It reuses the saved PlantVillage test logits, so it
measures the same checkpoints the paper already reports.

Writes ``experiments/ica26/metrics/shared_space_control.json``.

Exit codes: 0 written / verified, 1 a precondition failed or --check differed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ica26.experiments.mapping import load_mapping  # noqa: E402
from ica26.experiments import metrics as mmod  # noqa: E402

RUNS = REPO / "experiments/ica26/runs"
METRICS = REPO / "experiments/ica26/metrics"
OUT = METRICS / "shared_space_control.json"

MODEL_ORDER = ["resnet50", "efficientnet_b0", "mobilenet_v3_small"]
MODEL_DISPLAY = {
    "resnet50": "ResNet-50",
    "efficientnet_b0": "EfficientNet-B0",
    "mobilenet_v3_small": "MobileNetV3-Small",
}
SEEDS = [42, 1337, 2026]
TOLERANCE = 1e-9


def evaluate_one(run_id: str, mapping) -> dict | None:
    """Score one run's PlantVillage test logits over the shared space."""
    run_dir = RUNS / run_id
    dump = run_dir / "predictions_in_domain_test.npz"
    result_path = run_dir / "result.json"
    if not (dump.exists() and result_path.exists()):
        return None

    result = json.loads(result_path.read_text())
    source_classes = result["dataset"]["classes"]
    source_to_idx = {c: i for i, c in enumerate(source_classes)}

    data = np.load(dump)
    logits, labels = data["logits"], data["labels"].astype(np.int64)

    # Sanity gate: the dump must reproduce the reported in-domain number, or it
    # does not describe the run whose name it carries.
    reported = result["evaluations"]["in_domain_test"]
    recomputed_acc = float((logits.argmax(1) == labels).mean())
    if abs(recomputed_acc - reported["accuracy"]) > TOLERANCE:
        raise RuntimeError(
            f"{run_id}: dump accuracy {recomputed_acc:.10f} != reported "
            f"{reported['accuracy']:.10f}; the dump and result disagree"
        )

    canon_classes = mapping.canonical_classes
    canon_to_idx = {c: i for i, c in enumerate(canon_classes)}

    # PlantVillage source class -> canonical class, from the frozen mapping.
    source_to_canon: dict[int, int] = {}
    for canonical, source_labels in mapping.canonical_to_plantvillage.items():
        for name in source_labels:
            if name in source_to_idx:
                source_to_canon[source_to_idx[name]] = canon_to_idx[canonical]

    # Keep only test images whose own class is in the shared space.
    keep = np.array([lbl in source_to_canon for lbl in labels], dtype=bool)
    if not keep.any():
        return None
    kept_logits = logits[keep]
    y_true = np.array([source_to_canon[int(l)] for l in labels[keep]], dtype=np.int64)

    # The same grouping and renormalisation the cross-domain evaluation uses.
    probs = np.exp(kept_logits - kept_logits.max(axis=1, keepdims=True))
    probs /= probs.sum(axis=1, keepdims=True)
    grouped = np.zeros((probs.shape[0], len(canon_classes)), dtype=np.float64)
    for canonical, source_labels in mapping.canonical_to_plantvillage.items():
        cols = [source_to_idx[s] for s in source_labels if s in source_to_idx]
        if cols:
            grouped[:, canon_to_idx[canonical]] = probs[:, cols].sum(axis=1)
    mass = grouped.sum(axis=1, keepdims=True)
    retained = float(mass.mean())
    grouped /= np.maximum(mass, 1e-12)

    out = mmod.evaluate_classification(y_true, grouped.argmax(1), canon_classes)
    out["probabilistic"] = mmod.probabilistic_metrics(y_true, grouped)
    return {
        "run_id": run_id,
        "n_evaluated": int(keep.sum()),
        "n_in_domain_test_total": int(labels.size),
        "n_shared_classes": len(canon_classes),
        "n_classes_present": int(len(set(y_true.tolist()))),
        "mean_retained_probability_mass_before_renormalisation": round(retained, 6),
        "accuracy": out["accuracy"],
        "macro_f1": out["macro_f1"],
        "weighted_f1": out["weighted_f1"],
        "balanced_accuracy": out["balanced_accuracy"],
    }


def build() -> dict:
    mapping = load_mapping(REPO)
    per_run: dict[str, dict] = {}
    for model in MODEL_ORDER:
        for seed in SEEDS:
            run_id = f"pv_{model}_s{seed}"
            entry = evaluate_one(run_id, mapping)
            if entry:
                per_run[run_id] = entry

    # Paired decomposition: for each seed, the same checkpoint scored on the
    # shared space in domain and out of domain. Averaging the per-seed drop
    # keeps the pairing, which is what makes it a per-model quantity.
    summary = {}
    for model in MODEL_ORDER:
        in_shared, cross, drops = [], [], []
        for seed in SEEDS:
            entry = per_run.get(f"pv_{model}_s{seed}")
            res_path = METRICS / f"pv_{model}_s{seed}.json"
            if not (entry and res_path.exists()):
                continue
            xd = json.loads(res_path.read_text())["evaluations"].get(
                "cross_domain_plantdoc_core")
            if not xd:
                continue
            in_shared.append(entry["macro_f1"])
            cross.append(xd["macro_f1"])
            drops.append((entry["macro_f1"] - xd["macro_f1"]) / entry["macro_f1"] * 100)
        if in_shared:
            summary[model] = {
                "model": MODEL_DISPLAY[model],
                "n_seeds": len(in_shared),
                "macro_f1_in_domain_shared_mean": float(np.mean(in_shared)),
                "macro_f1_in_domain_shared_sd":
                    float(np.std(in_shared, ddof=1)) if len(in_shared) > 1 else None,
                "macro_f1_cross_domain_mean": float(np.mean(cross)),
                "relative_drop_percent_mean": float(np.mean(drops)),
                "relative_drop_percent_sd":
                    float(np.std(drops, ddof=1)) if len(drops) > 1 else None,
            }

    return {
        "schema": "ica26.shared_space_control/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc)
                            .replace(microsecond=0).isoformat(),
        "description": (
            "PlantVillage in-domain test performance restricted to the shared "
            "cross-domain label space, scored through the identical grouping and "
            "renormalisation used cross-domain. Holds task difficulty fixed at "
            "21 classes so the remaining gap is domain shift alone."
        ),
        "summary": summary,
        "per_run": per_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="recompute and compare against the committed file")
    args = ap.parse_args()

    payload = build()
    if not payload["per_run"]:
        print("no PlantVillage test dumps available", file=sys.stderr)
        return 1

    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT}", file=sys.stderr)
            return 1
        existing = json.loads(OUT.read_text())
        a = {k: v for k, v in existing.items() if k != "created_at_utc"}
        b = {k: v for k, v in payload.items() if k != "created_at_utc"}
        if a != b:
            print("CHECK FAILED: recomputed control differs", file=sys.stderr)
            return 1
        print("check OK")
        return 0

    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    any_run = next(iter(payload["per_run"].values()))
    print(f"wrote {OUT.relative_to(REPO)}")
    print(f"evaluated {any_run['n_evaluated']} of "
          f"{any_run['n_in_domain_test_total']} PlantVillage test images "
          f"over {any_run['n_shared_classes']} shared classes")
    print()
    print(f"{'model':20s} {'21-way in-dom':>14s} {'21-way cross':>13s} {'rel. drop':>11s}")
    for model in MODEL_ORDER:
        s = payload["summary"].get(model)
        if not s:
            continue
        print(f"{s['model']:20s} {s['macro_f1_in_domain_shared_mean']:14.4f} "
              f"{s['macro_f1_cross_domain_mean']:13.4f} "
              f"{s['relative_drop_percent_mean']:10.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
