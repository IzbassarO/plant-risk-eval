"""Apply a HUMAN adjudication of PlantDoc byte-exact duplicate groups (R2B).

:mod:`ica26.datasets.duplicates` enumerates the groups and refuses to report a
resolved status until a human has recorded a terminal decision for every one of
them. It decides nothing. This module is the other half: it takes those recorded
decisions and derives, deterministically, the **effective** record set — and it
still decides nothing. Every label, split, and exclusion it emits is read from a
decision row; nothing is inferred, defaulted, or guessed.

Two decisions are implementable here, and only these two:

``keep_one_record``
    Retain exactly one canonical member, on the adjudicated split, with the
    adjudicated label. Every other member of the group leaves the effective
    dataset. The retained record's file is never moved and never rewritten; the
    split and label are *overridden* in the effective manifest, and both the
    source and effective values are recorded in the resolution table.

``exclude_all_records``
    Every member leaves the effective dataset. No label is assigned — the point
    of the decision is that no defensible label exists.

Any other terminal decision from :data:`GROUP_HANDLING_DECISIONS` is a
**violation**, not a no-op: ``keep_all_records`` on a group that straddles
train/test would leave byte-identical pixels on both sides of the split, and this
module will not silently materialise that.

Authentication (the same standard as the cross-dataset gate)
------------------------------------------------------------
A decision row is credited only if it reproduces the freshly enumerated group's
identity field-for-field: byte digest, decoded-pixel digest, member count, split
and class counts, class labels, the content-derived group id, and the
authoritative display id. Because the group id is itself a digest over every
member's path, split, and label, a forged member set cannot keep its id — the
same-row-count substitution that R1-CRIT-001 exploited cannot pass here either.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Iterable, Optional, Sequence

from .duplicates import (
    GROUP_HANDLING_DECISIONS,
    NON_TERMINAL_GROUP_DECISIONS,
    SPLIT_HANDLING_DECISIONS,
    DuplicateGroup,
    DuplicateMember,
    display_group_ids,
    member_ids,
)

#: Versioned serialization for one effective record's scientific identity. Bump
#: this rather than editing the field list -- changing it changes every id.
EFFECTIVE_RECORD_SCHEMA = "ica26.datasets.effective_record/1"

#: Versioned identity of the remediation itself, recorded in the gate.
REMEDIATION_SCHEMA = "ica26.datasets.duplicate_remediation/1"

#: Hex digits of the identity digest kept in an effective record id.
EFFECTIVE_ID_HEX = 16

#: Terminal decisions this remediation knows how to materialise. A terminal
#: decision outside this set is a violation, never a silent pass-through.
REMEDIABLE_ACTIONS = ("keep_one_record", "exclude_all_records")

#: What happened to one reviewed record. Derived, never chosen.
MEMBER_ACTIONS = ("retain_canonical", "exclude_duplicate", "exclude_group")

#: Split decisions that name exactly one destination split.
_SPLIT_TARGET = {"move_to_train": "train", "move_to_test": "test"}

#: The sentinel a reviewer writes when a field does not apply.
NOT_APPLICABLE = "not_applicable"

#: Columns of the persisted resolution table (the R2B provenance record).
RESOLUTION_COLUMNS = (
    "group_id", "display_group_id", "member_id", "dataset",
    "original_archive_path", "active_relative_path",
    "source_split", "source_class_label", "byte_sha256", "decoded_rgb_sha256",
    "byte_size", "width", "height", "mode", "source_revision",
    "group_handling_decision", "canonical_label_decision", "split_handling_decision",
    "remediation_action", "effective_split", "effective_class_label",
    "effective_record_id", "decision_reason", "reviewer", "reviewed_at",
)

#: Group-level evidence columns a decision row must reproduce exactly. These are
#: facts about the data, not decisions, so any drift means the row was written
#: against a different dataset than the one in front of us.
_EVIDENCE_COLUMNS = (
    "group_id", "display_group_id", "byte_sha256", "decoded_rgb_sha256",
    "member_count", "crosses_split", "crosses_class", "train_count",
    "test_count", "class_count", "class_labels",
)


def _s(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


# --------------------------------------------------------------------------- #
# Effective record identity
# --------------------------------------------------------------------------- #
def effective_record_serialization(row: dict) -> str:
    """Deterministic, versioned serialization of one effective record.

    Carries the fields that make a record scientifically what it is -- where its
    pixels live, what they are labelled, which side of the split they sit on, and
    their digest and geometry. Acquisition metadata is deliberately excluded: a
    re-acquisition timestamp is not a change of identity.
    """
    return json.dumps({
        "schema": EFFECTIVE_RECORD_SCHEMA,
        "dataset": str(row.get("dataset", "")),
        "relpath": str(row.get("relpath", "")),
        "split": str(row.get("split", "")),
        "class_label": str(row.get("class_label", "")),
        "sha256": str(row.get("sha256", "")),
        "n_bytes": str(row.get("n_bytes", "")),
        "width": str(row.get("width", "")),
        "height": str(row.get("height", "")),
        "mode": str(row.get("mode", "")),
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def effective_record_id(row: dict) -> str:
    """Stable identity, e.g. ``erec-1a2b3c4d5e6f7a8b``. Not row-order derived."""
    digest = hashlib.sha256(
        effective_record_serialization(row).encode("utf-8")).hexdigest()
    return f"erec-{digest[:EFFECTIVE_ID_HEX]}"


def identity_set(rows: Iterable[dict]) -> list[str]:
    """Sorted effective-record identities. The unit of set comparison."""
    return sorted(effective_record_id(r) for r in rows)


def identity_set_digest(rows: Iterable[dict]) -> str:
    """One digest over the whole identity SET, for compact reconciliation."""
    payload = json.dumps(identity_set(rows), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Outcomes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MemberOutcome:
    """What an explicit human decision did to one reviewed record."""

    group_id: str
    display_group_id: str
    member_id: str
    member: DuplicateMember
    action: str
    effective_split: str            # "" when the record leaves the dataset
    effective_class_label: str      # "" when the record leaves the dataset
    group_handling_decision: str
    canonical_label_decision: str
    split_handling_decision: str
    decision_reason: str
    reviewer: str
    reviewed_at: str

    @property
    def retained(self) -> bool:
        return self.action == "retain_canonical"

    def as_row(self) -> dict:
        m = self.member
        row = {
            "group_id": self.group_id,
            "display_group_id": self.display_group_id,
            "member_id": self.member_id,
            "dataset": m.dataset,
            "original_archive_path": m.original_archive_path,
            "active_relative_path": m.active_relative_path,
            "source_split": m.split,
            "source_class_label": m.class_label,
            "byte_sha256": m.byte_sha256,
            "decoded_rgb_sha256": m.decoded_rgb_sha256,
            "byte_size": m.byte_size,
            "width": m.width,
            "height": m.height,
            "mode": m.mode,
            "source_revision": m.source_revision,
            "group_handling_decision": self.group_handling_decision,
            "canonical_label_decision": self.canonical_label_decision,
            "split_handling_decision": self.split_handling_decision,
            "remediation_action": self.action,
            "effective_split": self.effective_split,
            "effective_class_label": self.effective_class_label,
            "effective_record_id": "",
            "decision_reason": self.decision_reason,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
        }
        if self.retained:
            row["effective_record_id"] = effective_record_id({
                "dataset": m.dataset, "relpath": m.active_relative_path,
                "split": self.effective_split, "class_label": self.effective_class_label,
                "sha256": m.byte_sha256, "n_bytes": m.byte_size,
                "width": m.width, "height": m.height, "mode": m.mode,
            })
        return row


@dataclass(frozen=True)
class GroupOutcome:
    group_id: str
    display_group_id: str
    action: str
    members: tuple[MemberOutcome, ...]

    @property
    def retained(self) -> tuple[MemberOutcome, ...]:
        return tuple(m for m in self.members if m.retained)

    @property
    def excluded(self) -> tuple[MemberOutcome, ...]:
        return tuple(m for m in self.members if not m.retained)


@dataclass
class Adjudication:
    """The applied decisions, or the reasons they could not be applied."""

    groups: dict = field(default_factory=dict)          # cid -> GroupOutcome
    violations: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def members(self) -> list[MemberOutcome]:
        """All reviewed records, in a deterministic order."""
        out = [m for g in self.groups.values() for m in g.members]
        return sorted(out, key=lambda m: (m.display_group_id, m.member_id))

    @property
    def retained_by_path(self) -> dict[str, MemberOutcome]:
        return {m.member.active_relative_path: m for m in self.members if m.retained}

    @property
    def excluded_by_path(self) -> dict[str, MemberOutcome]:
        return {m.member.active_relative_path: m for m in self.members if not m.retained}

    def counts(self) -> dict:
        by_action: dict[str, int] = {a: 0 for a in REMEDIABLE_ACTIONS}
        for g in self.groups.values():
            by_action[g.action] = by_action.get(g.action, 0) + 1
        return {
            "groups": len(self.groups),
            "reviewed_records": len(self.members),
            "retained_records": sum(1 for m in self.members if m.retained),
            "excluded_records": sum(1 for m in self.members if not m.retained),
            "groups_by_action": dict(sorted(by_action.items())),
        }


# --------------------------------------------------------------------------- #
# Canonical member resolution
# --------------------------------------------------------------------------- #
def resolve_canonical_member(
    group: DuplicateGroup, target_split: str,
) -> Optional[DuplicateMember]:
    """Pick the single member to retain. Deterministic and content-derived.

    Members of an exact-duplicate group are byte-identical, so *which* file is
    kept is not a scientific choice -- only the split and label are, and a human
    made both. The rule is therefore mechanical and stated once here:

    1. prefer a member already sitting on the adjudicated split, so the decision
       needs no file to move;
    2. among the candidates, take the lexicographically smallest active relative
       path.

    Returns ``None`` only if the group has no members, which the caller reports
    as an unresolvable canonical record rather than papering over.
    """
    if not group.members:
        return None
    on_target = [m for m in group.members if m.split == target_split]
    pool = on_target or list(group.members)
    return sorted(pool, key=lambda m: m.active_relative_path)[0]


# --------------------------------------------------------------------------- #
# Decision authentication + application
# --------------------------------------------------------------------------- #
def _expected_evidence(group: DuplicateGroup, display: str) -> dict[str, str]:
    return {
        "group_id": group.canonical_content_id,
        "display_group_id": display,
        "byte_sha256": group.byte_sha256,
        "decoded_rgb_sha256": group.decoded_rgb_sha256,
        "member_count": str(group.member_count),
        "crosses_split": "true" if group.crosses_split else "false",
        "crosses_class": "true" if group.crosses_class else "false",
        "train_count": str(group.train_count),
        "test_count": str(group.test_count),
        "class_count": str(group.class_count),
        "class_labels": " | ".join(group.classes),
    }


def apply_adjudication(
    groups: Sequence[DuplicateGroup],
    decisions: Iterable[dict],
) -> Adjudication:
    """Turn authenticated human decisions into per-record outcomes.

    Fails closed on: a group with no decision row, a duplicated decision row, a
    row naming an unknown group, a blank or non-terminal decision, a terminal
    decision this module cannot materialise, missing attribution, an invalid
    review timestamp, any drift in the group's evidence columns, a
    ``keep_one_record`` without a usable canonical label or a single destination
    split, an ``exclude_all_records`` that nevertheless asserts a label or split,
    and a canonical record that cannot be resolved.

    Violations accumulate rather than raising, so one run reports every problem;
    an ``Adjudication`` with violations must never be applied.
    """
    from ..leakage.gate import parse_review_timestamp

    adj = Adjudication()
    by_id = {g.canonical_content_id: g for g in groups}
    display = display_group_ids(groups)
    seen: dict[str, int] = {}

    for i, row in enumerate(decisions, start=2):
        cid = _s(row, "canonical_content_id")
        where = f"decision row {i} ({cid or '<blank>'})"
        if not cid:
            adj.violations.append(f"{where}: blank canonical_content_id")
            continue
        if cid in seen:
            adj.violations.append(
                f"{where}: duplicate decision, first seen at row {seen[cid]}")
            continue
        seen[cid] = i
        group = by_id.get(cid)
        if group is None:
            adj.violations.append(
                f"{where}: does not correspond to any enumerated duplicate group")
            continue

        where = f"decision row {i} ({display[cid]} {cid})"

        # Evidence drift means the row was written against different data.
        drift = []
        for col, want in _expected_evidence(group, display[cid]).items():
            got = _s(row, col)
            if got != want:
                drift.append(f"{col} is '{got}', authoritative value is '{want}'")
        if drift:
            adj.violations.append(f"{where}: evidence mismatch -- " + "; ".join(drift))
            continue

        action = _s(row, "group_handling_decision")
        if not action:
            adj.violations.append(f"{where}: no group_handling_decision recorded")
            continue
        if action not in GROUP_HANDLING_DECISIONS:
            adj.violations.append(
                f"{where}: unsupported group_handling_decision '{action}' "
                f"(allowed: {list(GROUP_HANDLING_DECISIONS)})")
            continue
        if action in NON_TERMINAL_GROUP_DECISIONS:
            adj.violations.append(
                f"{where}: '{action}' is not terminal and resolves nothing")
            continue
        if action not in REMEDIABLE_ACTIONS:
            adj.violations.append(
                f"{where}: terminal decision '{action}' has no defined remediation; "
                f"the effective dataset cannot be derived from it "
                f"(remediable: {list(REMEDIABLE_ACTIONS)})")
            continue

        reason, reviewer, stamp = (_s(row, "decision_reason"), _s(row, "reviewer"),
                                   _s(row, "reviewed_at"))
        missing = [c for c, v in (("decision_reason", reason), ("reviewer", reviewer),
                                  ("reviewed_at", stamp)) if not v]
        if missing:
            adj.violations.append(f"{where}: terminal decision without {missing}")
            continue
        _, ts_error = parse_review_timestamp(stamp)
        if ts_error:
            adj.violations.append(f"{where}: {ts_error}")
            continue

        label = _s(row, "canonical_label_decision")
        split_decision = _s(row, "split_handling_decision")
        if split_decision and split_decision not in SPLIT_HANDLING_DECISIONS:
            adj.violations.append(
                f"{where}: unsupported split_handling_decision '{split_decision}' "
                f"(allowed: {list(SPLIT_HANDLING_DECISIONS)})")
            continue

        common = dict(group_handling_decision=action, canonical_label_decision=label,
                      split_handling_decision=split_decision, decision_reason=reason,
                      reviewer=reviewer, reviewed_at=stamp)
        ids = member_ids(group, display[cid])

        if action == "exclude_all_records":
            # No label may be asserted for a group that was excluded precisely
            # because no defensible label exists.
            bad = [f"{c}='{v}'" for c, v in (("canonical_label_decision", label),
                                             ("split_handling_decision", split_decision))
                   if v and v != NOT_APPLICABLE]
            if bad:
                adj.violations.append(
                    f"{where}: exclude_all_records must not assert {', '.join(bad)}; "
                    f"expected '{NOT_APPLICABLE}'")
                continue
            outcomes = tuple(
                MemberOutcome(group_id=cid, display_group_id=display[cid],
                              member_id=ids[m.active_relative_path], member=m,
                              action="exclude_group", effective_split="",
                              effective_class_label="", **common)
                for m in group.members)
            adj.groups[cid] = GroupOutcome(cid, display[cid], action, outcomes)
            continue

        # ---- keep_one_record ------------------------------------------------ #
        if not label or label == NOT_APPLICABLE:
            adj.violations.append(
                f"{where}: keep_one_record requires an explicit canonical_label_decision "
                f"(got '{label or '<blank>'}'); no label is inferred here")
            continue
        target = _SPLIT_TARGET.get(split_decision)
        if target is None:
            if split_decision == "keep_current_split" and not group.crosses_split:
                target = group.members[0].split
            else:
                adj.violations.append(
                    f"{where}: keep_one_record requires a split_handling_decision naming "
                    f"one destination split (got '{split_decision or '<blank>'}'); "
                    f"{sorted(_SPLIT_TARGET)} name one, and 'keep_current_split' does so "
                    f"only for a group that does not cross the split")
                continue
        canonical = resolve_canonical_member(group, target)
        if canonical is None:
            adj.violations.append(
                f"{where}: canonical record cannot be resolved (group has no members)")
            continue

        outcomes = tuple(
            MemberOutcome(
                group_id=cid, display_group_id=display[cid],
                member_id=ids[m.active_relative_path], member=m,
                action="retain_canonical" if m is canonical else "exclude_duplicate",
                effective_split=target if m is canonical else "",
                effective_class_label=label if m is canonical else "",
                **common)
            for m in group.members)
        adj.groups[cid] = GroupOutcome(cid, display[cid], action, outcomes)

    for cid in sorted(set(by_id) - set(seen)):
        adj.violations.append(
            f"enumerated duplicate group {display[cid]} ({cid}) has no decision row")

    # A record may belong to exactly one group; two claims on one file would make
    # the effective label and split ambiguous.
    claimed: dict[str, str] = {}
    for m in adj.members:
        path = m.member.active_relative_path
        if path in claimed and claimed[path] != m.group_id:
            adj.violations.append(
                f"record '{path}' is claimed by two duplicate groups "
                f"({claimed[path]} and {m.group_id})")
        claimed[path] = m.group_id

    adj.violations.sort()
    return adj


# --------------------------------------------------------------------------- #
# Effective record set
# --------------------------------------------------------------------------- #
def build_effective_records(
    manifest_rows: Sequence[dict],
    adjudication: Adjudication,
) -> tuple[list[dict], list[str]]:
    """Materialise the effective record set from the manifest + outcomes.

    Returns ``(rows, violations)``. Rows keep the manifest schema exactly, with
    ``split`` and ``class_label`` carrying the adjudicated values for a retained
    canonical record; provenance for every change lives in the resolution table.
    Order is canonical (split, class, relpath), so the output is byte-stable.

    Violations here are about the manifest disagreeing with the reviewed
    evidence: a reviewed record that is absent, duplicated, or whose digest,
    label, split or geometry has moved since the review, and a canonical label
    outside the dataset's own vocabulary.
    """
    violations: list[str] = []
    rows_by_path: dict[str, list[dict]] = {}
    for r in manifest_rows:
        rows_by_path.setdefault(str(r.get("relpath", "")), []).append(r)

    vocabulary = {str(r.get("class_label", "")) for r in manifest_rows}
    outcomes = {m.member.active_relative_path: m for m in adjudication.members}

    for path, outcome in sorted(outcomes.items()):
        found = rows_by_path.get(path, [])
        if not found:
            violations.append(
                f"{outcome.display_group_id}/{outcome.member_id}: reviewed record "
                f"'{path}' is absent from the manifest (authoritative membership changed)")
            continue
        if len(found) > 1:
            violations.append(
                f"{outcome.display_group_id}/{outcome.member_id}: reviewed record "
                f"'{path}' appears {len(found)} times in the manifest")
            continue
        row, m = found[0], outcome.member
        for col, want, what in (("sha256", m.byte_sha256, "byte digest"),
                                ("split", m.split, "split"),
                                ("class_label", m.class_label, "class label"),
                                ("n_bytes", str(m.byte_size), "byte size"),
                                ("width", str(m.width), "width"),
                                ("height", str(m.height), "height"),
                                ("mode", m.mode, "mode")):
            got = str(row.get(col, ""))
            if got != want:
                violations.append(
                    f"{outcome.display_group_id}/{outcome.member_id}: manifest {what} "
                    f"for '{path}' is '{got}', reviewed evidence records '{want}'")
        if outcome.retained and outcome.effective_class_label not in vocabulary:
            violations.append(
                f"{outcome.display_group_id}: canonical label "
                f"'{outcome.effective_class_label}' is not in the dataset's class "
                f"vocabulary; a decision may not invent a class")

    effective: list[dict] = []
    for r in manifest_rows:
        path = str(r.get("relpath", ""))
        outcome = outcomes.get(path)
        if outcome is None:
            effective.append(dict(r))          # untouched, byte-for-byte
            continue
        if not outcome.retained:
            continue                            # excluded by an explicit decision
        row = dict(r)
        row["split"] = outcome.effective_split
        row["class_label"] = outcome.effective_class_label
        effective.append(row)

    effective.sort(key=lambda r: (str(r.get("split", "")), str(r.get("class_label", "")),
                                  str(r.get("relpath", ""))))
    return effective, violations


def reconcile_identity_sets(fresh: Sequence[dict], persisted: Sequence[dict]) -> tuple[list[str], dict]:
    """Require identity-SET equality between a fresh rebuild and the persisted file.

    Counting is not enough and never was: a persisted file with the right number
    of rows but a substituted record must not reconcile. Comparing the sets of
    effective record identities makes every substitution -- path, split, label,
    digest, or geometry -- a mismatch at equal counts.
    """
    fresh_ids, persisted_ids = set(identity_set(fresh)), set(identity_set(persisted))
    fresh_only = sorted(fresh_ids - persisted_ids)
    persisted_only = sorted(persisted_ids - fresh_ids)

    violations: list[str] = []
    for i in fresh_only[:20]:
        violations.append(f"freshly reconstructed record {i} is absent from the persisted set")
    for i in persisted_only[:20]:
        violations.append(f"persisted record {i} was not produced by fresh reconstruction")
    if len(fresh_only) > 20 or len(persisted_only) > 20:
        violations.append(
            f"identity-set difference truncated: {len(fresh_only)} fresh-only and "
            f"{len(persisted_only)} persisted-only record(s) in total")

    report = {
        "schema": EFFECTIVE_RECORD_SCHEMA,
        "fresh_count": len(fresh_ids),
        "persisted_count": len(persisted_ids),
        "equal": not violations,
        "fresh_only": fresh_only[:20],
        "persisted_only": persisted_only[:20],
        "fresh_digest": identity_set_digest(fresh),
        "persisted_digest": identity_set_digest(persisted),
    }
    return violations, report


# --------------------------------------------------------------------------- #
# Verification of the materialised result
# --------------------------------------------------------------------------- #
def verify_effective_records(
    manifest_rows: Sequence[dict],
    effective_rows: Sequence[dict],
    adjudication: Adjudication,
    groups: Sequence[DuplicateGroup],
) -> tuple[list[str], dict]:
    """Prove the effective set is exactly what the human decisions authorise.

    Independent of how the rows were produced: it re-derives what *should* have
    changed from the outcomes and compares against what *did* change. Checks

    * every enumerated group appears in the outcomes (none silently dropped);
    * exactly one retained record per ``keep_one_record`` group, zero per
      ``exclude_all_records`` group;
    * every excluded record is gone and every retained record is present, on the
      adjudicated split with the adjudicated label;
    * **no record outside the reviewed set changed in any field**;
    * no relpath appears twice;
    * no byte digest appears twice, so no exact duplicate survives anywhere --
      which subsumes "none across train and test";
    * no surviving digest carries two class labels.
    """
    violations: list[str] = []
    outcomes = {m.member.active_relative_path: m for m in adjudication.members}

    for g in groups:
        cid = g.canonical_content_id
        outcome = adjudication.groups.get(cid)
        if outcome is None:
            violations.append(
                f"enumerated duplicate group {cid} has no outcome; a group was dropped")
            continue
        n = len(outcome.retained)
        want = 1 if outcome.action == "keep_one_record" else 0
        if n != want:
            violations.append(
                f"{outcome.display_group_id} ({outcome.action}): {n} retained record(s), "
                f"expected exactly {want}")

    effective_by_path: dict[str, list[dict]] = {}
    for r in effective_rows:
        effective_by_path.setdefault(str(r.get("relpath", "")), []).append(r)

    for path, rows in sorted(effective_by_path.items()):
        if len(rows) > 1:
            violations.append(
                f"effective dataset contains '{path}' {len(rows)} times")

    for path, outcome in sorted(outcomes.items()):
        present = effective_by_path.get(path, [])
        if outcome.retained:
            if len(present) != 1:
                violations.append(
                    f"{outcome.display_group_id}/{outcome.member_id}: retained canonical "
                    f"record '{path}' appears {len(present)} time(s) in the effective "
                    "dataset, expected exactly 1")
                continue
            row = present[0]
            if str(row.get("split", "")) != outcome.effective_split:
                violations.append(
                    f"{outcome.display_group_id}: retained record '{path}' is on split "
                    f"'{row.get('split')}', adjudicated split is "
                    f"'{outcome.effective_split}'")
            if str(row.get("class_label", "")) != outcome.effective_class_label:
                violations.append(
                    f"{outcome.display_group_id}: retained record '{path}' is labelled "
                    f"'{row.get('class_label')}', adjudicated label is "
                    f"'{outcome.effective_class_label}'")
        elif present:
            violations.append(
                f"{outcome.display_group_id}/{outcome.member_id}: record '{path}' was "
                f"excluded by decision '{outcome.group_handling_decision}' but is still "
                "in the effective dataset")

    # Nothing outside the reviewed identity set may differ in ANY field.
    unreviewed = {str(r.get("relpath", "")): r for r in manifest_rows
                  if str(r.get("relpath", "")) not in outcomes}
    for path, source in sorted(unreviewed.items()):
        present = effective_by_path.get(path, [])
        if len(present) != 1:
            violations.append(
                f"non-reviewed record '{path}' appears {len(present)} time(s) in the "
                "effective dataset, expected exactly 1")
            continue
        changed = sorted(k for k in set(source) | set(present[0])
                         if str(source.get(k, "")) != str(present[0].get(k, "")))
        if changed:
            violations.append(
                f"non-reviewed record '{path}' changed in {changed}; only records "
                "covered by an explicit human decision may change")
    for path in sorted(set(effective_by_path) - set(unreviewed) - set(outcomes)):
        violations.append(
            f"effective dataset contains '{path}', which is in neither the manifest "
            "nor the reviewed set")

    by_digest: dict[str, list[dict]] = {}
    for r in effective_rows:
        by_digest.setdefault(str(r.get("sha256", "")), []).append(r)
    surviving_duplicates = {d: rs for d, rs in by_digest.items() if len(rs) > 1}
    for digest, rs in sorted(surviving_duplicates.items()):
        splits = sorted({str(r.get("split", "")) for r in rs})
        labels = sorted({str(r.get("class_label", "")) for r in rs})
        violations.append(
            f"byte digest {digest[:12]} still appears {len(rs)} times in the effective "
            f"dataset (splits {splits}, labels {labels})")

    cross_split = sum(1 for rs in surviving_duplicates.values()
                      if len({str(r.get("split", "")) for r in rs}) > 1)
    contradictory = sum(1 for rs in surviving_duplicates.values()
                        if len({str(r.get("class_label", "")) for r in rs}) > 1)

    report = {
        "schema": REMEDIATION_SCHEMA,
        "effective_records": len(effective_rows),
        "source_records": len(manifest_rows),
        "removed_records": len(manifest_rows) - len(effective_rows),
        "distinct_byte_digests": len(by_digest),
        "surviving_exact_duplicate_groups": len(surviving_duplicates),
        "surviving_cross_split_duplicate_groups": cross_split,
        "surviving_contradictory_label_groups": contradictory,
        "unique_relpaths": len(effective_by_path) == len(effective_rows),
        "unique_effective_identities": len(set(identity_set(effective_rows))) == len(effective_rows),
        "non_reviewed_records_unchanged": not any(
            "non-reviewed record" in v for v in violations),
        **adjudication.counts(),
    }
    violations.sort()
    return violations, report


def resolution_rows(adjudication: Adjudication) -> list[dict]:
    """The persisted provenance table: one row per reviewed record."""
    return [m.as_row() for m in adjudication.members]


def asdict_outcome(outcome: MemberOutcome) -> dict:  # pragma: no cover - convenience
    return asdict(outcome)
