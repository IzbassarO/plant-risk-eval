"""Schema + IO for the disease-to-action mapping table.

The table is the human-curated bridge from a dataset's disease label to one of
the four action classes. This module defines its shape and safe defaults; it
never fills in scientific content (pathogen type, action, evidence).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from ..schemas import (
    ACTION_CLASSES,
    MAPPING_COLUMNS,
    MAPPING_CONFIDENCES,
    REVIEW_STATUSES,
)

# Re-export for convenience.
__all__ = [
    "ACTION_CLASSES",
    "MAPPING_COLUMNS",
    "MAPPING_CONFIDENCES",
    "REVIEW_STATUSES",
    "empty_row",
    "new_template",
    "read_mapping",
    "write_mapping",
]


def empty_row(
    *,
    dataset: str,
    dataset_class: str,
    canonical_crop: str = "",
    canonical_disease: str = "",
) -> dict:
    """A fresh, unreviewed mapping row. Evidence fields are intentionally blank.

    Defaults: ``review_status='pending'`` and ``mapping_confidence='low'`` so a
    row can never be born approved.
    """
    row = {c: "" for c in MAPPING_COLUMNS}
    row["dataset"] = dataset
    row["dataset_class"] = dataset_class  # ORIGINAL label, preserved verbatim
    row["canonical_crop"] = canonical_crop
    row["canonical_disease"] = canonical_disease
    row["mapping_confidence"] = "low"
    row["review_status"] = "pending"
    return row


def new_template(rows: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows), columns=list(MAPPING_COLUMNS))
    if len(df):
        df = df.sort_values(["dataset", "dataset_class"]).reset_index(drop=True)
    return df


def read_mapping(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")
    # ensure all columns exist (tolerate extra, order canonical columns first)
    for c in MAPPING_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    ordered = list(MAPPING_COLUMNS) + [c for c in df.columns if c not in MAPPING_COLUMNS]
    return df[ordered]


def write_mapping(df: pd.DataFrame, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for c in MAPPING_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[list(MAPPING_COLUMNS)]
    out.to_csv(path, index=False)
    return path
