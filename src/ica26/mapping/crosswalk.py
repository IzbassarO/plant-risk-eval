"""Deterministic label normalization -> mapping-template seed rows.

Turns each dataset's raw class label into a candidate ``canonical_crop`` /
``canonical_disease`` via pure string processing. It DOES NOT invent pathogen
types, actions, or evidence -- those columns stay blank and every row starts
``pending``. The original label is preserved verbatim in ``dataset_class``.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Mapping, Optional, Union

import pandas as pd

from .schema import empty_row, new_template, read_mapping, write_mapping

# Canonical crop vocabulary. Longer/multiword keys first so "bell pepper" wins
# over "pepper". Values are the canonical crop name we emit.
_CROP_ALIASES: list[tuple[str, str]] = [
    ("bell pepper", "pepper"),
    ("bell_pepper", "pepper"),
    ("maize", "corn"),
    ("corn", "corn"),
    ("tomato", "tomato"),
    ("potato", "potato"),
    ("apple", "apple"),
    ("grape", "grape"),
    ("cassava", "cassava"),
    ("coffee", "coffee"),
    ("pepper", "pepper"),
    ("peach", "peach"),
    ("cherry", "cherry"),
    ("strawberry", "strawberry"),
    ("blueberry", "blueberry"),
    ("raspberry", "raspberry"),
    ("soybean", "soybean"),
    ("soy", "soybean"),
    ("squash", "squash"),
    ("orange", "orange"),
    ("pear", "pear"),
    ("rice", "rice"),
    ("wheat", "wheat"),
]

DatasetManifest = Union[str, Path, pd.DataFrame]


def normalize_text(label: str) -> str:
    s = str(label)
    s = s.replace("___", " ").replace("__", " ").replace("_", " ")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_crop(label: str) -> str:
    """Return canonical crop if a known crop word is present, else '' (never guess)."""
    text = normalize_text(label)
    for alias, canon in _CROP_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return canon
    return ""


def normalize_disease(label: str) -> str:
    """Deterministic disease phrase. 'healthy' collapses to 'healthy'.

    Strips a leading crop word and a trailing/embedded 'leaf' token, leaving the
    normalized remainder. Faithful text processing -- not an ontology mapping.
    """
    text = normalize_text(label)
    if "healthy" in text:
        return "healthy"
    crop = normalize_crop(label)
    tokens = text.split()
    # drop the crop alias tokens and generic 'leaf'
    drop = {"leaf"}
    if crop:
        for alias, canon in _CROP_ALIASES:
            if canon == crop:
                drop.update(alias.split())
    remainder = [t for t in tokens if t not in drop]
    return " ".join(remainder).strip() or text


def _load(manifest: DatasetManifest) -> pd.DataFrame:
    if isinstance(manifest, pd.DataFrame):
        return manifest
    return pd.read_csv(manifest, dtype=str, keep_default_na=False)


def build_template_from_manifests(
    manifests: Mapping[str, DatasetManifest],
) -> pd.DataFrame:
    """Build seed rows from {dataset_name -> manifest}. One row per unique class."""
    rows = []
    for ds_name, man in manifests.items():
        df = _load(man)
        if "class_label" not in df.columns:
            continue
        for label in sorted(df["class_label"].astype(str).unique()):
            rows.append(
                empty_row(
                    dataset=ds_name,
                    dataset_class=label,
                    canonical_crop=normalize_crop(label),
                    canonical_disease=normalize_disease(label),
                )
            )
    return new_template(rows)


def merge_preserving_review(new_df: pd.DataFrame, existing_path: str | Path) -> pd.DataFrame:
    """Add only new (dataset, dataset_class) rows; keep existing human-edited rows.

    Protects evidence/review work done in later phases from being clobbered when
    the template is regenerated.
    """
    existing_path = Path(existing_path)
    if not existing_path.exists():
        return new_df
    old = read_mapping(existing_path)
    seen = set(zip(old["dataset"].astype(str), old["dataset_class"].astype(str)))
    add = new_df[
        ~new_df.apply(lambda r: (str(r["dataset"]), str(r["dataset_class"])) in seen, axis=1)
    ]
    merged = pd.concat([old, add], ignore_index=True)
    return merged.sort_values(["dataset", "dataset_class"]).reset_index(drop=True)


def build_and_write(
    manifest_paths: Optional[Mapping[str, DatasetManifest]] = None,
    out_path: str | Path = "data/mapping/action_mapping_template.csv",
    merge: bool = True,
) -> pd.DataFrame:
    if manifest_paths is None:
        manifest_paths = _discover_manifests()
    new_df = build_template_from_manifests(manifest_paths)
    if merge:
        new_df = merge_preserving_review(new_df, out_path)
    write_mapping(new_df, out_path)
    return new_df


def _discover_manifests(base: str | Path = "data/manifests") -> dict[str, DatasetManifest]:
    base = Path(base)
    found: dict[str, DatasetManifest] = {}
    for name, fname in [
        ("PlantDoc", "plantdoc_manifest.csv"),
        ("PlantVillage", "plantvillage_manifest.csv"),
    ]:
        p = base / fname
        if p.exists():
            found[name] = p
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-build-mapping", description="Build the action-mapping template from manifests.")
    ap.add_argument("--out", default="data/mapping/action_mapping_template.csv")
    ap.add_argument("--manifests-dir", default="data/manifests")
    ap.add_argument("--no-merge", action="store_true", help="overwrite instead of merging existing review work")
    args = ap.parse_args(argv)
    manifests = _discover_manifests(args.manifests_dir)
    if not manifests:
        print(f"[build-mapping] no manifests found under {args.manifests_dir} -- run dataset acquisition first.")
        return 2
    df = build_and_write(manifests, args.out, merge=not args.no_merge)
    from .validation import status_counts

    print(f"[build-mapping] datasets={list(manifests)} | rows={len(df)} | statuses={status_counts(df)}")
    print(f"[build-mapping] wrote {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
