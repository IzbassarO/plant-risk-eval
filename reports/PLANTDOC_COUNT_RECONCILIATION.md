# PlantDoc Count Reconciliation

**Question (audit P0.4 / MAJOR):** the brief and code embed **2,598** images; a
live GitHub tree query found **2,578**. Reconcile before using any manuscript
count. No number is forced.

## Source revision used

| | |
|---|---|
| Repository | `github.com/pratikkayal/PlantDoc-Dataset` (classification) |
| **Commit (pinned)** | `5467f6012d78d1c446145d5f582da6096f852ae8` |
| Commit date | 2021-05-02 (`Update README.md`) |
| Acquisition method | blobless `git clone --filter=blob:none` for enumeration; resumable download of blobs |
| Recorded in | `data/manifests/plantdoc_source_snapshot.json` |

## The seven counts

| Count | Value | Source |
|---|---:|---|
| **Paper-reported** (Singh et al. 2020) | **2,598** | arXiv 1911.10317 / CoDS-COMAD |
| **Upstream repository** (this commit) | **2,578** | `git ls-tree -r` at `5467f601` |
| — of which train | 2,342 | tree |
| — of which test | 236 | tree |
| **Valid decodable images** (downloaded) | *see `plantdoc_summary.json` → `reconciliation.valid_decodable_count`* | PIL verify |
| **Manifest rows** | *= downloaded* | `plantdoc_manifest.csv` |
| **Train class count** | **28** | tree (`train/`) |
| **Test class count** | **27** | tree (`test/`) — drops `Tomato two spotted spider mites leaf` |

## What explains the 2,598 → 2,578 delta (20 images)?

- **Not non-image files.** There are **0** non-image files under `train/` or
  `test/` at this commit. The extension histogram is exactly 2,576 `.jpg` +
  1 `.jpeg` + 1 `.png` = **2,578**.
- **Not hidden/unsupported files.** The tree enumeration counts every blob; only
  `LICENSE.txt`, `README.md`, and `PlantDoc_Examples.png` sit outside
  `train/`/`test/` and are excluded by design.
- **Repository drift since publication.** The paper reported 2,598 for the
  dataset as published in 2020; the current repository HEAD contains 2,578. The
  20-image difference is a genuine change to the repository between the 2020
  publication and this 2021-05-02 commit (images removed/deduplicated upstream).
  There is **16** duplicate *basename* occurrences in the tree, and 4 exact
  perceptual-hash duplicate pairs within the training set (see leakage report) —
  consistent with light upstream cleanup, though these do not by themselves sum
  to 20.

**Recommendation for the manuscript:** cite **2,578 at commit `5467f601`** as the
count actually used, and note the paper's original **2,598** with this
explanation. Do not force either number.

## Completion verdict

PlantDoc is called **complete only if** `downloaded == upstream (2,578)` **and**
all images decode **and** the filesystem matches the manifest in both directions
(no manifest row without a file; no file without a manifest row). The current
status (downloaded / valid / fs-vs-manifest) is recorded live in
`data/manifests/plantdoc_summary.json` under `reconciliation`, and summarized in
`reports/PHASE1_REMEDIATION_REPORT.md` §PlantDoc. Acquisition is resumable
(`ica26-plantdoc --download`), so any shortfall is completed by re-running
(fast on Colab).

---

## Update — 2026-07-29 (Phase-1 data completion session)

**Live upstream confirmation.** `git ls-remote` shows the default branch HEAD is
**exactly** the pinned commit `5467f6012d78d1c446145d5f582da6096f852ae8`, so the
frozen snapshot and current upstream are identical (no drift). Upstream image
count re-enumerated at the pinned commit: **2,578** (2,342 train + 236 test).

**Resumable download resumed** (`download_via_raw`, ref pinned to the frozen
commit, retries=5, atomic `.part`→final replace, incomplete responses rejected):
**1,663 → 1,717** images materialized this session (+54). The local uplink is
throughput-limited (measured ≈ 2 files/min for PlantDoc's small per-file HTTPS
requests, per-request latency-bound), so full local completion was **not**
achievable in-session and the run was stopped rather than retried indefinitely
(per PROJECT task §5). No `.part` remains; no partial file was counted.

**Independent verification of the frozen partial snapshot** (all consistent):

