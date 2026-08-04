#!/usr/bin/env python3
"""Run one ICA 2026 training experiment from a config file.

The experiment dataset lock is validated before anything else happens. If any
locked digest, identity set, count, label, split, or mapping has changed, the
run aborts before a single batch is loaded.

    python scripts/ica26_train.py --config experiments/ica26/configs/pv_resnet50_s42.yaml

Exit codes: 0 completed, 1 training failed, 2 the dataset lock did not validate.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ica26.experiments import lock as L  # noqa: E402
from ica26.experiments.train import ExperimentConfig, train_one_run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="path to an experiment YAML")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--out-root", default="experiments/ica26")
    ap.add_argument("--check-pixels", action="store_true",
                    help="also confirm every manifest row resolves to a file on disk")
    ap.add_argument("--skip-lock-validation", action="store_true",
                    help=argparse.SUPPRESS)  # deliberately undocumented; not for results
    args = ap.parse_args()

    print("=" * 78)
    print("ICA 2026 experiment runner")
    print("=" * 78)

    if args.skip_lock_validation:
        print("WARNING: dataset lock validation skipped. Any result produced by this "
              "run is NOT reportable.", file=sys.stderr)
        lock_digest = None
    else:
        print("[lock] validating the ICA 2026 paper experiment dataset lock ...")
        try:
            report = L.require_valid_lock(REPO, check_pixels=args.check_pixels)
        except L.LockValidationError as exc:
            print(f"\nABORT: {exc}", file=sys.stderr)
            return 2
        lock_digest = report["lock_digest"]
        print(f"[lock] VALID  digest={lock_digest}")

    cfg = ExperimentConfig.from_yaml(args.config)
    print(f"[config] {args.config}")
    print(f"[config] {json.dumps(cfg.to_dict(), sort_keys=True)}")

    try:
        results = train_one_run(
            cfg,
            repo_root=REPO,
            out_root=REPO / args.out_root,
            device_pref=args.device,
            lock_digest=lock_digest,
            git_commit=L.git_commit(REPO),
        )
    except Exception:
        traceback.print_exc()
        return 1

    ev = results["evaluations"]
    print("-" * 78)
    print(f"RESULT {cfg.experiment_id}")
    for name, block in ev.items():
        print(f"  {name}: n={block['n_samples']} acc={block['accuracy']:.4f} "
              f"macro_f1={block['macro_f1']:.4f}")
    print("-" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
