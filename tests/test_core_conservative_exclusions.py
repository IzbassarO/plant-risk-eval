"""Conservative G07/G08/G10 exclusions for Core Dataset V1 (R2B.2 Part 1).

The operator decided to drop three records whose canonical label rests on an
independent scientific review that was never performed. Excluding a record needs
no diagnosis, which is exactly why it is the conservative option -- but it is
still a decision, and it has to be as hard to forge as the adjudication it sits
on top of.

These tests hold the decision to three standards:

* it is **authenticated** -- a row that does not reproduce the R2B outcome it
  claims to overturn, field for field, is refused;
* it is **narrow** -- exactly three records leave, the other 2,561 are
  bit-identical to what R2B produced, and no label or split anywhere changes;
* it is **honest** -- it never presents itself as a scientific second review,
  and the pending review artifacts stay pending.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

from ica26.datasets.conservative_exclusions import (
    CONSERVATIVE_EXCLUSION_DECISION,
    CONSERVATIVE_EXCLUSION_SCHEMA,
    EXCLUSION_COLUMNS,
    apply_conservative_exclusions,
    parse_conservative_exclusions,
    verify_core_records,
)

DECISION = Path("data/exclusions/core_dataset_v1_conservative_exclusions.csv")
RESOLUTION = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
SOURCE_MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
EFFECTIVE = Path("data/manifests/plantdoc_effective_manifest.csv")
CORE = Path("data/manifests/plantdoc_core_effective_manifest.csv")
SCRIPT = Path("scripts/apply_core_conservative_exclusions.py")

EXCLUDED_GROUPS = ("G07", "G08", "G10")
#: The three canonical records the operator excluded, with the identity and
#: digest each decision row must reproduce. Pinned here so a silent change to
#: the decision file fails a test rather than passing quietly.
EXCLUDED_IDENTITIES = {
    "G07": ("erec-5373969d2572bb1d",
            "9dd93b4217495fbb725cfdded86d3dc5f98955c9616fff5323be1a00df17be8b",
            "train", "Potato leaf late blight"),
    "G08": ("erec-7692837fe06b10af",
            "a981ee59e5e1dcafd0d225f74369a05969200352c17743318c31987083ab6f4c",
            "train", "Tomato leaf late blight"),
    "G10": ("erec-80b6c8a97fcda29a",
            "e23a29c94b58aac28e92f57f95eb6f53e99c874323cb2b90ebd327085721574e",
            "train", "Tomato leaf bacterial spot"),
}

EXPECTED_SOURCE = 2578
EXPECTED_EFFECTIVE = 2564
EXPECTED_CORE = 2561
EXPECTED_NON_REVIEWED = 2554
EXPECTED_SPLITS = {"train": 2336, "test": 225}


def _rows(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def decision_rows(repo_root):
    return _rows(repo_root / DECISION)


@pytest.fixture(scope="module")
def adjudication(repo_root, plantdoc_pixels):
    """The live R2B outcomes, re-derived exactly as the apply script derives them."""
    sys.path.insert(0, str(repo_root / "scripts"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_apply_core_exclusions", repo_root / SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, adj = module.load_adjudication(repo_root)
    assert not adj.violations, adj.violations
    return adj


# --------------------------------------------------------------------------- #
# The recorded decision
# --------------------------------------------------------------------------- #
def test_the_decision_covers_exactly_the_three_uncertain_groups(decision_rows):
    assert [r["display_group_id"] for r in decision_rows] == list(EXCLUDED_GROUPS)
    assert len(decision_rows) == 3


def test_every_decision_row_carries_the_operators_attribution(decision_rows):
    for row in decision_rows:
        assert row["decision_schema"] == CONSERVATIVE_EXCLUSION_SCHEMA
        assert row["exclusion_decision"] == CONSERVATIVE_EXCLUSION_DECISION
        assert row["exclusion_basis"] == "insufficient_independent_diagnostic_evidence"
        assert row["reviewer_id"] == "dataset_owner_1"
        assert row["reviewer_role"] == "dataset_owner_research_lead"
        assert row["decided_at"].endswith("+05:00")
        assert len(row["reviewed_repository_commit"]) == 40
        assert "insufficient independent diagnostic evidence" in (
            row["exclusion_rationale"].lower())


def test_every_decision_row_binds_the_exact_record_it_removes(decision_rows):
    for row in decision_rows:
        identity, digest, split, label = EXCLUDED_IDENTITIES[row["display_group_id"]]
        assert row["prior_effective_record_id"] == identity
        assert row["byte_sha256"] == digest
        assert row["prior_effective_split"] == split
        assert row["prior_effective_class_label"] == label
        assert row["prior_remediation_action"] == "retain_canonical"


def test_the_decision_records_no_diagnosis(decision_rows):
    """It may not assert what the image is -- only that it will not be used."""
    for row in decision_rows:
        assert "new_class_label" not in row
        assert "proposed_canonical_label" not in row
        # The prior label is recorded as history, never re-asserted as a finding.
        assert set(row) == set(EXCLUSION_COLUMNS)


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def test_the_committed_decision_authenticates(repo_root, decision_rows, adjudication):
    parsed, violations = parse_conservative_exclusions(decision_rows, adjudication)
    assert violations == []
    assert len(parsed) == 3


@pytest.mark.parametrize("column,bad", [
    ("byte_sha256", "0" * 64),
    ("prior_effective_record_id", "erec-0000000000000000"),
    ("prior_effective_class_label", "Tomato leaf late blight"),
    ("prior_effective_split", "test"),
    ("active_relative_path", "train/Corn leaf blight/IMG_42231.jpg"),
    ("member_id", "G07-m1"),
    ("group_id", "pdup-0000000000000000"),
    ("width", "1"),
])
def test_any_drift_in_the_bound_evidence_is_refused(
    decision_rows, adjudication, column, bad,
):
    rows = [dict(r) for r in decision_rows]
    rows[0][column] = bad
    _, violations = parse_conservative_exclusions(rows, adjudication)
    assert violations, f"drift in {column} was accepted"


def test_a_row_may_not_exclude_a_record_r2b_never_retained(
    decision_rows, adjudication,
):
    """G03 was already excluded wholesale; 'excluding' it again decides nothing."""
    rows = [dict(r) for r in decision_rows]
    rows[0]["active_relative_path"] = (
        "test/Potato leaf early blight/backus-056-potato-blight.jpg")
    _, violations = parse_conservative_exclusions(rows, adjudication)
    assert any("not a record retained by the R2B adjudication" in v
               for v in violations)


def test_a_duplicated_row_is_refused(decision_rows, adjudication):
    rows = [dict(r) for r in decision_rows] + [dict(decision_rows[0])]
    _, violations = parse_conservative_exclusions(rows, adjudication)
    assert any("duplicate exclusion" in v for v in violations)


@pytest.mark.parametrize("column,bad", [
    ("decision_schema", "ica26.datasets.conservative_exclusion/99"),
    ("decision_schema", ""),
    ("exclusion_decision", "approved"),
    ("exclusion_decision", "relabel"),
    ("exclusion_basis", "reviewer_preference"),
    ("reviewer_id", ""),
    ("reviewer_id", "TBD"),
    ("reviewer_role", "unknown"),
    ("decided_at", "2026-08-04"),           # naive
    ("decided_at", "tomorrow"),
    ("decided_at", "2099-01-01T00:00:00+00:00"),   # future
    ("reviewed_repository_commit", "abc123"),
    ("exclusion_rationale", "TBD"),
    ("exclusion_rationale", "too short"),
])
def test_a_malformed_or_placeholder_decision_is_refused(
    decision_rows, adjudication, column, bad,
):
    rows = [dict(r) for r in decision_rows]
    rows[0][column] = bad
    _, violations = parse_conservative_exclusions(rows, adjudication)
    assert violations, f"{column}={bad!r} was accepted"


def test_a_rationale_hiding_a_placeholder_inside_prose_is_refused(
    decision_rows, adjudication,
):
    rows = [dict(r) for r in decision_rows]
    rows[0]["exclusion_rationale"] = (
        "Excluded because the supporting diagnostic source is TBD and will be "
        "supplied once somebody gets around to looking at it properly.")
    _, violations = parse_conservative_exclusions(rows, adjudication)
    assert any("placeholder" in v for v in violations)


def test_a_stale_artifact_binding_is_refused(decision_rows, adjudication):
    rows = [dict(r) for r in decision_rows]
    _, violations = parse_conservative_exclusions(
        rows, adjudication,
        artifact_digests={
            "bound_resolution_sha256": "f" * 64,
            "bound_effective_manifest_sha256": "f" * 64,
            "bound_second_review_packet_sha256": "f" * 64,
        })
    assert any("stale binding" in v for v in violations)


# --------------------------------------------------------------------------- #
# The materialised Core dataset
# --------------------------------------------------------------------------- #
def test_core_has_exactly_2561_records(repo_root):
    assert len(_rows(repo_root / CORE)) == EXPECTED_CORE


def test_the_layering_is_visible_in_the_artifacts(repo_root):
    assert len(_rows(repo_root / SOURCE_MANIFEST)) == EXPECTED_SOURCE
    assert len(_rows(repo_root / EFFECTIVE)) == EXPECTED_EFFECTIVE
    assert len(_rows(repo_root / CORE)) == EXPECTED_CORE


def test_core_splits_are_exactly_as_expected(repo_root):
    counts: dict[str, int] = {}
    for row in _rows(repo_root / CORE):
        counts[row["split"]] = counts.get(row["split"], 0) + 1
    assert counts == EXPECTED_SPLITS
    assert sum(counts.values()) == EXPECTED_CORE


def test_core_retains_all_28_classes(repo_root):
    labels = {r["class_label"] for r in _rows(repo_root / CORE)}
    assert len(labels) == 28


def test_the_excluded_records_are_gone_and_nothing_else_moved(repo_root, adjudication):
    effective = _rows(repo_root / EFFECTIVE)
    core = _rows(repo_root / CORE)
    core_by_path = {r["relpath"]: r for r in core}

    excluded_paths = {
        m.member.active_relative_path for m in adjudication.members
        if m.retained and m.display_group_id in EXCLUDED_GROUPS
    }
    assert len(excluded_paths) == 3
    for path in excluded_paths:
        assert path not in core_by_path

    # Every other effective record survives byte-for-byte, in every field.
    for row in effective:
        if row["relpath"] in excluded_paths:
            continue
        assert core_by_path[row["relpath"]] == row


def test_all_2554_non_reviewed_records_are_untouched(repo_root, adjudication):
    """The invariant the whole exercise turns on."""
    reviewed = {m.member.active_relative_path for m in adjudication.members}
    source = {r["relpath"]: r for r in _rows(repo_root / SOURCE_MANIFEST)}
    core = {r["relpath"]: r for r in _rows(repo_root / CORE)}

    non_reviewed = {p: r for p, r in source.items() if p not in reviewed}
    assert len(non_reviewed) == EXPECTED_NON_REVIEWED
    for path, row in non_reviewed.items():
        assert core[path] == row, f"non-reviewed record {path} changed"


def test_the_seven_surviving_reviewed_records_keep_their_r2b_decision(
    repo_root, adjudication,
):
    core = {r["relpath"]: r for r in _rows(repo_root / CORE)}
    survivors = [m for m in adjudication.members
                 if m.retained and m.display_group_id not in EXCLUDED_GROUPS]
    assert len(survivors) == 7
    for member in survivors:
        row = core[member.member.active_relative_path]
        assert row["split"] == member.effective_split
        assert row["class_label"] == member.effective_class_label


def test_the_fully_excluded_groups_stay_fully_excluded(repo_root, adjudication):
    core_paths = {r["relpath"] for r in _rows(repo_root / CORE)}
    for group in ("G03", "G11"):
        paths = [m.member.active_relative_path for m in adjudication.members
                 if m.display_group_id == group]
        assert paths
        assert not (set(paths) & core_paths)


def test_no_exact_duplicate_of_any_kind_survives_in_core(repo_root):
    rows = _rows(repo_root / CORE)
    by_digest: dict[str, list[dict]] = {}
    for row in rows:
        by_digest.setdefault(row["sha256"], []).append(row)
    survivors = {d: rs for d, rs in by_digest.items() if len(rs) > 1}
    assert survivors == {}
    assert len({r["relpath"] for r in rows}) == len(rows)


def test_the_verification_report_reconciles_every_expected_count(
    repo_root, decision_rows, adjudication,
):
    parsed, _ = parse_conservative_exclusions(decision_rows, adjudication)
    source = _rows(repo_root / SOURCE_MANIFEST)
    effective = _rows(repo_root / EFFECTIVE)
    core, apply_violations = apply_conservative_exclusions(effective, parsed)
    assert apply_violations == []

    violations, report = verify_core_records(
        source, effective, core, parsed, adjudication)
    assert violations == []
    assert report["source_records"] == EXPECTED_SOURCE
    assert report["effective_records"] == EXPECTED_EFFECTIVE
    assert report["core_records"] == EXPECTED_CORE
    assert report["conservatively_excluded_records"] == 3
    assert report["conservatively_excluded_groups"] == list(EXCLUDED_GROUPS)
    assert report["retained_reviewed_records"] == 7
    assert report["excluded_reviewed_records"] == 17
    assert report["non_reviewed_records"] == EXPECTED_NON_REVIEWED
    assert report["non_reviewed_records_unchanged"] is True
    assert report["core_split_counts"] == EXPECTED_SPLITS
    assert report["core_class_count"] == 28
    assert report["surviving_exact_duplicate_groups"] == 0
    assert report["surviving_cross_split_duplicate_groups"] == 0
    assert report["surviving_contradictory_label_groups"] == 0
    assert report["unique_relpaths"] is True
    assert report["unique_effective_identities"] is True


# --------------------------------------------------------------------------- #
# Determinism and idempotence
# --------------------------------------------------------------------------- #
def test_reapplying_the_decision_is_a_no_op(repo_root, decision_rows, adjudication):
    parsed, _ = parse_conservative_exclusions(decision_rows, adjudication)
    effective = _rows(repo_root / EFFECTIVE)
    once, _ = apply_conservative_exclusions(effective, parsed)
    twice, _ = apply_conservative_exclusions(list(once), parsed)
    # Re-running against the already-reduced set removes nothing further; the
    # records are simply reported absent rather than silently re-excluded.
    assert twice == once


def test_the_core_manifest_matches_a_fresh_rebuild(repo_root, plantdoc_pixels):
    r = subprocess.run(
        [sys.executable, str(repo_root / SCRIPT), "--check"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "check OK" in r.stdout


def test_the_recorded_decision_is_immutable(repo_root):
    """A second --record must refuse rather than silently rewrite history."""
    r = subprocess.run(
        [sys.executable, str(repo_root / SCRIPT), "--record",
         "--rationale", "x" * 60, "--reviewer-id", "someone",
         "--reviewer-role", "role", "--decided-at", "2026-08-04T12:00:00+05:00"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 1
    assert "immutable" in r.stdout


# --------------------------------------------------------------------------- #
# The exclusion is NOT a scientific review
# --------------------------------------------------------------------------- #
def test_the_r2b_adjudication_is_untouched(repo_root):
    """Excluding a record must not rewrite the decision that created it."""
    rows = _rows(repo_root / RESOLUTION)
    assert len(rows) == 24
    for row in rows:
        if row["display_group_id"] in EXCLUDED_GROUPS and row["member_id"].endswith("m2"):
            # The historical record still says what R2B decided, unedited.
            assert row["remediation_action"] == "retain_canonical"
            assert row["group_handling_decision"] == "keep_one_record"


def test_no_second_review_artifact_was_fabricated(repo_root):
    assert not (repo_root
                / "human_review/plantdoc_label_second_review/second_review.json").exists()


def test_the_second_review_packet_still_reports_the_groups_as_pending(repo_root):
    import json

    manifest = json.loads(
        (repo_root
         / "reports/plantdoc_label_second_review/packet_manifest.json").read_text())
    assert manifest["status"] == "pending"
    assert manifest["groups_under_review"] == list(EXCLUDED_GROUPS)
