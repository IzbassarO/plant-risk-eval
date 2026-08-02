"""Per-image manifest construction: hashing, metadata, corruption, validation.

Deterministic and dataset-agnostic. PlantDoc and PlantVillage modules build on
these helpers so every manifest shares one schema and one notion of "corrupt".
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from PIL import Image, ImageFile

from ..schemas import (
    IMAGE_EXTENSIONS,
    IMAGE_MANIFEST_COLUMNS,
    ValidationResult,
)

# We want to DETECT truncation, not silently tolerate it.
ImageFile.LOAD_TRUNCATED_IMAGES = False


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def read_image_meta(path: str | Path) -> tuple[Optional[int], Optional[int], Optional[str], bool]:
    """Return (width, height, mode, is_corrupt).

    ``is_corrupt`` is True if PIL cannot verify+open the file (truncated,
    unreadable, or not an image). Never raises.
    """
    try:
        with Image.open(path) as im:
            im.verify()  # cheap integrity check
        with Image.open(path) as im:
            w, h = im.size
            mode = im.mode
        return int(w), int(h), str(mode), False
    except Exception:
        return None, None, None, True


def iter_image_files(root: str | Path) -> Iterable[Path]:
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
            yield p


def image_record(
    *,
    abs_path: str | Path,
    root: str | Path,
    dataset: str,
    split: str,
    class_label: str,
    source_url: str,
    acquired_at_utc: Optional[str] = None,
) -> dict:
    """Build one manifest row (dict keyed by IMAGE_MANIFEST_COLUMNS)."""
    abs_path = Path(abs_path)
    root = Path(root)
    w, h, mode, corrupt = read_image_meta(abs_path)
    return {
        "dataset": dataset,
        "split": split,
        "class_label": class_label,
        "relpath": str(abs_path.relative_to(root)),
        "sha256": sha256_of_file(abs_path),
        "width": w,
        "height": h,
        "mode": mode,
        "n_bytes": abs_path.stat().st_size,
        "is_corrupt": corrupt,
        "source_url": source_url,
        "acquired_at_utc": acquired_at_utc or utc_now_iso(),
    }


def build_split_class_manifest(
    *,
    root: str | Path,
    dataset: str,
    source_url: str,
    split_dirs: Iterable[str],
    acquired_at_utc: Optional[str] = None,
    extra_columns: Iterable[str] = (),
) -> pd.DataFrame:
    """Scan ``root/<split>/<class>/<img>`` and return a manifest DataFrame.

    ``no silent skipped files``: every image file under each split/class is
    recorded, including corrupt ones (flagged, not dropped).
    """
    root = Path(root)
    stamp = acquired_at_utc or utc_now_iso()
    rows: list[dict] = []
    for split in split_dirs:
        split_root = root / split
        if not split_root.exists():
            continue
        for class_dir in sorted(p for p in split_root.iterdir() if p.is_dir()):
            for img in sorted(class_dir.iterdir()):
                if not img.is_file() or img.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                rec = image_record(
                    abs_path=img,
                    root=root,
                    dataset=dataset,
                    split=split,
                    class_label=class_dir.name,
                    source_url=source_url,
                    acquired_at_utc=stamp,
                )
                for c in extra_columns:
                    rec.setdefault(c, "")
                rows.append(rec)
    cols = list(IMAGE_MANIFEST_COLUMNS) + [c for c in extra_columns if c not in IMAGE_MANIFEST_COLUMNS]
    df = pd.DataFrame(rows, columns=cols)
    # deterministic ordering
    if len(df):
        df = df.sort_values(["split", "class_label", "relpath"]).reset_index(drop=True)
    return df


def find_duplicate_paths(df: pd.DataFrame) -> list[str]:
    """Return relpaths that appear more than once in the manifest."""
    if "relpath" not in df.columns or not len(df):
        return []
    vc = df["relpath"].value_counts()
    return sorted(vc[vc > 1].index.tolist())


def validate_manifest(df: pd.DataFrame) -> ValidationResult:
    """Structural checks: required columns, duplicate paths, corrupt reporting."""
    res = ValidationResult()
    for col in IMAGE_MANIFEST_COLUMNS:
        if col not in df.columns:
            res.add("error", col, f"missing required manifest column '{col}'")
    if not res.ok:
        return res
    dups = find_duplicate_paths(df)
    for d in dups:
        res.add("error", d, "duplicate relpath in manifest")
    n_corrupt = int(df["is_corrupt"].sum()) if "is_corrupt" in df.columns else 0
    if n_corrupt:
        res.add("warning", "is_corrupt", f"{n_corrupt} corrupt/unreadable image(s) flagged")
    # sha256 sanity
    bad_hash = df["sha256"].astype(str).map(lambda s: len(s) != 64).sum()
    if bad_hash:
        res.add("error", "sha256", f"{int(bad_hash)} row(s) with malformed sha256")
    return res


def manifest_summary(df: pd.DataFrame, dataset: str) -> dict:
    """Aggregate counts for a *_summary.json file."""
    if not len(df):
        return {"dataset": dataset, "n_images": 0, "empty": True}
    by_split = df.groupby("split")
    per_split = {}
    for split, g in by_split:
        per_split[str(split)] = {
            "n_images": int(len(g)),
            "n_classes": int(g["class_label"].nunique()),
            "classes": sorted(g["class_label"].unique().tolist()),
            "n_corrupt": int(g["is_corrupt"].sum()),
        }
    summary = {
        "dataset": dataset,
        "generated_at_utc": utc_now_iso(),
        "n_images": int(len(df)),
        "n_classes_total": int(df["class_label"].nunique()),
        "n_corrupt_total": int(df["is_corrupt"].sum()),
        "duplicate_relpaths": find_duplicate_paths(df),
        "resolution": {
            "median_width": _safe_median(df["width"]),
            "median_height": _safe_median(df["height"]),
        },
        "modes": df["mode"].value_counts(dropna=False).to_dict(),
        "per_split": per_split,
        "source_url": df["source_url"].iloc[0] if "source_url" in df.columns else "",
    }
    # keys of value_counts may be NaN/None -> stringify for JSON safety
    summary["modes"] = {str(k): int(v) for k, v in summary["modes"].items()}
    return summary


def _safe_median(s: pd.Series):
    vals = pd.to_numeric(s, errors="coerce").dropna()
    return float(vals.median()) if len(vals) else None


def write_manifest(df: pd.DataFrame, csv_path: str | Path) -> Path:
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    return csv_path


def write_summary(summary: dict, json_path: str | Path) -> Path:
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=False))
    return json_path
