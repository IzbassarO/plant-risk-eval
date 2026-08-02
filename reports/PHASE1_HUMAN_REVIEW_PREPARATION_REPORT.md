# Phase-1 Human-Review Preparation Report

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation
Framework for Deep Learning-Based Plant Disease Recognition*
**Task:** assemble the Phase-1 **human review packet** — resolve the PlantDoc
case-collision representation, build a visual near-duplicate review packet, correct the
exclusion-artifact semantics, and prepare a mapping checklist. **No decisions were made.**
**Generated:** 2026-07-30. Reproducible via `python scripts/prepare_human_review.py`.

---

## 1 · PlantDoc collision-pair findings

Both members of all six case-collision pairs were extracted from the authoritative commit
archive (`5467f601`); SHA-256, byte size, decoded dimensions and image mode were computed
directly — equivalence was **not** inferred from filenames.

| Group | Class | Member A (survivor, on disk) | Member B (was absent) | Verdict |
|---|---|---|---|---|
| cg01 | Apple rust leaf | `CAR1.jpg` 498×841, 249 767 B | `car1.jpg` 320×320, 43 509 B | **genuinely different** |
| cg02 | Blueberry leaf | `Blueberry-Leaf.jpg` 400×380, 43 901 B | `blueberry-leaf.jpg` 1422×2000, 1 234 441 B | **genuinely different** |
| cg03 | Blueberry leaf | `Blueberry-leaves.jpg` 650×400, 176 516 B | `blueberry-leaves.jpg` 450×338, 24 227 B | **genuinely different** |
| cg04 | Corn leaf blight | `Northern-Corn-Leaf-Blight.jpg` 332×250, 14 226 B | `northern-corn-leaf-blight.jpg` 750×350, 59 950 B | **genuinely different** |
| cg05 | Peach leaf | `Peach-Leaf.jpg` 420×420, 156 315 B | `peach-leaf.jpg` 2136×1424, 148 756 B | **genuinely different** |
| cg06 | Potato leaf early blight | `…A60HXN.jpg` 1300×956, 241 221 B | `…a60hxn.jpg` 640×447, 113 078 B | **genuinely different** |

**Finding:** all 6 pairs are **genuinely different image content** — they are *not*
duplicates. On the case-insensitive macOS filesystem only the member that sorts first can
exist under its original name, so the other member's distinct content was **absent** from
the on-disk training set. Both members are now preserved under collision-safe names
(`data/raw/plantdoc/_collisions/…`). Materialization: **0** `shared_identical_content`,
**12** `collision_safe_rename` records (6 pairs × 2). Full detail:
`reports/PLANTDOC_CASE_COLLISION_REVIEW.md`; evidence: `data/manifests/_plantdoc_case_collisions.json`.

Byte-identical pairs: **0** · re-encoded-identical: **0** · genuinely-different: **6**.

## 2 · Source inventory

- `data/manifests/plantdoc_source_inventory.csv` — **2,578 rows** (every upstream train/test
  image path; all `original_upstream_path` values distinct).
- **Materialized-content count (distinct SHA-256): 2,566.** The 2,578→2,566 gap (12 records)
  is **pre-existing intra-PlantDoc exact duplication** (2,572 on-disk files carry only 2,560
  distinct SHA-256), **independent of the case-collisions**; every collision pair is distinct.
- Collision-safe image files materialized on disk: **12** (`data/raw/plantdoc/_collisions/`).
- The model-training manifest (`data/manifests/plantdoc_manifest.csv`, 2,572 rows) was **not
  modified** — the decision to add the 6 currently-absent distinct images is left to a human.

## 3 · Near-duplicate review packet

- pHash-near pairs (independently re-counted from `reports/leakage_plantvillage_vs_plantdoc_pairs.csv`):
  **16** (Hamming ≤ 6; **0** exact).
- Contact sheets: **4** PNGs (4 pairs/page, contain-fit so full images and backgrounds stay
  visible), in `reports/near_duplicate_contact_sheets/`.
- Review CSV: `data/exclusions/cross_dataset_near_duplicate_review.csv` — 16 rows, **all human
  decision fields blank** (`human_decision`, `decision_reason`, `reviewer`, `reviewed_at`,
  `final_disposition`). Each row links to its contact sheet, SHA-256s, pHash values and distance.
