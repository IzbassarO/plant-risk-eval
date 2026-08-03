"""The Dataset V1 freeze-readiness assessment.

A freeze is the point after which numbers become quotable, so "may we freeze?"
deserves one reproducible answer rather than a reader assembling it from five
reports. These tests pin what that answer currently is, prove the assessment
cannot freeze anything, and prove that a scientific judgement is never satisfied
by default.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

READINESS_JSON = "reports/dataset_v1_freeze_readiness.json"
READINESS_MD = "reports/DATASET_V1_FREEZE_READINESS.md"
SCRIPT = "scripts/build_dataset_v1_freeze_readiness.py"

#: Preconditions the pipeline can settle on its own.
MACHINE_CONDITIONS = {
    "plantdoc_acquired", "plantvillage_materialized", "cross_dataset_leakage_gate",
    "internal_duplicate_gate", "effective_dataset_current", "effective_dataset_integrity",
    "effective_dataset_pixels_verified", "human_review_evidence_intact", "anonymity",
}
#: Preconditions that are scientific judgements. No artifact, no credit.
HUMAN_CONDITIONS = {
    "disease_action_mapping_reviewed", "plantvillage_action_mapping_coverage",
    "harm_matrix_approved", "open_audit_findings_closed",
    "remediation_independently_audited", "freeze_approval_recorded",
}


@pytest.fixture(scope="module")
def readiness(repo_root):
    return json.loads((repo_root / READINESS_JSON).read_text())


@pytest.fixture(scope="module")
def by_id(readiness):
    return {c["id"]: c for c in readiness["conditions"]}


def test_every_condition_is_declared_exactly_once(by_id, readiness):
    assert set(by_id) == MACHINE_CONDITIONS | HUMAN_CONDITIONS
    assert len(readiness["conditions"]) == len(by_id)


def test_conditions_are_typed_machine_or_human(by_id):
    for cid, c in by_id.items():
        assert c["kind"] == ("machine" if cid in MACHINE_CONDITIONS else "human"), cid
        assert c["status"] in ("satisfied", "blocked")
        assert c["detail"], cid


@pytest.mark.parametrize("cid", sorted(MACHINE_CONDITIONS))
def test_every_mechanical_precondition_is_satisfied(by_id, cid):
    """R2A + R2B settled all of these; a regression here is a real defect."""
    assert by_id[cid]["status"] == "satisfied", by_id[cid]["detail"]


@pytest.mark.parametrize("cid", sorted(HUMAN_CONDITIONS))
def test_every_scientific_judgement_is_still_blocked(by_id, cid):
    """None of these has been decided. A default-yes here would be the whole bug."""
    assert by_id[cid]["status"] == "blocked", by_id[cid]["detail"]


def test_dataset_v1_is_not_ready_and_not_frozen(readiness):
    assert readiness["status"] == "not_ready"
    assert readiness["frozen"] is False
    assert readiness["satisfied"] == len(MACHINE_CONDITIONS)
    assert readiness["blocked"] == len(HUMAN_CONDITIONS)
    assert set(readiness["blockers"]) == HUMAN_CONDITIONS


def test_the_assessment_freezes_nothing(repo_root, readiness):
    assert readiness["provenance"]["freezes_nothing"] is True
    for artifact in ("data/manifests/dataset_v1_freeze.json",
                     "data/manifests/dataset_v1_freeze_approval.json",
                     "reports/DATASET_V1_AUDIT_SIGNOFF.json"):
        assert not (repo_root / artifact).exists(), (
            f"{artifact} exists; the freeze decision is not this pipeline's to take")


def test_it_binds_the_inputs_it_judged(readiness):
    for name in ("plantdoc_manifest", "effective_manifest", "duplicate_resolution",
                 "leakage_gate", "internal_duplicate_gate", "action_mapping_review",
                 "human_review_evidence"):
        assert readiness["input_digests"].get(name) not in (None, "<absent>"), name


def test_it_has_no_wall_clock_field(readiness):
    assert "generated_at" not in readiness
    assert "timestamp" not in readiness


def test_rebuild_is_byte_identical_and_reports_not_ready(repo_root):
    before = {p: (repo_root / p).read_bytes() for p in (READINESS_JSON, READINESS_MD)}
    r = subprocess.run([sys.executable, str(repo_root / SCRIPT), "--check"],
                       cwd=str(repo_root), capture_output=True, text=True)
    assert "check OK" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 1          # current, but not ready -> non-zero
    assert {p: (repo_root / p).read_bytes() for p in (READINESS_JSON, READINESS_MD)} == before


def test_the_markdown_states_plainly_that_nothing_was_frozen(repo_root):
    text = (repo_root / READINESS_MD).read_text()
    assert "freezes nothing" in text.lower()
    assert "NOT_READY" in text
    assert "Dataset V1 frozen: NO" in text
    for cid in sorted(HUMAN_CONDITIONS):
        assert cid in text, cid


def test_skipping_pixel_verification_blocks_rather_than_passes(repo_root, tmp_path):
    """An unverified check is not a passing one."""
    r = subprocess.run(
        [sys.executable, str(repo_root / SCRIPT), "--check", "--skip-pixel-verification"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert "effective_dataset_pixels_verified" in r.stdout
    assert r.returncode != 0
