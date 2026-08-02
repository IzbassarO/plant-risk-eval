# Phase 1 — Foundation Gate Report

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition*
**Venue:** ICA 2026 / Springer CCIS
**Date:** 2026-07-28
**Scope:** Establish a reliable, testable research foundation. **No final models, no scientific conclusions, no smoke-test values presented as results.**

---

## 1 · Executive status: **PARTIAL**

The **foundation itself is complete and verified** (reusable package, evidence-gated mapping, action/harm/selective metrics, perceptual-hash leakage tooling, 52 passing unit tests, reproducible check script). Two data-acquisition items are **incomplete locally by environment limits** (both allowed by the brief), and one governing artifact is **missing**:

| Area | Status |
|---|---|
| Core package `src/ica26/` | ✅ complete |
| Unit tests (52) | ✅ all pass |
| Action taxonomy + mapping schema + evidence-gate validator | ✅ complete & tested |
| Metrics (disease/action accuracy, majority baseline, harm, selective, risk-coverage) | ✅ complete & tested |
| Perceptual-hash leakage tooling + CLI | ✅ complete & tested; run on available data |
| Reproducible `scripts/run_phase1_checks.sh` | ✅ runs green |
| PlantDoc acquisition (resumable downloader) | ⚠️ **partial data** (636/≈2598) — tooling proven resumable; completion blocked by slow network + GitHub API rate-limit |
| PlantVillage acquisition | ⚠️ **implemented, Colab-ready, not run locally** (no `datasets` lib / large gated download) — fails loudly by design |
| `PROJECT_BRIEF.md` (declared governing spec) | ❌ **absent from repo** — see Known Blockers |

Overall **PARTIAL**: the gate's *engineering* deliverables pass; dataset completeness is environment-limited (and explicitly permitted to be partial), and the authoritative brief file is missing.

---

## 2 · Repository state before changes

- **Not a git repository.** `git status`, `git branch --show-current`, and `git log -5 --oneline` all returned `fatal: not a git repository`. There was therefore no committed history and no git-tracked uncommitted work.
- **Existing working tree (from the prior exploratory phase), preserved untouched:**
  `DATASETS.md`, `README.md`, `.gitignore`, `requirements.txt`, `notebooks/00–05*.ipynb`, `reports/DATASET_ASSESSMENT.md`, `reports/figures/*.png`, `data/interim/{eda_summary.csv, phash_index.csv}`, `data/mapping/{class_crosswalk.csv, disease_pathogen.csv}`, and `data/raw/plantdoc/test/*` (the 236-image PlantDoc **test** split).
- **Reusable vs exploratory (assessment):** notebook logic for perceptual hashing, class-name normalization, action/harm/selective evaluation, and manifest building was **exploratory and inconsistent across notebooks**; it has been **refactored into the `ica26` package** as the single source of truth. The prior smoke-baseline numbers (407-image PlantDoc, 0.414 acc, 3×3 confusion, abstention plot) are treated as **non-scientific** and were **not reused as results** (constraint 6).

No existing file was discarded, reset, or overwritten destructively. The prior `data/mapping/class_crosswalk.csv` and `disease_pathogen.csv` remain; the Phase-1 canonical mapping is the new `data/mapping/action_mapping_template.csv`.

---

## 3 · Files created and modified

**Created — package (`src/ica26/`):**
`__init__.py`, `schemas.py`, `config.py`,
`datasets/{__init__,manifest,plantdoc,plantvillage}.py`,
`mapping/{__init__,schema,validation,crosswalk}.py`,
`evaluation/{__init__,action_metrics,harm,selective}.py`,
`leakage/{__init__,phash}.py`.

**Created — configs / packaging / scripts:**
`pyproject.toml`, `configs/action_taxonomy.yaml`, `scripts/run_phase1_checks.sh`.

