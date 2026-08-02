# Project Brief — *From Diagnosis to Decision*

> **Purpose of this document.** A complete handover brief. Any model or collaborator reading this file alone should understand what the paper argues, what data backs it, what has actually been built, what is still broken, and what must not be done. Written 2026-07-28.

---

## 1. Identity

| | |
|---|---|
| **Paper title** (final, do not change) | *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition* |
| **Keywords** | plant disease recognition; decision support; action-level evaluation; severity estimation; selective prediction; sustainable crop protection |
| **Venue** | ICA 2026 — 4th International Conference on Agriculture-Centric Computation |
| **Proceedings** | Springer CCIS (Scopus-indexed at series level) |
| **Format** | Springer LNCS/CCIS template, 12–15 pages, **double-blind** (anonymized PDF) |
| **Author** | Solo author, MSc student. Affiliation transitions from Atyrau University (Kazakhstan) to Syracuse University (USA) mid-August 2026 |
| **Budget** | Zero. Free datasets, Google Colab free tier (T4 GPU, ephemeral disk) only |
| **Timeline** | ~2.5 weeks of work, contingent on deadline resolution (see §11) |

### Venue detail

- **Dates / place:** 1–4 November 2026, ANNAM.AI, IIT Ropar, Rupnagar, Punjab 140001, India
- **Theme:** *"AI Meets Farm — Digital Agriculture for a Sustainable Future"*
- **Organizers:** ANNAM.AI (Centre of Excellence in AI for Digital Agriculture) + IIT Ropar, supported by the Ministry of Education, Government of India
- **Submission system:** Microsoft CMT3 — `cmt3.research.microsoft.com/ICA2026`
- **Contact:** `ica@iitrpr.ac.in`
- **Fees:** India/SAARC INR 9,440 (academic) / 15,000 (industry); international USD 100 (academic) / 150 (industry). No student rate published
- **Attendance:** in-person required; virtual presentation only in exceptional circumstances with prior organizer approval

**Deadlines (from the CFP page):**

| Stage | Date |
|---|---|
| Abstract submission | 8 August 2026 |
| Full paper submission | 15 August 2026 ("Firm Deadline") |
| Acceptance notification | 8 September 2026 |
| Camera-ready | 22 September 2026 |
| Conference | 1–4 November 2026 |

⚠️ **Unresolved conflict:** the Registration page banner states "Paper Submission Deadline: 31 July 2026". The CFP page states 8/15 August in three places. This has not been confirmed with the organizers. **This is the single highest-priority open question.**

### Past editions — acceptance selectivity

| Edition | Host | Proceedings | Accepted / submitted |
|---|---|---|---|
| ICA 2023 | IIT Ropar | CCIS vol. 1866 | 18 / 52 (~35%) |
| ICA 2024 | IIIT Delhi | CCIS vol. 2207, DOI `10.1007/978-3-031-74440-2` | 26 / 79 (~33%) |
| ICA 2025 | IIT Guwahati | DOI `10.1007/978-3-032-17083-5`, ISBN 978-3-032-17082-8 | 28 / 115 (~24%) |

### Strategic fact — the organizers work on this exact problem

ICA 2025 proceedings contain **"LeADS (Leaf Anomaly Detection System): Deep Learning Pipeline for Leaf Stress, Disease & Severity Estimation"** by Mayur Pratim Das, **Neeraj Goel** and **Mukesh Saini**. Goel and Saini are editors of the ICA 2023, 2024 and 2025 proceedings and are based at IIT Ropar, which hosts ICA 2026.

**Implication:** LeADS is a mandatory citation and the natural positioning anchor. LeADS carries the pipeline as far as *severity estimation*. This paper asks what to do with severity — the next link in the chain. Frame it as continuation, never as critique.

### Venue title conventions (observed from ICA 2025 ToC)

Titles run 11–16 words, almost always contain a colon, always name the crop/agriculture domain and the method, and are **constructive rather than provocative**. Patterns: `Acronym: Descriptive expansion` (AgriFed, LeADS), `Enhancing X: ...`, `Method-Based Framework for Task`. Avoid ML-conference contrarian styling ("Beyond Accuracy:", "X Is Not Enough") — it reads as foreign at this venue.

---

## 2. The research problem

### One-paragraph statement

