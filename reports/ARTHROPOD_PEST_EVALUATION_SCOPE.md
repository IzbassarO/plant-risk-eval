# Arthropod-Pest Evaluation Scope

**Policy identifier:** `policy:arthropod-pest-scope-v1`
**Decided by:** `human_reviewer_1`
**Decided at:** `2026-08-02T21:10:00+05:00`
**Machine-readable encoding:** `configs/evaluation_scope.yaml`

_Governance document. It removes no image, deletes no manifest row, and creates no
disease-to-action mapping._

## 1. The problem

Two dataset classes label an **arthropod pest**, not a plant pathogen:

| Dataset | Exact class label | Images |
|---|---|---|
| PlantDoc | `Tomato two spotted spider mites leaf` | 2 |
| PlantVillage | `Tomato___Spider_mites Two-spotted_spider_mite` | 1,676 |

Both are *Tetranychus urticae*, the twospotted spider mite — an animal (Arachnida: Acari), not a
fungus, oomycete, bacterium, or virus. The paper's action taxonomy is **pathogen-based**:
`fungicide`, `copper_sanitation`, and `remove_vector` all presuppose a pathogen, and
`remove_vector` specifically presupposes an organism that *transmits* one. A spider mite is the
damaging agent itself, not a vector. Of the four action classes only `monitor` is not actively
wrong, and it would be right for the wrong reason — chosen by elimination rather than by evidence.

Scoring a mite class through a plant-disease action metric would therefore report a number whose
meaning does not match the metric's definition.

## 2. The decision

For **both** labels above:

- **Retained** in diagnosis-level classification and evaluation.
- **Excluded** from action-level disease evaluation.
- **Excluded** from risk-weighted (harm-matrix) disease evaluation.
- **Identified explicitly** as out-of-scope arthropod-pest classes.
- **Images are not deleted.** No row is removed from any diagnosis manifest.

This is an **evaluation-scope decision, not a data-quality exclusion.** The images are not
corrupt, mislabelled, duplicated, or otherwise defective — they are perfectly good images of a
real, correctly labelled condition. They simply fall outside the definition of the disease-action
metrics. Any report of those metrics must state that these classes were out of scope, and must not
present the reduced denominator as though it covered the full label set.

## 3. Machine-readable encoding

`configs/evaluation_scope.yaml` records one entry per class:

```yaml
- dataset: PlantDoc
  dataset_class: Tomato two spotted spider mites leaf
  include_diagnosis: true
  include_action_evaluation: false
  include_risk_weighted_evaluation: false
  exclusion_reason: arthropod_pest_out_of_disease_scope
  policy_reference: reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md
```

The default posture is **inclusive**: a class with no entry participates in every evaluation
layer. Narrowing scope always requires writing it down, with a reason and a policy reference —
`ica26.evaluation.scope.validate_scope()` rejects an entry missing either.

## 4. Enforcement

| Layer | Mechanism |
|---|---|
| Loader / predicates | `src/ica26/evaluation/scope.py` (`EvaluationScope`) |
| Action metrics | `action_lookup(..., scope=...)` drops out-of-scope classes, so they project to `None` and are counted in `n_excluded` rather than scored |
| Risk-weighted metrics | `EvaluationScope.filter_risk_weighted_lookup()`; a `None` true action is excluded by `HarmMatrix.mean_harm` |
| Canonical mapping | `scripts/apply_action_mapping_review.py` never emits an out-of-action-scope class, and treats an *approved* out-of-scope row as a hard error rather than silently choosing a winner |
| Tests | `tests/test_evaluation_scope.py` |

The scope filter is enforced independently of approval status. That is deliberate: if scope were
enforced only by "no approved mapping row exists", a future reviewer approving a mite row would
silently pull the pest class into disease-action metrics. `tests/test_evaluation_scope.py`
constructs exactly that adversarial case — an **approved** mite mapping row — and asserts the
scope filter still drops it.

## 5. PlantDoc mapping-row status

`Tomato two spotted spider mites leaf` is recorded in `data/mapping/action_mapping_review.csv` as:

- `review_status = excluded`
- `review_notes` citing `policy:arthropod-pest-scope-v1` and this document
- `reviewer = human_reviewer_1`, `reviewed_at = 2026-08-02T21:10:00+05:00`

Its scientific content (pathogen name, type, candidate action, evidence, source) is preserved
byte-exact — the row documents a decision, it is not blanked. It is **not** emitted into
`data/mapping/action_mapping_approved.csv`.

## 6. PlantVillage mapping-row status

**No PlantVillage action-mapping row exists and none was created.** The 38-class PlantVillage
action mapping has not been authored or reviewed; authoring it is a separate, later phase. The
scope entry above records the confirmed decision in advance, so that when that mapping is written
the spider-mite class is already out of disease-action and risk-weighted scope and cannot enter
those metrics by oversight.

## 7. What this decision does not do

- It does not delete, move, or modify any image.
- It does not remove any row from `data/manifests/plantdoc_manifest.csv` or
  `data/manifests/plantvillage_manifest.csv` (both still carry the classes: 2 and 1,676 rows).
- It does not change the four-class action taxonomy.
- It does not approve, create, or alter any disease-to-action mapping.
- It does not affect diagnosis-level accuracy, confusion matrices, or class counts.
