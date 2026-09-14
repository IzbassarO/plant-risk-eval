# Revision Inventory: ICA 2026 camera-ready

**Date:** 2026-09-14 · **Scope:** read-only. No `.tex` edited, nothing trained, downloaded or installed, no `git` command run. This file is the only write.
**Authoritative source:** `paper/camera_ready_source/` (Overleaf export; untracked in the working tree).
**Numbers:** only values committed on `origin/claude/ica26-training-launch` (tip `9acdebf`). I read the branch from `.git/objects/pack` with the read-only reader described in `reports/RECOVERY_AUDIT.md` §0.
**Derived arithmetic:** every value below that is not a verbatim copy (means, SDs, paired drops) was computed from committed per-run values in this audit and is labelled as such. None of it may go into the paper by hand (see §3).

---

## 1. The 21-class in-domain control

### 1.1 File and provenance

| Item | Value |
|---|---|
| File | `experiments/ica26/metrics/shared_space_control.json`, 5,504 B, schema `ica26.shared_space_control/1` |
| `created_at_utc` | `2026-08-06T15:20:34+00:00` |
| Committed in | `9acdebf` "Final stage" (2026-08-07). It was absent from the parent `f3b79de`. |
| Produced by | `scripts/ica26_shared_space_control.py` (9,045 B, also first committed in `9acdebf`) |
| Verbatim `description` | "PlantVillage in-domain test performance restricted to the shared cross-domain label space, scored through the identical grouping and renormalisation used cross-domain. Holds task difficulty fixed at 21 classes so the remaining gap is domain shift alone." |
| Runs covered | The 9 PlantVillage-trained runs `pv_{resnet50,efficientnet_b0,mobilenet_v3_small}_s{42,1337,2026}`. No PlantDoc-trained runs. |
| Not recorded in the file | lock digest, git commit, digests of the input dumps |
| Re-runnable today | **No.** Its inputs, `runs/pv_*/predictions_in_domain_test.npz`, are lost (RECOVERY_AUDIT §2a), so neither `--check` nor a rebuild is possible. |

**What was evaluated, step by step** (from the script, `evaluate_one()`):

1. **Input:** the saved 38-way PlantVillage **test** logits and labels for the run (`predictions_in_domain_test.npz`). The class order comes from that run's `result.json`.
2. **Sanity gate:** the recomputed argmax accuracy of the dump must equal the reported `in_domain_test.accuracy` within 1e-9, otherwise the script aborts. This is what binds each dump to its run.
3. **Population:** keep only test images whose **true** class is one of the 21 PlantVillage classes in `data/mapping/ica26_cross_domain_class_mapping.csv` (`inclusion_status = included`). That leaves **5,382 of 10,709** images.
4. **Scoring:** softmax over all 38 logits, **without temperature**. Probabilities are summed within each canonical class, which is a column selection because the mapping is strictly 1:1. The 21-way vector is then **renormalised** over the 21 shared classes, and the argmax is taken.
   - **Answer to "with or without renormalisation": WITH.** This is the same `_grouped` arithmetic as `train.py::evaluate_cross_domain`.
5. **Metrics:** `evaluate_classification` over the 21 canonical classes, with all 21 present. Only accuracy, macro-F1, weighted-F1, balanced accuracy and mean retained mass are written. `probabilistic_metrics` is computed but **not written**.
6. **Summary:** for each backbone and seed, the relative macro-F1 drop is `(F1_21 − F1_xd) / F1_21 × 100`. `F1_xd` is the **unscaled** `cross_domain_plantdoc_core.macro_f1` from `metrics/pv_<run>.json`, the same value the paper publishes. The script reports mean and sample SD (`ddof=1`) across seeds.

### 1.2 Committed values, verbatim (`per_run`)

All nine rows have `n_evaluated = 5382`, `n_in_domain_test_total = 10709`, `n_shared_classes = 21` and `n_classes_present = 21`.

| run_id | accuracy | macro_f1 | weighted_f1 | balanced_accuracy | mean_retained_probability_mass_before_renormalisation |
|---|---|---|---|---|---|
| pv_resnet50_s42 | 0.9916387959866221 | 0.9910715643560593 | 0.991651444658917 | 0.9907733821588703 | 0.957545 |
| pv_resnet50_s1337 | 0.9949832775919732 | 0.9951368112568764 | 0.9949755059733857 | 0.9945700698627393 | 0.945224 |
| pv_resnet50_s2026 | 0.9979561501300632 | 0.9977992884196741 | 0.9979547873824358 | 0.9971470852043951 | 0.954924 |
| pv_efficientnet_b0_s42 | 0.9986993682645856 | 0.9987533239972259 | 0.9986986848153088 | 0.9984947974280234 | 0.953474 |
| pv_efficientnet_b0_s1337 | 0.9981419546636938 | 0.9979262065912418 | 0.998141215941367 | 0.9978318841875742 | 0.948651 |
| pv_efficientnet_b0_s2026 | 0.9972129319955407 | 0.9971727089400546 | 0.9972107848067725 | 0.9965618749145949 | 0.9553 |
| pv_mobilenet_v3_small_s42 | 0.9966555183946488 | 0.9957829429709464 | 0.9966532002997927 | 0.9955509317131757 | 0.952409 |
| pv_mobilenet_v3_small_s1337 | 0.9973987365291713 | 0.9975272894915573 | 0.9973987016145569 | 0.9970865083558764 | 0.949502 |
| pv_mobilenet_v3_small_s2026 | 0.9966555183946488 | 0.9966075338060879 | 0.9966544211127276 | 0.9962058460126938 | 0.949535 |