Plant disease recognition models are evaluated almost universally by classification accuracy on the disease label. But a farmer does not consume a label — they consume an **action**: spray a fungicide, apply copper and sanitize, remove the plant and control the vector, or do nothing. Classification errors are **not interchangeable with respect to that action**. Confusing two fungal diseases usually leads to the same treatment and is nearly harmless. Confusing a viral disease for a fungal one is catastrophic: the farmer sprays a plant that should have been uprooted, loses the crop anyway, spends money on chemicals, and lets the vector spread. Accuracy cannot see this distinction. This paper introduces an evaluation framework that can.

### Why this matters now (the hook)

Current models are **good**, not bad. On PlantWild — the largest open in-the-wild benchmark — the published MVPDR baseline reaches **76.18%** top-1, a single DINOv2 ViT-L/14 backbone reaches **77.56%**, and a three-backbone frozen fusion reaches **80.23 ± 0.41%**.

At 52% accuracy nobody would deploy a system to farmers. At 80% they will. **That is exactly when it becomes urgent to ask whether 80% accuracy means 80% correct treatment decisions.** Do not frame the paper around "models are weak" — frame it around "models are now good enough to deploy, and accuracy is the wrong gate for deployment."

### Contributions (what to claim)

1. **An action-level evaluation protocol** for plant disease recognition — the first metric set that scores models by the correctness of the resulting agronomic intervention rather than the disease label.
2. **A published disease → action mapping** grounded in authoritative pest-management sources, released as a reusable artifact.
3. **A harm-weighted error metric** that penalizes misclassifications by their agronomic consequence rather than uniformly.
4. **A risk-calibrated abstention analysis** connecting a deferral threshold to agronomic cost, with risk–coverage curves.

### Expected headline result

Model rankings by accuracy and by harm differ. The most accurate model is not the safest. This is the type of finding that carries a paper at a 24–35% acceptance venue — it requires rigor, not state-of-the-art numbers.

### Track fit

Primary **Track 1 (Activity-level)** — matches the CFP line "Computer vision and deep learning pipelines for plant stress detection and phenotyping" verbatim. Secondary **Track 2 (Process-level)** via the decision/advisory layer.

---

## 3. Method

### 3.1 Action classes — **four**, not five

| Action class | Trigger | Agronomic content |
|---|---|---|
| `fungicide` | Fungal / oomycete pathogens | Targeted fungicide application |
| `copper_sanitation` | Bacterial pathogens | Copper-based products + sanitation, pruning |
| `remove_vector` | Viral pathogens | Remove plant, control insect vector — **no chemical cure exists** |
| `monitor` | Healthy / trace severity | No intervention |

> **A fifth class `abiotic_correction` (nutrient/water correction) was designed and then dropped.** No dataset in the stack contains labelled abiotic disorders. The only abiotic examples found are **mislabelled inside PlantDoc's healthy classes** (see §7). Declaring abiotic out of scope is more honest than carrying a class with no data. Say so explicitly in the paper.

### 3.2 Metrics

- **Accuracy** — standard top-1 on disease labels. Reported as the reference point being critiqued.
- **Action Accuracy** — top-1 after projecting predictions and ground truth through the disease → action mapping.
- **Harm-Weighted Error** — `Σ W[true_action, predicted_action] × count / N`, where `W` is an asymmetric penalty matrix. Viral→fungicide carries the maximum weight; fungal→fungal carries near-zero.
- **Majority-action baseline** — accuracy of always predicting the most frequent action class. **Mandatory floor** (see §8.2).
- **Risk–coverage curve** — selective accuracy and harm as a function of the fraction of cases the system answers rather than deferring to a human.
- *(Optional)* **Over-treatment / under-treatment rate** — fraction of cases where the predicted severity tier prescribes more or less intervention than the true tier.

### 3.3 Pipeline

```
Image
  │
[1] DIAGNOSIS ──── low confidence / OOD ──→ ABSTAIN → refer to agronomist
  │ confident
[2] SEVERITY (lesion area ÷ leaf area from segmentation mask)   [OPTIONAL — see §8.1]
  │
[3] ACTION CLASS (one of the four above, via the mapping)
  │
[4] CONTEXT MODIFIERS (growth stage, weather window, PHI, regional legality)
      — scoped as future work, not implemented
```

### 3.4 Models

Standard backbones from `timm`, trained on PlantVillage with leaf-grouped splits, evaluated in-domain and cross-dataset: ResNet-50, EfficientNet-B0, MobileNetV3, ViT-S. No architectural novelty is claimed or needed — the contribution is the evaluation layer.

---

## 4. Dataset inventory

### 4.1 Tier 1 — required

