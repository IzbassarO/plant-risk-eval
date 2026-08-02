"""Harm-weighted error over an asymmetric action-to-action cost matrix.

IMPORTANT: no scientific harm matrix is defined here. ``EXAMPLE_DEV_HARM_MATRIX``
is a placeholder for unit tests and pipeline development ONLY. The real,
review-approved weights are out of scope for Phase 1 and must be supplied
separately. Any figure produced with the example matrix is NOT a research result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ..schemas import ACTION_CLASSES, ValidationResult


class HarmMatrix:
    """Asymmetric cost of predicting ``pred`` when the truth is ``true``.

    Indexed by the four action classes; ``loss[true, pred]``. Diagonal is 0
    (a correct action costs nothing) unless explicitly overridden.
    """

    def __init__(self, matrix: pd.DataFrame, *, name: str = "custom", is_example: bool = False):
        self.name = name
        self.is_example = is_example
        self.matrix = self._coerce(matrix)

    @staticmethod
    def _coerce(matrix: pd.DataFrame) -> pd.DataFrame:
        m = matrix.reindex(index=list(ACTION_CLASSES), columns=list(ACTION_CLASSES))
        if m.isna().any().any():
            missing = m.index[m.isna().any(axis=1)].tolist()
            raise ValueError(f"harm matrix missing entries for action(s): {missing}")
        return m.astype(float)

    def loss(self, true_action: str, pred_action: str) -> float:
        return float(self.matrix.loc[true_action, pred_action])

    def mean_harm(
        self,
        true_actions: Sequence[Optional[str]],
        pred_actions: Sequence[Optional[str]],
        unmapped_pred_cost: Optional[float] = None,
    ) -> dict:
        """Mean harm per sample.

        Samples whose TRUE action is None are excluded (cannot score). If a
        PRED action is None: use ``unmapped_pred_cost`` if given, else exclude.
        Returns the metric plus counts (nothing is silently dropped).
        """
        total = 0.0
        included = excluded = 0
        for t, p in zip(true_actions, pred_actions):
            if t is None:
                excluded += 1
                continue
            if p is None or p not in ACTION_CLASSES:
                if unmapped_pred_cost is None:
                    excluded += 1
                    continue
                total += float(unmapped_pred_cost)
                included += 1
                continue
            total += self.loss(t, p)
            included += 1
        return {
            "harm_weighted_error": (total / included) if included else float("nan"),
            "total_harm": total,
            "n_included": included,
            "n_excluded": excluded,
            "matrix_name": self.name,
            "is_example_matrix": self.is_example,
        }

    def validate(self, require_zero_diagonal: bool = True) -> ValidationResult:
        res = ValidationResult()
        m = self.matrix
        if list(m.index) != list(ACTION_CLASSES) or list(m.columns) != list(ACTION_CLASSES):
            res.add("error", "shape", "harm matrix must be indexed by the four action classes")
            return res
        if (m.values < 0).any():
            res.add("error", "values", "harm weights must be non-negative")
        if require_zero_diagonal:
            for a in ACTION_CLASSES:
                if float(m.loc[a, a]) != 0.0:
                    res.add("warning", f"diag[{a}]", "non-zero diagonal (correct action has cost)")
        return res


def _matrix_from_rows(rows: dict[str, dict[str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows).T.reindex(index=list(ACTION_CLASSES), columns=list(ACTION_CLASSES))


# --------------------------------------------------------------------------- #
# EXAMPLE / DEVELOPMENT MATRIX -- NOT SCIENTIFIC. For tests & smoke-runs only.
# Ordering of ACTION_CLASSES: fungicide, copper_sanitation, remove_vector, monitor
# The only property tested is asymmetry + non-negativity + zero diagonal.
# --------------------------------------------------------------------------- #
_EXAMPLE_ROWS = {
    "fungicide":        {"fungicide": 0.0, "copper_sanitation": 1.0, "remove_vector": 2.0, "monitor": 3.0},
    "copper_sanitation":{"fungicide": 1.0, "copper_sanitation": 0.0, "remove_vector": 2.0, "monitor": 3.0},
    "remove_vector":    {"fungicide": 4.0, "copper_sanitation": 4.0, "remove_vector": 0.0, "monitor": 5.0},
    "monitor":          {"fungicide": 2.0, "copper_sanitation": 2.0, "remove_vector": 3.0, "monitor": 0.0},
}
EXAMPLE_DEV_HARM_MATRIX = HarmMatrix(
    _matrix_from_rows(_EXAMPLE_ROWS), name="EXAMPLE_DEV_ONLY", is_example=True
)


def harm_weighted_error(
    true_actions: Sequence[Optional[str]],
    pred_actions: Sequence[Optional[str]],
    harm: HarmMatrix,
    unmapped_pred_cost: Optional[float] = None,
) -> dict:
    """Convenience wrapper around :meth:`HarmMatrix.mean_harm`."""
    return harm.mean_harm(true_actions, pred_actions, unmapped_pred_cost=unmapped_pred_cost)


# --------------------------------------------------------------------------- #
# Reviewed harm matrix with provenance (production gate)
# --------------------------------------------------------------------------- #
HARM_MATRIX_PROVENANCE_FIELDS = (
    "matrix_id", "version", "created_at", "review_status",
    "source_notes", "action_order", "weights",
)
HARM_REVIEW_STATUSES = ("pending", "needs_review", "approved", "example")


class HarmMatrixError(RuntimeError):
    """Raised when a non-approved harm matrix is used where production is required."""


@dataclass
class ReviewedHarmMatrix:
    """A harm matrix carrying review provenance. Only ``review_status='approved'``
    (and not an example) is usable by paper-result commands."""

    matrix_id: str
    version: str
    created_at: str
    review_status: str
    source_notes: str
    action_order: list
    harm: Optional[HarmMatrix]
    is_example: bool = False

    @property
    def matrix(self) -> pd.DataFrame:
        if self.harm is None:
            raise HarmMatrixError(f"harm matrix '{self.matrix_id}' has no weights (template not filled)")
        return self.harm.matrix

    def loss(self, t: str, p: str) -> float:
        return self.matrix.loc[t, p]

    def mean_harm(self, *a, **k) -> dict:
        if self.harm is None:
            raise HarmMatrixError(f"harm matrix '{self.matrix_id}' has no weights")
        return self.harm.mean_harm(*a, **k)

    def is_production_ready(self) -> bool:
        return (
            self.review_status == "approved"
            and not self.is_example
            and self.harm is not None
        )

    def validate_provenance(self) -> ValidationResult:
        res = ValidationResult()
        for f in ("matrix_id", "version", "created_at", "source_notes"):
            if not str(getattr(self, f, "")).strip():
                res.add("error", f, f"provenance field '{f}' is empty")
        if self.review_status not in HARM_REVIEW_STATUSES:
            res.add("error", "review_status", f"invalid review_status '{self.review_status}'")
        if list(self.action_order) != list(ACTION_CLASSES):
            res.add("error", "action_order", f"action_order must equal {list(ACTION_CLASSES)}")
        if self.review_status == "approved" and self.harm is None:
            res.add("error", "weights", "approved matrix must have complete weights")
        return res


def load_reviewed_matrix(path: str | Path) -> ReviewedHarmMatrix:
    """Load a reviewed harm matrix from YAML/JSON. Incomplete weights are allowed
    to load (harm=None) so a pending template can be inspected, but such a matrix
    can never pass :func:`require_production_matrix`."""
    import yaml

    data = yaml.safe_load(Path(path).read_text())
    order = data.get("action_order", list(ACTION_CLASSES))
    weights = data.get("weights") or {}
    harm_obj: Optional[HarmMatrix] = None
    try:
        df = pd.DataFrame(weights).T.reindex(index=list(ACTION_CLASSES), columns=list(ACTION_CLASSES))
        if not df.isna().any().any():
            harm_obj = HarmMatrix(df, name=str(data.get("matrix_id", "reviewed")))
    except Exception:
        harm_obj = None
    return ReviewedHarmMatrix(
        matrix_id=str(data.get("matrix_id", "")),
        version=str(data.get("version", "")),
        created_at=str(data.get("created_at", "")),
        review_status=str(data.get("review_status", "pending")),
        source_notes=str(data.get("source_notes", "")),
        action_order=list(order),
        harm=harm_obj,
        is_example=bool(data.get("is_example", False)),
    )


def require_production_matrix(matrix) -> ReviewedHarmMatrix:
    """Return the matrix if it is approved (production-ready); else raise loudly.

    There is **no scientific default**: a missing or unreviewed matrix is a hard
    error. Paper-result commands must pass an approved ReviewedHarmMatrix.
    """
    if not isinstance(matrix, ReviewedHarmMatrix):
        raise HarmMatrixError(
            "production harm evaluation requires an approved ReviewedHarmMatrix; "
            "a bare/example HarmMatrix is not acceptable as scientific truth."
        )
    if not matrix.is_production_ready():
        raise HarmMatrixError(
            f"harm matrix '{matrix.matrix_id}' is not production-ready "
            f"(review_status='{matrix.review_status}', is_example={matrix.is_example}); "
            f"a human-approved matrix is required."
        )
    return matrix


# The example matrix wrapped with provenance -> explicitly NON-production.
EXAMPLE_DEV_REVIEWED_MATRIX = ReviewedHarmMatrix(
    matrix_id="EXAMPLE_DEV_ONLY",
    version="0",
    created_at="1970-01-01",
    review_status="example",
    source_notes="Placeholder weights for unit tests / pipeline development only. "
                 "NOT agronomically reviewed. Never use for paper results.",
    action_order=list(ACTION_CLASSES),
    harm=EXAMPLE_DEV_HARM_MATRIX,
    is_example=True,
)
