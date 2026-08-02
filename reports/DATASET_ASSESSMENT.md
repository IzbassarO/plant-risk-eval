# Dataset Assessment — *From Diagnosis to Decision*

**Target venue:** ICA 2026 (4th Int. Conf. on Agriculture‑Centric Computation), IIT Ropar — Springer CCIS, 12–15 pp. LNCS, double‑blind.
**Question this report answers:** for each dataset in `DATASETS.md`, *is it good enough to build the paper on?* — and, taken together, *is the study viable?*
**Method:** every headline figure, license, DOI, arXiv ID and repository below was checked against a **primary or authoritative source** (Hugging Face dataset cards + API, arXiv/CVF/Springer indexing, Zenodo landing pages, Mendeley DOIs, journal DOIs, GitHub REST). Where the spec was wrong, the correction and its source are given. Claims that could not be positively verified are marked **UNVERIFIABLE** rather than asserted.

> **Bottom line up front.** The dataset stack is **sufficient to publish**. Every dataset exists and nearly every figure in `DATASETS.md` checks out. The paper's four components — *diagnosis*, *in‑the‑wild generalization*, *severity*, *risk‑weighted / abstaining evaluation* — each have at least one adequate data source, and the **minimal viable set** (PlantVillage + PlantSeg + PlantWild + Cassava + RoCoLe) covers all four. The work is **methods‑limited, not data‑limited**: the contribution is the *action‑level, risk‑weighted evaluation framework*, and the data exists to instantiate it. Six corrections must be made before submission (§3) — one of them (the PlantWild "51.8 %" figure) is a factual error a reviewer would catch.

---

## 1 · Verdict at a glance

| Dataset | Tier | Role in the paper | Good enough? | Key caveat to disclose |
|---|---|---|---|---|
| **PlantVillage** | 1 | Training source (lab baseline) | ✅ **Yes** | Leaf grouping covers only **41,112 / 54,306** images; lab‑only domain |
| **PlantWild** | 1 | Primary in‑the‑wild eval | ✅ **Yes** | NC‑ND license (metrics only); **best method ≈ 67 %, not 51.8 %** |
| **PlantSeg** | 1 | Severity ground truth (masks) | ✅ **Yes** | Use **Zenodo v7 = 17719108**; license is version‑dependent |
| **PlantDoc** | 1 | Second field eval | ✅ **Yes (with noise)** | Label noise; class count is **28 train / 27 test**, not "27 (17+10)" |
| **FieldPlant** | 2 | Highest‑quality field GT | ✅ **Yes** | Hosted build drifts from paper (≈5,156 imgs / up to 31 cls) |
| **Cassava** | 2 | Viral classes for harm matrix | ✅ **Yes** | Severe imbalance (**CMD 61.9 %**) — must reweight/report |
| **Master Plant Disease** | 2 | Label‑crosswalk bootstrap | ⚠️ **Internal only** | License **UNVERIFIABLE (unstated)** — do not redistribute |
| **BRACOL** | 3 | Severity validation | ✅ **Yes** | Use the **whole‑leaf** set (1,747), not the symptom crops |
| **RoCoLe** | 3 | Severity + mask validation | ✅ **Best fit** | Has **both** severity labels **and** masks — the key validator |
| **JMuBEN(+2)** | 3 | Coffee volume | ✅ Optional | DOI mapping (see §3.6); 5 classes only |
| **DiaMOS / CD&S / Apple‑4‑stage** | 3 | Extra severity GT | ✅ Optional | Small/crop‑specific; use as robustness checks |
| **LeafNet / LeafBench** | 4 | Per‑class **pathogen type** → action mapping | ✅ **High value** | Real (arXiv 2602.13662); the semi‑automatic path to action labels |
| **AgroBench** | 4 | Management‑QA benchmark | ✅ Optional | ICCV 2025; VLM benchmark, not training data |
| **CDDM** | 4 | Control‑strategy QA | ⚠️ Optional | Repo hosts **code + external links, not the 137k images** |
| **IP102** | 4 | OOD / pest "vector control" class | ✅ Optional | Pests, not diseases — use as OOD only |
| **Leaf‑CG** | — | (wishlist) | ❌ **Unavailable** | No public data; **journal is *Plant Phenomics***, not AIA (§3.7) |

Legend: ✅ suitable · ⚠️ use with a stated restriction · ❌ not usable.

---

## 2 · Does the data cover every experimental component?

