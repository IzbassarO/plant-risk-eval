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

import hashlib
import csv
import json
import shutil
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
from ica26.governance.second_review import (
    EXPECTED_SECOND_REVIEW_GROUPS,
    GROUP_REQUIRED_FIELDS,
    PACKET_MANIFEST_PATH,
    PACKET_MEMBERS_PATH,
    PACKET_REVIEW_PATH,
    SECOND_REVIEW_SCHEMA,
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
        "reviewed_repository_commit": head,
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
# Completed PlantDoc relabel second-review fixtures
# --------------------------------------------------------------------------- #
SECOND_REVIEW_RESOLUTION = (
    "data/exclusions/plantdoc_internal_duplicate_resolution.csv"
)
SECOND_REVIEW_PACKET = (
    "reports/plantdoc_label_second_review/plantdoc_label_second_review.csv"
)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def second_review_repo(tmp_path, repo_root):
    """A real reviewed state containing the deterministic pending packet."""
    for relative in SECOND_REVIEW_SPEC.required_bindings:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo_root / relative, destination)
    for cmd in ("init -q", "add -A",
                "-c user.email=t@e -c user.name=t commit -qm seed"):
        subprocess.run(["git", "-C", str(tmp_path), *cmd.split()], check=True,
                       capture_output=True)
    return tmp_path


def _second_review_payload(repo):
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    stamp = subprocess.run(
        ["git", "-C", str(repo), "show", "-s", "--format=%cI", head],
        capture_output=True, text=True, check=True).stdout.strip()
    with (repo / PACKET_REVIEW_PATH).open(newline="", encoding="utf-8") as fh:
        review_rows = {
            row["display_group_id"]: row for row in csv.DictReader(fh)
        }
    with (repo / PACKET_MEMBERS_PATH).open(newline="", encoding="utf-8") as fh:
        member_rows = list(csv.DictReader(fh))
    packet_digest = _sha256(repo / PACKET_MANIFEST_PATH)
    groups = []
    for group_id in EXPECTED_SECOND_REVIEW_GROUPS:
        row = review_rows[group_id]
        members = sorted(
            (member for member in member_rows
             if member["display_group_id"] == group_id),
            key=lambda member: member["member_id"],
        )
        groups.append({
            "group_id": group_id,
            "reviewed_member_identities": [m["member_id"] for m in members],
            "reviewed_member_sha256": [m["byte_sha256"] for m in members],
            "current_canonical_identity": row["applied_effective_record_id"],
            "current_canonical_label": row["applied_canonical_label"],
            "decision": "agree",
            "confidence": "high",
            "reviewer_id": "independent_reviewer_2",
            "reviewer_role_or_qualification": "plant pathology reviewer",
            "reviewed_at": stamp,
            "diagnostic_rationale": (
                f"Independent diagnostic assessment for {group_id} supports the "
                "current canonical label against the cited source."
            ),
            "diagnostic_citations": [{
                "citation": f"Independent diagnostic source for {group_id}",
                "url": f"https://example.org/diagnostics/{group_id.lower()}",
            }],
            "recommended_action": "accept_current_label",
            "bound_packet_digest": packet_digest,
        })
    return {
        "schema_version": APPROVAL_SCHEMA,
        "artifact_type": SECOND_REVIEW_SPEC.artifact_type,
        "decision": AFFIRMATIVE,
        "scope": SECOND_REVIEW_SPEC.scope,
        "reviewer_id": "independent_reviewer_2",
        "reviewer_role": "plant pathology reviewer",
        "reviewed_at": stamp,
        "reviewed_repository_commit": head,
        "approved_artifacts": {
            relative: _sha256(repo / relative)
            for relative in SECOND_REVIEW_SPEC.required_bindings
        },
        "rationale": (
            "Independently reviewed every retained relabel and its cited diagnostic "
            "evidence against the bound review packet."
        ),
        "not_approved": ["new labels outside the reviewed groups", "training"],
        "review_schema_version": SECOND_REVIEW_SCHEMA,
        "groups": groups,
    }


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
    ok["reviewed_repository_commit"] = "0" * 40
    v = _v(ok, repo)
    assert not v.valid
    assert any("stale reviewed-state binding" in x or "unverifiable" in x
               for x in v.violations)


@pytest.mark.parametrize("commit", ["", "abc123", "HEAD", "main", "0" * 39])
def test_a_commit_that_is_not_a_full_sha_is_refused(ok, repo, commit):
    ok["reviewed_repository_commit"] = commit
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
    assert any("stale reviewed-state binding" in x for x in v.violations)


