# Dataset Acquisition Spec

**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation Framework for Deep Learning-Based Plant Disease Recognition*
**Target venue:** ICA 2026 (4th Int. Conf. on Agriculture-Centric Computation), IIT Ropar, India — Springer CCIS
**Compute budget:** Google Colab free tier (T4, ephemeral disk). Zero financial budget.
**Last verified:** 2026-07-28

---

## 0. Task for the agent

Download, verify, and inventory the datasets below **in priority order**. Do not proceed to Tier 2 until every Tier 1 dataset passes its verification check.

For each dataset:

1. Download using the exact identifier given. Do not substitute mirrors.
2. Run the **Verify** block. Record actual vs. expected counts.
3. Append a row to `data/manifest.csv` with: `name, tier, source, local_path, n_files, n_classes, size_gb, license, sha256_of_archive (if applicable), download_utc, status`.
4. If a check fails, **stop and report** — do not silently substitute another source.

Write all datasets under `data/raw/<dataset_name>/`. Mount Google Drive first; Colab's local disk does not survive a session restart.

```python
from google.colab import drive
drive.mount('/content/drive')
%cd /content/drive/MyDrive/diagnosis-to-decision
```

**Do not commit any image data to git.** Add `data/` to `.gitignore`. Only `manifest.csv` and the label-mapping files are versioned.

---

## 1. Credentials required

| Service | Needed for | Setup |
|---|---|---|
| Kaggle API | Cassava, Master Plant Disease Dataset | Account → Settings → Create New API Token → place `kaggle.json` at `~/.kaggle/kaggle.json`, `chmod 600` |
| Hugging Face | PlantVillage, PlantWild, LeafNet | `huggingface-cli login` (token may be needed for gated repos) |
| Roboflow | FieldPlant | Free account → Settings → API key |

Zenodo, GitHub, and Mendeley Data require no authentication.

```bash
pip install -q datasets huggingface_hub kaggle roboflow imagehash pillow tqdm pandas
```

---

## 2. TIER 1 — required for the paper

These four cover all experimental components. Nothing in the study can run without them.

### 1.1 PlantVillage

Laboratory-condition baseline. The training source for all models.

| Field | Value |
|---|---|
| Images | 54,306 |
| Classes | 38 (crop × disease) |
| Crops / diseases | 14 species, 26 diseases |
| Conditions | Laboratory, uniform background |
| Annotation | Image-level label + `leaf_id` |
| Size | ~2–3 GB |
| License | CC BY-SA 3.0 (per HF card) |
| Paper | Mohanty, Hughes, Salathé (2016), *Front. Plant Sci.* — DOI `10.3389/fpls.2016.01419` |

**Authoritative source — use this one:**

```python
from datasets import load_dataset
pv = load_dataset("mohanty/PlantVillage", "color")
# configs also available: "grayscale", "segmented"
```

Upstream original: `https://github.com/spMohanty/PlantVillage-Dataset`

> **CRITICAL — data leakage.** PlantVillage contains multiple photographs of the *same physical leaf*. A random `train_test_split` places images of one leaf on both sides and inflates accuracy by a large margin. The HF `mohanty/PlantVillage` release carries a **`leaf_id`** field and leaf-grouped splits. Use them. **Do not use the Kaggle mirrors** (`emmarex/plantdisease`, `abdallahalidev/plantvillage-dataset`) — they lack `leaf_id`.

**Verify:**
```python
assert len(pv["train"]) + len(pv.get("test", [])) >= 54000
assert "leaf_id" in pv["train"].features          # must be present
print(len(set(pv["train"]["label"])))              # expect 38 across full set
```

---

### 1.2 PlantWild

Primary in-the-wild evaluation set. The main cross-dataset generalization target.

| Field | Value |
|---|---|
| Images | 18,542 |
| Classes | 89 (56 diseased + 33 healthy); v2 extends to 115 |
| Conditions | In-the-wild, scraped from Google / Ecosia / Baidu image search, expert-filtered |
| Annotation | Image-level label + per-class textual symptom descriptions |
| Size | ~3 GB |
| License | **CC BY-NC-ND 4.0** |
| Paper | Wei et al. (2024), ACM MM — arXiv `2408.03120` |

```python
pw = load_dataset("uqtwei2/PlantWild")
```

Baseline code: `https://github.com/tqwei05/MVPDR`
Project page: `https://tqwei05.github.io/PlantWild/`

> **License constraint:** NC-ND. Research use and publishing metrics is fine. **Do not redistribute a repackaged or derived version of the images.** Any released artifact must be code + label mappings only.

**Verify:**
```python
n = sum(len(pw[s]) for s in pw)
assert 18000 <= n <= 19000
```

Reference point for the paper: the strongest published method on PlantWild reaches only ~51.8% accuracy. Large headroom, and a natural source of hard/ambiguous cases for the abstention gate.

