"""Review -> canonical transcription: candidate_action_class -> action_class.

The review CSV holds an author *proposal*; the canonical table holds a ratified
fact. These tests pin the one-way bridge between them: only an approved row
crosses, the four-class taxonomy is enforced, out-of-scope classes never cross,
and the human-review source is never written.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ica26.evaluation.scope import EvaluationScope, ScopeEntry
from ica26.mapping import review as R
from ica26.schemas import ACTION_CLASSES, MAPPING_COLUMNS

POLICY = "policy:healthy-monitor-v1"

REVIEW_COLUMNS = [c for c in MAPPING_COLUMNS if c != "action_class"] + [
    "candidate_action_class", "reviewer", "reviewed_at"]


def review_row(**overrides) -> dict:
    row = {c: "" for c in REVIEW_COLUMNS}
    row.update({
        "dataset": "PlantDoc", "dataset_class": "Corn rust leaf",
        "canonical_crop": "corn", "canonical_disease": "common rust",
        "pathogen_name": "PLACEHOLDER", "pathogen_type": "fungal",
        "candidate_action_class": "fungicide",
        "action_summary": "PLACEHOLDER", "source_name": "PLACEHOLDER",
        "source_url": "https://example.org/p", "source_identifier": "PLACEHOLDER",
        "evidence_summary": "PLACEHOLDER", "evidence_checked_at": "2026-07-28",
        "mapping_confidence": "high", "review_status": "approved",
        "reviewer": "human_reviewer_1", "reviewed_at": "2026-08-02T21:10:00+05:00",
    })
    row.update(overrides)
    return row


def healthy_review_row(**overrides) -> dict:
    return review_row(**{
        "dataset_class": "Apple leaf", "canonical_crop": "apple",
        "canonical_disease": "healthy", "pathogen_name": "", "pathogen_type": "",
        "candidate_action_class": "monitor", "source_url": "",
        "source_identifier": POLICY, "review_notes": f"Approved under {POLICY}.",
        **overrides,
    })


def df_of(*rows) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=REVIEW_COLUMNS)


def apply(*rows, scope=None):
    return R.apply_review(df_of(*rows), scope=scope, review_source="test.csv")


# --------------------------------------------------------------------------- #
# The transcription itself
# --------------------------------------------------------------------------- #
def test_approved_row_gets_its_candidate_ratified():
    out, res, summary = apply(review_row())
    assert res.ok, res.summary()
    assert len(out) == 1
    assert out.loc[0, "action_class"] == "fungicide"
    assert "candidate_action_class" not in out.columns
    assert summary["emitted_rows"] == 1


@pytest.mark.parametrize("status", ["needs_review", "pending", "excluded"])
def test_non_approved_rows_are_never_emitted(status):
    out, res, summary = apply(review_row(review_status=status))
    assert res.ok, res.summary()
    assert len(out) == 0
    assert summary["review_status_counts"][status] == 1


def test_healthy_approved_row_goes_through_the_healthy_policy():
    out, res, _ = apply(healthy_review_row())
    assert res.ok, res.summary()
    assert out.loc[0, "action_class"] == "monitor"
    assert out.loc[0, "policy_reference"] == POLICY


def test_healthy_row_failing_the_policy_blocks_the_whole_write():
    # healthy + fungicide is rejected by the canonical gate, not by this module.
    out, res, summary = apply(healthy_review_row(candidate_action_class="fungicide"))
    assert not res.ok
    assert summary["ok"] is False
    assert any("monitor" in e.message for e in res.errors)


def test_provenance_is_carried_into_the_canonical_row():
    out, res, _ = apply(review_row())
    assert res.ok
    assert out.loc[0, "reviewer"] == "human_reviewer_1"
    assert out.loc[0, "reviewed_at"] == "2026-08-02T21:10:00+05:00"
    assert out.loc[0, "review_source"] == "test.csv"
    assert out.loc[0, "review_source_row"] == "2"
    assert out.loc[0, "dataset"] == "PlantDoc"
    assert out.loc[0, "dataset_class"] == "Corn rust leaf"


# --------------------------------------------------------------------------- #
# Fail-closed behaviour
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action", ["abiotic_correction", "spray_something", ""])
def test_unsupported_action_fails_closed(action):
    out, res, _ = apply(review_row(candidate_action_class=action))
    assert not res.ok
    assert len(out) == 0


def test_action_vocabulary_is_the_four_classes():
    for action in ACTION_CLASSES:
        _, res, _ = apply(review_row(candidate_action_class=action,
                                     canonical_disease="common rust"
                                     if action != "monitor" else "common rust"))
        assert res.ok, f"{action}: {res.summary()}"


def test_unknown_review_status_fails_closed():
    _, res, _ = apply(review_row(review_status="looks_fine"))
    assert not res.ok
    assert any("unsupported review_status" in e.message for e in res.errors)


def test_blank_identity_fails_closed():
    _, res, _ = apply(review_row(dataset_class=""))
    assert not res.ok


def test_duplicate_identity_fails_closed():
    _, res, _ = apply(review_row(), review_row())
    assert not res.ok
    assert any("duplicate" in e.message for e in res.errors)


def test_review_input_carrying_action_class_is_rejected():
    df = df_of(review_row())
    df["action_class"] = "fungicide"
    _, res, _ = R.apply_review(df, review_source="test.csv")
    assert not res.ok
    assert any("must stay a candidate table" in e.message for e in res.errors)


def test_approved_row_missing_evidence_blocks_the_write():
    _, res, _ = apply(review_row(source_url=""))
    assert not res.ok
    assert any("evidence" in e.message for e in res.errors)


# --------------------------------------------------------------------------- #
# Scope interaction
# --------------------------------------------------------------------------- #
def _mite_scope() -> EvaluationScope:
    return EvaluationScope([ScopeEntry(
        dataset="PlantDoc", dataset_class="Tomato two spotted spider mites leaf",
        include_diagnosis=True, include_action_evaluation=False,
        include_risk_weighted_evaluation=False,
        exclusion_reason="arthropod_pest_out_of_disease_scope",
        policy_reference="reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md")])


def test_excluded_mite_row_is_simply_not_emitted():
    row = review_row(dataset_class="Tomato two spotted spider mites leaf",
                     canonical_disease="twospotted spider mite",
                     pathogen_type="mite", candidate_action_class="monitor",
                     review_status="excluded")
    out, res, _ = apply(row, scope=_mite_scope())
    assert res.ok, res.summary()
    assert len(out) == 0


def test_approved_but_out_of_scope_row_is_a_hard_error():
    row = review_row(dataset_class="Tomato two spotted spider mites leaf",
                     canonical_disease="twospotted spider mite",
                     pathogen_type="mite", candidate_action_class="monitor",
                     review_status="approved")
    out, res, summary = apply(row, scope=_mite_scope())
    assert not res.ok
    assert len(out) == 0
    assert any("out of\naction-evaluation scope" in e.message.replace(" ", " ")
               or "action-evaluation scope" in e.message for e in res.errors)
    assert summary["skipped_out_of_action_scope"] == [
        "PlantDoc/Tomato two spotted spider mites leaf"]


# --------------------------------------------------------------------------- #
# Determinism + the shipped artifact
# --------------------------------------------------------------------------- #
def test_output_is_sorted_and_deterministic():
    a = review_row(dataset_class="Zeta leaf", canonical_disease="common rust")
    b = review_row(dataset_class="Alpha leaf", canonical_disease="common rust")
    out1, res1, _ = apply(a, b)
    out2, res2, _ = apply(b, a)
    assert res1.ok and res2.ok
    assert list(out1["dataset_class"]) == ["Alpha leaf", "Zeta leaf"]
    pd.testing.assert_frame_equal(
        out1.drop(columns=["review_source_row"]),
        out2.drop(columns=["review_source_row"]),
    )


def test_shipped_canonical_mapping_matches_the_review_file(repo_root):
    from ica26.evaluation.scope import load_scope

    scope = load_scope(repo_root / "configs/evaluation_scope.yaml")
    review = R.read_review(repo_root / "data/mapping/action_mapping_review.csv")
    out, res, summary = R.apply_review(
        review, scope=scope,
        review_source="data/mapping/action_mapping_review.csv")
    assert res.ok, res.summary()
    assert summary["review_status_counts"]["approved"] == 10
    assert summary["review_status_counts"]["excluded"] == 1
    assert summary["review_status_counts"]["needs_review"] == 17
    assert summary["emitted_rows"] == 10
    assert summary["emitted_healthy_rows"] == 10
    assert summary["emitted_disease_rows"] == 0

    on_disk = pd.read_csv(repo_root / "data/mapping/action_mapping_approved.csv",
                          dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(out.reset_index(drop=True), on_disk)


def test_apply_never_writes_the_review_source(repo_root, tmp_path):
    import hashlib
    import subprocess
    import sys

    src = repo_root / "data/mapping/action_mapping_review.csv"
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts/apply_action_mapping_review.py"),
         "--out-csv", str(tmp_path / "out.csv"), "--out-json", str(tmp_path / "out.json")],
        cwd=str(repo_root), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
    assert (tmp_path / "out.csv").exists()