**PlantVillage** — training source, laboratory conditions
- 54,306 images / 38 classes / 14 species / 26 diseases. **12 of 38 classes are healthy.**
- HF `mohanty/PlantVillage`, configs `color`, `grayscale`, `segmented`. Upstream: `github.com/spMohanty/PlantVillage-Dataset`
- License CC BY-SA 3.0 (per HF card). Paper: Mohanty, Hughes & Salathé (2016), *Frontiers in Plant Science*, DOI `10.3389/fpls.2016.01419`
- **Leakage trap:** multiple photographs exist of the same physical leaf. Random splits inflate accuracy. Use the `leaf_id` field and leaf-grouped splits. **Kaggle mirrors lack `leaf_id` — do not use them.**
- **Leaf grouping is partial:** the original paper maps leaves for only **41,112 of 54,306** images. The HF `color` split sums to **54,305** (off-by-one vs the paper). Disclose both.
- Key motivating statistic: when evaluated on images captured in conditions different from training, accuracy drops to **31.4%**.

**PlantWild** — primary in-the-wild evaluation
- 18,542 images / 89 classes (56 diseased + 33 healthy); v2 extends to 115 classes. Per-class textual symptom descriptions included.
- HF `uqtwei2/PlantWild`. Baseline code `github.com/tqwei05/MVPDR`. Project page `tqwei05.github.io/PlantWild`
- License **CC BY-NC-ND 4.0** — metrics only, never redistribute repackaged images.
- Paper: Wei et al. (2024), ACM MM, arXiv `2408.03120`
- Provenance: collected via Google / Ecosia / Baidu image search. Disclose this.

**PlantSeg** — severity ground truth (pixel masks)
- 11,458 images with disease segmentation masks + 8,000 healthy images / 115 disease classes / in-the-wild
- **Use Zenodo v7: record `17719108`, DOI `10.5281/zenodo.17719108`** (1.1 GB, cited by the published paper). Superseded versions: v1 `13293891` (access-restricted), v2 `13762907` (3.0 GB), v4 `13958858` (1.7 GB, 7:1:2 split)
- **License is version-dependent:** v7 = **CC BY-NC 4.0**; v1–v4 and the arXiv preprint = CC BY-NC-ND 4.0. Cite the license of the version actually downloaded.
- Also on Kaggle `weitianqi/plantseg`, code at `github.com/tqwei05/PlantSeg`
- Paper: Wei et al., *Scientific Data* (2025), DOI `10.1038/s41597-025-06513-4`; arXiv `2409.04038`
- **Do not use the Roboflow copy** — truncated by platform size limits.

**PlantDoc** — second field evaluation, cleanest license
- 2,598 images / 13 species. **28 classes in `train` (18 disease + 10 healthy), 27 in `test`** — test drops *Tomato two-spotted spider mite*. Not "27 = 17 + 10".
- `github.com/pratikkayal/PlantDoc-Dataset` (classification), `PlantDoc-Object-Detection-Dataset` (bounding boxes)
- License **CC BY 4.0** — the only redistributable in-the-wild set, so use it for released qualitative figures.
- Paper: Singh et al. (2020), CoDS-COMAD, DOI `10.1145/3371158.3371196`; arXiv `1911.10317`
- Annotated without a plant pathologist. **Severe quality problems documented in §7.**

### 4.2 Tier 2 — recommended

**FieldPlant** — highest annotation quality
- 5,170 images / 8,629 individually annotated leaves / 27 classes. Corn, cassava, tomato on Cameroonian plantations. Annotated under plant-pathologist supervision.
- Roboflow Universe `plant-disease-detection/fieldplant` (v11; requires API key). Hosted build drifts from the paper: ~5,156 images, up to 31 classes.
- Paper: Moupojou et al. (2023), *IEEE Access* 11:35398–35410, DOI `10.1109/ACCESS.2023.3263042`

**Cassava Leaf Disease Classification** — viral classes for the harm matrix
- 21,367 training images / 5 classes (CBB, CBSD, CGM, CMD, Healthy). Uganda, NaCRRI + Makerere AI Lab.
- **61.9% of training images are CMD.** Requires class-balanced sampling or loss reweighting; report the imbalance ratio.
- Kaggle competition `cassava-leaf-disease-classification` (accept rules first). Not the older 2019 `cassava-disease`.
- **Strategically critical:** the harm matrix rests on the viral↔fungal distinction, and this is the only dataset with viral classes at volume.