---

### 1.3 PlantSeg

Pixel-level disease masks. This is what makes the **severity** component of the paper possible — lesion area ÷ leaf area → severity → intervention tier.

| Field | Value |
|---|---|
| Images | 11,400 with segmentation masks + 8,000 healthy |
| Classes | 115 diseases |
| Conditions | In-the-wild |
| Annotation | Pixel-level masks (JPEG images / PNG annotations) + `Metadata.csv` |
| Split | 70 / 10 / 20 |
| Size | ~6 GB |
| License | **CC BY-NC 4.0** |
| Paper | Wei et al. (2025), *Scientific Data* — DOI `10.1038/s41597-025-06513-4`; arXiv `2409.04038` |

**Sources, in order of preference:**

1. Zenodo record `13762907` — DOI `10.5281/zenodo.13762907`
2. Kaggle: `kaggle datasets download -d weitianqi/plantseg`
3. GitHub (code + pointers): `https://github.com/tqwei05/PlantSeg`

> **FLAG — multiple Zenodo records exist.** Record `13762907` and record `13958858` both circulate, and the *Scientific Data* paper cites a third DOI. **A human must open the Zenodo landing page and confirm which record is the complete dataset before bulk download.** Report which one you used.
>
> Do **not** use the Roboflow copy (`uqtwei-6gmpn/plantseg-segmentation-dataset`) — it is truncated by Roboflow's size limits.

**Verify:**
```bash
find data/raw/plantseg/images -type f | wc -l      # ~11,400 diseased
ls data/raw/plantseg/annotations | head
test -f data/raw/plantseg/Metadata.csv || echo "MISSING METADATA"
```

---

### 1.4 PlantDoc

Second field-condition test set. Cleanest license of the in-the-wild sets.

| Field | Value |
|---|---|
| Images | 2,598 |
| Classes | 27 (17 diseases + 10 healthy) |
| Crops | 13 species |
| Conditions | Field, internet-sourced (~300 h of manual annotation) |
| Size | ~300 MB |
| License | **CC BY 4.0** |
| Paper | Singh et al. (2020), CoDS-COMAD — DOI `10.1145/3371158.3371196`; arXiv `1911.10317` |

```bash
git clone https://github.com/pratikkayal/PlantDoc-Dataset.git data/raw/plantdoc
# object-detection variant, if bounding boxes are needed later:
git clone https://github.com/pratikkayal/PlantDoc-Object-Detection-Dataset.git
```

**Caveat:** some images are actually laboratory shots, and annotation was done without a plant pathologist — expect label noise. Note this as a threat to validity in the paper.

**Verify:**
```bash
find data/raw/plantdoc -name "*.jpg" -o -name "*.JPG" | wc -l    # ~2,598
ls data/raw/plantdoc/train | wc -l                                # ~27 class dirs
```

---

## 3. TIER 2 — strongly recommended

### 2.1 FieldPlant

The only field dataset annotated **under plant-pathologist supervision** — the highest-quality ground truth available for real plantation conditions.

| Field | Value |
|---|---|
| Images | 5,170 (8,629 individually annotated leaves) |
| Classes | 27 |
| Crops | Corn, cassava, tomato (Cameroon plantations) |
| Annotation | Bounding boxes per leaf |
| Paper | Moupojou et al. (2023), *IEEE Access* 11:35398–35410 — DOI `10.1109/ACCESS.2023.3263042` |

```python
from roboflow import Roboflow
rf = Roboflow(api_key="YOUR_KEY")
ds = rf.workspace("plant-disease-detection").project("fieldplant").version(11).download("folder")
```

Landing page: `https://universe.roboflow.com/plant-disease-detection/fieldplant`

---

### 2.2 Cassava Leaf Disease Classification

Real smallholder field imagery. Contributes the **viral** disease classes (CMD, CBSD), which carry the heaviest penalty in the harm matrix — viral misread as fungal means the farmer sprays a plant that should have been removed.

| Field | Value |
|---|---|
| Images | 21,367 (train) |
| Classes | 5 — CBB, CBSD, CGM, CMD, Healthy |
| Origin | Uganda (NaCRRI + Makerere AI Lab) |
| Imbalance | **61.9% of training images are CMD** |
| Size | ~6 GB |

```bash
kaggle competitions download -c cassava-leaf-disease-classification
```

Requires accepting competition rules on the Kaggle site first. Do not confuse with the older `cassava-disease` (2019) competition.

---

### 2.3 Master Plant Disease Dataset

A pre-merged, perceptual-hash-deduplicated union of 7 public sources. Saves substantial manual harmonization work.

| Field | Value |
|---|---|
| Images | 66,701 unique (after removing 3,504 duplicates via `imagehash.phash`) |
| Classes | 281 canonical (332 before dropping classes with <10 images) |
| Split | 80 / 10 / 20 with CSVs |
| Files | `master_images.zip`, `metadata.zip`, `outputs.zip` |

