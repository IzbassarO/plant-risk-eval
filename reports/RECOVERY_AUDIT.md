# Recovery Audit: ICA 2026 camera-ready revision

**Paper:** *From Laboratory to Field: A Leakage-Controlled Cross-Domain Evaluation Protocol for Plant Disease Recognition*
**Audit date:** 2026-09-14
**Scope:** read-only. Nothing was trained, downloaded, installed, modified or deleted. No `git` command was run. This file is the only write.

## 0. Method and repository state

- **Working tree** is `main` at `a946b72` ("fix: do not embed HEAD in the freeze-readiness artifact", 2026-08-03). `.git/logs/HEAD` shows it is a **fresh clone made today** (`clone: from https://github.com/IzbassarO/plant-risk-eval.git`). Every file has an mtime of 2026-09-14 16:21. The tree holds 172 files.
- **Branches.** There are no local branches besides `main`. `.git/packed-refs` lists 5 remote-tracking refs:

| Remote ref | Tip | Tip date (UTC) | Tip message | Files | Relation to main |
|---|---|---|---|---|---|
| `origin/main` | `a946b72` | 2026-08-03 12:40 | fix: do not embed HEAD in the freeze-readiness artifact | 172 | = working tree |
| `origin/codex/r2b1-critical-remediation` | `d4cbb89` | 2026-08-03 15:24 | docs: record R2B1 critical remediation evidence | 180 | main + 4 commits (governance/pHash hardening; no experiments) |
| `origin/claude/r2b2-core-dataset-finalization` | `c7a75b1` | 2026-08-04 09:02 | docs: record the R2B.2 Core Dataset V1 finalization evidence | 198 | adds Core Dataset V1 (G07/G08/G10 exclusions, `plantdoc_core_effective_manifest.csv`, PV reconstruction evidence) |
| `origin/claude/r2b2-core-targeted-audit` | `38bb7b3` | 2026-08-04 12:18 | fix: close two fail-open gates found by the R2B.2 targeted audit | 198 | c7a75b1 + 1 commit. **The experiment lock was built at this commit.** |
| `origin/claude/ica26-training-launch` | `9acdebf` | 2026-08-07 13:10 | Final stage | **451** | **All experiment code, run metadata, metrics, tables, figures, paper sources.** A strict superset of main: nothing on main is missing from it. |

- **How I read the branches without git:** the objects exist only in `.git/objects/pack/pack-ba10f423….pack` (13,019,292 B). I read the pack and index with a small read-only pure-Python reader and extracted the `9acdebf` tree to the session scratchpad, not into the repo. The blob sizes below come from the pack.
- **Outside the repo:**
  - The model archive that `reports/ica26_model_preservation.json` points to, `/Users/izbassar/ICA2026_model_archive`, **does not exist**.
  - The original working directory recorded in every `result.json` (`/Users/izbassar/Documents/Projects/ICA 2026/…`) **does not exist**.
  - No `best.pt`, `*.npz`, PlantVillage or PlantDoc data was found under `~` (searched to depth 4, excluding `~/Library`; `~/.Trash` could not be listed: "Operation not permitted").
  - `~/Downloads/ICA2026_leakage_controlled_cross_domain_evaluation.pdf` (411,245 B, 2026-09-13) exists. It is not in the repo and I did not open it.

> **Headline:** the working tree (`main`) has **no** experiment artifacts of any kind. Everything except checkpoints and per-item prediction dumps is committed on `origin/claude/ica26-training-launch`. Checkpoints and prediction dumps were gitignored and their only off-repo copy, the archive, is gone.

---

## 1. Run artifacts

The 18-run matrix: `pv_{resnet50,efficientnet_b0,mobilenet_v3_small}_s{42,1337,2026}` (9 PlantVillage-trained runs) and `pdc_{…}_s{42,1337,2026}` (9 PlantDoc-Core-trained runs). Cross-domain is not a separate run: each `pv_*` checkpoint is also evaluated on PlantDoc Core (`cross_domain_eval: true`).

### 1.1 What `train.py` writes per run

From `src/ica26/experiments/train.py` on the training branch, per run directory `experiments/ica26/runs/<id>/`:

| File | Content | Written at |
|---|---|---|
| `best.pt` | checkpoint `{model_state, epoch, class_to_idx, config}` | `train.py:337,417` |
| `predictions_in_domain_test.npz` | `logits` (float32, N×38 for pv / N×28 for pdc) and `labels` | `train.py:506` |
| `predictions_validation.npz` | `logits`, `labels` (validation split; used for temperature fitting) | `train.py:510` |
| `predictions_cross_domain.npz` (pv only) | `probs_canonical` (**21-way, already summed and renormalised**) and `labels`. **38-way cross-domain logits are never saved.** | `train.py:611` |
| `result.json` (also copied to `experiments/ica26/metrics/<id>.json`) | full metrics, confusion matrices, per-class, calibration, efficiency, history | `train.py:529–530` |
| `history.json`, `config.resolved.json` | per-epoch history, resolved config | `train.py:531–532` |

### 1.2 Presence table

"Main" means the current working tree. "Branch" means `origin/claude/ica26-training-launch@9acdebf`.

