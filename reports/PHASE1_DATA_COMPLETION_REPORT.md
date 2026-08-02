# Phase-1 Data Completion Report

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition*
**Task:** complete the remaining Phase-1 **data prerequisites** (PlantDoc full acquisition; PlantVillage pixel materialization; cross-dataset leakage; leakage gate) per `PROJECT_BRIEF.md`, `reports/PHASE1_CODEX_AUDIT.md`, `reports/PHASE1_REMEDIATION_REPORT.md`, `DATASETS.md`.
**Date:** 2026-07-29. **No Phase 2. No model trained. No scientific result produced. No mapping row auto-approved. No commit/push.**

---

## 1 · Final status: **BLOCKED**

Everything achievable in the local environment is done and verified. The two
remaining data steps — **completing PlantDoc (1,717 / 2,578)** and **materializing
PlantVillage `color` pixels (~2 GB)** — are **network-throughput-limited** on this
machine (measured below) and could not finish in-session. Per PROJECT task §5, the
run was **not retried indefinitely**; instead the authoritative completion path — a
validated Colab fallback notebook + shared driver script — was produced.

Because Colab (or a faster network) is required and **the notebook has not yet been
executed and its outputs returned**, the overall status is **BLOCKED** (PROJECT
task §5 definition). The reproducible check script's own internal verdict is
**PARTIAL** (exit 2): **all 9/9 HARD checks pass**; only the data-acquisition
STATUS lines are incomplete. The system **fails closed** throughout — cross-dataset
evaluation is blocked by an `incomplete` leakage gate, and action evaluation is
blocked by 0 approved mapping rows.

---

## 2 · Environment and disk-space summary

| Item | Value |
|---|---|
| Working dir | `<repository root>` (not a git repo — per instruction) |
| Date | 2026-07-29 |
| Python / pip | 3.13.9 / 25.3 |
| Key deps installed | `datasets` 5.0.1, `huggingface_hub` 1.25.1, `imagehash`, `pillow`, `pandas`, `numpy` |
| Disk (`.` volume) | 926 GiB total, **353 GiB available** (61% used) |
| Repo size (start) | 625 MB (`data/` 623 MB) |

### Disk-space estimate for completion (all fit in 353 GiB)

| Item | Estimate |
|---|---|
| Remaining PlantDoc (861 images) | ~0.15 GB |
| PlantVillage `data.zip` archive | ~2 GB |
| Extracted PlantVillage `color` pixels | ~1.5–2 GB |
| Manifests + pHash indexes | < 0.1 GB |
| **Total additional** | **~5 GB** — safely fits |

Disk was **never** the constraint. **Network throughput** is.

---

## 3 · Commands and exit codes

| Command | Exit | Result |
|---|---:|---|
| `git ls-remote …/PlantDoc-Dataset.git HEAD master` | 0 | HEAD = pinned `5467f601` (no drift) |
| `curl -I …/mohanty/PlantVillage/resolve/9e975998/README.md` | 0 | HTTP 307 → HF reachable |
| `pip install -e ".[hf,dev]"` | 0 | editable install + HF extras |
| `pytest -q` (initial) | 0 | **103 passed** |
| `./scripts/run_phase1_checks.sh` (initial) | 2 | PARTIAL; 9/9 HARD pass |
| PlantDoc resumable download (`download_via_raw`, ref pinned to `5467f601`) | — | **+54** (1,663→1,717), then stopped (network-limited) |
| PlantVillage `data.zip` (`hf_hub_download`, rev `9e975998`) | — | **262 MB / ~2 GB**, then stopped (network-limited) |
| `python -m ica26.portability` | 0 | no machine-specific/personal identifiers |
| `python -m ica26.leakage.phash --benchmark` | 0 | 54,000 hashes → **4.2 s** (scalable, not O(N²)) |
| Leakage-gate production guard test (5 states) | 0 | all pass (see §8) |
| PlantDoc manifest rebuild + independent verification | 0 | consistent at 1,717 (see §5) |
| Leakage-gate regeneration (re-bound to current manifests) | — | status `incomplete` (fail-closed) |
| `pip install -e .` (final) | 0 | ok |
| `pytest -q` (final) | 0 | **103 passed** |
| `./scripts/run_phase1_checks.sh` (final) | 2 | PARTIAL; 9/9 HARD pass; PlantDoc 1,717/2,578 |

Measured local throughput (why local completion was abandoned):
- **PlantDoc** ≈ **2 files/min** (small per-file HTTPS requests, per-request latency-bound) → ~7 h ETA for the remaining 861.
- **PlantVillage `data.zip`** ≈ **8 MB/min** → ~4 h ETA for ~2 GB.

---

## 4 · Test results

**103 passed, exit 0** (unchanged from the remediation baseline; no test files were
added or removed this session). Fresh run confirmed after all changes.

---

## 5 · PlantDoc

