"""Strict approval and sign-off validation (R2B.1 Finding 2).

The reported exploit is the first test in this file::

    {"approved": true}

It satisfied the previous freeze-approval predicate. Everything below pins the
ways an approval can be hollow — no author, no scope, no object, a timestamp
that predates the tree it claims to have read, a digest that no longer matches
the file it binds — and proves each one is refused.

No test in this file creates a valid approval in the repository. The one valid
payload is built in a temporary directory over synthetic artifacts, purely to
prove the validator is satisfiable; if it were not, every refusal below would be
vacuous.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from ica26.governance.approvals import (
    AFFIRMATIVE,
    APPROVAL_SCHEMA,
    AUDIT_SIGNOFF_SPEC,
    FREEZE_APPROVAL_SPEC,
    MIN_RATIONALE_CHARS,
    REQUIRED_FIELDS,
    SECOND_REVIEW_SPEC,
    ApprovalSpec,
    validate_approval,
    validate_approval_file,
)

SPEC = ApprovalSpec(artifact_type="test_approval", scope="test_scope",
                    required_bindings=("bound.txt",))


@pytest.fixture
def repo(tmp_path):
    """A real git repo with one committed artifact, so commit binding is testable."""
    (tmp_path / "bound.txt").write_text("authoritative content\n", encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "-A"],
                ["-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "seed"]):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True,
                       capture_output=True)
    return tmp_path


@pytest.fixture
def head(repo):
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.fixture
def bound_digest(repo):
    import hashlib
    return hashlib.sha256((repo / "bound.txt").read_bytes()).hexdigest()


@pytest.fixture
def valid(head, bound_digest):
    """A payload that satisfies SPEC. Synthetic; never written into the repository."""
    return {
        "schema_version": APPROVAL_SCHEMA,
        "artifact_type": "test_approval",
        "decision": AFFIRMATIVE,
        "scope": "test_scope",
        "reviewer_id": "reviewer_7",
        "reviewer_role": "dataset governance owner",
        "reviewed_at": "2099-01-01T00:00:00+00:00",   # replaced below
        "repository_commit": head,
        "approved_artifacts": {"bound.txt": bound_digest},
        "rationale": "Reviewed the bound artifact in full against the recorded criteria.",
        "not_approved": ["training", "phase 2", "any label decision"],
    }


@pytest.fixture
def now_stamp(repo, head):
    """A timestamp at the commit's own instant -- valid, and never in the future."""
    out = subprocess.run(["git", "-C", str(repo), "show", "-s", "--format=%cI", head],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


@pytest.fixture
def ok(valid, now_stamp):
    valid["reviewed_at"] = now_stamp
    return valid


def _v(payload, repo, spec=SPEC, **kw):
    return validate_approval(payload, spec, repo=repo, path="approval.json", **kw)


# --------------------------------------------------------------------------- #
# The baseline: the validator must be satisfiable
# --------------------------------------------------------------------------- #
def test_a_complete_approval_is_accepted(ok, repo):
    v = _v(ok, repo)
    assert v.valid, v.violations
    assert v.satisfied and v.decision == AFFIRMATIVE


# --------------------------------------------------------------------------- #
# The reported exploit
# --------------------------------------------------------------------------- #
def test_the_minimal_boolean_approval_is_refused(repo):
    """`{"approved": true}` -- the artifact the audit demonstrated."""
    v = _v({"approved": True}, repo)
    assert not v.valid and not v.satisfied
    assert any("missing or placeholder required field" in x for x in v.violations)


@pytest.mark.parametrize("payload", [True, False, None, 42, "approved",
                                     ["approved"], [{"decision": "approved"}]])
def test_a_non_object_artifact_is_refused(payload, repo):
    v = _v(payload, repo)
    assert not v.valid
    assert any("expected a single JSON object" in x for x in v.violations)


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_every_required_field_is_actually_required(ok, repo, field):
    ok.pop(field)
    v = _v(ok, repo)
    assert not v.valid, f"'{field}' was not required"
    assert not v.satisfied


@pytest.mark.parametrize("field", ["reviewer_id", "reviewer_role", "rationale", "scope"])
@pytest.mark.parametrize("token", ["", "   ", "TBD", "n/a", "none", "placeholder"])
def test_placeholder_values_are_refused(ok, repo, field, token):
    ok[field] = token
    assert not _v(ok, repo).valid


def test_an_empty_reviewer_is_refused(ok, repo):
    ok["reviewer_id"] = ""
    v = _v(ok, repo)
    assert not v.valid
    assert any("reviewer_id" in x for x in v.violations)


def test_a_missing_reviewer_role_is_refused(ok, repo):
    ok["reviewer_role"] = ""
    assert not _v(ok, repo).valid


@pytest.mark.parametrize("stamp", ["", "tomorrow", "2026-08-02T21:10:00",
                                   "2099-01-01T00:00:00+00:00",
                                   "2026-02-30T00:00:00+00:00", "not a date"])
def test_an_invalid_timestamp_is_refused(ok, repo, stamp):
    ok["reviewed_at"] = stamp
    assert not _v(ok, repo).valid


def test_a_short_rationale_is_refused(ok, repo):
    ok["rationale"] = "looks fine"
    v = _v(ok, repo)
    assert len(ok["rationale"]) < MIN_RATIONALE_CHARS
    assert not v.valid
    assert any("rationale" in x for x in v.violations)


def test_an_empty_not_approved_statement_is_refused(ok, repo):
    for value in ("", "n/a", []):
        payload = dict(ok, not_approved=value)
        assert not _v(payload, repo).valid, value


# --------------------------------------------------------------------------- #
# Wrong artifact, wrong scope, wrong decision
# --------------------------------------------------------------------------- #
def test_a_wrong_artifact_type_is_refused(ok, repo):
    ok["artifact_type"] = "dataset_v1_freeze_approval"
    v = _v(ok, repo)
    assert not v.valid
    assert any("artifact_type" in x for x in v.violations)


def test_an_approval_for_a_different_scope_does_not_transfer(ok, repo):
    ok["scope"] = "some_other_scope"
    v = _v(ok, repo)
    assert not v.valid
    assert any("scope" in x for x in v.violations)


@pytest.mark.parametrize("decision", ["yes", "ok", "APPROVED", "approve", "signed",
                                      "true", "1"])
def test_an_unknown_decision_value_is_refused(ok, repo, decision):
    ok["decision"] = decision
    v = _v(ok, repo)
    assert not v.valid
    assert any("unknown decision" in x for x in v.violations)


@pytest.mark.parametrize("decision", ["rejected", "deferred"])
def test_a_valid_negative_decision_is_valid_but_never_satisfies(ok, repo, decision):
    ok["decision"] = decision
    v = _v(ok, repo)
    assert v.valid and not v.satisfied
    assert "not 'approved'" in v.detail()


def test_a_wrong_schema_version_is_rejected_not_coerced(ok, repo):
    ok["schema_version"] = "ica26.governance.approval/0"
    v = _v(ok, repo)
    assert not v.valid
    assert any("schema_version" in x for x in v.violations)


# --------------------------------------------------------------------------- #
# Integrity binding
# --------------------------------------------------------------------------- #
def test_a_stale_artifact_digest_is_refused(ok, repo):
    (repo / "bound.txt").write_text("edited after approval\n", encoding="utf-8")
    v = _v(ok, repo)
    assert not v.valid
    assert any("has changed since approval" in x for x in v.violations)


def test_a_required_binding_may_not_be_omitted(ok, repo, bound_digest):
    ok["approved_artifacts"] = {"unrelated.txt": bound_digest}
    v = _v(ok, repo)
    assert not v.valid
    assert any("does not bind required 'bound.txt'" in x for x in v.violations)


def test_binding_a_nonexistent_artifact_is_refused(ok, repo, bound_digest):
    ok["approved_artifacts"]["ghost.txt"] = bound_digest
    v = _v(ok, repo)
    assert not v.valid
    assert any("does not exist" in x for x in v.violations)


@pytest.mark.parametrize("bad", ["", "not-a-digest", "abc", "z" * 64, 12345])
def test_a_malformed_digest_is_refused(ok, repo, bad):
    ok["approved_artifacts"]["bound.txt"] = bad
    assert not _v(ok, repo).valid


def test_an_empty_binding_map_is_refused(ok, repo):
    ok["approved_artifacts"] = {}
    assert not _v(ok, repo).valid


# --------------------------------------------------------------------------- #
# Commit binding and ordering
# --------------------------------------------------------------------------- #
def test_a_stale_commit_binding_is_refused(ok, repo):
    ok["repository_commit"] = "0" * 40
    v = _v(ok, repo)
    assert not v.valid
    assert any("stale commit binding" in x or "unverifiable" in x for x in v.violations)


@pytest.mark.parametrize("commit", ["", "abc123", "HEAD", "main", "0" * 39])
def test_a_commit_that_is_not_a_full_sha_is_refused(ok, repo, commit):
    ok["repository_commit"] = commit
    v = _v(ok, repo)
    assert not v.valid
    assert any("40-character commit SHA" in x for x in v.violations)


def test_an_approval_predating_the_reviewed_commit_is_refused(ok, repo):
    """You cannot have reviewed a tree that did not exist yet."""
    ok["reviewed_at"] = "2001-01-01T00:00:00+00:00"
    v = _v(ok, repo)
    assert not v.valid
    assert any("before commit" in x and "cannot have reviewed" in x for x in v.violations)


def test_an_approval_naming_a_different_head_is_refused(ok, repo, head):
    v = _v(ok, repo, expected_commit="f" * 40)
    assert not v.valid
    assert any("stale commit binding" in x for x in v.violations)


# --------------------------------------------------------------------------- #
# Duplicate and contradictory approvals
# --------------------------------------------------------------------------- #
def test_a_second_approval_for_the_same_scope_is_refused(ok, repo):
    sibling = dict(ok, decision="rejected")
    v = _v(ok, repo, siblings=[("other.json", sibling)])
    assert not v.valid
    assert any("duplicate or contradictory approvals" in x for x in v.violations)


def test_a_sibling_for_another_scope_is_not_a_duplicate(ok, repo):
    sibling = dict(ok, scope="unrelated_scope")
    assert _v(ok, repo, siblings=[("other.json", sibling)]).valid


# --------------------------------------------------------------------------- #
# File loading
# --------------------------------------------------------------------------- #
def test_an_absent_artifact_blocks_rather_than_raising(repo):
    v = validate_approval_file(repo / "nope.json", SPEC, repo=repo)
    assert not v.present and not v.valid and not v.satisfied
    assert "has not been taken" in v.detail()


def test_unreadable_json_blocks(repo):
    (repo / "broken.json").write_text("{not json", encoding="utf-8")
    v = validate_approval_file(repo / "broken.json", SPEC, repo=repo)
    assert v.present and not v.valid
    assert any("unreadable JSON" in x for x in v.violations)


def test_a_verdict_never_carries_an_absolute_path(repo, ok):
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    v = validate_approval_file(repo / "approval.json", SPEC, repo=repo)
    assert v.path == "approval.json"
    assert not v.path.startswith("/")


def test_duplicate_approval_files_on_disk_are_detected(repo, ok):
    (repo / "a.json").write_text(json.dumps(ok), encoding="utf-8")
    (repo / "b.json").write_text(json.dumps(ok), encoding="utf-8")
    v = validate_approval_file(repo / "a.json", SPEC, repo=repo)
    assert not v.valid
    assert any("duplicate or contradictory" in x for x in v.violations)


# --------------------------------------------------------------------------- #
# The repository's three real specs
# --------------------------------------------------------------------------- #
def test_the_audit_signoff_requires_independence_and_named_findings(repo, ok):
    payload = dict(ok, artifact_type=AUDIT_SIGNOFF_SPEC.artifact_type,
                   scope=AUDIT_SIGNOFF_SPEC.scope,
                   closed_findings=["AUD-EC-005"],
                   auditor_independent_of_implementer=False)
    v = validate_approval(payload, AUDIT_SIGNOFF_SPEC, repo=repo, path="s.json")
    assert not v.valid
    assert any("does not close required finding" in x for x in v.violations)
    assert any("self-audit does not close a finding" in x for x in v.violations)


def test_the_audit_signoff_must_close_the_r2b_remediation_itself(repo):
    assert "R2B-REMEDIATION" in AUDIT_SIGNOFF_SPEC.required_findings
    assert set(AUDIT_SIGNOFF_SPEC.required_findings) >= {
        "AUD-EC-005", "AUD-EC-006", "AUD-EC-007"}


def test_the_second_review_spec_demands_citations(repo):
    assert "diagnostic_citations" in SECOND_REVIEW_SPEC.extra_required
    assert "group_verdicts" in SECOND_REVIEW_SPEC.extra_required
    assert SECOND_REVIEW_SPEC.scope == "plantdoc_relabelled_groups"


def test_the_freeze_spec_binds_the_effective_dataset_and_both_gates():
    binds = set(FREEZE_APPROVAL_SPEC.required_bindings)
    assert "data/manifests/plantdoc_effective_manifest.csv" in binds
    assert "reports/plantdoc_internal_duplicate_gate.json" in binds
    assert "reports/leakage_gate.json" in binds


# --------------------------------------------------------------------------- #
# Nothing was approved in this repository
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("artifact", [
    "data/manifests/dataset_v1_freeze_approval.json",
    "data/manifests/dataset_v1_freeze.json",
    "reports/DATASET_V1_AUDIT_SIGNOFF.json",
    "human_review/plantdoc_label_second_review/second_review.json",
])
def test_no_approval_artifact_exists_in_the_repository(repo_root, artifact):
    assert not (repo_root / artifact).exists(), (
        f"{artifact} exists; no approval may be fabricated by this work")