### 1.3 Committed values, verbatim (`summary`)

All three backbones have `n_seeds = 3`.

| key | model | macro_f1_in_domain_shared_mean | macro_f1_in_domain_shared_sd | macro_f1_cross_domain_mean | relative_drop_percent_mean | relative_drop_percent_sd |
|---|---|---|---|---|---|---|
| resnet50 | ResNet-50 | 0.9946692213442033 | 0.0033881481688174324 | 0.22912286578472793 | 76.96261103471996 | 1.147715032343988 |
| efficientnet_b0 | EfficientNet-B0 | 0.9979507465095074 | 0.0007905932237443898 | 0.229999408180616 | 76.95315986127146 | 0.6365048782249599 |
| mobilenet_v3_small | MobileNetV3-Small | 0.9966392554228638 | 0.0008726058054585952 | 0.1869399210094623 | 81.24232269677196 | 1.1137355439189147 |

### 1.4 Mean ± sample SD per backbone, in the style of the in-domain compact table

The style follows `tables/table2_in_domain_performance_compact.tex` (printed as **Table 1** in the 15-page PDF): 4 decimals, mean ± sample SD over three seeds.

- The accuracy, weighted-F1, balanced-accuracy and retained-mass aggregates are **derived in this audit** from `per_run`.
- The macro-F1 row matches the committed `summary` exactly.

| Model | Corpus | N | Accuracy | Macro-F1 | Weighted-F1 | Balanced acc. | Ret. mass |
|---|---|---|---|---|---|---|---|
| ResNet-50 | PV, 21 shared classes | 5382 | 0.9949 ± 0.0032 | 0.9947 ± 0.0034 | 0.9949 ± 0.0032 | 0.9942 ± 0.0032 | 0.9526 ± 0.0065 |
| EfficientNet-B0 | PV, 21 shared classes | 5382 | 0.9980 ± 0.0008 | 0.9980 ± 0.0008 | 0.9980 ± 0.0008 | 0.9976 ± 0.0010 | 0.9525 ± 0.0034 |
| MobileNetV3-Small | PV, 21 shared classes | 5382 | 0.9969 ± 0.0004 | 0.9966 ± 0.0009 | 0.9969 ± 0.0004 | 0.9963 ± 0.0008 | 0.9505 ± 0.0017 |

**Relative macro-F1 drop, 21-class in-domain → 21-way cross-domain** (committed `summary`): ResNet-50 **76.96 ± 1.15 %**, EfficientNet-B0 **76.95 ± 0.64 %**, MobileNetV3-Small **81.24 ± 1.11 %**. At the one decimal the paper uses: 77.0 ± 1.1, 77.0 ± 0.6, 81.2 ± 1.1.

### 1.5 What is NOT available (do not promise in the text)

| Quantity | Status |
|---|---|
| Calibration of the 21-class control (ECE, MCE, NLL, Brier, reliability diagram) | **Not available.** Computed by the script but never written; the dumps are lost. |
| Temperature-scaled variant of the control | **Not available.** Never computed. |
| Selective prediction / AURC for the control | **Not available.** |
| Per-class metrics or a confusion matrix for the renormalised 21-class control | **Not available.** |
| Significance: McNemar between backbones on the control, or control vs 38-way | **Not available.** Needs per-item correctness. |
| BCa bootstrap CIs for the control | **Not available.** |
| Any per-item output, or any re-derivation or verification of the committed values | **Not available.** |
| Strict (argmax outside the 21 counts as an error) **cross-domain** score | **Not available** (RECOVERY_AUDIT §2b). |
| Macro precision / macro recall for the control | **Not available** (not written). |

