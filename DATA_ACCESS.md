# Data access

**No dataset images are distributed in this repository.** Only metadata is
versioned: per-image manifests (path, SHA-256, dimensions, class), perceptual-hash
indexes, class mappings, and exclusion tables. That is enough to verify and
reproduce every Phase-1 result without redistributing a single pixel.

`data/raw/` is git-ignored. Nothing under it is ever committed.

## Where data goes locally

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

## How to acquire it

One reproducible command fetches both sources at their pinned revisions,
rebuilds the manifests, and re-derives the indexes:

```bash
python scripts/run_phase1_local.py --resume        # downloads resume if interrupted
caffeinate -dimsu python scripts/run_phase1_local.py --resume   # macOS, long runs
```

Nothing here requires credentials: both sources are fetched from public URLs
pinned to an exact commit/revision.

| Dataset | Source | Pinned revision | Images | Licence |
|---|---|---|---|---|
| PlantDoc | `github.com/pratikkayal/PlantDoc-Dataset` | `5467f6012d78d1c446145d5f582da6096f852ae8` | 2,572 local (2,578 upstream) | CC BY 4.0 |
| PlantVillage (color) | `huggingface.co/datasets/mohanty/PlantVillage` | `9e97599868962bd0079b8db4b7f1efa9185fa1e7` | 54,305 | CC BY-SA 3.0 |

**Use the Hugging Face source for PlantVillage, not a Kaggle mirror.** The Kaggle
mirrors drop `leaf_id`, which the leaf-grouped split depends on. See `DATASETS.md`.

## Verifying you got the same bytes

Manifests carry a SHA-256 per image, and `reports/leakage_gate.json` binds to the
SHA-256 of the manifests themselves — so a changed dataset invalidates the gate
rather than silently passing:

```bash
python scripts/run_phase1_local.py --steps verify
python3 scripts/validate_phase1_review.py
```

## Licensing note

PlantDoc (CC BY 4.0) and PlantVillage (CC BY-SA 3.0) both permit redistribution
with attribution; this repository nonetheless does not redistribute them, to keep
provenance pointing at the upstream sources and the repository small. Other
datasets named in `DATASETS.md` carry stricter terms (PlantWild CC BY-NC-ND 4.0,
PlantSeg v7 CC BY-NC 4.0) and are metrics-only. Released artifacts are **code and
label mappings only**.
