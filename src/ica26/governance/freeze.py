"""Fail-closed validation for the deterministic Dataset V1 technical freeze.

The human approval and the technical freeze record deliberately have different
jobs.  An approval records a human decision over a candidate tree.  This module
does not create that decision; it can only turn an already-valid decision and a
current, fully satisfied readiness assessment into a canonical manifest of the
bytes that were frozen.

Keeping the two artifacts separate avoids a circular digest dependency: adding
an approval changes the readiness condition which reports that approval, so an
approval must bind the immutable data/evidence inputs rather than the dynamic
readiness report.  The technical record can then bind both final artifacts.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .approvals import (
    AUDIT_SIGNOFF_SPEC,
    FREEZE_APPROVAL_SPEC,
    SECOND_REVIEW_SPEC,
    _git_blob_sha256,
    _git_path_exists,
    _is_ancestor,
    _path_touch_commits,
    current_commit,
    validate_approval_file,
)


FREEZE_SCHEMA = "ica26.governance.dataset_v1_technical_freeze/1"
FREEZE_ARTIFACT_TYPE = "dataset_v1_technical_freeze"
FREEZE_DECISION = "frozen"
DATASET_NAME = "Dataset V1"

FREEZE_ARTIFACT_PATH = Path("data/manifests/dataset_v1_freeze.json")
FREEZE_APPROVAL_PATH = Path("data/manifests/dataset_v1_freeze_approval.json")
READINESS_PATH = Path("reports/dataset_v1_freeze_readiness.json")
READINESS_SCHEMA = "1.0"
DATASET_FINGERPRINT_SCHEMA = "ica26.governance.dataset-v1-fingerprint/1"
DATASET_FINGERPRINT_ALGORITHM = "sha256-canonical-artifact-map-v1"

#: The two manifests which constitute Dataset V1's record identity. The
#: technical record binds all mappings, controls, and evidence separately; this
#: compact fingerprint makes the exact composite dataset independently
#: reconstructible and easy to compare.
DATASET_FINGERPRINT_PATHS: dict[str, Path] = {
    "plantdoc_effective_manifest": Path(
        "data/manifests/plantdoc_effective_manifest.csv"),
    "plantvillage_manifest": Path("data/manifests/plantvillage_manifest.csv"),
}

#: Every file whose digest the readiness report records.  This is deliberately
#: one named map, shared with the readiness builder, so a checker cannot accept
#: a ready-looking report with an omitted or silently stale control-plane input.
READINESS_INPUT_PATHS: dict[str, Path] = {
    "plantdoc_summary": Path("data/manifests/plantdoc_summary.json"),
    "plantvillage_summary": Path("data/manifests/plantvillage_summary.json"),
    "plantdoc_manifest": Path("data/manifests/plantdoc_manifest.csv"),
    "plantvillage_manifest": Path("data/manifests/plantvillage_manifest.csv"),
    "plantvillage_source_snapshot": Path("data/manifests/plantvillage_source_snapshot.json"),
    "effective_manifest": Path("data/manifests/plantdoc_effective_manifest.csv"),
    "duplicate_resolution": Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv"),
    "leakage_gate": Path("reports/leakage_gate.json"),
    "leakage_search_summary": Path(
        "reports/leakage_plantvillage_vs_plantdoc_summary.json"),
    "internal_duplicate_gate": Path("reports/plantdoc_internal_duplicate_gate.json"),
    "action_mapping_review": Path("data/mapping/action_mapping_review.csv"),
    "evaluation_scope": Path("configs/evaluation_scope.yaml"),
    "harm_matrix": Path("configs/harm_matrix_template.yaml"),
    "human_review_evidence": Path("human_review/evidence_manifest.json"),
    "second_review_packet": Path(
        "reports/plantdoc_label_second_review/packet_manifest.json"),
    "second_review": Path("human_review/plantdoc_label_second_review/second_review.json"),
    "audit_signoff": Path("reports/DATASET_V1_AUDIT_SIGNOFF.json"),
    "freeze_approval": FREEZE_APPROVAL_PATH,
}


def freeze_bound_paths() -> tuple[str, ...]:
    """The closed direct dependency set of a technical freeze record.

    Readiness, second review, and audit approvals are transitive authorities.
    Expanding their declared inputs here makes that dependency graph explicit in
    the technical record instead of hiding it behind one parent JSON digest.
    """
    return tuple(sorted({
        *FREEZE_APPROVAL_SPEC.required_bindings,
        *SECOND_REVIEW_SPEC.required_bindings,
        *AUDIT_SIGNOFF_SPEC.required_bindings,
        *(str(path) for path in READINESS_INPUT_PATHS.values()),
        str(FREEZE_APPROVAL_PATH),
        str(READINESS_PATH),
    }))


class FreezeError(RuntimeError):
    """Raised when a caller asks to materialize a record before it is safe."""


@dataclass
class FreezeVerdict:
    """A machine-readable explanation of a finalized freeze record."""

    path: str
    present: bool
    valid: bool
    violations: list[str] = field(default_factory=list)

    @property
    def frozen(self) -> bool:
        return self.present and self.valid

    def detail(self) -> str:
        if not self.present:
            return (f"no validated technical freeze record at {self.path}; "
                    "Dataset V1 is not frozen")
        if self.violations:
            shown = self.violations[:3]
            more = (f" (+{len(self.violations) - len(shown)} more)"
                    if len(self.violations) > len(shown) else "")
            return f"{len(self.violations)} problem(s): " + "; ".join(shown) + more
        return "valid technical freeze record bound to the current approved inputs"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "present": self.present,
            "valid": self.valid,
            "frozen": self.frozen,
            "violations": sorted(self.violations),
        }


@dataclass
class FreezePreparation:
    """Inputs available for a technical record, or concrete reasons to refuse."""

    readiness: Optional[dict]
    approval: Optional[dict]
    violations: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.violations and self.readiness is not None and self.approval is not None

    def detail(self) -> str:
        if self.ready:
            return "all readiness, approval, and bound-input checks are satisfied"
        return "; ".join(self.violations[:5]) or "freeze inputs are unavailable"


def sha256_of(path: str | Path) -> str:
    """SHA-256 one regular artifact without buffering it in memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_dataset_fingerprint(repo: str | Path = ".") -> dict:
    """Freshly reconstruct Dataset V1's composite identity from manifest bytes."""
    root = Path(repo).resolve()
    artifacts: dict[str, dict[str, str]] = {}
    for name, relative in sorted(DATASET_FINGERPRINT_PATHS.items()):
        target = root / relative
        if target.is_symlink() or not target.is_file():
            raise FreezeError(
                f"cannot fingerprint Dataset V1: {relative} is absent or not a regular file")
        artifacts[name] = {"path": str(relative), "sha256": sha256_of(target)}
    canonical = json.dumps(
        artifacts, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return {
        "schema_version": DATASET_FINGERPRINT_SCHEMA,
        "algorithm": DATASET_FINGERPRINT_ALGORITHM,
        "sha256": hashlib.sha256(canonical).hexdigest(),
        "artifacts": artifacts,
    }


def _is_sha256(value: object) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _repo_relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except (OSError, ValueError):
        return str(path)


def _load_json(path: Path) -> tuple[Optional[dict], Optional[str]]:
    if not path.is_file():
        return None, "is absent"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report refusal rather than crash
        return None, f"is unreadable JSON ({type(exc).__name__}: {exc})"
    if not isinstance(payload, dict):
        return None, f"is {type(payload).__name__}, expected a JSON object"
    return payload, None


def _readiness_problems(repo: Path, readiness: Optional[dict]) -> list[str]:
    """Validate the *current* pre-decision readiness report exhaustively."""
    if readiness is None:
        return [f"readiness report at {READINESS_PATH} is absent or unreadable"]

    problems: list[str] = []
    if readiness.get("schema_version") != READINESS_SCHEMA:
        problems.append(
            f"readiness schema_version {readiness.get('schema_version')!r} != "
            f"{READINESS_SCHEMA!r}")
    if readiness.get("dataset") != DATASET_NAME:
        problems.append("readiness report does not identify Dataset V1")
    if readiness.get("status") != "ready":
        problems.append("readiness report is not ready")
    # The readiness builder is explicitly decision-free.  A true marker here
    # would recreate the old 'file exists therefore frozen' vulnerability.
    if readiness.get("frozen") is not False:
        problems.append("pre-decision readiness report must declare frozen=false")
    if readiness.get("blockers") != []:
        problems.append("ready readiness report has non-empty blockers")

    conditions = readiness.get("conditions")
    if not isinstance(conditions, list) or not conditions:
        problems.append("ready readiness report has no condition list")
    else:
        ids: list[str] = []
        for index, condition in enumerate(conditions):
            if not isinstance(condition, dict):
                problems.append(f"readiness condition {index} is not an object")
                continue
            cid = condition.get("id")
            if not isinstance(cid, str) or not cid.strip():
                problems.append(f"readiness condition {index} has no identifier")
            else:
                ids.append(cid)
            if condition.get("status") != "satisfied":
                problems.append(f"readiness condition {cid!r} is not satisfied")
        if len(ids) != len(set(ids)):
            problems.append("readiness report has duplicate condition identifiers")
        if readiness.get("satisfied") != len(conditions) or readiness.get("blocked") != 0:
            problems.append("readiness counts do not agree with its all-satisfied condition list")

    provenance = readiness.get("provenance")
    if not isinstance(provenance, dict) or provenance.get("freezes_nothing") is not True:
        problems.append("readiness report does not prove that it makes no freeze decision")

    digests = readiness.get("input_digests")
    if not isinstance(digests, dict):
        problems.append("readiness report has no input_digests map")
    else:
        expected = set(READINESS_INPUT_PATHS)
        actual = set(digests)
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            problems.append(f"readiness input_digests omits required input(s): {missing}")
        if extra:
            problems.append(f"readiness input_digests has unrecognised input(s): {extra}")
        for name, relpath in READINESS_INPUT_PATHS.items():
            declared = digests.get(name)
            target = repo / relpath
            if not _is_sha256(declared):
                problems.append(f"readiness input '{name}' has no SHA-256 digest")
            elif target.is_symlink() or not target.is_file():
                problems.append(
                    f"readiness input '{name}' is absent or not a regular file at {relpath}")
            elif sha256_of(target) != str(declared).lower():
                problems.append(f"readiness input '{name}' changed after assessment")
    return problems


def _fresh_readiness_problem(repo: Path) -> Optional[str]:
    """Require equality with a fresh, authoritative readiness recomputation.

    A digest map proves only that listed files are current.  It cannot prove
    that a hand-written ``status=ready`` report applied every policy predicate.
    The readiness builder's ``--check`` mode recomputes all conditions and
    compares its deterministic output byte-for-byte, so it is the authority for
    that question.  This call is deliberately made again at the final boundary
    rather than trusting a prior shell step or the JSON's self-description.
    """
    script = repo / "scripts" / "build_dataset_v1_freeze_readiness.py"
    if not script.is_file():
        return "cannot freshly validate readiness: builder script is absent"
    try:
        run = subprocess.run(
            [sys.executable, str(script), "--check"], cwd=str(repo),
            capture_output=True, text=True, timeout=600)
    except Exception as exc:  # noqa: BLE001
        return ("cannot freshly validate readiness: "
                f"{type(exc).__name__}: {exc}")
    if run.returncode == 0:
        return None
    output = " ".join((run.stdout + "\n" + run.stderr).split())
    if len(output) > 360:
        output = output[:357] + "..."
    return (f"fresh readiness --check returned {run.returncode}"
            + (f": {output}" if output else ""))


def prepare_freeze(repo: str | Path = ".") -> FreezePreparation:
    """Return the validated inputs from which a technical record may be built.

    This performs no write and never treats a ready-looking JSON file as an
    authority by itself: its declared input digests, every condition, and the
    separately validated human approval are all checked again.
    """
    root = Path(repo).resolve()
    readiness, read_error = _load_json(root / READINESS_PATH)
    problems = ([f"readiness report {read_error}"] if read_error else [])
    problems.extend(_readiness_problems(root, readiness))
    if not problems:
        fresh_problem = _fresh_readiness_problem(root)
        if fresh_problem:
            problems.append(fresh_problem)

    approval_path = root / FREEZE_APPROVAL_PATH
    approval_payload, approval_error = _load_json(approval_path)
    if approval_error:
        problems.append(f"freeze approval {approval_error}")
    approval_verdict = validate_approval_file(
        approval_path, FREEZE_APPROVAL_SPEC, repo=root)
    if not approval_verdict.satisfied:
        problems.append("freeze approval is not valid: " + approval_verdict.detail())

    return FreezePreparation(readiness=readiness, approval=approval_payload,
                             violations=problems)


def _single_path_history(repo: Path, path: str) -> tuple[list[str], str]:
    try:
        history = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--reverse", "HEAD", "--", path],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return [], f"could not inspect technical-record history: {type(exc).__name__}: {exc}"
    if history.returncode != 0:
        return [], "could not inspect technical-record history"
    return [line.strip() for line in history.stdout.splitlines() if line.strip()], ""


def _commit_parent(repo: Path, commit: str) -> tuple[Optional[str], str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", "-s", "--format=%P", commit],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return None, f"could not inspect technical-record parent: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return None, "could not inspect technical-record parent"
    parents = result.stdout.strip().split()
    if len(parents) != 1:
        return None, "technical freeze record must be introduced by a single-parent commit"
    return parents[0], ""


def _commit_changed_paths(repo: Path, commit: str) -> tuple[set[str], str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "diff-tree", "--no-commit-id", "--name-only",
             "-r", commit],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return set(), f"could not inspect technical-record commit: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return set(), "could not inspect technical-record commit"
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}, ""


def _technical_record_states(repo: Path) -> tuple[Optional[str], Optional[str], list[str]]:
    """Return (frozen-input commit, record commit, problems).

    Before materialization, the clean HEAD itself is the frozen-input state. Once
    committed, the technical record must have been added exactly once by the
    immediate single-file successor commit. This prevents a stale record copied
    onto a later state from acquiring authority merely because its JSON parses.
    """
    head = current_commit(repo)
    if not head:
        return None, None, ["cannot resolve current repository commit"]
    relative = str(FREEZE_ARTIFACT_PATH)
    if not _git_path_exists(head, relative, repo=repo):
        return head, None, []

    history, history_error = _single_path_history(repo, relative)
    if history_error:
        return None, None, [history_error]
    if len(history) != 1:
        return None, None, [
            "technical freeze artifact must be introduced once and never rewritten; "
            f"observed {len(history)} commits touching it"
        ]
    record_commit = history[0]
    parent, parent_error = _commit_parent(repo, record_commit)
    if parent_error or parent is None:
        return None, record_commit, [parent_error]
    paths, paths_error = _commit_changed_paths(repo, record_commit)
    if paths_error:
        return parent, record_commit, [paths_error]
    if paths != {relative}:
        return parent, record_commit, [
            "technical freeze record commit must change exactly one path; changed "
            f"{sorted(paths)}"
        ]
    return parent, record_commit, []


def _approval_record_commit(repo: Path, approval: dict, head: str) -> tuple[Optional[str], str]:
    reviewed = str(approval.get("reviewed_repository_commit") or "").strip()
    if len(reviewed) != 40:
        return None, "freeze approval has no reviewed_repository_commit"
    commits, error = _path_touch_commits(
        reviewed, head, str(FREEZE_APPROVAL_PATH), repo=repo)
    if error:
        return None, error
    if len(commits) != 1:
        return None, ("freeze approval must be introduced exactly once after its reviewed "
                      f"state; observed {len(commits)} commits touching it")
    return commits[0], ""


def build_freeze_payload(repo: str | Path = ".") -> dict:
    """Build the canonical technical record, or refuse before writing one."""
    root = Path(repo).resolve()
    prepared = prepare_freeze(root)
    if not prepared.ready:
        raise FreezeError("cannot materialize Dataset V1 freeze: " + prepared.detail())

    assert prepared.approval is not None
    frozen_commit, _, state_problems = _technical_record_states(root)
    if state_problems or frozen_commit is None:
        raise FreezeError(
            "cannot determine the immutable frozen-input state: "
            + "; ".join(state_problems))
    approval_record_commit, record_error = _approval_record_commit(
        root, prepared.approval, frozen_commit)
    if approval_record_commit is None:
        raise FreezeError("cannot bind the freeze approval record: " + record_error)
    paths = freeze_bound_paths()
    unsafe_paths = [
        name for name in paths
        if (root / name).is_symlink() or not (root / name).is_file()
    ]
    if unsafe_paths:
        raise FreezeError(
            "cannot bind absent or non-regular frozen artifact(s): "
            + repr(unsafe_paths))
    digests = {name: sha256_of(root / name) for name in paths}
    return {
        "schema_version": FREEZE_SCHEMA,
        "artifact_type": FREEZE_ARTIFACT_TYPE,
        "dataset": DATASET_NAME,
        "decision": FREEZE_DECISION,
        "frozen_repository_commit": frozen_commit,
        "dataset_fingerprint": build_dataset_fingerprint(root),
        "approval": {
            "path": str(FREEZE_APPROVAL_PATH),
            "sha256": digests[str(FREEZE_APPROVAL_PATH)],
            "reviewed_repository_commit": prepared.approval.get(
                "reviewed_repository_commit"),
            "approval_record_commit": approval_record_commit,
        },
        "readiness": {
            "path": str(READINESS_PATH),
            "sha256": digests[str(READINESS_PATH)],
        },
        "frozen_artifacts": dict(sorted(digests.items())),
    }


def _worktree_problem(repo: Path) -> Optional[str]:
    """Return a deterministic refusal if final validation is not at a checkout."""
    try:
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain=v1", "--untracked-files=all"],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return f"could not inspect repository worktree: {type(exc).__name__}: {exc}"
    if status.returncode != 0:
        return "could not inspect repository worktree"
    entries = [line for line in status.stdout.splitlines() if line]
    if entries:
        return ("repository worktree is not clean; validate a committed freeze "
                f"checkout ({len(entries)} changed path(s))")
    return None


def validate_freeze_file(
    path: str | Path = FREEZE_ARTIFACT_PATH,
    *,
    repo: str | Path = ".",
    require_clean_worktree: bool = True,
) -> FreezeVerdict:
    """Validate an existing technical freeze record against the live checkout.

    A record is valid only if it has the exact schema, every frozen artifact is
    present with the recorded digest in both the frozen Git state and current
    checkout, the dataset fingerprint reconstructs exactly, the readiness report
    is still fully ready, and the human approval remains valid under its
    reviewed-state/approval-record-state policy.
    """
    root = Path(repo).resolve()
    raw_path = Path(path)
    record_path = raw_path if raw_path.is_absolute() else root / raw_path
    relpath = _repo_relative(root, record_path)
    payload, load_error = _load_json(record_path)
    if load_error:
        return FreezeVerdict(path=relpath, present=record_path.exists(), valid=False,
                             violations=[f"technical freeze record {load_error}"])

    assert payload is not None
    verdict = FreezeVerdict(path=relpath, present=True, valid=False)
    expected_fields = {
        "schema_version", "artifact_type", "dataset", "decision", "approval",
        "readiness", "frozen_artifacts", "frozen_repository_commit",
        "dataset_fingerprint",
    }
    present_fields = set(payload)
    missing_fields = sorted(expected_fields - present_fields)
    extra_fields = sorted(present_fields - expected_fields)
    if missing_fields:
        verdict.violations.append(f"freeze record misses required field(s): {missing_fields}")
    if extra_fields:
        verdict.violations.append(f"freeze record has unrecognised field(s): {extra_fields}")
    if payload.get("schema_version") != FREEZE_SCHEMA:
        verdict.violations.append(
            f"schema_version {payload.get('schema_version')!r} != {FREEZE_SCHEMA!r}")
    if payload.get("artifact_type") != FREEZE_ARTIFACT_TYPE:
        verdict.violations.append("artifact_type is not a Dataset V1 technical freeze")
    if payload.get("dataset") != DATASET_NAME:
        verdict.violations.append("freeze record does not identify Dataset V1")
    if payload.get("decision") != FREEZE_DECISION:
        verdict.violations.append("freeze record decision is not 'frozen'")

    frozen_commit = payload.get("frozen_repository_commit")
    if not isinstance(frozen_commit, str) or len(frozen_commit) != 40 or any(
            ch not in "0123456789abcdef" for ch in frozen_commit.lower()):
        verdict.violations.append(
            "freeze record has no full frozen_repository_commit SHA")
        frozen_commit = None

    actual_frozen_commit, _record_commit, state_problems = _technical_record_states(root)
    verdict.violations.extend(state_problems)
    if frozen_commit and actual_frozen_commit and frozen_commit != actual_frozen_commit:
        verdict.violations.append(
            "freeze artifact was not recorded as the immediate successor of its "
            "declared frozen_repository_commit")
    head = current_commit(root)
    if frozen_commit and head and not _is_ancestor(frozen_commit, head, root):
        verdict.violations.append(
            "frozen_repository_commit is not an ancestor of the current commit")
    if head:
        committed_record_digest, record_error = _git_blob_sha256(
            head, str(FREEZE_ARTIFACT_PATH), repo=root)
        if committed_record_digest is None:
            verdict.violations.append(
                "technical freeze artifact is not a committed regular file "
                f"({record_error})")
        elif sha256_of(record_path) != committed_record_digest:
            verdict.violations.append(
                "technical freeze artifact worktree bytes differ from its committed record")

    fingerprint = payload.get("dataset_fingerprint")
    try:
        fresh_fingerprint = build_dataset_fingerprint(root)
    except FreezeError as exc:
        verdict.violations.append(str(exc))
    else:
        if fingerprint != fresh_fingerprint:
            verdict.violations.append(
                "dataset_fingerprint does not match a fresh reconstruction from the "
                "current Dataset V1 manifests")

    approval = payload.get("approval")
    if not isinstance(approval, dict):
        verdict.violations.append("freeze record approval section is not an object")
    else:
        if set(approval) != {
                "path", "sha256", "reviewed_repository_commit",
                "approval_record_commit"}:
            verdict.violations.append("freeze record approval section has the wrong fields")
        if approval.get("path") != str(FREEZE_APPROVAL_PATH):
            verdict.violations.append("freeze record names the wrong approval path")
        if not _is_sha256(approval.get("sha256")):
            verdict.violations.append("freeze record approval has no SHA-256 digest")
        reviewed_commit = approval.get("reviewed_repository_commit")
        if not isinstance(reviewed_commit, str) or len(reviewed_commit) != 40 or any(
                ch not in "0123456789abcdef" for ch in reviewed_commit.lower()):
            verdict.violations.append(
                "freeze record approval has no full reviewed_repository_commit SHA")
        approval_record_commit = approval.get("approval_record_commit")
        if (not isinstance(approval_record_commit, str)
                or len(approval_record_commit) != 40
                or any(ch not in "0123456789abcdef"
                       for ch in approval_record_commit.lower())):
            verdict.violations.append(
                "freeze record approval has no full approval_record_commit SHA")
        elif frozen_commit and not _is_ancestor(
                approval_record_commit, frozen_commit, root):
            verdict.violations.append(
                "approval_record_commit is not an ancestor of the frozen state")

    readiness_ref = payload.get("readiness")
    if not isinstance(readiness_ref, dict):
        verdict.violations.append("freeze record readiness section is not an object")
    else:
        if set(readiness_ref) != {"path", "sha256"}:
            verdict.violations.append("freeze record readiness section has the wrong fields")
        if readiness_ref.get("path") != str(READINESS_PATH):
            verdict.violations.append("freeze record names the wrong readiness path")
        if not _is_sha256(readiness_ref.get("sha256")):
            verdict.violations.append("freeze record readiness has no SHA-256 digest")

    frozen_artifacts = payload.get("frozen_artifacts")
    expected_paths = set(freeze_bound_paths())
    if not isinstance(frozen_artifacts, dict):
        verdict.violations.append("freeze record frozen_artifacts is not an object")
        frozen_artifacts = {}
    else:
        actual_paths = set(frozen_artifacts)
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        if missing or extra:
            parts = []
            if missing:
                parts.append(f"missing {missing}")
            if extra:
                parts.append(f"unexpected {extra}")
            verdict.violations.append(
                "freeze record does not bind exactly the required artifacts: " + "; ".join(parts))

    for name in sorted(expected_paths):
        declared = frozen_artifacts.get(name)
        target = root / name
        if not _is_sha256(declared):
            verdict.violations.append(f"freeze record digest for '{name}' is not SHA-256")
        elif target.is_symlink() or not target.is_file():
            verdict.violations.append(
                f"frozen artifact '{name}' is absent or not a regular file")
        elif sha256_of(target) != str(declared).lower():
            verdict.violations.append(f"frozen artifact '{name}' changed after freeze")
        if frozen_commit and _is_sha256(declared):
            frozen_digest, frozen_error = _git_blob_sha256(
                frozen_commit, name, repo=root)
            if frozen_digest is None:
                verdict.violations.append(
                    f"frozen artifact '{name}' was absent or invalid in "
                    f"frozen_repository_commit ({frozen_error})")
            elif frozen_digest != str(declared).lower():
                verdict.violations.append(
                    f"frozen artifact '{name}' does not match its Git blob in "
                    "frozen_repository_commit")

    # Cross-check the convenient named references against the same closed map.
    if isinstance(approval, dict):
        expected_digest = frozen_artifacts.get(str(FREEZE_APPROVAL_PATH))
        if approval.get("sha256") != expected_digest:
            verdict.violations.append("approval digest disagrees with frozen_artifacts")
    if isinstance(readiness_ref, dict):
        expected_digest = frozen_artifacts.get(str(READINESS_PATH))
        if readiness_ref.get("sha256") != expected_digest:
            verdict.violations.append("readiness digest disagrees with frozen_artifacts")

    prepared = prepare_freeze(root)
    verdict.violations.extend(prepared.violations)
    if isinstance(approval, dict) and prepared.approval is not None:
        if (approval.get("reviewed_repository_commit")
                != prepared.approval.get("reviewed_repository_commit")):
            verdict.violations.append(
                "freeze record reviewed commit disagrees with freeze approval")
        if frozen_commit:
            actual_approval_record, approval_record_error = _approval_record_commit(
                root, prepared.approval, frozen_commit)
            if actual_approval_record is None:
                verdict.violations.append(
                    "cannot verify freeze approval record commit: "
                    + approval_record_error)
            elif approval.get("approval_record_commit") != actual_approval_record:
                verdict.violations.append(
                    "freeze record approval_record_commit disagrees with Git history")

    if require_clean_worktree:
        problem = _worktree_problem(root)
        if problem:
            verdict.violations.append(problem)

    verdict.valid = not verdict.violations
    return verdict
