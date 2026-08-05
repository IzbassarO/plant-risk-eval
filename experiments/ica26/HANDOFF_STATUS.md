# ICA 2026 — matrix status

Updated 2026-08-05T08:50Z. Branch `claude/ica26-training-launch`.

**Guard confirmed working in flight.** The relaunched `pv_efficientnet_b0_s1337`
reproduced the failed run's training numbers exactly (epoch 1 loss 0.926426,
accuracy 0.93498) but now reaches val macro-F1 0.9876 instead of 0.0006, with
`skipped_nonfinite_steps` incrementing by one per epoch. A *single* overflowing
gradient per epoch was enough to kill the original run. At epoch 3 it tracks
seed 42 closely (0.9922 vs 0.9914). This run will finish with a non-zero skip
count and is therefore reported in the paper rather than pooled silently — the
`\SkippedStepsNote` macro does that automatically.

## Runs (18 planned = 6 configs x seeds 42/1337/2026)

**Complete and verified clean (9)** — archived with digests in
`reports/ica26_model_preservation.json`, verify with
`python scripts/ica26_preserve_models.py --verify`:

- seed 42: all six.
- seed 1337: `pdc_mobilenet_v3_small`, `pv_mobilenet_v3_small`,
  `pdc_efficientnet_b0`.

**Queued (9)**, launcher pid 71505, `caffeinate` pid 71516 attached via `-w`:

1. `pv_efficientnet_b0_s1337` (running, restarted 08:12Z after the NaN failure)
2. `pv_resnet50_s1337`
3. `pdc_resnet50_s1337`
4. seed 2026: all six, cheap-first order

Rough estimate to completion: ~9.5 h from 08:12Z.

## What failed and why

`pv_efficientnet_b0_s1337` died in epoch 1 with all-NaN weights. Cause: no
`GradScaler` on MPS, so an overflowing fp16 gradient reached AdamW, whose
`m/sqrt(v)` gave Inf/Inf = NaN, permanently killing the parameter. It was silent
— train loss 0.9264 and train accuracy 0.9350 looked healthy; only
`val_accuracy` 0.0115 (vs 0.9886 for seed 42) gave it away.

Fixed in `src/ica26/experiments/train.py` by skipping optimiser steps with a
non-finite gradient norm, **not** by changing precision (that would break
comparability with the validated seed-42 runs). Verified a no-op: re-running
`pdc_mobilenet_v3_small_s42` reproduced a byte-identical checkpoint
(`sha256 9027e979…`) with 0 of 363 steps skipped.

The old run directory was deleted; it never wrote a metrics file.

## Monitoring / recovery

- `tail -f experiments/ica26/logs/run_matrix.log` — per-run start/finish.
- If a run aborts on `assert_finite_state` or the >1% skip guard: log the
  diagnosis, `rm -rf experiments/ica26/runs/<id>`, requeue that one run with
  `bash scripts/ica26_run_matrix.sh <id>`, let the rest continue.
- Do **not** change protocol, lock, mapping, or configs to make a run pass.

## Paper state

Sections 1–4 and 8–10 drafted; 5–7 (Results) intentionally not written until the
matrix finishes. Every number is a generated macro — see `paper/README.md`.
Currently 13 pages (limit 12–15) plus a 6-page supplement.

Rebuild inputs with `python scripts/ica26_build_tables.py`,
`python scripts/ica26_build_paper_macros.py`. Full build (compiles):
`bash scripts/ica26_build_paper.sh`.

## Open decisions for the author

- Scope diverges from `PROJECT_BRIEF.md` (action-level framing has no verified
  results, BLOCK-07). See `paper/README.md` § Scope divergence.
- Any run finishing with non-zero `skipped_nonfinite_steps` must be reported in
  the paper, not silently pooled. None so far.