**Master Plant Disease Dataset** — label vocabulary only
- 66,701 unique images after removing 3,504 perceptual-hash duplicates; 281 canonical classes (332 before dropping classes with <10 images); merges 7 public sources.
- Kaggle `harisri2005/plant-disease-processed`
- **License unstated. Never train on it** — it almost certainly contains PlantVillage and the evaluation sets, which would contaminate every cross-dataset number. Use its canonicalization as a crosswalk vocabulary only.

### 4.3 Tier 3 — severity validation

| Dataset | Content | Access |
|---|---|---|
| **RoCoLe** ⭐ | 1,560 robusta coffee leaves; rust severity L1–L4 by % affected area **and leaf segmentation masks** | Mendeley DOI `10.17632/c5yvn32dzg.2`; Parraga-Alava et al. (2019), *Data in Brief* 25:104414 |
| **BRACOL** | 1,747 whole arabica leaves; 5 severity levels; miner, rust, brown leaf spot (= Phoma), cercospora | Mendeley DOI `10.17632/yy2k5y8mxg.1`; Esgario et al. (2020), *Comput. Electron. Agric.* 169:105162 |
| **JMuBEN / JMuBEN2** | `t2r6rszp5c` = JMuBEN (Cercospora 7,682 + Rust 8,337 + Phoma 6,572 = 22,591); `tgv3zb82nd` = JMuBEN2 (Miner 16,979 + Healthy 18,985 = 35,964). Total 58,555 | Mendeley; Jepkoech et al. (2021), *Data in Brief* 36:107142 |
| **DiaMOS Plant** | 3,505 pear images (499 fruit + 3,006 leaves); severity bands 0% → >50%; full season, Italy | DOI `10.3390/agronomy11112107` |
| **CD&S** | Corn field: NLB 511, GLS 524, NLS 562 + severity | arXiv `2110.12084` |
| **Apple black rot 4-stage** | PlantVillage apple black rot re-annotated by botanists into 4 severity stages | DOI `10.1155/2017/2917536` |

RoCoLe is the single most valuable Tier 3 set because it has **both** human severity labels and masks — it validates the mask→severity derivation end to end. (But see the caveat in §8.1.)

### 4.4 Tier 4 — metadata and knowledge benchmarks

**LeafNet / LeafBench** — highest-value metadata resource
- 186,000 images / 22 crops / 62 diseases across 97 classes, with **per-class pathogen type**: 43 fungal, 8 bacterial, 2 mould/oomycete, 6 viral, 3 mite. LeafBench = 13,950 expert QA pairs across 6 task types.
- HF collection `enalis/leafsight` (dataset `enalis/LeafNet`); GitHub `EnalisUs/LeafBench`; arXiv `2602.13662` (Feb 2026)
- **This is the semi-automatic route to action labels** — join its pathogen field onto PlantVillage/PlantWild class names instead of hand-coding the entire pathogen axis.
- Its own future-work section states that current annotations are limited to disease names, pathogen taxonomy and brief symptoms, and that extending them with severity scales and **management recommendations** would let models act like expert agronomists. **Cite this as direct evidence of the gap this paper fills.**

**AgroBench** — ICCV 2025 VLM benchmark, expert-annotated by agronomists. 203 crops, 682 disease categories, 134 pests, 108 weeds; 7 task types including management. `dahlian00.github.io/AgroBenchPage`, arXiv `2507.20519`. Even the strongest evaluated model (GPT-4o, 73.45% overall) sits far from reliable, against a 19.03% random baseline. Cite as related work on the action side.

**CDDM** — 137,000 images / 60 disease classes / 16 crops + ~1M QA pairs covering prevention and control. arXiv `2503.06973`, ECCV 2024. **The GitHub repo hosts code and external links, not the images.** Cite as related work; do not plan to use.

**IP102** — 75,000+ images / 102 insect pest classes. `github.com/xpwu95/IP102`, CVPR 2019. Dropped from this project (cost/benefit).

### 4.5 Knowledge bases for the action mapping — manual sources

None of these has a bulk-download path for the content needed. The mapping is built by hand.

