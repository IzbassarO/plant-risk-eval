# ICA 2026 Experiment Protocol

**Paper:** *Leakage-Controlled Cross-Domain Evaluation of Deep Learning Models for
Plant Disease Classification*

**Dataset lock:** `data/manifests/ica26_core_experiment_lock.json`
(schema `ica26.paper_experiment_dataset_lock/1`, digest
`83449f60136918554904cb9c596122f8b89cb51ff5bb5c52c541394a5698082d`)

**Scope note.** The Risk Evaluation Layer — action mappings, harm matrix,
treatment recommendation, action-aware training — is **outside** this paper and
is not required, referenced, or completed by any experiment here. The repository's
formal Core Dataset governance freeze remains **pending**; this protocol runs
against a scientific experiment lock instead, and does not assert otherwise.

---

## 1. Research question

Laboratory-condition plant-disease classifiers report near-perfect accuracy on
PlantVillage, but PlantVillage images are single leaves on uniform backgrounds
whereas field photographs are not. Two questions follow:

**RQ1.** How much in-domain accuracy do standard ImageNet-pretrained backbones
retain when a PlantVillage-trained classifier is evaluated on field-condition
PlantDoc images restricted to a shared, evidence-based label space?

**RQ2.** Does the ranking of backbones by in-domain performance survive the
domain shift, or do efficiency-oriented architectures degrade differently from
larger ones?

**RQ3 (secondary).** Does confidence calibration degrade under domain shift, and
can a single temperature fitted in-domain restore useful confidence ordering
out-of-domain?

A precondition runs underneath all three: the measured gap must not be
contaminated by train/test overlap between the two corpora. This paper's
contribution is as much the *controlled* comparison as the numbers themselves.

## 2. Hypotheses

- **H1.** All three backbones exceed 0.99 accuracy on the PlantVillage in-domain
  test split. PlantVillage is close to saturated and this is a sanity check, not
  a finding.
- **H2.** Cross-domain macro-F1 on the shared-class PlantDoc subset falls
  substantially below in-domain macro-F1, and the drop is large enough that it
  cannot be attributed to the label-space change alone.
- **H3.** In-domain ranking of the three backbones does not fully predict
  cross-domain ranking.
- **H4.** Models are over-confident out-of-domain: expected calibration error is
  higher cross-domain than in-domain, and temperature scaling fitted in-domain
  reduces but does not eliminate it.

Hypotheses are recorded here **before** results exist. Whichever way they
resolve is reported.

## 3. Datasets

| Dataset | Images | Train | Test | Classes |
|---|---:|---:|---:|---:|
| PlantVillage (color) | 54,305 | 43,596 | 10,709 | 38 |
| PlantDoc Core | 2,561 | 2,336 | 225 | 28 |

PlantVillage is pinned to immutable revision
`9e97599868962bd0079b8db4b7f1efa9185fa1e7`; the manifest is reconstructed
exactly from the pinned `splits/color_train.txt`, `splits/color_test.txt`, and
`leaf_grouping/leaf-map.json`, with all 54,305 pixels verified against their
recorded digests.

PlantDoc is pinned to source revision
`5467f6012d78d1c446145d5f582da6096f852ae8`. 2,578 records were acquired;
2,564 survive internal duplicate adjudication; 2,561 form Core.

**PlantDoc Core class support is highly uneven.** Train ranges from 180 images
(`Corn leaf blight`) to 2 (`Tomato two spotted spider mites leaf`) — a 90:1
ratio. The arthropod-pest class has **zero** test images, so PlantDoc Core is 28
train classes and 27 test classes.

## 4. Exclusions

| Stage | Removed | Basis |
|---|---:|---|
| Internal duplicate adjudication | 14 | 12 human-adjudicated byte-exact duplicate groups |
| Conservative exclusion (G07, G08, G10) | 3 | Insufficient independent diagnostic evidence for a relabel whose second scientific review has not been performed |

G07, G08, and G10 were **excluded, not relabelled**. The exclusion records no
diagnosis and confirms nothing about what those images depict. No source image
was deleted and no image byte was modified: the source manifest still carries
all 2,578 acquired records, and every digest in the lock is computed over
unmodified bytes.

The arthropod-pest classes in both datasets (*Tetranychus urticae*) are recorded
out of disease scope in `configs/evaluation_scope.yaml` and are excluded from the
cross-domain label space. The PlantDoc one remains in the PlantDoc in-domain
training label space, because removing it would alter the locked Core dataset.