- Human review guide: `reports/NEAR_DUPLICATE_HUMAN_REVIEW.md`.

## 4 · Exclusion-artifact semantics

- `data/exclusions/cross_dataset_exact_exclusions.csv` — kept for **hash/content-exact only**
  (currently 0 rows; contains no near pair).
- `data/exclusions/cross_dataset_reviewed_exclusions.csv` — **new skeleton, header only** (no
  prior human decisions exist; not populated).
- Policy documented in `reports/LEAKAGE_GATE_EXCLUSION_POLICY.md`: the gate consumes exact
  exclusions from the exact file and reviewed-near exclusions from the reviewed file, and can
  reach `status=pass` only with **0 skipped, every exact pair excluded, and 0 pending/uncertain
  near pairs**. The gate was **not** forced to pass.

## 5 · Mapping checklist

- `reports/ACTION_MAPPING_HUMAN_CHECKLIST.md` — **28 rows**, one compact per-class entry
  (canonical disease, pathogen + type, candidate action, taxonomy + management source, evidence
  summary, ambiguity flag) with a **blank** `Human choice` (approve / revise / exclude /
  insufficient_evidence). No sources fetched, no evidence replaced, **nothing approved**.
- Mapping state unchanged: **28 needs_review, 0 approved** (both `action_mapping_review.csv`
  and `action_mapping_template.csv`).

## 6 · Tests & gate

- `python -m pytest -q`: **103 passed**.
- Leakage gate: **`fail`** (fail-closed) — `unresolved_pair_count = 16`, manifest-bound, not stale.

## 7 · Validation results (all PASS)

no raw image in the return package · all generated paths repository-relative · all 16
near-duplicate pairs have a contact-sheet entry · no human decision field auto-filled · exact
exclusions contain no pending pHash-near pair · approved mapping count = 0 · leakage gate
fail-closed.

## 8 · Files created / modified

**Created**
- `data/manifests/plantdoc_source_inventory.csv`
- `reports/PLANTDOC_CASE_COLLISION_REVIEW.md`
- `data/raw/plantdoc/_collisions/…` (12 collision-safe images — **not packaged**, image-free zip)
- `reports/near_duplicate_contact_sheets/contact_sheet_0[1-4].png` (**not packaged**)
- `reports/NEAR_DUPLICATE_HUMAN_REVIEW.md`
- `data/exclusions/cross_dataset_near_duplicate_review.csv`
- `data/exclusions/cross_dataset_reviewed_exclusions.csv` (skeleton)
- `reports/LEAKAGE_GATE_EXCLUSION_POLICY.md`
- `reports/ACTION_MAPPING_HUMAN_CHECKLIST.md`
- `scripts/prepare_human_review.py`
- `reports/PHASE1_HUMAN_REVIEW_PREPARATION_REPORT.md` (this file)

**Unchanged** `data/manifests/plantdoc_manifest.csv`, all mapping CSVs, `reports/leakage_gate.json`,
all package source and tests.

## 9 · Exact human actions required

1. **PlantDoc collisions** — decide whether the 6 currently-absent distinct images (the
   non-surviving members, now under collision-safe names) should be added to the training
   manifest, or left out. The inventory already represents all 2,578 distinct source records.
2. **Near-duplicates** — open the 4 contact sheets, adjudicate each of the 16 pairs, fill
   `human_decision`/`final_disposition`/`reviewer`/`reviewed_at` in
   `cross_dataset_near_duplicate_review.csv`; copy `exclude_evaluation` rows into
   `cross_dataset_reviewed_exclusions.csv`; then `python scripts/run_phase1_local.py --steps leakage,gate`.
3. **Mapping** — fill the `Human choice` for each of the 28 rows in the checklist; set
   `review_status=approved` only where the evidence gate is fully satisfied.
4. **Harm matrix** — separately author + approve a `ReviewedHarmMatrix` (out of scope here).

## 10 · Explicit statements

- **"No near-duplicate decision was made automatically."**
- **"No disease-to-action mapping was approved automatically."**
- **"The leakage gate was not forced to pass."**
