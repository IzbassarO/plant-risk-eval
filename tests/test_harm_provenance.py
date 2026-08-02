"""Harm-matrix provenance: only approved matrices are production-usable."""
from __future__ import annotations

import pandas as pd
import pytest

from ica26.evaluation import harm
from ica26.schemas import ACTION_CLASSES


def _approved_matrix():
    weights = {a: {b: (0.0 if a == b else 1.0) for b in ACTION_CLASSES} for a in ACTION_CLASSES}
    df = pd.DataFrame(weights).T.reindex(index=list(ACTION_CLASSES), columns=list(ACTION_CLASSES))
    return harm.ReviewedHarmMatrix(
        matrix_id="test_v1", version="1.0", created_at="2026-07-28",
        review_status="approved", source_notes="test-only approved matrix",
        action_order=list(ACTION_CLASSES), harm=harm.HarmMatrix(df, name="test_v1"),
    )


def test_example_matrix_not_production_ready():
    assert harm.EXAMPLE_DEV_REVIEWED_MATRIX.is_production_ready() is False
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(harm.EXAMPLE_DEV_REVIEWED_MATRIX)


def test_bare_harmmatrix_rejected_for_production():
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(harm.EXAMPLE_DEV_HARM_MATRIX)


def test_approved_matrix_accepted():
    m = _approved_matrix()
    assert m.is_production_ready()
    assert harm.require_production_matrix(m) is m


def test_pending_matrix_rejected():
    m = _approved_matrix()
    m.review_status = "pending"
    assert not m.is_production_ready()
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(m)


def test_template_config_loads_but_is_not_production_ready():
    m = harm.load_reviewed_matrix("configs/harm_matrix_template.yaml")
    assert m.review_status == "pending"
    assert m.harm is None                       # unfilled weights -> not loadable as usable
    assert not m.is_production_ready()
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(m)


def test_provenance_validation_catches_bad_action_order():
    m = _approved_matrix()
    m.action_order = ["fungicide", "monitor"]
    assert not m.validate_provenance().ok


def test_no_scientific_default_matrix_exists():
    # the module must not expose an approved, ready-to-use scientific matrix
    for name in dir(harm):
        obj = getattr(harm, name)
        if isinstance(obj, harm.ReviewedHarmMatrix):
            assert obj.review_status != "approved", f"{name} must not be pre-approved"