| Source | URL | Role | Terms |
|---|---|---|---|
| **CABI PlantwisePlus** | `plantwiseplusknowledgebank.org` | Pest Management Decision Guides, ~3,500 species pages, 15,000+ items | Factsheets CC BY-NC-SA 4.0. No API. Bulk data via `enquiries@cabi.org` |
| **UC IPM Guidelines** | `ipm.ucanr.edu/agriculture/` | Concrete per-crop, per-disease control actions | Open HTML, no API. ~2M page views/year |
| **EPPO Global Database** | `gd.eppo.int`, Data Portal `data.eppo.int` | Disease ↔ pathogen ↔ vector; 98,700+ species; 1,900+ regulated pests | Free registration. **Data Portal supports batch export** — the one machine-readable source here |
| **PPDB** | `sitem.herts.ac.uk/aeru/ppdb/en/` | PHI, REI, pesticide class | ⚠️ **Bulk copying prohibited by copyright terms.** Manual lookup only |
| **AGROVOC** | `aims.fao.org/aos/agrovoc/` | 40,983 concepts, 986,076 terms, up to 42 languages | RDF bulk download + public SPARQL |
| **Plant Ontology** | `purl.obolibrary.org/obo/po.owl` | 1,300+ anatomy / growth-stage terms | CC BY 4.0; SPARQL at `sparql.hegroup.org/sparql` |

### 4.6 Excluded — do not spend time on these

| Item | Reason |
|---|---|
| **Leaf-CG** (441,448 images, 59 species, 373 diseases, 4 severity levels) | Not publicly released. Journal is ***Plant Phenomics*** (ISSN 2643-6515), PII `S2643651526000701` — **not** *Artificial Intelligence in Agriculture*. Cite as related work or omit |
| **AI Challenger 2018** | Original platform closed; only a Baidu AI Studio mirror (`aistudio.baidu.com/datasetdetail/76075`) of unstated license |
| **PDDD / PlantPAD** (400k+ / 421,314 images) | Real and useful but far too large for Colab free tier |
| **CDDM** | Images not in the repo |
| **IP102** | Marginal OOD role, does not repay 75k images of download |
| **PlantSeg on Roboflow** | Truncated |
| **PlantVillage on Kaggle** | No `leaf_id` |

---

## 5. Corrections to earlier project documents

These were established after `DATASETS.md` was written. **`DATASETS.md` contains at least one factual error that a reviewer would catch.**

**5.1 PlantWild accuracy — the important one.**
`DATASETS.md` states the best method on PlantWild reaches "~51.8%". **Wrong.** 51.80% is the **few-shot** MVPDR number (compared against Tip-Adapter-F at 50.07% and CoOp at 51.21%). An intermediate correction to "~67%" is also not current. The correct figures: MVPDR published **76.18%** top-1; DINOv2 ViT-L/14 alone **77.56%**; three-backbone frozen fusion **80.23 ± 0.41%** across five seeds. Source: Frontiers in Plant Science, DOI `10.3389/fpls.2026.1860665` (June 2026). See §2 for why this strengthens rather than weakens the paper.

**5.2 PlantSeg Zenodo record — resolved.** Use v7, record `17719108`.

**5.3 PlantSeg license is version-dependent.** v7 = CC BY-NC 4.0.

**5.4 PlantVillage leaf grouping is partial.** 41,112 of 54,306 images. State how the remainder is handled.

**5.5 PlantDoc class count.** 28 train / 27 test, not "27 = 17 + 10".

**5.6 JMuBEN DOI mapping.** `t2r6rszp5c` = JMuBEN; `tgv3zb82nd` = JMuBEN2. Cite the right half.

**5.7 Leaf-CG journal.** *Plant Phenomics*, not *Artificial Intelligence in Agriculture*. Image count 441,448.

**5.8 FieldPlant version drift.** Cite the paper's 5,170 images / 27 classes; note the hosted build differs.

**5.9 CDDM.** Repo hosts links, not images.

---

## 6. Current state of implementation

### Repository layout

```
notebooks/
  00_download_verify_manifest.ipynb   download + verify + manifest
  01_eda_classification_sets.ipynb    EDA          [EXECUTED — partial data]
  02_severity_plantseg.ipynb          mask → severity → tiers
  03_severity_validation_coffee.ipynb RoCoLe / BRACOL validation
  04_leakage_dedup_crosswalk.ipynb    leaf-grouped split, phash dedup, crosswalk
  05_baseline_pretraining.ipynb       baseline + abstention + harm matrix [EXECUTED — partial data]
reports/
  DATASET_ASSESSMENT.md               per-dataset verdicts, primary-source verified
  figures/                            eda_plantdoc.png, confusion_plantdoc.png, abstention_plantdoc.png
data/
  raw/plantdoc/                       ONLY dataset present; TRUNCATED
  interim/eda_summary.csv
  mapping/                            EMPTY
DATASETS.md                           acquisition spec (see §5 for its errors)
```

