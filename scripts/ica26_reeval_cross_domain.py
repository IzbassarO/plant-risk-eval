#!/usr/bin/env python3
"""Recompute cross-domain evaluation from saved checkpoints, without retraining.

The first matrix reported a single cross-domain block that had the
in-domain-fitted temperature already applied, and no unscaled baseline. That made
it impossible to say whether an in-domain calibration fix survives the domain
shift. This recomputes both variants from the checkpoint each run already saved.

Accuracy, F1, and the confusion matrix are unaffected by temperature -- it does
not move the argmax -- so only the confidence metrics change. The recomputed
unscaled block is verified against the stored one on exactly those invariants,
and the script refuses to write if they disagree.

    python scripts/ica26_reeval_cross_domain.py

Exit codes: 0 all runs updated, 1 a run failed or an invariant broke.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import torch  # noqa: E402

from ica26.experiments import lock as L  # noqa: E402
from ica26.experiments import models as models_mod  # noqa: E402
from ica26.experiments.mapping import load_mapping  # noqa: E402
from ica26.experiments.train import (  # noqa: E402
    ExperimentConfig,
    build_transforms,
    evaluate_cross_domain,
    prepare_data,
)

PV_RUNS = ["pv_resnet50_s42", "pv_efficientnet_b0_s42", "pv_mobilenet_v3_small_s42"]


def reeval(run_id: str, device_pref: str = "auto") -> bool:
    run_dir = REPO / "experiments/ica26/runs" / run_id
    metrics_path = REPO / "experiments/ica26/metrics" / f"{run_id}.json"
    ckpt_path = run_dir / "best.pt"
    for p in (metrics_path, ckpt_path):
        if not p.exists():
            print(f"  {run_id}: missing {p}", file=sys.stderr)
            return False

    payload = json.loads(metrics_path.read_text())
    cfg = ExperimentConfig(**payload["config"])
    hw = models_mod.select_device(device_pref)

    prepared = prepare_data(cfg, REPO)
    _, eval_tf = build_transforms(cfg.image_size)
    model = models_mod.build_model(cfg.model, len(prepared.classes), pretrained=False)
    state = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model_state"])
    model.to(hw.device)

    if state.get("class_to_idx") != prepared.class_to_idx:
        print(f"  {run_id}: checkpoint class index differs from the manifest index",
              file=sys.stderr)
        return False

    temperature = payload.get("calibration", {}).get("temperature")
    raw, scaled = evaluate_cross_domain(
        model, load_mapping(REPO), prepared.class_to_idx, eval_tf, hw.device, cfg,
        repo_root=REPO, temperature=temperature, run_dir=run_dir,
    )

    # The stored block was temperature-scaled, so its confidence metrics should
    # match the newly-scaled variant, and its argmax-derived metrics should match
    # both. Verify the invariants before overwriting anything.
    stored = payload["evaluations"].get("cross_domain_plantdoc_core")
    if stored is not None:
        for field in ("accuracy", "macro_f1", "n_samples"):
            for candidate in (raw, scaled or raw):
                if abs(float(stored[field]) - float(candidate[field])) > 1e-9:
                    print(f"  {run_id}: {field} changed under re-evaluation "
                          f"({stored[field]} -> {candidate[field]}); refusing to write",
                          file=sys.stderr)
                    return False

    payload["evaluations"]["cross_domain_plantdoc_core"] = raw
    if scaled is not None:
        payload["evaluations"]["cross_domain_plantdoc_core_temperature_scaled"] = scaled
    payload["cross_domain_reevaluated"] = {
        "schema": "ica26.cross_domain_reevaluation/1",
        "reason": ("the original run reported only the temperature-scaled block; "
                   "both the unscaled and scaled variants are now recorded"),
        "temperature_applied_to_scaled_block": temperature,
    }

    text = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    metrics_path.write_text(text)
    (run_dir / "result.json").write_text(text)

    ece_raw = raw["probabilistic"]["expected_calibration_error"]
    ece_scaled = scaled["probabilistic"]["expected_calibration_error"] if scaled else float("nan")
    print(f"  {run_id}: acc={raw['accuracy']:.4f} "
          f"ECE unscaled={ece_raw:.4f} -> T-scaled={ece_scaled:.4f} (T={temperature:.4f})")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("runs", nargs="*", default=None)
    args = ap.parse_args()

    try:
        L.require_valid_lock(REPO)
    except L.LockValidationError as exc:
        print(f"ABORT: {exc}", file=sys.stderr)
        return 1

    runs = args.runs or PV_RUNS
    print(f"re-evaluating cross-domain for {len(runs)} run(s)")
    ok = all(reeval(r, args.device) for r in runs)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