| Artifact | Main (working tree) | Branch `9acdebf` | Gitignore status |
|---|---|---|---|
| **Model checkpoints** `runs/<id>/best.pt` (18) | **ABSENT** | **ABSENT** | main `.gitignore:57` `*.pt`, `:67` `checkpoints/`, `:85` `runs/`. Branch `.gitignore:61` `*.pt`. |
| **Per-item predicted labels** (standalone file) | **ABSENT** | **ABSENT**. No per-item label file was ever produced; labels were derived from the npz logits. | Would be under `runs/`; see next row. |
| **Per-item logits/probabilities**: `predictions_in_domain_test.npz` (38-way pv / 28-way pdc), `predictions_validation.npz`, `predictions_cross_domain.npz` (21-way renormalised) | **ABSENT** | **ABSENT** | main `.gitignore:85` `runs/` (ignores any dir named `runs`). Branch re-includes the dir and then excludes the dumps: `.gitignore:104` `!experiments/ica26/runs/`, `:105` `experiments/ica26/runs/**/*.npz`. |
| **Per-run metric JSON** `experiments/ica26/metrics/<id>.json` and `runs/<id>/result.json` (18 + 18) | **ABSENT** | **PRESENT** (sizes in §1.3) | Not ignored on the branch. On main, `runs/<id>/result.json` would fall under `runs/` (`.gitignore:85`); `metrics/` is not ignored. They are absent from main because the branch was never merged. |
| `runs/<id>/history.json`, `config.resolved.json` (18 + 18) | ABSENT | PRESENT (§1.3) | as above |
| Aggregate metric files | ABSENT | PRESENT: `metrics/significance.json` 14,504 B; `metrics/significance_all_seeds.json` 54,268 B; `metrics/shared_space_control.json` 5,504 B; `metrics/environment.json` 2,308 B; `metrics/macro_snapshot.json` 12,304 B; `metrics/smoke_test_report.json` 2,110 B | not ignored |
| Per-run CSV summaries | ABSENT | Only aggregate `*_per_seed.csv` tables exist (see tables row); there is no standalone per-run CSV. | not ignored |
| **`paper/generated/results_macros.tex`** | **ABSENT** (no `paper/` dir on main) | **PRESENT**: 17,152 B, 292 `\newcommand`s, header says `runs complete: 18/18`, `pending macros: 0` | not ignored. Branch ignores only LaTeX scratch (`paper/*.aux` etc.). |
| `paper/updated/results_macros_additions.tex` | ABSENT | PRESENT 4,002 B (per `HANDOFF_STATUS.md`, now a no-op) | not ignored |
| **`experiments/ica26/tables/`** | **ABSENT** | **PRESENT**: 37 files + `.gitkeep` (§1.4) | not ignored |
| **`experiments/ica26/figures/`** | **ABSENT** | **PRESENT**: 51 files + `.gitkeep` (§1.4) | not ignored |
| Run logs `experiments/ica26/logs/*.log`, `run_matrix.log` | ABSENT | ABSENT | main `.gitignore:87` `logs/`, `:88` `*.log`. Branch `:106` `experiments/ica26/logs/`. |
| `build/table_numbers.json` (value snapshot, default input of `ica26_verify_tables.py`) | ABSENT | ABSENT | main `.gitignore:111` `build/` (branch `:129`) |
| Preservation manifest `reports/ica26_model_preservation.json` | ABSENT | PRESENT 26,457 B. Lists 117 artifacts, 719,937,577 B, archive root `/Users/izbassar/ICA2026_model_archive` (gone). | not ignored |
| Paper sources/PDFs | ABSENT | `paper/ica2026.tex` 37,242; `paper/ica2026.pdf` 108,970; `paper/supplementary.tex` 5,034; `paper/supplementary.pdf` 149,678; `paper/references.bib` 9,793; `paper/updated/ica2026.tex` 41,902; `paper/updated/PREVIEW_15pages.pdf` 252,632 | not ignored |

### 1.3 Per-run committed files on the branch (bytes), with lost-artifact sizes from the preservation manifest

`result.json` is byte-identical in size to `metrics/<id>.json` for every run. "Lost" columns are the sizes recorded in `reports/ica26_model_preservation.json`; those files exist nowhere now.

| Run | `result.json` / `metrics/<id>.json` | `history.json` | `config.resolved.json` | LOST `best.pt` | LOST `pred_in_domain_test.npz` | LOST `pred_validation.npz` | LOST `pred_cross_domain.npz` |
|---|---:|---:|---:|---:|---:|---:|---:|
| pv_resnet50_s42 | 226,929 | 2,389 | 750 | 94,641,453 | 783,137 | 320,480 | 149,953 |
| pv_resnet50_s1337 | 227,741 | 2,543 | 754 | 94,641,453 | 757,021 | 309,363 | 149,582 |
| pv_resnet50_s2026 | 227,572 | 3,776 | 754 | 94,641,453 | 765,719 | 313,154 | 149,502 |
| pv_efficientnet_b0_s42 | 227,330 | 3,039 | 764 | 16,501,477 | 884,163 | 362,942 | 150,063 |
| pv_efficientnet_b0_s1337 | 227,243 | 2,803 | 768 | 16,501,477 | 865,660 | 354,878 | 149,674 |
| pv_efficientnet_b0_s2026 | 227,786 | 3,542 | 768 | 16,501,477 | 866,097 | 354,950 | 149,899 |
| pv_mobilenet_v3_small_s42 | 227,920 | 3,244 | 770 | 6,349,225 | 946,449 | 388,237 | 148,636 |
| pv_mobilenet_v3_small_s1337 | 227,942 | 3,247 | 774 | 6,349,225 | 915,973 | 374,256 | 148,148 |
| pv_mobilenet_v3_small_s2026 | 226,302 | 2,309 | 774 | 6,349,225 | 931,507 | 381,445 | 148,730 |
| pdc_resnet50_s42 | 99,081 | 2,172 | 921 | 94,559,085 | 14,809 | 15,281 | n/a |
| pdc_resnet50_s1337 | 100,173 | 3,276 | 925 | 94,559,085 | 14,734 | 15,297 | n/a |
| pdc_resnet50_s2026 | 98,958 | 2,284 | 925 | 94,559,085 | 14,839 | 15,329 | n/a |
| pdc_efficientnet_b0_s42 | 99,034 | 1,970 | 935 | 16,449,829 | 15,628 | 16,217 | n/a |
| pdc_efficientnet_b0_s1337 | 99,148 | 1,970 | 939 | 16,449,829 | 15,610 | 16,196 | n/a |
| pdc_efficientnet_b0_s2026 | 99,170 | 2,537 | 939 | 16,449,829 | 15,582 | 16,122 | n/a |
| pdc_mobilenet_v3_small_s42 | 100,521 | 2,788 | 941 | 6,307,817 | 15,729 | 16,299 | n/a |
| pdc_mobilenet_v3_small_s1337 | 100,620 | 3,234 | 945 | 6,307,817 | 15,702 | 16,252 | n/a |
| pdc_mobilenet_v3_small_s2026 | 100,533 | 3,288 | 945 | 6,307,817 | 15,748 | 16,222 | n/a |