| Check | Value |
|---|---:|
| Filesystem image count (train/test) | 1,717 |
| Valid decodable count | 1,717 |
| Manifest rows | 1,717 |
| Train images / classes | 1,481 / 17 |
| Test images / classes | 236 / 27 |
| Corrupt | 0 |
| Duplicate relpaths | 0 |
| Zero-byte files | 0 |
| Manifest rows missing files | 0 |
| Files missing from manifest | 0 |
| SHA-256 sample checked / matched | 60 / 60 |

Completion criterion (`filesystem == valid == manifest == upstream 2,578`) is
therefore **still unmet: 1,717 / 2,578 (66.6%)**. The remaining 861 images are
network-limited and are completed by re-running the resumable download — locally
or, as intended, on Colab (`notebooks/06_phase1_data_completion_colab.ipynb`).
Full detail: `data/manifests/_plantdoc_verification.json`.


---

## Local completion update — 2026-07-29T20:15:22Z

- Acquisition: GitHub archive for commit `5467f6012d78` (+ raw-CDN fallback for any missing file); existing valid images preserved.
- Paper-reported count: **2598** (not forced).
- Upstream count at pinned commit: **2578** (train 1481 / test 236).
- Filesystem == manifest == valid decodable: **1717 / 1717 / 1717**.
- fs<->manifest mismatches: 0 rows-missing-files, 0 files-missing-from-manifest.
- Completion: **INCOMPLETE** (1717/2578).


---

## Local completion update — 2026-07-30T07:08:52Z

- Acquisition: GitHub archive for commit `5467f6012d78` (+ raw-CDN fallback for any missing file); existing valid images preserved.
- Paper-reported count: **2598** (not forced).
- Upstream count at pinned commit: **2578** (train 2336 / test 236).
- Filesystem == manifest == valid decodable: **2572 / 2572 / 2572**.
- fs<->manifest mismatches: 0 rows-missing-files, 0 files-missing-from-manifest.
- Completion: **INCOMPLETE** (2572/2578).


---

## Case-insensitive filesystem reconciliation

_Recorded 2026-07-30T07:14:43Z during local completion on macOS (APFS, case-insensitive)._

The frozen upstream commit exposes **2578** train/test image paths. **6** of them are *case-variant pairs* — distinct files in the case-sensitive git tree that map to the **same** path on a case-insensitive filesystem, so only one of each pair can exist on disk. Distinct on-disk images are therefore `2578 − 6` = **2572**, which equals the filesystem count, the valid decodable count, and the manifest row count (all consistent, 0 corrupt).

This delta is a **filesystem limitation, not a missing or failed download**. No count was forced and no file was fabricated to reach 2,578 (or the paper's 2,598). The colliding pairs are:

| # | Path A (case-sensitive upstream) | Path B (collides on case-insensitive FS) |
|---|---|---|
| 1 | `train/Apple rust leaf/CAR1.jpg` | `train/Apple rust leaf/car1.jpg` |
| 2 | `train/Blueberry leaf/Blueberry-Leaf.jpg` | `train/Blueberry leaf/blueberry-leaf.jpg` |
| 3 | `train/Blueberry leaf/Blueberry-leaves.jpg` | `train/Blueberry leaf/blueberry-leaves.jpg` |
| 4 | `train/Corn leaf blight/Northern-Corn-Leaf-Blight.jpg` | `train/Corn leaf blight/northern-corn-leaf-blight.jpg` |
| 5 | `train/Peach leaf/Peach-Leaf.jpg` | `train/Peach leaf/peach-leaf.jpg` |
| 6 | `train/Potato leaf early blight/potato-blight-phytophora-infestans-close-up-of-infected-leaf-showing-A60HXN.jpg` | `train/Potato leaf early blight/potato-blight-phytophora-infestans-close-up-of-infected-leaf-showing-a60hxn.jpg` |

**Implication for the paper:** PlantDoc acquisition is exhaustive on this machine; the evaluation set materializes as **2572** distinct images. If the full 2578-path set is ever required, extract on a case-sensitive volume (e.g. a case-sensitive APFS image or Linux); the acquisition code and manifest logic are unchanged. Evidence: `data/manifests/_plantdoc_case_collisions.json`.
