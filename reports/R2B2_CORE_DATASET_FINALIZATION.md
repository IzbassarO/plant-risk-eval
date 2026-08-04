# R2B.2 — Core Dataset V1 technical closure

**Starting commit:** `d4cbb89b18882e5cc38ee537826868cf13292faa`
**Branch:** `claude/r2b2-core-dataset-finalization`

## Scope and outcome

This record covers the R2B.2 work: the conservative exclusion of G07/G08/G10 from
Core Dataset V1, the replacement of the fragile pHash search, exact PlantVillage
manifest reconstruction, fresh-clone packet reproducibility, hardened
second-review validation, and the separation of Core Dataset V1 from Risk
Evaluation Layer V1.

**Core Dataset V1 is NOT frozen.** It reports `ready_for_independent_audit`: every
mechanical condition is satisfied and the two remaining blockers are the
independent audit sign-off and the freeze approval, which are exactly the two
decisions this work must not take for itself.

**No training was started.** No checkpoint, metric, or paper table exists.

**Risk Evaluation Layer V1 is not ready**, and its incompleteness says nothing
about the Core dataset's validity.

---

## 1. Operator conservative exclusion decision

The dataset owner and research lead recorded a data-quality decision, not a
diagnosis:

| Field | Value |
| --- | --- |
| Decision | `conservative_exclusion` |
| Basis | `insufficient_independent_diagnostic_evidence` |
| Reviewer role | `dataset_owner_research_lead` |
| Reviewer id | `dataset_owner_1` (see the note below) |
| Decided at | `2026-08-04T12:19:14+05:00` |
| Reviewed commit | `d4cbb89b18882e5cc38ee537826868cf13292faa` |
| Artifact | `data/exclusions/core_dataset_v1_conservative_exclusions.csv` |
| Schema | `ica26.datasets.conservative_exclusion/1` |

> **Reviewer identifier — deviation from the brief.** The brief specified
> `reviewer_id: izbassar`. This repository's anonymity gate hardcodes
> `\bizbassar\b` as a forbidden pattern in paper-facing artifacts, explicitly
> "to protect the double-blind submission", and the decision table
> (`data/exclusions/*.csv`) is inside that scanned set. Writing the real
> username there would have deanonymised a blind submission and blocked the
> `anonymity` condition. The pseudonymous `dataset_owner_1` is recorded instead;
> the role, basis, rationale, timestamp, commit and every identity binding are
> exactly as instructed. Changing the identifier is a one-line re-record if the
> owner wants to waive their own anonymity.

### Exactly what was excluded

| Group | Member | Effective record id | Byte SHA-256 | Prior split | Prior canonical label |
| --- | --- | --- | --- | --- | --- |
| G07 | `G07-m2` | `erec-5373969d2572bb1d` | `9dd93b4217495fbb725cfdded86d3dc5f98955c9616fff5323be1a00df17be8b` | train | Potato leaf late blight |
| G08 | `G08-m2` | `erec-7692837fe06b10af` | `a981ee59e5e1dcafd0d225f74369a05969200352c17743318c31987083ab6f4c` | train | Tomato leaf late blight |
| G10 | `G10-m2` | `erec-80b6c8a97fcda29a` | `e23a29c94b58aac28e92f57f95eb6f53e99c874323cb2b90ebd327085721574e` | train | Tomato leaf bacterial spot |

Active relative paths:

- G07 `train/Potato leaf early blight/irish-blight-symptoms-on-potato-leaves-atmf8b.jpg`
- G08 `train/Potato leaf early blight/5816740026_d42ef24413_Phytophthora-Infestans.jpg`
- G10 `train/Tomato Septoria leaf spot/tomato_V8.jpg`

### What this decision is not

It records no diagnosis, confirms nothing about what the three images depict, and
does not close the scientific question. No `agree` second review was created; the
review packet still reports `status: pending` for G07/G08/G10, and the artifact
`human_review/plantdoc_label_second_review/second_review.json` does not exist. The
exclusion makes the unresolved diagnosis unnecessary *for Core Dataset V1*, and
the historical evidence is preserved unchanged.

### Layering (history is not rewritten)

```
plantdoc_manifest.csv                        2,578   acquired source
  -> plantdoc_effective_manifest.csv         2,564   after R2B duplicate remediation
    -> plantdoc_core_effective_manifest.csv  2,561   after conservative exclusion
```

The R2B resolution table and effective manifest are byte-unchanged. The
adjudication still records `keep_one_record` / `retain_canonical` for G07/G08/G10,
because that is what the first reviewer decided.

---

## 2. Before / after reconciliation

