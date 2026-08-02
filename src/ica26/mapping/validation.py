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
    HEALTHY_ACTION_CLASS,
    HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL,
    HEALTHY_FORBIDDEN_FIELDS,
    HEALTHY_POLICY_ID,
    MAPPING_COLUMNS,
    MAPPING_CONFIDENCES,
    PATHOGEN_TYPES,
    REVIEW_STATUSES,
    ValidationResult,
    is_healthy_disease,
)
from .schema import read_mapping


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def cites_healthy_policy(row) -> bool:
    """True if the row explicitly cites the healthy-class policy identifier.

    Accepted carriers are ``source_identifier`` and ``review_notes`` -- the two
    fields that already exist for provenance. Nothing is inferred.
    """
    for col in ("source_identifier", "review_notes"):
        v = row.get(col)
        if not _blank(v) and HEALTHY_POLICY_ID in str(v):
            return True
    return False


def _check_healthy_approval(row, where: str, action: str, res: ValidationResult) -> None:
    """The NARROW healthy exemption (reports/HEALTHY_CLASS_ACTION_POLICY.md).

    Applies ONLY to an approved row whose ``canonical_disease`` is exactly
    ``healthy``. Pathogen-specific evidence is not required -- and must not be
    fabricated -- but action prose, evidence prose, an evidence date, the
    ``monitor`` action, and an explicit policy citation all remain mandatory.
    """
    if action != HEALTHY_ACTION_CLASS:
        res.add("error", where,
                f"approved healthy row must map to action_class "
                f"'{HEALTHY_ACTION_CLASS}' ({HEALTHY_POLICY_ID}), not '{action}'")
    for fld in HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL:
        if _blank(row.get(fld)):
            res.add("error", where,
                    f"approved healthy row missing required field '{fld}'")
    if not cites_healthy_policy(row):
        res.add("error", where,
                f"approved healthy row must cite '{HEALTHY_POLICY_ID}' in "
                "source_identifier or review_notes")
    for fld in HEALTHY_FORBIDDEN_FIELDS:
        if not _blank(row.get(fld)):
            res.add("error", where,
                    f"healthy row must leave '{fld}' blank -- a healthy negative "
                    "class has no pathogen and none may be fabricated")


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
            if is_healthy_disease(row.get("canonical_disease")):
                # Narrow, explicit, auditable exemption -- healthy rows only.
                _check_healthy_approval(row, where, action, res)
            else:
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


def action_lookup(df: pd.DataFrame, require_approved: bool = True,
                  scope=None) -> dict[tuple[str, str], str]:
    """Build a {(dataset, dataset_class) -> action_class} lookup.

    By default only APPROVED, evidence-backed rows are included, so evaluation
    never projects a disease through an unverified mapping.

    ``scope`` is an optional :class:`ica26.evaluation.scope.EvaluationScope`.
    When given, classes recorded as out of scope for action-level evaluation are
    dropped from the lookup, so they project to ``None`` and are excluded from
    action metrics rather than scored. Scope and approval are INDEPENDENT gates:
    a class must clear both. Passed positionally-free (keyword) and duck-typed to
    keep ``ica26.mapping`` free of a dependency on ``ica26.evaluation``.
    """
    src = approved_mapping(df) if require_approved else df
    lut: dict[tuple[str, str], str] = {}
    for _, row in src.iterrows():
        action = str(row["action_class"]).strip()
        if action in ACTION_CLASSES:
            lut[(str(row["dataset"]).strip(), str(row["dataset_class"]).strip())] = action
    if scope is not None:
        lut = scope.filter_action_lookup(lut)
    return lut


class NoApprovedMappingError(RuntimeError):
    """Raised when action evaluation is attempted with no approved mappings."""


def require_approved_lookup(df: pd.DataFrame, scope=None) -> dict[tuple[str, str], str]:
    """Return the approved lookup, or raise if it is empty.

    This is the **hard stop**: no disease label may be projected to an action
    until at least one mapping row is human-approved with evidence. An empty
    approved lookup blocks action-level evaluation by design.
    """
    lut = action_lookup(df, require_approved=True, scope=scope)
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