**Available but not in this file** (derivable from committed 38×38 confusion matrices in `metrics/pv_*.json`; would need generator code before citing):
- The **no-renormalisation** in-domain variant: images restricted to the 21 true classes, scored by the 38-way argmax, with out-of-space predictions counted as errors. Its accuracy and macro-F1 are exactly derivable.
- Derived here for reference only, strict macro-F1: ResNet-50 0.9943 ± 0.0035, EfficientNet-B0 0.9977 ± 0.0009, MobileNetV3-Small 0.9955 ± 0.0006.
- Strict accuracy: 0.9935 ± 0.0033, 0.9974 ± 0.0007, 0.9950 ± 0.0002.

---

## 2. The paired comparison

### 2.1 Per backbone (mean ± sample SD over seeds 42, 1337, 2026)

- **Published** values come from camera-ready macros: `\MacroFPvIn*`, `\MacroFXd*`, `\AbsDropF*`, and Table 5's 2-decimal `RelDrop`.
- **New** values are the committed control (§1).
- **Δ** and the ratio are derived here, paired within seed.

| Backbone | F1, 38-way in-domain (published) | F1, 21-class in-domain (new) | F1, 21-way cross-domain (published) | Rel. drop 38 → xd (published) | Rel. drop 21 → xd (new) | Δ drop, per seed (21 − 38) | Share of drop surviving | Abs. drop 38 → xd | Abs. drop 21 → xd |
|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | 0.9927 ± 0.0029 | 0.9947 ± 0.0034 | 0.2291 ± 0.0107 | 76.92 ± 1.13 % | 76.96 ± 1.15 % | +0.044 ± 0.015 pp | 100.06 % | 0.7636 ± 0.0131 | 0.7655 ± 0.0138 |
| EfficientNet-B0 | 0.9950 ± 0.0006 | 0.9980 ± 0.0008 | 0.2300 ± 0.0065 | 76.89 ± 0.65 % | 76.95 ± 0.64 % | +0.068 ± 0.018 pp | 100.09 % | 0.7650 ± 0.0064 | 0.7680 ± 0.0058 |
| MobileNetV3-Small | 0.9927 ± 0.0004 | 0.9966 ± 0.0009 | 0.1869 ± 0.0109 | 81.17 ± 1.10 % | 81.24 ± 1.11 % | +0.074 ± 0.011 pp | 100.09 % | 0.8058 ± 0.0111 | 0.8097 ± 0.0118 |

### 2.2 Per seed (derived; macro-F1)

| Run | F1₃₈ | F1₂₁ | F1_xd | Drop₃₈ % | Drop₂₁ % | Δ pp |
|---|---|---|---|---|---|---|
| pv_resnet50_s42 | 0.989946 | 0.991072 | 0.241410 | 75.614 | 75.642 | +0.028 |
| pv_resnet50_s1337 | 0.992547 | 0.995137 | 0.221770 | 77.656 | 77.715 | +0.058 |
| pv_resnet50_s2026 | 0.995708 | 0.997799 | 0.224189 | 77.484 | 77.532 | +0.047 |
| pv_efficientnet_b0_s42 | 0.995597 | 0.998753 | 0.235862 | 76.310 | 76.384 | +0.075 |
| pv_efficientnet_b0_s1337 | 0.994431 | 0.997926 | 0.231175 | 76.753 | 76.834 | +0.081 |
| pv_efficientnet_b0_s2026 | 0.995077 | 0.997173 | 0.222961 | 77.594 | 77.641 | +0.047 |
| pv_mobilenet_v3_small_s42 | 0.992749 | 0.995783 | 0.198215 | 80.034 | 80.095 | +0.061 |
| pv_mobilenet_v3_small_s1337 | 0.993055 | 0.997527 | 0.176378 | 82.239 | 82.319 | +0.080 |
| pv_mobilenet_v3_small_s2026 | 0.992297 | 0.996608 | 0.186227 | 81.233 | 81.314 | +0.081 |

### 2.3 How much of the published 76.9–81.2 % drop survives at 21 classes on both sides

**All of it.**
- On every one of the 9 model–seed pairs, 21-class in-domain macro-F1 is *higher* than 38-way, so the drop gets slightly *larger* when the in-domain side is held at 21 classes.
- The increase is +0.03 to +0.08 percentage points (100.06–100.09 % of the published drop).
- At the paper's one-decimal precision the drops read 77.0 / 77.0 / 81.2 % against the published 76.9 / 76.9 / 81.2 %.
- Changing the label space accounts for **none** of the measured drop.
- The change is 1/8 to 1/40 of the across-seed SD of the drop (0.64–1.15 pp), so the defensible wording is **"unchanged"**. Neither "larger" nor "smaller" is supported.

### 2.4 Caveats: why the decomposition is less clean than it looks