Every figure below was computed independently and reconciled, not assumed.

| Quantity | Before | After |
| --- | ---: | ---: |
| Source PlantDoc records | 2,578 | 2,578 |
| Effective (R2B) records | 2,564 | 2,564 |
| **Core effective records** | — | **2,561** |
| Retained duplicate-group records | 10 | 7 |
| Excluded reviewed records | 14 | 17 |
| Non-reviewed records | 2,554 | 2,554 |
| Core train split | 2,339 | **2,336** |
| Core test split | 225 | **225** |
| Distinct classes | 28 | 28 |
| Surviving exact-duplicate groups | 0 | 0 |
| Cross-split exact duplicates | 0 | 0 |
| Contradictory-label duplicate groups | 0 | 0 |

All three excluded records were on the effective **train** split, so `test` is
untouched. The 2,336 / 225 split was verified by counting the materialised Core
manifest, not by subtracting an expected number.

### Class-count changes

Only the three classes that owned an excluded record changed, each by one:

| Class | Before | After |
| --- | ---: | ---: |
| Potato leaf late blight | 101 | 100 |
| Tomato leaf bacterial spot | 110 | 109 |
| Tomato leaf late blight | 112 | 111 |

No class was emptied; the vocabulary remains 28 classes.

### Non-reviewed invariance

All **2,554** records not covered by any human decision are byte-identical to the
acquired source manifest, field for field. This is asserted directly in
`tests/test_core_conservative_exclusions.py::test_all_2554_non_reviewed_records_are_untouched`
and re-derived by `verify_core_records`, which reports
`non_reviewed_records_unchanged: true`. No source image was deleted and no
authoritative image byte was modified.

---

## 3. pHash: what changed and why

### The defect

The recursive striped pigeonhole partition was **complete but not bounded**. A
pair that agrees on more than one block is re-visited through each of them, so a
dense cluster of mutually-near hashes amplifies the traversal. Measured on this
machine at threshold 6 over 64-bit hashes:

| n (mutually near) | Recursive striped | Scalar brute force |
| ---: | --- | ---: |
| 50 | 0.085 s | 0.048 s |
| 100 | **did not finish in 60 s** | 0.187 s |
| 150 | **did not finish in 60 s** | 0.421 s |
| 200 | **did not finish in 60 s** | 0.734 s |
| 300 | **did not finish in 60 s** | 1.681 s |

An index slower than the scan it replaces — precisely when there is real output
to find — is a liability, so it is gone from the production path entirely. No
recursive striped code remains in `src/`.

### The replacement

Exact chunked brute-force Hamming evaluation over distinct fixed-width hash
values. Hashes are packed into an `(n, words)` uint64 matrix; a block of left
values is XORed against a block of right values, popcounted one 64-bit word at a
time, and pairs within the radius are kept. Intra-dataset evaluates the upper
triangle; cross-dataset evaluates the complete Cartesian product.

### Completeness argument

There is no completeness argument to get wrong, which is the point. Nothing is
pruned and no candidate set is constructed, so every possible distinct-hash pair
receives an exact popcount. The invariant is arithmetic rather than structural:

```
n_distance_evaluations == n_possible_pairs
```

`candidate_search_audit_fields` **refuses** any summary where those disagree, so a
future regression toward pruning cannot quietly publish itself as complete.
Correctness is additionally checked against a scalar oracle
(`brute_force_duplicates`) that shares no code with the implementation — Python
ints and `int.bit_count` rather than numpy words and chunking — so parity is
evidence and not a tautology.

### Complexity and memory — stated plainly

| Property | Value |
| --- | --- |
| Intra-dataset | **O(N² / 2)** exact distance evaluations |
| Cross-dataset | **O(N × M)** exact distance evaluations |
| Output-sensitive | **No** |
| Peak memory | Bounded by the chunk size, independent of input size |
| Chunk budget | 1,048,576 pairs (`DEFAULT_CHUNK_PAIRS`) |

This is **not** subquadratic and does not claim to be. The previous report's
claim that the striped implementation had bounded total work was wrong and has
been withdrawn — `PHASH_EXACT_SCALABILITY_BENCHMARK.md` is superseded by this
section and the benchmark below.

The distinction that matters:

- **output-sensitive methods** do work proportional to what they find, and
  degrade unpredictably when the output is large or the input is adversarial;
- **exact full evaluation** does a fixed, predictable amount of work that depends
  only on the input size — the evaluation count is knowable before the run;
- **bounded peak memory** is a separate property from complexity: the full
  all-pairs matrix is never allocated, so 50 million pairs cost the same working
  set as 500 thousand.

### Benchmark

