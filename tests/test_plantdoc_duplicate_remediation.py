"""R2B: applying the human adjudication of PlantDoc byte-exact duplicate groups.

`tests/test_plantdoc_duplicates.py` proves the groups were enumerated honestly and
that no gate could report `pass` while a group was unadjudicated. These tests
prove the other half: that the twelve recorded decisions were applied *exactly*,
that nothing else moved, and that the gate cannot be talked into accepting a
substituted record — including at an identical row count, which is the shape of
exploit the R1 re-audit found in the cross-dataset gate.

Nothing here decides anything, and no test may assert a diagnosis. Where a label
appears it is read from the recorded human decision.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys

import pytest

from ica26.datasets.duplicate_remediation import (
    NOT_APPLICABLE,
    REMEDIABLE_ACTIONS,
    Adjudication,
    apply_adjudication,
    build_effective_records,
    effective_record_id,
    identity_set,
    identity_set_digest,
    reconcile_identity_sets,
    resolve_canonical_member,
    resolution_rows,
    verify_effective_records,
)
from ica26.datasets.duplicates import (
    DuplicateGroup,
    DuplicateMember,
    build_internal_duplicate_gate,
    display_group_ids,
    find_duplicate_groups,
    validate_internal_gate,
)

PACKET = "reports/plantdoc_exact_duplicate_review"
GROUPS_CSV = f"{PACKET}/plantdoc_exact_duplicate_groups.csv"
MANIFEST_CSV = "data/manifests/plantdoc_manifest.csv"
EFFECTIVE_CSV = "data/manifests/plantdoc_effective_manifest.csv"
RESOLUTION_CSV = "data/exclusions/plantdoc_internal_duplicate_resolution.csv"
GATE_JSON = "reports/plantdoc_internal_duplicate_gate.json"

#: The recorded outcome of each group, read from the human decision file, not
#: from any judgement of ours. Pinned so a silent change to a decision fails.
EXPECTED_ACTIONS = {
    "G01": "keep_one_record", "G02": "keep_one_record", "G03": "exclude_all_records",
    "G04": "keep_one_record", "G05": "keep_one_record", "G06": "keep_one_record",
    "G07": "keep_one_record", "G08": "keep_one_record", "G09": "keep_one_record",
    "G10": "keep_one_record", "G11": "exclude_all_records", "G12": "keep_one_record",
}


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# Synthetic fixtures. Adversarial cases must not depend on the real dataset.
# --------------------------------------------------------------------------- #
def _member(**over) -> DuplicateMember:
    base = dict(dataset="PlantDoc", original_archive_path="train/alpha/a.jpg",
                active_relative_path="train/alpha/a.jpg", split="train",
                class_label="alpha", byte_sha256="a" * 64, decoded_rgb_sha256="d" * 64,
                byte_size=10, width=2, height=2, mode="RGB", source_revision="rev")
    base.update(over)
    return DuplicateMember(**base)


def _cross_split_group(sha="a" * 64, cls_a="alpha", cls_b="alpha", stem="a") -> DuplicateGroup:
    """One byte-identical record in train and one in test."""
    return DuplicateGroup(
        dataset="PlantDoc", byte_sha256=sha, decoded_rgb_sha256="d" * 64,
        members=(
            _member(byte_sha256=sha, class_label=cls_b,
                    active_relative_path=f"test/{cls_b}/{stem}.jpg",
                    original_archive_path=f"test/{cls_b}/{stem}.jpg", split="test"),
            _member(byte_sha256=sha, class_label=cls_a,
                    active_relative_path=f"train/{cls_a}/{stem}.jpg",
                    original_archive_path=f"train/{cls_a}/{stem}.jpg", split="train"),
        ))


def _decision(group, display, **over) -> dict:
    """A decision row that reproduces the group's evidence field-for-field."""
    row = {
        "group_id": group.canonical_content_id,
        "display_group_id": display,
        "canonical_content_id": group.canonical_content_id,
        "byte_sha256": group.byte_sha256,
        "decoded_rgb_sha256": group.decoded_rgb_sha256,
        "member_count": str(group.member_count),
        "crosses_split": "true" if group.crosses_split else "false",
        "crosses_class": "true" if group.crosses_class else "false",
        "train_count": str(group.train_count),
        "test_count": str(group.test_count),
        "class_count": str(group.class_count),
        "class_labels": " | ".join(group.classes),
        "current_status": "decision_recorded",
        "group_handling_decision": "keep_one_record",
        "canonical_label_decision": group.classes[0],
        "split_handling_decision": "move_to_train",
        "decision_reason": "recorded by a human reviewer",
        "reviewer": "human_reviewer_1",
        "reviewed_at": "2026-08-03T14:28:00+05:00",
    }
    row.update(over)
    return row


