"""Review-packet regeneration must never destroy a human decision (AUD-EC-004).

Before this fix, `scripts/prepare_human_review.py` rebuilt the review CSV with
every decision field blank and unconditionally rewrote a header-only
reviewed-exclusions file. Running a nominally reproducible command therefore
erased adjudications and their provenance.

Regeneration now merges prior decisions back by CANONICAL IDENTITY and fails
closed if a decided pair's identity drifted.
"""
from __future__ import annotations

import importlib.util
import sys

import pytest


def _load_module(repo_root):
    path = repo_root / "scripts" / "prepare_human_review.py"
    spec = importlib.util.spec_from_file_location("prepare_human_review", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("prepare_human_review", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def phr(repo_root):
    return _load_module(repo_root)


def _fresh(pair_id="ndp-01", **over):
    """A freshly-derived row: authoritative identity, blank decisions."""
    row = {
        "pair_id": pair_id,
        "training_dataset": "PlantVillage", "training_relative_path": "t/a.jpg",
        "training_class": "A", "training_sha256": "a" * 64,
        "evaluation_dataset": "PlantDoc", "evaluation_relative_path": "e/b.jpg",
        "evaluation_class": "B", "evaluation_sha256": "b" * 64,
        "phash_distance": "6", "contact_sheet": "reports/sheet_01.png",
        "human_decision": "", "decision_reason": "", "reviewer": "",
        "reviewed_at": "", "final_disposition": "",
    }
    row.update(over)
    return row


def _decided(pair_id="ndp-01", **over):
    decision = {
        "human_decision": "clearly_different",
        "decision_reason": "visually distinct source images",
        "reviewer": "human_reviewer_1",
        "reviewed_at": "2026-08-02T21:10:00+05:00",
        "final_disposition": "keep",
    }
    decision.update(over)
    return _fresh(pair_id, **decision)


# --------------------------------------------------------------------------- #
# Preservation
# --------------------------------------------------------------------------- #
def test_decisions_survive_regeneration(phr):
    merged, report = phr.merge_near_review([_fresh()], [_decided()])
    assert merged[0]["human_decision"] == "clearly_different"
    assert merged[0]["final_disposition"] == "keep"
    assert merged[0]["reviewer"] == "human_reviewer_1"
    assert merged[0]["reviewed_at"] == "2026-08-02T21:10:00+05:00"
    assert merged[0]["decision_reason"] == "visually distinct source images"
    assert report["preserved"] == ["ndp-01"]
    assert report["new"] == [] and report["dropped"] == []


def test_pair_id_is_preserved_not_reassigned_by_row_order(phr):
    """pair_id is a label; re-ordering must not relabel a decided pair."""
    fresh = [_fresh("ndp-01", training_relative_path="t/z.jpg"), _fresh("ndp-02")]
    existing = [_decided("ndp-07")]
    merged, _ = phr.merge_near_review(fresh, existing)
    by_path = {r["training_relative_path"]: r for r in merged}
    assert by_path["t/a.jpg"]["pair_id"] == "ndp-07"          # kept its identity label
    assert by_path["t/a.jpg"]["human_decision"] == "clearly_different"


def test_new_pair_is_added_undecided(phr):
    fresh = [_fresh("x", training_relative_path="t/a.jpg"),
             _fresh("y", training_relative_path="t/new.jpg")]
    merged, report = phr.merge_near_review(fresh, [_decided("ndp-01")])
    new = [r for r in merged if r["training_relative_path"] == "t/new.jpg"][0]
    assert new["human_decision"] == "" and new["final_disposition"] == ""
    assert len(report["new"]) == 1
    assert report["preserved"] == ["ndp-01"]


def test_new_pair_id_does_not_reuse_an_existing_label(phr):
    fresh = [_fresh("a", training_relative_path="t/a.jpg"),
             _fresh("b", training_relative_path="t/new.jpg")]
    merged, report = phr.merge_near_review(fresh, [_decided("ndp-16")])
    assert report["new"] == ["ndp-17"]
    assert {r["pair_id"] for r in merged} == {"ndp-16", "ndp-17"}


def test_contact_sheet_repaging_is_not_identity_drift(phr):
    """Re-paging sheets is cosmetic and must not invalidate a decision."""
    merged, report = phr.merge_near_review(
        [_fresh(contact_sheet="reports/sheet_09.png")], [_decided()])
    assert merged[0]["human_decision"] == "clearly_different"
    assert merged[0]["contact_sheet"] == "reports/sheet_09.png"
    assert report["preserved"] == ["ndp-01"]


# --------------------------------------------------------------------------- #
# Fail-closed on identity drift
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field,value", [
    ("training_sha256", "c" * 64),
    ("evaluation_sha256", "d" * 64),
    ("phash_distance", "3"),
    ("training_class", "OTHER"),
    ("evaluation_class", "OTHER"),
    ("training_dataset", "OTHER"),
    # R1-HIGH-002: BOTH relative paths are identity. Previously a path change
    # produced a dropped row plus a blank new row instead of raising.
    ("training_relative_path", "t/moved.jpg"),
    ("evaluation_relative_path", "e/moved.jpg"),
])
def test_identity_drift_on_a_decided_pair_fails_closed(phr, field, value):
    with pytest.raises(phr.HumanDecisionDrift):
        phr.merge_near_review([_fresh(**{field: value})], [_decided()])