**What `result.json` does contain** that matters for rescoring:
- per-evaluation `confusion_matrix` and `confusion_matrix_labels`: 38×38 for pv in-domain, 28×28 for pdc in-domain, 21×21 for pv→PlantDoc cross-domain after grouping;
- `per_class` metrics, `probabilistic` (ECE etc.), `selective_prediction` curves, and temperature-scaled variants;
- the cross-domain `protocol` block, including the **mean** retained probability mass (for example 0.72812 for pv_resnet50_s42) but no per-item values.

### 1.4 Tables and figures on the branch (bytes)

**`experiments/ica26/tables/`**
- table1_dataset_statistics.csv 99, .tex 451
- table1b_dataset_provenance.csv 457, .tex 820
- table2_in_domain_performance.csv 912, .tex 1,665, _compact.tex 837, _per_seed.csv 2,769
- table3_cross_domain_performance.csv 648, .tex 1,497, _compact.tex 861, _per_seed.csv 1,639
- table4_efficiency.csv 803, .tex 1,552, _compact.tex 1,023, _per_seed.csv 1,646
- table5_domain_shift_degradation.csv 622, .tex 1,517, _compact.tex 981, _per_seed.csv 1,707
- table6_calibration.csv 2,726, .tex 3,967, _compact.tex 1,070, _per_seed.csv 8,623
- table7_ranking_stability.csv 1,376, .tex 2,045
- table7b_ranking_margins.csv 920, .tex 1,713, _compact.tex 1,401
- table8_confidence_intervals.csv 942, .tex 1,509, _compact.tex 1,224
- table8b_mcnemar.csv 1,021, .tex 1,653, _compact.tex 1,391
- table9_significance_across_seeds.csv 756, .tex 1,375, _compact.tex 1,226

**`experiments/ica26/figures/`**
- `fig_confusion_<run>_in_domain_test.pdf` ×18 (23,943–28,381 B)
- `fig_confusion_pv_<model>_s<seed>_cross_domain_plantdoc_core.pdf` ×9 (23,027–27,496 B)
- `fig_reliability_<run>.pdf` ×18 (15,537–17,836 B)
- fig_risk_coverage.pdf 37,787, .png 85,630
- fig_seed_spread.pdf 23,317, .png 50,681
- fig_training_curves.pdf 37,403, .png 146,714

**Caveat from `experiments/ica26/HANDOFF_STATUS.md` (branch):** "The final `.tex` were assembled and checked by hand outside this repository. Do not regenerate anything expecting it to match what was submitted." `table6_calibration_compact` and `table9_significance_across_seeds_compact` were transposed to 3 rows in the submitted version. The later "Final stage" commit (`9acdebf`) committed the transposing generators, `tests/test_table_generation.py`, `paper/updated/*` and `shared_space_control.json`. The exact submitted `.tex` is not verifiably in the repo; `paper/updated/ica2026.tex` is the closest candidate.

---

## 2. Rescoring feasibility

Relevant facts, verified from branch files:

- **The shared mapping is strictly 1:1.** `data/mapping/ica26_cross_domain_class_mapping.csv` (9,320 B) has 45 rows: 21 `included` (one PlantVillage label ↔ one PlantDoc label ↔ one canonical id), 7 PlantDoc-only excluded and 17 PlantVillage-only excluded. With a 1:1 mapping, "sum within canonical class and renormalise" is just "restrict the softmax to 21 columns and renormalise". The restricted argmax equals the 38-way argmax **whenever** the 38-way argmax lies in a mapped column, and is **undetermined** from argmax information alone when it does not.
- **Cross-domain dumps are lossy.** `predictions_cross_domain.npz` saved only `probs_canonical`, the 21-way distribution after renormalisation (`train.py:611–614`). Per-item 38-way cross-domain outputs were never persisted, even before the archive was lost.
- **Current state:** no npz and no checkpoints exist anywhere (§0, §1.2).

### (a) In-domain PlantVillage, restricted to the 21 shared classes, same summing and renormalisation, without retraining: **PARTIAL**

