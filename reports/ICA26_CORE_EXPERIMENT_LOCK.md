# ICA 2026 Paper Experiment Dataset Lock

**Schema:** `ica26.paper_experiment_dataset_lock/1`
**Artifact:** `data/manifests/ica26_core_experiment_lock.json`
**Lock digest:** `83449f60136918554904cb9c596122f8b89cb51ff5bb5c52c541394a5698082d`
**Built at repository commit:** `38bb7b335533b0e7b174fe0087d23d65c8d938f3`
**Dataset owner:** `dataset_owner_1`

## What this is, and what it is not

This is a **reproducible scientific lock** over the exact dataset inputs used by
the ICA 2026 paper *Leakage-Controlled Cross-Domain Evaluation of Deep Learning
Models for Plant Disease Classification*.

**It is not the repository's formal governance freeze.** It records:

- no human independent-audit signature,
- no closure of any audit finding,
- no formal governance freeze approval.

The formal Core Dataset governance freeze remains **pending**. `scripts/run_phase1_checks.sh`
continues to report `SCIENTIFIC PHASE-1 STATUS: BLOCKED` (exit 2) on the two
governance conditions `open_audit_findings_closed` and `freeze_approval_recorded`,
and this lock does not change that. The lock exists so that ordinary computer-vision
experiments can proceed against a corpus whose exact contents are pinned and
machine-verifiable, without pretending that the governance process has concluded.

## Owner authorization

The dataset owner (`dataset_owner_1`) authorizes the exact locked Core Dataset
for, and only for:

- baseline CV training
- in-domain evaluation
- cross-domain evaluation
- calibration experiments
- generation of paper tables and figures

Explicitly **not** authorized by this lock: Risk Evaluation Layer completion,
action-aware training, harm-weighted evaluation, treatment recommendation.

## Assertions

| Assertion | Value |
|---|---|
| No source image was deleted | true |
| No image byte was modified | true |
| G07 / G08 / G10 were excluded, not relabelled | true |
| Formal governance freeze still pending | true |
| Lock scope is ICA 2026 paper experiments only | true |

Exclusion removes a record from the Core evaluation population only. The source
manifest still carries all 2,578 acquired records, every image file remains on
disk with its original bytes, and every digest in this lock is computed over
those unmodified bytes.

## Verified counts

### PlantVillage

| Quantity | Value |
|---|---|
| Total | 54,305 |
| Train | 43,596 |
| Test | 10,709 |
| Classes | 38 |

### PlantDoc

| Quantity | Value |
|---|---|
| Source (acquired) | 2,578 |
| Previous effective | 2,564 |
| Core | 2,561 |
| Core train | 2,336 |
| Core test | 225 |
| Classes | 28 |
| Non-reviewed unchanged | 2,554 |
| Retained reviewed | 7 |
| Excluded reviewed | 17 |

### Leakage (PlantVillage vs PlantDoc, pHash Hamming ≤ 6)

| Population | Exact | Near | Unresolved |
|---|---|---|---|
| Acquired (2,578 evaluation records) | 0 | 16 | 0 |
| Core (2,561 evaluation records) | 0 | 16 | 0 |

All 16 near pairs were adjudicated by a human as `clearly_different` / `keep`;
perceptual hashing was used for candidate generation only, never as the decision
rule.

## Bound artifacts

24 files across 10 roles are bound by SHA-256. Any change to any of them fails
validation and aborts training.

| Role | Files |
|---|---|
| `plantvillage_committed_manifest` | `data/manifests/plantvillage_manifest.csv` |
| `plantvillage_pinned_reconstruction_evidence` | `reports/plantvillage_manifest_reconstruction.json`, `data/manifests/plantvillage_source_snapshot.json`, `data/manifests/plantvillage_summary.json` |
| `plantdoc_acquired_manifest` | `data/manifests/plantdoc_manifest.csv`, `data/manifests/plantdoc_source_snapshot.json`, `data/manifests/plantdoc_summary.json` |
| `plantdoc_effective_manifest` | `data/manifests/plantdoc_effective_manifest.csv` |
| `plantdoc_core_manifest` | `data/manifests/plantdoc_core_effective_manifest.csv` |
| `conservative_exclusion_artifact` | `data/exclusions/core_dataset_v1_conservative_exclusions.csv` |
| `duplicate_exclusion_and_adjudication_artifacts` | `data/exclusions/plantdoc_internal_duplicate_resolution.csv`, `data/exclusions/cross_dataset_exact_exclusions.csv`, `data/exclusions/cross_dataset_reviewed_exclusions.csv`, `data/exclusions/cross_dataset_near_duplicate_review.csv`, `reports/plantdoc_internal_duplicate_gate.json`, `data/manifests/plantdoc_case_collision_mapping.csv` |
| `leakage_reports` | `reports/leakage_two_population_report.json`, `reports/leakage_gate.json`, `reports/leakage_plantvillage_vs_plantdoc_pairs.csv`, `reports/leakage_plantvillage_vs_plantdoc_summary.json` |
| `class_taxonomy` | `data/mapping/plantvillage_class_list.csv`, `data/mapping/action_mapping_review.csv`, `configs/evaluation_scope.yaml` |
| `cross_domain_class_mapping` | `data/mapping/ica26_cross_domain_class_mapping.csv` |

Beyond file digests, the lock also binds, per corpus:

- the **class taxonomy** (the exact sorted label list),
- the **class-index mapping** and its digest (so a re-derived index that differs
  in even one position is caught),
- the **split assignment identity digest** over sorted
  `(relpath, split, class_label, sha256)` — this catches a moved record, a
  relabelled record, or a changed image content digest, and is insensitive to
  row order in the CSV,
- **per-class split counts**.

## Cross-domain class mapping

21 shared canonical classes covering **1,951** PlantDoc Core images (1,773 train
/ 178 test). See `data/mapping/ica26_cross_domain_class_mapping.csv` and the
"Shared-class definition" section of `reports/ICA26_EXPERIMENT_PROTOCOL.md`.

## Reproduction

```bash
# Rebuild and confirm byte-identical
python scripts/ica26_build_experiment_lock.py --check

# Validate the on-disk corpus against the lock (what every training run does)
python scripts/ica26_validate_experiment_lock.py

# Also confirm every manifest row resolves to a file on disk
python scripts/ica26_validate_experiment_lock.py --check-pixels
```

`--check` carries `created_at_utc` and `repository_commit` over from the existing
file rather than recomputing them. Those two fields record when and at which
commit the lock was written; recomputing them would make an unchanged corpus look
changed, because committing the lock necessarily advances `HEAD`. Every other
field, including all 24 digests, is rebuilt from disk and compared.

## Validator behaviour

`scripts/ica26_validate_experiment_lock.py` recomputes and compares:

1. all 24 artifact SHA-256 digests
2. record counts and split counts per corpus
3. the class taxonomy (exact label list)
4. the class-index mapping digest
5. the split/label/identity assignment digest
6. per-class split counts
7. the independently verified counts above, including PlantDoc source 2,578 and
   previous-effective 2,564
8. leakage exact/near counts for both populations
9. the shared-class set and both directions of the cross-domain mapping

With `--check-pixels` it additionally confirms every manifest row resolves to a
file on disk. It reports **every** violation rather than stopping at the first,
and `require_valid_lock()` — called at the top of every training command — raises
and aborts the run if any violation is present.
