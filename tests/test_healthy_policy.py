"""The narrow healthy-class evidence exemption (policy:healthy-monitor-v1).

A healthy class is a NEGATIVE diagnosis class: there is no pathogen to cite, so
the pathogen-specific half of the evidence gate is unsatisfiable by construction.
These tests pin the exemption to exactly that case and prove it neither leaks to
diseased rows nor lets a healthy row through on thin provenance.

See reports/HEALTHY_CLASS_ACTION_POLICY.md.
"""
from __future__ import annotations

import pytest

from ica26 import schemas
from ica26.mapping import schema, validation


POLICY = schemas.HEALTHY_POLICY_ID


def healthy_row(**overrides) -> dict:
    """A policy-compliant approved healthy row (no pathogen, no external URL)."""
    row = schema.empty_row(dataset="PlantDoc", dataset_class="Apple leaf",
                           canonical_crop="apple", canonical_disease="healthy")
    row.update({
        "action_class": "monitor",
        "action_summary": "Healthy tissue - no intervention indicated.",
        "source_name": "(definitional: healthy class, no pathogen)",
        "source_identifier": POLICY,
        "evidence_summary": "No disease pathogen present; monitor only.",
        "evidence_checked_at": "2026-07-28",
        "mapping_confidence": "high",
        "review_status": "approved",
        "review_notes": f"Approved under {POLICY}.",
    })
    row.update(overrides)
    return row


def diseased_row(**overrides) -> dict:
    row = schema.empty_row(dataset="PlantDoc", dataset_class="Corn rust leaf",
                           canonical_crop="corn", canonical_disease="common rust")
    row.update({
        "pathogen_name": "PLACEHOLDER",
        "pathogen_type": "fungal",
        "action_class": "fungicide",
        "action_summary": "PLACEHOLDER action summary",
        "source_name": "PLACEHOLDER source",
        "source_url": "https://example.org/placeholder",
        "source_identifier": "PLACEHOLDER-ID",
        "evidence_summary": "PLACEHOLDER evidence summary",
        "evidence_checked_at": "2026-07-28",
        "mapping_confidence": "high",
        "review_status": "approved",
    })
    row.update(overrides)
    return row


def errors_of(row: dict) -> list[str]:
    res = validation.validate_mapping(schema.new_template([row]))
    return [i.message for i in res.errors]


# --------------------------------------------------------------------------- #
# 1. A valid healthy + monitor row passes without pathogen-specific evidence.
# --------------------------------------------------------------------------- #
def test_healthy_monitor_row_passes_without_pathogen_evidence():
    row = healthy_row()
    assert row["pathogen_name"] == "" and row["pathogen_type"] == ""
    assert row["source_url"] == ""
    assert errors_of(row) == []


def test_healthy_row_may_cite_the_policy_in_review_notes_only():
    row = healthy_row(source_identifier="", review_notes=f"see {POLICY}")
    assert errors_of(row) == []


# --------------------------------------------------------------------------- #
# 2. Healthy + any non-monitor action fails.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action", ["fungicide", "copper_sanitation", "remove_vector"])
def test_healthy_with_non_monitor_action_fails(action):
    errs = errors_of(healthy_row(action_class=action))
    assert any("must map to action_class 'monitor'" in e for e in errs)


# --------------------------------------------------------------------------- #
# 3. The exemption does not reach a diseased class.
# --------------------------------------------------------------------------- #
def test_exemption_does_not_apply_to_a_diseased_class():
    # Same thin provenance that is fine for healthy, on a diseased row.
    row = diseased_row(pathogen_name="", pathogen_type="", source_url="",
                       source_identifier=POLICY, action_class="monitor")
    errs = errors_of(row)
    for missing in ("pathogen_type", "source_url"):
        assert any(f"missing required evidence field '{missing}'" in e for e in errs)


@pytest.mark.parametrize("disease", ["unknown", "abiotic", "twospotted spider mite", ""])
def test_exemption_does_not_apply_to_ambiguous_pest_or_unknown_classes(disease):
    row = healthy_row(canonical_disease=disease)
    assert errors_of(row), f"canonical_disease={disease!r} must not get the exemption"


# --------------------------------------------------------------------------- #
# 4. Diseased rows keep the ORIGINAL evidence requirements.
# --------------------------------------------------------------------------- #
def test_diseased_row_still_requires_full_evidence():
    assert errors_of(diseased_row()) == []
    for fld in schemas.EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL:
        errs = errors_of(diseased_row(**{fld: ""}))
        assert errs, f"blanking '{fld}' on a diseased row must fail"


# --------------------------------------------------------------------------- #
# 5. A healthy row without a policy citation or evidence prose fails.
# --------------------------------------------------------------------------- #
def test_healthy_without_policy_reference_fails():
    errs = errors_of(healthy_row(source_identifier="", review_notes=""))
    assert any(POLICY in e and "must cite" in e for e in errs)


@pytest.mark.parametrize("fld", schemas.HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL)
def test_healthy_missing_required_field_fails(fld):
    assert errors_of(healthy_row(**{fld: ""}))


def test_healthy_row_may_not_fabricate_a_pathogen():
    errs = errors_of(healthy_row(pathogen_name="Venturia inaequalis"))
    assert any("no pathogen and none may be fabricated" in e for e in errs)
    errs = errors_of(healthy_row(pathogen_type="fungal"))
    assert any("no pathogen and none may be fabricated" in e for e in errs)


def test_healthy_exemption_only_applies_to_approved_rows():
    # A needs_review healthy row is not evaluated by the gate at all...
    assert errors_of(healthy_row(review_status="needs_review")) == []
    # ...but the moment it is approved, the policy must be satisfied.
    assert errors_of(healthy_row(review_status="approved", review_notes="",
                                 source_identifier=""))


# --------------------------------------------------------------------------- #
# 6. The four-class taxonomy is unchanged.
# --------------------------------------------------------------------------- #
def test_action_taxonomy_unchanged():
    assert schemas.ACTION_CLASSES == (
        "fungicide", "copper_sanitation", "remove_vector", "monitor")
    assert "abiotic_correction" in schemas.FORBIDDEN_ACTION_CLASSES
    assert schemas.HEALTHY_ACTION_CLASS in schemas.ACTION_CLASSES


# --------------------------------------------------------------------------- #
# The shipped review file must actually satisfy the policy.
# --------------------------------------------------------------------------- #
def test_repository_healthy_rows_satisfy_the_policy(repo_root):
    df = validation.read_mapping(repo_root / "data/mapping/action_mapping_approved.csv")
    healthy = df[df["canonical_disease"].str.strip().str.lower() == "healthy"]
    assert len(healthy) == 10
    assert set(healthy["action_class"]) == {"monitor"}
    assert set(healthy["pathogen_name"]) == {""}
    assert set(healthy["pathogen_type"]) == {""}
    assert set(healthy["source_url"]) == {""}
    assert all(validation.cites_healthy_policy(r) for _, r in healthy.iterrows())
    assert validation.validate_mapping(df).ok
