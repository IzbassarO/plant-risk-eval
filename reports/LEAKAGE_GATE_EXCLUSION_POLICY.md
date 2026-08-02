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

## How rule (3) is implemented (schema 1.1)

Until 2026-08-02 rule (3) was written here but **not implemented**: `compute_gate()` derived
`unresolved = detected − excluded`, which silently equated "resolved" with "excluded". Under that
arithmetic a pair a reviewer inspected and judged independent still counted as unresolved, so the
gate could never reach `pass` no matter what a human decided — the only way out would have been to
record false exclusions. That was a defect in the code, not a safety property.

Gate schema **1.1** implements the rule as written:

```
unresolved = max(0, detected − excluded_pair_count − resolved_pair_count)
```

`resolved_pair_count` comes from `summarize_near_review()`, which reads the human adjudication CSV
and credits a pair only when **all** of the following hold:

- the row matches an authoritative flagged near pair by `(training_relpath, evaluation_relpath)`
  — pair identity comes from the pHash pair table, never from filenames;
- `human_decision` is non-blank and in the allowed vocabulary;
- `human_decision` is not `uncertain`;
- `final_disposition` is `keep` or `exclude_evaluation` (never `needs_secondary_review`);
- if the disposition is `exclude_evaluation`, the pair **also appears** in
  `cross_dataset_reviewed_exclusions.csv` — an exclusion that was never propagated has no
  downstream effect and therefore resolves nothing.

Everything else credits zero. A flagged pair with no review row at all is unresolved. Omitting the
review file entirely resolves nothing, so the default posture stays fail-closed. A schema-1.0 gate
file is now **rejected** rather than reinterpreted, because the meaning of `unresolved_pair_count`
changed.

Covered by `tests/test_near_duplicate_decisions.py` (pending, uncertain, deferred, unknown
vocabulary, un-propagated exclusion, unmatched pair, missing row, missing file) and
`tests/test_leakage_gate.py`.

## Current state (2026-08-02; not forced)

- Exact cross-dataset pairs: **0** (exact file has no rows; contains no near pair — compliant).
- pHash-near pairs: **16**, all adjudicated by `human_reviewer_1` on `2026-08-02T21:10:00+05:00`
  → **16 resolved**, `unresolved = 0`.
- Dispositions: **16 `keep`**, **0 `exclude_evaluation`**, 0 uncertain, 0 deferred.
- Reviewed-exclusions file: **header only** — correct, because no pair was excluded. Writing a row
  there would misrepresent a keep decision as an exclusion.
- Skipped images: **0** on both sides.
- Gate status: **`pass`**.

The decisions and their reasons are recorded in
`reports/PHASE1_HUMAN_DECISIONS_2026-08-02.md`. The gate reached `pass` because a human resolved
every flagged pair after visual inspection — no count was edited, no exclusion was invented, and
no status was overridden.

**Note:** a passing leakage gate authorises *cross-dataset evaluation*; it does not mean Phase 1 is
complete. 17 PlantDoc disease mappings remain unreviewed and the PlantVillage action mapping has
not been authored, so `scripts/validate_phase1_review.py` still reports `BLOCKED`.