def _manifest_rows(*groups) -> list[dict]:
    return [{"dataset": m.dataset, "split": m.split, "class_label": m.class_label,
             "relpath": m.active_relative_path, "sha256": m.byte_sha256,
             "width": m.width, "height": m.height, "mode": m.mode,
             "n_bytes": m.byte_size, "is_corrupt": "False", "source_url": "u",
             "acquired_at_utc": "2026-08-02T18:02:14+00:00"}
            for g in groups for m in g.members]


def _apply(groups, decisions, extra_rows=()):
    display = display_group_ids(groups)
    adj = apply_adjudication(groups, decisions)
    rows = _manifest_rows(*groups) + list(extra_rows)
    effective, build_v = build_effective_records(rows, adj)
    verify_v, report = verify_effective_records(rows, effective, adj, groups)
    return display, adj, effective, sorted(adj.violations + build_v + verify_v), report


# --------------------------------------------------------------------------- #
# The twelve real decisions
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def decisions(repo_root):
    return _rows(repo_root / GROUPS_CSV)


@pytest.fixture(scope="module")
def resolution(repo_root):
    return _rows(repo_root / RESOLUTION_CSV)


@pytest.fixture(scope="module")
def gate(repo_root):
    return json.loads((repo_root / GATE_JSON).read_text())


@pytest.mark.parametrize("display", sorted(EXPECTED_ACTIONS))
def test_every_reviewed_group_has_its_recorded_terminal_decision(decisions, display):
    row = next(r for r in decisions if r["display_group_id"] == display)
    assert row["group_handling_decision"] == EXPECTED_ACTIONS[display]
    assert row["group_handling_decision"] in REMEDIABLE_ACTIONS
    assert row["decision_reason"] and row["reviewer"] and row["reviewed_at"]


def test_all_twelve_groups_are_decided_exactly_once(decisions):
    assert len(decisions) == 12
    assert len({r["canonical_content_id"] for r in decisions}) == 12
    assert sorted(r["display_group_id"] for r in decisions) == sorted(EXPECTED_ACTIONS)
    assert not [r for r in decisions if r["group_handling_decision"] == "needs_further_review"]


@pytest.mark.parametrize("display", sorted(EXPECTED_ACTIONS))
def test_each_group_retains_exactly_what_its_decision_authorises(resolution, display):
    members = [r for r in resolution if r["display_group_id"] == display]
    retained = [r for r in members if r["remediation_action"] == "retain_canonical"]
    assert len(members) == 2
    assert len(retained) == (1 if EXPECTED_ACTIONS[display] == "keep_one_record" else 0)


def test_keep_one_record_groups_apply_the_adjudicated_label_and_split(resolution, decisions):
    by_display = {r["display_group_id"]: r for r in decisions}
    kept = [r for r in resolution if r["remediation_action"] == "retain_canonical"]
    assert len(kept) == 10
    for r in kept:
        decision = by_display[r["display_group_id"]]
        assert r["effective_class_label"] == decision["canonical_label_decision"]
        assert r["effective_split"] == "train" == decision["split_handling_decision"][len("move_to_"):]
        assert r["effective_record_id"].startswith("erec-")