The paper has four moving parts. Each needs data; here is the coverage.

| Component | What it needs | Covered by | Status |
|---|---|---|---|
| **Diagnosis** (classify crop×disease) | Labelled disease images, leak‑safe split | PlantVillage (leaf‑grouped) | ✅ Solid |
| **Generalization** (lab→field drop) | An *independent* field eval set with no train overlap | PlantWild + PlantDoc + FieldPlant + Cassava | ✅ Multiple, cross‑checked for leakage (nb 04) |
| **Severity** (→ intervention tier) | Pixel masks + a way to validate the derived severity | PlantSeg (masks) + RoCoLe (masks **and** human severity) | ✅ Derivation + validation both possible |
| **Risk‑weighted / abstaining eval** | Per‑class **pathogen type** to build a harm matrix; hard cases for the gate | LeafNet pathogen field + EPPO/AGROVOC; PlantWild hard cases | ✅ Semi‑automatic mapping feasible |

**Conclusion:** no component is stranded for lack of data. The one component with no large ready‑made dataset — *ordinal severity labels* — is exactly the gap the paper closes by **deriving** severity from PlantSeg masks and **validating** it on RoCoLe. That is a contribution, not a blocker.

---

## 3 · Corrections that must be made before submission

These are the places where `DATASETS.md` (and therefore a draft written from it) would state something a reviewer can falsify. All are sourced.

**3.1 PlantWild "only ~51.8 % accuracy" — WRONG.**
51.8 % is the **16‑shot few‑shot** number for the MVPDR baseline, not the ceiling. Fully‑supervised methods on PlantWild range from ~53 % (CLIP‑Adapter) to **~67 %** (MVPDR). Cite the fully‑supervised best (~67 %) as the state of the art and, if you want to stress difficulty, name the few‑shot regime explicitly. *Source: arXiv:2408.03120, Table 1.* The paper's "large headroom" framing survives — just with the correct number.

**3.2 PlantSeg Zenodo record — resolved; use v7.**
The `DATASETS.md` flag ("multiple records, a human must confirm") is now answered. One Zenodo *concept*, several versions: **v1 `13293891`** (restricted), **v2 `13762907`** (3.0 GB, superseded), **v4 `13958858`** (1.7 GB, 7:1:2 split, superseded), **v7 `17719108`** (1.1 GB, **current, cited by the published *Scientific Data* paper**). **Cite and download v7, DOI `10.5281/zenodo.17719108`.**

**3.3 PlantSeg license is version‑dependent.**
v7 / published dataset = **CC BY‑NC 4.0**; the arXiv preprint and v1–v4 = **CC BY‑NC‑ND 4.0**. State the license of the exact version you use (v7 → CC BY‑NC 4.0). *Sources: zenodo.org/records/17719108; arXiv:2409.04038.*

