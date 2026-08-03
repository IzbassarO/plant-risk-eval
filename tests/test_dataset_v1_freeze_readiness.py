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
#: Domain judgements about the data itself.
HUMAN_SCIENTIFIC_CONDITIONS = {
    "disease_action_mapping_reviewed", "plantvillage_action_mapping_coverage",
    "harm_matrix_approved", "relabel_second_scientific_review",
}
#: A decision to proceed, taken by an accountable owner.
GOVERNANCE_CONDITIONS = {"freeze_approval_recorded"}
#: A verdict by someone who did not do the work.
INDEPENDENT_AUDIT_CONDITIONS = {"open_audit_findings_closed"}

#: Everything that is not the pipeline's to settle. R2B.1 split these by KIND:
#: a governance approval cannot stand in for a scientific judgement, and neither
#: can stand in for an independent audit.
HUMAN_CONDITIONS = (HUMAN_SCIENTIFIC_CONDITIONS | GOVERNANCE_CONDITIONS
                    | INDEPENDENT_AUDIT_CONDITIONS)

KIND_OF = {
    **{c: "machine" for c in MACHINE_CONDITIONS},
    **{c: "human_scientific" for c in HUMAN_SCIENTIFIC_CONDITIONS},
    **{c: "governance_approval" for c in GOVERNANCE_CONDITIONS},
    **{c: "independent_audit" for c in INDEPENDENT_AUDIT_CONDITIONS},
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


def test_conditions_carry_their_correct_kind(by_id):
    for cid, c in by_id.items():
        assert c["kind"] == KIND_OF[cid], cid
        assert c["status"] in ("satisfied", "blocked")
        assert c["detail"], cid


def test_the_four_kinds_are_all_represented(by_id):
    """Collapsing these into one 'human' bucket is what R2B.1 undid."""
    kinds = {c["kind"] for c in by_id.values()}
    assert kinds == {"machine", "human_scientific", "governance_approval",
                     "independent_audit"}


def test_every_condition_binds_the_digest_of_its_evidence(by_id):
    """A verdict must not outlive the artifact it was computed from."""
    for cid, c in by_id.items():
        assert c["evidence"], cid
        digest = c["evidence_digest"]
        assert digest == "<absent>" or (len(digest) == 64 and
                                        all(ch in "0123456789abcdef" for ch in digest)), cid


def test_conditions_awaiting_a_human_artifact_record_it_as_absent(by_id):
    for cid in ("freeze_approval_recorded", "open_audit_findings_closed",
                "relabel_second_scientific_review"):
        assert by_id[cid]["evidence_digest"] == "<absent>", cid


@pytest.mark.parametrize("cid", sorted(MACHINE_CONDITIONS))
def test_every_mechanical_precondition_is_satisfied(by_id, cid):
    """R2A + R2B settled all of these; a regression here is a real defect."""
    assert by_id[cid]["status"] == "satisfied", by_id[cid]["detail"]


@pytest.mark.parametrize("cid", sorted(HUMAN_CONDITIONS))
def test_every_human_decision_is_still_blocked(by_id, cid):
    """None of these has been decided. A default-yes here would be the whole bug."""
    assert by_id[cid]["status"] == "blocked", by_id[cid]["detail"]


def test_mapping_readiness_names_the_undecided_classes(by_id):
    """R2B.1 Finding 1: the verdict reports identities, not just a count."""
    detail = by_id["disease_action_mapping_reviewed"]["detail"]
    assert "non-terminal" in detail and "not terminal" in detail
    assert "coverage 11/28" in detail

    pv = by_id["plantvillage_action_mapping_coverage"]["detail"]
    assert "coverage 0/38" in pv and "missing" in pv


def test_approval_conditions_say_the_decision_was_not_taken(by_id):
    for cid in ("freeze_approval_recorded", "open_audit_findings_closed",
                "relabel_second_scientific_review"):
        assert "has not been taken" in by_id[cid]["detail"], cid


def test_dataset_v1_is_not_ready_and_not_frozen(readiness):
    assert readiness["status"] == "not_ready"
    assert readiness["frozen"] is False
    assert readiness["satisfied"] == len(MACHINE_CONDITIONS)
    assert readiness["blocked"] == len(HUMAN_CONDITIONS)
    assert set(readiness["blockers"]) == HUMAN_CONDITIONS


def test_the_assessment_records_the_schemas_it_validated_against(readiness):
    prov = readiness["provenance"]
    assert prov["approval_schema"] == "ica26.governance.approval/1"
    assert prov["mapping_readiness_schema"] == "ica26.governance.mapping_readiness/1"
    assert prov["condition_kinds"] == ["machine", "human_scientific",
                                       "governance_approval", "independent_audit"]


def test_the_assessment_does_not_embed_the_current_commit(readiness):
    """Embedding HEAD would make this artifact stale on every commit, including
    the one that stores it -- a --check that can never pass teaches a reader to
    ignore it. Approvals are still bound to live HEAD at validation time."""
    text = json.dumps(readiness)
    assert "repository_commit" not in readiness["provenance"]
    assert "live HEAD at run time" in readiness["provenance"]["commit_binding"]
    import re
    assert not re.search(r"\b[0-9a-f]{40}\b", text), "a raw commit SHA is embedded"


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
