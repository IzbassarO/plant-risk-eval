"""Mapping schema + evidence-gate validation."""
from __future__ import annotations

import pandas as pd

from ica26.mapping import schema, validation
from ica26.mapping.crosswalk import normalize_crop, normalize_disease


def test_template_columns_exact():
    df = schema.new_template([])
    assert list(df.columns) == list(schema.MAPPING_COLUMNS)


def test_pending_row_is_valid(mapping_df):
    assert validation.validate_mapping(mapping_df).ok


def test_pending_row_has_no_action(mapping_df):
    assert str(mapping_df.loc[0, "action_class"]).strip() == ""
    assert mapping_df.loc[0, "review_status"] == "pending"


def test_approved_without_evidence_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "action_class"] = "remove_vector"
    bad.loc[0, "review_status"] = "approved"
    res = validation.validate_mapping(bad)
    assert not res.ok
    assert any("evidence" in i.message for i in res.errors)


def test_approved_with_full_evidence_passes(approved_row_with_evidence):
    df = schema.new_template([approved_row_with_evidence])
    assert validation.validate_mapping(df).ok


def test_unknown_action_class_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "action_class"] = "spray_something"
    assert not validation.validate_mapping(bad).ok


def test_forbidden_action_class_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "action_class"] = "abiotic_correction"
    res = validation.validate_mapping(bad)
    assert not res.ok
    assert any("forbidden" in i.message for i in res.errors)


def test_invalid_review_status_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "review_status"] = "totally_fine"
    assert not validation.validate_mapping(bad).ok


def test_bad_pathogen_type_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "pathogen_type"] = "space_fungus"
    assert not validation.validate_mapping(bad).ok


def test_empty_dataset_class_fails(mapping_df):
    bad = mapping_df.copy()
    bad.loc[0, "dataset_class"] = ""
    assert not validation.validate_mapping(bad).ok


def test_action_lookup_only_returns_approved(mapping_df, approved_row_with_evidence):
    df = pd.concat([mapping_df, schema.new_template([approved_row_with_evidence])], ignore_index=True)
    lut = validation.action_lookup(df, require_approved=True)
    # only the approved+evidence row appears
    assert lut == {("PlantDoc", "Corn rust leaf"): "fungicide"}


def test_status_counts(mapping_df):
    c = validation.status_counts(mapping_df)
    assert c["pending"] == 1 and c["approved"] == 0


def test_normalization_is_deterministic():
    assert normalize_crop("Tomato leaf late blight") == "tomato"
    assert normalize_crop("Bell_pepper leaf spot") == "pepper"
    assert normalize_crop("Corn Gray leaf spot") == "corn"
    assert normalize_crop("Something unknown") == ""  # never guesses
    assert normalize_disease("Apple leaf healthy") == "healthy"
