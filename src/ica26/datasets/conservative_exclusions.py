"""Operator-recorded conservative exclusions for Core Dataset V1 (R2B.2).

:mod:`ica26.datasets.duplicate_remediation` applies the R2B human adjudication of
byte-exact duplicate groups and produces the *effective* PlantDoc record set. In
three of those groups (G07, G08, G10) the retained canonical record was given a
label that **no copy in the group carried**, or that adjudicated between two
contradictory diagnoses on identical pixels. Those relabels were referred for an
independent scientific second review, and that review has **not been performed**.

This module implements the other available response: the dataset owner may
decide, as a matter of data-quality policy rather than diagnosis, to drop the
uncertain records from the training/evaluation corpus. Excluding a record needs
no diagnosis — that is precisely why it is the conservative option.

What this module is NOT
-----------------------
It is not a second review, and it must never be mistaken for one. It records no
verdict on what G07/G08/G10 actually depict, confirms nothing about the applied
canonical labels, and leaves the open scientific question open. The R2B
adjudication, the review packet, and the pending-review status all remain
exactly as they were; the question simply stops being load-bearing for Core
Dataset V1 once the records are out of it.

Layering
--------
Exclusion is a third stage, applied *after* R2B and recorded separately so that
neither stage rewrites the other::

    plantdoc_manifest.csv            2,578  acquired source
      -> R2B duplicate remediation   2,564  plantdoc_effective_manifest.csv
        -> conservative exclusion    2,561  plantdoc_core_effective_manifest.csv

Authentication
--------------
A decision row is credited only if it reproduces the R2B outcome it claims to
overturn, field for field: content group id, display id, member id, active
relative path, byte and decoded-pixel digests, geometry, and the prior
remediation action, split, label, and effective record id. A row may only
exclude a record that R2B actually retained — a "conservative exclusion" of a
record that was never in the effective set decides nothing and is refused, as is
a row whose bound artifact digests no longer match the files on disk.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from ..governance.mapping import contains_placeholder_token, is_placeholder
from .duplicate_remediation import Adjudication, effective_record_id, identity_set

#: Versioned identity of the conservative-exclusion decision record. Bump rather
#: than editing the column list or the semantics in place.
CONSERVATIVE_EXCLUSION_SCHEMA = "ica26.datasets.conservative_exclusion/1"

#: The only decision this module can apply. It is deliberately a single value:
#: an exclusion table is not a place to record approvals, relabels, or reviews.
CONSERVATIVE_EXCLUSION_DECISION = "conservative_exclusion"

#: Why a record may be conservatively excluded. A free-text rationale is still
#: required, but the *basis* is a closed vocabulary so the reason a record left
#: Core Dataset V1 can be counted and audited without parsing prose.
EXCLUSION_BASES = ("insufficient_independent_diagnostic_evidence",)

#: Minimum characters of operator rationale. Short enough not to invite padding,
#: long enough that a bare word cannot stand in for a reason.
MIN_RATIONALE_CHARS = 40

#: Columns of the persisted decision table. Every one is either the operator's
#: decision or a binding to the exact record and artifacts it was taken against.
EXCLUSION_COLUMNS = (
    "decision_schema",
    "group_id",
    "display_group_id",
    "member_id",
    "dataset",
    "active_relative_path",
    "source_split",
    "source_class_label",
    "byte_sha256",
    "decoded_rgb_sha256",
    "byte_size",
    "width",
    "height",
    "mode",
    "source_revision",
    "prior_remediation_action",
    "prior_effective_split",
    "prior_effective_class_label",
    "prior_effective_record_id",
    "exclusion_decision",
    "exclusion_basis",
    "exclusion_rationale",
    "reviewer_id",
    "reviewer_role",
    "decided_at",
    "reviewed_repository_commit",
    "bound_resolution_sha256",
    "bound_effective_manifest_sha256",
    "bound_second_review_packet_sha256",
)

#: Artifact bindings a decision row must reproduce. Names map to the digest
#: column carrying them; the caller supplies the authoritative current values.
BOUND_ARTIFACTS = (
    "bound_resolution_sha256",
    "bound_effective_manifest_sha256",
    "bound_second_review_packet_sha256",
)

#: The prior R2B action a conservative exclusion may act on. Excluding a record
#: that R2B already removed is a no-op dressed as a decision.
EXCLUDABLE_PRIOR_ACTION = "retain_canonical"


def _s(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


@dataclass(frozen=True)
class ConservativeExclusion:
    """One authenticated operator decision to drop one retained record."""

    group_id: str
    display_group_id: str
    member_id: str
    dataset: str
    active_relative_path: str
    byte_sha256: str
    decoded_rgb_sha256: str
    prior_effective_split: str
    prior_effective_class_label: str
    prior_effective_record_id: str
    exclusion_basis: str
    exclusion_rationale: str
    reviewer_id: str
    reviewer_role: str
    decided_at: str
    reviewed_repository_commit: str

    def as_evidence(self) -> dict:
        """Compact, order-stable projection for reports and gate artifacts."""
        return {
            "display_group_id": self.display_group_id,
            "group_id": self.group_id,
            "member_id": self.member_id,
            "active_relative_path": self.active_relative_path,
            "byte_sha256": self.byte_sha256,
            "decoded_rgb_sha256": self.decoded_rgb_sha256,
            "prior_effective_record_id": self.prior_effective_record_id,
            "prior_effective_split": self.prior_effective_split,
            "prior_effective_class_label": self.prior_effective_class_label,
            "exclusion_basis": self.exclusion_basis,
        }


def _expected_binding(outcome, display: str) -> dict[str, str]:
    """The authoritative R2B facts a decision row must reproduce exactly."""
    member = outcome.member
    return {
        "group_id": outcome.group_id,
        "display_group_id": display,
        "member_id": outcome.member_id,
        "dataset": member.dataset,
        "active_relative_path": member.active_relative_path,
        "source_split": member.split,
        "source_class_label": member.class_label,
        "byte_sha256": member.byte_sha256,
        "decoded_rgb_sha256": member.decoded_rgb_sha256,
        "byte_size": str(member.byte_size),
        "width": str(member.width),
        "height": str(member.height),
        "mode": member.mode,
        "source_revision": member.source_revision,
        "prior_remediation_action": outcome.action,
        "prior_effective_split": outcome.effective_split,
        "prior_effective_class_label": outcome.effective_class_label,
        "prior_effective_record_id": outcome.as_row()["effective_record_id"],
    }


def parse_conservative_exclusions(
    rows: Iterable[dict],
    adjudication: Adjudication,
    *,
    artifact_digests: Optional[dict] = None,
    now=None,
) -> tuple[list[ConservativeExclusion], list[str]]:
    """Authenticate operator exclusion rows against the applied R2B outcomes.

    Fails closed on: an unknown or absent schema, a decision value other than
    ``conservative_exclusion``, a basis outside :data:`EXCLUSION_BASES`, a
    missing or placeholder rationale/reviewer/role, an invalid or naive
    timestamp, a malformed reviewed commit, a duplicated row, a row naming a
    record R2B never retained, any drift in the bound record evidence, and a
    stale artifact digest.

    Violations accumulate rather than raising, so one run reports every problem.
    """
    from ..leakage.gate import parse_review_timestamp

    violations: list[str] = []
    parsed: list[ConservativeExclusion] = []

    retained = {
        m.member.active_relative_path: m
        for m in adjudication.members if m.retained
    }
    display_of = {
        m.member.active_relative_path: m.display_group_id
        for m in adjudication.members if m.retained
    }
    seen: dict[str, int] = {}

    for i, row in enumerate(rows, start=2):
        path = _s(row, "active_relative_path")
        where = f"exclusion row {i} ({_s(row, 'display_group_id') or path or '<blank>'})"

        schema = _s(row, "decision_schema")
        if schema != CONSERVATIVE_EXCLUSION_SCHEMA:
            violations.append(
                f"{where}: decision_schema is '{schema or '<blank>'}', this module "
                f"only applies '{CONSERVATIVE_EXCLUSION_SCHEMA}'")
            continue

        if not path:
            violations.append(f"{where}: blank active_relative_path")
            continue
        if path in seen:
            violations.append(
                f"{where}: duplicate exclusion, first seen at row {seen[path]}")
            continue
        seen[path] = i

        outcome = retained.get(path)
        if outcome is None:
            violations.append(
                f"{where}: '{path}' is not a record retained by the R2B adjudication; "
                "a conservative exclusion may only remove a record that is currently "
                "in the effective dataset")
            continue

        drift = []
        for col, want in _expected_binding(outcome, display_of[path]).items():
            got = _s(row, col)
            if got != want:
                drift.append(f"{col} is '{got}', authoritative value is '{want}'")
        if drift:
            violations.append(f"{where}: evidence mismatch -- " + "; ".join(drift))
            continue

        if outcome.action != EXCLUDABLE_PRIOR_ACTION:
            violations.append(
                f"{where}: prior action '{outcome.action}' is not "
                f"'{EXCLUDABLE_PRIOR_ACTION}'")
            continue

        decision = _s(row, "exclusion_decision")
        if decision != CONSERVATIVE_EXCLUSION_DECISION:
            violations.append(
                f"{where}: exclusion_decision is '{decision or '<blank>'}', the only "
                f"supported value is '{CONSERVATIVE_EXCLUSION_DECISION}'")
            continue

        basis = _s(row, "exclusion_basis")
        if basis not in EXCLUSION_BASES:
            violations.append(
                f"{where}: exclusion_basis '{basis or '<blank>'}' is not one of "
                f"{list(EXCLUSION_BASES)}")
            continue

        rationale = _s(row, "exclusion_rationale")
        token = contains_placeholder_token(rationale)
        if is_placeholder(rationale) or token:
            violations.append(
                f"{where}: exclusion_rationale is blank or carries the placeholder "
                f"token '{token or rationale}'")
            continue
        if len(rationale) < MIN_RATIONALE_CHARS:
            violations.append(
                f"{where}: exclusion_rationale must be at least "
                f"{MIN_RATIONALE_CHARS} characters, got {len(rationale)}")
            continue

        reviewer_id, reviewer_role = _s(row, "reviewer_id"), _s(row, "reviewer_role")
        attribution_bad = False
        for field_name, value in (("reviewer_id", reviewer_id),
                                  ("reviewer_role", reviewer_role)):
            bad_token = contains_placeholder_token(value)
            if is_placeholder(value) or bad_token:
                violations.append(
                    f"{where}: {field_name} is blank or a placeholder"
                    + (f" ('{bad_token}')" if bad_token else ""))
                attribution_bad = True
        if attribution_bad:
            continue

        stamp = _s(row, "decided_at")
        _, ts_error = parse_review_timestamp(stamp, now=now)
        if ts_error:
            violations.append(f"{where}: decided_at {ts_error.split(' ', 1)[-1]}")
            continue

        commit = _s(row, "reviewed_repository_commit")
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            violations.append(
                f"{where}: reviewed_repository_commit '{commit or '<blank>'}' is not a "
                "40-character lowercase Git commit SHA")
            continue

        if artifact_digests is not None:
            stale = []
            for col in BOUND_ARTIFACTS:
                want = str(artifact_digests.get(col, ""))
                got = _s(row, col)
                if not want:
                    stale.append(f"{col} has no authoritative value to bind against")
                elif got != want:
                    stale.append(f"{col} is '{got}', the artifact now digests to '{want}'")
            if stale:
                violations.append(f"{where}: stale binding -- " + "; ".join(stale))
                continue

        parsed.append(ConservativeExclusion(
            group_id=_s(row, "group_id"),
            display_group_id=_s(row, "display_group_id"),
            member_id=_s(row, "member_id"),
            dataset=_s(row, "dataset"),
            active_relative_path=path,
            byte_sha256=_s(row, "byte_sha256"),
            decoded_rgb_sha256=_s(row, "decoded_rgb_sha256"),
            prior_effective_split=_s(row, "prior_effective_split"),
            prior_effective_class_label=_s(row, "prior_effective_class_label"),
            prior_effective_record_id=_s(row, "prior_effective_record_id"),
            exclusion_basis=basis,
            exclusion_rationale=rationale,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            decided_at=stamp,
            reviewed_repository_commit=commit,
        ))

    parsed.sort(key=lambda e: (e.display_group_id, e.member_id))
    violations.sort()
    return parsed, violations


def apply_conservative_exclusions(
    effective_rows: Sequence[dict],
    exclusions: Sequence[ConservativeExclusion],
) -> tuple[list[dict], list[str]]:
    """Remove exactly the excluded records from the R2B effective record set.

    Pure and idempotent: the result is a function of the inputs, canonically
    ordered, with no wall-clock field. Applying an already-applied exclusion set
    to its own output is a no-op that reports the records as already absent
    rather than silently succeeding, so callers always run it against the R2B
    stage rather than compounding stages by accident.
    """
    violations: list[str] = []
    by_path: dict[str, list[dict]] = {}
    for row in effective_rows:
        by_path.setdefault(str(row.get("relpath", "")), []).append(row)

    drop: set[str] = set()
    for exclusion in exclusions:
        path = exclusion.active_relative_path
        present = by_path.get(path, [])
        if len(present) != 1:
            violations.append(
                f"{exclusion.display_group_id}/{exclusion.member_id}: excluded record "
                f"'{path}' appears {len(present)} time(s) in the effective dataset, "
                "expected exactly 1")
            continue
        row = present[0]
        for col, want, what in (
            ("sha256", exclusion.byte_sha256, "byte digest"),
            ("split", exclusion.prior_effective_split, "split"),
            ("class_label", exclusion.prior_effective_class_label, "class label"),
        ):
            got = str(row.get(col, ""))
            if got != want:
                violations.append(
                    f"{exclusion.display_group_id}/{exclusion.member_id}: effective "
                    f"{what} for '{path}' is '{got}', the decision was taken against "
                    f"'{want}'")
        identity = effective_record_id(row)
        if identity != exclusion.prior_effective_record_id:
            violations.append(
                f"{exclusion.display_group_id}/{exclusion.member_id}: effective record "
                f"'{path}' now has identity {identity}, the decision was taken against "
                f"{exclusion.prior_effective_record_id}")
        drop.add(path)

    core = [dict(r) for r in effective_rows
            if str(r.get("relpath", "")) not in drop]
    core.sort(key=lambda r: (str(r.get("split", "")), str(r.get("class_label", "")),
                             str(r.get("relpath", ""))))
    violations.sort()
    return core, violations


def verify_core_records(
    source_rows: Sequence[dict],
    effective_rows: Sequence[dict],
    core_rows: Sequence[dict],
    exclusions: Sequence[ConservativeExclusion],
    adjudication: Adjudication,
) -> tuple[list[str], dict]:
    """Prove the Core set is the effective set minus exactly the excluded records.

    Re-derives the expected outcome from the decisions instead of trusting how
    the rows were produced. Checks

    * every excluded record is absent from Core and every other effective record
      is present, unchanged in **every** field;
    * a conservatively excluded group retains zero Core records;
    * a group that was not conservatively excluded is untouched;
    * no record outside the reviewed set changed, relative to the acquired
      source manifest — the invariant the whole exercise turns on;
    * no duplicate relpath, effective identity, or byte digest survives, so no
      exact duplicate (and therefore no cross-split exact duplicate) remains;
    * no surviving digest carries two class labels.
    """
    violations: list[str] = []
    excluded_paths = {e.active_relative_path for e in exclusions}
    excluded_groups = {e.display_group_id for e in exclusions}

    effective_by_path = {str(r.get("relpath", "")): r for r in effective_rows}
    core_by_path: dict[str, list[dict]] = {}
    for row in core_rows:
        core_by_path.setdefault(str(row.get("relpath", "")), []).append(row)

    for path, rows in sorted(core_by_path.items()):
        if len(rows) > 1:
            violations.append(f"Core dataset contains '{path}' {len(rows)} times")

    for path in sorted(excluded_paths):
        if path in core_by_path:
            violations.append(
                f"conservatively excluded record '{path}' is still in the Core dataset")

    for path, row in sorted(effective_by_path.items()):
        if path in excluded_paths:
            continue
        present = core_by_path.get(path, [])
        if len(present) != 1:
            violations.append(
                f"effective record '{path}' appears {len(present)} time(s) in the Core "
                "dataset, expected exactly 1")
            continue
        changed = sorted(k for k in set(row) | set(present[0])
                         if str(row.get(k, "")) != str(present[0].get(k, "")))
        if changed:
            violations.append(
                f"retained effective record '{path}' changed in {changed}; a "
                "conservative exclusion removes records and changes nothing else")

    for path in sorted(set(core_by_path) - set(effective_by_path)):
        violations.append(
            f"Core dataset contains '{path}', which the effective dataset does not")

    # Per-group accounting: an excluded group keeps nothing; every other group
    # keeps exactly what R2B gave it.
    retained_by_group: dict[str, list[str]] = {}
    for member in adjudication.members:
        if member.retained:
            retained_by_group.setdefault(member.display_group_id, []).append(
                member.member.active_relative_path)
    for group, paths in sorted(retained_by_group.items()):
        survivors = [p for p in paths if p in core_by_path]
        if group in excluded_groups and survivors:
            violations.append(
                f"{group} was conservatively excluded but retains {len(survivors)} "
                f"Core record(s): {sorted(survivors)}")
        if group not in excluded_groups and len(survivors) != len(paths):
            violations.append(
                f"{group} was not conservatively excluded but lost "
                f"{len(paths) - len(survivors)} Core record(s)")

    # The load-bearing invariant: records nobody reviewed are untouched, all the
    # way back to the acquired source manifest.
    reviewed = {m.member.active_relative_path for m in adjudication.members}
    non_reviewed = {str(r.get("relpath", "")): r for r in source_rows
                    if str(r.get("relpath", "")) not in reviewed}
    non_reviewed_changed = 0
    for path, source in sorted(non_reviewed.items()):
        present = core_by_path.get(path, [])
        if len(present) != 1:
            violations.append(
                f"non-reviewed record '{path}' appears {len(present)} time(s) in the "
                "Core dataset, expected exactly 1")
            non_reviewed_changed += 1
            continue
        changed = sorted(k for k in set(source) | set(present[0])
                         if str(source.get(k, "")) != str(present[0].get(k, "")))
        if changed:
            violations.append(
                f"non-reviewed record '{path}' changed in {changed}; only records "
                "covered by an explicit human decision may change")
            non_reviewed_changed += 1

    by_digest: dict[str, list[dict]] = {}
    for row in core_rows:
        by_digest.setdefault(str(row.get("sha256", "")), []).append(row)
    surviving = {d: rs for d, rs in by_digest.items() if len(rs) > 1}
    for digest, rows in sorted(surviving.items()):
        splits = sorted({str(r.get("split", "")) for r in rows})
        labels = sorted({str(r.get("class_label", "")) for r in rows})
        violations.append(
            f"byte digest {digest[:12]} still appears {len(rows)} times in the Core "
            f"dataset (splits {splits}, labels {labels})")

    cross_split = sum(1 for rs in surviving.values()
                      if len({str(r.get("split", "")) for r in rs}) > 1)
    contradictory = sum(1 for rs in surviving.values()
                        if len({str(r.get("class_label", "")) for r in rs}) > 1)

    split_counts: dict[str, int] = {}
    for row in core_rows:
        key = str(row.get("split", ""))
        split_counts[key] = split_counts.get(key, 0) + 1

    identities = identity_set(core_rows)
    report = {
        "schema": CONSERVATIVE_EXCLUSION_SCHEMA,
        "source_records": len(source_rows),
        "effective_records": len(effective_rows),
        "core_records": len(core_rows),
        "conservatively_excluded_records": len(exclusions),
        "conservatively_excluded_groups": sorted(excluded_groups),
        "reviewed_records": len(reviewed),
        "non_reviewed_records": len(non_reviewed),
        "non_reviewed_records_unchanged": non_reviewed_changed == 0,
        "retained_reviewed_records": sum(
            1 for m in adjudication.members
            if m.retained and m.member.active_relative_path not in excluded_paths),
        "excluded_reviewed_records": sum(
            1 for m in adjudication.members
            if not m.retained or m.member.active_relative_path in excluded_paths),
        "core_split_counts": dict(sorted(split_counts.items())),
        "core_class_count": len({str(r.get("class_label", "")) for r in core_rows}),
        "distinct_byte_digests": len(by_digest),
        "surviving_exact_duplicate_groups": len(surviving),
        "surviving_cross_split_duplicate_groups": cross_split,
        "surviving_contradictory_label_groups": contradictory,
        "unique_relpaths": len(core_by_path) == len(core_rows),
        "unique_effective_identities": len(set(identities)) == len(core_rows),
        "core_identity_digest": hashlib.sha256(
            json.dumps(identities, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "exclusions": [e.as_evidence() for e in exclusions],
    }
    violations.sort()
    return violations, report