- **Already computed.** The exact result exists, precomputed on the original machine from the (now lost) `predictions_in_domain_test.npz`, in `experiments/ica26/metrics/shared_space_control.json` (5,504 B, branch). It was produced by `scripts/ica26_shared_space_control.py` (9,045 B) using the identical grouping code path, evaluated on 5,382 of 10,709 test images.
  - It stores, per pv run: `accuracy`, `macro_f1`, `weighted_f1`, `balanced_accuracy`, and mean retained mass.
  - It stores a per-backbone `summary` (in-shared mean/sd, cross-domain mean, relative drop).
  - `HANDOFF_STATUS.md` quotes relative drops of 77.0 / 77.0 / 81.2 % for this 21-way control, against 76.9 / 76.9 / 81.2 % for the headline 38-way → 21-way drop.
- **Cannot be re-run or verified.** `ica26_shared_space_control.py` (and its `--check`) needs `runs/pv_*/predictions_in_domain_test.npz`, which is absent. It exits 1 with "no PlantVillage test dumps available".
- **Not available at all:**
  - probabilistic metrics (ECE/NLL/Brier), which were computed but not written to `per_run`;
  - per-class metrics and confusion matrices for the restricted space;
  - a temperature-scaled variant;
  - any new metric not already in that JSON.
- **What the committed 38×38 confusion matrices still give** (in each `metrics/pv_*.json` → `evaluations.in_domain_test.confusion_matrix`):
  - Restricting rows to the 21 mapped true classes, an item whose 38-way argmax falls in an unmapped column has an unknown restricted prediction. Such items number only 4–12 of 5,382 per run.
  - This yields exact lower/upper bounds on restricted accuracy. For example, pv_resnet50_s42 lies in [0.990152, 0.992196], and the committed exact value 0.991639 falls inside.
  - All 9 runs' committed values fall inside their bounds, which I checked. Restricted macro-F1 cannot be exactly recomputed this way.
- **Minimum to recompute fully:**
  - Best case: the 9 `runs/pv_*/predictions_in_domain_test.npz` files. They are pure numpy and need no GPU or datasets, but they exist only in the lost archive (sha256 values are in the preservation manifest, so a recovered copy can be verified).
  - Otherwise: the 9 `pv_*` `best.pt` checkpoints plus re-inference on the PlantVillage test split (needs PlantVillage pixels).
  - Otherwise: **retrain the 9 PlantVillage runs**. The PlantDoc-trained runs are not needed.

### (b) Strict cross-domain score, where an argmax outside the 21 shared classes counts as an error, without retraining: **NO**

- The strict score needs, for each of the 1,951 evaluable PlantDoc Core images, whether the **38-way** argmax falls in one of the 21 mapped PlantVillage columns.
- No committed artifact holds that:
  - the cross-domain confusion matrix is 21×21, built after restriction and renormalisation;
  - the `protocol` block keeps only the **mean** retained mass (0.52–0.73 across runs), which is not per item.
- The lost `predictions_cross_domain.npz` would not help either: it held only the renormalised 21-way `probs_canonical`, from which out-of-space argmax cannot be recovered.
- (By contrast, a strict **in-domain** score, meaning 38-way argmax outside the 21 counts as an error, *is* exactly computable now from the committed 38×38 matrices. For example, strict accuracy for pv_resnet50_s42 is 5,329/5,382 = 0.990152. That is not what (b) asks.)
- **Minimum re-run:**
  - If the 9 `pv_*` `best.pt` checkpoints were recovered: inference only, no training. Evaluate the 1,951 PlantDoc Core images, saving the full 38-way logits. The current `evaluate_cross_domain` does not save these, so a small change to what gets saved is required. `scripts/ica26_reeval_cross_domain.py` is the existing checkpoint-only harness. It needs PlantDoc Core pixels and a valid lock.
  - Since the checkpoints are gone: **retrain the 9 `pv_*` runs** (3 backbones × 3 seeds). This needs PlantVillage and PlantDoc pixels. The 9 `pdc_*` runs are not needed.

---

## 3. Datasets

### 3.1 Documents

- **`DATASETS.md`** (18,121 B, main = branch) is the **original acquisition spec** for the earlier framing ("From Diagnosis to Decision…", Colab free tier, "Last verified 2026-07-28").
  - Tier 1 lists PlantVillage (HF `mohanty/PlantVillage`, config `color`, 54,306 images, 38 classes, CC BY-SA 3.0; must keep `leaf_id`; no Kaggle mirrors), PlantWild, PlantSeg and PlantDoc (`github.com/pratikkayal/PlantDoc-Dataset`, ~2,598 images, 27 classes, CC BY 4.0).
  - Its verify snippets and `data/manifest.csv` convention are **superseded**. It pins no revisions, and the paper uses only PlantVillage and PlantDoc.
- **`DATA_ACCESS.md`** (2,653 B, main = branch) is the operative local-placement doc:

```
data/raw/
├── plantdoc/                    # PlantDoc, pinned to commit 5467f601
│   ├── train/<class>/*.jpg
│   ├── test/<class>/*.jpg
│   ├── _collisions/             # case-collision-safe renames (macOS)
│   └── _archive/                # cached commit tarball
└── plantvillage/
    ├── extracted/raw/color/…    # PlantVillage color, revision 9e975998
    └── _hf/data.zip             # cached upstream archive
```

The training code resolves pixels at `data/raw/plantvillage/extracted` (manifest relpaths start `raw/color/…`) and `data/raw/plantdoc` (`src/ica26/experiments/data.py:26–27`, branch). **`data/raw/` is absent in the working tree** and is gitignored (`.gitignore:14` `data/raw/`).

