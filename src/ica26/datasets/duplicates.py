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
    *has a human adjudicated every intra-dataset exact-duplicate group?*
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


INTERNAL_GATE_SCHEMA_VERSION = "1.0"


def _decision_of(row: dict) -> str:
    return (row.get("group_handling_decision") or "").strip()


def build_internal_duplicate_gate(
    groups: Sequence[DuplicateGroup],
    decisions: Iterable[dict] = (),
    *,
    dataset: str,
    input_digests: Optional[dict] = None,
    provenance: Optional[dict] = None,
) -> InternalDuplicateGate:
    """Resolve only when EVERY group carries a terminal human decision.

    A group with no decision row, a blank decision, an unsupported decision, a
    non-terminal decision, a duplicate decision row, or a decision for an unknown
    group all prevent ``pass``. There is no count parameter and no override.
    """
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

    if violations:
        status = "fail"
    elif unresolved:
        status = "incomplete"
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
    )
