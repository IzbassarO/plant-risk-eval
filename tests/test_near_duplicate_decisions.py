"""Near-duplicate adjudication: recorded decisions and how the gate consumes them.

`LEAKAGE_GATE_EXCLUSION_POLICY.md` §3 says a flagged near pair is *resolved* once
a human gives it a terminal decision -- keeping a pair resolves it just as much
as excluding one, because the reviewer looked at the contact sheet and judged the
two images independent. These tests pin that semantics and prove it stays
fail-closed for every non-terminal state.
"""
from __future__ import annotations

import csv

import pytest

from ica26.leakage.gate import (
    NEAR_REVIEW_DECISIONS,
    NEAR_REVIEW_DISPOSITIONS,
    summarize_near_review,
)

REVIEW_CSV = "data/exclusions/cross_dataset_near_duplicate_review.csv"
REVIEWED_EXCL_CSV = "data/exclusions/cross_dataset_reviewed_exclusions.csv"

REVIEW_COLUMNS = [
    "pair_id", "training_dataset", "training_relative_path", "training_class",
    "training_sha256", "evaluation_dataset", "evaluation_relative_path",
    "evaluation_class", "evaluation_sha256", "phash_distance", "contact_sheet",
    "human_decision", "decision_reason", "reviewer", "reviewed_at",
    "final_disposition",
]


@pytest.fixture(scope="module")
def recorded(repo_root):
    with open(repo_root / REVIEW_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# The recorded decisions themselves
# --------------------------------------------------------------------------- #
def test_all_sixteen_pairs_are_adjudicated(recorded):
    assert len(recorded) == 16
    assert [r["pair_id"] for r in recorded] == [f"ndp-{i:02d}" for i in range(1, 17)]
    for r in recorded:
        assert r["human_decision"] in NEAR_REVIEW_DECISIONS
        assert r["final_disposition"] in NEAR_REVIEW_DISPOSITIONS


def test_recorded_decisions_match_the_confirmed_review(recorded):
    by_id = {r["pair_id"]: r for r in recorded}
    for i in range(1, 16):
        assert by_id[f"ndp-{i:02d}"]["human_decision"] == "clearly_different"
    assert by_id["ndp-16"]["human_decision"] == "visually_similar_but_independent"
    assert {r["final_disposition"] for r in recorded} == {"keep"}


def test_aggregate_counts(recorded):
    assert sum(r["final_disposition"] == "keep" for r in recorded) == 16
    assert sum(r["final_disposition"] == "exclude_evaluation" for r in recorded) == 0
    assert sum(r["human_decision"] == "uncertain" for r in recorded) == 0
    assert sum(r["final_disposition"] == "needs_secondary_review" for r in recorded) == 0


def test_every_decision_is_attributed_anonymously(recorded):
    for r in recorded:
        assert r["reviewer"] == "human_reviewer_1"
        assert r["reviewed_at"] == "2026-08-02T21:10:00+05:00"
        assert r["decision_reason"].strip()


def test_no_pair_was_excluded_so_the_exclusions_file_stays_empty(repo_root):
    with open(repo_root / REVIEWED_EXCL_CSV, newline="", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh)) == []


def test_identity_fields_are_intact(recorded):
    for r in recorded:
        assert r["training_dataset"] == "PlantVillage"
        assert r["evaluation_dataset"] == "PlantDoc"
        assert len(r["training_sha256"]) == 64
        assert len(r["evaluation_sha256"]) == 64
        assert 0 < int(r["phash_distance"]) <= 6


# --------------------------------------------------------------------------- #
# How the gate consumes them
# --------------------------------------------------------------------------- #
def _keys(rows):
    return {(r["training_relative_path"], r["evaluation_relative_path"]) for r in rows}


def test_kept_pairs_count_as_resolved(repo_root, recorded):
    out = summarize_near_review(repo_root / REVIEW_CSV, _keys(recorded),
                                repo_root / REVIEWED_EXCL_CSV)
    assert out["resolved"] == 16
    assert out["kept"] == 16
    assert out["excluded"] == 0
    assert out["unresolved"] == 0
    assert out["invalid"] == 0
    assert out["unmatched"] == 0


def _write(tmp_path, rows):
    p = tmp_path / "review.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return p


def _row(**kw):
    r = {c: "" for c in REVIEW_COLUMNS}
    r.update({
        "pair_id": "ndp-01", "training_relative_path": "t/a.jpg",
        "evaluation_relative_path": "e/b.jpg", "phash_distance": "6",
        "human_decision": "clearly_different", "final_disposition": "keep",
        "reviewer": "human_reviewer_1", "reviewed_at": "2026-08-02",
    })
    r.update(kw)
    return r


KEYS = {("t/a.jpg", "e/b.jpg")}


@pytest.mark.parametrize("kw", [
    {"human_decision": "", "final_disposition": ""},          # pending
    {"human_decision": "uncertain"},                          # non-terminal decision
    {"final_disposition": "needs_secondary_review"},          # non-terminal disposition
    {"human_decision": "clearly_different", "final_disposition": ""},
    {"human_decision": "", "final_disposition": "keep"},
])
def test_non_terminal_states_resolve_nothing(tmp_path, kw):
    out = summarize_near_review(_write(tmp_path, [_row(**kw)]), KEYS)
    assert out["resolved"] == 0
    assert out["unresolved"] == 1


def test_unknown_vocabulary_resolves_nothing(tmp_path):
    out = summarize_near_review(_write(tmp_path, [_row(human_decision="looks_ok")]), KEYS)
    assert out["resolved"] == 0
    assert out["invalid"] == 1


def test_exclusion_not_propagated_resolves_nothing(tmp_path):
    row = _row(human_decision="same_source_image", final_disposition="exclude_evaluation")
    out = summarize_near_review(_write(tmp_path, [row]), KEYS)
    assert out["resolved"] == 0
    assert out["invalid"] == 1
    assert out["unresolved"] == 1


def test_propagated_exclusion_resolves(tmp_path):
    row = _row(human_decision="same_source_image", final_disposition="exclude_evaluation")
    excl = tmp_path / "excl.csv"
    with open(excl, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["training_relative_path",
                                           "evaluation_relative_path"],
                           lineterminator="\n")
        w.writeheader()
        w.writerow({"training_relative_path": "t/a.jpg",
                    "evaluation_relative_path": "e/b.jpg"})
    out = summarize_near_review(_write(tmp_path, [row]), KEYS, excl)
    assert out["resolved"] == 1
    assert out["excluded"] == 1


def test_review_row_for_an_unflagged_pair_is_ignored(tmp_path):
    out = summarize_near_review(
        _write(tmp_path, [_row(training_relative_path="t/other.jpg")]), KEYS)
    assert out["resolved"] == 0
    assert out["unmatched"] == 1
    assert out["unresolved"] == 1  # the real flagged pair still has no decision


def test_flagged_pair_with_no_review_row_is_unresolved(tmp_path):
    out = summarize_near_review(_write(tmp_path, []),
                                KEYS | {("t/c.jpg", "e/d.jpg")})
    assert out["resolved"] == 0
    assert out["unresolved"] == 2


def test_missing_review_file_resolves_nothing(tmp_path):
    out = summarize_near_review(tmp_path / "absent.csv", KEYS)
    assert out["resolved"] == 0