```bash
kaggle datasets download -d harisri2005/plant-disease-processed
```

> **License not stated** on the Kaggle page. Since it merges 7 upstream sources with mixed licenses, treat it as **internal working data only**. Use it to bootstrap the label crosswalk; do not redistribute, and cite the original seven sources in the paper.

---

## 4. TIER 3 — severity ground truth

There is **no large public dataset with ordinal severity labels**. The plan is: derive severity from PlantSeg masks, then validate that derivation against these small human-labelled sets.

| Dataset | Content | Access |
|---|---|---|
| **BRACOL** | 1,747 arabica coffee leaves; severity of leaf miner, rust, brown leaf spot, cercospora | Mendeley DOI `10.17632/yy2k5y8mxg.1` — Esgario et al. (2020), *Comput. Electron. Agric.* 169:105162 |
| **RoCoLe** | 1,560 robusta coffee leaves; healthy/unhealthy + severity by spotted leaf area + **leaf segmentation masks** | Mendeley DOI `10.17632/c5yvn32dzg.2` — Parraga-Alava et al. (2019), *Data in Brief* 25:104414 |
| **JMuBEN + JMuBEN2** | 58,555 coffee images, 5 classes | Mendeley `tgv3zb82nd/1` and `t2r6rszp5c/1` — Jepkoech et al. (2021), *Data in Brief* 36:107142 |
| **DiaMOS Plant** | 3,505 pear images (499 fruit + 3,006 leaves); severity bands 0% → >50%; full season, Italy | DOI `10.3390/agronomy11112107` — Fenu & Malloci (2021) |
| **CD&S** | Corn field images: NLB 511, GLS 524, NLS 562 + severity estimation | arXiv `2110.12084` — Ahmad et al. |
| **Apple black rot 4-stage** | PlantVillage apple black rot images re-annotated by botanists into 4 severity stages | Described in DOI `10.1155/2017/2917536` — Wang, Sun, Wang (2017) |

Mendeley datasets download directly over HTTPS with no auth. RoCoLe is the most valuable of these: it has both severity *and* masks, so it validates the mask→severity pipeline end to end.

---

## 5. TIER 4 — metadata and knowledge benchmarks

Not for training. These supply the **pathogen type** per disease class, which is the backbone of the disease→action mapping.

| Resource | What it gives | Access |
|---|---|---|
| **LeafNet / LeafBench** | 186k images, 22 crops, 62 diseases; per-class metadata: species, disease, **pathogenic agent** (fungal / bacterial / viral / oomycete / mite), symptom description, acquisition environment. LeafBench = 13,950 expert QA pairs | HF collection `enalis/leafsight`; GitHub `EnalisUs/LeafBench`; arXiv `2602.13662` |
| **AgroBench** | Expert-agronomist-annotated VLM benchmark: 203 crops, 682 diseases, 7 task types incl. management | `https://dahlian00.github.io/AgroBenchPage/`; arXiv `2507.20519` (ICCV 2025) |
| **CDDM** | 137k disease images + 1M QA pairs covering prevention and control strategies | GitHub `UnicomAI/UnicomBenchmark/tree/main/CDDMBench`; arXiv `2503.06973` (ECCV 2024) — **verify images are actually present in the repo before relying on it** |
| **IP102** | 75,000+ images, 102 insect pest classes | GitHub `xpwu95/IP102` — useful as an OOD / "vector control" action class |

**LeafNet is the highest-value item here.** Its per-class pathogen field can be joined onto PlantVillage/PlantWild class names to derive action classes semi-automatically instead of by hand.

---

## 6. Knowledge bases for action labels — MANUAL, not downloadable

The disease→action mapping is the paper's core contribution and must be built by hand from authoritative sources. **None of these have a bulk-download path for the content we need.**

| Source | URL | Use | Terms |
|---|---|---|---|
| **CABI PlantwisePlus Knowledge Bank** | `https://www.plantwiseplusknowledgebank.org` | Pest Management Decision Guides, Factsheets for Farmers, ~3,500 pest/disease species pages | Technical factsheets **CC BY-NC-SA 4.0**. No public API — read manually. Granular distribution data needs a request to `enquiries@cabi.org` |
| **UC IPM Pest Management Guidelines** | `https://ipm.ucanr.edu/agriculture/` | Concrete per-crop, per-disease control actions: fungicide, copper + sanitation, resistant varieties, removal | Open HTML, no API. ~2M page views/year — well-established authority |
| **EPPO Global Database** | `https://gd.eppo.int` + Data Portal `https://data.eppo.int` | Disease ↔ pathogen ↔ vector links; EPPO codes; 98,700+ species | Free registration. **Data Portal supports batch export of EPPO codes** — the one machine-readable source here |
| **PPDB** | `https://sitem.herts.ac.uk/aeru/ppdb/en/` | PHI (pre-harvest interval), REI (re-entry interval), pesticide class | ⚠️ **Bulk copying/downloading is prohibited by its copyright terms.** Look up individual entries manually only |
| **AGROVOC** | `https://aims.fao.org/aos/agrovoc/` | 40,983 concepts, 986,076 terms, up to 42 languages | RDF bulk download + public SPARQL endpoint. FAO-maintained |
| **Plant Ontology** | `http://purl.obolibrary.org/obo/po.owl` | 1,300+ anatomy / growth-stage terms | **CC BY 4.0**, OWL/OBO download, SPARQL at `https://sparql.hegroup.org/sparql` |
| **EU Pesticides Database / US EPA labels** | — | Registered active ingredients, regional legality, PHI/REI | Open, manual reading |

