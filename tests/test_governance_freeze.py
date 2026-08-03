"""Fail-closed technical Dataset V1 freeze-record validation.

These tests build a deliberately tiny Git checkout containing synthetic bytes
for every real control-plane path.  They prove the technical record can be
valid without manufacturing a human decision in this repository, and then pin
the ways a plausible-looking freeze marker must still be refused.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

import ica26.governance.freeze as freeze
from ica26.governance.approvals import (
    AFFIRMATIVE,
    APPROVAL_SCHEMA,
    FREEZE_APPROVAL_SPEC,
)
from ica26.governance.freeze import (
    DATASET_NAME,
    FREEZE_APPROVAL_PATH,
    FREEZE_ARTIFACT_PATH,
    FREEZE_DECISION,
    FreezeError,
    READINESS_INPUT_PATHS,
    READINESS_PATH,
    build_freeze_payload,
    freeze_bound_paths,
    validate_freeze_file,
)


_REAL_FRESH_READINESS_PROBLEM = freeze._fresh_readiness_problem


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(root: Path, relative: str | Path, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=freeze-test@example.test",
         "-c", "user.name=Freeze Test", "commit", "-qm", message)
    return _git(root, "rev-parse", "HEAD")


def _commit_stamp(root: Path, commit: str) -> str:
    return _git(root, "show", "-s", "--format=%cI", commit)


@pytest.fixture(autouse=True)
def _synthetic_readiness_recomputation(monkeypatch):
    """Keep byte-level freeze tests independent of the full dataset pipeline.

    Production always executes the authoritative readiness builder.  These tiny
    synthetic repositories intentionally do not contain the whole pipeline, so
    individual tests substitute only its successful result; the refusal path is
    exercised explicitly below.
    """
    monkeypatch.setattr(freeze, "_fresh_readiness_problem", lambda _repo: None)


def _ready_report(root: Path) -> dict:
    """A minimal but exhaustive *pre-decision* readiness assessment."""
    return {
        "schema_version": "1.0",
        "dataset": DATASET_NAME,
        "status": "ready",
        "frozen": False,
        "satisfied": 1,
        "blocked": 0,
        "blockers": [],
        "conditions": [{"id": "synthetic_all_controls", "status": "satisfied"}],
        "input_digests": {
            name: _sha256(root / relative)
            for name, relative in READINESS_INPUT_PATHS.items()
        },
        "provenance": {"command": "synthetic-test", "freezes_nothing": True},
    }


def test_authoritative_readiness_check_executes_and_requires_zero(tmp_path):
    script = _write(
        tmp_path, "scripts/build_dataset_v1_freeze_readiness.py",
        "import sys\nraise SystemExit(0 if sys.argv[1:] == ['--check'] else 9)\n",
    )
    assert script.is_file()
    assert _REAL_FRESH_READINESS_PROBLEM(tmp_path) is None

    script.write_text("raise SystemExit(7)\n", encoding="utf-8")
    problem = _REAL_FRESH_READINESS_PROBLEM(tmp_path)
    assert problem is not None and "returned 7" in problem


def _prepare_ready_repo(root: Path) -> Path:
    """Create a clean ready-for-freeze checkout over fully bound fake inputs.

    The approval names the initial candidate commit.  The successor commits
    only the approval/readiness, exercising the production lifecycle-descendant
    rule rather than bypassing it.
    """
    _git(root, "init", "-q")

    deferred = {
        str(FREEZE_APPROVAL_PATH),
        str(READINESS_PATH),
        str(FREEZE_ARTIFACT_PATH),
    }
    all_inputs = set(freeze_bound_paths()) | {
        str(path) for path in READINESS_INPUT_PATHS.values()
    }
    for relative in sorted(all_inputs - deferred):
        _write(root, relative, f"synthetic authoritative bytes for {relative}\n")
    candidate = _commit(root, "seed frozen inputs")

    approval = {
        "schema_version": APPROVAL_SCHEMA,
        "artifact_type": FREEZE_APPROVAL_SPEC.artifact_type,
        "decision": AFFIRMATIVE,
        "scope": FREEZE_APPROVAL_SPEC.scope,
        "reviewer_id": "synthetic_governance_reviewer",
        "reviewer_role": "dataset governance owner",
        "reviewed_at": _commit_stamp(root, candidate),
        "reviewed_repository_commit": candidate,
        "approved_artifacts": {
            relative: _sha256(root / relative)
            for relative in FREEZE_APPROVAL_SPEC.required_bindings
        },
        "rationale": (
            "Synthetic test approval binds every real required input so the "
            "technical freeze validator can be tested without approving Dataset V1."
        ),
        "not_approved": ["training", "new datasets", "future label changes"],
    }
    _write(root, FREEZE_APPROVAL_PATH, json.dumps(approval, indent=2, sort_keys=True) + "\n")
    _write(root, READINESS_PATH,
           json.dumps(_ready_report(root), indent=2, sort_keys=True) + "\n")
    _commit(root, "record approval and pre-decision readiness")
    return root


@pytest.fixture
def ready_repo(tmp_path: Path) -> Path:
    return _prepare_ready_repo(tmp_path)


@pytest.fixture
def frozen_repo(ready_repo: Path) -> Path:
    """A committed, valid technical record over fake but fully bound inputs."""
    root = ready_repo

    payload = build_freeze_payload(root)
    _write(root, FREEZE_ARTIFACT_PATH, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _commit(root, "record deterministic technical freeze")
    return root


def test_a_committed_complete_freeze_record_is_valid_and_deterministic(frozen_repo):
    verdict = validate_freeze_file(repo=frozen_repo)
    assert verdict.valid, verdict.violations
    assert verdict.frozen

    stored = json.loads((frozen_repo / FREEZE_ARTIFACT_PATH).read_text(encoding="utf-8"))
    assert build_freeze_payload(frozen_repo) == stored
    assert stored["decision"] == FREEZE_DECISION
    assert set(stored["frozen_artifacts"]) == set(freeze_bound_paths())
    assert stored["frozen_repository_commit"] == _git(
        frozen_repo, "rev-parse", "HEAD^")
    assert stored["dataset_fingerprint"] == freeze.build_dataset_fingerprint(
        frozen_repo)
    assert stored["approval"]["reviewed_repository_commit"]
    assert stored["approval"]["approval_record_commit"]


def test_freeze_dependency_graph_expands_all_direct_control_inputs():
    paths = set(freeze_bound_paths())
    assert set(FREEZE_APPROVAL_SPEC.required_bindings) <= paths
    assert set(freeze.SECOND_REVIEW_SPEC.required_bindings) <= paths
    assert set(freeze.AUDIT_SIGNOFF_SPEC.required_bindings) <= paths
    assert {str(path) for path in READINESS_INPUT_PATHS.values()} <= paths
    assert {
        "configs/action_taxonomy.yaml",
        "data/mapping/action_mapping_review.csv",
        "data/mapping/action_mapping_approved.csv",
        "data/mapping/action_mapping_apply_summary.json",
    } <= paths


def _materializer_module():
    script = Path(__file__).resolve().parents[1] / "scripts/materialize_dataset_v1_freeze.py"
    spec = importlib.util.spec_from_file_location("test_materialize_dataset_v1_freeze", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_materializer_writes_once_then_requires_a_committed_checkout(ready_repo, monkeypatch):
    materializer = _materializer_module()
    monkeypatch.setattr(materializer, "REPO", ready_repo)
    target = ready_repo / FREEZE_ARTIFACT_PATH

    assert materializer._write() == 0
    assert target.exists()
    assert materializer._check() == 3  # present but uncommitted is a hard refusal

    _commit(ready_repo, "commit technical freeze record")
    assert materializer._check() == 0
    assert materializer._write() == 0  # a valid existing record is never rewritten


def test_materializer_distinguishes_absence_from_an_invalid_record(tmp_path, monkeypatch):
    materializer = _materializer_module()
    monkeypatch.setattr(materializer, "REPO", tmp_path)
    assert materializer._check() == 1

    _write(tmp_path, FREEZE_ARTIFACT_PATH, "{}\n")
    assert materializer._check() == 3


@pytest.mark.parametrize("arbitrary", [
    {},
    {"status": "ready"},
    {"frozen": True},
    {"schema_version": "unrelated", "artifact_type": "something_else"},
])
def test_missing_or_arbitrary_freeze_record_never_means_frozen(tmp_path, arbitrary):
    missing = validate_freeze_file(repo=tmp_path, require_clean_worktree=False)
    assert not missing.present and not missing.valid and not missing.frozen

    _write(tmp_path, FREEZE_ARTIFACT_PATH, json.dumps(arbitrary) + "\n")
    bare = validate_freeze_file(repo=tmp_path, require_clean_worktree=False)
    assert bare.present and not bare.valid and not bare.frozen
    assert any("misses required field" in issue for issue in bare.violations)


@pytest.mark.parametrize(("field", "bad_value", "expected"), [
    ("schema_version", "ica26.governance.dataset_v1_technical_freeze/0",
     "schema_version"),
    ("artifact_type", "unrelated_json", "artifact_type"),
    ("dataset", "Another Dataset", "does not identify Dataset V1"),
    ("decision", "ready", "decision is not 'frozen'"),
])
def test_wrong_freeze_identity_fields_are_refused(
        frozen_repo, field, bad_value, expected):
    path = frozen_repo / FREEZE_ARTIFACT_PATH
    record = json.loads(path.read_text(encoding="utf-8"))
    record[field] = bad_value
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid and not verdict.frozen
    assert any(expected in issue for issue in verdict.violations)


def test_freeze_record_requires_the_exact_closed_artifact_map(frozen_repo):
    path = frozen_repo / FREEZE_ARTIFACT_PATH
    record = json.loads(path.read_text(encoding="utf-8"))
    omitted = next(iter(record["frozen_artifacts"]))
    record["frozen_artifacts"].pop(omitted)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict = validate_freeze_file(path, repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("does not bind exactly the required artifacts" in issue
               for issue in verdict.violations)
    assert any(omitted in issue for issue in verdict.violations)


@pytest.mark.parametrize("reference", ["approval", "readiness"])
def test_stale_named_reference_digest_is_refused(frozen_repo, reference):
    path = frozen_repo / FREEZE_ARTIFACT_PATH
    record = json.loads(path.read_text(encoding="utf-8"))
    record[reference]["sha256"] = "0" * 64
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any(f"{reference} digest disagrees" in issue for issue in verdict.violations)


def test_stale_dataset_manifest_digest_and_fingerprint_are_refused(frozen_repo):
    path = frozen_repo / FREEZE_ARTIFACT_PATH
    record = json.loads(path.read_text(encoding="utf-8"))
    manifest = str(freeze.DATASET_FINGERPRINT_PATHS["plantdoc_effective_manifest"])
    record["frozen_artifacts"][manifest] = "0" * 64
    record["dataset_fingerprint"]["sha256"] = "f" * 64
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any(manifest in issue for issue in verdict.violations)
    assert any("fresh reconstruction" in issue for issue in verdict.violations)


def test_tampering_any_bound_data_input_invalidates_the_freeze(frozen_repo):
    target = frozen_repo / FREEZE_APPROVAL_SPEC.required_bindings[0]
    target.write_text("altered after the technical freeze\n", encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("changed after freeze" in issue for issue in verdict.violations)
    assert any("freeze approval is not valid" in issue for issue in verdict.violations)


@pytest.mark.parametrize("missing", [
    "configs/harm_matrix_template.yaml",
    "configs/action_taxonomy.yaml",
    "data/mapping/action_mapping_approved.csv",
    "human_review/plantdoc_label_second_review/second_review.json",
    "reports/DATASET_V1_AUDIT_SIGNOFF.json",
    str(FREEZE_APPROVAL_PATH),
])
def test_absent_human_or_scientific_dependency_blocks_freeze(frozen_repo, missing):
    (frozen_repo / missing).unlink()

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid and not verdict.frozen
    assert any(missing in issue or "freeze approval" in issue
               for issue in verdict.violations)


def test_approval_bound_to_a_different_reviewed_state_is_refused(frozen_repo):
    path = frozen_repo / FREEZE_ARTIFACT_PATH
    record = json.loads(path.read_text(encoding="utf-8"))
    record["approval"]["reviewed_repository_commit"] = record[
        "frozen_repository_commit"]
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("reviewed commit disagrees" in issue for issue in verdict.violations)


def test_freeze_artifact_copied_onto_a_later_commit_is_refused(ready_repo):
    stale_record = build_freeze_payload(ready_repo)
    _write(ready_repo, "unrelated-record-metadata.txt", "later state\n")
    _commit(ready_repo, "advance beyond the state used to build the freeze record")
    _write(ready_repo, FREEZE_ARTIFACT_PATH,
           json.dumps(stale_record, indent=2, sort_keys=True) + "\n")
    _commit(ready_repo, "copy stale technical freeze artifact")

    verdict = validate_freeze_file(repo=ready_repo)
    assert not verdict.valid and not verdict.frozen
    assert any("immediate successor" in issue for issue in verdict.violations)


def test_committed_dataset_change_after_ready_freeze_is_refused(frozen_repo):
    target = frozen_repo / FREEZE_APPROVAL_SPEC.required_bindings[0]
    target.write_text("committed mutation after ready state\n", encoding="utf-8")
    _commit(frozen_repo, "change an approved dataset input after freeze")

    verdict = validate_freeze_file(repo=frozen_repo)
    assert not verdict.valid and not verdict.frozen
    assert any("changed after freeze" in issue or "changed after its reviewed state" in issue
               for issue in verdict.violations)


def test_freeze_refuses_a_readiness_record_that_fails_fresh_recomputation(
        frozen_repo, monkeypatch):
    """Current digests cannot rescue a hand-authored ready-looking assessment."""
    monkeypatch.setattr(
        freeze, "_fresh_readiness_problem",
        lambda _repo: "fresh readiness --check returned 3: persisted assessment is stale")

    with pytest.raises(FreezeError, match="fresh readiness --check returned 3"):
        build_freeze_payload(frozen_repo)

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("fresh readiness --check returned 3" in issue
               for issue in verdict.violations)


def test_freeze_never_treats_a_bare_approval_file_as_a_human_decision(frozen_repo):
    approval_path = frozen_repo / FREEZE_APPROVAL_PATH
    approval_path.write_text('{"approved": true}\n', encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("freeze approval is not valid" in issue for issue in verdict.violations)


def test_readiness_cannot_omit_a_live_control_plane_digest(frozen_repo):
    readiness_path = frozen_repo / READINESS_PATH
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    omitted = next(iter(READINESS_INPUT_PATHS))
    readiness["input_digests"].pop(omitted)
    readiness_path.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n",
                              encoding="utf-8")

    verdict = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert not verdict.valid
    assert any("input_digests omits required input" in issue
               for issue in verdict.violations)


def test_final_freeze_must_be_validated_from_a_clean_checkout(frozen_repo):
    _write(frozen_repo, "untracked-after-freeze.txt", "not part of the freeze\n")

    strict = validate_freeze_file(repo=frozen_repo)
    assert not strict.valid
    assert any("worktree is not clean" in issue for issue in strict.violations)

    diagnostic = validate_freeze_file(repo=frozen_repo, require_clean_worktree=False)
    assert diagnostic.valid, diagnostic.violations
