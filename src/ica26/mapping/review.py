"""Deterministic transcription of the human-review CSV into the canonical mapping.

The two tables deliberately differ. The review CSV carries
``candidate_action_class`` -- an *author proposal* that a human has not yet
ratified -- while the canonical mapping schema carries ``action_class``, which is
a ratified fact. Nothing bridges them automatically: this module copies the
candidate into the canonical column **only** for a row a human marked
``approved``, and re-validates the result through the ordinary evidence gate
(including the narrow healthy-class exemption) before it may be written.

Rows that are ``needs_review``, ``pending``, or ``excluded`` are never emitted.
Classes recorded as out of action-evaluation scope are never emitted. Both are
independent gates: a class must clear approval AND scope.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pandas as pd

from ..schemas import (
    ACTION_CLASSES,
    FORBIDDEN_ACTION_CLASSES,
    MAPPING_COLUMNS,
    REVIEW_STATUSES,
    ValidationResult,
    is_healthy_disease,
)
from .schema import read_mapping
from .validation import validate_mapping

#: The action column as it appears in the human-review CSV.
REVIEW_ACTION_COLUMN = "candidate_action_class"

#: The action column as it appears in the canonical mapping schema.
CANONICAL_ACTION_COLUMN = "action_class"

#: Statuses a human has terminated. Only ``approved`` is emitted.
TERMINAL_REVIEW_STATUSES: tuple[str, ...] = ("approved", "excluded")

#: Provenance appended to every emitted canonical row.
PROVENANCE_COLUMNS: tuple[str, ...] = (
    "reviewer",
    "reviewed_at",
    "policy_reference",
    "review_source",
    "review_source_row",
)

CANONICAL_OUTPUT_COLUMNS: tuple[str, ...] = MAPPING_COLUMNS + PROVENANCE_COLUMNS

# Dots may appear INSIDE an identifier but never terminate one, so a policy id at
# the end of a sentence does not swallow the full stop.
_POLICY_RE = re.compile(r"policy:[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*")


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def read_review(path: str | Path) -> pd.DataFrame:
    """Read the review CSV verbatim (all columns preserved, everything a string)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")


def policy_references(row) -> list[str]:
    """Every ``policy:<id>`` token cited by the row, sorted and de-duplicated."""
    found: set[str] = set()
    for col in ("source_identifier", "review_notes"):
        v = row.get(col)
        if not _blank(v):
            found.update(_POLICY_RE.findall(str(v)))
    return sorted(found)


