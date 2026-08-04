"""PlantDoc byte-exact duplicate groups, review packet, and internal gate.

R1-CRIT-002: the restored PlantDoc V1 contains groups of records whose FILE BYTES
are identical. Most straddle train/test, and most give identical pixels two
different diagnosis labels. These tests pin the enumeration, prove the packet the
reviewer received was decision-neutral and deterministic, and prove the gate
cannot report `pass` while a single group is unadjudicated.

The reviewer has since decided all twelve groups, so the *live* packet now
carries those decisions. Decision-neutrality is therefore asserted against the
preserved pre-adjudication packet under `human_review/`, which is the artifact
the claim was ever about. What the decisions did to the dataset is tested in
`tests/test_plantdoc_duplicate_remediation.py`.

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

#: The packet exactly as issued to the reviewer, preserved unmodified. This is
#: what "the pipeline offered no recommendation" is a claim about.
ORIGINAL_PACKET = "human_review/plantdoc_exact_duplicates/original"
ORIGINAL_GROUPS_CSV = f"{ORIGINAL_PACKET}/plantdoc_exact_duplicate_groups.csv"

#: Decision columns the packet MUST leave blank when it is issued.
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
# Decision neutrality — asserted on the packet AS ISSUED
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def issued_groups(repo_root):
    return _rows(repo_root / ORIGINAL_GROUPS_CSV)


@pytest.mark.parametrize("column", DECISION_COLUMNS)
def test_every_decision_field_was_blank_when_issued(issued_groups, column):
    assert all(not (g[column] or "").strip() for g in issued_groups), column


def test_no_group_was_marked_resolved_when_issued(issued_groups):
    assert all(g["current_status"] == "unresolved" for g in issued_groups)


def test_the_issued_packet_enumerated_exactly_the_live_groups(issued_groups, groups):
    """The reviewer decided the groups that actually exist -- no more, no fewer."""
    assert len(issued_groups) == len(groups) == 12
    for column in ("canonical_content_id", "byte_sha256", "decoded_rgb_sha256",
                   "member_count", "crosses_split", "crosses_class", "train_count",
                   "test_count", "class_count", "class_labels", "display_group_id"):
        assert ({g[column] for g in issued_groups} == {g[column] for g in groups}), column


def test_every_live_group_now_carries_a_terminal_decision(groups):
    for g in groups:
        assert g["group_handling_decision"] in GROUP_HANDLING_DECISIONS
        assert g["group_handling_decision"] != "needs_further_review"
        assert g["current_status"] == "decision_recorded"
        assert g["decision_reason"] and g["reviewer"] and g["reviewed_at"]


def test_markdown_offers_no_recommendation(repo_root):
    text = (repo_root / PACKET / "PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md").read_text()
    assert "makes no decision" in text
    assert "______" in text                      # blank decision prompts
    for banned in ("we recommend", "should be excluded", "the correct label is"):
        assert banned not in text.lower()


def test_packet_manifest_hashes_are_correct(repo_root):
    """Every digest in the manifest must belong to a file a clone actually has.

    The manifest used to bind four contact-sheet PNGs that `.gitignore`
    excludes, so this test could only pass on the machine that rendered them.
    It now covers exactly the tracked text artifacts.
    """
    import hashlib

    manifest = json.loads((repo_root / PACKET / "packet_manifest.json").read_text())
    assert manifest["group_schema"] == DUPLICATE_GROUP_SCHEMA
    assert manifest["aggregate"]["groups"] == 12
    for name, digest in manifest["artifacts"].items():
        p = repo_root / PACKET / name
        assert p.exists(), name
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest, name


def test_the_manifest_binds_no_untracked_derivative(repo_root):
    manifest = json.loads((repo_root / PACKET / "packet_manifest.json").read_text())
    assert not [n for n in manifest["artifacts"] if n.endswith(".png")]
    derivatives = manifest["rendered_derivatives"]
    # The sheets are still declared -- name, renderer configuration, and the
    # command that regenerates them -- so a reader knows what the reviewer saw.
    assert derivatives["contact_sheets"] == [f"contact_sheet_{i:02d}.png"
                                             for i in range(1, 5)]
    assert derivatives["tracked"] is False
    assert derivatives["required_for_validation"] is False
    assert derivatives["rendering"]["groups_per_sheet"] == 3
    assert derivatives["rendering"]["regenerate_with"]


def test_the_manifest_covers_every_tracked_text_artifact(repo_root):
    manifest = json.loads((repo_root / PACKET / "packet_manifest.json").read_text())
    assert set(manifest["artifacts"]) == {
        "PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md",
        "README.md",
        "plantdoc_exact_duplicate_groups.csv",
        "plantdoc_exact_duplicate_members.csv",
    }


def test_packet_generation_is_deterministic(repo_root, tmp_path, plantdoc_pixels):
    """Re-render the text artifacts; they must reproduce byte-for-byte."""
    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts/build_plantdoc_duplicate_packet.py"),
         "--check"], cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "check OK" in r.stdout


def test_check_does_not_depend_on_locally_rendered_png_files(repo_root, tmp_path):
    """The fresh-clone regression, stated directly.

    `--check` used to discover the sheet list by globbing the packet directory,
    so a clone with no PNGs rendered a Markdown file without the sheet bullets
    and reported an up-to-date packet as stale. The sheet names now come from
    the group count, which a clone always has.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_dup_packet_builder",
        repo_root / "scripts/build_plantdoc_duplicate_packet.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    assert builder.contact_sheet_names(12) == [
        f"contact_sheet_{i:02d}.png" for i in range(1, 5)]
    # Derived purely from the data: 12 groups at 3 per sheet is 4 sheets,
    # whatever happens to exist on disk.
    assert builder.contact_sheet_names(0) == []
    assert builder.contact_sheet_names(1) == ["contact_sheet_01.png"]
    assert builder.contact_sheet_names(4) == ["contact_sheet_01.png",
                                              "contact_sheet_02.png"]


