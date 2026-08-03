"""The G07/G08/G10 second-review packet (R2B.1 Finding 5).

Three canonical labels were changed on one anonymous reviewer's rationale with no
independently citable diagnostic source. The packet gives a second reviewer what
they need; it must not, anywhere, do their job for them.

These tests hold that line: the packet proposes nothing, the adjudicated
decisions are untouched, and the readiness gate keeps reporting the review as
pending until a valid human artifact exists.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys

import pytest

PACKET = "reports/plantdoc_label_second_review"
REVIEW_CSV = f"{PACKET}/plantdoc_label_second_review.csv"
MEMBERS_CSV = f"{PACKET}/plantdoc_label_second_review_members.csv"
CHECKLIST = f"{PACKET}/PLANTDOC_LABEL_SECOND_REVIEW.md"
MANIFEST = f"{PACKET}/packet_manifest.json"
RESOLUTION = "data/exclusions/plantdoc_internal_duplicate_resolution.csv"
SCRIPT = "scripts/build_plantdoc_second_review_packet.py"

#: The groups whose retained record was given a different label.
EXPECTED_GROUPS = ["G07", "G08", "G10"]

SECOND_REVIEW_FIELDS = (
    "independent_reviewer_id", "independent_reviewer_role", "independent_reviewed_at",
    "agreement", "proposed_canonical_label", "confidence",
    "diagnostic_evidence_citation", "diagnostic_evidence_url",
    "recommended_action_if_unresolved", "independent_notes",
)


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def review(repo_root):
    return _rows(repo_root / REVIEW_CSV)


@pytest.fixture(scope="module")
def members(repo_root):
    return _rows(repo_root / MEMBERS_CSV)


@pytest.fixture(scope="module")
def resolution(repo_root):
    return _rows(repo_root / RESOLUTION)


# --------------------------------------------------------------------------- #
# The right groups, derived rather than listed
# --------------------------------------------------------------------------- #
def test_the_packet_covers_exactly_the_relabelled_groups(review):
    assert [r["display_group_id"] for r in review] == EXPECTED_GROUPS


def test_group_selection_is_derived_from_the_resolution_table(repo_root, resolution):
    sys.path.insert(0, str(repo_root / "scripts"))
    from build_plantdoc_second_review_packet import relabelled_groups

    assert relabelled_groups(resolution) == EXPECTED_GROUPS


def test_a_hypothetical_new_relabel_would_be_picked_up(repo_root, resolution):
    """The selection must not be a hard-coded list that a future decision escapes."""
    sys.path.insert(0, str(repo_root / "scripts"))
    from build_plantdoc_second_review_packet import relabelled_groups

    mutated = [dict(r) for r in resolution]
    victim = next(r for r in mutated
                  if r["display_group_id"] == "G01"
                  and r["remediation_action"] == "retain_canonical")
    victim["effective_class_label"] = "Some Other Class"
    assert "G01" in relabelled_groups(mutated)


def test_every_covered_group_actually_changed_its_retained_label(review, resolution):
    by_group = {}
    for r in resolution:
        by_group.setdefault(r["display_group_id"], []).append(r)
    for row in review:
        kept = next(m for m in by_group[row["display_group_id"]]
                    if m["remediation_action"] == "retain_canonical")
        assert kept["source_class_label"] != kept["effective_class_label"]
        assert row["retained_record_source_label"] == kept["source_class_label"]
        assert row["applied_canonical_label"] == kept["effective_class_label"]


def test_the_relabel_kind_distinguishes_in_group_from_outside_group(review):
    kinds = {r["display_group_id"]: r["relabel_kind"] for r in review}
    assert kinds["G08"] == "outside_group"     # neither copy carried the label
    assert kinds["G07"] == "in_group" and kinds["G10"] == "in_group"


# --------------------------------------------------------------------------- #
# The packet decides nothing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", SECOND_REVIEW_FIELDS)
def test_every_second_review_field_is_blank(review, field):
    assert all(not (r[field] or "").strip() for r in review), field


def test_every_group_is_marked_pending(review):
    assert all(r["second_review_status"] == "pending" for r in review)


def test_the_checklist_offers_no_diagnosis(repo_root):
    text = (repo_root / CHECKLIST).read_text().lower()
    assert "makes no diagnosis" in text
    assert "______" in text                       # blank prompts
    for banned in ("we recommend", "the correct label is", "should be labelled",
                   "the correct diagnosis", "we believe", "clearly shows"):
        assert banned not in text, banned


def test_the_checklist_says_uncertain_is_an_acceptable_answer(repo_root):
    text = (repo_root / CHECKLIST).read_text().lower()
    assert "do not feel obliged to confirm" in text
    assert "uncertain" in text


def test_the_checklist_quotes_the_first_rationale_verbatim(review, repo_root):
    text = (repo_root / CHECKLIST).read_text()
    for r in review:
        assert r["first_reviewer_rationale"] in text


def test_no_citation_is_fabricated(review):
    for r in review:
        assert r["diagnostic_evidence_citation"] == ""
        assert r["diagnostic_evidence_url"] == ""


# --------------------------------------------------------------------------- #
# Evidence completeness
# --------------------------------------------------------------------------- #
def test_all_original_records_are_present_with_full_identity(members, resolution):
    covered = [m for m in resolution if m["display_group_id"] in EXPECTED_GROUPS]
    assert len(members) == len(covered) == 6
    for m in members:
        assert len(m["byte_sha256"]) == 64 and len(m["decoded_rgb_sha256"]) == 64
        assert m["active_relative_path"] and m["original_archive_path"]
        assert m["source_split"] in ("train", "test")
        assert m["source_class_label"]
        assert m["remediation_action"] in ("retain_canonical", "exclude_duplicate")


def test_the_review_rows_carry_the_first_reviewers_attribution(review):
    for r in review:
        assert r["first_reviewer_id"] and r["first_reviewed_at"]
        assert r["first_reviewer_rationale"]


def test_the_packet_manifest_digests_match(repo_root):
    import hashlib

    manifest = json.loads((repo_root / MANIFEST).read_text())
    assert manifest["status"] == "pending"
    assert manifest["groups_under_review"] == EXPECTED_GROUPS
    for name, digest in manifest["artifacts"].items():
        p = repo_root / PACKET / name
        assert p.exists(), name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, name


def test_the_packet_rebuilds_byte_identically(repo_root):
    before = {p: (repo_root / p).read_bytes()
              for p in (REVIEW_CSV, MEMBERS_CSV, CHECKLIST, MANIFEST)}
    r = subprocess.run([sys.executable, str(repo_root / SCRIPT), "--check"],
                       cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "check OK" in r.stdout
    assert {p: (repo_root / p).read_bytes()
            for p in (REVIEW_CSV, MEMBERS_CSV, CHECKLIST, MANIFEST)} == before


# --------------------------------------------------------------------------- #
# No adjudicated decision moved
# --------------------------------------------------------------------------- #
def test_the_adjudicated_decisions_are_untouched(resolution):
    """R2B's outcome, restated here so this packet cannot quietly alter it."""
    assert len(resolution) == 24
    kept = [r for r in resolution if r["remediation_action"] == "retain_canonical"]
    assert len(kept) == 10
    assert len(resolution) - len(kept) == 14
    assert len({r["display_group_id"] for r in resolution}) == 12
    assert all(r["effective_split"] == "train" for r in kept)


def test_the_effective_dataset_is_unchanged(repo_root):
    effective = _rows(repo_root / "data/manifests/plantdoc_effective_manifest.csv")
    assert len(effective) == 2564
    assert len({r["sha256"] for r in effective}) == 2564


def test_the_second_review_artifact_does_not_exist(repo_root):
    assert not (repo_root
                / "human_review/plantdoc_label_second_review/second_review.json").exists()


# --------------------------------------------------------------------------- #
# Readiness integration
# --------------------------------------------------------------------------- #
def test_readiness_reports_the_second_review_as_blocked(repo_root):
    readiness = json.loads(
        (repo_root / "reports/dataset_v1_freeze_readiness.json").read_text())
    cond = next(c for c in readiness["conditions"]
                if c["id"] == "relabel_second_scientific_review")
    assert cond["status"] == "blocked"
    assert cond["kind"] == "human_scientific"
    assert "has not been taken" in cond["detail"]
    for gid in EXPECTED_GROUPS:
        assert gid in cond["title"]