### 3.2 Pinned upstream revisions and expected counts

| Dataset | Source | Pinned revision | Upstream component digests | Expected counts (lock `EXPECTED_COUNTS`, `src/ica26/experiments/lock.py`) |
|---|---|---|---|---|
| PlantVillage (color) | `huggingface.co/datasets/mohanty/PlantVillage` | `9e97599868962bd0079b8db4b7f1efa9185fa1e7` | `data.zip` 2,184,723,441 B, sha256 `fba30c6a7965e49be94b47a62f8aff6cfb1c35c27f475f22092b56db41745e84`; `leaf_grouping/leaf-map.json` `3b4b2536…a25b`; `splits/color_test.txt` `7a7257dc…2f8b`; `splits/color_train.txt` `c43e0205…dbd` (branch `data/manifests/plantvillage_source_snapshot.json`) | total **54,305**, train **43,596**, test **10,709**, **38** classes. Leaf map has 40,328 entries. |
| PlantDoc | `github.com/pratikkayal/PlantDoc-Dataset` | commit `5467f6012d78d1c446145d5f582da6096f852ae8` | per-image sha256 in `data/manifests/plantdoc_manifest.csv` | acquired source **2,578** (upstream train 2,342 / test 236); previous effective 2,564; **Core 2,561** (train **2,336** / test **225**), **28** classes. Cross-domain evaluable subset: **1,951** images over **21** shared classes (610 unmapped excluded). |
| Leakage (lock) | pHash, threshold 6 | — | — | acquired and Core: exact 0, near 16, unresolved 0 |

Notes:
- `DATA_ACCESS.md`/`README.md` on main say "2,572 local (2,578 upstream)". Six case-colliding images are lost on case-insensitive APFS. The lock expects 2,578, and the Core manifest contains 12 content-disambiguated `…__<sha12>.<ext>` relpaths, so `scripts/restore_plantdoc_collisions.py` must run after acquisition.
- PlantDoc Core is the effective manifest minus the conservative G07/G08/G10 exclusions (`data/exclusions/core_dataset_v1_conservative_exclusions.csv`, branch only).

### 3.3 The experiment lock

- **File:** `data/manifests/ica26_core_experiment_lock.json` (23,234 B). **Branch only; absent on main.** Human summary: `reports/ICA26_CORE_EXPERIMENT_LOCK.md` (7,125 B, branch).
- **Lock digest validated by code:** `83449f60136918554904cb9c596122f8b89cb51ff5bb5c52c541394a5698082d`. It is recorded as `experiment_lock_digest` in all 18 `result.json`s, in `metrics/environment.json` and in `\LockDigestFull`. Built at commit `38bb7b3` on 2026-08-04T13:03:19Z. Schema `ica26.paper_experiment_dataset_lock/1`; `is_formal_governance_freeze: false`.
- **What `validate()` checks:**
  - sha256 of 24 bound artifacts;
  - class taxonomy and class-index digests;
  - identity and split digests, per-class split counts;
  - expected counts;
  - the cross-domain mapping.
  - With `--check-pixels`, every manifest row must also resolve to a file on disk.
- **I recomputed the 24 artifact digests against both trees:**
  - **Branch `9acdebf`: 24/24 match.**
  - **Main working tree: fails.** 5 absent (`data/exclusions/core_dataset_v1_conservative_exclusions.csv`, `data/mapping/ica26_cross_domain_class_mapping.csv`, `reports/leakage_two_population_report.json`, `data/manifests/plantdoc_core_effective_manifest.csv`, `reports/plantvillage_manifest_reconstruction.json`). 3 digest mismatches (`reports/leakage_plantvillage_vs_plantdoc_summary.json`, `data/manifests/plantvillage_source_snapshot.json`, `data/manifests/plantvillage_summary.json`). The validator script does not exist on main either.

### 3.4 Commands to re-acquire and re-verify (listed, **not run**)

All of these assume the training-branch tree is checked out, since main lacks the lock and the `ica26_*` scripts. Sources: `DATA_ACCESS.md`, `scripts/run_phase1_local.py` docstring, and `reports/ICA26_EXPERIMENT_PROTOCOL.md` §14. No credentials are needed; both sources are public pinned URLs.

```bash
# --- PlantDoc (commit 5467f601; archive -> git clone -> raw-CDN fallback)
caffeinate -dimsu python scripts/run_phase1_local.py --steps plantdoc --resume
python scripts/restore_plantdoc_collisions.py --dry-run
python scripts/restore_plantdoc_collisions.py          # required: Core manifest uses 12 collision-safe paths

# --- PlantVillage color (HF data.zip @ 9e975998, ~2.18 GB)
caffeinate -dimsu python scripts/run_phase1_local.py --steps plantvillage --resume

# --- Byte-level verification of both corpora against committed manifests
python scripts/run_phase1_local.py --steps verify

# --- PlantDoc Core / PV reconstruction evidence are committed; optional re-checks
python scripts/apply_core_conservative_exclusions.py --check
python scripts/build_plantvillage_reconstruction.py --check     # needs the pinned HF sources ("hf" extra)

# --- Experiment lock
python scripts/ica26_build_experiment_lock.py --check           # rebuild lock from disk, compare byte-for-byte
python scripts/ica26_validate_experiment_lock.py --check-pixels # digest 83449f60… + every manifest row on disk
python scripts/ica26_build_cross_domain_mapping.py --check      # mapping is a deterministic rebuild
```