Deterministic operation counters, not elapsed time, are the regression criterion.

| Fixture | n | Possible pairs | Exact evaluations | Output pairs | Chunks | Chunk dims | Peak chunk pairs | Est. peak bytes | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| sparse (dense-band-near-empty) | 1,000 | 499,500 | 499,500 | 0 | 1 | 1000×1000 | 1,000,000 | 56,000,000 | 0.02 |
| sparse (dense-band-near-empty) | 10,000 | 49,995,000 | 49,995,000 | 0 | 55 | 1024×1024 | 1,048,576 | 58,720,256 | 0.46 |
| dense true-output | 300 | 44,850 | 44,850 | **44,850** | 1 | 300×300 | 90,000 | 5,040,000 | 1.75 |
| acquired corpus (real) | 54,305 × 2,578 | 136,847,443 | 136,847,443 | 16 | 162 | 1024×1024 | 1,048,576 | 58,720,256 | 1.1 |
| Core corpus (real) | 54,305 × 2,561 | 136,630,311 | 136,630,311 | 16 | 162 | 1024×1024 | 1,048,576 | 58,720,256 | 1.1 |

The 300-item dense cluster — the case the previous implementation could not
finish — returns all 44,850 true pairs in 1.75 s. A hundredfold increase in pairs
(1,000 → 10,000 sparse) leaves the peak chunk unchanged, which is the whole point
of chunking.

---

## 4. Real-data leakage, both populations

Both populations were computed separately and neither result was inherited from
the other.

| | Acquired corpus | Core training corpus |
| --- | --- | --- |
| Training records | 54,305 PlantVillage | 54,305 PlantVillage |
| Evaluation records | 2,578 acquired PlantDoc | **2,561 Core PlantDoc** |
| Distinct hashes (train / eval) | 54,283 / 2,521 | 54,283 / 2,517 |
| Exact pairs | **0** | **0** |
| Near pairs (Hamming ≤ 6) | **16** | **16** |
| Resolved decisions | 16 | 16 |
| Unresolved pairs | **0** | **0** |
| Exclusions applied | 0 | 0 |
| Exact distance evaluations | 136,847,443 | 136,630,311 |

**Identity-set differences:** the acquired and Core near-pair identity sets are
equal — 0 pairs only in acquired, 0 only in Core. None of the 16 near pairs
involved a conservatively excluded record, so removing them changed no leakage
decision.

**The 16 human decisions are byte-identical.** The freshly computed acquired
near-pair identities reconcile exactly with the recorded pair table; no review
row, disposition, or exclusion file was written by this verification. Persisted
at `reports/leakage_two_population_report.json` (schema
`ica26.leakage.two_population_report/1`, no wall-clock field).

---

## 5. PlantVillage exact reconstruction

The persisted provenance authenticated the downloaded components well, then bound
the manifest by its own SHA-256. A digest proves only that a file has not changed
since someone hashed it — so a fabricated one-row manifest with a self-consistent
digest passed every check, because nothing ever asked what the file should
contain.

`reconstruct_manifest_identities` now re-derives every record from the pinned
sources alone. The expected record count is a **result** of reconstruction, never
an input to it.

| Property | Result |
| --- | --- |
| Records derived from pinned sources | **54,305** (43,596 train + 10,709 test) |
| Persisted records | 54,305 |
| Missing rows | 0 |
| Additional rows | 0 |
| Duplicated identities | 0 |
| Semantic value mismatches | 0 |
| Deterministic ordering | matches |
| Leaf-map entries | 40,328 |
| Manifest SHA-256 | `b9acc43637ef2e930bd9e5e8a09b1d5025c720d65f9dd3fc9aabdfbd7e399591` |
| Every required image present and digest-verified | yes |

Independently derived per record: identity, relative image path, class label,
split, leaf metadata, and source-component membership. No PlantVillage scientific
label or split was modified.

**Materialization fail-closed.** `pixels_materialized` used `.any()`, so one
materialized image in a 54,305-record manifest reported the whole dataset as
materialized; two of its three call sites also accepted any non-empty string as a
digest. `all_pixels_materialized` now requires **every** record to carry a full
64-character digest, and image verification requires every required file to exist
and match its recorded identity. Absent or unreadable files fail closed.

Refused forgeries (each a test): fabricated one-row manifest, deleted row, added
row, duplicated identity, changed class, changed split, changed leaf metadata,
reordered rows, missing image, only one image present, image not matching its
digest.

---

## 6. Fresh-clone packet reproducibility

