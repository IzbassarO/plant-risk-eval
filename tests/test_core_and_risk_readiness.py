"""Core Dataset V1 and Risk Evaluation Layer V1 are assessed separately (Part 7).

One readiness assessment used to cover two different questions, and the stricter
of them held the other hostage: baseline computer-vision training was blocked on
a harm matrix it does not use. It also invited the opposite misreading, because
"Dataset V1 is not ready" sounds like the dataset is defective when the machine
evidence says otherwise.

These tests hold the separation to its two obligations. Core readiness must not
depend on any risk artifact -- asserted by removing them and re-evaluating, not
by reading the condition list. And neither assessment may drift toward claiming
more than it has: Core is not frozen, training is not authorized, and the Risk
Layer's scientific second review has not been performed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

CORE_JSON = Path("reports/core_dataset_v1_readiness.json")
CORE_MD = Path("reports/CORE_DATASET_V1_READINESS.md")
RISK_JSON = Path("reports/risk_evaluation_layer_v1_readiness.json")
RISK_MD = Path("reports/RISK_EVALUATION_LAYER_V1_READINESS.md")
SCRIPT = Path("scripts/build_core_and_risk_readiness.py")

#: Artifacts that belong to risk modelling. Core must not consult any of them.
RISK_ARTIFACTS = (
    "data/mapping/action_mapping_review.csv",
    "data/mapping/action_mapping_approved.csv",
    "configs/harm_matrix_template.yaml",
    "human_review/plantdoc_label_second_review/second_review.json",
)

RISK_CONDITIONS = {
    "disease_action_mapping_reviewed",
    "plantvillage_action_mapping_coverage",
    "harm_matrix_approved",
    "relabel_second_scientific_review",
}


@pytest.fixture(scope="module")
def core(repo_root):
    return json.loads((repo_root / CORE_JSON).read_text())


@pytest.fixture(scope="module")
def risk(repo_root):
    return json.loads((repo_root / RISK_JSON).read_text())


# --------------------------------------------------------------------------- #
# The separation itself
# --------------------------------------------------------------------------- #
def test_core_readiness_contains_no_risk_condition(core):
    assert not (set(c["id"] for c in core["conditions"]) & RISK_CONDITIONS)
    assert core["depends_on_risk_layer"] is False


def test_risk_readiness_contains_exactly_the_risk_conditions(risk):
    assert {c["id"] for c in risk["conditions"]} == RISK_CONDITIONS


def test_every_condition_belongs_to_exactly_one_layer(core, risk):
    core_ids = {c["id"] for c in core["conditions"]}
    risk_ids = {c["id"] for c in risk["conditions"]}
    assert not (core_ids & risk_ids)
    # The builder refuses to run if a condition belongs to neither layer, so a
    # future condition cannot be silently dropped from both assessments.
    assert core["unassigned_conditions"] == []


def test_core_covers_the_dataset_dimensions_it_claims_to(core):
    ids = {c["id"] for c in core["conditions"]}
    for required in ("plantdoc_acquired", "plantvillage_materialized",
                     "plantvillage_manifest_reconstructed",
                     "cross_dataset_leakage_gate", "core_cross_dataset_leakage",
                     "internal_duplicate_gate", "conservative_exclusions_recorded",
                     "core_dataset_current", "core_dataset_integrity",
                     "effective_dataset_pixels_verified",
                     "human_review_evidence_intact", "anonymity",
                     "open_audit_findings_closed", "freeze_approval_recorded"):
        assert required in ids, required


def test_core_readiness_does_not_read_any_risk_artifact(repo_root, tmp_path):
    """The load-bearing claim, tested by deletion rather than by inspection.

    Moving the risk artifacts out of the way must not change a single Core
    condition. Reading the condition list would only prove the *reported* set is
    clean; this proves the evaluation does not consult them.
    """
    import shutil

    work = tmp_path / "repo"
    shutil.copytree(repo_root, work, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "*.zip"))

    before = json.loads((work / CORE_JSON).read_text())
    for relative in RISK_ARTIFACTS:
        target = work / relative
        if target.exists():
            target.unlink()

    result = subprocess.run(
        [sys.executable, str(work / SCRIPT)], cwd=str(work),
        capture_output=True, text=True)
    assert result.returncode in (0, 1), result.stdout + result.stderr

    after = json.loads((work / CORE_JSON).read_text())
    assert after["status"] == before["status"]
    assert after["machine_blockers"] == before["machine_blockers"]
    assert ([c["id"] for c in after["conditions"]]
            == [c["id"] for c in before["conditions"]])
    assert ([c["status"] for c in after["conditions"]]
            == [c["status"] for c in before["conditions"]])


# --------------------------------------------------------------------------- #
# What each assessment is allowed to claim
# --------------------------------------------------------------------------- #
def test_core_is_ready_for_independent_audit_and_nothing_more(core):
    assert core["status"] == "ready_for_independent_audit"
    assert core["machine_blockers"] == []
    # What remains is exactly the two decisions a machine must not take.
    assert core["open_decisions"] == ["open_audit_findings_closed",
                                      "freeze_approval_recorded"]


def test_core_is_not_frozen_and_authorizes_no_training(core):
    assert core["frozen"] is False
    assert core["training_authorized"] is False
    assert core["provenance"]["freezes_nothing"] is True
    assert core["provenance"]["authorizes_no_training"] is True


def test_the_risk_layer_is_not_ready(risk):
    assert risk["status"] == "not_ready"
    assert set(risk["blockers"]) == RISK_CONDITIONS
    assert risk["frozen"] is False
    assert risk["scientific_second_review_performed"] is False


def test_the_training_boundary_is_machine_readable(core):
    boundary = core["training_boundary"]
    assert "plantvillage_in_domain_classification_baseline" in (
        boundary["permitted_after_core_freeze"])
    assert "plantdoc_core_in_domain_classification_baseline" in (
        boundary["permitted_after_core_freeze"])
    for blocked in ("harm_weighted_model_selection", "action_aware_training",
                    "treatment_recommendation", "risk_weighted_conclusions",
                    "final_risk_aware_evaluation_tables"):
        assert blocked in boundary["blocked_until_risk_layer_frozen"]
    assert not (set(boundary["permitted_after_core_freeze"])
                & set(boundary["blocked_until_risk_layer_frozen"]))


# --------------------------------------------------------------------------- #
# The Core-specific evidence
# --------------------------------------------------------------------------- #
def _detail(payload, cid):
    return next(c for c in payload["conditions"] if c["id"] == cid)["detail"]


def test_core_records_the_conservative_exclusions(core):
    detail = _detail(core, "conservative_exclusions_recorded")
    assert "3 authenticated exclusion" in detail
    assert "G07" in detail and "G08" in detail and "G10" in detail


def test_core_integrity_reports_the_expected_shape(core):
    detail = _detail(core, "core_dataset_integrity")
    assert "2561 record" in detail
    assert "'train': 2336" in detail and "'test': 225" in detail
    assert "28 class" in detail
    assert "2554 non-reviewed record(s) unchanged" in detail


def test_core_leakage_is_computed_over_the_core_corpus(core):
    detail = _detail(core, "core_cross_dataset_leakage")
    assert "54305" in detail and "2561" in detail
    assert "0 exact" in detail
    assert "0 unresolved" in detail


def test_plantvillage_reconstruction_is_a_core_condition(core):
    detail = _detail(core, "plantvillage_manifest_reconstructed")
    assert "54305 record" in detail


# --------------------------------------------------------------------------- #
# Determinism and the human-readable renderings
# --------------------------------------------------------------------------- #
def test_the_assessments_rebuild_byte_identically(repo_root):
    result = subprocess.run(
        [sys.executable, str(repo_root / SCRIPT), "--check"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "check OK" in result.stdout


def test_neither_assessment_carries_a_wall_clock_field(core, risk):
    for payload in (core, risk):
        text = json.dumps(payload)
        for banned in ("generated_at", "timestamp", "retrieved_at", "elapsed"):
            assert banned not in text


def test_the_core_report_states_plainly_that_nothing_is_frozen(repo_root):
    text = (repo_root / CORE_MD).read_text()
    assert "Core Dataset V1 frozen: NO" in text
    assert "Training authorized: NO" in text
    assert "READY_FOR_INDEPENDENT_AUDIT" in text


def test_the_risk_report_does_not_impugn_the_core_dataset(repo_root):
    text = (repo_root / RISK_MD).read_text()
    assert "not ready" in text.lower()
    # It must say explicitly that its own incompleteness is not a dataset defect.
    assert "not** about the dataset" in text or "not about the dataset" in text
    assert "ready_for_independent_audit" in text