def apply_review(
    review_df: pd.DataFrame,
    *,
    scope=None,
    review_source: str = "",
) -> tuple[pd.DataFrame, ValidationResult, dict]:
    """Transform reviewed rows into the canonical approved mapping.

    Returns ``(canonical_df, result, summary)``. ``result`` is truthy only when
    every input row is well-formed AND every emitted row passes the canonical
    evidence gate. A non-ok result means the caller must not write anything.
    """
    res = ValidationResult()

    if REVIEW_ACTION_COLUMN not in review_df.columns:
        res.add("error", "<schema>",
                f"review CSV has no '{REVIEW_ACTION_COLUMN}' column")
        return pd.DataFrame(columns=list(CANONICAL_OUTPUT_COLUMNS)), res, {}
    if CANONICAL_ACTION_COLUMN in review_df.columns:
        res.add("error", "<schema>",
                f"review CSV already carries '{CANONICAL_ACTION_COLUMN}'; the "
                "review input must stay a candidate table so an unratified "
                "proposal can never be mistaken for a ratified mapping")
        return pd.DataFrame(columns=list(CANONICAL_OUTPUT_COLUMNS)), res, {}

    emitted_rows: list[dict] = []
    counts = {s: 0 for s in REVIEW_STATUSES}
    counts["<invalid>"] = 0
    skipped_out_of_scope: list[str] = []
    seen: set[tuple[str, str]] = set()

    for idx, row in review_df.iterrows():
        ds = str(row.get("dataset", "")).strip()
        dc = str(row.get("dataset_class", "")).strip()
        where = f"row {idx + 2} ({ds}/{dc})"  # +2: 1-based, past the header

        if _blank(ds) or _blank(dc):
            res.add("error", where, "dataset and dataset_class must both be non-blank")
            counts["<invalid>"] += 1
            continue
        if (ds, dc) in seen:
            res.add("error", where, f"duplicate (dataset, dataset_class) ({ds}, {dc})")
            counts["<invalid>"] += 1
            continue
        seen.add((ds, dc))

        status = str(row.get("review_status", "")).strip()
        if status not in REVIEW_STATUSES:
            res.add("error", where,
                    f"unsupported review_status '{status}' (allowed: {list(REVIEW_STATUSES)})")
            counts["<invalid>"] += 1
            continue
        counts[status] += 1

        action = str(row.get(REVIEW_ACTION_COLUMN, "")).strip()
        if action in FORBIDDEN_ACTION_CLASSES:
            res.add("error", where, f"forbidden action class '{action}'")
            continue
        if not _blank(action) and action not in ACTION_CLASSES:
            res.add("error", where,
                    f"unknown action class '{action}' (allowed: {list(ACTION_CLASSES)})")
            continue

        if status != "approved":
            continue  # needs_review / pending / excluded are never emitted

        if _blank(action):
            res.add("error", where,
                    f"approved row has a blank '{REVIEW_ACTION_COLUMN}'; there is "
                    "nothing to ratify")
            continue

        in_scope = scope is None or scope.include_action_evaluation(ds, dc)
        if not in_scope:
            # An approved row for an out-of-action-scope class is a contradiction:
            # the human both ratified a disease action and declared the class out
            # of disease-action scope. Fail closed rather than pick a winner.
            res.add("error", where,
                    "row is approved but its class is recorded out of "
                    "action-evaluation scope; resolve the contradiction in "
                    "configs/evaluation_scope.yaml or the review CSV")
            skipped_out_of_scope.append(f"{ds}/{dc}")
            continue

        out = {c: "" for c in CANONICAL_OUTPUT_COLUMNS}
        for c in MAPPING_COLUMNS:
            if c == CANONICAL_ACTION_COLUMN:
                continue
            if c in review_df.columns:
                out[c] = str(row.get(c, ""))
        # THE transcription: candidate -> ratified, for approved rows only.
        out[CANONICAL_ACTION_COLUMN] = action
        out["reviewer"] = str(row.get("reviewer", "")).strip()
        out["reviewed_at"] = str(row.get("reviewed_at", "")).strip()
        out["policy_reference"] = ";".join(policy_references(row))
        out["review_source"] = review_source
        out["review_source_row"] = str(idx + 2)
        emitted_rows.append(out)

    canonical = pd.DataFrame(emitted_rows, columns=list(CANONICAL_OUTPUT_COLUMNS))
    if len(canonical):
        canonical = canonical.sort_values(["dataset", "dataset_class"]).reset_index(drop=True)

    # Re-validate through the ordinary canonical gate. The healthy exemption is
    # applied there, not here, so there is exactly one evidence gate in the code.
    if len(canonical):
        canonical_res = validate_mapping(canonical)
        for issue in canonical_res.issues:
            res.add(issue.level, f"canonical:{issue.where}", issue.message)

    healthy = sum(1 for r in emitted_rows if is_healthy_disease(r.get("canonical_disease")))
    summary = {
        "review_rows": int(len(review_df)),
        "review_status_counts": {k: v for k, v in counts.items() if v or k in REVIEW_STATUSES},
        "emitted_rows": int(len(canonical)),
        "emitted_healthy_rows": healthy,
        "emitted_disease_rows": int(len(canonical)) - healthy,
        "action_class_counts": (
            canonical["action_class"].value_counts().sort_index().to_dict()
            if len(canonical) else {}
        ),
        "skipped_out_of_action_scope": sorted(skipped_out_of_scope),
        "scope_out_of_action_evaluation": (
            [f"{d}/{c}" for d, c in scope.out_of_scope("include_action_evaluation")]
            if scope is not None else []
        ),
        "errors": [f"{i.where}: {i.message}" for i in res.errors],
        "warnings": [f"{i.where}: {i.message}" for i in res.warnings],
        "ok": res.ok,
    }
    return canonical, res, summary


def write_canonical(df: pd.DataFrame, path: str | Path) -> Path:
    """Atomically write the canonical mapping (temp file + rename, LF endings)."""
    import os

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for c in CANONICAL_OUTPUT_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out = out[list(CANONICAL_OUTPUT_COLUMNS)]
    tmp = path.with_name(path.name + ".part")
    out.to_csv(tmp, index=False, lineterminator="\n")
    os.replace(tmp, path)
    return path


def read_canonical(path: str | Path) -> pd.DataFrame:
    """Read a previously written canonical mapping (canonical columns first)."""
    return read_mapping(path)