1. **The control fixes the label space, not how lenient the scoring is.**
   - Both sides are renormalised over 21 classes, but renormalisation does very different amounts of work on each side. The mean retained mass is **0.950–0.953 in domain** (§1.4) against **0.566–0.659 cross-domain** (`\RetainedMass*`).
   - Cross-domain, 34–43 % of each model's probability is discarded before the argmax, and predictions that would have landed on a non-shared class are silently redirected into the shared space.
   - The strict cross-domain score that would expose this cannot be computed (§1.5), so what was compared is "lenient vs lenient".
   - Strict accuracy can never exceed lenient accuracy, so a strict cross-domain accuracy would be no higher than the published one. Macro-F1 is not strictly monotone under that change, but a lower value is very likely.
   - In domain the same leniency is negligible: strict and renormalised macro-F1 differ by only 0.0003–0.0011 (§1.5).
2. **The in-domain side is at ceiling, so the control could hardly have moved the drop.**
   - With F1₃₈ ≥ 0.989 the relative drop is ≈ 1 − F1_xd/F1_in. Even a perfect 21-class F1 of 1.0 would change ResNet-50's drop only from 76.92 % to 77.09 %.
   - The control shows that in-domain performance does not depend on the restriction. It cannot show that the cross-domain task would be as hard at 38 ways, because no 38-way PlantDoc evaluation exists.
   - The paper's Limitation 1 concern (task difficulty) is answered only on the in-domain side.
3. **Class composition, not renormalisation, explains most of the in-domain increase.**
   - In the committed 38-way `per_class` blocks, the 21 mapped classes are easier than the 17 excluded ones. Mean per-class F1 is 0.9933 vs 0.9920 (ResNet-50), 0.9974 vs 0.9921 (EfficientNet-B0) and 0.9951 vs 0.9898 (MobileNetV3-Small).
   - For ResNet-50, 0.9927 (38-way) → 0.9943 (restricted population, strict argmax) → 0.9947 (renormalised). About 80 % of that small gain is population selection.
4. **The evaluation populations differ in kind.**
   - In-domain: PlantVillage **test split only** (5,382 images).
   - Cross-domain: **all 1,951** shared-class PlantDoc Core images, including those in PlantDoc's *train* split (split composition is in every `result.json`).
   - Per-class supports differ between the two sets. Macro-F1 weights classes equally, so the effect is smaller than for accuracy, but the two sets are not matched samples.
5. **The only uncertainty available is the spread across seeds.**
   - No bootstrap CI and no paired test exist for the control. "The drop is unchanged" must be stated relative to seed SD, not as a non-significant test result.
6. **Provenance is weaker than for every other number in the paper.**
   - The JSON cannot be regenerated or `--check`ed, and it carries no lock digest, commit or input-dump digests.
   - It was written 12 minutes before `f3b79de` (the source of the camera-ready macro file) was committed, but the script and JSON were only committed in `9acdebf`.
   - Two things bind it to the runs: the script's sanity gate (dump accuracy equals reported accuracy within 1e-9), and consistency with the committed confusion matrices. All 9 committed accuracies fall inside the exact bounds derivable from the 38×38 matrices (RECOVERY_AUDIT §2a).
7. **Temperature is not applied.** The control is argmax-based, so F1 is identical with or without temperature. Consequently it supports no calibration statement (§1.5).
8. **The abstract range is fragile.** `\RelDropFMeanRn{}--\RelDropFMeanMn{}` prints ResNet-50 to MobileNetV3-Small, which happens to be min to max today. EfficientNet-B0's 76.9 ties with the minimum; a new drop macro range built the same way would silently misreport if the order changed.

---

## 3. Macro plumbing

### 3.1 Which file comes from where

| File (camera-ready) | Size | Origin | Hand-maintained? |
|---|---|---|---|
| `results_macros.tex` | 16,201 B, 279 `\newcommand` | Lines 1–336 are **byte-identical** to `paper/generated/results_macros.tex` at commit **`f3b79de`**, written by `scripts/ica26_build_paper_macros.py`. **Lines 337–341 were appended by hand**: a block `% --- significance: CIs Xd` defining `\MacroFXdRnS{0.2414}`, `\MacroFXdEbS{0.2359}`, `\MacroFXdMnS{0.1982}`. The file has no trailing newline. | **Partly.** The header "DO NOT EDIT BY HAND" is no longer true of this copy. |
| `results_macros_additions.tex` | 789 B | Hand-written (Russian comments). Four `\providecommand` with typed values: `\EceRatioRn{1.48}`, `\EceRatioEb{1.55}`, `\EceRatioMn{1.94}`, `\TempSdMax{0.0076}`. It is **not** the branch's `paper/updated/results_macros_additions.tex` (4,002 B, English, also defined `\ResultPending` placeholders). | **Yes, entirely.** |

`ica2026.tex:38–39` loads `results_macros` first, then `results_macros_additions`. Because the additions use `\providecommand`, any macro the generator already defines wins, and the additions become no-ops.

