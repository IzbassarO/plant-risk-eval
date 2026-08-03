"""Fail-closed mapping readiness (R2B.1 Finding 1).

The audit's exploit was that mapping readiness was a *negative* test —
``needs_review == 0`` — plus "a row exists for this class". Both go green for
reasons that have nothing to do with a human having decided anything: rename the
status, or add an empty row. These tests fix the exploit in place, so it cannot
come back as a refactor.

Nothing here approves a mapping. Every fixture is synthetic.
"""
from __future__ import annotations

import pytest

from ica26.governance.mapping import (
    MAPPING_READINESS_SCHEMA,
    TERMINAL_STATUSES,
    evaluate_mapping_readiness,
    is_placeholder,
)

EXPECTED = ("Alpha leaf", "Beta leaf", "Gamma leaf")


def _row(cls, **over):
    """A fully valid approved disease row. Overridden per test to break one thing."""
    row = {
        "dataset": "TestSet", "dataset_class": cls,
        "canonical_crop": "alpha", "canonical_disease": "alpha blight",
        "pathogen_name": "Alphaspora test", "pathogen_type": "fungal",
        "action_class": "fungicide",
        "action_summary": "Apply a protectant fungicide on the documented schedule.",
        "source_name": "Test Extension Service",
        "source_url": "https://example.org/alpha-blight",
        "source_identifier": "alpha-blight-1",
        "evidence_summary": "The cited guideline recommends a protectant fungicide.",
        "evidence_checked_at": "2026-07-28",
        "mapping_confidence": "high", "review_status": "approved",
        "review_notes": "reviewed against the cited guideline",
        "reviewer": "human_reviewer_1", "reviewed_at": "2026-08-02T21:10:00+05:00",
    }
    row.update(over)
    return row


def _all_valid():
    return [_row(c) for c in EXPECTED]


def _evaluate(rows, expected=EXPECTED, **kw):
    return evaluate_mapping_readiness(rows, dataset="TestSet",
                                      expected_classes=expected, **kw)


# --------------------------------------------------------------------------- #
# The baseline must be reachable, or every test below proves nothing
# --------------------------------------------------------------------------- #
def test_a_fully_valid_table_is_ready():
    r = _evaluate(_all_valid())
    assert r.satisfied, r.detail()
    assert r.approved_classes == 3 and r.covered_classes == 3
    assert r.schema == MAPPING_READINESS_SCHEMA
    assert not (r.missing or r.unexpected or r.duplicated or r.nonterminal or r.invalid)


def test_terminal_statuses_are_an_allow_list_not_a_deny_list():
    assert TERMINAL_STATUSES == ("approved", "excluded")


# --------------------------------------------------------------------------- #
# The reported exploits
# --------------------------------------------------------------------------- #
def test_pending_rows_cannot_pass():
    rows = _all_valid()
    rows[0]["review_status"] = "pending"
    r = _evaluate(rows)
    assert not r.satisfied
    assert any("Alpha leaf" in n and "not terminal" in n for n in r.nonterminal)


def test_needs_review_rows_cannot_pass():
    rows = _all_valid()
    rows[1]["review_status"] = "needs_review"
    r = _evaluate(rows)
    assert not r.satisfied and r.covered_classes == 2


@pytest.mark.parametrize("renamed", [
    "pending_review", "in_review", "under_review", "reviewed?", "APPROVED_PENDING",
    "awaiting_approval", "provisionally_approved", "approved_pending_evidence",
])
def test_a_renamed_nonterminal_status_cannot_pass(renamed):
    """The exploit: `needs_review == 0` goes green when the status is renamed."""
    rows = _all_valid()
    rows[0]["review_status"] = renamed
    r = _evaluate(rows)
    assert not r.satisfied
    assert not [x for x in rows if x["review_status"] == "needs_review"]  # the old test passes
    assert any("not terminal" in n for n in r.nonterminal)