def test_check_mode_writes_nothing(repo_root, plantdoc_pixels):
    """`--check` must not mutate the primary checkout."""
    import hashlib

    packet = repo_root / PACKET
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(packet.iterdir()) if p.is_file()}
    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts/build_plantdoc_duplicate_packet.py"),
         "--check"], cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(packet.iterdir()) if p.is_file()}
    assert before == after


def test_no_source_record_was_changed(repo_root):
    """The packet is read-only with respect to the dataset."""
    manifest = _rows(repo_root / "data/manifests/plantdoc_manifest.csv")
    assert len(manifest) == 2578
    assert len({r["sha256"] for r in manifest}) == 2566


# --------------------------------------------------------------------------- #
# Internal duplicate gate
# --------------------------------------------------------------------------- #
def test_shipped_gate_enumerates_the_full_problem(gate):
    """The counts the gate reports are the ones the re-audit found."""
    assert gate["total_groups"] == 12
    assert gate["total_records"] == 24
    assert gate["cross_split_groups"] == 11
    assert gate["cross_class_groups"] == 9
    assert gate["resolved_groups"] == 12
    assert gate["unresolved_groups"] == 0
    assert gate["unresolved_group_ids"] == []
    assert gate["violations"] == []


def test_gate_binds_its_inputs(gate):
    for name in ("plantdoc_manifest", "duplicate_groups", "duplicate_members",
                 "group_schema"):
        assert name in gate["input_digests"]
        assert gate["input_digests"][name] != "<absent>"


def test_gate_has_no_wall_clock_field(gate):
    assert "generated_at" not in gate


def test_gate_rebuild_is_byte_identical(repo_root, plantdoc_pixels):
    r = subprocess.run(
        [sys.executable,
         str(repo_root / "scripts/build_plantdoc_internal_duplicate_gate.py"), "--check"],
        cwd=str(repo_root), capture_output=True, text=True)
    assert "check OK" in r.stdout, r.stdout + r.stderr
    assert r.returncode == 0         # byte-identical AND passing


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
    """A decision row that reproduces the group's evidence field-for-field.

    The evidence columns are not decoration: a row that fails to reproduce them
    is refused, so a helper that omitted them would test the wrong rejection.
    """
    from ica26.datasets.duplicates import display_group_ids

    row = {"canonical_content_id": g.canonical_content_id,
           "group_id": g.canonical_content_id,
           "display_group_id": display_group_ids([g])[g.canonical_content_id],
           "byte_sha256": g.byte_sha256,
           "decoded_rgb_sha256": g.decoded_rgb_sha256,
           "member_count": str(g.member_count),
           "crosses_split": "true" if g.crosses_split else "false",
           "crosses_class": "true" if g.crosses_class else "false",
           "train_count": str(g.train_count), "test_count": str(g.test_count),
           "class_count": str(g.class_count), "class_labels": " | ".join(g.classes),
           "group_handling_decision": "keep_all_records",
           "decision_reason": "reviewed", "reviewer": "human_reviewer_1",
           "reviewed_at": "2026-08-02T21:10:00+05:00"}
    row.update(over)
    return row


def test_no_decisions_is_incomplete():
    g = _group()
    out = build_internal_duplicate_gate([g], [], dataset="PlantDoc")
    assert out.status == "incomplete" and out.unresolved_groups == 1


def test_a_recorded_decision_is_credited_but_does_not_by_itself_pass():
    """Schema 2.0: "a human decided" and "the decision was applied" are two claims.

    ``keep_all_records`` is terminal, so the adjudication half credits the group —
    and the gate still refuses, because leaving byte-identical pixels on both
    sides of the split is not something this pipeline will materialise.
    """
    g = _group()
    out = build_internal_duplicate_gate([g], [_decision(g)], dataset="PlantDoc")
    assert out.resolved_groups == 1 and out.unresolved_groups == 0
    assert out.status == "fail"
    assert any("has no defined remediation" in v for v in out.violations)


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
