# Phase-1 Remediation Matrix

Every finding from `reports/PHASE1_CODEX_AUDIT.md` (P0–P3, plus the blocker and
contradiction lists), its root cause, the fix, the files touched, how it was
verified, and its final status. Nothing is silently dropped.

Status key: **DONE** · **DONE (local-partial)** = code complete, full data
acquisition network-limited · **N/A**.

---

## P0 — before any Phase 2

| # | Audit finding | Root cause | Fix | Files | Verification | Status |
|---|---|---|---|---|---|---|
| P0.1 | Zero approved mappings; empty approved lookup is not a hard stop for action evaluation | Phase-1 only shipped a blank template + a syntactic validator | Built a verified evidence packet (28 rows, `needs_review`, 0 approved); added `require_approved_lookup()` that raises `NoApprovedMappingError` on an empty approved set; the cross-dataset entry point calls it | `mapping/validation.py`, `evaluation/cross_dataset.py`, `data/mapping/action_mapping_review.csv`, `action_mapping_template.csv`, `reports/ACTION_MAPPING_REVIEW_PACKET.md` | `test_cross_dataset.py::test_blocks_without_approved_mapping`; live check shows approved-lookup size 0 → blocked | **DONE** |
| P0.2 | No enforced leakage gate for cross-dataset metrics | Notebook 04 only *recommended* a phash check; nothing blocked evaluation | Persisted `leakage_gate.json` (schema v1, manifest-SHA-bound); `validate_gate()` fails closed on missing/stale/incomplete/unresolved/not-pass; `require_valid_gate()` guards the cross-dataset entry point; dev-only override warns loudly | `leakage/gate.py`, `evaluation/cross_dataset.py` | `test_leakage_gate.py` (7 states), `test_cross_dataset.py` | **DONE** |
| P0.3 | O(N²) all-pairs perceptual-hash search | Block-vs-all uint64 XOR grid | Replaced with a **hash-dict (exact) + BK-tree (near)** index; kept a brute-force reference; added a benchmark | `leakage/phash.py` | `test_phash_scale.py::test_indexed_matches_brute_force_*`; benchmark table in remediation report | **DONE** |
| P0.4 | PlantDoc count discrepancy 2,598 vs live 2,578 unresolved | Hard-coded 2,598 (paper) never reconciled to the current repo tree | Blobless clone at pinned commit `5467f601`; enumerated 2,578 images (0 non-image files); recorded source snapshot; reconciliation report explains the 20-image delta | `datasets/plantdoc.py`, `data/manifests/plantdoc_source_snapshot.json`, `reports/PLANTDOC_COUNT_RECONCILIATION.md` | `test_datasets.py::test_source_snapshot_schema` (asserts paper 2598 / upstream 2578) | **DONE** |
| P0.5 | Notebook 05 hard-coded harm matrix + stored 0.746 output; notebook 02 fixed severity tiers — conflict with example-only/no-result constraints | Exploratory notebooks retained as-is with stored smoke outputs | Cleared **all** notebook outputs; moved notebooks to `notebooks/legacy/` and smoke figures to `reports/_legacy_smoke_figures/`; production harm requires an approved `ReviewedHarmMatrix` (no default) | `notebooks/legacy/*`, `reports/_legacy_smoke_figures/*`, `evaluation/harm.py`, `configs/harm_matrix_template.yaml` | grep for `0.746`/`0.414` in notebooks → none; `test_harm_provenance.py` | **DONE** |

## P1 — before model training

