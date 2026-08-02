"""PlantVillage acquisition from the authoritative Hugging Face source.

Source (per DATASETS.md / brief): ``mohanty/PlantVillage`` -- the ONLY copy that
carries ``leaf_id`` for leak-safe leaf-grouped splitting. Kaggle mirrors are
forbidden (they drop leaf_id).

This module is Colab-first: it requires the optional ``datasets`` dependency
(``pip install ica26[hf]``). If ``datasets`` is unavailable it FAILS LOUDLY with
an actionable message rather than silently degrading. It never manufactures a
leaf_id for images that lack one; it reports how many are missing.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from ..schemas import (
    IMAGE_MANIFEST_COLUMNS,
    PLANTVILLAGE_EXTRA_COLUMNS,
    PLANTVILLAGE_SOURCE,
)
from . import manifest as M

HF_REPO = "mohanty/PlantVillage"
SUPPORTED_CONFIGS = ("color", "segmented", "grayscale")


class DatasetsNotInstalled(RuntimeError):
    pass


def _require_datasets():
    try:
        import datasets  # noqa: F401
    except Exception as e:  # fail loudly, actionably
        raise DatasetsNotInstalled(
            "The 'datasets' package is required for PlantVillage acquisition. "
            "Install it with:  pip install 'ica26[hf]'   (or  pip install datasets huggingface_hub). "
            "PlantVillage MUST come from the Hugging Face repo "
            f"'{HF_REPO}' (Kaggle mirrors lack leaf_id and are forbidden)."
        ) from e
    import datasets

    return datasets


def load_hf(config: str = "color", streaming: bool = False):
    """Load the PlantVillage HF dataset for a given config. Colab/HF only."""
    if config not in SUPPORTED_CONFIGS:
        raise ValueError(f"config must be one of {SUPPORTED_CONFIGS}, got {config!r}")
    datasets = _require_datasets()
    return datasets.load_dataset(HF_REPO, config, streaming=streaming)


def hf_revision(repo: str = HF_REPO) -> Optional[str]:
    """Return the exact HF dataset commit SHA (source revision), or None."""
    try:
        from huggingface_hub import HfApi
        info = HfApi().dataset_info(repo)
        return info.sha
    except Exception:
        return None


def build_source_snapshot(config: str, revision: Optional[str], execution_mode: str,
                          disk_bytes: int = 0, seconds: float = 0.0) -> dict:
    return {
        "dataset": "PlantVillage",
        "hf_repo": HF_REPO,
        "config": config,
        "revision": revision or "unknown",
        "execution_mode": execution_mode,   # "streaming-sample" | "full" | "not-executed"
        "retrieved_at_utc": M.utc_now_iso(),
        "disk_bytes": int(disk_bytes),
        "execution_seconds": round(float(seconds), 1),
        "license": PLANTVILLAGE_SOURCE.license,
        "source_of_truth_note": "Kaggle mirrors are forbidden (they drop leaf_id).",
    }


def _content_hash_and_size(pil_img) -> tuple[str, int]:
    raw = pil_img.tobytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _row_from_example(ex, config, split, label_names, has_leaf_field, stamp, idx, materialize) -> dict:
    img = ex["image"]
    label_idx = ex["label"]
    label = label_names[label_idx] if label_names else str(label_idx)
    leaf_id = ex.get("leaf_id") if has_leaf_field else None
    has_leaf = leaf_id is not None and str(leaf_id) not in ("", "-1")
    sha, nbytes = _content_hash_and_size(img)
    relpath = f"{config}/{split}/{label}/{idx}.png"
    if materialize is not None:
        out = materialize / relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
    return {
        "dataset": "PlantVillage", "split": split, "class_label": label, "relpath": relpath,
        "sha256": sha, "width": int(img.size[0]), "height": int(img.size[1]),
        "mode": str(img.mode), "n_bytes": nbytes, "is_corrupt": False,
        "source_url": PLANTVILLAGE_SOURCE.url, "acquired_at_utc": stamp,
        "leaf_id": "" if leaf_id is None else str(leaf_id), "has_leaf_id": bool(has_leaf),
    }


def build_manifest_from_hf(
    config: str = "color",
    limit: Optional[int] = None,
    materialize_dir: Optional[str | Path] = None,
    acquired_at_utc: Optional[str] = None,
    streaming: bool = False,
) -> pd.DataFrame:
    """Iterate the HF dataset and build a per-image manifest.

    Records leaf_id + has_leaf_id for every image (never fabricated). sha256 is
    over the decoded pixel bytes (HF serves decoded PIL images). ``streaming=True``
    fetches examples lazily so a real sample can be acquired without the full
    multi-GB download.
    """
    ds = load_hf(config, streaming=streaming)
    stamp = acquired_at_utc or M.utc_now_iso()
    rows: list[dict] = []
    materialize = Path(materialize_dir) if materialize_dir else None

    for split in ds:
        d = ds[split]
        feats = getattr(d, "features", None)
        label_feat = feats.get("label") if feats else None
        label_names = getattr(label_feat, "names", None) if label_feat is not None else None
        has_leaf_field = bool(feats and ("leaf_id" in feats))
        if streaming:
            count = 0
            for ex in d:
                if limit is not None and count >= limit:
                    break
                rows.append(_row_from_example(ex, config, split, label_names, has_leaf_field, stamp, count, materialize))
                count += 1
        else:
            n = len(d) if limit is None else min(limit, len(d))
            for i in range(n):
                rows.append(_row_from_example(d[i], config, split, label_names, has_leaf_field, stamp, i, materialize))
    cols = list(IMAGE_MANIFEST_COLUMNS) + list(PLANTVILLAGE_EXTRA_COLUMNS)
    df = pd.DataFrame(rows, columns=cols)
    if len(df):
        df = df.sort_values(["split", "class_label", "relpath"]).reset_index(drop=True)
    return df


LEAF_MAP_PATH = "leaf_grouping/leaf-map.json"


def _leaf_tag(relpath: str) -> str:
    stem = relpath.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stem.split("___", 1)[1].strip() if "___" in stem else ""


def build_manifest_from_repo(
    config: str = "color",
    images_root: Optional[str | Path] = None,
    acquired_at_utc: Optional[str] = None,
) -> tuple[pd.DataFrame, dict]:
    """Build a manifest from the AUTHORITATIVE repo files (splits/*.txt +
    leaf-map.json), since `datasets` 4.0+ no longer runs the repo's loading
    script. leaf_id per image comes from the filename tag; has_leaf_id is True
    iff that tag is present in leaf-map.json (the authors' explicit grouping).
    If ``images_root`` (an extracted data.zip) is given, pixel fields are filled.
    """
    from huggingface_hub import hf_hub_download

    tr = [l.strip() for l in open(hf_hub_download(HF_REPO, f"splits/{config}_train.txt", repo_type="dataset")) if l.strip()]
    te = [l.strip() for l in open(hf_hub_download(HF_REPO, f"splits/{config}_test.txt", repo_type="dataset")) if l.strip()]
    import json
    lmap = json.load(open(hf_hub_download(HF_REPO, LEAF_MAP_PATH, repo_type="dataset")))
    leafkeys = {str(k).strip().lower() for k in lmap}
    stamp = acquired_at_utc or M.utc_now_iso()
    images_root = Path(images_root) if images_root else None

    rows = []
    for split, paths in [("train", tr), ("test", te)]:
        for rel in paths:
            parts = rel.split("/")
            cls = parts[-2] if len(parts) >= 2 else "?"
            tag = _leaf_tag(rel)
            has_leaf = bool(tag) and (tag.lower() in leafkeys)
            row = {
                "dataset": "PlantVillage", "split": split, "class_label": cls, "relpath": rel,
                "sha256": "", "width": "", "height": "", "mode": "", "n_bytes": "",
                "is_corrupt": "", "source_url": PLANTVILLAGE_SOURCE.url, "acquired_at_utc": stamp,
                "leaf_id": tag, "has_leaf_id": bool(has_leaf),
            }
            if images_root is not None:
                ap = images_root / rel
                if ap.exists():
                    w, h, mode, corrupt = M.read_image_meta(ap)
                    row.update(sha256=M.sha256_of_file(ap), width=w, height=h, mode=mode,
                               n_bytes=ap.stat().st_size, is_corrupt=corrupt)
            rows.append(row)
    cols = list(IMAGE_MANIFEST_COLUMNS) + list(PLANTVILLAGE_EXTRA_COLUMNS)
    df = pd.DataFrame(rows, columns=cols).sort_values(["split", "class_label", "relpath"]).reset_index(drop=True)
    return df, {"leaf_map_entries": len(lmap)}


def repo_summary(df: pd.DataFrame, config: str, leaf_map_entries: int, snapshot: dict) -> dict:
    n = int(len(df))
    per_split = {str(s): {"n_images": int(len(g)), "n_classes": int(g["class_label"].nunique())}
                 for s, g in df.groupby("split")}
    n_with = int(df["has_leaf_id"].sum()) if n else 0
    n_without = n - n_with
    pixels = bool(df["sha256"].astype(str).str.len().gt(0).any()) if n else False
    return {
        "dataset": "PlantVillage", "config": config, "hf_repo": HF_REPO,
        "n_images": n, "n_classes_total": int(df["class_label"].nunique()) if n else 0,
        "n_healthy_classes": int(sum("healthy" in c.lower() for c in df["class_label"].unique())) if n else 0,
        "per_split": per_split,
        "leaf_id": {
            "n_with_leaf_id": n_with, "n_without_leaf_id": n_without,
            "proportion_with_leaf_id": round(n_with / n, 4) if n else 0.0,
            "leaf_map_entries": leaf_map_entries,
            "grouped_split_readiness": "ready",  # authors ship leaf-grouped split files
            "note": "Leaf-grouped train/test split files are provided by the dataset authors; "
                    "leaf-map.json explicitly groups the images with a leaf tag.",
        },
        "pixels_materialized": pixels,
        "pixel_note": "" if pixels else "sha256/width/height pending until data.zip images are materialized.",
        "license": PLANTVILLAGE_SOURCE.license,
        "source_snapshot": snapshot,
    }


def acquire_from_repo(
    config: str = "color",
    images_root: Optional[str | Path] = None,
    manifest_csv: str | Path = "data/manifests/plantvillage_manifest.csv",
    summary_json: str | Path = "data/manifests/plantvillage_summary.json",
    snapshot_json: str | Path = "data/manifests/plantvillage_source_snapshot.json",
) -> dict:
    import time
    rev = hf_revision()
    t0 = time.perf_counter()
    df, meta = build_manifest_from_repo(config=config, images_root=images_root)
    secs = time.perf_counter() - t0
    M.write_manifest(df, manifest_csv)
    pixels = bool(df["sha256"].astype(str).str.len().gt(0).any()) if len(df) else False
    mode = "repo-files+pixels" if pixels else "repo-files-structural"
    snapshot = build_source_snapshot(config, rev, mode, seconds=secs)
    summary = repo_summary(df, config, meta["leaf_map_entries"], snapshot)
    summary["execution"] = {"mode": mode, "n_images": int(len(df)), "seconds": round(secs, 1)}
    M.write_summary(summary, summary_json)
    M.write_summary(snapshot, snapshot_json)
    return {"manifest": df, "summary": summary, "snapshot": snapshot}


def summarize(df: pd.DataFrame, config: str) -> dict:
    s = M.manifest_summary(df, "PlantVillage")
    n = int(len(df))
    n_with = int(df["has_leaf_id"].sum()) if n else 0
    n_without = n - n_with
    prop_with = (n_with / n) if n else 0.0
    if n == 0:
        readiness = "unavailable"
    elif prop_with >= 0.999:
        readiness = "ready"  # fully leaf-resolved -> fully leak-safe grouping
    elif prop_with > 0.0:
        readiness = "partial"  # some images lack leaf_id (see brief: PV maps only ~41,112/54,306)
    else:
        readiness = "no_grouping"
    s["config"] = config
    s["leaf_id"] = {
        "n_with_leaf_id": n_with,
        "n_without_leaf_id": n_without,
        "proportion_with_leaf_id": round(prop_with, 4),
        "grouped_split_readiness": readiness,
    }
    s["license"] = PLANTVILLAGE_SOURCE.license
    s["hf_repo"] = HF_REPO
    return s


def acquire(
    config: str = "color",
    manifest_csv: str | Path = "data/manifests/plantvillage_manifest.csv",
    summary_json: str | Path = "data/manifests/plantvillage_summary.json",
    snapshot_json: str | Path = "data/manifests/plantvillage_source_snapshot.json",
    limit: Optional[int] = None,
    materialize_dir: Optional[str | Path] = None,
    streaming: bool = False,
) -> dict:
    import time

    rev = hf_revision()
    t0 = time.perf_counter()
    df = build_manifest_from_hf(config=config, limit=limit,
                                materialize_dir=materialize_dir, streaming=streaming)
    secs = time.perf_counter() - t0
    M.write_manifest(df, manifest_csv)
    summary = summarize(df, config)
    disk = int(pd.to_numeric(df["n_bytes"], errors="coerce").fillna(0).sum()) if len(df) else 0
    mode = "streaming-sample" if streaming else "full"
    snapshot = build_source_snapshot(config, rev, mode, disk_bytes=disk, seconds=secs)
    summary["source_snapshot"] = snapshot
    summary["execution"] = {"mode": mode, "limit": limit, "n_images": int(len(df)),
                            "seconds": round(secs, 1)}
    M.write_summary(summary, summary_json)
    M.write_summary(snapshot, snapshot_json)
    return {"manifest": df, "summary": summary, "snapshot": snapshot}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-plantvillage", description="Acquire PlantVillage (HF) + manifest.")
    ap.add_argument("--config", default="color", choices=SUPPORTED_CONFIGS)
    ap.add_argument("--manifest", default="data/manifests/plantvillage_manifest.csv")
    ap.add_argument("--summary", default="data/manifests/plantvillage_summary.json")
    ap.add_argument("--snapshot", default="data/manifests/plantvillage_source_snapshot.json")
    ap.add_argument("--limit", type=int, default=None, help="cap #images (sample/dry-run)")
    ap.add_argument("--stream", action="store_true", help="stream examples (real sample without full download)")
    ap.add_argument("--materialize", default=None, help="also save images under this dir")
    args = ap.parse_args(argv)
    try:
        out = acquire(
            config=args.config, manifest_csv=args.manifest, summary_json=args.summary,
            snapshot_json=args.snapshot, limit=args.limit,
            materialize_dir=args.materialize, streaming=args.stream,
        )
    except DatasetsNotInstalled as e:
        print("[plantvillage] BLOCKED:", e)
        return 2
    df, summary = out["manifest"], out["summary"]
    print(f"[plantvillage] {len(df)} images ({args.config}, mode={summary['execution']['mode']}) "
          f"| revision={summary['source_snapshot']['revision']}")
    print(f"[plantvillage] leaf_id: {summary['leaf_id']}")
    print(f"[plantvillage] wrote {args.manifest}, {args.summary}, {args.snapshot}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