@pytest.mark.parametrize("blank", ["", "   ", "n/a", "N/A", "none", "NULL", "TBD", "-", "?"])
def test_blank_null_and_placeholder_statuses_cannot_pass(blank):
    rows = _all_valid()
    rows[2]["review_status"] = blank
    r = _evaluate(rows)
    assert not r.satisfied
    assert any("Gamma leaf" in n for n in r.nonterminal)


def test_a_missing_status_key_cannot_pass():
    rows = _all_valid()
    del rows[0]["review_status"]
    assert not _evaluate(rows).satisfied


def test_a_none_status_cannot_pass():
    rows = _all_valid()
    rows[0]["review_status"] = None
    assert not _evaluate(rows).satisfied


def test_a_bare_row_naming_a_class_is_not_coverage():
    """The PlantVillage exploit: existence counted as coverage."""
    rows = [{"dataset": "TestSet", "dataset_class": c} for c in EXPECTED]
    r = _evaluate(rows)
    assert not r.satisfied
    assert r.covered_classes == 0
    assert len(r.nonterminal) == 3


def test_duplicated_class_rows_cannot_pass():
    rows = _all_valid() + [_row("Alpha leaf")]
    r = _evaluate(rows)
    assert not r.satisfied
    assert "Alpha leaf" in r.duplicated


def test_a_duplicate_cannot_be_used_to_overwrite_a_bad_decision():
    """First row pending, second row approved: the class must still block."""
    rows = [_row("Alpha leaf", review_status="pending"), _row("Alpha leaf"),
            _row("Beta leaf"), _row("Gamma leaf")]
    r = _evaluate(rows)
    assert not r.satisfied
    assert "Alpha leaf" in r.duplicated


def test_partial_coverage_cannot_pass():
    r = _evaluate([_row("Alpha leaf"), _row("Beta leaf")])
    assert not r.satisfied
    assert r.missing == ("Gamma leaf",)


def test_an_empty_table_cannot_pass():
    r = _evaluate([])
    assert not r.satisfied and len(r.missing) == 3


def test_an_empty_expected_set_cannot_pass():
    """No denominator is not the same as full coverage."""
    assert not _evaluate(_all_valid(), expected=()).satisfied


def test_unexpected_classes_cannot_silently_count():
    rows = _all_valid() + [_row("Delta leaf")]
    r = _evaluate(rows)
    assert not r.satisfied
    assert r.unexpected == ("Delta leaf",)


def test_an_unexpected_class_cannot_substitute_for_a_missing_one():
    """Equal row count, wrong identities -- the same shape as the forged tables."""
    rows = [_row("Alpha leaf"), _row("Beta leaf"), _row("Delta leaf")]
    r = _evaluate(rows)
    assert len(rows) == len(EXPECTED)          # counts agree exactly
    assert not r.satisfied
    assert r.missing == ("Gamma leaf",) and r.unexpected == ("Delta leaf",)


def test_a_versioned_allow_list_admits_an_extra_class_explicitly():
    rows = _all_valid() + [_row("Delta leaf")]
    r = _evaluate(rows, allowed_extra_classes=("Delta leaf",))
    assert r.satisfied, r.detail()


def test_blank_dataset_class_is_invalid():
    rows = _all_valid() + [_row("   ")]
    r = _evaluate(rows)
    assert not r.satisfied
    assert any("placeholder dataset_class" in x for x in r.invalid)


def test_rows_for_another_dataset_are_ignored():
    rows = _all_valid() + [_row("Whatever", dataset="OtherSet", review_status="pending")]
    assert _evaluate(rows).satisfied


# --------------------------------------------------------------------------- #
# The evidence gate on an approved row
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", [
    "pathogen_type", "action_summary", "source_name", "source_url",
    "source_identifier", "evidence_summary", "evidence_checked_at",
])
def test_an_approved_row_missing_evidence_cannot_pass(field):
    rows = _all_valid()
    rows[0][field] = ""
    r = _evaluate(rows)
    assert not r.satisfied
    assert any(field in x for x in r.invalid)


