# Phase-1 Human Review Decisions — 2026-08-02

**Decision timestamp:** `2026-08-02T21:10:00+05:00`
**Reviewer:** `human_reviewer_1` (anonymous identifier; the submission is double-blind)

_Record of the human decisions returned for the Phase-1 review packet. It records decisions
already made; it does not make one. Nothing here approves a disease mapping, freezes a dataset,
or trains a model._

---

## 1. Cross-dataset near-duplicate adjudication

**Artifact:** `data/exclusions/cross_dataset_near_duplicate_review.csv`
**Candidates:** 16 pHash-near pairs (PlantVillage color → PlantDoc), `imagehash.phash`, Hamming ≤ 6

### Method

The reviewer **visually inspected the contact sheets** in
`reports/near_duplicate_contact_sheets/` (`contact_sheet_01.png` … `contact_sheet_04.png`), which
render the full, uncropped images so background, framing, and crop differences remain visible.

**Perceptual hashing was used for candidate generation only — it was not the decision rule.**
A low Hamming distance flagged a pair for human attention; whether the pair actually shares source
content was decided by the reviewer looking at the images. The automated visual-similarity notes
printed on the contact sheets are non-authoritative heuristics and were not treated as evidence.

### Decisions

| pair_id | `human_decision` | `final_disposition` |
|---|---|---|
| ndp-01 | `clearly_different` | `keep` |
| ndp-02 | `clearly_different` | `keep` |
| ndp-03 | `clearly_different` | `keep` |
| ndp-04 | `clearly_different` | `keep` |
| ndp-05 | `clearly_different` | `keep` |
| ndp-06 | `clearly_different` | `keep` |
| ndp-07 | `clearly_different` | `keep` |
| ndp-08 | `clearly_different` | `keep` |
| ndp-09 | `clearly_different` | `keep` |
| ndp-10 | `clearly_different` | `keep` |
| ndp-11 | `clearly_different` | `keep` |
| ndp-12 | `clearly_different` | `keep` |
| ndp-13 | `clearly_different` | `keep` |
| ndp-14 | `clearly_different` | `keep` |
| ndp-15 | `clearly_different` | `keep` |
| ndp-16 | `visually_similar_but_independent` | `keep` |

**Recorded reason, ndp-01 … ndp-15:**
> visually distinct source images; pHash similarity results from coarse single-leaf composition
> and does not indicate shared source content

**Recorded reason, ndp-16:**
> same disease category but visibly different leaf, damage geometry, background, framing, and
> source scene

ndp-16 is the only pair whose two images share a disease category (`Tomato___Late_blight` vs
`Tomato leaf late blight`), which is why it carries the weaker `visually_similar_but_independent`
verdict rather than `clearly_different`. The reviewer nonetheless judged the two images to be
independent captures, so the disposition is still `keep`.

### Aggregate counts

| Quantity | Value |
|---|---|
| Flagged near pairs | 16 |
| Resolved (terminal decision + disposition) | **16** |
| Kept | **16** |
| Excluded from evaluation | **0** |
| Uncertain | **0** |
| Deferred to secondary review | **0** |
| Rows added to `cross_dataset_reviewed_exclusions.csv` | **0** |
| Exact (Hamming 0) cross-dataset pairs | **0** |

Because no pair was excluded, `data/exclusions/cross_dataset_reviewed_exclusions.csv` correctly
remains header-only. Writing a row there would misrepresent a keep decision as an exclusion.

### Integrity

Only the five decision columns (`human_decision`, `decision_reason`, `reviewer`, `reviewed_at`,
`final_disposition`) were written. Every identity field — `pair_id`, both dataset names, both
relative paths, both class labels, both SHA-256 digests, `phash_distance`, `contact_sheet` — was
carried through byte-exact and verified against `HEAD` after the write. Pair identity comes from
the authoritative pHash pair table (`reports/leakage_plantvillage_vs_plantdoc_pairs.csv`) and the
recorded SHA-256 values; nothing was inferred from filenames.

---

## 2. Healthy-class policy

Healthy classes stay in diagnosis-level classification, map to `monitor`, and receive a narrow,
explicit exemption from **pathogen-specific** evidence requirements. No pathogen name, pathogen
type, external source, or URL was fabricated for any healthy class.

Full policy: **`reports/HEALTHY_CLASS_ACTION_POLICY.md`** (`policy:healthy-monitor-v1`).

Ten PlantDoc healthy classes were approved under it — `Apple leaf`, `Bell_pepper leaf`,
`Blueberry leaf`, `Cherry leaf`, `Peach leaf`, `Raspberry leaf`, `Soyabean leaf`,
`Strawberry leaf`, `Tomato leaf`, `grape leaf`.

---

## 3. Arthropod-pest evaluation scope

The two spider-mite classes (`Tomato two spotted spider mites leaf` in PlantDoc,
`Tomato___Spider_mites Two-spotted_spider_mite` in PlantVillage) remain diagnosis-eligible with
all images and manifest rows retained, and are excluded from action-level and risk-weighted
disease evaluation as out-of-scope arthropod pests.

Full policy: **`reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md`** (`policy:arthropod-pest-scope-v1`),
encoded in `configs/evaluation_scope.yaml`.

---

## 4. Action-mapping review status after these decisions

| Status | Rows | Notes |
|---|---|---|
| `approved` | **10** | the healthy classes above, all `monitor` |
| `excluded` | **1** | the PlantDoc spider-mite class (evaluation scope) |
| `needs_review` | **17** | PlantDoc disease classes — **still awaiting human scientific review** |
| **Total** | **28** | every PlantDoc class in `data/manifests/plantdoc_manifest.csv` |

PlantVillage contributes 38 classes / 54,305 images to the training side and has **0** action-mapping
rows. That packet has not been authored. Action-mapping coverage of the training set is therefore
still 0%.

## 5. What remains blocked

These decisions do **not** close Phase 1. Outstanding:

1. **17 PlantDoc disease mappings** remain `needs_review` and require independent scientific
   source verification and human review.
2. **The 38-class PlantVillage action-mapping review packet** has not been authored.

Phase 1 is **not** accepted. `python scripts/validate_phase1_review.py` still exits non-zero, and
that is the correct outcome.