**Created — tests (`tests/`):**
`conftest.py`, `test_taxonomy.py`, `test_mapping.py`, `test_action_metrics.py`, `test_harm.py`, `test_selective.py`, `test_phash.py`, `test_manifest.py`.

**Created — generated artifacts:**
`data/manifests/plantdoc_manifest.csv`, `data/manifests/plantdoc_summary.json`,
`data/mapping/action_mapping_template.csv`,
`reports/leakage_pairs.csv`, `reports/leakage_summary.json`, `reports/PHASE1_REPORT.md`.

**Modified:** `requirements.txt` (rewritten to bounded core deps + optional extras).
**Preserved unchanged:** all prior notebooks, `DATASETS.md`, `README.md`, `reports/DATASET_ASSESSMENT.md`, `data/interim/*`, prior `data/mapping/*` seeds.

---

## 4 · Exact commands executed

```bash
# audit
git status; git branch --show-current; git log -5 --oneline   # -> not a git repository
find . -maxdepth 3 -type f | sort

# environment / install
python -m venv .venv && pip install pytest PyYAML pyarrow
pip install -e .                                               # editable install of ica26

# dataset acquisition (resumable; hit API rate-limit, then resumed)
python -m ica26.datasets.plantdoc --download --retries 5 \
  --manifest data/manifests/plantdoc_manifest.csv \
  --summary  data/manifests/plantdoc_summary.json

# mapping template
python -m ica26.mapping.crosswalk  --out data/mapping/action_mapping_template.csv
python -m ica26.mapping.validation data/mapping/action_mapping_template.csv

# leakage on available data
python -m ica26.leakage.phash \
  --manifest-a data/manifests/plantdoc_manifest.csv --root-a data/raw/plantdoc \
  --threshold 5 \
  --out-pairs reports/leakage_pairs.csv --out-summary reports/leakage_summary.json

# full gate
PYTHON=python ./scripts/run_phase1_checks.sh
python -m pytest -q
```

**Exit codes (final runs):** `pytest` → 0 (52 passed); taxonomy validation → 0; PlantDoc manifest build/validate → 0; mapping build → 0; mapping validate → 0; leakage → 0; `run_phase1_checks.sh` → 0. The **first** PlantDoc `--download` returned a handled `RuntimeError` (GitHub API 403 rate-limit); acquisition was retried after the ~12-minute reset and resumed successfully.

---

## 5 · Test results

```
52 passed in 0.35s
```

Coverage of the required cases:

| Required test | File | Status |
|---|---|---|
| action taxonomy validation | `test_taxonomy.py` | ✅ |
| mapping schema validation | `test_mapping.py` | ✅ |
| approved row without evidence must fail | `test_mapping.py::test_approved_without_evidence_fails` | ✅ |
| unknown action class must fail | `test_mapping.py::test_unknown_action_class_fails` | ✅ |
| (bonus) forbidden `abiotic_correction` must fail | `test_mapping.py::test_forbidden_action_class_fails` | ✅ |
| disease-to-action projection | `test_action_metrics.py::test_projection` | ✅ |
| action accuracy | `test_action_metrics.py` | ✅ |
| majority-action baseline | `test_action_metrics.py::test_majority_action_baseline` | ✅ |
| asymmetric harm calculation | `test_harm.py` | ✅ |
| missing mapping handling | `test_action_metrics.py::test_missing_true_mapping_is_excluded_not_dropped_silently` | ✅ |
| risk-coverage calculations | `test_selective.py` | ✅ |
| deterministic threshold ordering | `test_selective.py::test_default_thresholds_sorted_ascending`, `test_deterministic_repeatability` | ✅ |
| exact perceptual duplicate detection | `test_phash.py::test_exact_duplicate_detected_intra`, `test_image_based_duplicate_detection` | ✅ |
| near-duplicate detection | `test_phash.py::test_near_duplicate_threshold_boundary` | ✅ |
| manifest duplicate-path detection | `test_manifest.py::test_duplicate_path_detection` | ✅ |
| corrupt-image reporting | `test_manifest.py::test_build_manifest_flags_corrupt_not_dropped` | ✅ |

