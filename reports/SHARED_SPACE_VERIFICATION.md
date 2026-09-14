# Shared-Space Control: Independent Verification

**Date:** 2026-09-14
**Verified file:** `experiments/ica26/metrics/shared_space_control.json` (5,504 B, schema `ica26.shared_space_control/1`, `created_at_utc` 2026-08-06T15:20:34Z). It is byte-identical to the `origin/claude/ica26-training-launch@9acdebf` copy, merged into `main`.
**Evidence used:** only committed files. That means the 38×38 `evaluations.in_domain_test.confusion_matrix` plus `per_class` from the nine `experiments/ica26/metrics/pv_*.json`, `evaluations.cross_domain_plantdoc_core.macro_f1` from the same files, and `data/mapping/ica26_cross_domain_class_mapping.csv`.
**Verdict:** **all 36 stored per-run metric values fall inside their bounds. All 9 `n_evaluated` counts are exact. All 18 `summary` values reproduce from `per_run` to within 1e-9. No value fails.**

## 1. What `scripts/ica26_shared_space_control.py` computed

The steps below are from the script (9,045 B), which is byte-identical to the branch copy. Line numbers refer to it.

1. **Inputs, per PlantVillage-trained run** (`pv_{resnet50,efficientnet_b0,mobilenet_v3_small}_s{42,1337,2026}`):
   - `experiments/ica26/runs/<run>/predictions_in_domain_test.npz`, holding float32 `logits` (10,709 × 38) and `labels`;
   - the run's `result.json` for the class order.
   - The `.npz` dumps are gitignored and have since been lost, which is why the file cannot be re-run.
2. **Gate** (l. 66–76): the argmax accuracy of the dump must equal the reported `in_domain_test.accuracy` within `TOLERANCE = 1e-9`. Otherwise the run aborts.
3. **Population** (l. 80–93): keep only test images whose **true** PlantVillage class is one of the 21 `included` rows of the frozen mapping. That is 5,382 of 10,709 images. Labels are re-indexed to the 21 canonical classes, sorted by canonical id.
4. **Scores** (l. 95–105):
   - softmax over all 38 logits (`exp(z − max z)` then normalise), with **no temperature**;
   - sum the probabilities of the PlantVillage columns that map to each canonical class. The mapping is 1:1, so this is a column selection;
   - record the mean of the summed mass before renormalisation, `mean_retained_probability_mass_before_renormalisation`;
   - **renormalise** over the 21 classes.
   - This is the same arithmetic as the cross-domain evaluation in `src/ica26/experiments/train.py::evaluate_cross_domain`.
5. **Prediction and metrics** (l. 107–119):
   - prediction = argmax of the renormalised 21-way vector;
   - `ica26.experiments.metrics.evaluate_classification` (scikit-learn, `zero_division=0`, macro averages over supported classes; all 21 are present).
   - **Written:** `accuracy`, `macro_f1`, `weighted_f1`, `balanced_accuracy`, retained mass and counts.
   - `probabilistic_metrics` (ECE, NLL, Brier) was computed but **not written**.
6. **Summary** (l. 130–163), per backbone:
   - mean and sample SD (`ddof=1`) over seeds of the 21-class macro-F1;
   - mean of the **unscaled** cross-domain macro-F1 from `metrics/pv_<run>.json`;
   - the relative drop `(F1_21 − F1_xd) / F1_21 × 100`, computed **within each seed** and then averaged, with sample SD.

**Description for the paper, factually:** PlantVillage test images from the 21 shared classes were scored by the same PlantVillage-trained checkpoints. The scoring used the identical shared-space procedure as the cross-domain evaluation: source probabilities summed within each canonical class, renormalised over the 21 shared classes, no temperature. It was computed from the 38-way test logits saved at training time; no model was re-run.

## 2. Verification method

**What the bounds range over.**
- The mapping is 1:1, so for an image whose true class is mapped:
  - if the **38-way argmax** is a mapped column, the control's prediction is that same column, because renormalisation rescales the mapped entries by a positive constant;
  - if the 38-way argmax is one of the 17 unmapped columns, the control's prediction is some mapped column that the confusion matrix cannot identify.
- Per run there are U = 4–12 such images, spread over 3–8 true classes. Every other cell of the control's 21×21 confusion matrix is fixed by the committed 38×38 matrix. The bounds below range over **every possible placement** of those U images.

