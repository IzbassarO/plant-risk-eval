"""Strict validators for human approval and audit sign-off artifacts (Finding 2).

The audit's demonstration was one line long::

    {"approved": true}

That file satisfied the previous freeze-approval predicate. It names no
reviewer, no scope, no commit, no timestamp, and nothing it claims to have
approved — it is an assertion with no author and no object. A gate that accepts
it is not recording a human decision, it is recording the *word* for one.

Schema v2 uses two immutable Git states. ``reviewed_repository_commit`` names
the pre-approval tree whose regular-file blobs were examined; a later commit
introduces the approval record itself. The validator proves ancestry, reconciles
every declared SHA-256 against both Git states and the worktree, and refuses a
record that existed in the state it purports to approve.

An approval is only meaningful if you can answer, from the artifact alone: who
decided, what exactly they decided, over which bytes, at which commit, when, on
what grounds, and what they pointedly did **not** approve. Every one of those is
required here, and each is bound to the artifact it claims to cover by SHA-256,
so an approval cannot survive the thing it approved being edited.

Nothing in this module can create an approval. It only ever refuses or accepts
one a human wrote.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .mapping import is_placeholder, sha256_of_file
from .second_review import (
    SECOND_REVIEW_REQUIRED_BINDINGS,
    SECOND_REVIEW_SCHEMA,
    validate_second_review_payload,
)

#: Versioned artifact schema. An artifact declaring a different version is
#: rejected, never coerced: fields may have changed meaning between versions.
APPROVAL_SCHEMA = "ica26.governance.approval/2"

#: Fields EVERY approval artifact must carry, whatever it approves.
REQUIRED_FIELDS = (
    "schema_version",       # which contract this artifact claims to satisfy
    "artifact_type",        # what kind of decision this is
    "decision",             # the decision itself, from an allow-list
    "scope",                # exactly what is in scope
    "reviewer_id",          # anonymous but stable identifier
    "reviewer_role",        # the qualification that makes the decision meaningful
    "reviewed_at",          # strict ISO-8601 with an explicit offset
    "reviewed_repository_commit",  # immutable pre-record state reviewed
    "approved_artifacts",   # {path: sha256} -- the exact bytes approved
    "rationale",            # why, or a pointer to a preserved review report
    "not_approved",         # what this decision explicitly does NOT cover
)

#: A rationale shorter than this is not a rationale.
MIN_RATIONALE_CHARS = 40

#: Decision values that mean "yes". Anything else -- including an unknown
#: string -- never satisfies a condition.
AFFIRMATIVE = "approved"


class ApprovalError(RuntimeError):
    """Raised only by helpers that cannot express refusal in a verdict."""


@dataclass(frozen=True)
class ApprovalSpec:
    """What one kind of approval artifact must look like."""

    artifact_type: str
    scope: str
    #: Every decision value the artifact may legally carry. Membership does not
    #: imply satisfaction -- only ``AFFIRMATIVE`` does.
    allowed_decisions: tuple[str, ...] = (AFFIRMATIVE, "rejected", "deferred")
    #: Repository paths whose digests the artifact must bind, by name.
    required_bindings: tuple[str, ...] = ()
    #: Extra top-level fields this artifact type requires.
    extra_required: tuple[str, ...] = ()
    #: Audit finding ids that a sign-off must explicitly list as closed.
    required_findings: tuple[str, ...] = ()

    def describe(self) -> str:
        return (f"{self.artifact_type} (scope '{self.scope}', schema "
                f"{APPROVAL_SCHEMA}, binds {list(self.required_bindings)})")


#: The Dataset V1 freeze decision itself.
FREEZE_APPROVAL_SPEC = ApprovalSpec(
    artifact_type="dataset_v1_freeze_approval",
    scope="dataset_v1",
    required_bindings=("data/manifests/plantdoc_effective_manifest.csv",
                       "data/exclusions/plantdoc_internal_duplicate_resolution.csv",
                       "reports/plantdoc_internal_duplicate_gate.json",
                       "reports/leakage_gate.json",
                       "reports/leakage_plantvillage_vs_plantdoc_summary.json",
                       "configs/action_taxonomy.yaml",
                       "configs/evaluation_scope.yaml",
                       "data/mapping/action_mapping_review.csv",
                       "data/mapping/action_mapping_approved.csv",
                       "data/mapping/action_mapping_apply_summary.json",
                       "data/mapping/disease_pathogen.csv",
                       "data/mapping/class_crosswalk.csv",
                       "data/mapping/plantvillage_class_list.csv",
                       "data/manifests/plantvillage_manifest.csv",
                       "data/manifests/plantvillage_source_snapshot.json",
                       "configs/harm_matrix_template.yaml",
                       "human_review/evidence_manifest.json",
                       "human_review/plantdoc_label_second_review/second_review.json",
                       "reports/DATASET_V1_AUDIT_SIGNOFF.json"),
)

#: The independent re-audit that closes outstanding findings.
AUDIT_SIGNOFF_SPEC = ApprovalSpec(
    artifact_type="dataset_v1_audit_signoff",
    scope="phase1_audit_findings",
    required_bindings=("reports/plantdoc_internal_duplicate_gate.json",
                       "data/manifests/plantdoc_effective_manifest.csv"),
    extra_required=("closed_findings", "auditor_independent_of_implementer"),
    required_findings=("AUD-EC-005", "AUD-EC-006", "AUD-EC-007", "R2B-REMEDIATION"),
)

#: The second, independent scientific review of the G07/G08/G10 relabels.
SECOND_REVIEW_SPEC = ApprovalSpec(
    artifact_type="plantdoc_label_second_review",
    scope="plantdoc_relabelled_groups",
    required_bindings=SECOND_REVIEW_REQUIRED_BINDINGS,
    extra_required=("review_schema_version", "groups"),
)

#: Type-specific schema for the self-contained G07/G08/G10 review objects.
#: The generic approval schema still governs authorship and reviewed-state
#: binding; this nested version governs the scientific evidence contract.
SECOND_REVIEW_SCHEMA_VERSION = SECOND_REVIEW_SCHEMA


@dataclass
class ApprovalVerdict:
    """Why an artifact was refused, or that it was accepted."""

    artifact_type: str
    path: str
    present: bool
    valid: bool
    decision: str = ""
    violations: list = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        return self.present and self.valid and self.decision == AFFIRMATIVE

    def detail(self) -> str:
        if not self.present:
            return (f"no {self.artifact_type} artifact at {self.path}; "
                    "the decision has not been taken")
        if self.violations:
            shown = self.violations[:3]
            more = (f" (+{len(self.violations) - len(shown)} more)"
                    if len(self.violations) > len(shown) else "")
            return f"{len(self.violations)} problem(s): " + "; ".join(shown) + more
        if self.decision != AFFIRMATIVE:
            return f"decision is '{self.decision}', not '{AFFIRMATIVE}'"
        return f"valid {self.artifact_type} by an identified reviewer"

    def as_dict(self) -> dict:
        return {"artifact_type": self.artifact_type, "path": self.path,
                "present": self.present, "valid": self.valid,
                "decision": self.decision, "satisfied": self.satisfied,
                "violations": sorted(self.violations)}


def commit_timestamp(commit: str, repo: str | Path = ".") -> Optional[datetime]:
    """Committer date of ``commit`` as an aware datetime, or None if unknown.

    Used to reject an approval dated *before* the tree it claims to have
    reviewed existed. None is not "fine" -- the caller treats it as unverifiable
    and blocks.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "show", "-s", "--format=%cI", commit],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        return datetime.fromisoformat(out.stdout.strip())
    except Exception:
        return None


