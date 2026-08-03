# PlantDoc byte-exact duplicate adjudication proposal

- Repository HEAD supplied by reviewer: `433c3ce236b5061a7f9afaaf04348f91902fe77b`
- Anonymous reviewer id recorded in CSV: `human_reviewer_1`
- Review timestamp: `2026-08-03T14:28:00+05:00`
- Policy: no byte-identical content may remain on both sides of train/test; retain one canonical record in train when the diagnosis is defensible; exclude the entire group when the diagnosis cannot be resolved without guessing.

## Decisions

| Group | Handling | Canonical label | Split | Confidence | Rationale |
|---|---|---|---|---|---|
| G01 | `keep_one_record` | `Blueberry leaf` | `move_to_train` | High | Byte-identical train/test records have the same label. Retain one canonical sample in train and remove its test twin so evaluation cannot credit memorisation. |
| G02 | `keep_one_record` | `Tomato leaf yellow virus` | `move_to_train` | High | Byte-identical train/test records have the same label. Retain one canonical sample in train and remove its test twin so evaluation cannot credit memorisation. |
| G03 | `exclude_all_records` | `not_applicable` | `not_applicable` | High for exclusion; low for diagnosis | Identical pixels carry mutually exclusive potato early- and late-blight labels. The image and available provenance do not support a defensible diagnosis, so exclude both rather than inject label noise. |
| G04 | `keep_one_record` | `Corn Gray leaf spot` | `move_to_train` | High | The lesions are narrow and largely vein-bounded, consistent with gray leaf spot; the original PlantDoc object-detection annotation also assigns Corn Gray leaf spot. Retain one canonical record in train. |
| G05 | `keep_one_record` | `Corn Gray leaf spot` | `move_to_train` | High | The filename explicitly names gray leaf spot, morphology is compatible, and the original PlantDoc object-detection annotation assigns Corn Gray leaf spot. Retain one canonical record in train. |
| G06 | `keep_one_record` | `Tomato Septoria leaf spot` | `move_to_train` | High | Byte-identical train/test records have the same label. Retain one canonical sample in train and remove its test twin so evaluation cannot credit memorisation. |
| G07 | `keep_one_record` | `Potato leaf late blight` | `move_to_train` | High | The source filename/title describes Irish blight symptoms on potato leaves, supporting potato late blight rather than early blight. Retain one canonical record in train. |
| G08 | `keep_one_record` | `Tomato leaf late blight` | `move_to_train` | Very high | The exact source identifier 5816740026 resolves to Tomato late blight foliar lesions. Both existing potato labels are wrong; relabel the canonical record as Tomato leaf late blight and keep it in train. |
| G09 | `keep_one_record` | `Potato leaf early blight` | `move_to_train` | High | Multiple lesions show the characteristic concentric target-ring pattern of potato early blight. Retain one canonical record in train. |
| G10 | `keep_one_record` | `Tomato leaf bacterial spot` | `move_to_train` | Moderate-high | The original PlantDoc test annotation labels both objects as Tomato leaf bacterial spot, and the visible symptoms are compatible. Retain one canonical record in train. |
| G11 | `exclude_all_records` | `not_applicable` | `not_applicable` | High for exclusion; low for diagnosis | Identical training pixels carry contradictory potato early- and late-blight labels. The lesions are not diagnostically decisive and reliable provenance is unavailable, so exclude both to avoid supervised label noise. |
| G12 | `keep_one_record` | `Corn leaf blight` | `move_to_train` | High | The image shows a large elongated cigar-shaped lesion, consistent with corn leaf blight; the original PlantDoc train annotation also assigns Corn leaf blight. Retain one canonical record in train. |

## Aggregate result

- 10 groups: retain one canonical record and place it in train.
- 2 groups (G03, G11): exclude all records because the contradictory diagnosis cannot be resolved defensibly.
- 0 groups remain `needs_further_review`.
- The resulting policy removes all 11 exact train/test leakage paths represented in this packet.

## Important implementation note

Do not manually move, relabel, or delete images. Replace the packet groups CSV with the adjudicated CSV, rerun `python scripts/build_plantdoc_internal_duplicate_gate.py`, and let the separately audited remediation step apply the decisions. Regenerate the packet manifest after replacing the CSV; the original manifest will no longer match.