| Field | Value |
|---|---|
| Source revision | `5467f6012d78d1c446145d5f582da6096f852ae8` (= live default-branch HEAD) |
| Acquisition method | implemented **resumable** raw-CDN per-file download, ref **pinned to the frozen commit**; atomic `.part`→final replace; retries=5; incomplete HTTP rejected; existing files skipped (resume, not restart) |
| Paper-reported count | 2,598 (not forced) |
| Target upstream count | **2,578** (confirmed at pinned commit: 2,342 train + 236 test) |
| Filesystem image count | **1,717** |
| Valid decodable count | **1,717** (0 corrupt) |
| Manifest row count | **1,717** |
| Train / test images | **1,481 / 236** |
| Train / test classes (local) | **17 / 27** present (upstream is 28 train / 27 test; not all train classes reached yet) |
| Corrupt / duplicate-relpath / zero-byte | **0 / 0 / 0** |
| fs↔manifest (both directions) | **0 / 0** mismatches |
| SHA-256 sample checked / matched | **60 / 60** |
| Completion status | **INCOMPLETE — 1,717 / 2,578 (66.6%)** |

Completion criterion (`filesystem == valid == manifest == upstream 2,578`) is **not
met**. Local progress this session: **+54** images. Remaining 861 are network-limited.
Artifacts updated: `data/manifests/plantdoc_manifest.csv`, `plantdoc_summary.json`,
`plantdoc_source_snapshot.json`; evidence in `data/manifests/_plantdoc_verification.json`;
reconciliation appended (dated 2026-07-29) — **earlier evidence preserved**.

---

## 6 · PlantVillage

| Field | Value |
|---|---|
| Source revision | `9e97599868962bd0079b8db4b7f1efa9185fa1e7` (HF `mohanty/PlantVillage`; **not Kaggle**) |
| Configuration | `color` (authoritative `data.zip` carries color/grayscale/segmented) |
| Metadata (manifest) count | **54,305** |
| Pixel count (sha256 filled) | **0 — NOT materialized** |
| Valid decodable count | n/a (no pixels locally) |
| Manifest row count | 54,305 |
| Class count | **38** |
| Healthy-class count | **12** |
| leaf_id present / missing | **41,111 / 13,194** (preserved; never fabricated; missing left missing) |
| Corrupt / missing | n/a (structural manifest only) |
| Completion status | **INCOMPLETE / BLOCKED** — `data.zip` reached **262 MB / ~2 GB** then stopped (network) |

The leaf_id structure + leaf-grouped split readiness are acquired; **pixel bytes
are not** (this is explicitly *not* "pixel materialization"). Materialization is
implemented in the driver/notebook: download `data.zip` (rev `9e975998`) → extract
`color` members → fill `sha256`/dims/mode/`n_bytes`/`is_corrupt` per image →
deterministic decode (≥100) + SHA-256 (≥100) sample verification → record source
revision, acquisition command, execution time, disk usage. A **262 MB resumable
partial** `data.zip` remains in the git-ignored `data/raw/plantvillage/_hf/` cache.

---

## 7 · Cross-dataset leakage

| Field | Value |
|---|---|
| Training source | PlantVillage `color` |
| Evaluation source | PlantDoc |
| Algorithm | `imagehash.phash`, 64-bit |
| Threshold | **Hamming ≤ 6** (reviewed config; **not changed**) |
| Runtime | **not run** — blocked: PlantVillage pixels not materialized |
| Exact / near / pending-review pairs | n/a (blocked) |
| Exclusions | n/a (blocked) |
| Skipped files | n/a (blocked) |

The comparison **cannot run** without training pixels: a live gate computation
skips all **54,305** training images (see §8). The full pipeline is implemented in
`scripts/run_phase1_data_completion.py` (`leakage` step) and emits, on real data:
`reports/leakage_plantvillage_vs_plantdoc_pairs.csv` (training/eval relpath +
class, both hashes, Hamming distance, exact|near classification, review_status,
proposed disposition, notes) and `…_summary.json`; exact duplicates →
`data/exclusions/cross_dataset_exact_exclusions.csv` (proposed exclusion of the
**evaluation** image, with reason + provenance); near duplicates →
`reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md` (`review_status=pending`, never
auto-classified as true duplicates). Ordering is deterministic; no self/reversed
pairs; skipped/corrupt counted; current-manifest hashes used; no image
redistributed. **These artifacts are produced when the data completes (Colab).**

---

## 8 · Leakage gate

| Field | Value |
|---|---|
| Status | **`incomplete`** (fail-closed) |
| Training manifest SHA-256 (bound) | `9e2a82bb7dae…` |
| Evaluation manifest SHA-256 (bound) | `56708daad9f9…` (re-bound to the rebuilt PlantDoc manifest) |
| Threshold | 6 |
| Skipped training / evaluation | **54,305 / 0** (PV pixels absent → all training images skipped) |
| Unresolved conditions | PlantVillage pixels not materialized ⇒ leakage check incomplete ⇒ cross-dataset evaluation blocked |

`validate_gate` confirms the gate **does not authorise evaluation** (errors:
"leakage check was incomplete"; "status is 'incomplete', not 'pass'").