All notebooks are Colab-first with a local fallback, auto-detect which datasets are present, and parse cleanly.

### ⚠️ What the existing numbers actually are

**No scientific result has been produced yet.** Everything computed so far is a smoke test on a truncated download.

`data/interim/eda_summary.csv`:

```
dataset,n_images,n_classes,imbalance_ratio,largest_class,smallest_class,corrupt_in_sample,probed,median_w,median_h,median_megapix
plantdoc,407,27,23.2,Apple Scab Leaf (93),Corn Gray leaf spot (4),0,400,800,640,0.48
```

- **407 images** against PlantDoc's real 2,598 — roughly 16% of the dataset.
- `train/` contains **only three classes** (Apple Scab Leaf, Apple leaf, Apple rust leaf); the rest failed to download.
- The confusion matrix figure is **3×3**, not 27×27.
- The abstention curve reports full-coverage accuracy **0.414** on a three-class problem where chance is 0.333, from a model trained in ~3 seconds.

**None of these three figures may appear in the paper.** They demonstrate that the code runs. That is their entire value.

### Verified as working

- Notebooks 01 and 05 execute end-to-end without errors on real image data
- Zero corrupt files among 400 probed
- The abstention gate mechanism functions (selective accuracy rises monotonically as coverage falls)
- `DATASET_ASSESSMENT.md` was fact-checked against primary sources and marks unverifiable claims as such rather than asserting them

---

## 7. Critical findings from manual data inspection

These came from reading PlantDoc filenames, not from any model. They are among the most valuable observations in the project so far.

### 7.1 Healthy classes are stock photography; diseased classes are field photography

Healthy-class filenames are dominated by stock-library artifacts:

```
Strawberry leaf/  strawberry-leaves-isolated-white-17473157.jpg
                  strawberry-leaf--stock-photo-1431216.jpg          (8/8 files)
Raspberry leaf/   depositphotos_1323264-Raspberry-leaf-on-white.jpg
Peach leaf/       stock-photo-peach-leaf-isolated-on-white-background-281097503.jpg
Apple leaf/       stock-photo-apple-leaves-isolated-on-white-background-232913425.jpg
```

Diseased-class filenames are field/extension photography:

```
apple-scab-venturia-inaequalis-early-leaf-infection-and-mycelium-AW0TTX.jpg
corn-gray-leaf-spot-f4.jpg
LateBlight04.jpg
```

**Consequence:** "healthy" correlates strongly with a white studio background. A model can separate healthy from diseased without examining the leaf.

**Why this matters for this specific paper:** healthy maps to the `monitor` action — "do nothing". If the visual signature of health is a white background, then in the field, where no white background exists, the system will classify healthy plants as diseased and prescribe treatment. That is a **systematic over-treatment bias originating in dataset construction, not in the model** — wasted money, wasted chemicals, exactly what this paper measures. This deserves its own paragraph and probably its own figure.

Quantify it on the complete download:

```bash
cd data/raw/plantdoc
for d in */*/; do
  n=$(ls "$d" | wc -l)
  s=$(ls "$d" | grep -icE 'stock-photo|depositphotos|shutterstock|isolated|white-background|123rf|alamy|picture-id')
  printf "%-42s %4d %4d %5.1f%%\n" "$d" "$n" "$s" "$(echo "100*$s/$n"|bc -l)"
done | sort -k4 -nr
```

### 7.2 Ground-truth labels contain action-level errors

Identified from filenames in the partial download alone:

| Labelled as | Filename | Actually depicts |
|---|---|---|
| Tomato leaf **yellow virus** | `glyphosate.jpg` | Herbicide damage |
| Corn **leaf blight** | `corn-gray-leaf-spot-f4.jpg`, `2013Corn_GrayLeafSpot_0815_0003.jpg`, `0796.20graylssymt.jpg` | Gray leaf spot — the adjacent class |
| **Soyabean** leaf | `leaf-raspberry-isolated-on-a-white-...jpg` | A raspberry leaf |
| Raspberry leaf *(healthy)* | `iron-deficiency-raspberry-leaf-chlorosis-...jpg` | Iron deficiency |
| Blueberry leaf *(healthy)* | `blueberry-leaves-normal-above-and-iron-deficient-below-...jpg` | Iron deficiency |
| Apple leaf *(healthy)* | `apple-tree-leaf-curl-...-aphids-...jpg` | Aphid damage |
| Bell_pepper leaf *(healthy)* | `why-are-my-pepper-plants-yellow-...-green-veins.jpg` | Chlorosis |
| grape leaf **black rot** | `piano gully spray seed damage 06.jpg` | Spray/drift damage |

