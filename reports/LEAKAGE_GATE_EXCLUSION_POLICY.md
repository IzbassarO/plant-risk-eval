# Leakage-Gate Exclusion Policy (two-file model)

_Specifies how the cross-dataset leakage gate (`reports/leakage_gate.json`) consumes
exclusion artifacts. This is a governance/spec document; it does **not** change the
current gate status, and the gate is **not** forced to pass._

## Two exclusion artifacts — distinct semantics

| File | Contains | Populated by |
|---|---|---|
| `data/exclusions/cross_dataset_exact_exclusions.csv` | **hash-exact or verified content-exact** cross-dataset duplicates only (pHash Hamming distance 0, or SHA-256 / decoded-pixel identity). | The automated leakage step (an exact match is machine-verifiable). |
| `data/exclusions/cross_dataset_reviewed_exclusions.csv` | **human-reviewed near-duplicates that a reviewer decided to exclude.** One row per confirmed exclusion, carrying the human decision + reason + reviewer + timestamp + the source review file. | A **human**, after adjudicating `data/exclusions/cross_dataset_near_duplicate_review.csv` (visual contact sheets in `reports/near_duplicate_contact_sheets/`). |

Rules:

- A **pending or uncertain** pHash-near pair is **never** written to either exclusion
  file. It stays in the review CSV until a human decides.
- The exact file must **never** contain a pHash-near (distance > 0) pair.
- The reviewed file must **never** contain a pair the human has not explicitly decided
  to exclude.

## `status = pass` requires ALL of

1. **0 skipped images** on both sides (every manifest image was hashable).
2. **Every exact pair excluded** — recorded in `cross_dataset_exact_exclusions.csv`.
3. **Every pHash-near pair resolved** — each of the flagged near pairs has a non-blank,
   non-`uncertain` `human_decision` in the review CSV, i.e. **0 pending and 0 uncertain**.
   Pairs decided `exclude_evaluation` are copied to `cross_dataset_reviewed_exclusions.csv`;
   pairs decided to keep are resolved but not excluded.
4. Manifest binding intact (training/evaluation manifest SHA-256 unchanged since the gate
   was generated).

If any of (1)–(4) fails, the gate is `fail` or `incomplete` — **fail-closed**.

## Current state (do not force)

- Exact cross-dataset pairs: **0** (exact file has no rows; contains no near pair — compliant).
- pHash-near pairs: **16**, all `review_status=pending` → **0 resolved**, so `unresolved = 16`.
- Reviewed-exclusions file: **header only** (no human decisions exist yet).
- Gate status: **`fail`** (fail-closed) — correct while near pairs are pending.

**Next:** a human adjudicates the 16 near pairs (see `reports/NEAR_DUPLICATE_HUMAN_REVIEW.md`
and the contact sheets), records excludes in `cross_dataset_reviewed_exclusions.csv`, then
`python scripts/run_phase1_local.py --steps leakage,gate`. The gate may reach `pass` only once
no near pair is pending/uncertain and every exact pair is excluded. No count here was changed
and the gate was not forced to pass.