### Production cross-dataset guard — all five states verified (`reports/leakage_gate_guard_test.json`)

| # | Scenario | Guard result |
|---|---|---|
| 1 | Missing gate | **rejected** ✓ |
| 2 | Incomplete gate | **rejected** ✓ |
| 3 | Stale gate (manifest SHA changed) | **rejected** ✓ |
| 4 | Unresolved pairs | **rejected** ✓ |
| 5 | Current valid `pass` gate (bound to current manifests) | **accepted** ✓ |

*No model evaluation was run after the guard test.*

---

## 9 · Mapping status — **no row approved**

| Category | Count |
|---|---:|
| Total rows | **28** |
| pending | 0 |
| **needs_review** | **28** |
| **approved** | **0** |
| excluded | 0 |
| ambiguous (subset of needs_review) | **2** (Tomato leaf mosaic virus = non-vectored virus; Tomato two-spotted spider mites = arthropod pest, not a pathogen) |

**Confirmation: no mapping row was changed and none was auto-approved.** No new
agronomic recommendations were fetched or generated. Human, source-verified review
remains a separate task (`data/mapping/action_mapping_review.csv`,
`reports/ACTION_MAPPING_REVIEW_PACKET.md`).

---

## 10 · Local execution vs Colab execution

- **Local:** genuine attempt made — resumable PlantDoc download (+54) and HF
  `data.zip` fetch (262 MB) both ran; throughput measured and found insufficient
  (§3). All non-network work completed and verified locally.
- **Colab:** the required completion path. `notebooks/06_phase1_data_completion_colab.ipynb`
  + `scripts/run_phase1_data_completion.py` resume PlantDoc, materialize
  PlantVillage `color` pixels, rebuild + verify manifests, build pHash indexes, run
  the cross-dataset comparison, create the leakage review artifacts + gate, run the
  Phase-1 checks, and package **only** reports/manifests/indexes for return (never
  raw images). **The notebook has not yet been executed → status remains BLOCKED.**

---

## 11 · Files created / modified

**Created**
- `scripts/run_phase1_data_completion.py` — shared local+Colab data-completion driver.
- `notebooks/06_phase1_data_completion_colab.ipynb` — Colab fallback (valid JSON; all 7 code cells parse; no personal paths/credentials/tokens).
- `reports/leakage_gate_guard_test.json` — five-state guard evidence.
- `data/manifests/_plantdoc_verification.json` — PlantDoc verification battery.

**Modified**
- `data/manifests/plantdoc_manifest.csv` / `plantdoc_summary.json` / `plantdoc_source_snapshot.json` — 1,663 → **1,717**, re-verified, pinned to `5467f601`.
- `reports/leakage_gate.json` — re-bound to current manifests; status `incomplete`.
- `reports/PLANTDOC_COUNT_RECONCILIATION.md` — appended dated 2026-07-29 update (earlier evidence preserved).
- `reports/PHASE1_DATA_COMPLETION_REPORT.md` — this report.

**Untouched / preserved:** `PROJECT_BRIEF.md`, `PHASE1_CODEX_AUDIT.md`,
`PHASE1_REMEDIATION_REPORT.md`, `PHASE1_REMEDIATION_MATRIX.md`, `DATASETS.md`,
all mapping CSVs, `plantvillage_manifest.csv/summary.json/source_snapshot.json`,
all package source and tests.
**Git-ignored partial cache:** `data/raw/plantvillage/_hf/` (262 MB resumable `data.zip`).

---

## 12 · Remaining blockers

1. **PlantDoc completion** — 861 images (1,717 → 2,578); network-limited; resumable locally or on Colab.
2. **PlantVillage pixel materialization** — `data.zip` ~2 GB; network-limited; Colab.
3. **Cross-dataset leakage comparison** — blocked on (2).
4. **Leakage gate `incomplete`** — remains non-`pass` until (1)+(2) complete and any pairs are resolved (fail-closed; correct).
5. **Mapping 0 approved** — by design; needs human, source-verified review of the 28-row packet.
6. **No version control** — not initialized (per task instruction).

---

## 13 · Exact human actions required

1. **Run the Colab notebook** (`notebooks/06_phase1_data_completion_colab.ipynb`) — or re-run the driver on a faster network — to (a) complete PlantDoc to 2,578 and (b) materialize PlantVillage `color` pixels; then **return the packaged reports/manifests/indexes** to the local repo.
2. After return, **re-run leakage + gate** (`--steps leakage,gate`) → expect gate `pass`, or resolve any exact/near pairs first.
3. **Human review** of `reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md` (once generated) before the gate may pass.
4. **Human mapping review** of the 28 rows (separate task; source verification).
5. **Re-run** `./scripts/run_phase1_checks.sh` → target PASS, then request a fresh Codex audit.

---

## 14 · Explicit statements

- **"No model training was performed."**
- **"No scientific performance result was produced or claimed."**
- **"No disease-to-action mapping row was automatically approved."**
