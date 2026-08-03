"""Strict validators for human approval and audit sign-off artifacts (Finding 2).

The audit's demonstration was one line long::

    {"approved": true}

That file satisfied the previous freeze-approval predicate. It names no
reviewer, no scope, no commit, no timestamp, and nothing it claims to have
approved — it is an assertion with no author and no object. A gate that accepts
it is not recording a human decision, it is recording the *word* for one.

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
from typing import Iterable, Optional, Sequence

from .mapping import PLACEHOLDER_TOKENS, is_placeholder, sha256_of_file

#: Versioned artifact schema. An artifact declaring a different version is
#: rejected, never coerced: fields may have changed meaning between versions.
APPROVAL_SCHEMA = "ica26.governance.approval/1"

#: Fields EVERY approval artifact must carry, whatever it approves.
REQUIRED_FIELDS = (
    "schema_version",       # which contract this artifact claims to satisfy
    "artifact_type",        # what kind of decision this is
    "decision",             # the decision itself, from an allow-list
    "scope",                # exactly what is in scope
    "reviewer_id",          # anonymous but stable identifier
    "reviewer_role",        # the qualification that makes the decision meaningful
    "reviewed_at",          # strict ISO-8601 with an explicit offset
    "repository_commit",    # the tree state the decision was taken against
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
                       "reports/leakage_gate.json"),
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
    required_bindings=("data/exclusions/plantdoc_internal_duplicate_resolution.csv",
                       "reports/plantdoc_label_second_review/"
                       "plantdoc_label_second_review.csv"),
    extra_required=("group_verdicts", "diagnostic_citations"),
)


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
        for name in spec.required_bindings:
            if name not in bindings:
                v.violations.append(f"approved_artifacts does not bind required '{name}'")
        for name, declared in sorted(bindings.items()):
            target = Path(repo) / name
            if not _is_sha256(declared):
                v.violations.append(f"approved_artifacts['{name}'] is not a SHA-256 digest")
                continue
            if not target.exists():
                v.violations.append(
                    f"approved_artifacts binds '{name}', which does not exist")
                continue
            actual = sha256_of_file(target)
            if actual != str(declared).strip().lower():
                v.violations.append(
                    f"'{name}' has changed since approval (stale digest: approved "
                    f"{str(declared)[:12]}…, current {actual[:12]}…)")

    # --- commit binding ---------------------------------------------------- #
    commit = str(payload.get("repository_commit") or "").strip()
    head = expected_commit if expected_commit is not None else current_commit(repo)
    if len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit.lower()):
        v.violations.append(
            f"repository_commit '{commit}' is not a full 40-character commit SHA")
    elif head and commit.lower() != head.lower():
        v.violations.append(
            f"stale commit binding: approval names {commit[:12]}…, HEAD is {head[:12]}…")
    else:
        # An approval cannot predate the tree it claims to have reviewed.
        committed_at = commit_timestamp(commit, repo)
        if committed_at is None:
            v.violations.append(
                f"cannot resolve the date of commit {commit[:12]}…; the approval's "
                "ordering against the reviewed tree is unverifiable")
        elif reviewed_dt is not None and reviewed_dt < committed_at:
            v.violations.append(
                f"approval is dated {stamp}, before commit {commit[:12]}… was created "
                f"({committed_at.isoformat()}); it cannot have reviewed that tree")

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
    """Load and validate an approval artifact. Absence is a refusal, not an error."""
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
                             expected_commit=expected_commit, siblings=siblings)