@pytest.mark.parametrize("field,value", [
    ("training_relative_path", "t/moved.jpg"),
    ("evaluation_relative_path", "e/moved.jpg"),
])
def test_path_drift_writes_nothing(phr, field, value, tmp_path):
    """The decision must not silently reappear as a dropped + blank pair."""
    with pytest.raises(phr.HumanDecisionDrift) as e:
        phr.merge_near_review([_fresh(**{field: value})], [_decided()])
    assert "Nothing was written" in str(e.value)


def test_identity_drift_on_an_undecided_pair_is_fine(phr):
    """Nothing to protect: an undecided row can be refreshed freely."""
    merged, report = phr.merge_near_review(
        [_fresh(training_sha256="c" * 64)], [_fresh()])
    assert merged[0]["training_sha256"] == "c" * 64
    assert report["drift"] == []


# --------------------------------------------------------------------------- #
# Removed pairs are reported, never silently dropped
# --------------------------------------------------------------------------- #
def test_removing_a_decided_pair_fails_closed(phr):
    """R1-HIGH-002: losing a decision must stop the run, not be logged."""
    with pytest.raises(phr.HumanDecisionDrift) as e:
        phr.merge_near_review([], [_decided()])
    assert "ndp-01" in str(e.value)


def test_removing_an_undecided_pair_is_only_reported(phr):
    merged, report = phr.merge_near_review([], [_fresh()])
    assert merged == []
    assert len(report["dropped"]) == 1
    assert report["dropped"][0]["had_decision"] is False


# --------------------------------------------------------------------------- #
# The destructive path exists but is explicit
# --------------------------------------------------------------------------- #
def test_reset_flag_discards_decisions_explicitly(phr):
    merged, report = phr.merge_near_review([_fresh()], [_decided()], reset=True)
    assert merged[0]["human_decision"] == ""
    assert report["reset"] is True
    assert report["preserved"] == []


def test_reset_is_not_the_default(phr):
    _, report = phr.merge_near_review([_fresh()], [_decided()])
    assert report["reset"] is False


# --------------------------------------------------------------------------- #
# Reviewed exclusions
# --------------------------------------------------------------------------- #
def _excl(pair_id="ndp-01", t="t/a.jpg", e="e/b.jpg"):
    return {"pair_id": pair_id, "match_type": "near", "training_relative_path": t,
            "evaluation_relative_path": e, "phash_distance": "6",
            "human_decision": "same_source_image", "exclusion_reason": "same source",
            "reviewer": "human_reviewer_1", "reviewed_at": "2026-08-02T21:10:00+05:00",
            "source_review_file": "x.csv"}


def test_propagated_exclusion_survives_regeneration(phr):
    review = [_decided(human_decision="same_source_image",
                       final_disposition="exclude_evaluation")]
    kept, report = phr.merge_reviewed_exclusions(review, [_excl()])
    assert len(kept) == 1 and report["kept"] == 1
    assert kept[0]["exclusion_reason"] == "same source"
    assert report["missing_propagation"] == []


def test_exclusion_is_dropped_when_the_decision_is_no_longer_exclude(phr):
    kept, report = phr.merge_reviewed_exclusions([_decided()], [_excl()])
    assert kept == [] and len(report["dropped"]) == 1


def test_exclude_decision_without_a_record_is_reported(phr):
    review = [_decided(human_decision="same_source_image",
                       final_disposition="exclude_evaluation")]
    kept, report = phr.merge_reviewed_exclusions(review, [])
    assert kept == [] and report["missing_propagation"] == ["ndp-01"]


def test_regeneration_never_blanks_a_populated_exclusion_file(phr):
    """The old behaviour wrote a header-only file unconditionally."""
    review = [_decided(human_decision="same_source_image",
                       final_disposition="exclude_evaluation")]
    kept, _ = phr.merge_reviewed_exclusions(review, [_excl()])
    assert kept, "a still-valid exclusion record must survive regeneration"


# --------------------------------------------------------------------------- #
# The shipped repository state
# --------------------------------------------------------------------------- #
def test_repository_review_is_fully_decided_and_stable(phr, repo_root):
    import csv

    with open(repo_root / "data/exclusions/cross_dataset_near_duplicate_review.csv",
              newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 16
    assert all(r["canonical_pair_id"].startswith("near-") for r in rows)
    merged, report = phr.merge_near_review([dict(r, **{c: "" for c in phr.DECISION_COLUMNS})
                                            for r in rows], rows)
    assert len(report["preserved"]) == 16
    assert report["new"] == [] and report["dropped"] == []
    assert merged == rows, "a no-op regeneration must reproduce the file exactly"