A fresh clone failed two tests before reaching governance status. The packet
manifest bound SHA-256 digests for four contact-sheet PNGs that `.gitignore`
excludes, and `--check` discovered the sheet list by **globbing the packet
directory** — so a clone with no PNGs rendered a Markdown file without the sheet
bullets and reported an up-to-date packet as stale.

**Why "regenerate and compare digests" was rejected.** The renderer needs the raw
pixels under the untracked `data/raw/`, and it resolves fonts by absolute macOS
paths, falling back silently to a different bitmap face elsewhere; PNG bytes also
depend on the Pillow and zlib versions. Pinning those digests in a tracked
contract is what made the packet verifiable on exactly one workstation. A fresh
clone cannot regenerate them at all.

**Design chosen** — the convention this repository's sibling packet already used:

- sheet names are derived from the **group count** (12 groups ÷ 3 per sheet = 4
  sheets), never from the filesystem, so the Markdown is identical everywhere;
- `packet_manifest.json` digests the four **tracked text artifacts**, taken from
  their rendered text in memory, so nothing underivable from tracked inputs can
  enter the contract by construction;
- the manifest is itself a rendered artifact compared by `--check`, so a
  hand-edited manifest is still caught;
- the sheets move to a `rendered_derivatives` block recording their logical
  names, renderer configuration and regeneration command — a reader still knows
  what the reviewer looked at;
- rendering failure is reported rather than fatal, and `--no-contact-sheets`
  skips it outright;
- `--check` writes nothing (asserted).

The repository already treated sheet identity as cosmetic — re-paging is
explicitly not identity drift in the near-duplicate packet — so this makes one
convention out of two. The preserved immutable copy under
`human_review/plantdoc_exact_duplicates/original/` is left untouched: its PNG
digests are historical provenance of what a human actually viewed.

---

## 7. Hardened second-review validation

G07/G08/G10 are excluded from Core, so this validator no longer gates the Core
dataset. It still gates the Risk Evaluation Layer, and the observed gaps are
closed:

| Gap | Fix |
| --- | --- |
| Reviewer independence compared raw strings | NFKC-normalised and case-folded, so `HUMAN_REVIEWER_1` no longer bypasses a conflict with `human_reviewer_1` |
| Placeholder match was whole-string only | Tokens matched on word boundaries inside longer text: `TBD`, `TODO`, `unknown`, `unstructured`, `source to be supplied`, `placeholder`, `pending`, `n/a` |
| Qualification could be one character | Minimum length and word count; must name a discipline or role |
| Rationale could be any 40 characters | Must identify the group it is filed under |
| Citations | Structured objects with required fields; arbitrary strings refused |
| One group borrowing another's evidence | Rationale and citations naming another reviewed group are refused |
| Identical rationale / citations across groups | Refused unless `shared_evidence_basis` is explicitly declared **and** each group still carries its own group-specific reasoning |

The embedded-token list is deliberately narrower than the whole-cell list: words
that occur in real prose are excluded, because "confirmed against the latest APS
compendium" is a real sentence and a naive substring rule would reject it. That
case is pinned as a test.

Scientific truth is not inferred by code anywhere in this. The validator refuses
input carrying no evidence — a much smaller claim.

**The Core exclusion artifact does not masquerade as a scientific review.** It
carries no diagnostic verdict, no citation, and no confidence; it is a
`conservative_exclusion` by a `dataset_owner_research_lead`. The Risk Layer
continues to report the scientific second review as **not performed**, and no
shipped code path can write that artifact (asserted directly).

---

## 8. Core / Risk architectural separation

One assessment covered two different questions, and the stricter held the other
hostage: baseline computer-vision training was blocked on a harm matrix it does
not use. It also invited the opposite misreading — "Dataset V1 is not ready"
sounds like the dataset is defective, which the machine evidence contradicts.

### Core Dataset V1 — `ready_for_independent_audit`

Image identities, classification labels, splits, provenance, duplicate and
conservative exclusions, leakage decisions, effective manifests, fingerprints.

14 conditions satisfied, **0 machine blockers**, 2 open decisions:
`open_audit_findings_closed` and `freeze_approval_recorded`.

Core readiness depends on **none** of: action mappings, harm matrix, risk weights,
treatment recommendations, risk-aware evaluation approval. This is tested by
**deletion** rather than inspection — the risk artifacts are removed and the
assessment re-run, and every Core condition must be unchanged. Reading the
condition list would only show the reported set is clean, not that the evaluation
never consults them.

Artifacts: `reports/core_dataset_v1_readiness.json`,
`reports/CORE_DATASET_V1_READINESS.md`.

### Risk Evaluation Layer V1 — `not_ready`

Disease-to-action mappings, PlantVillage action mappings, harm matrix, error
costs, risk-aware metrics, optional independent scientific diagnostic reviews.

