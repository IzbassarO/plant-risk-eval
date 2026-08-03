"""Strict, packet-bound validation for the PlantDoc relabel second review.

The second review is not a generic vote over a list of group names.  It is a
set of three independently attributable scientific review records, one for
each canonical relabel currently in force.  Every record is reconciled to the
deterministic pending packet before it can contribute to freeze readiness.

This module only validates human-authored records.  It never creates a review
or supplies a diagnosis, citation, confidence, or recommendation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .mapping import PLACEHOLDER_TOKENS


SECOND_REVIEW_SCHEMA = "ica26.governance.plantdoc_label_second_review/2"
SECOND_REVIEW_PACKET_SCHEMA = (
    "ica26.governance.plantdoc_label_second_review_packet/1"
)
EXPECTED_SECOND_REVIEW_GROUPS = ("G07", "G08", "G10")

RESOLUTION_PATH = "data/exclusions/plantdoc_internal_duplicate_resolution.csv"
PACKET_REVIEW_PATH = (
    "reports/plantdoc_label_second_review/plantdoc_label_second_review.csv"
)
PACKET_MEMBERS_PATH = (
    "reports/plantdoc_label_second_review/plantdoc_label_second_review_members.csv"
)
PACKET_CHECKLIST_PATH = (
    "reports/plantdoc_label_second_review/PLANTDOC_LABEL_SECOND_REVIEW.md"
)
PACKET_MANIFEST_PATH = "reports/plantdoc_label_second_review/packet_manifest.json"
COMPLETED_REVIEW_PATH = (
    "human_review/plantdoc_label_second_review/second_review.json"
)

SECOND_REVIEW_REQUIRED_BINDINGS = (
    RESOLUTION_PATH,
    PACKET_REVIEW_PATH,
    PACKET_MEMBERS_PATH,
    PACKET_CHECKLIST_PATH,
    PACKET_MANIFEST_PATH,
)

GROUP_REQUIRED_FIELDS = frozenset({
    "group_id",
    "reviewed_member_identities",
    "reviewed_member_sha256",
    "current_canonical_identity",
    "current_canonical_label",
    "decision",
    "confidence",
    "reviewer_id",
    "reviewer_role_or_qualification",
    "reviewed_at",
    "diagnostic_rationale",
    "diagnostic_citations",
    "recommended_action",
    "bound_packet_digest",
})
GROUP_OPTIONAL_FIELDS = frozenset({"proposed_canonical_label"})

DECISIONS = frozenset({"agree", "disagree", "uncertain"})
CONFIDENCE_LEVELS = frozenset({"low", "moderate", "high"})
AGREE_ACTIONS = frozenset({"accept_current_label"})
DISAGREE_ACTIONS = frozenset({"replace_current_label", "exclude_record", "escalate"})
UNCERTAIN_ACTIONS = frozenset({"exclude_record", "retain_with_flag", "escalate"})
MIN_GROUP_RATIONALE_CHARS = 40
MIN_CITATION_CHARS = 12
SECOND_REVIEW_PLACEHOLDERS = PLACEHOLDER_TOKENS | frozenset({"unstructured"})
LEGACY_GENERIC_FIELDS = frozenset({"group_verdicts", "diagnostic_citations"})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_csv(path: Path, *, name: str, errors: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        errors.append(f"second-review {name} is absent at {path}")
        return []
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                errors.append(f"second-review {name} has no CSV header")
                return []
            return list(reader)
    except Exception as exc:  # noqa: BLE001 - refusal must include malformed inputs
        errors.append(
            f"second-review {name} is unreadable: {type(exc).__name__}: {exc}"
        )
        return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_review_placeholder(value: Any) -> bool:
    text = _text(value)
    return not text or text.casefold() in SECOND_REVIEW_PLACEHOLDERS


def _is_sha256(value: Any) -> bool:
    text = _text(value).lower()
    return len(text) == 64 and all(ch in "0123456789abcdef" for ch in text)


def _exact_group_ids(
    values: list[str], *, source: str, errors: list[str]
) -> bool:
    counts = Counter(values)
    duplicates = sorted(group for group, count in counts.items() if count > 1)
    missing = sorted(set(EXPECTED_SECOND_REVIEW_GROUPS) - set(values))
    extra = sorted(set(values) - set(EXPECTED_SECOND_REVIEW_GROUPS))
    if duplicates:
        errors.append(
            f"{source} contains duplicate group entries {duplicates}; each group must "
            "appear exactly once"
        )
    if missing:
        errors.append(f"{source} is missing required group(s) {missing}")
    if extra:
        errors.append(f"{source} contains unexpected group(s) {extra}")
    return not (duplicates or missing or extra)


def _manifest_and_digest(repo: Path, errors: list[str]) -> tuple[dict, str]:
    manifest_path = repo / PACKET_MANIFEST_PATH
    if not manifest_path.is_file():
        errors.append(
            f"second-review packet manifest is absent at {PACKET_MANIFEST_PATH}"
        )
        return {}, ""
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(
            "second-review packet manifest is unreadable JSON: "
            f"{type(exc).__name__}: {exc}"
        )
        return {}, ""
    if not isinstance(payload, dict):
        errors.append("second-review packet manifest must be a JSON object")
        return {}, _sha256(manifest_path)

    if payload.get("schema_version") != SECOND_REVIEW_PACKET_SCHEMA:
        errors.append(
            f"second-review packet manifest schema_version must be "
            f"'{SECOND_REVIEW_PACKET_SCHEMA}'"
        )
    if payload.get("dataset") != "PlantDoc":
        errors.append("second-review packet manifest dataset must be 'PlantDoc'")
    if payload.get("status") != "pending":
        errors.append(
            "second-review packet manifest status must remain 'pending'; the packet "
            "cannot record a human decision"
        )
    if payload.get("completed_artifact_expected_at") != COMPLETED_REVIEW_PATH:
        errors.append(
            "second-review packet manifest names the wrong completed artifact path"
        )

    groups = payload.get("groups_under_review")
    if not isinstance(groups, list) or not all(isinstance(v, str) for v in groups):
        errors.append(
            "second-review packet manifest groups_under_review must be a string list"
        )
    else:
        _exact_group_ids(groups, source="second-review packet manifest", errors=errors)

    expected_artifacts = {
        Path(PACKET_REVIEW_PATH).name: PACKET_REVIEW_PATH,
        Path(PACKET_MEMBERS_PATH).name: PACKET_MEMBERS_PATH,
        Path(PACKET_CHECKLIST_PATH).name: PACKET_CHECKLIST_PATH,
    }
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append(
            "second-review packet manifest artifacts must be a {name: sha256} object"
        )
    else:
        actual_names = {name for name in artifacts if isinstance(name, str)}
        missing = sorted(set(expected_artifacts) - actual_names)
        extra = sorted(actual_names - set(expected_artifacts))
        if missing or extra:
            errors.append(
                "second-review packet manifest must bind exactly the packet artifacts; "
                f"missing={missing}, unexpected={extra}"
            )
        for name, relative in expected_artifacts.items():
            declared = artifacts.get(name)
            artifact_path = repo / relative
            if not _is_sha256(declared):
                errors.append(
                    f"second-review packet manifest digest for '{name}' is not SHA-256"
                )
                continue
            if not artifact_path.is_file():
                errors.append(f"second-review packet artifact is absent at {relative}")
                continue
            observed = _sha256(artifact_path)
            if _text(declared).lower() != observed:
                errors.append(
                    f"second-review packet artifact '{name}' is stale: manifest "
                    f"{_text(declared)[:12]}..., current {observed[:12]}..."
                )

    return payload, _sha256(manifest_path)


def _resolution_expectations(repo: Path, errors: list[str]) -> dict[str, dict]:
    rows = _read_csv(repo / RESOLUTION_PATH, name="resolution table", errors=errors)
    by_group: dict[str, list[dict[str, str]]] = {}
    for line, row in enumerate(rows, start=2):
        group = _text(row.get("display_group_id"))
        if not group:
            errors.append(f"second-review resolution row {line} has no display_group_id")
            continue
        by_group.setdefault(group, []).append(row)

    derived: list[str] = []
    expected: dict[str, dict] = {}
    for group, members in sorted(by_group.items()):
        kept = [r for r in members if _text(r.get("remediation_action")) == "retain_canonical"]
        if len(kept) != 1:
            if group in EXPECTED_SECOND_REVIEW_GROUPS:
                errors.append(
                    f"resolution group {group} has {len(kept)} retained canonical rows; "
                    "exactly one is required"
                )
            continue
        retained = kept[0]
        source_label = _text(retained.get("source_class_label"))
        canonical_label = _text(retained.get("effective_class_label"))
        if source_label != canonical_label:
            derived.append(group)
        if group not in EXPECTED_SECOND_REVIEW_GROUPS:
            continue

        canonical_identity = _text(retained.get("effective_record_id"))
        first_reviewer_id = _text(retained.get("reviewer"))
        if _is_review_placeholder(canonical_identity):
            errors.append(
                f"resolution group {group} has no usable effective_record_id"
            )
        if _is_review_placeholder(canonical_label):
            errors.append(
                f"resolution group {group} has no usable effective_class_label"
            )
        if _is_review_placeholder(first_reviewer_id):
            errors.append(f"resolution group {group} has no first-reviewer identity")

        member_ids: list[str] = []
        member_hashes: list[str] = []
        for member in sorted(members, key=lambda row: _text(row.get("member_id"))):
            member_id = _text(member.get("member_id"))
            member_hash = _text(member.get("byte_sha256")).lower()
            if _is_review_placeholder(member_id):
                errors.append(f"resolution group {group} contains a blank member_id")
            if not _is_sha256(member_hash):
                errors.append(
                    f"resolution group {group} member '{member_id}' has invalid byte_sha256"
                )
            member_ids.append(member_id)
            member_hashes.append(member_hash)
        if len(set(member_ids)) != len(member_ids):
            errors.append(f"resolution group {group} contains duplicate member identities")
        expected[group] = {
            "member_ids": member_ids,
            "member_hashes": member_hashes,
            "canonical_identity": canonical_identity,
            "canonical_label": canonical_label,
            "first_reviewer_id": first_reviewer_id,
        }

    _exact_group_ids(derived, source="current duplicate-resolution table", errors=errors)
    return expected


def _reconcile_packet(
    repo: Path, expected: dict[str, dict], errors: list[str]
) -> int:
    review_rows = _read_csv(
        repo / PACKET_REVIEW_PATH, name="group packet CSV", errors=errors
    )
    review_ids = [_text(row.get("display_group_id")) for row in review_rows]
    if _exact_group_ids(review_ids, source="second-review group packet", errors=errors):
        for row in review_rows:
            group = _text(row.get("display_group_id"))
            authoritative = expected.get(group)
            if not authoritative:
                continue
            checks = {
                "applied_effective_record_id": authoritative["canonical_identity"],
                "applied_canonical_label": authoritative["canonical_label"],
                "second_review_status": "pending",
            }
            for field, wanted in checks.items():
                got = _text(row.get(field))
                if got != wanted:
                    errors.append(
                        f"second-review group packet {group}.{field} is '{got}', "
                        f"current resolution value is '{wanted}'"
                    )

    member_rows = _read_csv(
        repo / PACKET_MEMBERS_PATH, name="member packet CSV", errors=errors
    )
    member_group_ids = [_text(row.get("display_group_id")) for row in member_rows]
    packet_group_set = set(member_group_ids)
    missing_groups = sorted(set(EXPECTED_SECOND_REVIEW_GROUPS) - packet_group_set)
    extra_groups = sorted(packet_group_set - set(EXPECTED_SECOND_REVIEW_GROUPS))
    if missing_groups or extra_groups:
        errors.append(
            "second-review member packet has wrong group coverage: "
            f"missing={missing_groups}, unexpected={extra_groups}"
        )
    for group in EXPECTED_SECOND_REVIEW_GROUPS:
        authoritative = expected.get(group)
        if not authoritative:
            continue
        rows = sorted(
            (row for row in member_rows if _text(row.get("display_group_id")) == group),
            key=lambda row: _text(row.get("member_id")),
        )
        ids = [_text(row.get("member_id")) for row in rows]
        hashes = [_text(row.get("byte_sha256")).lower() for row in rows]
        if ids != authoritative["member_ids"]:
            errors.append(
                f"second-review member packet {group} identities {ids} do not match "
                f"current resolution identities {authoritative['member_ids']}"
            )
        if hashes != authoritative["member_hashes"]:
            errors.append(
                f"second-review member packet {group} SHA-256 values do not match the "
                "current resolution table"
            )
    return len(member_rows)


def _reviewed_commit_timestamp(payload: dict, repo: Path) -> datetime | None:
    commit = _text(payload.get("reviewed_repository_commit"))
    if len(commit) != 40:
        return None
    result = subprocess.run(
        ["git", "-C", str(repo), "show", "-s", "--format=%cI", commit],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return None
    try:
        return datetime.fromisoformat(result.stdout.strip())
    except ValueError:
        return None


def _validate_citations(
    group: str, citations: Any, *, required: bool, errors: list[str]
) -> None:
    where = f"groups[{group}].diagnostic_citations"
    if not isinstance(citations, list):
        errors.append(f"{where} must be a list of structured citation objects")
        return
    if required and not citations:
        errors.append(f"{where} must contain citation evidence for this decision")
        return
    for index, citation in enumerate(citations):
        item = f"{where}[{index}]"
        if not isinstance(citation, dict):
            errors.append(f"{item} must be an object with exactly citation and url")
            continue
        keys = set(citation)
        if keys != {"citation", "url"}:
            errors.append(
                f"{item} must contain exactly ['citation', 'url']; got {sorted(keys)}"
            )
        citation_text = _text(citation.get("citation"))
        if _is_review_placeholder(citation_text) or len(citation_text) < MIN_CITATION_CHARS:
            errors.append(
                f"{item}.citation is blank, a placeholder, or too short to identify a source"
            )
        url = _text(citation.get("url"))
        parsed = urlparse(url)
        if (_is_review_placeholder(url) or parsed.scheme not in {"http", "https"}
                or not parsed.netloc):
            errors.append(
                f"{item}.url must be a non-placeholder http(s) source locator"
            )


def validate_second_review_payload(payload: dict, *, repo: str | Path) -> list[str]:
    """Return every strict second-review violation in deterministic order."""
    from ..leakage.gate import parse_review_timestamp

    errors: list[str] = []
    legacy = sorted(LEGACY_GENERIC_FIELDS & set(payload))
    if legacy:
        errors.append(
            "legacy generic second-review field(s) are forbidden because they can "
            f"contradict the self-contained group records: {legacy}"
        )
    root = Path(repo)
    if payload.get("review_schema_version") != SECOND_REVIEW_SCHEMA:
        errors.append(
            f"review_schema_version '{payload.get('review_schema_version')}' != "
            f"'{SECOND_REVIEW_SCHEMA}'"
        )

    manifest, packet_digest = _manifest_and_digest(root, errors)
    expected = _resolution_expectations(root, errors)
    packet_record_count = _reconcile_packet(root, expected, errors)
    if manifest and manifest.get("records") != packet_record_count:
        errors.append(
            "second-review packet manifest record count does not match the member packet: "
            f"declared={manifest.get('records')}, current={packet_record_count}"
        )

    groups = payload.get("groups")
    if not isinstance(groups, list):
        errors.append(
            "'groups' must be a list of exactly three self-contained per-group reviews"
        )
        return errors

    group_ids = [
        _text(entry.get("group_id")) if isinstance(entry, dict) else ""
        for entry in groups
    ]
    _exact_group_ids(group_ids, source="second-review artifact", errors=errors)
    reviewed_commit_dt = _reviewed_commit_timestamp(payload, root)
    decisions: dict[str, str] = {}

    for index, entry in enumerate(groups):
        if not isinstance(entry, dict):
            errors.append(f"groups[{index}] must be an object")
            continue
        group = _text(entry.get("group_id")) or f"index-{index}"
        where = f"groups[{group}]"
        missing = sorted(GROUP_REQUIRED_FIELDS - set(entry))
        unexpected = sorted(set(entry) - GROUP_REQUIRED_FIELDS - GROUP_OPTIONAL_FIELDS)
        if missing:
            errors.append(f"{where} is missing required field(s) {missing}")
        if unexpected:
            errors.append(f"{where} contains unexpected field(s) {unexpected}")
        authoritative = expected.get(group)

        identities = entry.get("reviewed_member_identities")
        if not isinstance(identities, list) or not all(
            isinstance(value, str) for value in identities
        ):
            errors.append(f"{where}.reviewed_member_identities must be a string list")
        elif len(set(identities)) != len(identities):
            errors.append(f"{where}.reviewed_member_identities contains duplicates")
        elif authoritative and identities != authoritative["member_ids"]:
            errors.append(
                f"{where}.reviewed_member_identities {identities} do not match packet "
                f"identities {authoritative['member_ids']} in canonical order"
            )

        hashes = entry.get("reviewed_member_sha256")
        if not isinstance(hashes, list) or not all(_is_sha256(value) for value in hashes):
            errors.append(f"{where}.reviewed_member_sha256 must be a SHA-256 list")
        elif authoritative and [_text(v).lower() for v in hashes] != authoritative["member_hashes"]:
            errors.append(
                f"{where}.reviewed_member_sha256 does not match packet member bytes "
                "position-for-position"
            )
        if isinstance(identities, list) and isinstance(hashes, list) and len(identities) != len(hashes):
            errors.append(
                f"{where} member identity and SHA-256 lists have different lengths"
            )

        if authoritative:
            for field, wanted in (
                ("current_canonical_identity", authoritative["canonical_identity"]),
                ("current_canonical_label", authoritative["canonical_label"]),
            ):
                got = _text(entry.get(field))
                if got != wanted:
                    errors.append(
                        f"{where}.{field} is '{got}', packet value is '{wanted}'"
                    )

        decision = entry.get("decision")
        if decision not in DECISIONS:
            errors.append(
                f"{where}.decision '{decision}' is invalid; allowed={sorted(DECISIONS)}"
            )
            decision = ""
        decisions[group] = str(decision)

        confidence = entry.get("confidence")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(
                f"{where}.confidence '{confidence}' is invalid; "
                f"allowed={sorted(CONFIDENCE_LEVELS)}"
            )

        reviewer_id = _text(entry.get("reviewer_id"))
        reviewer_role = _text(entry.get("reviewer_role_or_qualification"))
        if _is_review_placeholder(reviewer_id):
            errors.append(f"{where}.reviewer_id is blank or a placeholder")
        if _is_review_placeholder(reviewer_role):
            errors.append(
                f"{where}.reviewer_role_or_qualification is blank or a placeholder"
            )
        if authoritative and reviewer_id == authoritative["first_reviewer_id"]:
            errors.append(
                f"{where}.reviewer_id is the first reviewer; the second review must "
                "be independent"
            )

        reviewed_at = _text(entry.get("reviewed_at"))
        reviewed_dt, timestamp_error = parse_review_timestamp(reviewed_at)
        if timestamp_error:
            errors.append(f"{where}.{timestamp_error}")
        elif reviewed_commit_dt is not None and reviewed_dt is not None and reviewed_dt < reviewed_commit_dt:
            errors.append(
                f"{where}.reviewed_at predates the repository state under review"
            )

        rationale = _text(entry.get("diagnostic_rationale"))
        if (_is_review_placeholder(rationale)
                or len(rationale) < MIN_GROUP_RATIONALE_CHARS):
            errors.append(
                f"{where}.diagnostic_rationale must be non-placeholder and at least "
                f"{MIN_GROUP_RATIONALE_CHARS} characters"
            )

        _validate_citations(
            group,
            entry.get("diagnostic_citations"),
            required=decision in {"agree", "disagree"},
            errors=errors,
        )

        action = entry.get("recommended_action")
        allowed_actions = {
            "agree": AGREE_ACTIONS,
            "disagree": DISAGREE_ACTIONS,
            "uncertain": UNCERTAIN_ACTIONS,
        }.get(str(decision), frozenset())
        if action not in allowed_actions:
            errors.append(
                f"{where}.recommended_action '{action}' is invalid for decision "
                f"'{decision}'; allowed={sorted(allowed_actions)}"
            )
        if decision == "disagree":
            proposed = _text(entry.get("proposed_canonical_label"))
            current = _text(entry.get("current_canonical_label"))
            if _is_review_placeholder(proposed):
                errors.append(
                    f"{where}.proposed_canonical_label is required for disagreement"
                )
            elif proposed == current:
                errors.append(
                    f"{where}.proposed_canonical_label cannot repeat the label being rejected"
                )
        elif "proposed_canonical_label" in entry and not _is_review_placeholder(
            entry.get("proposed_canonical_label")
        ):
            errors.append(
                f"{where}.proposed_canonical_label is only valid for disagreement"
            )

        bound_digest = _text(entry.get("bound_packet_digest")).lower()
        if not _is_sha256(bound_digest):
            errors.append(f"{where}.bound_packet_digest is not SHA-256")
        elif packet_digest and bound_digest != packet_digest:
            errors.append(
                f"{where}.bound_packet_digest is stale: bound {bound_digest[:12]}..., "
                f"current {packet_digest[:12]}..."
            )

    non_agree = sorted(group for group, decision in decisions.items() if decision != "agree")
    if _text(payload.get("decision")) == "approved" and non_agree:
        errors.append(
            "second-review decision 'approved' requires three independently valid "
            f"agree decisions; non-agree group(s)={non_agree}"
        )
    return errors
