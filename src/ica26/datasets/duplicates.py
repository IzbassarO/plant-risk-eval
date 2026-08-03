"""Byte-exact duplicate groups INSIDE one dataset, and their fail-closed gate.

Cross-dataset leakage (PlantVillage -> PlantDoc) is handled by
:mod:`ica26.leakage.gate`. This module covers a different and equally
disqualifying problem the R1 re-audit surfaced: the *same bytes* appearing twice
inside PlantDoc itself (R1-CRIT-002). Eleven of the twelve groups straddle the
train/test boundary, so held-out accuracy can be memorised rather than
generalised, and nine assign two different diagnosis labels to identical pixels,
so the ground truth itself is contradictory.

Nothing here adjudicates anything. It enumerates groups, proves byte and decoded
pixel identity, and refuses to report a resolved status until a human has
recorded a terminal decision for every group. Deleting, relabelling, or
re-splitting a record is a scientific decision and is deliberately impossible
from this module.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

#: Versioned canonical serialization for a duplicate group's identity. Bump this
#: rather than editing the field list -- changing it changes every group id.
DUPLICATE_GROUP_SCHEMA = "ica26.datasets.duplicate_group/1"

#: Hex digits of the identity digest kept in a canonical content id.
CANONICAL_ID_HEX = 16

#: Terminal decisions a human may record for a group. `unresolved` is the
#: absence of a decision, not a decision.
GROUP_HANDLING_DECISIONS = (
    "keep_all_records",
    "keep_one_record",
    "exclude_from_evaluation",
    "exclude_all_records",
    "needs_further_review",
)

#: Decisions that do NOT terminate review.
NON_TERMINAL_GROUP_DECISIONS = frozenset({"needs_further_review"})

SPLIT_HANDLING_DECISIONS = (
    "group_aware_split",
    "keep_current_split",
    "move_to_train",
    "move_to_test",
    "not_applicable",
)

GATE_STATUSES = ("pass", "fail", "incomplete")


@dataclass(frozen=True)
class DuplicateMember:
    """One record participating in a byte-exact duplicate group."""

    dataset: str
    original_archive_path: str
    active_relative_path: str
    split: str
    class_label: str
    byte_sha256: str
    decoded_rgb_sha256: str
    byte_size: int
    width: int
    height: int
    mode: str
    source_revision: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of records whose file bytes are identical."""

    dataset: str
    byte_sha256: str
    decoded_rgb_sha256: str
    members: tuple[DuplicateMember, ...]

    # -- derived facts (never decisions) ----------------------------------- #
    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def splits(self) -> tuple[str, ...]:
        return tuple(sorted({m.split for m in self.members}))

    @property
    def classes(self) -> tuple[str, ...]:
        return tuple(sorted({m.class_label for m in self.members}))

    @property
    def crosses_split(self) -> bool:
        return len(self.splits) > 1

    @property
    def crosses_class(self) -> bool:
        return len(self.classes) > 1

    @property
    def train_count(self) -> int:
        return sum(1 for m in self.members if m.split == "train")

    @property
    def test_count(self) -> int:
        return sum(1 for m in self.members if m.split == "test")

    @property
    def class_count(self) -> int:
        return len(self.classes)

    def canonical_serialization(self) -> str:
        """Deterministic, versioned serialization of the group's identity.

        Members are sorted, so the id does not depend on row order. Only
        serialization is normalised; no label, split, or digest is altered.
        """
        return json.dumps({
            "schema": DUPLICATE_GROUP_SCHEMA,
            "dataset": self.dataset,
            "byte_sha256": self.byte_sha256,
            "decoded_rgb_sha256": self.decoded_rgb_sha256,
            "members": sorted(
                [m.original_archive_path, m.split, m.class_label] for m in self.members
            ),
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @property
    def canonical_content_id(self) -> str:
        """Stable identity, e.g. ``pdup-1a2b3c4d5e6f7a8b``. Not row-order derived."""
        digest = hashlib.sha256(
            self.canonical_serialization().encode("utf-8")).hexdigest()
        return f"pdup-{digest[:CANONICAL_ID_HEX]}"


def decoded_rgb_sha256(path: str | Path) -> str:
    """SHA-256 of the decoded RGB pixel buffer.

    Separates a genuine re-encoding (same pixels, different bytes) from truly
    identical files. Computed, never fabricated; blank if the image cannot be
    decoded, which is itself reportable.
    """
    try:
        from PIL import Image

        with Image.open(path) as im:
            return hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()
    except Exception:
        return ""


def find_duplicate_groups(
    manifest_rows: Sequence[dict],
    *,
    dataset: str,
    source_revision: str,
    active_root: str | Path,
    original_path_of: Optional[dict[str, str]] = None,
) -> list[DuplicateGroup]:
    """Enumerate every byte-SHA group with more than one record.

    Grouping is on the manifest's recorded ``sha256`` -- file bytes, not
    perceptual similarity -- so membership is exact and not threshold-dependent.
    Returns groups sorted by ``byte_sha256`` for determinism.
    """
    original_path_of = original_path_of or {}
    by_sha: dict[str, list[dict]] = {}
    for r in manifest_rows:
        by_sha.setdefault(r["sha256"], []).append(r)

    groups: list[DuplicateGroup] = []
    for sha, rows in sorted(by_sha.items()):
        if len(rows) < 2:
            continue
        members = []
        decoded = ""
        for r in sorted(rows, key=lambda x: x["relpath"]):
            active = r["relpath"]
            d = decoded_rgb_sha256(Path(active_root) / active)
            decoded = decoded or d
            members.append(DuplicateMember(
                dataset=dataset,
                original_archive_path=original_path_of.get(active, active),
                active_relative_path=active,
                split=r["split"],
                class_label=r["class_label"],
                byte_sha256=r["sha256"],
                decoded_rgb_sha256=d,
                byte_size=int(r["n_bytes"]),
                width=int(r["width"]),
                height=int(r["height"]),
                mode=r["mode"],
                source_revision=source_revision,
            ))
        groups.append(DuplicateGroup(
            dataset=dataset, byte_sha256=sha,
            decoded_rgb_sha256=decoded, members=tuple(members)))
    return groups


def display_group_ids(groups: Sequence[DuplicateGroup]) -> dict[str, str]:
    """Authoritative ``canonical_content_id -> display id`` map (``G01`` …).

    Assigned from a canonical SORT of the groups' byte digests, so they are
    reproducible and independent of enumeration order. Display ids exist for
    human legibility only; they authorise nothing, and every consumer derives
    them from this one function so a packet and a gate can never disagree.
    """
    return {g.canonical_content_id: f"G{i:02d}"
            for i, g in enumerate(sorted(groups, key=lambda g: g.byte_sha256), 1)}


def member_ids(group: DuplicateGroup, display: str) -> dict[str, str]:
    """``active_relative_path -> member id`` (``G01-m1`` …) for one group.

    Members are numbered in the group's own canonical member order, which
    :func:`find_duplicate_groups` fixes by relative path.
    """
    return {m.active_relative_path: f"{display}-m{i}"
            for i, m in enumerate(group.members, 1)}


def aggregate(groups: Sequence[DuplicateGroup]) -> dict:
    """Counts a reader needs before deciding anything. Purely descriptive."""
    return {
        "groups": len(groups),
        "records": sum(g.member_count for g in groups),
        "cross_split_groups": sum(1 for g in groups if g.crosses_split),
        "cross_class_groups": sum(1 for g in groups if g.crosses_class),
        "same_class_same_split": sum(
            1 for g in groups if not g.crosses_class and not g.crosses_split),
        "same_class_cross_split": sum(
            1 for g in groups if not g.crosses_class and g.crosses_split),
        "cross_class_same_split": sum(
            1 for g in groups if g.crosses_class and not g.crosses_split),
        "cross_class_cross_split": sum(
            1 for g in groups if g.crosses_class and g.crosses_split),
        "byte_identical_groups": sum(
            1 for g in groups if len({m.byte_sha256 for m in g.members}) == 1),
        "pixel_identical_groups": sum(
            1 for g in groups
            if len({m.decoded_rgb_sha256 for m in g.members}) == 1
            and all(m.decoded_rgb_sha256 for m in g.members)),
    }


# --------------------------------------------------------------------------- #
# Fail-closed internal-duplicate gate
# --------------------------------------------------------------------------- #
@dataclass
class InternalDuplicateGate:
    """Separate from the cross-dataset gate on purpose.

    Overloading one artifact with two different scientific questions is how a
    'pass' comes to mean less than a reader assumes. This one answers exactly:
    *has a human adjudicated every intra-dataset exact-duplicate group, and does
    the effective dataset contain precisely what those decisions authorise?*

    Schema 2.0 (R2B) added the second half. A 1.0 gate is rejected rather than
    reinterpreted: its ``pass`` meant only that decisions had been recorded, not
    that they had been applied, so the two statuses are not comparable.
    """

    schema_version: str
    dataset: str
    group_schema: str
    total_groups: int
    total_records: int
    cross_split_groups: int
    cross_class_groups: int
    resolved_groups: int
    unresolved_groups: int
    status: str
    violations: list = field(default_factory=list)
    unresolved_group_ids: list = field(default_factory=list)
    input_digests: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    remediation: dict = field(default_factory=dict)
    identity_reconciliation: dict = field(default_factory=dict)
    group_outcomes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "InternalDuplicateGate":
        known = {f: d[f] for f in InternalDuplicateGate.__annotations__ if f in d}
        return InternalDuplicateGate(**known)

    def write(self, path: str | Path) -> Path:
        """Atomic, deterministic write: sorted keys, LF, trailing newline."""
        import os

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"
        tmp = path.with_name(path.name + ".part")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
        return path


# 1.0: adjudication completeness only -- did a human decide every group?
# 2.0: R2B. The gate additionally proves the decisions were APPLIED: one
#      canonical record per keep_one_record group, zero per exclude_all_records,
#      no surviving exact duplicate, no non-reviewed record changed, and the
#      persisted effective dataset equal by IDENTITY SET to a fresh rebuild.
INTERNAL_GATE_SCHEMA_VERSION = "2.0"


def _decision_of(row: dict) -> str:
    return (row.get("group_handling_decision") or "").strip()


def _rows_from_groups(groups: Sequence[DuplicateGroup]) -> list[dict]:
    """Manifest-shaped rows for exactly the duplicate members.

    Used when no dataset manifest is supplied: the remediation checks then run
    over the groups' own records rather than being skipped. Verification is never
    optional -- an unevaluated check is indistinguishable from a passing one.
    """
    return [{"dataset": m.dataset, "split": m.split, "class_label": m.class_label,
             "relpath": m.active_relative_path, "sha256": m.byte_sha256,
             "width": m.width, "height": m.height, "mode": m.mode,
             "n_bytes": m.byte_size}
            for g in groups for m in g.members]


def build_internal_duplicate_gate(
    groups: Sequence[DuplicateGroup],
    decisions: Iterable[dict] = (),
    *,
    dataset: str,
    input_digests: Optional[dict] = None,
    provenance: Optional[dict] = None,
    manifest_rows: Optional[Sequence[dict]] = None,
    persisted_effective: Optional[Sequence[dict]] = None,
) -> InternalDuplicateGate:
    """Resolve only when every group is decided AND the decisions are applied.

    Adjudication half (schema 1.0): a group with no decision row, a blank
    decision, an unsupported decision, a non-terminal decision, a duplicate
    decision row, or a decision for an unknown group all prevent ``pass``.

    Remediation half (schema 2.0): the recorded decisions are applied to
    ``manifest_rows`` and the result is verified — exactly one retained record
    per ``keep_one_record`` group and zero per ``exclude_all_records``, the
    adjudicated label and split on every retained record, no exact duplicate
    surviving anywhere (so none across train and test), no duplicated record
    identity, and **no change to any record outside the reviewed set**. When
    ``persisted_effective`` is given, the persisted file must equal a fresh
    rebuild by identity SET, not by row count.

    There is no count parameter and no override, and no check is skippable: with
    no manifest supplied the remediation runs over the groups' own members.
    """
    from .duplicate_remediation import (
        REMEDIATION_SCHEMA,
        apply_adjudication,
        build_effective_records,
        identity_set_digest,
        reconcile_identity_sets,
        verify_effective_records,
    )

    decisions = list(decisions)
    by_id = {g.canonical_content_id: g for g in groups}
    violations: list[str] = []
    seen: dict[str, int] = {}
    resolved: set[str] = set()

    for i, row in enumerate(decisions, start=2):
        cid = (row.get("canonical_content_id") or "").strip()
        where = f"decision row {i} ({cid or '<blank>'})"
        if not cid:
            violations.append(f"{where}: blank canonical_content_id")
            continue
        if cid in seen:
            violations.append(
                f"{where}: duplicate decision, first seen at row {seen[cid]}")
            continue
        seen[cid] = i
        if cid not in by_id:
            violations.append(
                f"{where}: does not correspond to any enumerated duplicate group")
            continue

        decision = _decision_of(row)
        if not decision:
            continue  # undecided: no credit, no violation
        if decision not in GROUP_HANDLING_DECISIONS:
            violations.append(
                f"{where}: unsupported group_handling_decision '{decision}' "
                f"(allowed: {list(GROUP_HANDLING_DECISIONS)})")
            continue
        if decision in NON_TERMINAL_GROUP_DECISIONS:
            continue  # deferred: resolves nothing
        for fld in ("decision_reason", "reviewer", "reviewed_at"):
            if not (row.get(fld) or "").strip():
                violations.append(f"{where}: terminal decision without '{fld}'")
                break
        else:
            from ..leakage.gate import parse_review_timestamp

            _, err = parse_review_timestamp(row.get("reviewed_at"))
            if err:
                violations.append(f"{where}: {err}")
            else:
                resolved.add(cid)

    unresolved = sorted(set(by_id) - resolved)
    agg = aggregate(groups)

    # ---- remediation half (schema 2.0) ------------------------------------- #
    # Applying decisions we could not authenticate would be meaningless, so the
    # remediation runs only once the adjudication half is clean -- the same
    # precondition discipline the cross-dataset gate uses for identity equality.
    source_rows = list(manifest_rows) if manifest_rows is not None else _rows_from_groups(groups)
    remediation: dict = {"schema": None, "evaluated": False, "ok": False}
    reconciliation: dict = {"evaluated": False, "equal": False}
    outcomes: list = []

    if violations or unresolved:
        remediation["reason"] = (
            "not evaluated: the adjudication is not clean, so applying it would "
            "authenticate against decisions that were never credited")
        reconciliation["reason"] = remediation["reason"]
    else:
        adj = apply_adjudication(groups, decisions)
        effective, build_violations = build_effective_records(source_rows, adj)
        verify_violations, report = verify_effective_records(
            source_rows, effective, adj, groups)
        remediation_violations = list(adj.violations) + list(build_violations) + list(verify_violations)
        violations.extend(remediation_violations)

        remediation = {
            "schema": REMEDIATION_SCHEMA,
            "evaluated": True,
            "ok": not remediation_violations,
            "manifest_supplied": manifest_rows is not None,
            "effective_identity_digest": identity_set_digest(effective),
            **report,
        }
        outcomes = sorted(
            ({"display_group_id": g.display_group_id,
              "group_id": g.group_id,
              "action": g.action,
              "retained_record_count": len(g.retained),
              "excluded_record_count": len(g.excluded),
              "retained": sorted(m.member.active_relative_path for m in g.retained),
              "excluded": sorted(m.member.active_relative_path for m in g.excluded),
              "effective_split": next((m.effective_split for m in g.retained), ""),
              "effective_class_label": next((m.effective_class_label for m in g.retained), "")}
             for g in adj.groups.values()),
            key=lambda d: d["display_group_id"])

        if persisted_effective is None:
            reconciliation = {
                "evaluated": False, "equal": False,
                "reason": "no persisted effective dataset was supplied for comparison"}
            violations.append(
                "no persisted effective dataset was supplied; fresh-vs-persisted "
                "equality could not be proved")
        else:
            set_violations, reconciliation = reconcile_identity_sets(
                effective, list(persisted_effective))
            reconciliation["evaluated"] = True
            violations.extend(set_violations)

    if violations:
        status = "fail"
    elif unresolved:
        status = "incomplete"
    elif not (remediation.get("ok") and reconciliation.get("equal")):
        status = "fail"
    else:
        status = "pass"

    return InternalDuplicateGate(
        schema_version=INTERNAL_GATE_SCHEMA_VERSION,
        dataset=dataset,
        group_schema=DUPLICATE_GROUP_SCHEMA,
        total_groups=agg["groups"],
        total_records=agg["records"],
        cross_split_groups=agg["cross_split_groups"],
        cross_class_groups=agg["cross_class_groups"],
        resolved_groups=len(resolved),
        unresolved_groups=len(unresolved),
        status=status,
        violations=sorted(violations),
        unresolved_group_ids=unresolved,
        input_digests=dict(sorted((input_digests or {}).items())),
        provenance=dict(sorted((provenance or {}).items())),
        remediation=dict(sorted(remediation.items())),
        identity_reconciliation=dict(sorted(reconciliation.items())),
        group_outcomes=outcomes,
    )


def validate_internal_gate(gate: Optional[InternalDuplicateGate]) -> list[str]:
    """Fail-closed validation for consumers. Empty list == the gate authorises use.

    A caller must never read ``status`` alone: a gate from schema 1.0 says only
    that decisions were recorded, and an unevaluated remediation block is
    indistinguishable from a passing one if you do not look.
    """
    if gate is None:
        return ["internal duplicate gate is missing"]
    errors: list[str] = []
    if gate.schema_version != INTERNAL_GATE_SCHEMA_VERSION:
        return [f"unsupported internal-duplicate gate schema '{gate.schema_version}' "
                f"(expected {INTERNAL_GATE_SCHEMA_VERSION}); an older gate did not "
                "verify that decisions were applied"]
    if gate.status != "pass":
        errors.append(f"gate status is '{gate.status}', not 'pass'")
    if gate.unresolved_groups:
        errors.append(f"{gate.unresolved_groups} unadjudicated duplicate group(s)")
    if gate.violations:
        errors.append(f"{len(gate.violations)} violation(s), first: {gate.violations[0]}")
    if not (gate.remediation or {}).get("evaluated"):
        errors.append("the remediation half of the gate was never evaluated")
    elif not gate.remediation.get("ok"):
        errors.append("the remediation did not verify")
    if not (gate.identity_reconciliation or {}).get("equal"):
        errors.append("persisted and freshly reconstructed identity sets are not equal")
    return errors