## 5. Leakage protocol

Candidate generation: `imagehash.phash`, 64-bit, exact chunked brute-force
Hamming evaluation over every distinct-hash pair — 136,847,443 distance
evaluations for the acquired population. The search is exhaustive by
construction, not index-approximate.

Decision threshold: Hamming ≤ 6.

| Population | Evaluation records | Exact | Near | Unresolved |
|---|---:|---:|---:|---:|
| Acquired | 2,578 | 0 | 16 | 0 |
| Core | 2,561 | 0 | 16 | 0 |

All 16 near pairs were adjudicated by a human as `clearly_different` / `keep`.
**Perceptual hashing was used for candidate generation only; it was never the
decision rule.** 15 of the 16 pairs are cross-class collisions on plain green
foliage.

Zero exact overlap in both populations means no PlantVillage training image is a
byte- or pixel-duplicate of any PlantDoc evaluation image. The cross-domain
number is therefore a genuine generalisation measurement.

**Within-PlantVillage leakage.** PlantVillage carries `leaf_id`: several images
can photograph one physical leaf. The official train/test split is leaf-grouped
upstream. The validation set this protocol carves out of train is **also**
leaf-grouped, so no leaf appears on both sides of model selection.

## 6. Shared-class definition

The repository has **no** human-authored PlantVillage class mapping —
PlantVillage action-mapping coverage is 0/38, tracked as open blocker BLOCK-07.
This protocol authors none. The shared-class mapping
(`data/mapping/ica26_cross_domain_class_mapping.csv`) is assembled from exactly
two pieces of existing evidence:

**Source 1 — `deterministic_normalizer_key_collision` (11 pairs).** The
repository's own `ica26.mapping.crosswalk.normalize_crop` / `normalize_disease`
functions, applied *unchanged and identically* to both label spaces, produce
eleven colliding `(crop, disease)` keys. The same function runs on both sides, so
no human judgement enters the pairing.

**Source 2 — `human_approved_healthy_policy` (10 pairs).** `policy:healthy-monitor-v1`
(`reports/HEALTHY_CLASS_ACTION_POLICY.md`) is a recorded human decision that each
PlantDoc `"<Crop> leaf"` class has `canonical_disease = healthy`; those ten rows
carry `review_status = approved` in `data/mapping/action_mapping_review.csv`. On
the PlantVillage side the token `healthy` is literal in the label. Ten crops
appear on both sides.

**Result: 21 shared canonical classes over 1,951 PlantDoc Core images**
(1,773 train / 178 test).

Everything else is **excluded with a recorded reason** — 24 rows. This includes
biologically plausible near-misses that the normaliser does not align, such as
PlantDoc `Corn Gray leaf spot` against PlantVillage
`Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot`, and PlantDoc
`Bell_pepper leaf spot` against PlantVillage `Pepper,_bell___Bacterial_spot`.
Asserting those pairs would be a new semantic judgement, which this repository's
governance deliberately routes through human review. The exclusion reasons make
visible exactly what would change if a PlantVillage mapping were authored.

**Evaluation protocol over the shared space.** Source-model probabilities are
summed within each canonical class and renormalised over the 21 shared classes
only. PlantDoc images outside the mapping are excluded from the evaluation set —
they are **never** counted as ordinary errors. The mean retained probability mass
before renormalisation is recorded in every result file, so the reader can see
how much of the model's belief fell outside the shared space.

## 7. Models

| Model | ImageNet weights | Parameters (task head attached) |
|---|---|---:|
| ResNet-50 | `ResNet50_Weights.IMAGENET1K_V2` | 23.6 M (38-class head) |
| EfficientNet-B0 | `EfficientNet_B0_Weights.IMAGENET1K_V1` | 4.1 M |
| MobileNetV3-Small | `MobileNet_V3_Small_Weights.IMAGENET1K_V1` | 1.6 M |

The final classifier layer is replaced by a fresh linear layer sized to the task.
Backbone choice is the only architectural variable.

## 8. Hyperparameters

One common protocol across all six runs:

| Setting | Value |
|---|---|
| Image size | 224 × 224 |
| Optimizer | AdamW |
| Learning rate | 3 × 10⁻⁴ |
| Weight decay | 1 × 10⁻⁴ |
| Schedule | Cosine decay, stepped per batch |
| Mixed precision | Enabled (fp16 autocast) |
| Max epochs | 15 |
| Early stopping | Patience 3 on validation macro-F1 |
| Batch size | 64 (train), 128 (eval) |
| Label smoothing | 0.1 |
| Validation split | 10% carved from train |
| Model selection | Best validation macro-F1; best checkpoint only |
| Seed | 42 |

**Augmentation** (train only): `RandomResizedCrop(224, scale=(0.7, 1.0))`,
horizontal flip p=0.5, rotation ±15°, colour jitter
(brightness 0.2, contrast 0.2, saturation 0.2, **hue 0.02**).
Hue jitter is deliberately near-zero: chlorosis and necrosis are diagnosed by
colour, and a hue shift would destroy the signal the task depends on. Evaluation
uses resize-256 + center-crop-224 with no augmentation.

**Two documented deviations, both dataset-driven rather than architectural:**

1. **PlantVillage validation is grouped by `leaf_id`** (§5). Random splitting
   would place sibling images of one leaf on both sides.
2. **PlantDoc Core uses inverse-frequency class weighting** (normalised to mean
   1, so the effective learning rate is unchanged). Train imbalance is 90:1. A
   class-balanced sampler would replay the 2-image arthropod-pest class ~90×
   per epoch and overfit it; weighted loss is the gentler instrument. Classes
   with fewer than 3 groups contribute nothing to validation rather than losing
   half their examples to it.

## 9. Metrics

**Classification** (every evaluation): accuracy, macro-F1, weighted-F1, balanced
accuracy, macro precision, macro recall, per-class precision / recall / F1 with
support, confusion matrix.

Macro averages are computed over the classes **present in the evaluation split**,
with the full declared label space reported alongside. PlantDoc Core's
arthropod-pest class has zero test images; averaging it in as a hard 0.0 would
describe the split rather than the model. Zero-support classes, and any
predictions that land on them, are reported explicitly rather than by omission.

**Probabilistic:** negative log-likelihood, Brier score, expected calibration
error (15 equal-width bins), maximum calibration error, reliability diagram.
The scalar ECE and the diagram are computed from the same bin table, so they
cannot disagree.

**Selective prediction:** confidence-abstention curve (accuracy vs coverage) and
area under the risk-coverage curve.

**Efficiency:** total and trainable parameters, wall-clock training time, epochs
run, seconds per epoch, single-image inference latency (batch 1, after warm-up),
batched throughput, peak accelerator memory where the backend exposes it.

**Calibration:** a single temperature fitted by L-BFGS on validation NLL and
applied unchanged to test and cross-domain logits. It is never refitted on
evaluation data. Temperature does not change the argmax, so accuracy and F1 are
identical before and after; only confidence moves.

## 10. Hardware

| Property | Value |
|---|---|
| Machine | Apple M1 Pro, 10 CPU cores, 16 GB unified memory |
| Accelerator | Apple MPS (Metal) — CUDA unavailable on this host |
| Backend priority | CUDA → **MPS** → CPU |
| PyTorch | 2.13.0 |
| torchvision | 0.28.0 |
| Python | 3.13.7 |
| OS | macOS 26.5.1 (arm64) |

Runs execute **sequentially**. With 16 GB shared between CPU and GPU, two
concurrent large-model trainings risk an out-of-memory kill mid-run. Peak memory
is recorded per run. Nothing else was run on the machine during training, so the
recorded times and throughput are not contended.

**Transient read failures on macOS.** Two runs initially died with
`PermissionError [Errno 13]` on images that are present, owned by the user, mode
0644, and readable moments later — the first after roughly 218,000 successful
opens. The cause is environmental: Spotlight (`mds`, `mds_stores`, `mdsync`,
`spotlightknowledged.updater`) was reindexing the dataset tree while six
DataLoader workers read it. No file is damaged; the exact images that failed
re-read cleanly and still match their manifest digests, and file descriptors were
never exhausted (`ulimit -n` is 1,048,576).

`ManifestImageDataset._read` therefore retries a bounded five times with linear
backoff, and **only** for errors that can plausibly be transient. A genuinely
absent file (`FileNotFoundError`) and a corrupt or undecodable one
(`UnidentifiedImageError`) raise on the first attempt with no retry; a transient
error that never clears still raises, reporting the attempt count. Because image
content is pinned by the manifest digests bound in the experiment lock — which is
revalidated at the start of every run — a retry cannot substitute different
pixels for the intended ones.