**Every macro used by the sources resolves.**
- `ica2026.tex` uses 65 result macros: 61 from `results_macros.tex` (three of them the hand-appended `\MacroFXd*S`) and 4 from the additions file.
- `supplementary.tex` uses 5, all from `results_macros.tex`.
- None is undefined.

**The branch generator at `9acdebf` already emits every hand-supplied macro.**
- Its output (293 macros) differs from the camera-ready file **only** by adding these blocks, with identical values for everything shared:
  - `% --- cross-domain majority baseline` (`\AccXdMajority`, `\MacroFXdMajority`, `\XdMajorityClass`)
  - `% --- cross-domain, significance seed only` (`\MacroFXd{Rn,Eb,Mn}S`, the same values as the hand-appended block)
  - `% --- calibration transport` (`\EceRatio{Rn,Eb,Mn}`, `\TempSdMax`, the same values as the additions file)
  - **`% --- 21-class in-domain control`**:

    ```latex
    \newcommand{\MacroFPvInSharedRn}{\ensuremath{0.9947 \pm 0.0034}}
    \newcommand{\RelDropFSharedRn}{\ensuremath{77.0 \pm 1.1}}
    \newcommand{\MacroFPvInSharedEb}{\ensuremath{0.9980 \pm 0.0008}}
    \newcommand{\RelDropFSharedEb}{\ensuremath{77.0 \pm 0.6}}
    \newcommand{\MacroFPvInSharedMn}{\ensuremath{0.9966 \pm 0.0009}}
    \newcommand{\RelDropFSharedMn}{\ensuremath{81.2 \pm 1.1}}
    \newcommand{\NPvTestShared}{5\,382}
    ```
- Code: `scripts/ica26_build_paper_macros.py` lines 417–435 on the branch read `metrics/shared_space_control.json` → `summary`. The output path is `OUT = REPO / "paper/generated/results_macros.tex"` (line 44), and there is a `--check` mode.
- The generator reads only committed JSON (the lock, `metrics/*.json`, `significance.json`, `shared_space_control.json`). **It does not need the lost npz dumps.**

### 3.2 Where new 21-class macros must go (to keep "no number typed by hand" true)

1. **Only in the generator:** `scripts/ica26_build_paper_macros.py` on the training branch, in the existing `# ---- 21-class in-domain control` section. **Not** in `results_macros_additions.tex`, and **never** in `ica2026.tex`. The branch test `tests/test_ica26_paper_macros.py` rejects `\newcommand` in the paper source.
2. **The camera-ready `results_macros.tex` should be replaced whole** by the generator's output, not patched:
   - This also removes the hand-appended block (lines 337–341), which the generator emits under its own heading. Keeping both would make LaTeX fail with "command already defined".
   - `results_macros_additions.tex` would then shadow nothing and can be emptied or deleted.
   - The `\input` at `ica2026.tex:39` and `supplementary.tex` would need to follow suit (a `.tex` edit, not done here).
3. Values not present in the JSON `summary` need a small addition to the generator that aggregates them from `per_run`:
   - accuracy, balanced accuracy, weighted-F1 and retained mass;
   - bare means;
   - drop ranges.
   The generator's existing `agg()` (sample SD) and `agg_from()` helpers already implement the convention.

### 3.3 Proposed macro names (not written)

These follow the existing convention: `<Metric><Setting><ModelTag>` with `Rn`/`Eb`/`Mn`; `…Mean…` for bare means; `\ensuremath{m \pm s}` bodies.

| Macro | Content | Status |
|---|---|---|
| `\MacroFPvInShared{Rn,Eb,Mn}` | macro-F1, 21-class control, mean ± SD | **exists in generator** |
| `\RelDropFShared{Rn,Eb,Mn}` | rel. drop 21 → xd, 1 decimal, mean ± SD | **exists in generator** |
| `\NPvTestShared` | 5,382 | **exists in generator** |
| `\AccPvInShared{Rn,Eb,Mn}` | accuracy, 21-class control | proposed |
| `\BalAccPvInShared{Rn,Eb,Mn}` | balanced accuracy, 21-class control | proposed (mirrors `\BalAccPvIn*`) |
| `\AccMeanPvInShared{Rn,Eb,Mn}`, `\MacroFMeanPvInShared{Rn,Eb,Mn}` | bare means | proposed (mirrors `\AccMeanPvIn*`, `\MacroFMeanPvIn*`) |
| `\RetainedMassPvInShared{Rn,Eb,Mn}` | in-domain retained mass, 3 decimals like `\RetainedMass*` | proposed; supports caveat 2.4.1 |
| `\AbsDropFShared{Rn,Eb,Mn}` | abs. drop 21 → xd | proposed (mirrors `\AbsDropF*`) |
| `\RelDropFSharedMean{Rn,Eb,Mn}` | bare mean, 1 decimal | proposed (mirrors `\RelDropFMean*`) |
| `\RelDropFMeanMin`, `\RelDropFMeanMax`, `\RelDropFSharedMeanMin`, `\RelDropFSharedMeanMax` | order-independent ranges for the abstract | proposed; fixes caveat 2.4.8 |
| `\RelDropFSharedDelta{Rn,Eb,Mn}` | paired Δ in pp | optional; only if the text quotes it |
| `\WeightedFPvInShared{Rn,Eb,Mn}` | weighted-F1 | optional; no `WeightedF` family exists in the paper yet |
| `\AccPvInStrict{m}`, `\MacroFPvInStrict{m}` | no-renormalisation variant from committed confusion matrices | optional; needs new generator code; not in the control file |

