"""PlantDoc byte-exact duplicate groups, review packet, and internal gate.

R1-CRIT-002: the restored PlantDoc V1 contains groups of records whose FILE BYTES
are identical. Most straddle train/test, and most give identical pixels two
different diagnosis labels. These tests pin the enumeration, prove the packet is
decision-neutral and deterministic, and prove the gate cannot report `pass` while
a single group is unadjudicated.

Nothing here decides anything, and nothing here may fill a decision field.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys

import pytest

from ica26.datasets.duplicates import (
    DUPLICATE_GROUP_SCHEMA,
    GROUP_HANDLING_DECISIONS,
    DuplicateGroup,
    DuplicateMember,
    aggregate,
    build_internal_duplicate_gate,
    find_duplicate_groups,
)

PACKET = "reports/plantdoc_exact_duplicate_review"
GROUPS_CSV = f"{PACKET}/plantdoc_exact_duplicate_groups.csv"
MEMBERS_CSV = f"{PACKET}/plantdoc_exact_duplicate_members.csv"
GATE_JSON = "reports/plantdoc_internal_duplicate_gate.json"

#: Decision columns the packet MUST leave blank.
DECISION_COLUMNS = ("group_handling_decision", "canonical_label_decision",
                    "split_handling_decision", "decision_reason", "reviewer",
                    "reviewed_at")


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def groups(repo_root):
    return _rows(repo_root / GROUPS_CSV)


@pytest.fixture(scope="module")
def members(repo_root):
    return _rows(repo_root / MEMBERS_CSV)


@pytest.fixture(scope="module")
def gate(repo_root):
    return json.loads((repo_root / GATE_JSON).read_text())


# --------------------------------------------------------------------------- #
# Enumeration derived from current data (not hard-coded expectations)
# --------------------------------------------------------------------------- #
def test_enumeration_matches_the_manifest(repo_root):
    """Re-derive groups from the manifest; the packet must agree."""
    manifest = _rows(repo_root / "data/manifests/plantdoc_manifest.csv")
    by_sha = {}
    for r in manifest:
        by_sha.setdefault(r["sha256"], []).append(r)
    dup = {k: v for k, v in by_sha.items() if len(v) > 1}
    assert len(dup) == 12
    assert sum(len(v) for v in dup.values()) == 24
    packet = _rows(repo_root / GROUPS_CSV)
    assert {r["byte_sha256"] for r in packet} == set(dup)


def test_group_and_member_counts(groups, members):
    assert len(groups) == 12
    assert len(members) == 24
    assert all(int(g["member_count"]) == 2 for g in groups)


def test_aggregate_flags(groups):
    assert sum(g["crosses_split"] == "true" for g in groups) == 11
    assert sum(g["crosses_class"] == "true" for g in groups) == 9
    assert sum(g["crosses_split"] == "false" for g in groups) == 1


def test_every_group_is_byte_and_pixel_identical(members):
    by_group = {}
    for m in members:
        by_group.setdefault(m["group_id"], []).append(m)
    assert len(by_group) == 12
    for gid, ms in by_group.items():
        assert len({m["byte_sha256"] for m in ms}) == 1, f"{gid}: bytes differ"
        decoded = {m["decoded_rgb_sha256"] for m in ms}
        assert "" not in decoded, f"{gid}: an image failed to decode"
        assert len(decoded) == 1, f"{gid}: decoded pixels differ"


def test_group_ids_are_content_derived_and_stable(groups):
    for g in groups:
        assert g["canonical_content_id"].startswith("pdup-")
        assert g["group_id"] == g["canonical_content_id"]
    assert len({g["canonical_content_id"] for g in groups}) == 12
    assert sorted(g["display_group_id"] for g in groups) == [f"G{i:02d}" for i in range(1, 13)]


def test_members_carry_full_provenance(members, repo_root):
    manifest = {r["relpath"]: r for r in
                _rows(repo_root / "data/manifests/plantdoc_manifest.csv")}
    for m in members:
        assert m["dataset"] == "PlantDoc"
        assert m["original_archive_path"]
        assert m["active_relative_path"] in manifest
        assert m["split"] in ("train", "test")
        assert m["class_label"]
        assert len(m["byte_sha256"]) == 64
        assert m["source_revision"] == "5467f6012d78d1c446145d5f582da6096f852ae8"
        row = manifest[m["active_relative_path"]]
        assert m["byte_sha256"] == row["sha256"]
        assert m["class_label"] == row["class_label"]
        assert m["split"] == row["split"]


# --------------------------------------------------------------------------- #
# Decision neutrality
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("column", DECISION_COLUMNS)
def test_every_decision_field_is_blank(groups, column):
    assert all(not (g[column] or "").strip() for g in groups), column


def test_no_group_is_marked_resolved(groups):
    assert all(g["current_status"] == "unresolved" for g in groups)


def test_markdown_offers_no_recommendation(repo_root):
    text = (repo_root / PACKET / "PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md").read_text()
    assert "makes no decision" in text
    assert "______" in text                      # blank decision prompts
    for banned in ("we recommend", "should be excluded", "the correct label is"):
        assert banned not in text.lower()


def test_packet_manifest_hashes_are_correct(repo_root):
    import hashlib

    manifest = json.loads((repo_root / PACKET / "packet_manifest.json").read_text())
    assert manifest["group_schema"] == DUPLICATE_GROUP_SCHEMA
    assert manifest["aggregate"]["groups"] == 12
    for name, digest in manifest["artifacts"].items():
        p = repo_root / PACKET / name
        assert p.exists(), name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, name


def test_packet_generation_is_deterministic(repo_root, tmp_path):
    """Re-render the text artifacts; they must reproduce byte-for-byte."""
    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts/build_plantdoc_duplicate_packet.py"),
         "--check"], cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "check OK" in r.stdout


def test_no_source_record_was_changed(repo_root):
    """The packet is read-only with respect to the dataset."""
    manifest = _rows(repo_root / "data/manifests/plantdoc_manifest.csv")
    assert len(manifest) == 2578
    assert len({r["sha256"] for r in manifest}) == 2566


# --------------------------------------------------------------------------- #
# Internal duplicate gate
# --------------------------------------------------------------------------- #
def test_shipped_gate_is_incomplete(gate):
    assert gate["status"] == "incomplete"
    assert gate["total_groups"] == 12
    assert gate["total_records"] == 24
    assert gate["resolved_groups"] == 0
    assert gate["unresolved_groups"] == 12
    assert gate["violations"] == []
    assert len(gate["unresolved_group_ids"]) == 12


def test_gate_binds_its_inputs(gate):
    for name in ("plantdoc_manifest", "duplicate_groups", "duplicate_members",
                 "group_schema"):
        assert name in gate["input_digests"]
        assert gate["input_digests"][name] != "<absent>"


def test_gate_has_no_wall_clock_field(gate):
    assert "generated_at" not in gate


def test_gate_rebuild_is_byte_identical(repo_root):
    r = subprocess.run(
        [sys.executable,
         str(repo_root / "scripts/build_plantdoc_internal_duplicate_gate.py"), "--check"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert "check OK" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 1        # OK but still incomplete -> non-zero


# --------------------------------------------------------------------------- #
# Gate logic, in isolation
# --------------------------------------------------------------------------- #
def _member(**over):
    base = dict(dataset="PlantDoc", original_archive_path="train/c/a.jpg",
                active_relative_path="train/c/a.jpg", split="train", class_label="c",
                byte_sha256="a" * 64, decoded_rgb_sha256="d" * 64, byte_size=10,
                width=2, height=2, mode="RGB", source_revision="rev")
    base.update(over)
    return DuplicateMember(**base)


def _group(**over):
    members = over.pop("members", (
        _member(), _member(active_relative_path="test/c/a.jpg", split="test")))
    base = dict(dataset="PlantDoc", byte_sha256="a" * 64,
                decoded_rgb_sha256="d" * 64, members=members)
    base.update(over)
    return DuplicateGroup(**base)


def _decision(g, **over):
    row = {"canonical_content_id": g.canonical_content_id,
           "group_handling_decision": "keep_all_records",
           "decision_reason": "reviewed", "reviewer": "human_reviewer_1",
           "reviewed_at": "2026-08-02T21:10:00+05:00"}
    row.update(over)
    return row


def test_no_decisions_is_incomplete():
    g = _group()
    out = build_internal_duplicate_gate([g], [], dataset="PlantDoc")
    assert out.status == "incomplete" and out.unresolved_groups == 1


def test_all_terminal_decisions_pass():
    g = _group()
    out = build_internal_duplicate_gate([g], [_decision(g)], dataset="PlantDoc")
    assert out.status == "pass" and out.resolved_groups == 1


def test_one_missing_decision_prevents_pass():
    a = _group()
    b = _group(byte_sha256="b" * 64,
               members=(_member(byte_sha256="b" * 64),
                        _member(byte_sha256="b" * 64, active_relative_path="test/c/b.jpg",
                                split="test")))
    out = build_internal_duplicate_gate([a, b], [_decision(a)], dataset="PlantDoc")
    assert out.status == "incomplete"
    assert out.unresolved_group_ids == [b.canonical_content_id]


def test_duplicate_decision_row_is_a_violation():
    g = _group()
    out = build_internal_duplicate_gate([g], [_decision(g), _decision(g)],
                                        dataset="PlantDoc")
    assert out.status == "fail"
    assert any("duplicate decision" in v for v in out.violations)


def test_unknown_decision_row_is_a_violation():
    g = _group()
    row = _decision(g, canonical_content_id="pdup-ffffffffffffffff")
    out = build_internal_duplicate_gate([g], [row], dataset="PlantDoc")
    assert out.status == "fail"
    assert any("does not correspond" in v for v in out.violations)


def test_unsupported_decision_is_a_violation():
    g = _group()
    out = build_internal_duplicate_gate(
        [g], [_decision(g, group_handling_decision="delete_everything")],
        dataset="PlantDoc")
    assert out.status == "fail"


def test_deferred_decision_resolves_nothing():
    g = _group()
    out = build_internal_duplicate_gate(
        [g], [_decision(g, group_handling_decision="needs_further_review")],
        dataset="PlantDoc")
    assert out.status == "incomplete" and out.resolved_groups == 0


@pytest.mark.parametrize("field", ["decision_reason", "reviewer", "reviewed_at"])
def test_terminal_decision_needs_attribution(field):
    g = _group()
    out = build_internal_duplicate_gate([g], [_decision(g, **{field: ""})],
                                        dataset="PlantDoc")
    assert out.status == "fail"


@pytest.mark.parametrize("stamp", ["tomorrow", "2026-08-02T21:10:00", "2099-01-01T00:00:00+00:00"])
def test_invalid_review_timestamp_is_a_violation(stamp):
    g = _group()
    out = build_internal_duplicate_gate([g], [_decision(g, reviewed_at=stamp)],
                                        dataset="PlantDoc")
    assert out.status == "fail"


def test_group_identity_is_order_independent():
    m1 = _member()
    m2 = _member(active_relative_path="test/c/a.jpg", split="test")
    assert _group(members=(m1, m2)).canonical_content_id == \
        _group(members=(m2, m1)).canonical_content_id


def test_group_identity_changes_with_label_or_split():
    base = _group()
    other = _group(members=(_member(class_label="different"),
                            _member(active_relative_path="test/c/a.jpg", split="test")))
    assert base.canonical_content_id != other.canonical_content_id


def test_supported_decision_vocabulary_is_explicit():
    assert "keep_all_records" in GROUP_HANDLING_DECISIONS
    assert "needs_further_review" in GROUP_HANDLING_DECISIONS


def test_find_duplicate_groups_ignores_unique_records(tmp_path):
    rows = [
        {"relpath": "train/c/a.jpg", "sha256": "a" * 64, "split": "train",
         "class_label": "c", "n_bytes": "1", "width": "1", "height": "1", "mode": "RGB"},
        {"relpath": "train/c/b.jpg", "sha256": "b" * 64, "split": "train",
         "class_label": "c", "n_bytes": "1", "width": "1", "height": "1", "mode": "RGB"},
    ]
    assert find_duplicate_groups(rows, dataset="PlantDoc", source_revision="r",
                                 active_root=tmp_path) == []


def test_aggregate_categories_sum_to_group_count(groups):
    counts = [
        sum(g["crosses_class"] == "false" and g["crosses_split"] == "false" for g in groups),
        sum(g["crosses_class"] == "false" and g["crosses_split"] == "true" for g in groups),
        sum(g["crosses_class"] == "true" and g["crosses_split"] == "false" for g in groups),
        sum(g["crosses_class"] == "true" and g["crosses_split"] == "true" for g in groups),
    ]
    assert counts == [0, 3, 1, 8]
    assert sum(counts) == 12