---

## 4. Environment

| Item | What the repo says | Source |
|---|---|---|
| Python | `requires-python = ">=3.10"`. Training host used **Python 3.13.7**. | `pyproject.toml`; `reports/ICA26_EXPERIMENT_PROTOCOL.md` §10 (branch) |
| Dependency manager | **pip + venv + setuptools** (`pip install -e`). No lockfile, no uv/poetry/conda. Scripts default to `PY=$REPO/.venv/bin/python`. | `pyproject.toml`, `README.md`, `scripts/ica26_run_*.sh` |
| Core deps | numpy>=1.24,<3; pandas>=2.0,<4; pillow>=10,<12; imagehash>=4.3,<5; pyyaml>=6,<7; requests>=2.28,<3; extras `hf` = datasets>=2.19, huggingface_hub>=0.23; `dev` = pytest>=8,<9 | `pyproject.toml`, `requirements.txt` (identical on branch) |
| Training deps (**not declared** in pyproject/requirements) | torch, torchvision, scikit-learn, matplotlib, and scipy (imported by `scripts/ica26_significance.py`). The protocol installs them **unpinned**. Recorded versions: **torch 2.13.0, torchvision 0.28.0**. | protocol §14; `result.json` → `hardware` |
| Hardware | **Apple M1 Pro, 10 CPU cores, 16 GB unified memory**, macOS 26.5.1 arm64, backend **MPS** | protocol §10; every `result.json` |
| Paper build | `tectonic`, which `scripts/ica26_fit_tables.py` hard-codes as `/opt/homebrew/bin/tectonic`; `brew install tectonic` | `scripts/ica26_build_paper.sh`, `ica26_fit_tables.py:47` |