def current_commit(repo: str | Path = ".") -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _safe_repository_path(repo: str | Path, name: str) -> tuple[Optional[Path], str]:
    """Resolve one repository-relative artifact path without following it outside.

    Approval contracts contain fixed paths, but artifacts are untrusted input.
    Keeping path validation in one helper ensures both the worktree and Git-tree
    checks apply the same refusal semantics.
    """
    if not name or Path(name).is_absolute():
        return None, "is not a non-empty repository-relative path"
    root = Path(repo).resolve()
    try:
        target = (root / name).resolve()
        target.relative_to(root)
    except (OSError, ValueError):
        return None, "escapes the repository"
    return target, ""


def _git_blob_sha256(
    commit: str,
    name: str,
    *,
    repo: str | Path,
) -> tuple[Optional[str], str]:
    """SHA-256 of a regular-file blob at ``commit``, without checkout.

    This is the core reviewed-state guarantee.  Looking only at the current
    filesystem proves what exists now, not what the reviewer saw.  ``ls-tree``
    also lets us reject symlinks and submodules before streaming the blob.
    """
    target, unsafe = _safe_repository_path(repo, name)
    if target is None:
        return None, unsafe
    del target  # only path safety, not the worktree bytes, matters here
    try:
        entry = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-z", commit, "--", name],
            capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return None, f"could not inspect reviewed Git tree: {type(exc).__name__}: {exc}"
    if entry.returncode != 0:
        return None, "reviewed Git commit is missing or unreadable"
    records = [record for record in entry.stdout.split(b"\0") if record]
    if len(records) != 1 or b"\t" not in records[0]:
        return None, "does not exist as one regular file in the reviewed Git tree"
    metadata, recorded_name = records[0].split(b"\t", 1)
    try:
        mode, object_type, object_id = metadata.decode("ascii").split()
        decoded_name = recorded_name.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None, "has an unreadable Git tree entry"
    if decoded_name != name:
        return None, "does not resolve to the exact declared path in the reviewed Git tree"
    if object_type != "blob" or not mode.startswith("100"):
        return None, f"is Git mode {mode} type {object_type}, not a regular file"

    try:
        process = subprocess.Popen(
            ["git", "-C", str(repo), "cat-file", "blob", object_id],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None
        digest = hashlib.sha256()
        for chunk in iter(lambda: process.stdout.read(1 << 20), b""):
            digest.update(chunk)
        stderr = process.stderr.read() if process.stderr is not None else b""
        returncode = process.wait(timeout=30)
    except Exception as exc:  # noqa: BLE001
        try:
            process.kill()
        except Exception:  # noqa: BLE001
            pass
        return None, f"could not read reviewed Git blob: {type(exc).__name__}: {exc}"
    if returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()
        return None, "could not read reviewed Git blob" + (f": {detail}" if detail else "")
    return digest.hexdigest(), ""


def _is_ancestor(candidate: str, head: str, repo: str | Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", candidate, head],
            capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        return False
    return result.returncode == 0


def _git_path_exists(commit: str, name: str, *, repo: str | Path) -> bool:
    target, _ = _safe_repository_path(repo, name)
    if target is None:
        return False
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-tree", "-z", commit, "--", name],
            capture_output=True, timeout=30)
    except Exception:  # noqa: BLE001
        return False
    return result.returncode == 0 and bool(result.stdout)


def _path_touch_commits(
    candidate: str,
    head: str,
    path: str,
    *,
    repo: str | Path,
) -> tuple[list[str], str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--reverse", f"{candidate}..{head}",
             "--", path],
            capture_output=True, text=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return [], f"could not inspect approval-record history: {type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return [], "could not inspect approval-record history"
    return [line.strip() for line in result.stdout.splitlines() if line.strip()], ""


def _reviewed_state_is_recorded(
    candidate: str,
    head: str,
    *,
    repo: str | Path,
    approval_path: str = "",
) -> tuple[bool, str]:
    """Verify the two-state approval lifecycle using immutable Git objects.

    ``candidate`` is the reviewed state and deliberately excludes the approval
    record.  ``head`` is the approval-record state (or a later descendant).  The
    artifact-level blob checks are performed separately by ``validate_approval``;
    this helper proves ancestry, record introduction, and record immutability.

    Artifact applicability is derived from immutable Git objects and never from
    a mutable allow-list of paths.
    """
    if candidate.lower() == head.lower():
        return False, ("approval-record state is missing: reviewed_repository_commit "
                       "must precede the commit that records the approval")
    if not _is_ancestor(candidate, head, repo):
        return False, ("stale reviewed-state binding: approval names "
                       f"{candidate[:12]}…, HEAD is {head[:12]}…, and the reviewed "
                       "commit is not an ancestor")
    if not approval_path:
        return False, "approval-record path is unavailable; persistence cannot be verified"

    if _git_path_exists(candidate, approval_path, repo=repo):
        return False, ("approval record already existed in the reviewed state; an approval "
                       "cannot approve a state containing its own content")

    head_record_digest, head_error = _git_blob_sha256(head, approval_path, repo=repo)
    if head_record_digest is None:
        return False, ("approval record is not a committed regular file in the "
                       f"approval-record state: {head_error}")
    record_path, unsafe = _safe_repository_path(repo, approval_path)
    if record_path is None or record_path.is_symlink() or not record_path.is_file():
        return False, f"approval record path is unsafe or absent: {unsafe or approval_path}"
    if sha256_of_file(record_path) != head_record_digest:
        return False, "approval record worktree bytes differ from the committed record state"

    touch_commits, touch_error = _path_touch_commits(
        candidate, head, approval_path, repo=repo)
    if touch_error:
        return False, touch_error
    if len(touch_commits) != 1:
        return False, ("approval artifact must be introduced exactly once after its reviewed "
                       f"state; observed {len(touch_commits)} commits touching it")
    return True, ""


def _is_sha256(value) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(c in "0123456789abcdef" for c in text)


def validate_approval(
    payload,
    spec: ApprovalSpec,
    *,
    repo: str | Path = ".",
    path: str = "",
    expected_commit: Optional[str] = None,
    siblings: Iterable[tuple[str, dict]] = (),
    require_recorded_state: bool = False,
) -> ApprovalVerdict:
    """Validate one already-loaded approval payload against ``spec``.

    ``siblings`` are other (path, payload) pairs in the same directory, used to
    detect duplicate or contradictory approvals for the same scope.
    """
    from ..leakage.gate import parse_review_timestamp

    v = ApprovalVerdict(artifact_type=spec.artifact_type, path=str(path),
                        present=True, valid=False)

    # A list, a bare boolean, or a scalar is not an approval record. This is the
    # `{"approved": true}` class of artifact, caught before anything else.
    if not isinstance(payload, dict):
        v.violations.append(
            f"artifact is {type(payload).__name__}, expected a single JSON object; "
            "a bare value cannot carry reviewer, scope, or integrity binding")
        return v

    missing = [f for f in REQUIRED_FIELDS + spec.extra_required
               if f not in payload or is_placeholder(payload.get(f))
               and not isinstance(payload.get(f), (list, dict))]
    # A list/dict field is missing only if absent or empty.
    for f in REQUIRED_FIELDS + spec.extra_required:
        val = payload.get(f)
        if isinstance(val, (list, dict)) and not val and f not in missing:
            missing.append(f)
    if missing:
        v.violations.append(f"missing or placeholder required field(s): {sorted(set(missing))}")

    if payload.get("schema_version") != APPROVAL_SCHEMA:
        v.violations.append(
            f"schema_version '{payload.get('schema_version')}' != '{APPROVAL_SCHEMA}'; "
            "an artifact from another contract is rejected, not reinterpreted")
    if payload.get("artifact_type") != spec.artifact_type:
        v.violations.append(
            f"artifact_type '{payload.get('artifact_type')}' != '{spec.artifact_type}' "
            "(approval for a different kind of decision)")
    if str(payload.get("scope") or "").strip() != spec.scope:
        v.violations.append(
            f"scope '{payload.get('scope')}' != '{spec.scope}' "
            "(approval for a different scope does not transfer)")

    decision = str(payload.get("decision") or "").strip()
    v.decision = decision
    if decision not in spec.allowed_decisions:
        v.violations.append(
            f"unknown decision '{decision}' (allowed: {list(spec.allowed_decisions)})")

    for fld in ("reviewer_id", "reviewer_role"):
        if is_placeholder(payload.get(fld)):
            v.violations.append(f"'{fld}' is empty or a placeholder")

    stamp = str(payload.get("reviewed_at") or "").strip()
    reviewed_dt, ts_error = parse_review_timestamp(stamp) if stamp else (None, "reviewed_at is blank")
    if ts_error:
        v.violations.append(ts_error)

    rationale = str(payload.get("rationale") or "").strip()
    if not is_placeholder(rationale) and len(rationale) < MIN_RATIONALE_CHARS:
        v.violations.append(
            f"rationale is {len(rationale)} characters; at least {MIN_RATIONALE_CHARS} "
            "are required, or a reference to a preserved review report")

    not_approved = payload.get("not_approved")
    if isinstance(not_approved, str) and is_placeholder(not_approved):
        v.violations.append("'not_approved' must state what this decision does not cover")

    # --- integrity binding to the exact bytes approved --------------------- #
    bindings = payload.get("approved_artifacts")
    if not isinstance(bindings, dict) or not bindings:
        v.violations.append(
            "'approved_artifacts' must be a non-empty {path: sha256} map binding the "
            "exact bytes reviewed")
    else:
        # An approval is a closed set of named bytes, not an arbitrary map that
        # happens to contain the required entries.  Exact coverage makes the
        # review surface independently auditable and prevents a path outside the
        # declared contract from being smuggled into an otherwise valid record.
        expected_bindings = set(spec.required_bindings)
        non_string_names = [repr(name) for name in bindings if not isinstance(name, str)]
        if non_string_names:
            v.violations.append(
                "approved_artifacts has non-string path key(s): "
                f"{non_string_names}")
        actual_bindings = {name for name in bindings if isinstance(name, str)}
        for name in sorted(expected_bindings - actual_bindings):
            v.violations.append(f"approved_artifacts does not bind required '{name}'")
        unexpected_bindings = sorted(actual_bindings - expected_bindings)
        if unexpected_bindings:
            v.violations.append(
                "approved_artifacts binds path(s) outside this approval contract: "
                f"{unexpected_bindings}")
        for name, declared in sorted(bindings.items(), key=lambda item: str(item[0])):
            if not isinstance(name, str):
                continue
            target, unsafe = _safe_repository_path(repo, name)
            if target is None:
                v.violations.append(
                    f"approved_artifacts['{name}'] is not a safe repository-relative "
                    f"path ({unsafe})")
                continue
            if not _is_sha256(declared):
                v.violations.append(f"approved_artifacts['{name}'] is not a SHA-256 digest")
                continue
            if target.is_symlink() or not target.is_file():
                v.violations.append(
                    f"approved_artifacts binds '{name}', which does not exist as a "
                    "regular non-symlink file")
                continue
            actual = sha256_of_file(target)
            if actual != str(declared).strip().lower():
                v.violations.append(
                    f"'{name}' has changed since approval (stale digest: approved "
                    f"{str(declared)[:12]}…, current {actual[:12]}…)")

    # --- commit binding ---------------------------------------------------- #
    if "repository_commit" in payload:
        v.violations.append(
            "legacy 'repository_commit' is ambiguous; use "
            "'reviewed_repository_commit' for the pre-approval reviewed state")
    commit = str(payload.get("reviewed_repository_commit") or "").strip()
    head = expected_commit if expected_commit is not None else current_commit(repo)
    commit_is_resolvable = False
    if len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit.lower()):
        v.violations.append(
            f"reviewed_repository_commit '{commit}' is not a full 40-character commit SHA")
    elif not head:
        v.violations.append(
            "current approval-record commit cannot be resolved; reviewed-state "
            "ancestry is unverifiable")
    else:
        if commit.lower() != head.lower():
            if require_recorded_state:
                current, reason = _reviewed_state_is_recorded(
                    commit, head, repo=repo, approval_path=path)
                if not current:
                    v.violations.append(reason)
            else:
                v.violations.append(
                    "stale reviewed-state binding: approval names "
                    f"{commit[:12]}…, HEAD is {head[:12]}…")
        elif require_recorded_state:
            v.violations.append(
                "approval-record state is missing: reviewed_repository_commit must "
                "precede the commit that records the approval")
        # An approval cannot predate the tree it claims to have reviewed.
        # This holds both for an in-memory preflight and a persisted descendant
        # approval record.
        committed_at = commit_timestamp(commit, repo)
        if committed_at is None:
            v.violations.append(
                f"cannot resolve the date of commit {commit[:12]}…; the approval's "
                "ordering against the reviewed tree is unverifiable")
        elif reviewed_dt is not None and reviewed_dt < committed_at:
            v.violations.append(
                f"approval is dated {stamp}, before commit {commit[:12]}… was created "
                f"({committed_at.isoformat()}); it cannot have reviewed that tree")
        else:
            commit_is_resolvable = True

    # Validate the declared SHA-256 values against immutable blobs in the
    # reviewed commit and in the current approval-record state.  The existing
    # worktree checks above additionally catch uncommitted mutation.
    if commit_is_resolvable and isinstance(bindings, dict):
        for name, declared in sorted(bindings.items(), key=lambda item: str(item[0])):
            if not isinstance(name, str) or not _is_sha256(declared):
                continue
            expected_digest = str(declared).strip().lower()
            reviewed_digest, reviewed_error = _git_blob_sha256(commit, name, repo=repo)
            if reviewed_digest is None:
                v.violations.append(
                    f"approved artifact '{name}' is absent or invalid at reviewed state "
                    f"{commit[:12]}… ({reviewed_error})")
            elif reviewed_digest != expected_digest:
                v.violations.append(
                    f"approved_artifacts['{name}'] does not match its reviewed-state "
                    f"Git blob (declared {expected_digest[:12]}…, reviewed "
                    f"{reviewed_digest[:12]}…)")

            if head:
                head_digest, head_error = _git_blob_sha256(head, name, repo=repo)
                if head_digest is None:
                    v.violations.append(
                        f"approved artifact '{name}' is absent or invalid at current "
                        f"approval-record state ({head_error})")
                elif head_digest != expected_digest:
                    v.violations.append(
                        f"approved artifact '{name}' changed after its reviewed state "
                        f"(approved {expected_digest[:12]}…, current Git blob "
                        f"{head_digest[:12]}…)")

    if isinstance(bindings, dict) and path:
        record_target, _ = _safe_repository_path(repo, str(path))
        record_rel = ""
        if record_target is not None:
            try:
                record_rel = str(record_target.relative_to(Path(repo).resolve()))
            except ValueError:
                record_rel = ""
        if record_rel and record_rel in bindings:
            v.violations.append(
                "approval record appears in approved_artifacts; an approval cannot "
                "approve its own content")
        if require_recorded_state and record_target is not None:
            try:
                recorded_payload = json.loads(record_target.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                v.violations.append(
                    "committed approval record cannot be compared with the validated "
                    f"payload ({type(exc).__name__}: {exc})")
            else:
                if recorded_payload != payload:
                    v.violations.append(
                        "validated payload differs from the committed approval record")

    # --- type-specific requirements ---------------------------------------- #
    if spec.required_findings:
        closed = payload.get("closed_findings")
        if not isinstance(closed, list):
            v.violations.append("'closed_findings' must be a list of audit finding ids")
        else:
            declared = {str(x).strip() for x in closed}
            absent = [f for f in spec.required_findings if f not in declared]
            if absent:
                v.violations.append(f"sign-off does not close required finding(s): {absent}")
        if payload.get("auditor_independent_of_implementer") is not True:
            v.violations.append(
                "'auditor_independent_of_implementer' must be exactly true; a "
                "self-audit does not close a finding")

    if (spec.artifact_type == SECOND_REVIEW_SPEC.artifact_type
            and spec.scope == SECOND_REVIEW_SPEC.scope):
        v.violations.extend(validate_second_review_payload(payload, repo=repo))

    # --- duplicate / contradictory approvals -------------------------------- #
    for other_path, other in siblings:
        if str(other_path) == str(path) or not isinstance(other, dict):
            continue
        if (other.get("artifact_type") == spec.artifact_type
                and str(other.get("scope") or "").strip() == spec.scope):
            v.violations.append(
                f"a second {spec.artifact_type} for scope '{spec.scope}' exists at "
                f"{other_path}; duplicate or contradictory approvals are refused")

    v.valid = not v.violations
    return v


def validate_approval_file(
    path: str | Path,
    spec: ApprovalSpec,
    *,
    repo: str | Path = ".",
    expected_commit: Optional[str] = None,
) -> ApprovalVerdict:
    """Load and validate a *persisted* approval record.

    Unlike ``validate_approval`` (which may preflight an in-memory human record
    against the reviewed commit), file validation always requires the distinct,
    committed approval-record state. Absence or an uncommitted file is a refusal,
    not an error or a provisional approval.
    """
    p = Path(path)
    # Repository-relative, always: a verdict is a paper-facing artifact and an
    # absolute path would carry the reviewer's home directory into it.
    try:
        rel = str(p.resolve().relative_to(Path(repo).resolve()))
    except Exception:                                          # noqa: BLE001
        rel = str(p)
    if not p.exists():
        return ApprovalVerdict(artifact_type=spec.artifact_type, path=rel,
                               present=False, valid=False)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:                                   # noqa: BLE001
        return ApprovalVerdict(artifact_type=spec.artifact_type, path=rel, present=True,
                               valid=False, violations=[f"unreadable JSON: {exc}"])

    siblings: list[tuple[str, dict]] = []
    for other in sorted(p.parent.glob("*.json")):
        if other == p:
            continue
        try:
            data = json.loads(other.read_text(encoding="utf-8"))
        except Exception:                                      # noqa: BLE001
            continue
        if isinstance(data, dict):
            siblings.append((str(other), data))

    return validate_approval(payload, spec, repo=repo, path=rel,
                             expected_commit=expected_commit, siblings=siblings,
                             require_recorded_state=True)