def test_exclude_all_records_groups_assign_no_label(resolution, decisions):
    excluded_groups = {d["display_group_id"] for d in decisions
                       if d["group_handling_decision"] == "exclude_all_records"}
    assert excluded_groups == {"G03", "G11"}
    for r in resolution:
        if r["display_group_id"] in excluded_groups:
            assert r["remediation_action"] == "exclude_group"
            assert r["effective_class_label"] == ""
            assert r["effective_split"] == ""
            assert r["effective_record_id"] == ""
            assert r["canonical_label_decision"] == NOT_APPLICABLE


def test_contradictory_label_groups_are_all_resolved(decisions, resolution):
    contradictory = [d for d in decisions if d["crosses_class"] == "true"]
    assert len(contradictory) == 9
    for d in contradictory:
        kept = [r for r in resolution
                if r["display_group_id"] == d["display_group_id"]
                and r["remediation_action"] == "retain_canonical"]
        if d["group_handling_decision"] == "exclude_all_records":
            assert kept == []
        else:
            # one surviving record, therefore exactly one surviving label
            assert len(kept) == 1
            assert kept[0]["effective_class_label"] == d["canonical_label_decision"]


def test_a_relabelled_record_keeps_its_source_label_in_provenance(resolution):
    """G07/G08/G10 land on a label none of their own paths carries."""
    relabelled = [r for r in resolution if r["remediation_action"] == "retain_canonical"
                  and r["effective_class_label"] != r["source_class_label"]]
    assert {r["display_group_id"] for r in relabelled} == {"G07", "G08", "G10"}
    for r in relabelled:
        assert r["source_class_label"]          # the original is never overwritten
        assert r["decision_reason"] and r["reviewer"]


def test_every_excluded_record_names_the_decision_that_removed_it(resolution):
    excluded = [r for r in resolution if r["remediation_action"] != "retain_canonical"]
    assert len(excluded) == 14
    for r in excluded:
        assert r["group_handling_decision"] in REMEDIABLE_ACTIONS
        assert r["reviewer"] and r["reviewed_at"] and r["decision_reason"]
        assert len(r["byte_sha256"]) == 64      # evidence preserved, not just a path


# --------------------------------------------------------------------------- #
# The effective dataset
# --------------------------------------------------------------------------- #
def test_train_test_exact_duplicates_are_gone(repo_root):
    source, effective = _rows(repo_root / MANIFEST_CSV), _rows(repo_root / EFFECTIVE_CSV)

    def cross_split(rows):
        by_sha = {}
        for r in rows:
            by_sha.setdefault(r["sha256"], set()).add(r["split"])
        return sum(1 for s in by_sha.values() if len(s) > 1)

    assert cross_split(source) == 11        # the problem R1-CRIT-002 reported
    assert cross_split(effective) == 0      # and what the decisions removed


def test_no_exact_duplicate_survives_anywhere(repo_root):
    effective = _rows(repo_root / EFFECTIVE_CSV)
    assert len(effective) == 2564
    assert len({r["sha256"] for r in effective}) == len(effective)
    assert len({r["relpath"] for r in effective}) == len(effective)
    assert len(set(identity_set(effective))) == len(effective)


def test_no_record_outside_the_reviewed_set_changed(repo_root):
    source = _rows(repo_root / MANIFEST_CSV)
    effective = {r["relpath"]: r for r in _rows(repo_root / EFFECTIVE_CSV)}
    reviewed = {r["active_relative_path"] for r in _rows(repo_root / RESOLUTION_CSV)}
    assert len(reviewed) == 24

    unchanged = 0
    for r in source:
        if r["relpath"] in reviewed:
            continue
        assert r["relpath"] in effective, r["relpath"]
        assert effective[r["relpath"]] == r, r["relpath"]
        unchanged += 1
    assert unchanged == len(source) - 24 == 2554
    assert set(effective) - reviewed == {r["relpath"] for r in source} - reviewed


def test_effective_record_count_is_derived_not_asserted(repo_root):
    source = _rows(repo_root / MANIFEST_CSV)
    resolution = _rows(repo_root / RESOLUTION_CSV)
    removed = sum(1 for r in resolution if r["remediation_action"] != "retain_canonical")
    assert len(_rows(repo_root / EFFECTIVE_CSV)) == len(source) - removed