Tests use synthetic arrays and generated temporary images only — **no dataset download is required to run them.**

---

## 6 · PlantDoc

| Field | Expected (brief) | Observed (snapshot 2026-07-28) |
|---|---|---|
| total images | ≈ 2,598 | **636** (partial download) |
| train images / classes | — / 28 | 400 / **6** (train still downloading) |
| test images / classes | — / 27 | **236 / 27** (test split complete) |
| corrupt / unreadable | — | **0** (of 636 hashed/opened) |
| missing / skipped files | — | **0 silently skipped** — every listed file is either downloaded or recorded as a failure in `download_report` |
| dataset complete? | — | **No** — see discrepancy |

- **Discrepancy explanation:** the earlier tarball acquisition truncated on this slow link. The new module (`ica26.datasets.plantdoc`) enumerates files via the GitHub tree API and downloads each **individually, resumably, with retries and atomic writes**. It **works** — it resumed the dataset from 236 → 636 images across this session — but the local network (~0.05–0.2 MB/s) plus the unauthenticated GitHub API rate-limit (60 req/hour) prevented completing all ~2,598 files locally. This is explicitly permitted by the brief; the tooling is Colab-ready where it completes in minutes.
- **The test split is complete** (236 images, 27 classes); the "Tomato two-spotted spider mites" class absence from test cannot yet be confirmed against train because train is partial — it will surface once train download completes (train is expected to have the 28th class).
- **To complete (resumable, safe to re-run):**
  `python -m ica26.datasets.plantdoc --download` (locally to continue, or on Colab).

Manifests: `data/manifests/plantdoc_manifest.csv` (per-image: split, class, relpath, **sha256**, width, height, mode, n_bytes, is_corrupt, source_url, acquired_at_utc) and `data/manifests/plantdoc_summary.json` (observed-vs-expected, per-split, corrupt count, download report).

---

## 7 · PlantVillage

| Field | Value |
|---|---|
| acquisition status | **Implemented, not run locally.** Requires the optional `datasets` dependency and a multi-GB Hugging Face download. The module **fails loudly** (`DatasetsNotInstalled`) with an actionable message rather than degrading silently. |
| authoritative source | `mohanty/PlantVillage` (Hugging Face) — **Kaggle mirrors forbidden** (they drop `leaf_id`). Enforced in code. |
| configuration | `color` (default); `segmented` and `grayscale` also supported. |
| leaf_id handling | Recorded per image as `leaf_id` + `has_leaf_id`; the summary reports **n_with / n_without / proportion** and a `grouped_split_readiness` flag (`ready` / `partial` / `no_grouping`). **No leaf_id is ever manufactured.** |
| grouped-split readiness | Determined at acquisition time; per the source, PlantVillage maps leaves for only ~41,112/54,306 images, so readiness is expected to be **`partial`** — the manifest will quantify it exactly on Colab. |
| total image count / with-leaf_id / without | **Pending Colab run** (not downloadable in this environment). |

To acquire on Colab: `pip install "ica26[hf]"` then
`python -m ica26.datasets.plantvillage --config color`.

---

## 8 · Mapping

| Metric | Value |
|---|---|
| rows | **27** (one per available PlantDoc class; grows to 28 when the train-only class downloads) |
| `pending` | **27** |
| `needs_review` | 0 |
| `approved` | **0** |
| `excluded` | 0 |
| auto-approved unsupported rows | **0 — none.** Rows are born `pending`; `mapping_confidence` defaults to `low`. |