def _commit(repo, message):
    """Commit all staged changes in a synthetic repo and return its SHA."""
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@e",
                    "-c", "user.name=t", "commit", "-qm", message], check=True,
                   capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_persisted_approval_validates_at_its_descendant_record_state(repo, ok):
    """An approval can name its reviewed candidate, then be committed by itself."""
    candidate = ok["reviewed_repository_commit"]
    lifecycle_spec = ApprovalSpec(
        artifact_type=SPEC.artifact_type,
        scope=SPEC.scope,
        required_bindings=SPEC.required_bindings,
    )
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    new_head = _commit(repo, "record approval")
    assert new_head != candidate

    lifecycle = validate_approval_file(
        repo / "approval.json", lifecycle_spec, repo=repo)
    assert lifecycle.valid, lifecycle.violations
    assert lifecycle.satisfied


def test_two_state_approval_git_history_end_to_end(repo, ok):
    """Review -> record -> validate -> committed input change -> refuse."""
    reviewed_commit = ok["reviewed_repository_commit"]
    lifecycle_spec = ApprovalSpec(
        artifact_type=SPEC.artifact_type,
        scope=SPEC.scope,
        required_bindings=SPEC.required_bindings,
    )
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    approval_record_commit = _commit(repo, "record approval")
    assert approval_record_commit != reviewed_commit

    recorded = validate_approval_file(
        repo / "approval.json", lifecycle_spec, repo=repo)
    assert recorded.valid and recorded.satisfied, recorded.violations

    (repo / "bound.txt").write_text("changed after review\n", encoding="utf-8")
    changed_commit = _commit(repo, "mutate reviewed input")
    assert changed_commit not in {reviewed_commit, approval_record_commit}

    stale = validate_approval_file(
        repo / "approval.json", lifecycle_spec, repo=repo)
    assert not stale.valid and not stale.satisfied
    assert any("changed after its reviewed state" in issue
               or "changed since approval" in issue
               for issue in stale.violations)


def test_reviewed_state_semantics_do_not_depend_on_a_path_allowlist(repo, ok):
    """Applicability follows exact reviewed blobs, not a mutable path allow-list."""
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    _commit(repo, "record approval")

    lifecycle = validate_approval_file(
        repo / "approval.json", SPEC, repo=repo)
    assert lifecycle.valid, lifecycle.violations


def test_reviewed_blob_is_checked_even_when_current_bytes_match_declared(repo, ok):
    """A later artifact cannot be retroactively attributed to an older review."""
    reviewed = ok["reviewed_repository_commit"]
    (repo / "bound.txt").write_text("replacement bytes\n", encoding="utf-8")
    _commit(repo, "replace bound input before writing approval")
    ok["approved_artifacts"]["bound.txt"] = _sha256(repo / "bound.txt")
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    _commit(repo, "record approval claiming the older state")

    verdict = validate_approval_file(
        repo / "approval.json", SPEC, repo=repo)
    assert not verdict.valid
    assert reviewed
    assert any("reviewed-state Git blob" in issue for issue in verdict.violations)


def test_an_approval_record_cannot_exist_in_the_state_it_reviews(repo, ok):
    """The record state must be a real descendant, not a self-reference."""
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    record_commit = _commit(repo, "first approval record")
    payload = json.loads((repo / "approval.json").read_text(encoding="utf-8"))
    payload["reviewed_repository_commit"] = record_commit
    (repo / "approval.json").write_text(json.dumps(payload), encoding="utf-8")
    _commit(repo, "rewrite record to point at itself")

    verdict = validate_approval_file(
        repo / "approval.json", SPEC, repo=repo)
    assert not verdict.valid
    assert any("already existed in the reviewed state" in issue
               for issue in verdict.violations)


def test_a_divergent_reviewed_commit_never_authorizes_current_branch(repo, ok):
    """A full Git SHA from another branch is not a valid past state of HEAD."""
    base = ok["reviewed_repository_commit"]
    primary_branch = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "checkout", "-qb", "divergent"],
                   check=True, capture_output=True)
    (repo / "branch-only.txt").write_text("divergent\n", encoding="utf-8")
    divergent = _commit(repo, "divergent reviewed candidate")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", primary_branch],
                   check=True, capture_output=True)
    assert base != divergent
    ok["reviewed_repository_commit"] = divergent
    (repo / "approval.json").write_text(json.dumps(ok), encoding="utf-8")
    _commit(repo, "record stale branch approval")

    verdict = validate_approval_file(
        repo / "approval.json", SPEC, repo=repo)
    assert not verdict.valid
    assert any("not an ancestor" in issue for issue in verdict.violations)


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
    assert not v.valid and not v.satisfied
    assert any("approval-record state is missing" in issue for issue in v.violations)


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