def test_persisted_and_freshly_reconstructed_identity_sets_are_equal(repo_root):
    """A full rebuild from the authoritative manifest, compared by identity."""
    source = _rows(repo_root / MANIFEST_CSV)
    groups = find_duplicate_groups(
        source, dataset="PlantDoc",
        source_revision="5467f6012d78d1c446145d5f582da6096f852ae8",
        active_root=repo_root / "data/raw/plantdoc")
    adj = apply_adjudication(groups, _rows(repo_root / GROUPS_CSV))
    assert adj.ok, adj.violations
    fresh, build_v = build_effective_records(source, adj)
    assert build_v == []

    persisted = _rows(repo_root / EFFECTIVE_CSV)
    violations, report = reconcile_identity_sets(fresh, persisted)
    assert violations == []
    assert report["equal"] is True
    assert report["fresh_digest"] == report["persisted_digest"]
    assert identity_set(fresh) == identity_set(persisted)


def test_shipped_gate_passes_and_records_the_remediation(gate):
    assert gate["schema_version"] == "2.0"
    assert gate["status"] == "pass"
    assert gate["resolved_groups"] == 12 and gate["unresolved_groups"] == 0
    assert gate["violations"] == []
    r = gate["remediation"]
    assert r["evaluated"] is True and r["ok"] is True
    assert r["groups_by_action"] == {"keep_one_record": 10, "exclude_all_records": 2}
    assert r["retained_records"] == 10 and r["excluded_records"] == 14
    assert r["surviving_exact_duplicate_groups"] == 0
    assert r["surviving_cross_split_duplicate_groups"] == 0
    assert r["surviving_contradictory_label_groups"] == 0
    assert r["non_reviewed_records_unchanged"] is True
    assert gate["identity_reconciliation"]["equal"] is True
    assert len(gate["group_outcomes"]) == 12


def test_gate_binds_the_remediation_artifacts(gate):
    for name in ("plantdoc_manifest", "duplicate_groups", "duplicate_members",
                 "duplicate_resolution", "effective_manifest", "group_schema"):
        assert gate["input_digests"].get(name) not in (None, "<absent>"), name


def test_gate_has_no_wall_clock_field(gate):
    assert "generated_at" not in gate