**Setup commands as documented** (README.md on main plus protocol §14 on the branch):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[hf,dev]"
python -m pip install torch torchvision scikit-learn matplotlib   # unpinned in the repo; paper used torch 2.13.0 / torchvision 0.28.0
# scipy is also imported by scripts/ica26_significance.py
brew install tectonic                                              # paper build only
```

**MPS specifics** (all on the branch):
- **Device priority** is CUDA → MPS → CPU: `select_device()` in `src/ica26/experiments/models.py`.
- **AMP:** CUDA uses fp16 with `GradScaler`; **MPS uses fp16 autocast with no scaler** (`_autocast`, `train.py:205–210`; scaler only when `device == "cuda"`, `train.py:332`).
- **Non-finite-gradient guard** lives in `src/ica26/experiments/train.py`:
  - `gradient_norm()` at `:264–272` computes the norm via `clip_grad_norm_(…, inf)`.
  - In the step loop at `:364–380`, if `torch.isfinite(gradient_norm(model))` fails, the step is skipped, the gradients are zeroed, and `skipped_steps` is incremented.
  - `assert_finite_state()` at `:275–285` runs at every epoch end (`:390`) and on the restored checkpoint (`:453`).
  - A run skipping more than 1% of steps is refused (`:435–441`).
  - `_assert_reportable()` at `:634–657` checks metric finiteness before `result.json` is written.
  - `skipped_nonfinite_steps` is recorded in the history and the result.
  - Tests: `tests/test_ica26_numerical_guards.py`. Rationale: protocol §10 (pv_efficientnet_b0_s1337 died with NaN weights before the guard existed).
- **Guard outcome:** 1 run skipped steps (pv_efficientnet_b0_s1337: 11 of 6,754). 8 runs predate the counter and have no `optimiser_steps` field: pv_resnet50_s42, pv_efficientnet_b0_s42, pv_mobilenet_v3_small_s42, pdc_resnet50_s42, pdc_efficientnet_b0_s42, pdc_efficientnet_b0_s1337, pdc_mobilenet_v3_small_s1337 and pv_mobilenet_v3_small_s1337. pdc_mobilenet_v3_small_s42 was re-run under the guard and gave a byte-identical checkpoint, so 10 runs are guarded. Macros: `\NRunsWithSkippedSteps{1}`, `\NSkippedSteps{11}`, `\NGuardedRuns{10}`.
- **Other macOS notes:**
  - Spotlight can cause transient `EACCES` errors. `ManifestImageDataset._read` retries 5×, and `ica26_run_matrix.sh` retries each run once.
  - Runs must be sequential (16 GB memory).
  - `caffeinate -dimsu` keeps the machine awake.

**This machine today:** Apple M1 Pro, 16 GB, 10 cores (same class as the training host); system `python3` is 3.14.7; no `.venv` in the repo; `torch` not importable; `tectonic` not on PATH; 777 GiB free.

---

## 5. Entrypoints and cost

All `ica26_*` scripts exist **only on the training branch**.

| Purpose | Entrypoint |
|---|---|
| **(a) Train one run** | `python scripts/ica26_train.py --config experiments/ica26/configs/<id>.yaml [--device auto\|cuda\|mps\|cpu] [--check-pixels]` validates the lock first (exit 2 on failure). Core: `src/ica26/experiments/train.py::train_one_run`. |
| Train a batch | `bash scripts/ica26_run_matrix.sh [ids…]` (retry once; default = the six seed-42 runs) · `bash scripts/ica26_run_all.sh` (six seed-42 runs) · configs for the other seeds: `python scripts/ica26_make_seed_configs.py [--check]` · pre-flight: `python scripts/ica26_smoke.py` |
| **(b) Cross-domain evaluation** | Runs inside training for `pv_*` configs (`cross_domain_eval: true` → `train.py::evaluate_cross_domain`). Checkpoint-only re-evaluation: `python scripts/ica26_reeval_cross_domain.py [run_ids…]`, which needs `best.pt` and defaults to the three s42 pv runs. 21-way in-domain control: `python scripts/ica26_shared_space_control.py [--check]`, which needs the in-domain npz files. |
| **(c) Leakage audit** | Full pipeline: `python scripts/run_phase1_local.py --steps index,leakage,gate` (also on main). Two-population recomputation (acquired 2,578 and Core 2,561): `python scripts/verify_core_and_acquired_leakage.py --out <dir> [--reuse-index <dir>] [--persist]`. Low-level CLIs: `ica26-leakage` (`src/ica26/leakage/phash.py`, `--manifest-a/--root-a/--manifest-b/--root-b/--threshold/--out-pairs/--out-summary`) and `ica26-leakage-gate` (`src/ica26/leakage/gate.py`, requires `--training-manifest --training-root --training-dataset --evaluation-manifest --evaluation-root --evaluation-dataset --pair-table --near-review --reviewed-exclusions --exact-exclusions`). Governance gate: `bash scripts/run_phase1_checks.sh` (exit 2 = BLOCKED by design). |
| **(d) Regenerate every table, figure and macro** | `bash scripts/ica26_build_paper.sh` runs, in order: `ica26_build_tables.py` → `ica26_fit_tables.py` (needs tectonic) → `ica26_build_paper_macros.py` → anonymity gate → `ica26_preflight.py` → tectonic compile. Also: `python scripts/ica26_significance.py [--seed N] [--check]` writes `significance*.json` and **needs the npz dumps**; `python scripts/ica26_macro_drift.py [--snapshot]`; `python scripts/ica26_verify_tables.py` (default snapshot `build/table_numbers.json`, which is absent). `ica26_build_tables.py` and `ica26_build_paper_macros.py` read only committed JSON (`metrics/*.json`, `significance.json`, the lock), so they can in principle run from the branch as-is. |

### 5.1 Recorded wall-clock timings

- **Source:** `efficiency.training_time_seconds` in each committed `result.json` / `metrics/<id>.json`. It equals the sum of per-epoch `epoch_seconds` in the history to within about 1 s.
- **What it covers:** the training loop only, including per-epoch validation. It **excludes** data preparation, final test, validation and cross-domain inference, temperature fitting and latency benchmarking.
- **End-to-end** per-run durations were logged to `experiments/ica26/logs/run_matrix.log` (`finished <id> in Ns`), but those logs are gitignored and absent. **No end-to-end timing is recorded in the repo.**
- `reports/` on main contains no training timings (Phase-1 only).
- Hardware for all runs: M1 Pro / MPS / torch 2.13.0, run sequentially.

| Backbone | Dataset | s42 (s) | s1337 (s) | s2026 (s) | Mean (min) | Epochs run (42/1337/2026) | s/epoch (mean) |
|---|---|---:|---:|---:|---:|---|---:|
| ResNet-50 | PlantVillage | 7,246.9 | 7,598.7 | 11,060.7 | **143.9** | 11 / 10 / 15 | 718.7 |
| EfficientNet-B0 | PlantVillage | 7,926.7 | 6,594.3 | 8,477.3 | **127.8** | 14 / 11 / 14 | 590.4 |
| MobileNetV3-Small | PlantVillage | 2,010.6 | 2,119.4 | 1,334.9 | **30.4** | 15 / 15 / 9 | 141.2 |
| ResNet-50 | PlantDoc Core | 727.1 | 778.7 | 532.4 | **11.3** | 10 / 13 / 9 | 63.9 |
| EfficientNet-B0 | PlantDoc Core | 505.8 | 709.9 | 684.0 | **10.6** | 9 / 9 / 10 | 67.8 |
| MobileNetV3-Small | PlantDoc Core | 140.0 | 184.4 | 165.5 | **2.7** | 11 / 15 / 13 | 12.6 |

Means match committed `experiments/ica26/tables/table4_efficiency.csv`.

**Training-loop totals:**
- 9 PlantVillage runs: 54,370 s ≈ **15.1 h**
- 9 PlantDoc runs: 4,427 s ≈ **1.2 h**
- full 18-run matrix: ≈ **16.3 h**

Evaluation overhead is additional and unrecorded. Epochs vary with early stopping (patience 3, max 15). Peak memory is about 9.2–9.5 GB for pv ResNet/EfficientNet and about 11.4–12.5 GB for pdc ResNet/EfficientNet.

---

## 6. Label smoothing

**Where 0.1 is configured** (training branch):
- **Default:** `src/ica26/experiments/train.py:52`, `label_smoothing: float = 0.1` (field of `ExperimentConfig`).
- **Consumed:** `train.py:323–326`, `nn.CrossEntropyLoss(label_smoothing=cfg.label_smoothing, weight=…)`.
- **Explicit in every YAML:** `label_smoothing: 0.1` in all 24 files under `experiments/ica26/configs/` (18 matrix + 6 smoke), for example `pv_resnet50_s42.yaml:15` and `pv_resnet50_s1337.yaml:18`.
- **Recorded** in all 18 `runs/<id>/config.resolved.json` (line 13) and in `result.json` → `config`.
- Nowhere else: no hard-coded 0.1 in scripts or tests.

**Difficulty of a no-label-smoothing variant:**
- **Training: config flag only, no code change.** `ExperimentConfig.from_yaml` accepts `label_smoothing`, so a new YAML with `label_smoothing: 0.0` and a new `experiment_id` trains correctly under the same lock and guard. Run directories are keyed by `experiment_id`, so nothing is overwritten.
- **Reporting: code change needed to tabulate it.**
  - `ica26_build_tables.py` (`RUN_IDS` built from `MODEL_ORDER × SEEDS`, `:85–102`), `ica26_build_paper_macros.py` (`runs.get(f"{prefix}_{model}_s{seed}")`) and `ica26_significance.py` all hard-code the `<prefix>_<model>_s<seed>` id pattern. An ablation run would be silently ignored by them.
  - `ica26_make_seed_configs.py --check` enforces that derived configs differ from seed-42 sources only in `experiment_id` and `seed`, so ablation YAMLs must be authored outside that derivation.
  - Temperature fitting and the cross-domain temperature-scaled block are produced automatically per run, which is what the calibration caveat concerns.

**Runs required for a PlantVillage-only ablation:**
- **9 runs** for parity with the paper's matrix (3 backbones × 3 seeds, `pv_*` only; each gives in-domain, cross-domain and temperature-scaled results). At the recorded rates that is about **15.1 h** of training loop on this M1 Pro class, plus evaluation.
- **1 run** at minimum (one backbone, one seed), as scoped in `experiments/ica26/HANDOFF_STATUS.md` under "Still open": about 22–35 min for MobileNetV3-Small, 1.8–2.4 h for EfficientNet-B0, or 2.0–3.1 h for ResNet-50.
- No PlantDoc-trained runs are needed for a PlantVillage-only ablation.

---

## BLOCKERS

Anything that prevents reproducing the published numbers today:

1. **No experiment artifacts in the working tree.** `main` (a fresh clone) has no experiment code, configs, lock, mapping, metrics, tables, figures, macros or paper. All of it is only on `origin/claude/ica26-training-launch@9acdebf`, which has not been checked out or merged.
2. **All 18 checkpoints and all prediction dumps are lost.**
   - Gitignored: `*.pt`, `runs/`, `experiments/ica26/runs/**/*.npz`.
   - The sole backup, `/Users/izbassar/ICA2026_model_archive` (117 files, 719,937,577 B), does not exist.
   - The original working tree `/Users/izbassar/Documents/Projects/ICA 2026` does not exist.
   - `~/.Trash` could not be inspected (permission denied).
   - Only sha256 values survive, in `reports/ica26_model_preservation.json`, which is enough to verify a recovered copy.
3. **Significance results cannot be recomputed.** `scripts/ica26_significance.py` (McNemar, BCa; feeds Tables 8, 8b, 9 and the significance macros) reads the npz dumps. Those tables and macros can only be re-emitted from the committed `significance*.json`, not re-derived.
4. **The strict cross-domain score is impossible without new model outputs** (§2b). It needs checkpoint re-inference, and with checkpoints lost, retraining the 9 `pv_*` runs.
5. **The 21-class in-domain control cannot be re-verified or extended** (§2a). Its committed JSON is the only record.
6. **No datasets on disk.**
   - `data/raw/` is absent: PlantVillage color (54,305 images from a 2.18 GB `data.zip` at HF revision `9e975998…`) and PlantDoc (2,578 images at commit `5467f601…`) must be re-acquired.
   - Continued upstream availability of those exact pinned revisions was **not verified**, since no network access was used.
   - `restore_plantdoc_collisions.py` must also succeed for the lock to validate.
7. **The lock does not validate on main.** It needs the branch tree: on main, 5 bound artifacts are absent and 3 have mismatching digests. Every training and re-evaluation entrypoint aborts on an invalid lock.
8. **The environment is not reproducible from declared dependencies.**
   - torch, torchvision, scikit-learn, matplotlib and scipy are undeclared and installed unpinned.
   - The recorded versions (torch 2.13.0, torchvision 0.28.0, Python 3.13.7) are not enforced.
   - This machine has no venv and no torch; system Python is 3.14.7, and whether a matching torch 2.13.0 wheel exists for it was not checked.
   - `tectonic` (hard-coded to `/opt/homebrew/bin/tectonic` in `ica26_fit_tables.py`) is not installed.
9. **Retraining would not bit-reproduce the published numbers.**
   - No deterministic-algorithms mode is set, and MPS fp16 training is not guaranteed deterministic across torch or macOS versions.
   - The committed `result.json`s record 13 distinct training-time `git_commit`s.
   - One published run (pv_efficientnet_b0_s1337) skipped 11 steps under the guard.
   - Retrained models would give *new* numbers, not the published ones. The only same-code evidence of determinism is one re-run (pdc_mobilenet_v3_small_s42) that reproduced a byte-identical checkpoint on the original machine.
10. **The submitted paper source is not verifiably in the repo.** `HANDOFF_STATUS.md` states the final `.tex` was "assembled and checked by hand outside this repository" and warns that regenerated tables need not match the submission. Two compact tables were hand-transposed. `build/table_numbers.json` (the "no digit moved" snapshot) is gitignored and absent. `paper/updated/ica2026.tex` is the closest in-repo candidate; the PDF in `~/Downloads` was not inspected.
11. **Documentation on main is stale and contradictory.** `README.md` says "Model training / Phase 2 experiments: not started" and uses the superseded "From Diagnosis to Decision" title. `DATASETS.md` is the old Colab-era spec. The operative protocol and reproduction commands exist only in `reports/ICA26_EXPERIMENT_PROTOCOL.md` on the training branch.
