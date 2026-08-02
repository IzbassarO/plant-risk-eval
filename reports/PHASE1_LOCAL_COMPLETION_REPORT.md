# Phase-1 LOCAL Completion Report

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition*  
**Task:** complete the remaining Phase-1 **data prerequisites** locally (macOS, repository-only) with one reproducible command.  
**Generated:** 2026-07-30T07:53:23Z  
**No model training was performed.** **No scientific performance result was produced or claimed.** **No disease-to-action mapping row was automatically approved.**

## A. Overall status: **DATA-COMPLETE — human review pending (gate fail-closed)**

- Data prerequisites materialized: **yes** (PlantVillage pixels: yes; PlantDoc acquisition exhaustive on this filesystem: yes).
- PlantDoc: **2572** distinct images on disk — all 2578 upstream paths fetched; 6 case-variant duplicate(s) are unrepresentable on the case-insensitive macOS filesystem (see §B).
- PlantVillage: **54305** images, pixels materialized, corrupt **0**.
- Leakage gate status: **fail** (fail-closed) — 16 near-duplicate pair(s) pending human review, 0 exact.
- Tests: **103 passed**; Phase-1 checks verdict: **PARTIAL**.
- Data-completion run duration: **≈1:33:20** (06:12→07:46 UTC; dominated by the 2 GB PlantVillage download and the PlantDoc commit archive over a ~0.1–1 MB/s link, fully resumable).

## B. PlantDoc completion

- Source revision (frozen): `5467f6012d78d1c446145d5f582da6096f852ae8`
- Acquisition: GitHub archive for the pinned commit (single file) → raw-CDN fallback for any missing file. Existing valid images preserved; SHA-256 per image.
- Paper-reported count: **2598** (not forced).
- Upstream count at pinned commit: **2578** (train 2342 / test 236).
- Local manifest split: train **2336** / test **236**.
- Filesystem == manifest == valid decodable: **2572 / 2572 / 2572** (fully consistent).
- Corrupt: **0**; duplicate relpaths: **0**; fs<->manifest mismatches: **0 / 0**.
- **Case-collision reconciliation:** all **2578** upstream train/test image paths were fetched, but **6** are case-variant pairs (e.g. `CAR1.jpg` vs `car1.jpg`) that are distinct in the case-sensitive upstream git tree yet **cannot coexist on the case-insensitive macOS (APFS) filesystem**; each pair collapses to one file, so distinct on-disk images = 2578 − 6 = **2572** (evidence: `data/manifests/_plantdoc_case_collisions.json`). This is a filesystem limitation, not a missing download; no count was forced or fabricated.
- Completion vs the strict 2578-path target: **2572/2578** (`complete=False`); acquisition is otherwise **exhaustive** on this filesystem (only the 6 case-variant duplicates are unrepresentable).

## C. PlantVillage completion

- Source revision (frozen): HF `mohanty/PlantVillage` @ `9e97599868962bd0079b8db4b7f1efa9185fa1e7` (color; **not Kaggle**).
- Manifest rows: **54305**; classes: **38** (healthy: **12**).
- Pixels materialized: **yes** (count 54305); corrupt: **0**; zero-byte: **0**.
- Deterministic sample: decode **100/100**, SHA-256 **100/100**.
- leaf_id present / missing: **41111 / 13194** (preserved; never fabricated; missing left missing).

## D. Cross-dataset leakage result (PlantVillage color -> PlantDoc)

- Algorithm / threshold: `imagehash.phash` / Hamming <= **6** (unchanged).
- Indexed: training **54305**, evaluation **2572**; skipped: training **0**, evaluation **0**.
- Exact duplicate pairs: **0** (proposed evaluation exclusions; source files never deleted).
- Near-duplicate pairs: **16** — **pending human review** (never auto-approved).

## E. Leakage gate status

- Status: **fail** (exact 0, near 16, excluded 0, unresolved 16).
- Manifest-bound (training SHA `b9acc43637ef…`, evaluation SHA `d77ef4d8b0fa…`).
- Five-state guard test: `reports/leakage_gate_guard_test.json` (all_pass=True).
- The gate **fails closed**: it cannot report `pass` while any image is skipped, any exact pair is unresolved, or any near-duplicate remains pending.

## F. Test results

- `python -m pytest -q`: **103 passed**, 0 failed (exit 0).

## G. Remaining human review

- Disease->action mapping: **28 rows**, needs_review **28**, approved **0** (unchanged; none auto-approved).
- Near-duplicate cross-dataset pairs pending: **16** (`reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md`).
- A ReviewedHarmMatrix must still be authored + approved before harm-weighted evaluation (out of Phase-1 data scope).

## H. Phase-1 check verdict

- `scripts/run_phase1_checks.sh`: verdict **PARTIAL** (exit 2; exit 2 == PARTIAL, not an execution error).

## I. Changed / produced files

- `data/manifests/plantdoc_manifest.csv`, `plantdoc_summary.json`, `plantdoc_source_snapshot.json`
- `data/manifests/plantvillage_manifest.csv`, `plantvillage_summary.json`, `plantvillage_source_snapshot.json`
- `data/indexes/phash_index_plantvillage.csv`, `phash_index_plantdoc.csv`, `phash_index_meta.json`
- `data/exclusions/cross_dataset_exact_exclusions.csv`
- `reports/leakage_plantvillage_vs_plantdoc_pairs.csv`, `…_summary.json`
- `reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md`, `reports/leakage_gate.json`, `reports/leakage_gate_guard_test.json`
- `reports/PLANTDOC_COUNT_RECONCILIATION.md` (appended), `reports/phase1_local_run.log`
- `reports/PHASE1_LOCAL_COMPLETION_REPORT.md` (this file), `phase1_return_package.zip`

## J. Exact next action

- **Data acquisition is complete.** The only remaining blocker is human review: the leakage gate is `fail` (fail-closed) because **16 near-duplicate pair(s)** are pending adjudication (near-duplicates are never auto-excluded).
  1. Adjudicate `reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md` (mark each pair keep/exclude with a reason).
  2. Record confirmed cross-dataset duplicates in `data/exclusions/cross_dataset_exact_exclusions.csv` (evaluation-side exclusions).
  3. Re-run the gate: `python scripts/run_phase1_local.py --steps leakage,gate` → expect `pass` once no unresolved pairs remain.
  4. Separately (non-data): review + approve the 28-row disease->action mapping and author + approve a ReviewedHarmMatrix.

## K. Explicit statements

- "No model training was performed."
- "No scientific performance result was produced or claimed."
- "No disease-to-action mapping row was automatically approved."