4 blockers: `disease_action_mapping_reviewed`,
`plantvillage_action_mapping_coverage`, `harm_matrix_approved`,
`relabel_second_scientific_review`.

Artifacts: `reports/risk_evaluation_layer_v1_readiness.json`,
`reports/RISK_EVALUATION_LAYER_V1_READINESS.md`.

### Training authorization boundary

**Training authorized: NO** — Core Dataset V1 is not frozen. Recorded as machine-
readable data in the Core artifact.

Permitted after an independent audit and a recorded Core freeze approval:
PlantVillage in-domain classification baselines, PlantDoc Core in-domain
classification baselines, model calibration experiments, ordinary classification
metrics, dataset-loading and training-pipeline validation.

Blocked until Risk Evaluation Layer V1 is frozen: harm-weighted model selection,
action-aware training, treatment recommendation, risk-weighted conclusions, final
risk-aware evaluation tables.

The combined `dataset_v1_freeze_readiness` assessment is unchanged in meaning and
remains the authority for the technical freeze workflow.

---

## 9. Commands and exit codes

| Command | Exit | Result |
| --- | ---: | --- |
| `python scripts/apply_core_conservative_exclusions.py --record …` | 0 | recorded 3 exclusions |
| `python scripts/apply_core_conservative_exclusions.py` | 0 | wrote Core manifest, 2,561 records |
| `python scripts/apply_core_conservative_exclusions.py --check` | 0 | matches a fresh rebuild |
| `python scripts/verify_core_and_acquired_leakage.py --out … --persist` | 0 | both populations, 0 unresolved |
| `python scripts/build_plantdoc_duplicate_packet.py --no-contact-sheets` | 0 | 5 tracked artifacts |
| `python scripts/build_plantdoc_duplicate_packet.py --check` | 0 | check OK with no PNGs present |
| `python scripts/build_dataset_v1_freeze_readiness.py` | 1 | not ready (6 human/audit blockers) |
| `python scripts/build_dataset_v1_freeze_readiness.py --check` | 0 | matches current inputs |
| `python scripts/build_core_and_risk_readiness.py` | 0 | Core ready_for_independent_audit |
| `python scripts/build_core_and_risk_readiness.py --check` | 0 | matches current inputs |
| `python -m pytest` | 0 | **1,106 passed** |
| `bash -n scripts/run_phase1_checks.sh` | 0 | shell syntax OK |
| `PYTHON=… bash scripts/run_phase1_checks.sh` | **2** | 11/11 HARD checks pass; scientifically BLOCKED |
| fresh clone → venv → `pytest` | 0 | see below |

`run_phase1_checks.sh` exit **2** is "scientifically BLOCKED", not a hard failure
(which would be exit 1). All eleven mechanical HARD checks pass and the run
reaches the governance status stage, which is the required outcome.

### Test totals

| | Collected | Passed | Failed |
| --- | ---: | ---: | ---: |
| Baseline at `d4cbb89` (isolated checkout) | 957 | 955 | **2** |
| After R2B.2 | **1,106** | **1,106** | **0** |

The two baseline failures were exactly the fresh-clone packet defects
(`test_packet_manifest_hashes_are_correct`,
`test_packet_generation_is_deterministic`).

---

## 10. Remaining conditions before Core Dataset V1 may be frozen

1. **Independent audit sign-off** — `reports/DATASET_V1_AUDIT_SIGNOFF.json`, by an
   auditor independent of the implementer, closing `AUD-EC-005`, `AUD-EC-006`,
   `AUD-EC-007`, `R2B-REMEDIATION`. *Deliberately not produced here.*
2. **Core freeze approval** — `data/manifests/dataset_v1_freeze_approval.json`, a
   governance decision by an accountable owner, bound to the reviewed state.
   *Deliberately not produced here.*

Only after both exist may the technical freeze record be materialised.

### Remaining for Risk Evaluation Layer V1 (independent of the above)

Terminal mapping decisions for 17 PlantDoc classes and all 38 PlantVillage
classes, an approved harm matrix, and — if those three records are ever wanted
back — an independent scientific second review of the G07/G08/G10 relabels.

---

## 11. Explicit statements

- **Core Dataset V1 is not frozen.** No freeze record was created; no freeze
  approval was fabricated.
- **No training was started.** No model was trained, no checkpoint written, no
  metric or paper table produced.
- **No independent audit was conducted and no audit sign-off was created.**
- **No scientific second review was fabricated**, and no `agree` decision was
  recorded for G07, G08 or G10.
- **No source image byte was modified or deleted.**