@pytest.mark.parametrize("token", ["TBD", "n/a", "none", "placeholder", "TODO", "-"])
def test_placeholder_evidence_is_not_evidence(token):
    rows = _all_valid()
    rows[0]["evidence_summary"] = token
    r = _evaluate(rows)
    assert not r.satisfied
    assert any("evidence_summary" in x for x in r.invalid)


def test_an_approved_row_without_a_target_cannot_pass():
    rows = _all_valid()
    rows[0]["action_class"] = ""
    r = _evaluate(rows)
    assert not r.satisfied
    assert any("no action target" in x or "action_class" in x for x in r.invalid)


@pytest.mark.parametrize("target", ["abiotic_correction", "spray_something",
                                    "FUNGICIDE", "fungicide ", "monitor_closely"])
def test_a_target_outside_the_approved_vocabulary_cannot_pass(target):
    rows = _all_valid()
    rows[0]["action_class"] = target
    r = _evaluate(rows)
    if target == "fungicide ":
        assert r.satisfied            # whitespace only; the value is still 'fungicide'
    else:
        assert not r.satisfied
        assert any("forbidden" in x or "outside the approved vocabulary" in x
                   for x in r.invalid)


def test_the_candidate_column_is_accepted_when_action_class_is_absent():
    """The review table proposes in `candidate_action_class`; both are read."""
    rows = [_row(c) for c in EXPECTED]
    for r_ in rows:
        r_["candidate_action_class"] = r_.pop("action_class")
    assert _evaluate(rows).satisfied


@pytest.mark.parametrize("field", ["reviewer", "reviewed_at"])
def test_an_approved_row_without_attribution_cannot_pass(field):
    rows = _all_valid()
    rows[0][field] = ""
    r = _evaluate(rows)
    assert not r.satisfied
    assert any(field in x for x in r.invalid)


@pytest.mark.parametrize("stamp", ["tomorrow", "2026-08-02T21:10:00",
                                   "2099-01-01T00:00:00+00:00", "2026-02-30T00:00:00+00:00"])
def test_an_invalid_review_timestamp_cannot_pass(stamp):
    rows = _all_valid()
    rows[0]["reviewed_at"] = stamp
    assert not _evaluate(rows).satisfied


# --------------------------------------------------------------------------- #
# Healthy exemption, exclusions, and scope
# --------------------------------------------------------------------------- #
def test_a_healthy_row_needs_the_policy_citation():
    healthy = _row("Alpha leaf", canonical_disease="healthy", action_class="monitor",
                   pathogen_name="", pathogen_type="",
                   source_identifier="", review_notes="approved")
    r = _evaluate([healthy, _row("Beta leaf"), _row("Gamma leaf")])
    assert not r.satisfied
    assert any("policy:healthy-monitor-v1" in x for x in r.invalid)


def test_a_healthy_row_citing_the_policy_passes():
    healthy = _row("Alpha leaf", canonical_disease="healthy", action_class="monitor",
                   pathogen_name="", pathogen_type="",
                   source_identifier="policy:healthy-monitor-v1")
    assert _evaluate([healthy, _row("Beta leaf"), _row("Gamma leaf")]).satisfied


def test_a_healthy_row_may_not_be_approved_into_a_treatment():
    healthy = _row("Alpha leaf", canonical_disease="healthy", action_class="fungicide",
                   pathogen_name="", pathogen_type="",
                   source_identifier="policy:healthy-monitor-v1")
    r = _evaluate([healthy, _row("Beta leaf"), _row("Gamma leaf")])
    assert not r.satisfied
    assert any("must map to 'monitor'" in x for x in r.invalid)


def test_an_excluded_row_is_terminal_but_is_not_an_approval():
    rows = [_row("Alpha leaf", review_status="excluded",
                 review_notes="out of disease scope; arthropod pest"),
            _row("Beta leaf"), _row("Gamma leaf")]
    r = _evaluate(rows)
    assert r.satisfied
    assert r.approved_classes == 2 and r.excluded_classes == 1
    assert r.covered_classes == 3