Anyone reproducing this on macOS should expect the same and may prefer to exclude
the dataset directory from Spotlight indexing.

## 11. Random seeds

Seeds are set for Python `random`, NumPy, and PyTorch at the start of every run.
The validation carve-out is seeded identically and depends only on (frame,
fraction, seed) — not on row order or platform.

**Three seeds: 42, 1337, 2026.** Seed 42 ran the initial matrix; the two
repetitions were launched only after that complete one-seed matrix succeeded,
as this protocol required. 1337 and 2026 were chosen arbitrarily and fixed
before the runs; nothing about either value is special, and the choice is
recorded in `scripts/ica26_make_seed_configs.py` rather than remembered.

The repetition configs are **derived mechanically** from the seed-42 files by
that script, not copied by hand, and `--check` verifies semantically that each
derived config differs from its source in exactly `experiment_id` and `seed`.
A seed repetition only estimates variance if the seed is the only thing that
varied; hand-copying twelve YAML files invites a silent divergence that would
turn a variance estimate into a comparison of two protocols.

Run directories are keyed by `experiment_id`, which carries the seed, so a new
seed cannot overwrite an existing run's checkpoint.

**Preservation.** Checkpoints and prediction dumps are gitignored, so they exist
only in the working tree. `scripts/ica26_preserve_models.py` copies the bytes to
an archive outside the repository and records their SHA-256 digests in
`reports/ica26_model_preservation.json`, which *is* tracked — so the archive can
be proven intact, or proven damaged, from a clean checkout that contains no
weights. Each digest sits next to the `experiment_lock_digest` and `git_commit`
that run's own `result.json` bound at training time, which is what lets a paper
number be traced back to a specific weight file. `--verify` re-hashes both
locations.

## 11a. Statistical methodology

Aggregated tables report **mean ± sample standard deviation** across seeds.
A single seed reports the bare mean: one run has no variance estimate and
printing `± 0.0000` would claim it does. Domain-shift drops are computed
*within* a seed and then averaged, preserving the pairing between a checkpoint
and its own cross-domain evaluation; differencing the two seed-averages would
discard it. Every aggregated table has a `*_per_seed.csv` companion so the
aggregation can be recomputed without rerunning anything.

Two further instruments, in `scripts/ica26_significance.py`:

**McNemar's exact test** on per-item correctness, for every backbone pair in
every evaluation setting. Two models scored on one evaluation set are not
independent samples, so comparing their accuracies as though they were is the
wrong test. The exact binomial form is used rather than the chi-square
approximation because the discordant counts here are small. Because every
pairwise comparison is reported, p-values are also given with **Holm** step-down
adjustment across the whole family.

**BCa bootstrap** 95% intervals for accuracy and macro-F1, 10,000 resamples at a
fixed RNG seed. Both the bias correction and the acceleration are computed; if
either is undefined — as it is for a statistic that does not vary across
resamples — the interval degrades to a percentile interval and is *labelled* as
such rather than silently reported as BCa. The evaluated label space is pinned
to the classes present in the original evaluation, so the statistic keeps one
definition across all replicates.

Both are exact rather than approximate. Accuracy and macro-F1 over a fixed label
set depend on the data only through the (true, predicted) contingency table, so
a bootstrap resample of n items is exactly a multinomial draw over that table's
cells, and the leave-one-out jackknife has at most `n_true × n_pred` distinct
outcomes instead of n. The equivalence is not assumed: a test drives both routes
from one RNG seed and requires exact agreement.

Two gates run before any statistic is computed, and both currently pass for all
nine seed-42 evaluations:

1. The label vectors must be **identical across models**, or the runs were not
   scored on the same items in the same order and no paired test over them is
   valid.
2. Every recomputed accuracy and macro-F1 must match `result.json` to 1e-9, or
   the prediction dump and the result file describe different runs.

**What the two interval types mean is different and they are not
interchangeable.** A bootstrap interval describes sampling variability of a
fixed evaluation set for one trained checkpoint. An across-seed standard
deviation describes variability of the training process. A difference smaller
than the seed spread is not claimed as a finding regardless of its p-value.

## 12. Experiment matrix

Eighteen training runs: six configurations × three seeds. The six per seed are:

| # | Run ID | Train on | In-domain eval | Cross-domain eval |
|---|---|---|---|---|
| 1 | `pv_resnet50_s42` | PlantVillage train | PlantVillage test | PlantDoc Core shared-class |
| 2 | `pv_efficientnet_b0_s42` | PlantVillage train | PlantVillage test | PlantDoc Core shared-class |
| 3 | `pv_mobilenet_v3_small_s42` | PlantVillage train | PlantVillage test | PlantDoc Core shared-class |
| 4 | `pdc_resnet50_s42` | PlantDoc Core train | PlantDoc Core test | — |
| 5 | `pdc_efficientnet_b0_s42` | PlantDoc Core train | PlantDoc Core test | — |
| 6 | `pdc_mobilenet_v3_small_s42` | PlantDoc Core train | PlantDoc Core test | — |

The PlantVillage checkpoints supply both in-domain and cross-domain results, so
no separate cross-domain model is trained.

The `_s42` suffix becomes `_s1337` and `_s2026` for the repetitions, giving 18
run IDs and 18 non-colliding run directories. The repetitions were run in
seed-complete order — all six of 1337, then all six of 2026 — with the cheap
MobileNet runs first within each seed, so an interrupted session leaves whole
seeds finished rather than three partial ones.

## 13. Limitations

1. **Three seeds.** Three repetitions give a usable spread but a weak variance
   estimate. The across-seed standard deviation is reported as a descriptive
   quantity; no significance claim is attached to it, and a between-model
   difference smaller than that spread is not claimed as a finding. Table 7b
   reports each margin against the pooled seed SD so the comparison is visible
   rather than asserted.
2. **The two label spaces differ.** In-domain PlantVillage is 38-way; cross-domain
   is 21-way over a restricted space. The measured drop therefore combines
   domain shift with a change in task difficulty and should be read as a paired
   trend across models, not as an isolated quantity.
3. **The shared mapping is conservative by construction.** 21 of a possible
   ~25–27 semantically shared classes are used. Excluded near-misses are listed
   with reasons; a human-authored PlantVillage mapping would likely enlarge the
   shared space and change the cross-domain numbers.
4. **PlantDoc carries documented label noise.** `PROJECT_BRIEF.md` §7.2 lists
   images whose filename contradicts the assigned class (herbicide damage
   labelled as a virus, gray leaf spot filed under leaf blight, a raspberry leaf
   filed under soybean). This bounds achievable PlantDoc accuracy and is not
   corrected here — correcting it would alter the locked dataset.
5. **PlantDoc Core test is small** (225 images, 27 classes, as few as 3 per
   class). Per-class test metrics have wide confidence intervals.
6. **The arthropod-pest class has 2 training images and no test images.** It
   cannot be learned or measured; it is retained only because removing it would
   alter the locked corpus.
7. **MPS, not CUDA.** Timings and throughput are Apple-Silicon numbers and do not
   transfer to NVIDIA hardware. Relative ordering between backbones should
   transfer; absolute latency will not.
8. **Cross-domain evaluation includes PlantDoc train images.** All 1,951
   shared-class Core images are used, since a PlantVillage-trained model has
   never seen any of them. This is stated explicitly; the split composition is
   recorded in every result file.
9. **Governance status.** The formal Core Dataset governance freeze is pending.
   These results rest on a scientific experiment lock, not on a completed
   governance process.

## 13a. Hypothesis outcomes (recorded after the matrix completed)

The hypotheses in §2 were written before any result existed and are left
unedited above. This section records what actually happened, seed 42, one run
each. Every number is read from `experiments/ica26/metrics/*.json`.

> **Status: seed 42 only; revised once the three-seed matrix completes.** The
> paired tests in §11a have since sharpened one of these outcomes materially —
> see the note appended to H3 below. The rest of this section has not yet been
> re-derived across seeds.

**H1 — supported.** All three backbones exceed 0.99 accuracy on the PlantVillage
test split: EfficientNet-B0 0.9968, MobileNetV3-Small 0.9950, ResNet-50 0.9925.

**H2 — supported.** Cross-domain macro-F1 collapses relative to in-domain:
0.9899 → 0.2414 (ResNet-50), 0.9956 → 0.2359 (EfficientNet-B0), 0.9927 → 0.1982
(MobileNetV3-Small). Relative drops are 75.6%, 76.3%, and 80.0%. The label-space
change alone cannot account for this: a 21-way task with the observed class
supports would give a majority-class baseline far above 0.24.