def _group(payload, group_id):
    return next(group for group in payload["groups"]
                if group["group_id"] == group_id)


def test_the_second_review_spec_demands_self_contained_packet_bound_groups():
    assert set(SECOND_REVIEW_SPEC.extra_required) == {
        "review_schema_version", "groups"}
    assert PACKET_MANIFEST_PATH in SECOND_REVIEW_SPEC.required_bindings
    assert PACKET_MEMBERS_PATH in SECOND_REVIEW_SPEC.required_bindings
    assert SECOND_REVIEW_SPEC.scope == "plantdoc_relabelled_groups"


def test_three_complete_agree_reviews_are_accepted(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert verdict.valid, verdict.violations
    assert verdict.satisfied


def test_second_review_missing_required_group_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    payload["groups"] = [g for g in payload["groups"] if g["group_id"] != "G08"]
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("missing required group(s) ['G08']" in issue for issue in verdict.violations)


def test_second_review_extra_group_is_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    extra = dict(payload["groups"][0], group_id="G99")
    payload["groups"].append(extra)
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("unexpected group(s) ['G99']" in issue for issue in verdict.violations)


def test_duplicate_and_contradictory_group_entries_are_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    duplicate = dict(_group(payload, "G07"), decision="disagree",
                     recommended_action="replace_current_label",
                     proposed_canonical_label="Potato leaf early blight")
    payload["groups"].append(duplicate)
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("duplicate group entries ['G07']" in issue for issue in verdict.violations)


def test_generic_meaningless_arrays_are_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    payload.pop("groups")
    payload["group_verdicts"] = ["unrelated"]
    payload["diagnostic_citations"] = ["unstructured"]
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("missing or placeholder required field" in issue for issue in verdict.violations)
    assert any("'groups' must be a list" in issue for issue in verdict.violations)


def test_legacy_generic_arrays_cannot_contradict_valid_group_records(
        second_review_repo):
    payload = _second_review_payload(second_review_repo)
    payload["group_verdicts"] = ["unrelated"]
    payload["diagnostic_citations"] = ["unstructured"]
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("legacy generic second-review field(s) are forbidden" in issue
               for issue in verdict.violations)


@pytest.mark.parametrize("field", sorted(GROUP_REQUIRED_FIELDS - {"group_id"}))
def test_every_per_group_field_is_independently_required(
        second_review_repo, field):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G08").pop(field)
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid, field
    assert any("groups[G08] is missing required field" in issue and field in issue
               for issue in verdict.violations)


@pytest.mark.parametrize("bad_decision", [
    "", " ", "pending", "approved", "unrelated", "unknown", "todo", "n/a",
])
def test_group_decision_uses_a_strict_vocabulary(second_review_repo, bad_decision):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G10")["decision"] = bad_decision
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G10].decision" in issue and "invalid" in issue
               for issue in verdict.violations)


@pytest.mark.parametrize("bad_confidence", ["", "very high", "unknown", 101, -1, 0.7])
def test_group_confidence_uses_a_strict_vocabulary(second_review_repo, bad_confidence):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["confidence"] = bad_confidence
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G07].confidence" in issue for issue in verdict.violations)


def test_member_identities_and_hashes_must_match_the_packet(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    group = _group(payload, "G07")
    group["reviewed_member_identities"][0] = "G07-forged"
    group["reviewed_member_sha256"][1] = "f" * 64
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("reviewed_member_identities" in issue and "do not match packet" in issue
               for issue in verdict.violations)
    assert any("reviewed_member_sha256" in issue and "does not match" in issue
               for issue in verdict.violations)


def test_current_canonical_identity_and_label_must_match_packet(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    group = _group(payload, "G08")
    group["current_canonical_identity"] = "erec-forged"
    group["current_canonical_label"] = "Potato leaf late blight"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("current_canonical_identity" in issue and "packet value" in issue
               for issue in verdict.violations)
    assert any("current_canonical_label" in issue and "packet value" in issue
               for issue in verdict.violations)


def test_group_reviewer_must_be_independent_and_qualified(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    group = _group(payload, "G07")
    group["reviewer_id"] = "human_reviewer_1"
    group["reviewer_role_or_qualification"] = "unknown"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("first reviewer" in issue and "independent" in issue
               for issue in verdict.violations)
    assert any("reviewer_role_or_qualification" in issue and "placeholder" in issue
               for issue in verdict.violations)


@pytest.mark.parametrize("bad_timestamp", [
    "", "pending", "2026-08-03T14:28:00", "2026-13-03T14:28:00+05:00",
    "2999-01-01T00:00:00+00:00",
])
def test_group_timestamp_is_strict_offset_iso8601(second_review_repo, bad_timestamp):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G10")["reviewed_at"] = bad_timestamp
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G10].reviewed_at" in issue for issue in verdict.violations)


@pytest.mark.parametrize("placeholder", [
    "", "   ", "unstructured", "unknown", "todo", "n/a", "pending",
])
def test_group_rationale_placeholders_are_refused(second_review_repo, placeholder):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G08")["diagnostic_rationale"] = placeholder
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G08].diagnostic_rationale" in issue
               for issue in verdict.violations)