---

## 4. Source diff

### 4.1 Paper sources that exist

| Source | Location | Lines | Built PDF |
|---|---|---|---|
| **Camera-ready (Overleaf)** | `paper/camera_ready_source/ica2026.tex` (41,043 B) | 719 | none in repo |
| Branch "updated" draft | `paper/updated/ica2026.tex` @ `9acdebf` (41,902 B) | 732 | `paper/updated/PREVIEW_15pages.pdf` (252,632 B, 15 pp) |
| Branch main draft | `paper/ica2026.tex` @ `9acdebf` (37,242 B) | 662 | `paper/ica2026.pdf` (108,970 B, 14 pp) |

None of `ica2026.tex`, `results_macros.tex`, `results_macros_additions.tex`, `supplementary.tex` or `references.bib` from the camera-ready export matches **any** blob in the pack's full history.

### 4.2 Camera-ready vs `paper/updated/ica2026.tex`: the closest ancestor

The body prose is identical except for one sentence.

1. **Removed** (updated lines 493–495, after camera-ready line 483): "For scale, a predictor that always emits the most frequent shared class reaches `\AccXdMajority{}` accuracy and `\MacroFXdMajority{}` macro-F1 on the same images, so the models are informative but not by a wide margin."
   - It is the only substantive text change.
   - It typeset as `[PENDING]` in `PREVIEW_15pages.pdf`, because the branch additions file defined those macros as pending.
2. Comments only:
   - The header (updated 3–16) was rewritten, and its build line changed from `bash scripts/ica26_build_paper.sh` to "Build with pdfLaTeX".
   - The note that the additions file defaults to `\ResultPending` was dropped.
   - Comment lines were removed at updated 44, 55–56 and 89–90.
   - The trailing newline was dropped.

### 4.3 Camera-ready vs `paper/ica2026.tex` (older 14-page draft): substantially different

About 858 changed diff lines. Examples:
- **Abstract:** "trained under one protocol on 54,305 laboratory images" became "on the `\NPvTrain{}`-image PlantVillage training split … across `\NSeedsDone{}` seeds". The "Macro-F1 falls by …" sentence and the "because it does not produce an ordering stable enough to carry" clause were added.
- **Floats:** the old draft inputs `table1_dataset_statistics` in §3 and `table5_domain_shift_degradation_compact` in §6. It has no significance table, no figure, and no §6.1/§6.2.
- **Discussion:** the old draft has §8.3 "Why the Controls Change What Can Be Concluded", which the camera-ready folds into the end of §8.2.
- **Paths:** the old draft uses `../experiments/ica26/tables/…` and `generated/results_macros`.

### 4.4 Associated files (camera-ready vs branch)

| File | Finding |
|---|---|
| `results_macros.tex` | `f3b79de` generator output plus 5 hand-appended lines (§3.1) |
| `results_macros_additions.tex` | hand-written; differs from the branch bridge file (§3.1) |
| `references.bib` | = `paper/updated/references.bib` minus the trailing newline (67 changed lines vs `paper/references.bib`) |
| `supplementary.tex` | differs from `paper/supplementary.tex`: local `tables/` and `figures/` paths, loads `results_macros_additions`, adds `\authorrunning`, adds 4 explanatory paragraphs (provenance counts, contended throughput, UNSTABLE vs partial order, seed of CIs), and adds `\input{tables/table5_domain_shift_degradation_compact.tex}` after the full Table 5. It names **`scripts/ica26_fix_tables.py` (lines 38 and 62–63), which does not exist**; the script is `ica26_fit_tables.py`. |
| `tables/*.tex` (17) | 13 are byte-identical to the committed versions at `f3b79de` (pre-`latexfmt` formatting, e.g. `10709` without a thin space). `table6_calibration_compact`, `table9_significance_across_seeds` and `table9_significance_across_seeds_compact` are identical to `9acdebf` (the transposed 3-row versions). `table3_cross_domain_performance_compact` and `table5_domain_shift_degradation_compact` are `f3b79de` plus one trailing blank line. **`table5_domain_shift_degradation_compact.tex:8` carries the double-escaping bug `Rel. drop (\textbackslash \%)`** (supplement only). |
| `figures/*.pdf` (3) | byte-identical to `9acdebf` (`fig_risk_coverage`, `fig_seed_spread`, `fig_training_curves`) |