Several of these are not merely label noise but **action-level errors**. Herbicide damage labelled as a virus: the label prescribes "remove the plant and control the vector"; reality is "do nothing, this is drift from a neighbouring field." Iron deficiency labelled healthy: the label prescribes "no action"; reality is "correct the nutrition."

**Use this.** The reference standard against which everyone measures accuracy itself contains errors *at the action level*. This strengthens the paper's thesis and simultaneously obliges an honest response: either manually clean the evaluation subset or explicitly report a contamination estimate.

---

## 8. Known problems and open technical risks

### 8.1 The severity pipeline has a systematic flaw

`leaf_mask_otsu()` in notebooks 02 and 03 separates "greenish, saturated pixels" from background using Otsu thresholding on an excess-green + saturation score.

On PlantVillage (leaf on white) this works. **On PlantSeg it does not: the background is itself green** — grass, adjacent foliage, canopy. Otsu will assign background vegetation to the leaf, inflating leaf area and deflating severity.

The error is **systematic rather than random**, and — critically — **the planned validation will not detect it.** RoCoLe consists of single leaves on uniform backgrounds, where Otsu performs well. A strong Spearman ρ on RoCoLe would produce false confidence in a method that fails on the target data.

Options: (a) segment the leaf with SAM (free, runs on Colab); (b) report lesion fraction relative to image area and name the metric honestly; (c) restrict severity analysis to datasets carrying leaf masks. Option (a) is correct but costs time.

**Decision: severity is demoted to an optional extension.** The paper stands on action-level and harm-weighted evaluation plus abstention. If severity does not converge within a week, its absence does not kill the paper.

### 8.2 Action-class collapse mechanically inflates accuracy

Projecting 38 disease labels onto 4 action classes raises accuracy for free, independent of model quality. Mandatory countermeasures:

1. Report the **distribution over action classes**.
2. Report the **majority-action baseline** (always predict the most frequent action) as the floor.
3. Report **harm-weighted error**, which does not benefit from collapse.

Without these, a reviewer will correctly object that the paper measured task easiness rather than decision quality.

### 8.3 The viral axis is thin where it matters most

PlantVillage contains only **2 viral classes out of 38**, yet viral misdiagnosis carries the maximum harm weight. Build the class set **around the action axis rather than by taking datasets wholesale** — pull additional viral classes from Cassava (CMD, CBSD), PlantWild and PlantDoc. Otherwise the most important cell of the harm matrix rests on two classes.

### 8.4 Other issues

- **Healthy classes are 12 of 38 in PlantVillage** — report them separately or they dilute every metric.
- **Corn Gray leaf spot has n = 4** in the current PlantDoc download, with an overall imbalance ratio of 23.2:1. Nothing can be concluded from four examples, and the class is also contaminated by its neighbour (§7.2). Merge it or exclude it with justification.
- **Cross-dataset leakage.** PlantWild, PlantSeg and PlantDoc all draw partly from web image search and may share images. Any image present in both a training and an evaluation set invalidates the generalization claim. Notebook 04 runs perceptual-hash deduplication (`imagehash.phash`, Hamming ≤ 6) — run it before reporting any cross-dataset number.
- **Action-label subjectivity.** The disease→action mapping is partly a judgement call. Ground every row in a citable source (UC IPM, CABI, EPPO) and say so.

---

## 9. Licensing discipline

Springer reviewers check this. State it explicitly in the Data section.

| Status | Datasets |
|---|---|
| **Redistributable** | PlantDoc (CC BY 4.0), Plant Ontology (CC BY 4.0) |
| **Non-commercial** | PlantSeg v7 (CC BY-NC 4.0), CABI factsheets (CC BY-NC-SA 4.0) |
| **Non-commercial, no derivatives — metrics only** | PlantWild (CC BY-NC-ND 4.0) |
| **Share-alike** | PlantVillage (CC BY-SA 3.0 per HF card; some mirrors claim CC0 — cite the primary source) |
| **Unstated — internal use only** | Master Plant Disease Dataset |
| **Bulk copying prohibited** | PPDB |

**Any released artifact is code and label mappings, never images.**

