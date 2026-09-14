"""Harm-matrix provenance: only approved matrices are production-usable."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ica26.evaluation import harm
from ica26.schemas import ACTION_CLASSES


def _approved_matrix():
    weights = {a: {b: (0.0 if a == b else 1.0) for b in ACTION_CLASSES} for a in ACTION_CLASSES}
    df = pd.DataFrame(weights).T.reindex(index=list(ACTION_CLASSES), columns=list(ACTION_CLASSES))
    return harm.ReviewedHarmMatrix(
        matrix_id="harm_matrix_test_v1", version="1.0",
        created_at="2026-07-28T09:00:00+00:00",
        review_status="approved",
        source_notes=("Test-only source record documenting the agronomic evidence "
                      "and the citable basis for every matrix weight."),
        action_order=list(ACTION_CLASSES), harm=harm.HarmMatrix(df, name="test_v1"),
        reviewer_id="reviewer_01", reviewer_role="plant pathology reviewer",
        reviewed_at="2026-07-28T10:00:00+00:00",
        review_rationale=("Reviewed every off-diagonal cost against the documented "
                          "agronomic sources and verified the action ordering."),
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
    assert m.validate_provenance().ok
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
    assert m.reviewer_id == ""
    assert m.reviewed_at == ""
    assert m.harm is None                       # unfilled weights -> not loadable as usable
    assert not m.is_production_ready()
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(m)


def test_changing_only_template_status_to_approved_cannot_create_an_approval(tmp_path):
    payload = Path("configs/harm_matrix_template.yaml").read_text(encoding="utf-8")
    forged = tmp_path / "forged_approved_matrix.yaml"
    forged.write_text(payload.replace("review_status: pending", "review_status: approved"),
                      encoding="utf-8")
    m = harm.load_reviewed_matrix(forged)

    errors = m.validate_provenance().errors
    assert any(issue.where == "reviewer_id" for issue in errors)
    assert any(issue.where == "reviewed_at" for issue in errors)
    assert not m.is_production_ready()
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(m)


def test_provenance_validation_catches_bad_action_order():
    m = _approved_matrix()
    m.action_order = ["fungicide", "monitor"]
    assert not m.validate_provenance().ok


@pytest.mark.parametrize("field", ["reviewer_id", "reviewer_role", "reviewed_at",
                                   "review_rationale"])
def test_bare_approved_status_without_accountable_review_is_refused(field):
    m = _approved_matrix()
    setattr(m, field, "")
    result = m.validate_provenance()
    assert any(issue.where == field for issue in result.errors)
    assert not m.is_production_ready()
    with pytest.raises(harm.HarmMatrixError):
        harm.require_production_matrix(m)


@pytest.mark.parametrize("field, value", [
    ("reviewed_at", "2026-07-28T10:00:00"),       # offset missing
    ("reviewed_at", "not-a-timestamp"),
    ("created_at", "2026-07-28"),                 # date is not an auditable instant
])
def test_approved_matrix_requires_strict_timestamp_provenance(field, value):
    m = _approved_matrix()
    setattr(m, field, value)
    result = m.validate_provenance()
    assert any(issue.where == field for issue in result.errors)
    assert not m.is_production_ready()


def test_approved_matrix_cannot_reuse_unfilled_template_source_notes():
    m = _approved_matrix()
    m.source_notes = "UNFILLED TEMPLATE. Add sources later."
    result = m.validate_provenance()
    assert any(issue.where == "source_notes" for issue in result.errors)
    assert not m.is_production_ready()


def test_no_scientific_default_matrix_exists():
    # the module must not expose an approved, ready-to-use scientific matrix
    for name in dir(harm):
        obj = getattr(harm, name)
        if isinstance(obj, harm.ReviewedHarmMatrix):
            assert obj.review_status != "approved", f"{name} must not be pre-approved"