| # | Audit finding | Root cause | Fix | Files | Verification | Status |
|---|---|---|---|---|---|---|
| P1.1 | Incomplete PlantDoc train (400/2,342) | Earlier tarball truncated on slow link | git-based listing (not API) + resumable raw-CDN download; fs↔manifest verification both directions | `datasets/plantdoc.py` | `run_phase1_checks.sh` HARD-8 (0 mismatches); `test_datasets.py::test_filesystem_vs_manifest_mismatch` | **DONE (local-partial)** — see reconciliation report for final count |
| P1.2 | PlantVillage never executed (no manifest/leaf_id/split) | Only implemented behind a datasets-dep block | Executed acquisition from the authoritative repo files (`datasets` 4.0+ can't run the repo script); manifest of 54,305 images, **41,111 with leaf_id (75.7%)**, leaf-grouped split ready; source revision recorded | `datasets/plantvillage.py`, `data/manifests/plantvillage_*` | `test_datasets.py::test_plantvillage_missing_leaf_id_stays_missing`; live run reported 41,111/13,194 | **DONE (local-partial)** — leaf_id structure acquired; pixel bytes (data.zip 2 GB) deferred to Colab |
| P1.3 | Four PlantDoc exact training duplicates | Same image under different filenames in train | Detected + listed in `leakage_pairs.csv`; documented for exclusion before training (all intra-train, no train↔test) | `reports/leakage_pairs.csv`, remediation report §leakage | leakage run reports 4 exact / 0 near | **DONE** (documented; exclusion is a training-time action) |
| P1.4 | Selective-action metric drops unmapped-true counts | Table returned without accounting | `selective_action_accuracy()` now returns `{risk_coverage, n_total, n_scored, n_unmapped_true_excluded}`; risk-coverage adds `n_deferred` | `evaluation/selective.py` | `test_selective.py::test_selective_action_accuracy_preserves_counts` | **DONE** |
| P1.5 | Missing integration tests (provenance, leakage refusal, remote/local completeness, notebook parity) | Only unit tests existed | Added `test_leakage_gate`, `test_cross_dataset`, `test_phash_scale`, `test_harm_provenance`, `test_portability`, `test_guards`, `test_datasets`, `test_metric_controls` | `tests/*` | full suite green (count in remediation report) | **DONE** |

## P2 — before paper submission

| # | Audit finding | Root cause | Fix | Files | Verification | Status |
|---|---|---|---|---|---|---|
| P2.1 | Personal absolute paths in `phash_index.csv` (double-blind risk) | Legacy notebook wrote absolute paths | Regenerated `phash_index.csv` with repo-relative paths; added a portability validator | `data/interim/phash_index.csv`, `portability.py` | `test_portability.py::test_repo_artifacts_are_portable`; `ica26-portability` → OK | **DONE** |
| P2.2 | Incomplete ignore rules (credentials, weights, trackers, caches) | Minimal `.gitignore` | Expanded to cover secrets, weights, archives, trackers, HF caches, backups | `.gitignore` | file inspection | **DONE** |
| P2.3 | Mapping sources / harm rationale / license statements not validated | No evidence discipline yet | Every mapping row cites a fetched page; harm matrix carries provenance + review gate; licenses per-dataset in reconciliation/remediation reports | `data/mapping/*`, `evaluation/harm.py`, reports | `test_harm_provenance.py`; packet §sources | **DONE** (rows `needs_review` pending human sign-off) |
| P2.4 | Smoke figures/notebooks mistakable for results | Stored outputs + figures in place | Cleared outputs; quarantined to `legacy/` + `_legacy_smoke_figures/` | notebooks, figures | grep clean | **DONE** |

## P3 — recommended

| # | Audit finding | Fix | Files | Verification | Status |
|---|---|---|---|---|---|
| P3.1 | Input-length validation in metrics | `_check_lengths()` in disease/action metrics | `evaluation/action_metrics.py` | `test_metric_controls.py::test_length_mismatch_raises` | **DONE** |
| P3.2 | Record pHash threshold/version/hash-size provenance | phash summary + gate record `phash_algorithm`, `hash_size_bits`, `threshold` | `leakage/phash.py`, `leakage/gate.py` | leakage summary JSON | **DONE** |
| P3.3 | Notebooks should call the package or be deprecated | Notebooks moved to `notebooks/legacy/` and marked superseded by `ica26` | `notebooks/legacy/*` | file layout | **DONE** |

## Blocker / contradiction list (audit §Blockers, §Contradiction check)

| Item | Severity | Disposition |
|---|---|---|
| No approved authoritative mapping | BLOCKER | Evidence packet built; hard stop enforced (P0.1) — **DONE** |
| No enforceable leakage gate | BLOCKER | Gate + enforcement (P0.2) — **DONE** |
| O(N²) phash | BLOCKER | BK-tree index (P0.3) — **DONE** |
| Notebook harm/severity conflict | BLOCKER | Quarantined (P0.5) — **DONE** |
| 2,598 vs 2,578 | MAJOR | Reconciled (P0.4) — **DONE** |
| PlantDoc train partial | MAJOR | Resumable download; final count in reconciliation — **DONE (local-partial)** |
| PlantVillage unacquired / not leaf-grouped | MAJOR | Executed; leaf_id + split acquired (P1.2) — **DONE (local-partial)** |
| Notebook 02 severity tiers | MAJOR | Quarantined; severity out of Phase-1 scope — **DONE** |
| Package "single source of truth" but notebooks don't import it | MAJOR | Notebooks quarantined to `legacy/`; package is the sole implementation — **DONE** |
| Master Plant Disease training not durably prevented | (implied) | Added `datasets/guards.py::assert_trainable` — **DONE** |
| No version control | MINOR | Recommended `git init`; **NOT done** (task: do not initialize git unless instructed) |
| Incomplete ignores + interim PII | MAJOR | Fixed (P2.1, P2.2) — **DONE** |