### 4.5 Which version is the 15-page submitted PDF

**The camera-ready export.** Its compiled counterpart is **not in the repository**; it is `~/Downloads/ICA2026_leakage_controlled_cross_domain_evaluation.pdf` (411,245 B, 15 pages, anonymised).

I extracted text with macOS PDFKit (read-only) and compared:
- All four main-text table captions (in-domain, significance, cross-domain and calibration compacts) match the camera-ready table files.
- The majority-baseline sentence is absent, and there are no `[PENDING]` markers. EceRatio typesets as "1.48, 1.55, and 1.94 times" from the camera-ready additions.
- Line-level matching of the camera-ready prose against that PDF misses only 12 of the body lines. All 12 are hyphenation or page-break artefacts, or lines carrying macro-expanded numbers.
- `PREVIEW_15pages.pdf` is **not** the submitted version: it contains the majority sentence with two `[PENDING]` markers.
- `paper/ica2026.pdf` (14 pp) is the older draft.

I cannot prove from the repository that the Downloads file is byte-for-byte what was uploaded to CMT; it is the only PDF that matches the authoritative source.

---

## 5. Page budget

### 5.1 Floats in the main text, measured from the 15-page PDF

I measured line coordinates with PDFKit.
- **Body text block:** y ≈ 664 → 127 pt, about 45 lines at about 12 pt leading.
- **Footprint:** the vertical space removed from the text flow, including float separation.

| Printed | Source (`ica2026.tex` line) | File | Page | Content extent | Footprint incl. separation | ≈ body lines |
|---|---|---|---|---|---|---|
| Table 1 (in-domain) | 427 | `tables/table2_in_domain_performance_compact.tex` | 8, mid-page | 128 pt (3-line caption + 7 rows) | **≈176 pt** | ≈15 |
| Table 2 (significance stability) | 451 | `tables/table9_significance_across_seeds_compact.tex` | 9, top | 128 pt (6-line caption + 5 rows) | **≈150 pt** | ≈12.5 |
| Fig. 1 (seed spread) | 453–463 | `figures/fig_seed_spread.pdf` @ 0.85\textwidth | 9, below Table 2 | 181 pt (plot + 5-line caption) | **≈202 pt** | ≈17 |
| Table 3 (cross-domain) | 485 | `tables/table3_cross_domain_performance_compact.tex` | 10, top | 106 pt (4-line caption + 4 rows) | **≈135 pt** | ≈11 |
| Table 4 (calibration ECE) | 536 | `tables/table6_calibration_compact.tex` | 11, top | 117 pt (5-line caption + 5 rows) | **≈147 pt** | ≈12 |
| **Total** | | | | | **≈810 pt** | **≈68 lines ≈ 1.5 pages** |

There are no floats on pages 1–7 or 12–15. On **page 15 the references end at y ≈ 270**, leaving **≈143 pt (~12 body lines) of slack** before the page limit, assuming references count toward the 15 pages.

### 5.2 Compact vs full: what the main text uses

| Table | Main text | Supplementary |
|---|---|---|
| 2 in-domain | **compact** (`ica2026.tex:427`) | full (`supplementary.tex:78`) |
| 3 cross-domain | **compact** (`ica2026.tex:485`) | full (`supplementary.tex:79`) |
| 5 degradation | **not used** in main text (drops are quoted in prose, `ica2026.tex:471–473`) | **both** full (`:80`) and compact (`:81`), a duplicate; the compact copy has the `\textbackslash` bug |
| 6 calibration | **compact** (`ica2026.tex:536`), transposed 3-row form | full (`supplementary.tex:96`) |
| 9 significance | **compact** (`ica2026.tex:451`), transposed 3-row form | full (`supplementary.tex:116`) |

All compact variants that exist are already used. There is no further "switch to compact" saving.

### 5.3 Three best candidates

1. **Move Fig. 1 (seed spread) to the supplementary. Frees ≈202 pt (≈17 lines).**
   - It is already in the supplement (`supplementary.tex:148`, `fig_seed_spread.pdf`).
   - Its content duplicates Tables 1–3 plus the stability table.
   - Cost: the references at `ica2026.tex:448–449` and `562–563` need rewording.
2. **Merge Table 1 (in-domain) and Table 3 (cross-domain) into one paired table. Frees ≈80–110 pt (≈7–9 lines) net**, depending on final layout (estimate).
   - The merged table would have one caption and one header. Per backbone, its rows would hold 38-way in-domain, **21-class in-domain (new)** and 21-way cross-domain, with the PDC in-domain rows kept.
   - This is also the cheapest vehicle for the new control, since no new float is added.
   - The estimate: remove Table 3's ≈135 pt block and add ≈3 rows or 1–2 columns (≈25–55 pt) to Table 1.
