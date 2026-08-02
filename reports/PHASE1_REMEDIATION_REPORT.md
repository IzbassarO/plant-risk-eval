# Phase-1 Remediation Report

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition*
**Task:** remediate the REJECTED Phase-1 implementation per `reports/PHASE1_CODEX_AUDIT.md`.
**Date:** 2026-07-28. **No model trained. No scientific result produced. No mapping auto-approved. No commit made.**

---

## 1 · Final status: **PARTIAL**

Every **P0 blocker is fixed in code and tested**, and every HARD gate check
passes. The remaining gaps are **network-limited data acquisition only** (PlantDoc
full download, PlantVillage pixel materialization) — explicitly permitted to be
partial by the brief and completed by re-running on Colab. The system now **fails
closed**: cross-dataset evaluation is blocked without a passing leakage gate, and
action evaluation is blocked without an approved mapping.

`scripts/run_phase1_checks.sh`: **9/9 HARD checks PASS**, overall **PARTIAL** (exit 2).

## 2 · Every Codex finding and its disposition

Full traceability is in `reports/PHASE1_REMEDIATION_MATRIX.md`. Summary:

| Priority | Findings | Fixed | Local-partial (code done, data network-limited) |
|---|---|---|---|
| P0 | 5 | **5** | — |
| P1 | 5 | 3 | 2 (PlantDoc completion, PlantVillage pixels) |
| P2 | 4 | **4** | — |
| P3 | 3 | **3** | — |

Nothing was ignored, including MINOR items (no-version-control is noted; git was
**not** initialized per the task instruction).

## 3 · Files created / modified

**New package modules:** `leakage/gate.py`, `evaluation/cross_dataset.py`,
`datasets/guards.py`, `config.py`, `portability.py`; **rewritten:**
`leakage/phash.py` (dict + banded multi-index), `datasets/plantdoc.py` (git
acquisition + reconciliation), `datasets/plantvillage.py` (repo-file acquisition
+ leaf_id), `evaluation/harm.py` (reviewed-matrix provenance),
`evaluation/selective.py` + `action_metrics.py` (count preservation, controls,
length checks), `mapping/validation.py` (hard stop).
**Configs:** `configs/harm_matrix_template.yaml`; **script:** `scripts/run_phase1_checks.sh` (rewritten).
**New tests (8 files):** `test_leakage_gate, test_cross_dataset, test_phash_scale, test_harm_provenance, test_portability, test_guards, test_datasets, test_metric_controls`.
**Data/reports:** `data/mapping/action_mapping_review.csv`, updated `action_mapping_template.csv`, `data/manifests/plantdoc_*`, `plantvillage_*`, `reports/leakage_gate.json`, `reports/leakage_pairs.csv`, `reports/PHASE1_REMEDIATION_MATRIX.md`, `PLANTDOC_COUNT_RECONCILIATION.md`, `ACTION_MAPPING_REVIEW_PACKET.md`, this report.
**Quarantined (preserved):** `notebooks/legacy/*` (outputs cleared), `reports/_legacy_smoke_figures/*`. **Expanded:** `.gitignore`. **Preserved untouched:** `PROJECT_BRIEF.md`, `PHASE1_CODEX_AUDIT.md`, `PHASE1_REPORT.md`, `DATASETS.md`; originals backed up to `reports/_remediation_backup_<ts>/`.

## 4 · Exact commands and exit codes

```
git ls-remote / blobless clone (pinned commit 5467f601)         0
pip install -e .                                                0
python -m ica26.datasets.plantdoc --download --method raw       0   (resumable; frozen at 1,663)
python -m ica26.datasets.plantvillage (repo-file acquisition)   0   (54,305 rows)
python -m ica26.mapping.crosswalk / validation                  0
python -m ica26.leakage.phash --benchmark                       0
python -m ica26.leakage.gate (PlantVillage->PlantDoc)           1   (status=incomplete, as designed)
python -m ica26.portability                                     0
python -m pytest -q                                             0   (103 passed)
./scripts/run_phase1_checks.sh                                  2   (9/9 HARD pass; verdict PARTIAL)
```

## 5 · Test count and result

**103 passed** in ~1.5s across **16** test files (was 52). New coverage: leakage
gate (absent / stale-manifest / incomplete / unresolved / valid / dev-override),
indexed==brute-force parity, no-reversed/self pairs, BK-tree correctness,
harm-provenance (approved required, example/template rejected, no default),
portability, Master-training guard, cross-dataset fail-closed, mandatory metric
controls, filesystem↔manifest mismatch, PlantVillage leaf_id preservation,
source-snapshot schema, metric length validation.

## 6 · PlantDoc

| Field | Value |
|---|---|
| Acquisition method | git listing (blobless clone) + resumable raw-CDN download (replaces truncation-prone tarball) |
| Source revision | commit `5467f6012d78d1c446145d5f582da6096f852ae8` (2021-05-02) |
| Paper-reported count | **2,598** |
| Upstream repository count | **2,578** (2,342 train + 236 test) |
| Filesystem count (frozen snapshot) | **1,663** |
| Valid decodable count | **1,663** (0 corrupt) |
| Manifest count | **1,663** (fs↔manifest: 0 rows-missing-files, 0 files-missing-from-manifest) |
| Train / test classes (upstream) | **28 / 27** (test drops *Tomato two spotted spider mites leaf*) |
| Completion verdict | **INCOMPLETE (1,663/2,578)** — network-limited; resumable via `ica26-plantdoc --download` |

Reconciliation (full detail in `PLANTDOC_COUNT_RECONCILIATION.md`): the 2,598→2,578
delta is **repository drift since the 2020 publication**, not non-image files
(0 non-image files under train/test). Cite 2,578 at the pinned commit; note the
paper's 2,598.