**Consistency checks on the committed matrices** (all pass):
- the matrix total is 10,709;
- the matrix trace reproduces `in_domain_test.accuracy` to 1e-12;
- row sums equal `per_class.support`;
- the `per_class.class_name` order equals `confusion_matrix_labels`.

**Bounds.** Let TPᵢ, FPᵢ and FNᵢ be counts over the 21 mapped rows and columns, with the unknown images counted as FN of their true class.

| Metric | Lower bound | Upper bound |
|---|---|---|
| Accuracy | all U wrong: ΣTP / N | all U right: (ΣTP + U) / N |
| Balanced accuracy (mean recall; a row's recall depends only on that row) | all U wrong | all U right |
| Macro-F1, weighted-F1 | **exact minimum** over all placements into a different class. Each Fⱼ is convex and decreasing in added false positives, so this is solved as a convex min-cost flow. | every unknown image placed on its own class. This is the maximum, because a correct placement only raises that class's F1 and leaves the others unchanged. |

**Solver check:** the flow minimum was checked against brute-force enumeration of all 21^U placements on the three runs where that is tractable (U = 4, 4, 5), for both macro-F1 and weighted-F1. It matched to 1e-12.

**Counts:** `n_evaluated` must equal the summed support of the 21 mapped rows (5,382), `n_in_domain_test_total` must equal 10,709, and `n_shared_classes = n_classes_present = 21`.

**Summary block:** means and sample SDs were recomputed from the stored `per_run` values and the committed cross-domain macro-F1.

The verifier is a stdlib-only script run from the session scratchpad; it is not part of the repository.

## 3. Results per run

"Unknown items (rows)" is U and the number of true classes it is spread over. All values are rounded to 6 decimals; the comparison used full precision with a 1e-12 tolerance.

| Run | N | Unknown items (rows) | Metric | Lower bound | Stored value | Upper bound | Inside |
|---|---|---|---|---|---|---|---|
| pv_resnet50_s42 | 5382 | 11 (4) | accuracy | 0.990152 | 0.991639 | 0.992196 | yes |
| pv_resnet50_s42 | 5382 | 11 (4) | macro_f1 | 0.986801 | 0.991072 | 0.991478 | yes |
| pv_resnet50_s42 | 5382 | 11 (4) | balanced_accuracy | 0.989306 | 0.990773 | 0.991185 | yes |
| pv_resnet50_s42 | 5382 | 11 (4) | weighted_f1 | 0.990138 | 0.991651 | 0.992210 | yes |
| pv_resnet50_s1337 | 5382 | 11 (6) | accuracy | 0.993683 | 0.994983 | 0.995726 | yes |
| pv_resnet50_s1337 | 5382 | 11 (6) | macro_f1 | 0.991292 | 0.995137 | 0.995875 | yes |
| pv_resnet50_s1337 | 5382 | 11 (6) | balanced_accuracy | 0.993451 | 0.994570 | 0.995175 | yes |
| pv_resnet50_s1337 | 5382 | 11 (6) | weighted_f1 | 0.993661 | 0.994976 | 0.995716 | yes |
| pv_resnet50_s2026 | 5382 | 9 (5) | accuracy | 0.996656 | 0.997956 | 0.998328 | yes |
| pv_resnet50_s2026 | 5382 | 9 (5) | macro_f1 | 0.994266 | 0.997799 | 0.998229 | yes |
| pv_resnet50_s2026 | 5382 | 9 (5) | balanced_accuracy | 0.995911 | 0.997147 | 0.997690 | yes |
| pv_resnet50_s2026 | 5382 | 9 (5) | weighted_f1 | 0.996644 | 0.997955 | 0.998327 | yes |
| pv_efficientnet_b0_s42 | 5382 | 5 (4) | accuracy | 0.998142 | 0.998699 | 0.999071 | yes |
| pv_efficientnet_b0_s42 | 5382 | 5 (4) | macro_f1 | 0.996912 | 0.998753 | 0.999035 | yes |
| pv_efficientnet_b0_s42 | 5382 | 5 (4) | balanced_accuracy | 0.997943 | 0.998495 | 0.998712 | yes |
| pv_efficientnet_b0_s42 | 5382 | 5 (4) | weighted_f1 | 0.998141 | 0.998699 | 0.999070 | yes |
| pv_efficientnet_b0_s1337 | 5382 | 4 (3) | accuracy | 0.997399 | 0.998142 | 0.998142 | yes |
| pv_efficientnet_b0_s1337 | 5382 | 4 (3) | macro_f1 | 0.996245 | 0.997926 | 0.997926 | yes |
| pv_efficientnet_b0_s1337 | 5382 | 4 (3) | balanced_accuracy | 0.997231 | 0.997832 | 0.997832 | yes |
| pv_efficientnet_b0_s1337 | 5382 | 4 (3) | weighted_f1 | 0.997397 | 0.998141 | 0.998141 | yes |
| pv_efficientnet_b0_s2026 | 5382 | 4 (4) | accuracy | 0.996656 | 0.997213 | 0.997399 | yes |
| pv_efficientnet_b0_s2026 | 5382 | 4 (4) | macro_f1 | 0.995526 | 0.997173 | 0.997260 | yes |
| pv_efficientnet_b0_s2026 | 5382 | 4 (4) | balanced_accuracy | 0.995948 | 0.996562 | 0.996611 | yes |
| pv_efficientnet_b0_s2026 | 5382 | 4 (4) | weighted_f1 | 0.996652 | 0.997211 | 0.997397 | yes |
| pv_mobilenet_v3_small_s42 | 5382 | 11 (7) | accuracy | 0.994983 | 0.996656 | 0.997027 | yes |
| pv_mobilenet_v3_small_s42 | 5382 | 11 (7) | macro_f1 | 0.991158 | 0.995783 | 0.996225 | yes |
| pv_mobilenet_v3_small_s42 | 5382 | 11 (7) | balanced_accuracy | 0.993090 | 0.995551 | 0.995768 | yes |
| pv_mobilenet_v3_small_s42 | 5382 | 11 (7) | weighted_f1 | 0.994968 | 0.996653 | 0.997024 | yes |
| pv_mobilenet_v3_small_s1337 | 5382 | 12 (7) | accuracy | 0.995169 | 0.997399 | 0.997399 | yes |
| pv_mobilenet_v3_small_s1337 | 5382 | 12 (7) | macro_f1 | 0.991888 | 0.997527 | 0.997527 | yes |
| pv_mobilenet_v3_small_s1337 | 5382 | 12 (7) | balanced_accuracy | 0.993895 | 0.997087 | 0.997087 | yes |
| pv_mobilenet_v3_small_s1337 | 5382 | 12 (7) | weighted_f1 | 0.995157 | 0.997399 | 0.997399 | yes |
| pv_mobilenet_v3_small_s2026 | 5382 | 12 (8) | accuracy | 0.994797 | 0.996656 | 0.997027 | yes |
| pv_mobilenet_v3_small_s2026 | 5382 | 12 (8) | macro_f1 | 0.991810 | 0.996608 | 0.996973 | yes |
| pv_mobilenet_v3_small_s2026 | 5382 | 12 (8) | balanced_accuracy | 0.994181 | 0.996206 | 0.996423 | yes |
| pv_mobilenet_v3_small_s2026 | 5382 | 12 (8) | weighted_f1 | 0.994785 | 0.996654 | 0.997026 | yes |

- **Counts:** every run gives `n_evaluated` = 5382 (exact), `n_in_domain_test_total` = 10709 and `n_shared_classes` = `n_classes_present` = 21.
- **`summary` block:** all 18 values reproduce from `per_run` and the committed cross-domain macro-F1 to within 1e-9. These are, for each of the three backbones: `macro_f1_in_domain_shared_mean`, `macro_f1_in_domain_shared_sd`, `macro_f1_cross_domain_mean`, `relative_drop_percent_mean`, `relative_drop_percent_sd` and `n_seeds`.

## 4. What this does and does not establish

- **Established:**
  - Every stored accuracy, macro-F1, balanced accuracy and weighted-F1 is consistent with the committed per-run confusion matrices under the documented procedure.
  - The population size is exact.
  - The summary arithmetic, including the paired within-seed drop, is correct.
  - Two runs (`pv_efficientnet_b0_s1337`, `pv_mobilenet_v3_small_s1337`) sit exactly at the upper bound on all four metrics. That is consistent with every out-of-space argmax being recovered to its true class after renormalisation.
- **Not established:**
  - **Exact** values. The bound widths are 0.0006–0.0056, so a value inside a bound is consistent, not proven.
  - `mean_retained_probability_mass_before_renormalisation`. No committed artifact constrains it; it is **unverified**.
  - The input dumps' integrity beyond the script's own gate. The file records no lock digest, git commit or dump digests.
- **Precision:** the verified values support the paper's four-decimal macros. The bounds exclude any error at the scale of the reported seed SDs (≥ 0.0008).