- Every row preserves the **original dataset label** (`dataset_class`) verbatim; `canonical_crop`/`canonical_disease` are produced by **deterministic normalization only**. **No pathogen type, action, treatment text, source, or citation was invented** — those columns are blank and the rows are `pending`.
- The validator (`ica26.mapping.validation`) **rejects** any `approved` row missing a required evidence field, any unknown/forbidden action class, and any invalid enum. Verified by unit tests (§5) and by a clean validation run of the generated template.
- File: `data/mapping/action_mapping_template.csv` (16 columns exactly as specified).

---

## 9 · Leakage

| Field | Value |
|---|---|
| datasets checked | **PlantDoc** (intra-dataset), 636 images, threshold = 5 |
| exact-duplicate pairs | **4** (all `train ↔ train`, within the same class folder) |
| near-duplicate pairs | **0** |
| skipped (corrupt/missing) | **0** |
| datasets **not** yet checked | **Cross-dataset (PlantDoc ↔ PlantVillage)** — PlantVillage is not downloaded, so no cross-dataset claim is made. Cross-dataset leakage MUST be re-run before any cross-dataset performance number (constraint 5). |

The 4 exact duplicates are genuine intra-training redundancies (e.g. `Apple Scab Leaf/Apple-Scab1.jpg` ≡ `applescab.jpg`; three pairs in `Bell_pepper leaf spot`). **No train↔test leakage** was found in the available data. Artifacts: `reports/leakage_pairs.csv`, `reports/leakage_summary.json`.

---

## 10 · Known blockers

1. **`PROJECT_BRIEF.md` is absent from the repository.** The task names it the authoritative governing spec, but no such file exists (only `DATASETS.md`). To avoid fabricating scientific decisions, Phase 1 proceeded on **the constraints stated in the task prompt** + `DATASETS.md`, and produced **no scientific content**. **Action needed:** add the real `PROJECT_BRIEF.md`; if it contradicts any assumption here, the affected step must be revisited.
2. **PlantDoc full download** is environment-limited (slow network + GitHub API 60/hour). Resumable; completes on Colab. Partial locally (636/≈2598).
3. **PlantVillage** not acquired locally (needs `datasets` + large gated download). Colab-ready; fails loudly locally.
4. **Repository is not under version control.** Recommend `git init` + an initial commit to snapshot this foundation before Phase 2 (not done here — the task said do not commit unless instructed).

---

## 11 · Recommended next command / task for Phase 2

Run acquisition + the full gate on **Google Colab** (fast network, no API limit), which completes both datasets and the cross-dataset leakage check:

```bash
pip install -e ".[hf]"
python -m ica26.datasets.plantdoc     --download                 # completes ≈2598 images
python -m ica26.datasets.plantvillage --config color             # leaf_id manifest + summary
python -m ica26.leakage.phash \
  --manifest-a data/manifests/plantvillage_manifest.csv --root-a data/raw/plantvillage \
  --manifest-b data/manifests/plantdoc_manifest.csv     --root-b data/raw/plantdoc \
  --threshold 5 --out-pairs reports/leakage_pv_pd.csv --out-summary reports/leakage_pv_pd.json
PYTHON=python ./scripts/run_phase1_checks.sh
```

**Phase 2 task:** with complete manifests and a leak-safe (leaf-grouped) PlantVillage split in hand, **populate and human-review the disease-to-action mapping** — fill `pathogen_type`, `action_class`, and the evidence fields from authoritative sources (EPPO / AGROVOC / UC IPM), moving rows `pending → needs_review → approved` **only** when the evidence gate is satisfied. The validator already enforces this. No model training until the mapping has approved rows and cross-dataset leakage is confirmed clean.

---

## 12 · Explicit statement

**No scientific performance result was produced or claimed in Phase 1.**

The only numbers in this report are dataset inventory counts, unit-test counts, and duplicate-pair counts. The harm matrix used anywhere in code is the clearly-labelled `EXAMPLE_DEV_ONLY` placeholder for unit tests, not a scientific weighting. The prior 407-image / 0.414-accuracy smoke values were explicitly **not** used.