## 7 · PlantVillage

| Field | Value |
|---|---|
| Execution status | **EXECUTED** (real files fetched). `datasets` 4.0+ cannot run the repo's loading script, so acquisition reads the authoritative `splits/*.txt` + `leaf_grouping/leaf-map.json` directly. |
| Source revision | HF commit `9e97599868962bd0079b8db4b7f1efa9185fa1e7` |
| Image count (color) | **54,305** (43,596 train + 10,709 test) — confirms the brief's off-by-one vs the paper's 54,306 |
| Classes | 38 (12 healthy) |
| leaf_id present | **41,111** (75.7%) |
| leaf_id missing | **13,194** — reported, never fabricated |
| Grouped-split readiness | **ready** (authors ship leaf-grouped `color_train/test.txt`) |
| Manifest count | 54,305 |
| Completion verdict | **PARTIAL** — leaf_id structure + splits acquired; pixel bytes (`data.zip`, ~2 GB) not materialized locally → `sha256`/dimensions pending. Complete on Colab: `pip install ica26[hf]` then materialize `data.zip`. |

## 8 · Path-portability audit

`ica26-portability` scans manifests, mappings, leakage outputs, remediation
reports and package source → **OK, 0 machine-specific/personal identifiers**. The
audit-flagged `data/interim/phash_index.csv` was regenerated with
repository-relative paths. Human-authored inputs that legitimately quote a machine
path while *describing* the problem (the audit, the brief) are excluded by design.

## 9 · Leakage implementation

| Aspect | Value |
|---|---|
| Algorithm | **exact:** hash→members dict (O(N)); **near:** **banded multi-index hashing** ((t+1) bands, pigeonhole) — replaces the O(N²) all-pairs scan and the BK-tree's degenerate case on uniform hashes |
| Reference | brute-force implementation retained; `test_phash_scale` asserts indexed == brute-force exactly |
| Benchmark (measured, synthetic worst-case uniform hashes) | 636 → 0.003 s · 2,600 → 0.012 s · 18,000 → 0.487 s · **54,000 → 5.84 s** (real clustered image data is faster) |
| Provenance recorded | `phash_algorithm`, `hash_size_bits`, `threshold` in every summary/gate |
| Intra-PlantDoc result (frozen, threshold 6) | **24 exact + 9 near** duplicate pairs — recorded in `reports/leakage_pairs.csv`; resolve (dedupe/group) before training |
| Cross-dataset gate | `reports/leakage_gate.json` = **incomplete** (PlantVillage pixels not materialized) → **correctly blocks** cross-dataset evaluation |

## 10 · Harm / severity isolation

- **No scientific harm matrix exists in code.** `EXAMPLE_DEV_REVIEWED_MATRIX` is
  `review_status=example`, `is_example=True`; `configs/harm_matrix_template.yaml`
  is `pending` with unfilled weights. `require_production_matrix()` raises on
  anything not `approved`; there is **no default**.
- Provenance schema: `matrix_id, version, created_at, review_status, source_notes,
  action_order, weights`. Only `approved` is usable by paper commands.
- **Severity** is out of Phase-1 scope: notebook 02's fixed tiers were quarantined
  to `notebooks/legacy/` with outputs cleared; nothing in the core pipeline
  depends on severity.

## 11 · Mapping review packet

| Category | Count |
|---|---:|
| Total rows | **28** |
| `needs_review` | **28** |
| `approved` | **0** |
| `pending` | 0 |
| `excluded` | 0 |
| Ready for review (disease 16 + healthy 10) | 26 |
| Ambiguous (ToMV non-vectored; spider-mite = pest not pathogen) | 2 |
| Insufficient evidence | 0 |

Every disease row cites a **fetched, verified** authoritative page (UC IPM →
university extension → EPPO); two were hand-spot-verified. **Confirmation: no row
was auto-approved.** The `require_approved_lookup` hard stop was verified to block
action evaluation with 0 approved rows. Detail in `ACTION_MAPPING_REVIEW_PACKET.md`.

## 12 · Remaining blockers

1. **PlantDoc full download** (1,663/2,578) — slow local network; resumable, fast on Colab.
2. **PlantVillage pixel materialization** (`data.zip`, ~2 GB) — deferred to Colab; leaf_id structure already acquired.
3. **Cross-dataset leakage gate is `incomplete`** until (2) is done — by design it blocks cross-dataset metrics.
4. **Mapping has 0 approved rows** — by design; needs human review of the 28-row packet before any action metric can run.
5. **No version control** — recommend `git init` + initial commit (not done: task said do not initialize git).

## 13 · Exact next human actions

1. On Colab: `pip install -e ".[hf]"`; run `ica26-plantdoc --download` (→ 2,578) and materialize PlantVillage `data.zip`, then re-run `ica26-plantvillage` for pixel-level fields.
2. Re-generate the leakage gate: `ica26-leakage-gate --training-manifest …plantvillage… --evaluation-manifest …plantdoc… --threshold 6` → expect `pass` (or resolve reported pairs).
3. Review `data/mapping/action_mapping_review.csv`: confirm each source, resolve the 2 ambiguous rows + the healthy-class policy, set `review_status=approved` only where the evidence gate is satisfied.
4. Author + approve a `ReviewedHarmMatrix` (fill `configs/harm_matrix_template.yaml`, set `approved`).
5. Re-run `./scripts/run_phase1_checks.sh` → target **PASS**. Then request a fresh audit.

## 14 · Explicit statements

- **"No final model training was performed during remediation."**
- **"No scientific performance result was produced or claimed."**
- **"No disease-to-action mapping row was automatically approved."**