def test_one_group_cannot_supply_citations_for_another(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["diagnostic_citations"].append({
        "citation": "A second independent source for the G07 diagnosis",
        "url": "https://example.org/diagnostics/g07-second",
    })
    _group(payload, "G08")["diagnostic_citations"] = []
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G08].diagnostic_citations must contain citation evidence" in issue
               for issue in verdict.violations)


@pytest.mark.parametrize(("citation", "url"), [
    ("unstructured", "https://example.org/source"),
    ("unknown", "https://example.org/source"),
    ("A plausible source title", "n/a"),
    ("A plausible source title", "javascript:alert(1)"),
    ("A plausible source title", "example.org/no-scheme"),
])
def test_citations_are_structured_and_nonplaceholder(
        second_review_repo, citation, url):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["diagnostic_citations"] = [{
        "citation": citation, "url": url}]
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("groups[G07].diagnostic_citations[0]" in issue
               for issue in verdict.violations)


def test_bare_citation_strings_are_refused(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G10")["diagnostic_citations"] = ["unstructured"]
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("must be an object with exactly citation and url" in issue
               for issue in verdict.violations)


def test_approved_second_review_cannot_hide_uncertainty(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    group = _group(payload, "G10")
    group["decision"] = "uncertain"
    group["diagnostic_citations"] = []
    group["recommended_action"] = "escalate"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid and not verdict.satisfied
    assert any("requires three independently valid agree decisions" in issue
               for issue in verdict.violations)


def test_approved_second_review_cannot_hide_disagreement(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    group = _group(payload, "G08")
    group["decision"] = "disagree"
    group["recommended_action"] = "replace_current_label"
    group["proposed_canonical_label"] = "Potato leaf late blight"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid and not verdict.satisfied
    assert any("requires three independently valid agree decisions" in issue
               for issue in verdict.violations)


def test_uncertain_cannot_recommend_accepting_current_label(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    payload["decision"] = "deferred"
    group = _group(payload, "G08")
    group["decision"] = "uncertain"
    group["diagnostic_citations"] = []
    group["recommended_action"] = "accept_current_label"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("recommended_action" in issue and "invalid for decision 'uncertain'" in issue
               for issue in verdict.violations)


def test_structured_dissent_is_valid_but_cannot_satisfy_readiness(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    payload["decision"] = "deferred"
    disagree = _group(payload, "G08")
    disagree["decision"] = "disagree"
    disagree["recommended_action"] = "replace_current_label"
    disagree["proposed_canonical_label"] = "Potato leaf late blight"
    uncertain = _group(payload, "G10")
    uncertain["decision"] = "uncertain"
    uncertain["diagnostic_citations"] = []
    uncertain["recommended_action"] = "exclude_record"
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert verdict.valid, verdict.violations
    assert not verdict.satisfied
    assert "not 'approved'" in verdict.detail()


def test_stale_packet_digest_is_refused_per_group(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    _group(payload, "G07")["bound_packet_digest"] = "0" * 64
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("bound_packet_digest is stale" in issue for issue in verdict.violations)


def test_packet_manifest_detects_changed_packet_bytes(second_review_repo):
    payload = _second_review_payload(second_review_repo)
    packet = second_review_repo / PACKET_MEMBERS_PATH
    packet.write_text(packet.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("packet artifact" in issue and "is stale" in issue
               for issue in verdict.violations)


def test_a_new_resolution_relabel_cannot_escape_the_exact_group_contract(
        second_review_repo):
    resolution = second_review_repo / SECOND_REVIEW_RESOLUTION
    with resolution.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames
        rows = list(reader)
    victim = next(row for row in rows
                  if row["display_group_id"] == "G01"
                  and row["remediation_action"] == "retain_canonical")
    victim["effective_class_label"] = "A newly asserted canonical label"
    with resolution.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    payload = _second_review_payload(second_review_repo)
    verdict = validate_approval(payload, SECOND_REVIEW_SPEC,
                                repo=second_review_repo, path="second_review.json")
    assert not verdict.valid
    assert any("current duplicate-resolution table" in issue
               and "unexpected group(s) ['G01']" in issue
               for issue in verdict.violations)


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
