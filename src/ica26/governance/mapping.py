"""Fail-closed readiness for a disease-to-action mapping table (R2B.1 Finding 1).

The predicate this replaces was ``sum(review_status == "needs_review") == 0``,
with PlantVillage coverage measured as "a row exists for this class". Both fail
**open**, and the audit demonstrated it: rename ``needs_review`` to
``pending_review`` and the first goes green; add an empty row naming a class and
the second counts it as covered. A readiness predicate that a typo can satisfy
is not measuring readiness.

What is checked here instead
----------------------------
Readiness is decided against an **expected class identity set** — the classes
actually present in the dataset — not against whatever the file happens to
contain. For that set:

* every expected class must appear **exactly once** (missing and duplicated are
  both reported, by name);
* a class the file names but the dataset does not have is **unexpected** and
  blocks, unless a versioned policy explicitly allows it;
* every row must carry a status from a small allow-list of **terminal** values.
  Anything else — ``pending``, ``needs_review``, blank, null, a placeholder, or
  an unrecognised string — is non-terminal and blocks. There is no "not
  needs_review therefore fine" path;
* an ``approved`` row must additionally pass the repository's own evidence gate,
  name an action from the approved target vocabulary, and carry reviewer
  attribution with a strict ISO-8601 timestamp;
* an ``excluded`` row is terminal but is **not** coverage: it records a class
  deliberately left unmapped, and must itself carry a reason and attribution.

Readiness is bound to the exact SHA-256 of the mapping artifact, so a table that
changes after the assessment cannot keep its verdict.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from ..schemas import (
    ACTION_CLASSES,
    EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL,
    FORBIDDEN_ACTION_CLASSES,
    HEALTHY_ACTION_CLASS,
    HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL,
    HEALTHY_POLICY_ID,
    is_healthy_disease,
)

#: Versioned policy identity. Bump rather than editing the rules in place --
#: changing what "ready" means silently would defeat the point of recording it.
MAPPING_READINESS_SCHEMA = "ica26.governance.mapping_readiness/1"

#: The ONLY statuses that terminate review. Everything else -- including a
#: status that merely *looks* terminal -- is non-terminal and blocks.
STATUS_APPROVED = "approved"
STATUS_EXCLUDED = "excluded"
TERMINAL_STATUSES = (STATUS_APPROVED, STATUS_EXCLUDED)

#: Strings that carry no decision even though the cell is not empty. Compared
#: case-folded and stripped, so `N/A`, ` none `, and `TBD` are all caught.
PLACEHOLDER_TOKENS = frozenset({
    "", "-", "--", "?", "??", "n/a", "n.a.", "na", "none", "null", "nil", "nan",
    "tbd", "tba", "todo", "to do", "pending", "unknown", "unspecified",
    "placeholder", "xxx", "xx", "fixme", "changeme", "example", "sample",
    "lorem ipsum", "foo", "bar", "test", "dummy",
})

#: Attribution a terminal mapping decision must carry.
ATTRIBUTION_FIELDS = ("reviewer", "reviewed_at")

#: Column carrying the mapped target. The review table names it
#: `candidate_action_class` (it is a proposal); the approved table names it
#: `action_class` (it is a decision). Both are accepted and the first present
#: wins, so neither table needs reshaping to be validated.
TARGET_COLUMNS = ("action_class", "candidate_action_class")


def is_placeholder(value) -> bool:
    """True if the cell carries no usable content.

    A blank cell and a cell containing ``TBD`` are the same amount of evidence.
    """
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return text.casefold() in PLACEHOLDER_TOKENS


def _get(row: dict, *names: str) -> str:
    for n in names:
        if n in row and not is_placeholder(row.get(n)):
            return str(row[n]).strip()
    return ""


def sha256_of_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class MappingReadiness:
    """The verdict, with every disqualifying identity named rather than counted."""

    schema: str
    dataset: str
    artifact: str
    artifact_digest: str
    expected_classes: int
    approved_classes: int
    excluded_classes: int
    satisfied: bool
    missing: tuple[str, ...] = ()
    unexpected: tuple[str, ...] = ()
    duplicated: tuple[str, ...] = ()
    nonterminal: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()

    @property
    def covered_classes(self) -> int:
        """Classes with a terminal decision. Not the same as 'rows present'."""
        return self.approved_classes + self.excluded_classes

    def detail(self) -> str:
        if self.satisfied:
            return (f"{self.approved_classes} approved + {self.excluded_classes} "
                    f"explicitly excluded = {self.covered_classes}/{self.expected_classes} "
                    f"class(es) terminally decided")
        parts = [f"coverage {self.covered_classes}/{self.expected_classes}"]
        for name, ids in (("missing", self.missing), ("unexpected", self.unexpected),
                          ("duplicated", self.duplicated),
                          ("non-terminal", self.nonterminal), ("invalid", self.invalid)):
            if ids:
                shown = list(ids[:3])
                more = f" (+{len(ids) - len(shown)} more)" if len(ids) > len(shown) else ""
                parts.append(f"{len(ids)} {name}: {shown}{more}")
        return "; ".join(parts)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema, "dataset": self.dataset, "artifact": self.artifact,
            "artifact_digest": self.artifact_digest,
            "expected_classes": self.expected_classes,
            "approved_classes": self.approved_classes,
            "excluded_classes": self.excluded_classes,
            "covered_classes": self.covered_classes,
            "satisfied": self.satisfied,
            "missing": list(self.missing), "unexpected": list(self.unexpected),
            "duplicated": list(self.duplicated), "nonterminal": list(self.nonterminal),
            "invalid": list(self.invalid),
        }


def _validate_approved_row(row: dict, cls: str, *, out_of_action_scope: bool) -> list[str]:
    """Everything an ``approved`` row must carry. Returns reasons it does not."""
    from ..leakage.gate import parse_review_timestamp

    problems: list[str] = []

    # A class the scope config removed from action evaluation must not be
    # *approved* into an action -- that would re-admit it through the back door.
    if out_of_action_scope:
        problems.append("class is out of action-evaluation scope and may not carry "
                        "an approved action mapping; record 'excluded' instead")

    target = _get(row, *TARGET_COLUMNS)
    if not target:
        problems.append(f"no action target in any of {list(TARGET_COLUMNS)}")
    elif target in FORBIDDEN_ACTION_CLASSES:
        problems.append(f"forbidden action class '{target}'")
    elif target not in ACTION_CLASSES:
        problems.append(f"action '{target}' is outside the approved vocabulary "
                        f"{list(ACTION_CLASSES)}")

    healthy = is_healthy_disease(row.get("canonical_disease"))
    required = (HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL if healthy
                else EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL)
    for fld in required:
        if fld in TARGET_COLUMNS:
            continue                       # already checked, and may be renamed
        if is_placeholder(row.get(fld)):
            problems.append(f"required evidence field '{fld}' is blank or a placeholder")

    if healthy:
        # The narrow healthy exemption waives pathogen evidence, never the
        # citation that authorises the waiver.
        if target and target != HEALTHY_ACTION_CLASS:
            problems.append(f"approved healthy class must map to '{HEALTHY_ACTION_CLASS}', "
                            f"not '{target}'")
        cites = any(HEALTHY_POLICY_ID in str(row.get(c) or "")
                    for c in ("source_identifier", "review_notes", "policy_reference"))
        if not cites:
            problems.append(f"approved healthy class does not cite '{HEALTHY_POLICY_ID}'")

    for fld in ATTRIBUTION_FIELDS:
        if is_placeholder(row.get(fld)):
            problems.append(f"missing attribution '{fld}'")
    if not is_placeholder(row.get("reviewed_at")):
        _, err = parse_review_timestamp(str(row.get("reviewed_at")).strip())
        if err:
            problems.append(err)
    return problems


def _validate_excluded_row(row: dict) -> list[str]:
    """An exclusion is a decision too, and carries the same burden of proof."""
    from ..leakage.gate import parse_review_timestamp

    problems: list[str] = []
    if is_placeholder(row.get("review_notes")) and is_placeholder(row.get("exclusion_reason")):
        problems.append("excluded without a recorded reason "
                        "(review_notes or exclusion_reason)")
    for fld in ATTRIBUTION_FIELDS:
        if is_placeholder(row.get(fld)):
            problems.append(f"missing attribution '{fld}'")
    if not is_placeholder(row.get("reviewed_at")):
        _, err = parse_review_timestamp(str(row.get("reviewed_at")).strip())
        if err:
            problems.append(err)
    return problems


def evaluate_mapping_readiness(
    rows: Iterable[dict],
    *,
    dataset: str,
    expected_classes: Iterable[str],
    artifact: str = "",
    artifact_digest: str = "",
    allowed_extra_classes: Iterable[str] = (),
    out_of_action_scope_classes: Iterable[str] = (),
    control_plane_errors: Iterable[str] = (),
) -> MappingReadiness:
    """Decide whether ``dataset``'s mapping rows terminally cover every class.

    ``expected_classes`` is the authority — the classes the dataset actually
    contains. A file may not define its own denominator.

    ``allowed_extra_classes`` is the versioned escape hatch for a class that is
    legitimately mapped but absent from the current manifest; it must be listed
    explicitly, never inferred.

    ``out_of_action_scope_classes`` are classes an evaluation-scope decision
    removed from action evaluation. They still require a terminal decision, but
    that decision must be ``excluded``: approving one into an action would
    re-admit it through the back door.

    ``control_plane_errors`` carries a failure to load an authority the mapping
    decision depends on (for example the evaluation-scope policy).  A broken
    policy must block readiness; treating it as an empty policy would silently
    widen the action-evaluation scope.
    """
    expected = {str(c) for c in expected_classes}
    allowed_extra = {str(c) for c in allowed_extra_classes}
    out_of_scope = {str(c) for c in out_of_action_scope_classes}

    seen: dict[str, int] = {}
    approved: set[str] = set()
    excluded: set[str] = set()
    unexpected: set[str] = set()
    duplicated: set[str] = set()
    nonterminal: list[str] = []
    invalid: list[str] = [f"control-plane: {str(error)}" for error in control_plane_errors
                          if str(error).strip()]

    for i, row in enumerate(rows, start=2):
        if str(row.get("dataset", "")).strip() != dataset:
            continue
        cls = str(row.get("dataset_class", "") or "").strip()
        if is_placeholder(cls):
            invalid.append(f"row {i}: blank or placeholder dataset_class")
            continue

        seen[cls] = seen.get(cls, 0) + 1
        if seen[cls] > 1:
            duplicated.add(cls)
            continue                       # one class, one decision
        if cls not in expected and cls not in allowed_extra:
            unexpected.add(cls)
            continue

        raw_status = row.get("review_status")
        status = "" if raw_status is None else str(raw_status).strip()
        if is_placeholder(status):
            nonterminal.append(
                f"{cls}: status '{status}' is blank or a placeholder, so it is not "
                f"terminal (terminal: {list(TERMINAL_STATUSES)})")
            continue
        if status not in TERMINAL_STATUSES:
            nonterminal.append(f"{cls}: status '{status}' is not terminal "
                               f"(terminal: {list(TERMINAL_STATUSES)})")
            continue

        if status == STATUS_APPROVED:
            problems = _validate_approved_row(
                row, cls, out_of_action_scope=cls in out_of_scope)
            if problems:
                invalid.extend(f"{cls}: {p}" for p in problems)
            else:
                approved.add(cls)
        else:
            problems = _validate_excluded_row(row)
            if problems:
                invalid.extend(f"{cls}: {p}" for p in problems)
            else:
                excluded.add(cls)

    missing = sorted(expected - set(seen))
    satisfied = bool(expected) and not (
        missing or unexpected or duplicated or nonterminal or invalid)
    # Belt and braces: coverage must also add up. If it does not, something in
    # the accounting above is wrong and the safe answer is 'not ready'.
    decided = approved | excluded
    if satisfied and not expected <= decided:
        satisfied = False
        invalid.append(
            f"internal accounting mismatch: {sorted(expected - decided)} expected but "
            "not terminally decided")

    return MappingReadiness(
        schema=MAPPING_READINESS_SCHEMA,
        dataset=dataset,
        artifact=str(artifact),
        artifact_digest=str(artifact_digest),
        expected_classes=len(expected),
        approved_classes=len(approved),
        excluded_classes=len(excluded),
        satisfied=satisfied,
        missing=tuple(missing),
        unexpected=tuple(sorted(unexpected)),
        duplicated=tuple(sorted(duplicated)),
        nonterminal=tuple(sorted(nonterminal)),
        invalid=tuple(sorted(invalid)),
    )