Also disclose that PlantWild and PlantDoc images were collected via web image search. Stating this up front is stronger than having a reviewer discover it.

---

## 10. Priorities

| # | Component | Status | Note |
|---|---|---|---|
| 1 | **Disease → action mapping + harm weights** | **Not started** | The actual contribution. Needs no data, no GPU, no download — only UC IPM, EPPO and LeafNet's pathogen field. Start immediately and in parallel with everything else |
| 2 | Action-level re-scoring of standard models | Blocked on 1 | Core of the paper |
| 3 | Abstention + risk–coverage | Code exists | Cheap once 2 is done |
| 4 | Severity → intervention tier | Flawed (§8.1) | **Optional** |

**Free experiment worth adding:** PlantVillage ships a `segmented` config (background removed) in the same HF repository. Training on `color` versus `segmented` and comparing the drop on field data is a built-in background ablation that directly quantifies the contribution of background cues. It costs nothing and yields a complete experiment.

---

## 11. Open questions and blockers

1. **The submission deadline is unresolved** — 31 July (Registration page) versus 15 August (CFP page). Today is 28 July. The difference between three days and eighteen days changes every downstream decision, including whether severity is attempted at all. **Contact `ica@iitrpr.ac.in`.**
2. **The full PlantDoc re-download has not completed.** All current numbers are from a 16% subset.
3. Whether virtual presentation is permitted for an author unable to travel to India, and whether any fee reduction exists.
4. Whether the 8,000 healthy images are inside the PlantSeg v7 archive (the landing text emphasises the masked set).

---

## 12. Conventions for anyone working on this project

- **Do not present smoke-test numbers as results.** The 0.414 accuracy, the 3×3 confusion matrix and the 407-image EDA are plumbing checks.
- **Do not train on the Master Plant Disease Dataset.** Vocabulary only.
- **Do not use PlantVillage without `leaf_id` grouping.**
- **Do not report a cross-dataset number before running the perceptual-hash deduplication in notebook 04.**
- **Do not frame the paper as "models are bad."** Models reach ~80% on PlantWild. The argument is that accuracy is the wrong gate, not that accuracy is low.
- **Do not position the work against LeADS.** Position it as the continuation of LeADS by the same institution.
- **Every row of the disease→action mapping needs a citable source.** This is the part of the work that must be unmistakably human and defensible; it is what separates this paper from a generated one.
- **Prefer honest negative results.** "The zero-cost leaf estimate is the bottleneck" is a finding. Silence about it is a defect.

---

## 13. Key references

| Work | Identifier |
|---|---|
| Mohanty, Hughes & Salathé (2016) — PlantVillage | DOI `10.3389/fpls.2016.01419` |
| Singh et al. (2020) — PlantDoc | DOI `10.1145/3371158.3371196`; arXiv `1911.10317` |
| Wei et al. (2024) — PlantWild / MVPDR | arXiv `2408.03120` (ACM MM 2024) |
| Wei et al. (2025) — PlantSeg | DOI `10.1038/s41597-025-06513-4`; arXiv `2409.04038` |
| Frontiers (2026) — frozen multi-backbone fusion on PlantWild, SOTA 80.23% | DOI `10.3389/fpls.2026.1860665` |
| Moupojou et al. (2023) — FieldPlant | DOI `10.1109/ACCESS.2023.3263042` |
| Quoc, Dao & Quach (2026) — LeafNet / LeafBench | arXiv `2602.13662` |
| Shinoda et al. (2025) — AgroBench | arXiv `2507.20519` (ICCV 2025) |
| CDDM (2024) | arXiv `2503.06973` (ECCV 2024) |
| Esgario et al. (2020) — BRACOL | *Comput. Electron. Agric.* 169:105162 |
| Parraga-Alava et al. (2019) — RoCoLe | *Data in Brief* 25:104414 |
| Jepkoech et al. (2021) — JMuBEN | *Data in Brief* 36:107142 |
| Wang, Sun & Wang (2017) — severity estimation | DOI `10.1155/2017/2917536` |
| Fenu & Malloci (2021) — DiaMOS Plant | DOI `10.3390/agronomy11112107` |
| Das, Goel & Saini (2025) — **LeADS**, ICA 2025 | In CCIS, DOI `10.1007/978-3-032-17083-5` |
| Wu et al. (2019) — IP102 | IEEE CVPR 2019, pp. 8787–8796 |
| Barbedo et al. (2018) — Digipathos / PDDB | IEEE LATAM, doc 8444395 |