def test_remediation_is_idempotent(repo_root):
    """A second execution must change nothing at all."""
    before = {p: (repo_root / p).read_bytes()
              for p in (EFFECTIVE_CSV, RESOLUTION_CSV, GATE_JSON)}
    for script in ("scripts/apply_plantdoc_duplicate_adjudication.py",
                   "scripts/build_plantdoc_internal_duplicate_gate.py"):
        r = subprocess.run([sys.executable, str(repo_root / script), "--check"],
                           cwd=str(repo_root), capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "check OK" in r.stdout
    assert {p: (repo_root / p).read_bytes()
            for p in (EFFECTIVE_CSV, RESOLUTION_CSV, GATE_JSON)} == before


# --------------------------------------------------------------------------- #
# Fail-closed behaviour, on synthetic data
# --------------------------------------------------------------------------- #
def test_keep_one_record_retains_one_and_moves_it_to_the_decided_split():
    g = _cross_split_group()
    display, adj, effective, violations, report = _apply(
        [g], [_decision(g, "G01")])
    assert violations == []
    outcome = adj.groups[g.canonical_content_id]
    assert len(outcome.retained) == 1 and len(outcome.excluded) == 1
    assert [r["relpath"] for r in effective] == ["train/alpha/a.jpg"]
    assert effective[0]["split"] == "train" and effective[0]["class_label"] == "alpha"
    assert report["surviving_exact_duplicate_groups"] == 0


def test_exclude_all_records_removes_every_member():
    g = _cross_split_group()
    _, adj, effective, violations, report = _apply(
        [g], [_decision(g, "G01", group_handling_decision="exclude_all_records",
                        canonical_label_decision=NOT_APPLICABLE,
                        split_handling_decision=NOT_APPLICABLE)])
    assert violations == []
    assert effective == []
    assert len(adj.groups[g.canonical_content_id].retained) == 0
    assert report["excluded_records"] == 2


def test_exclude_all_records_may_not_smuggle_in_a_label():
    g = _cross_split_group(cls_a="alpha", cls_b="beta")
    _, _, _, violations, _ = _apply(
        [g], [_decision(g, "G01", group_handling_decision="exclude_all_records",
                        canonical_label_decision="alpha",
                        split_handling_decision=NOT_APPLICABLE)])
    assert any("must not assert" in v for v in violations)


def test_canonical_label_outside_the_vocabulary_is_refused():
    g = _cross_split_group()
    _, _, _, violations, _ = _apply(
        [g], [_decision(g, "G01", canonical_label_decision="a class that does not exist")])
    assert any("not in the dataset's class vocabulary" in v for v in violations)


def test_keep_one_record_without_a_label_is_refused():
    g = _cross_split_group()
    for label in ("", NOT_APPLICABLE):
        _, _, _, violations, _ = _apply(
            [g], [_decision(g, "G01", canonical_label_decision=label)])
        assert any("requires an explicit canonical_label_decision" in v for v in violations)


def test_keep_one_record_without_a_single_destination_split_is_refused():
    g = _cross_split_group()
    for split in ("", "keep_current_split", "group_aware_split"):
        _, _, _, violations, _ = _apply(
            [g], [_decision(g, "G01", split_handling_decision=split)])
        assert any("naming one destination split" in v for v in violations), split


def test_move_to_test_is_honoured_when_that_is_what_was_decided():
    g = _cross_split_group()
    _, _, effective, violations, _ = _apply(
        [g], [_decision(g, "G01", split_handling_decision="move_to_test")])
    assert violations == []
    assert [(r["relpath"], r["split"]) for r in effective] == [("test/alpha/a.jpg", "test")]


def test_canonical_member_choice_is_deterministic_and_prefers_the_decided_split():
    g = _cross_split_group()
    assert resolve_canonical_member(g, "train").split == "train"
    assert resolve_canonical_member(g, "test").split == "test"
    # order of the member tuple must not matter
    reversed_g = DuplicateGroup(dataset=g.dataset, byte_sha256=g.byte_sha256,
                                decoded_rgb_sha256=g.decoded_rgb_sha256,
                                members=tuple(reversed(g.members)))
    assert (resolve_canonical_member(reversed_g, "train").active_relative_path
            == resolve_canonical_member(g, "train").active_relative_path)


def test_same_split_group_falls_back_to_the_lexicographic_first_member():
    """Both members already in train: the choice must still be reproducible."""
    g = DuplicateGroup(
        dataset="PlantDoc", byte_sha256="a" * 64, decoded_rgb_sha256="d" * 64,
        members=(_member(active_relative_path="train/alpha/z.jpg"),
                 _member(active_relative_path="train/alpha/b.jpg")))
    assert resolve_canonical_member(g, "train").active_relative_path == "train/alpha/b.jpg"


def test_missing_decision_is_refused():
    a, b = _cross_split_group(), _cross_split_group(sha="b" * 64, stem="b")
    display = display_group_ids([a, b])
    _, _, _, violations, _ = _apply([a, b], [_decision(a, display[a.canonical_content_id])])
    assert any("has no decision row" in v for v in violations)


def test_duplicated_decision_row_is_refused():
    g = _cross_split_group()
    _, _, _, violations, _ = _apply([g], [_decision(g, "G01"), _decision(g, "G01")])
    assert any("duplicate decision" in v for v in violations)


def test_unknown_group_is_refused():
    g = _cross_split_group()
    row = _decision(g, "G01", canonical_content_id="pdup-ffffffffffffffff")
    _, _, _, violations, _ = _apply([g], [row])
    assert any("does not correspond to any enumerated duplicate group" in v for v in violations)
    assert any("has no decision row" in v for v in violations)


@pytest.mark.parametrize("action", ["keep_all_records", "exclude_from_evaluation"])
def test_terminal_but_unremediable_action_is_refused(action):
    """A decision this pipeline cannot materialise must stop it, not be ignored."""
    g = _cross_split_group()
    _, _, _, violations, _ = _apply([g], [_decision(g, "G01", group_handling_decision=action)])
    assert any("has no defined remediation" in v for v in violations)


def test_unknown_action_is_refused():
    g = _cross_split_group()
    _, _, _, violations, _ = _apply(
        [g], [_decision(g, "G01", group_handling_decision="delete_everything")])
    assert any("unsupported group_handling_decision" in v for v in violations)


def test_non_terminal_decision_is_refused():
    g = _cross_split_group()
    _, _, _, violations, _ = _apply(
        [g], [_decision(g, "G01", group_handling_decision="needs_further_review")])
    assert any("not terminal" in v for v in violations)


@pytest.mark.parametrize("field", ["decision_reason", "reviewer", "reviewed_at"])
def test_terminal_decision_without_attribution_is_refused(field):
    g = _cross_split_group()
    _, _, _, violations, _ = _apply([g], [_decision(g, "G01", **{field: ""})])
    assert any("without" in v for v in violations)


@pytest.mark.parametrize("stamp", ["tomorrow", "2026-08-03T14:28:00", "2099-01-01T00:00:00+00:00"])
def test_invalid_review_timestamp_is_refused(stamp):
    g = _cross_split_group()
    _, _, _, violations, _ = _apply([g], [_decision(g, "G01", reviewed_at=stamp)])
    assert violations


# --- identity forgery ------------------------------------------------------- #
@pytest.mark.parametrize("column", [
    "byte_sha256", "decoded_rgb_sha256", "member_count", "crosses_split",
    "crosses_class", "train_count", "test_count", "class_count", "class_labels",
    "display_group_id", "group_id",
])
def test_decision_row_with_drifted_evidence_is_refused(column):
    """The row must reproduce the group's facts, not merely name its id."""
    g = _cross_split_group(cls_a="alpha", cls_b="beta")
    forged = _decision(g, display_group_ids([g])[g.canonical_content_id])
    forged[column] = "9" * 64 if "sha256" in column else "999"
    _, _, _, violations, _ = _apply([g], [forged])
    assert any("evidence mismatch" in v for v in violations), column


def test_hash_mismatch_between_manifest_and_reviewed_evidence_is_refused():
    """The review said one digest; the manifest now says another."""
    g = _cross_split_group()
    adj = apply_adjudication([g], [_decision(g, "G01")])
    assert adj.ok
    rows = _manifest_rows(g)
    rows[0]["sha256"] = "f" * 64
    _, violations = build_effective_records(rows, adj)
    assert any("byte digest" in v and "reviewed evidence records" in v for v in violations)


def test_membership_change_since_the_review_is_refused():
    """A reviewed record that is no longer in the manifest cannot be remediated."""
    g = _cross_split_group()
    adj = apply_adjudication([g], [_decision(g, "G01")])
    rows = [r for r in _manifest_rows(g) if r["split"] != "test"]
    _, violations = build_effective_records(rows, adj)
    assert any("authoritative membership changed" in v for v in violations)


def test_forged_group_with_the_same_row_count_is_refused():
    """The R1-CRIT-001 shape: right number of decisions, wrong identities.

    Two real groups, two decision rows — but one row was written against a
    *substituted* member set. Its content-derived id no longer matches anything,
    so the count agrees and the authorization still fails, twice over.
    """
    real_a = _cross_split_group(stem="a")
    real_b = _cross_split_group(sha="b" * 64, stem="b")
    display = display_group_ids([real_a, real_b])

    substituted = _cross_split_group(sha="b" * 64, stem="forged")
    rows = [_decision(real_a, display[real_a.canonical_content_id]),
            _decision(substituted, display[real_b.canonical_content_id])]
    assert len(rows) == 2 == len([real_a, real_b])       # counts agree exactly

    _, adj, _, violations, _ = _apply([real_a, real_b], rows)
    assert not adj.ok
    assert any("does not correspond to any enumerated duplicate group" in v for v in violations)
    assert any("has no decision row" in v for v in violations)


def test_forged_effective_manifest_with_the_same_row_count_is_refused():
    """A persisted set of the right size with one record swapped must not reconcile."""
    g = _cross_split_group()
    other = {"dataset": "PlantDoc", "split": "train", "class_label": "alpha",
             "relpath": "train/alpha/keep.jpg", "sha256": "c" * 64, "width": 2,
             "height": 2, "mode": "RGB", "n_bytes": 10, "is_corrupt": "False",
             "source_url": "u", "acquired_at_utc": "2026-08-02T18:02:14+00:00"}
    _, _, fresh, violations, _ = _apply([g], [_decision(g, "G01")], extra_rows=[other])
    assert violations == []
    assert len(fresh) == 2

    forged = [dict(r) for r in fresh]
    forged[-1]["relpath"] = "train/alpha/substituted.jpg"
    assert len(forged) == len(fresh)                      # counts agree exactly

    set_violations, report = reconcile_identity_sets(fresh, forged)
    assert set_violations
    assert report["equal"] is False
    assert report["fresh_count"] == report["persisted_count"]
    assert report["fresh_digest"] != report["persisted_digest"]


def test_a_reviewed_record_silently_replaced_by_another_is_caught():
    g = _cross_split_group()
    display, adj, effective, _, _ = _apply([g], [_decision(g, "G01")])
    rows = _manifest_rows(g)
    tampered = [dict(r) for r in effective]
    tampered[0]["relpath"] = "train/alpha/someone-elses-file.jpg"
    violations, _ = verify_effective_records(rows, tampered, adj, [g])
    assert any("retained canonical record" in v for v in violations)


def test_a_record_outside_the_reviewed_set_may_not_change():
    g = _cross_split_group()
    other = {"dataset": "PlantDoc", "split": "test", "class_label": "alpha",
             "relpath": "test/alpha/untouched.jpg", "sha256": "c" * 64, "width": 2,
             "height": 2, "mode": "RGB", "n_bytes": 10, "is_corrupt": "False",
             "source_url": "u", "acquired_at_utc": "2026-08-02T18:02:14+00:00"}
    display, adj, effective, violations, report = _apply(
        [g], [_decision(g, "G01")], extra_rows=[other])
    assert violations == [] and report["non_reviewed_records_unchanged"] is True

    rows = _manifest_rows(g) + [other]
    for mutation in ({"split": "train"}, {"class_label": "beta"}, {"sha256": "e" * 64}):
        tampered = [dict(r) for r in effective]
        target = next(r for r in tampered if r["relpath"] == "test/alpha/untouched.jpg")
        target.update(mutation)
        v, rep = verify_effective_records(rows, tampered, adj, [g])
        assert any("non-reviewed record" in x for x in v), mutation
        assert rep["non_reviewed_records_unchanged"] is False


def test_an_excluded_record_that_survives_is_caught():
    g = _cross_split_group()
    display, adj, effective, _, _ = _apply([g], [_decision(g, "G01")])
    rows = _manifest_rows(g)
    violations, _ = verify_effective_records(rows, rows, adj, [g])   # nothing removed
    assert any("still in the effective dataset" in v for v in violations)


def test_a_silently_dropped_group_is_caught():
    a, b = _cross_split_group(stem="a"), _cross_split_group(sha="b" * 64, stem="b")
    display = display_group_ids([a, b])
    adj = apply_adjudication([a], [_decision(a, display[a.canonical_content_id])])
    rows = _manifest_rows(a, b)
    effective, _ = build_effective_records(rows, adj)
    violations, _ = verify_effective_records(rows, effective, adj, [a, b])
    assert any("a group was dropped" in v for v in violations)


def test_one_record_claimed_by_two_groups_is_refused():
    g = _cross_split_group()
    twin = DuplicateGroup(dataset="PlantDoc", byte_sha256="b" * 64,
                          decoded_rgb_sha256="e" * 64, members=g.members)
    display = display_group_ids([g, twin])
    adj = apply_adjudication([g, twin], [_decision(g, display[g.canonical_content_id]),
                                         _decision(twin, display[twin.canonical_content_id])])
    assert any("claimed by two duplicate groups" in v for v in adj.violations)


# --- identity primitives ---------------------------------------------------- #
def test_effective_record_id_is_content_derived():
    row = {"dataset": "PlantDoc", "relpath": "train/alpha/a.jpg", "split": "train",
           "class_label": "alpha", "sha256": "a" * 64, "n_bytes": 10, "width": 2,
           "height": 2, "mode": "RGB"}
    base = effective_record_id(row)
    assert base.startswith("erec-") and len(base) == len("erec-") + 16
    assert effective_record_id(dict(row)) == base                    # pure
    assert effective_record_id({**row, "acquired_at_utc": "later"}) == base
    for field in ("relpath", "split", "class_label", "sha256", "n_bytes", "width",
                  "height", "mode", "dataset"):
        assert effective_record_id({**row, field: "changed"}) != base, field


def test_identity_set_digest_ignores_row_order():
    rows = [{"dataset": "PlantDoc", "relpath": f"train/alpha/{i}.jpg", "split": "train",
             "class_label": "alpha", "sha256": str(i) * 64, "n_bytes": i, "width": 2,
             "height": 2, "mode": "RGB"} for i in range(1, 5)]
    assert identity_set_digest(rows) == identity_set_digest(list(reversed(rows)))


def test_resolution_rows_are_stable_and_complete():
    g = _cross_split_group()
    adj = apply_adjudication([g], [_decision(g, "G01")])
    rows = resolution_rows(adj)
    assert [r["member_id"] for r in rows] == ["G01-m1", "G01-m2"]
    assert resolution_rows(adj) == rows


# --- gate integration ------------------------------------------------------- #
def test_gate_fails_when_the_persisted_set_is_not_supplied():
    g = _cross_split_group()
    out = build_internal_duplicate_gate([g], [_decision(g, "G01")], dataset="PlantDoc")
    assert out.status == "fail"
    assert any("fresh-vs-persisted" in v for v in out.violations)


def test_gate_passes_only_with_a_matching_persisted_set():
    g = _cross_split_group()
    rows = _manifest_rows(g)
    decisions = [_decision(g, "G01")]
    adj = apply_adjudication([g], decisions)
    effective, _ = build_effective_records(rows, adj)
    out = build_internal_duplicate_gate(
        [g], decisions, dataset="PlantDoc", manifest_rows=rows,
        persisted_effective=effective)
    assert out.status == "pass"
    assert validate_internal_gate(out) == []


def test_gate_refuses_a_persisted_set_that_still_holds_an_excluded_record():
    g = _cross_split_group()
    rows = _manifest_rows(g)
    decisions = [_decision(g, "G01")]
    out = build_internal_duplicate_gate(
        [g], decisions, dataset="PlantDoc", manifest_rows=rows, persisted_effective=rows)
    assert out.status == "fail"
    assert validate_internal_gate(out)


def test_gate_does_not_evaluate_remediation_against_uncredited_decisions():
    """No decision at all: incomplete, and the remediation is not pretended."""
    g = _cross_split_group()
    out = build_internal_duplicate_gate([g], [], dataset="PlantDoc")
    assert out.status == "incomplete"
    assert out.remediation["evaluated"] is False
    assert validate_internal_gate(out)


def test_validate_internal_gate_rejects_an_older_schema():
    g = _cross_split_group()
    rows = _manifest_rows(g)
    decisions = [_decision(g, "G01")]
    adj = apply_adjudication([g], decisions)
    effective, _ = build_effective_records(rows, adj)
    out = build_internal_duplicate_gate(
        [g], decisions, dataset="PlantDoc", manifest_rows=rows,
        persisted_effective=effective)
    out.schema_version = "1.0"
    assert any("did not verify that decisions were applied" in e
               for e in validate_internal_gate(out))


def test_empty_adjudication_reports_no_outcomes():
    adj = Adjudication()
    assert adj.ok and adj.members == [] and adj.counts()["groups"] == 0