3. **Move Table 4 (calibration ECE) to the supplementary. Frees ≈147 pt (≈12 lines).**
   - The §7 prose already carries the claim through `\EceRatio*`, `\TempPv*` and `\TempSdMax`.
   - The full table is in the supplement.
   - A lighter alternative: cut its 5-line caption to 2 lines, which frees ≈33 pt.

Not recommended: moving Table 2 (significance, ≈150 pt). §8.1 (`ica2026.tex:565–576`) reasons directly over its nine verdicts.

---

## 6. Text locations in `paper/camera_ready_source/ica2026.tex`

| Passage | Lines | Content / note |
|---|---|---|
| **Abstract: macro-F1 drop** | **73–74** | "Macro-F1 falls by `\RelDropFMeanRn{}--\RelDropFMeanMn{}\,\%` under the shift." (range fragility: §2.4.8). The context sentence on the label-space construction is at 64–68. |
| **Section 4.2: Cross-Domain Evaluation Procedure (renormalisation)** | **300–311** (heading 300) | Summing and renormalisation: 302–305. Unmapped images excluded: 305–307. "Renormalisation discards probability mass…" and the retained-mass recording: 307–310. |
| **Table 3 caption** | **not in `ica2026.tex`**: `tables/table3_cross_domain_performance_compact.tex:2` (the `\input` is at `ica2026.tex:485`; the in-text reference is at 477–478) | The supplementary full table caption is at `tables/table3_cross_domain_performance.tex:2`. Both are generator output (`ica26_build_tables.py`), so caption changes belong in the generator. |
| **Section 6: Cross-Domain Generalisation** | **466–524** | Heading 466. Drop paragraph ("lose roughly three quarters…", `\RelDropF*`) 470–475. Absolute performance and bootstrap CIs 477–483. `\input` Table 3 at 485. §6.1 487–513. |
| **Section 6.2: How the Models Fail** | **515–524** | Retained-mass sentence and "symptom of the shift rather than of the mapping" at 521–524. The in-domain retained mass of ≈0.95 (§1.4) bears directly on this claim. |
| **Section 8.2: In-Domain Calibration Does Not Transport** | **587–621** | Heading 587. Mechanism and label-smoothing scope 595–605. **"inverts the usual recommendation"** 607–613. "Both findings depend on the controls… conservative bias makes the headline gap *larger*" 615–621. |
| "standard recommendation", literal phrase | **138–140** (Introduction, contribution 4) | The only literal occurrence is in §1: "…the opposite of the standard recommendation." Related "standard" wording is at 77–78 (abstract, "standard practice"), 541 (§7, "standard remedy"), 601 (§8.2, "standard pipeline"), 611 (§8.2, "standard fix") and 642 (Limitation 2). |
| **Limitation 1** (label spaces differ; conservative mapping) | **629–637** | "combines domain shift with a change in task difficulty" 631–633. "lower bound on transfer" 634–637. |
| **Limitation 4** (small field test split; small design) | **652–662** | Bootstrap and per-class caveats 653–656. Seed-spread vs test variability 659–661. |
| **Limitation 5** (cross-domain includes field training images) | **664–669** | Population asymmetry with the in-domain control (caveat 2.4.4). |

---

### Incidental findings (for the revision checklist; no action taken)

- **The camera-ready `results_macros.tex` contains hand-typed macros** (lines 337–341), and `results_macros_additions.tex` is entirely hand-typed. `ica2026.tex:146–147` ("no number in this document was typed by hand") is not literally true of the export until the file is regenerated (§3.2).
- **Integer formatting is mixed.** Tables use `10709` / `1951` (pre-`latexfmt`, `f3b79de`); macros use `10\,709` / `1\,951`. Regenerating the tables with the `9acdebf` generator would change integer formatting and table size prologues. `experiments/ica26/HANDOFF_STATUS.md` warns this can cost pages.
- **`tables/table5_domain_shift_degradation_compact.tex:8`** prints a literal backslash in "Rel. drop (\%)" (supplement only), and is input twice alongside the full Table 5 (`supplementary.tex:80–81`).
- **`supplementary.tex:38, 62–63`** cite a non-existent `scripts/ica26_fix_tables.py`; the script is `ica26_fit_tables.py`.
- **Numbering:** file `table2_…` prints as **Table 1**, `table9_…` as **Table 2**, `table3_…` as **Table 3**, and `table6_…` as **Table 4**. "Table 2 of the paper" in §1 was interpreted as the in-domain table (printed Table 1), matching the task's intent.