**3.4 PlantVillage leaf grouping is partial.**
`leaf_id` is real (HF card declares the feature; repo ships `leaf_grouping/leaf-map.json` and precomputed `splits/color_*.txt`). **But** the original paper maps leaves for only **41,112 of 54,306** images — the remaining ~13,000 cannot be leaf‑grouped. Report your leak‑safe split as "leaf‑grouped where leaf identity is known (41,112 images); the remainder handled by [your rule]." Also: the HF `color` split sums to **54,305** (off‑by‑one vs the paper's 54,306). *Source: Frontiers 10.3389/fpls.2016.01419; HF mohanty/PlantVillage.*

**3.5 PlantDoc class count.**
Not "27 (17 + 10)." The repo has **28 classes in `train` (18 disease + 10 healthy)** and **27 in `test`** (test drops *Tomato two‑spotted spider‑mite*). The paper says "13 species, up to 17 disease classes." State the split and count you actually use. *Source: github.com/pratikkayal/PlantDoc-Dataset; arXiv:1911.10317.*

**3.6 JMuBEN DOI mapping (if used).**
`t2r6rszp5c` = **JMuBEN** (Cercospora 7,682 + Rust 8,337 + Phoma 6,572 = 22,591); `tgv3zb82nd` = **JMuBEN2** (Miner 16,979 + Healthy 18,985 = 35,964); total 58,555. Cite the right DOI for the right half.

**3.7 Leaf‑CG journal misattributed (only matters if you mention it).**
The paper (PII `S2643651526000701`) is in ***Plant Phenomics*** (ISSN 2643‑6515), **not** *Artificial Intelligence in Agriculture* (ISSN 2589‑7217). Image count is likely **441,448**, not 441,488. Data remains non‑public. Either cite it correctly as related work or drop it.

**Also worth a line, not blockers:**
- **Master Plant Disease** license is **unstated/UNVERIFIABLE** — treat as internal working data; cite the seven upstream sources, don't redistribute. Phrase the counts as "66,701 after deduplication *and filtering*" (70,457→66,701 is not a clean minus‑3,504).
- **CDDM** GitHub hosts **code + external download links, not the 137k images** — don't claim the repo contains them.
- **FieldPlant**: cite the paper's **5,170 images / 27 classes**; note the Roboflow‑hosted build differs (~5,156 images, up to 31 classes / 4 species).
- **BRACOL**: "brown leaf spot" **is** the Phoma class (no ambiguity); the 1,747 count is the **whole‑leaf** set, distinct from the symptom‑crop subset.

---

## 4 · Per‑dataset assessment

### Tier 1 — required

**PlantVillage** — *training source.* 54,306 lab images, 38 classes, 14 species, 26 diseases; CC BY‑SA 3.0 (HF card). **Verdict: essential and adequate as the training source,** with two disclosures: (i) it is lab‑only (uniform background) — that is the *point*, it sets up the domain gap; (ii) leaf grouping is partial (§3.4). The well‑known leakage trap is real and avoidable — nb `04` builds the leaf‑grouped split. Do **not** use the Kaggle mirrors (no `leaf_id`).

**PlantWild** — *primary field eval.* 18,542 in‑the‑wild images, 89 classes (v2 → 115), CC BY‑NC‑ND 4.0, ACM MM 2024. **Verdict: the right primary generalization target.** Genuinely hard (best ~67 %), so it exposes the lab→field drop and supplies ambiguous cases for the abstention gate. License is **metrics‑only** — publish numbers, never repackaged images. Provenance (web image search) is a limitation to state up front.

**PlantSeg** — *severity ground truth.* 11,458 masked disease images + 8,000 healthy, 115 disease classes, *Scientific Data* 2025/26. **Verdict: this is what makes severity possible;** without it the diagnosis→severity→action chain has no pixel ground truth. Use v7 (§3.2), cite its license (§3.3). Confirm the 8,000 healthy images are inside the v7 archive if you need them (the landing text emphasises the masked set).

**PlantDoc** — *second field eval, cleanest license.* 2,598 images, 13 species, **CC BY 4.0** (redistributable). **Verdict: useful corroborating field set** and the only redistributable in‑the‑wild source — good for released qualitative figures. Label noise (annotated without a pathologist; some lab shots mixed in) is a real threat to validity; disclose it and prefer FieldPlant where annotation quality matters. *This is the one dataset already downloaded and analysed locally — see nb `01`/`05` for real numbers.*

### Tier 2 — strongly recommended

**FieldPlant** — *highest‑quality field GT.* Pathologist‑supervised bounding‑box annotation on real Cameroonian plantations; IEEE Access 2023. **Verdict: the gold standard for field annotation quality;** use it where you need trustworthy field labels (and as a detection‑style stress test). Mind the hosted‑vs‑paper version drift (§3).

**Cassava** — *viral classes for the harm matrix.* 21,367 images, 5 classes, Uganda. **Verdict: important for the risk story** — CMD/CBSD are the viral classes that carry the heaviest harm weight (viral misread as fungal → wrong action, spread). The **61.9 % CMD** imbalance is a feature for the harm analysis but demands class‑balanced sampling / loss reweighting; report the imbalance ratio.

**Master Plant Disease** — *crosswalk bootstrap.* 66,701 deduped images, 281 canonical classes, merges 7 sources. **Verdict: use it to seed the label crosswalk, not as released data** (license unstated). Its canonicalization saves real harmonization effort (nb 04 seeds from it).

### Tier 3 — severity validation

**RoCoLe** — **the key validator.** 1,560 robusta leaves with rust severity (L1–L4 by % area) **and** leaf segmentation masks. **Verdict: the single most valuable Tier‑3 set** — because it has *both* severity labels and masks, it validates the mask→severity pipeline end‑to‑end (nb 03). If you download only one severity set, download this one.

**BRACOL** — 1,747 whole arabica leaves, 5 severity levels, 4 diseases. **Verdict: good second validator** (severity labels, no masks) — use for an OOD ranking check of a severity regressor. Use the whole‑leaf set (§3).

**JMuBEN/JMuBEN2, DiaMOS, CD&S, Apple‑4‑stage** — **Verdict: optional robustness/coverage.** DiaMOS (pear, full‑season severity bands), CD&S (corn, exact severity counts), Apple‑4‑stage (botanist‑graded stages) are each small and crop‑specific; use them to show severity findings aren't coffee‑only. JMuBEN adds coffee volume (5 classes).

### Tier 4 — metadata / knowledge

**LeafNet / LeafBench** — **high value, real.** arXiv:2602.13662 (Feb 2026); 186k images, 22 crops, 62 diseases across 97 classes, **per‑class pathogen type** (43 fungal / 8 bacterial / 2 oomycete / 6 viral / 3 mite) + 13,950 expert QA pairs; HF `enalis/LeafNet`, GitHub `EnalisUs/LeafBench`. **Verdict: the semi‑automatic route to action labels** — join its pathogen field onto PlantVillage/PlantWild class names to derive the harm matrix's pathogen axis instead of hand‑coding all of it. Strongly recommended.

**AgroBench** (ICCV 2025; 203 crops, 682 diseases, 7 task types incl. management) and **CDDM** (ECCV 2024; 137k images + 1M QA on control) — **Verdict: optional** management‑knowledge benchmarks; cite as related work / evaluation targets for the *action* side. CDDM's images live behind external links, not in the repo.

**IP102** (75k images, 102 pest classes, CVPR 2019) — **Verdict: optional OOD** / "vector control" action class. Pests, not diseases — keep it as an out‑of‑distribution probe.

---

## 5 · Gaps, risks, and threats to validity

1. **No native ordinal‑severity dataset at scale.** Mitigated by derive‑then‑validate (PlantSeg → RoCoLe). Report the validation correlation; if weak, that is itself a finding (the Otsu leaf estimate is the bottleneck → motivates a learned segmenter).
2. **Cross‑dataset leakage.** PlantWild/PlantSeg/PlantDoc all draw partly from web image search and may share images. **Any image in both a train and an eval set invalidates the generalization claim.** nb `04` runs perceptual‑hash dedup and reports cross‑dataset collisions; remove them from eval before reporting.
3. **Label noise** (PlantDoc especially) and **partial leaf grouping** (PlantVillage) — both disclosed as threats to validity.
4. **Licensing discipline** (Springer reviewers will check): redistributable = PlantDoc, Plant Ontology (CC BY 4.0); metrics‑only = PlantWild (NC‑ND); non‑commercial = PlantSeg v7 (BY‑NC 4.0); internal‑only = Master (unstated). Any released artifact = **code + label mappings, never images.**
5. **Action‑label subjectivity.** The disease→action mapping is the core contribution and is partly manual; ground it in authoritative sources (EPPO, AGROVOC, UC IPM) and have the mapping reviewed. LeafNet's pathogen field reduces but doesn't eliminate the manual work.

---

## 6 · Recommendation

**Green‑light.** Build on the **minimal viable set** first — it covers all four components and fits the Colab free tier:

| Dataset | Size | Role |
|---|---|---|
| PlantVillage (HF, leaf‑grouped) | ~2–3 GB | training |
| PlantSeg **v7** | ~1.1 GB | severity masks |
| PlantWild | ~3 GB | in‑the‑wild eval + abstention hard cases |
| Cassava | ~6 GB | viral classes for the harm matrix |
| RoCoLe | <2 GB | severity validation (masks + labels) |

Add **LeafNet** (pathogen field → action mapping), **FieldPlant** (annotation‑quality field eval), and **PlantDoc** (redistributable qualitative figures) as the budget allows. Everything else is enhancement.

Execute the corrections in §3, run the leakage/dedup pass (nb 04) before any cross‑dataset number, and the data foundation is sound enough for a Springer CCIS submission. The paper's risk is in **execution and novelty of the evaluation framework**, not in the datasets.

---

*Companion notebooks (`notebooks/00`–`05`) implement download+verify, EDA, severity derivation, severity validation, leakage/dedup/crosswalk, and the baseline "pre‑training" results with the abstention gate and harm‑matrix evaluation. They auto‑detect which datasets are present, so they run on Colab with the full stack and locally on just PlantDoc. All dataset facts above were verified against primary sources on 2026‑07‑28.*
