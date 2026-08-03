# Preserved human-review evidence

This directory is the archive of scientific decisions that a machine may not
make. Its value is entirely in being unaltered, so it has one rule:

> **Evidence is append-only.** A completed decision file is added *beside* the
> inputs the reviewer was shown, never over them.

`evidence_manifest.json` records the SHA-256 of every file here. It is generated
by `python scripts/build_human_review_evidence_manifest.py`, never edited by
hand, and carries no wall-clock field, so it can be re-derived and compared:

```
python scripts/build_human_review_evidence_manifest.py --check
```

## `plantdoc_exact_duplicates/`

PlantDoc contains 12 groups of records whose **file bytes are identical**
(R1-CRIT-002). Eleven straddle the train/test boundary and nine give identical
pixels two different diagnosis labels. Byte identity was machine-proved; what the
duplication *means* is a scientific judgement, and this is where that judgement
is recorded.

| Path | Content |
|---|---|
| `original/` | The pre-adjudication packet, exactly as the reviewer received it. Every decision column in `plantdoc_exact_duplicate_groups.csv` is blank. **Immutable.** |
| `original/plantdoc_exact_duplicate_members.csv` | The 24 immutable evidence rows: path, split, label, byte digest, decoded-pixel digest, geometry. |
| `original/packet_manifest.json` | Digests of the packet as issued, including the contact sheets the reviewer looked at. |
| `adjudicated/` | The completed decisions and the reviewer's written rationale. |

The 12 recorded decisions are 10 × `keep_one_record` and 2 × `exclude_all_records`
(G03 and G11, where identical pixels carry contradictory potato early/late blight
labels and no defensible diagnosis was available). Nothing remains
`needs_further_review`.

## How a decision reaches the dataset

Decisions are not applied by hand. The recorded CSV is installed into the review
packet and the pipeline derives the effect:

```
python scripts/apply_plantdoc_duplicate_adjudication.py   # derive the effective dataset
python scripts/build_plantdoc_internal_duplicate_gate.py  # prove it matches the decisions
```

The remediation reads exclusions, labels, and splits from the decision rows and
infers none of them; the gate fails closed if a decision is missing, unknown,
duplicated, unremediable, or contradicted by the data it was written against.
Full account: `reports/PHASE1_INTEGRITY_REMEDIATION_R2B.md`.