def test_an_excluded_row_still_needs_a_reason_and_attribution():
    for broken in ({"review_notes": ""}, {"reviewer": ""}, {"reviewed_at": ""}):
        overrides = {"review_status": "excluded", "review_notes": "why", **broken}
        rows = [_row("Alpha leaf", **overrides), _row("Beta leaf"), _row("Gamma leaf")]
        assert not _evaluate(rows).satisfied, broken


def test_an_out_of_scope_class_may_not_be_approved_into_an_action():
    rows = _all_valid()
    r = _evaluate(rows, out_of_action_scope_classes=("Alpha leaf",))
    assert not r.satisfied
    assert any("out of action-evaluation scope" in x for x in r.invalid)


def test_an_out_of_scope_class_is_satisfied_by_an_explicit_exclusion():
    rows = [_row("Alpha leaf", review_status="excluded",
                 review_notes="arthropod pest, out of disease-action scope"),
            _row("Beta leaf"), _row("Gamma leaf")]
    assert _evaluate(rows, out_of_action_scope_classes=("Alpha leaf",)).satisfied


# --------------------------------------------------------------------------- #
# Reporting + binding
# --------------------------------------------------------------------------- #
def test_the_verdict_names_the_offending_identities():
    rows = [_row("Alpha leaf", review_status="pending"), _row("Beta leaf"),
            _row("Beta leaf"), _row("Delta leaf")]
    r = _evaluate(rows)
    assert "Gamma leaf" in r.missing
    assert "Beta leaf" in r.duplicated
    assert "Delta leaf" in r.unexpected
    assert any("Alpha leaf" in n for n in r.nonterminal)
    text = r.detail()
    assert "missing" in text and "duplicated" in text and "non-terminal" in text


def test_readiness_records_the_artifact_digest_it_judged():
    r = _evaluate(_all_valid(), artifact="data/mapping/x.csv", artifact_digest="a" * 64)
    assert r.as_dict()["artifact_digest"] == "a" * 64
    assert r.as_dict()["artifact"] == "data/mapping/x.csv"


@pytest.mark.parametrize("value,expected", [
    ("", True), ("   ", True), (None, True), ("n/a", True), ("N/A", True),
    ("None", True), ("null", True), ("TBD", True), ("todo", True), ("-", True),
    ("?", True), ("placeholder", True), ("unknown", True), ("pending", True),
    ("fungicide", False), ("Alpha leaf", False), ("0", False),
])
def test_placeholder_detection(value, expected):
    assert is_placeholder(value) is expected


# --------------------------------------------------------------------------- #
# The live tables
# --------------------------------------------------------------------------- #
def test_the_live_plantdoc_mapping_is_still_not_ready(repo_root):
    """17 rows are genuinely undecided. This must not quietly become ready."""
    import csv

    with open(repo_root / "data/mapping/action_mapping_review.csv",
              newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(repo_root / "data/manifests/plantdoc_effective_manifest.csv",
              newline="", encoding="utf-8") as fh:
        classes = {r["class_label"] for r in csv.DictReader(fh)}
    r = evaluate_mapping_readiness(rows, dataset="PlantDoc", expected_classes=classes)
    assert not r.satisfied
    assert len(r.nonterminal) == 17
    assert r.approved_classes == 10 and r.excluded_classes == 1


def test_the_live_plantvillage_mapping_has_no_coverage(repo_root):
    import csv

    with open(repo_root / "data/mapping/action_mapping_review.csv",
              newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    with open(repo_root / "data/manifests/plantvillage_manifest.csv",
              newline="", encoding="utf-8") as fh:
        classes = {r["class_label"] for r in csv.DictReader(fh)}
    r = evaluate_mapping_readiness(rows, dataset="PlantVillage", expected_classes=classes)
    assert not r.satisfied
    assert r.covered_classes == 0
    assert len(r.missing) == len(classes) == 38
