# From Diagnosis to Decision — data & analysis

Companion code and dataset assessment for the ICA 2026 submission
*"From Diagnosis to Decision: An Action‑Level and Risk‑Weighted Evaluation
Framework for Deep Learning‑Based Plant Disease Recognition."*

## Research objective

Plant‑disease models are evaluated as classifiers, but they are used as decision
support. This project builds an evaluation framework that scores a model at the
level of the **agronomic action** it implies (fungicide, copper + sanitation,
remove vector, monitor) and weights errors by their **real‑world harm**, rather
than treating every misclassification as equally costly.

## Status — Phase 1, BLOCKED

> **This is unfinished research. Nothing here is a final scientific result.**

| Item | State |
|---|---|
| Data acquisition | ✅ complete — PlantDoc 2,572 imgs / 28 classes, PlantVillage 54,305 imgs / 38 classes, both pinned to an exact upstream revision |
| Cross‑dataset leakage scan | ✅ complete — 0 exact, 16 near‑duplicate pairs (pHash, Hamming ≤ 6) |
| Leakage gate | ⛔ `fail` (fail‑closed) — 16 pairs unresolved |
| Human review of near‑duplicates | ⛔ **not returned** — 0 / 16 decisions recorded |
| Human review of disease→action mapping | ⛔ **not returned** — 0 / 28 approved, all `needs_review` |
| **Dataset V1 freeze** | ⛔ **does not exist** — not built, not frozen |
| Model training / Phase 2 experiments | ⛔ not started |
| Paper results | ⛔ none exist |

**Phase 1 is blocked pending completed human review.** The closeout ran and
stopped correctly at its validation gate; see
[`reports/PHASE1_REVIEW_VALIDATION.md`](reports/PHASE1_REVIEW_VALIDATION.md) for
the 74 blocking findings and the exact human actions required, and
[`reports/PHASE1_CLOSEOUT_PREFLIGHT.md`](reports/PHASE1_CLOSEOUT_PREFLIGHT.md)
for the repository‑state audit.

Re‑check the blocked state at any time (stdlib‑only, deterministic, exit 1 while
blocked):

```bash
python3 scripts/validate_phase1_review.py
```

⚠️ `phase1_return_package.zip` is the **outbound** review packet, not a completed
returned one. It is git‑ignored; its contents are versioned individually.

## Data

**No dataset images are distributed in this repository** — only manifests,
perceptual‑hash indexes, mappings, exclusions, and reports. `data/raw/` is
git‑ignored. See [`DATA_ACCESS.md`](DATA_ACCESS.md) for where to place datasets
locally and how to reproduce them from pinned upstream revisions.

## What's here

| Path | What it is |
|---|---|
| `DATASETS.md` | The acquisition spec (datasets, sources, licenses, known problems). |
| `reports/DATASET_ASSESSMENT.md` | **Read this first.** Per‑dataset suitability verdict, fact‑check vs. primary sources, corrections to make before submission, and the go/no‑go. |
| `DATA_ACCESS.md` | Where datasets go locally, pinned revisions, verification. |
| `scripts/run_phase1_local.py` | One reproducible command for the whole Phase‑1 local pipeline. |
| `scripts/validate_phase1_review.py` | Deterministic validator for the returned human‑review decisions. |
| `src/ica26/` | Package: schemas, dataset acquisition, mapping, leakage gate, evaluation. |
| `notebooks/06_phase1_data_completion_colab.ipynb` | Colab runner for the Phase‑1 data completion. |
| `notebooks/legacy/00`–`05` | Earlier Colab‑first notebooks (download, EDA, severity, leakage, baseline). Superseded by `scripts/`; kept for reference. |
| `data/` | Datasets (git‑ignored). Manifests, indexes, mappings and exclusions **are** versioned. |

## How the notebooks are designed

- **Colab‑first, local‑friendly.** Each notebook detects Colab (mounts Drive) or
  runs locally, and **auto‑detects which datasets are present** — so you can run
  analysis after only the Tier‑1 (or minimal‑viable) subset has downloaded.
- **Two backends in nb 05.** A GPU CNN backend (Colab) and a CPU "smoke" backend
  (colour+texture → linear model) that runs anywhere and exercises the *entire*
  evaluation harness — abstention curve, per‑class F1, harm‑weighted error — on
  whatever is downloaded. Use it to validate the pipeline before spending GPU time.
- **Leak‑safe by construction.** nb 04 builds the PlantVillage leaf‑grouped split
  and flags cross‑dataset near‑duplicates; run it before any cross‑dataset number.

## Quick start

**Locally (current, recommended — no GPU, no credentials):**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[hf,dev]"

python scripts/run_phase1_local.py --status     # inspect state, change nothing
python scripts/run_phase1_local.py --resume     # full Phase-1 pipeline; downloads resume
python3 scripts/validate_phase1_review.py       # review-decision gate (exit 1 while blocked)
python -m pytest -o addopts=-q
```

**On Google Colab (matches the original compute budget):**
1. Put this folder in Google Drive at `MyDrive/diagnosis-to-decision`.
2. Run `notebooks/06_phase1_data_completion_colab.ipynb`.

The `notebooks/legacy/00`–`05` sequence predates `scripts/` and is kept for
reference only; `run_phase1_local.py` supersedes it and is the reproducible path.

## Minimal viable dataset set (covers every experiment)

PlantVillage (leaf‑grouped) · PlantSeg **v7** (`zenodo:17719108`) · PlantWild ·
Cassava · RoCoLe. See `reports/DATASET_ASSESSMENT.md` §6.

## Licensing (state in the paper; never redistribute images)

Redistributable: PlantDoc, Plant Ontology (CC BY 4.0). Metrics‑only: PlantWild
(CC BY‑NC‑ND 4.0). Non‑commercial: PlantSeg v7 (CC BY‑NC 4.0). Internal‑only:
Master Plant Disease (license unstated). Released artifacts = code + label
mappings only.
