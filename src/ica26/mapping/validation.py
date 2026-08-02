"""Validation for the disease-to-action mapping table.

Central rule (the evidence gate): a row may be ``approved`` ONLY if it carries
verifiable evidence in every required field. Anything else must remain
``pending``/``needs_review``. Unknown or forbidden action classes are rejected.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from ..schemas import (
    ACTION_CLASSES,
    EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL,
    FORBIDDEN_ACTION_CLASSES,
    MAPPING_COLUMNS,
    MAPPING_CONFIDENCES,
    PATHOGEN_TYPES,
    REVIEW_STATUSES,
    ValidationResult,
)
from .schema import read_mapping


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def validate_mapping(df: pd.DataFrame) -> ValidationResult:
    """Validate a mapping DataFrame. Returns a ValidationResult (truthy == ok)."""
    res = ValidationResult()

    for col in MAPPING_COLUMNS:
        if col not in df.columns:
            res.add("error", col, f"missing required column '{col}'")
    if not res.ok:
        return res

    for idx, row in df.iterrows():
        where = f"row {idx} ({row.get('dataset','?')}/{row.get('dataset_class','?')})"

        # Original label must be preserved.
        if _blank(row["dataset_class"]):
            res.add("error", where, "dataset_class (original label) is empty")

        # review_status enum
        status = str(row["review_status"]).strip()
        if status not in REVIEW_STATUSES:
            res.add("error", where, f"invalid review_status '{status}' (allowed: {REVIEW_STATUSES})")

        # mapping_confidence enum
        conf = str(row["mapping_confidence"]).strip()
        if conf not in MAPPING_CONFIDENCES:
            res.add("error", where, f"invalid mapping_confidence '{conf}' (allowed: {MAPPING_CONFIDENCES})")

        # action_class: forbidden always rejected; if present must be valid
        action = str(row["action_class"]).strip()
        if action in FORBIDDEN_ACTION_CLASSES:
            res.add("error", where, f"forbidden action_class '{action}'")
        elif not _blank(action) and action not in ACTION_CLASSES:
            res.add("error", where, f"unknown action_class '{action}' (allowed: {ACTION_CLASSES})")

        # pathogen_type: if present must be recognised (catches typos; never auto-filled)
        ptype = str(row["pathogen_type"]).strip()
        if not _blank(ptype) and ptype not in PATHOGEN_TYPES:
            res.add("error", where, f"unrecognised pathogen_type '{ptype}' (allowed: {PATHOGEN_TYPES})")

        # THE EVIDENCE GATE
        if status == "approved":
            if _blank(action) or action not in ACTION_CLASSES:
                res.add("error", where, "approved row must have a valid action_class")
            for fld in EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL:
                if _blank(row.get(fld)):
                    res.add("error", where, f"approved row missing required evidence field '{fld}'")

    return res


def assert_valid(df: pd.DataFrame) -> None:
    res = validate_mapping(df)
    if not res.ok:
        msgs = "\n".join(f"  - [{i.level}] {i.where}: {i.message}" for i in res.errors)
        raise ValueError(f"mapping validation failed ({res.summary()}):\n{msgs}")


def approved_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Return only rows that are approved AND pass validation (evidence present)."""
    ok_rows = []
    for idx, row in df.iterrows():
        if str(row["review_status"]).strip() != "approved":
            continue
        single = validate_mapping(df.loc[[idx]])
        if single.ok:
            ok_rows.append(idx)
    return df.loc[ok_rows].copy()


def action_lookup(df: pd.DataFrame, require_approved: bool = True) -> dict[tuple[str, str], str]:
    """Build a {(dataset, dataset_class) -> action_class} lookup.

    By default only APPROVED, evidence-backed rows are included, so evaluation
    never projects a disease through an unverified mapping.
    """
    src = approved_mapping(df) if require_approved else df
    lut: dict[tuple[str, str], str] = {}
    for _, row in src.iterrows():
        action = str(row["action_class"]).strip()
        if action in ACTION_CLASSES:
            lut[(str(row["dataset"]).strip(), str(row["dataset_class"]).strip())] = action
    return lut


class NoApprovedMappingError(RuntimeError):
    """Raised when action evaluation is attempted with no approved mappings."""


def require_approved_lookup(df: pd.DataFrame) -> dict[tuple[str, str], str]:
    """Return the approved lookup, or raise if it is empty.

    This is the **hard stop**: no disease label may be projected to an action
    until at least one mapping row is human-approved with evidence. An empty
    approved lookup blocks action-level evaluation by design.
    """
    lut = action_lookup(df, require_approved=True)
    if not lut:
        raise NoApprovedMappingError(
            "No approved disease->action mappings found. Action-level evaluation "
            "is blocked until at least one row has review_status=approved with "
            "complete evidence. This is a deliberate fail-closed guard."
        )
    return lut


def status_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = {s: 0 for s in REVIEW_STATUSES}
    for v in df["review_status"].astype(str).str.strip():
        if v in counts:
            counts[v] += 1
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-validate-mapping", description="Validate a disease-to-action mapping CSV.")
    ap.add_argument("mapping_csv", nargs="?", default="data/mapping/action_mapping_template.csv")
    args = ap.parse_args(argv)
    path = Path(args.mapping_csv)
    if not path.exists():
        print(f"[validate-mapping] file not found: {path}")
        return 2
    df = read_mapping(path)
    res = validate_mapping(df)
    counts = status_counts(df)
    print(f"[validate-mapping] {path} | rows={len(df)} | statuses={counts}")
    for issue in res.errors:
        print(f"  ERROR  {issue.where}: {issue.message}")
    for issue in res.warnings:
        print(f"  WARN   {issue.where}: {issue.message}")
    print(f"[validate-mapping] result: {res.summary()} -> {'OK' if res.ok else 'FAIL'}")
    return 0 if res.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