**Agent task here:** do *not* attempt to scrape CABI or PPDB. Instead, pull the EPPO code list and the AGROVOC RDF (both explicitly permit bulk access), and produce a starter table `data/mapping/disease_pathogen.csv` with columns `dataset_class, crop, disease_name, eppo_code, pathogen_type`. The human fills in the `action_class` column afterwards.

---

## 7. Known problems — do not waste time on these

| Item | Status |
|---|---|
| **Leaf-CG** (441,488 images, 59 species, 373 diseases, 4 severity levels) | Described in *Artificial Intelligence in Agriculture* (2026), PII `S2643651526000701`. **No public repository, DOI, or mirror found.** Not available. Do not plan around it |
| **AI Challenger 2018** (61 categories incl. severity) | Original platform closed. Only mirror is Baidu AI Studio `aistudio.baidu.com/datasetdetail/76075`, license unstated, possible regional blocking. **Skip** |
| **PDDD / PlantPAD** (400k+ images) | Real and useful, but far too large for Colab free tier. Skip unless disk allows |
| **PlantSeg on Roboflow** | Truncated by platform limits — incomplete. Use Zenodo or Kaggle |
| **PlantVillage on Kaggle** | Missing `leaf_id` → cannot build leak-safe splits. Use HF |
| **PPDB bulk export** | Explicitly forbidden by copyright terms |

---

## 8. Post-download tasks

Once Tier 1 verification passes:

1. **Deduplicate across datasets.** Compute `imagehash.phash` for every image in PlantVillage / PlantDoc / PlantWild / PlantSeg. Overlap is expected — PlantWild and PlantSeg were both built partly from web sources and may share images with PlantDoc. Write `data/interim/phash_index.parquet` and report the cross-dataset collision count. **Any image appearing in both a training and an evaluation set invalidates the cross-dataset experiment.**

2. **Build the class crosswalk.** Emit `data/mapping/class_crosswalk.csv` with columns `source_dataset, original_label, crop_canonical, disease_canonical`. Seed it from the PlantSeg canonicalization (332 classes) and the Master Plant Disease Dataset canonicalization (281 classes), then reconcile. Flag every unmatched label for manual review rather than guessing.

3. **Extract severity from masks.** For PlantSeg, compute per-image `lesion_pixels / leaf_pixels` and write `data/interim/plantseg_severity.csv`. Leaf area needs a leaf-vs-background segmentation step — Otsu thresholding on the green channel is the zero-cost baseline.

4. **Report image statistics** per dataset: resolution distribution, aspect ratios, corrupt/unreadable files, class counts, imbalance ratio (max class / min class).

---

## 9. Minimal viable set

If disk or time runs short, this subset still supports every component of the paper:

- **PlantVillage** (HF, leaf-grouped) — training source
- **PlantSeg** — severity component
- **PlantWild** — in-the-wild evaluation + abstention hard cases
- **Cassava** — viral classes for the harm matrix
- **RoCoLe** or **BRACOL** — severity validation (both under 2 GB)

Everything else is an enhancement.

---

## 10. Licensing summary for the paper

State these explicitly in the Data section. Reviewers at a Springer venue will check.

- **Redistributable:** PlantDoc (CC BY 4.0), Plant Ontology (CC BY 4.0)
- **Non-commercial, no derivatives:** PlantWild (CC BY-NC-ND 4.0) — metrics only, no repackaging
- **Non-commercial:** PlantSeg (CC BY-NC 4.0), CABI factsheets (CC BY-NC-SA 4.0)
- **Share-alike:** PlantVillage (CC BY-SA 3.0 per HF card; some mirrors claim CC0 — cite the primary source, not mirrors)
- **Unstated / mixed:** Master Plant Disease Dataset — internal use only
- **Restricted:** PPDB — no bulk copying

Also disclose that PlantWild and PlantDoc images were collected via web image search. This is a real provenance limitation and stating it up front is stronger than having a reviewer find it.