**H3 — supported, and more sharply than expected.** The in-domain PlantVillage
ranking is EfficientNet-B0 > MobileNetV3-Small > ResNet-50, spread across
0.0043 accuracy. The cross-domain ranking is ResNet-50 > EfficientNet-B0 >
MobileNetV3-Small. ResNet-50 places **last** in domain and **first** out of
domain. Cross-domain ordering instead matches the PlantDoc-trained in-domain
ordering exactly (ResNet-50 0.6933 > EfficientNet-B0 0.6800 >
MobileNetV3-Small 0.5556). A saturated in-domain benchmark carried essentially
no information about which backbone transfers.

**H3, corrected by the paired tests (§11a).** The raw ordering above overstates
what the data supports, and the correction cuts both ways. Cross-domain,
ResNet-50 and EfficientNet-B0 are **not** statistically distinguishable
(McNemar exact p = 0.7488, Holm 1.0000, 351 discordant items). "ResNet-50 first,
EfficientNet-B0 second" is not a finding; it is a coin landing.

What *is* a finding is the ResNet-50 / MobileNetV3-Small crossing, which is
significant **in both directions** after family-wise correction:

| Setting | Margin (ResNet-50 − MobileNetV3-Small) | p exact | p Holm |
|---|---:|---:|---:|
| PlantVillage in-domain | −0.0024 | 0.0095 | 0.0363 |
| PlantVillage → PlantDoc Core | +0.0359 | 0.0002 | 0.0013 |

MobileNetV3-Small is significantly *better* in domain and significantly *worse*
out of domain. That is a genuine crossing rather than a re-ordering within
noise, and it is a stronger claim than the raw ranking flip — so the paper makes
that one and drops the other.

**H4 — first clause supported, second clause falsified.** Miscalibration does
worsen out of domain: ECE rises from 0.090/0.098/0.096 in domain to
0.304/0.239/0.160 cross-domain (ResNet-50 / EfficientNet-B0 /
MobileNetV3-Small, unscaled).

But temperature scaling fitted in domain does **not** reduce the residual
out-of-domain miscalibration — it makes it substantially worse:

| Model | Cross-domain ECE, unscaled | After in-domain T | Fitted T |
|---|---:|---:|---:|
| ResNet-50 | 0.3038 | 0.4305 | 0.7086 |
| EfficientNet-B0 | 0.2390 | 0.3778 | 0.7030 |
| MobileNetV3-Small | 0.1600 | 0.3011 | 0.6988 |

The mechanism is legible. Label smoothing of 0.1 leaves the models
*under*-confident in domain, so the fitted temperature is below 1 (≈0.70) and
**sharpens** the distribution — which is exactly right in domain, cutting ECE
from ≈0.09 to ≈0.009. Out of domain the model is already over-confident relative
to its much lower accuracy, and sharpening amplifies that error.

The practical consequence for deployment is the opposite of the usual advice: a
temperature fitted on in-domain validation data should not be transported across
a domain shift, and doing so is worse than leaving the model uncalibrated. Both
variants are reported in Table 6 so the comparison is visible rather than
implied.

## 14. Exact reproduction commands

```bash
# 0. Environment
python -m pip install -e .
python -m pip install torch torchvision scikit-learn matplotlib

# 1. Verify the corpus matches the paper's locked inputs
python scripts/ica26_build_experiment_lock.py --check
python scripts/ica26_validate_experiment_lock.py --check-pixels

# 2. Verify the shared-class mapping is a deterministic rebuild
python scripts/ica26_build_cross_domain_mapping.py --check

# 3. Pre-flight smoke tests (7 gates)
python scripts/ica26_smoke.py

# 4. Run the full six-experiment matrix, sequentially
bash scripts/ica26_run_all.sh

#    ...or a single experiment
python scripts/ica26_train.py --config experiments/ica26/configs/pv_resnet50_s42.yaml

# 5. Regenerate every table and figure from the result files
python scripts/ica26_build_tables.py

# 6. Full repository verification
python -m pytest -o addopts= -q
bash scripts/run_phase1_checks.sh    # exit 2 = governance BLOCKED, by design
```

Monitoring a running matrix:

```bash
tail -f experiments/ica26/logs/run_all.log                    # per-run start/finish
tail -f experiments/ica26/logs/pv_resnet50_s42.log            # per-epoch detail
cat experiments/ica26/logs/run_all.pid                        # launcher PID
ls experiments/ica26/metrics/                                 # completed results
```
