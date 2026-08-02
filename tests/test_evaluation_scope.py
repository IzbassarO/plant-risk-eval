"""Arthropod-pest evaluation scope: diagnosis-eligible, action/harm out of scope.

Spider mites are arthropod pests, not plant pathogens. The two dataset classes
below stay fully classifiable at diagnosis level -- their images and manifest
rows are untouched -- but they must never reach a *plant-disease* action metric
or a risk-weighted disease metric.

See reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md and configs/evaluation_scope.yaml.
"""
from __future__ import annotations

import pytest

from ica26.evaluation import harm
from ica26.evaluation.action_metrics import action_accuracy, project_labels
from ica26.evaluation.scope import (
    SCOPE_LAYERS,
    EvaluationScope,
    ScopeEntry,
    load_scope,
    validate_scope,
)
from ica26.mapping import schema, validation

SPIDER_MITE_CLASSES = [
    ("PlantDoc", "Tomato two spotted spider mites leaf"),
    ("PlantVillage", "Tomato___Spider_mites Two-spotted_spider_mite"),
]


@pytest.fixture(scope="module")
def repo_scope(request):
    root = request.config.rootpath
    return load_scope(root / "configs/evaluation_scope.yaml")


# --------------------------------------------------------------------------- #
# The shipped config records exactly the confirmed decision.
# --------------------------------------------------------------------------- #
def test_repo_scope_is_valid(repo_root):
    res = validate_scope(repo_root / "configs/evaluation_scope.yaml")
    assert res.ok, res.summary()


@pytest.mark.parametrize("dataset,dataset_class", SPIDER_MITE_CLASSES)
def test_spider_mites_remain_diagnosis_eligible(repo_scope, dataset, dataset_class):
    assert repo_scope.include_diagnosis(dataset, dataset_class) is True


@pytest.mark.parametrize("dataset,dataset_class", SPIDER_MITE_CLASSES)
def test_spider_mites_out_of_action_and_risk_weighted_scope(repo_scope, dataset, dataset_class):
    assert repo_scope.include_action_evaluation(dataset, dataset_class) is False
    assert repo_scope.include_risk_weighted_evaluation(dataset, dataset_class) is False


@pytest.mark.parametrize("dataset,dataset_class", SPIDER_MITE_CLASSES)
def test_spider_mite_entries_carry_reason_and_policy(repo_scope, dataset, dataset_class):
    e = repo_scope.entry(dataset, dataset_class)
    assert e is not None
    assert e.exclusion_reason == "arthropod_pest_out_of_disease_scope"
    assert e.policy_reference == "reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md"


def test_scope_lists_exactly_the_two_arthropod_classes(repo_scope):
    assert repo_scope.out_of_scope("include_action_evaluation") == sorted(SPIDER_MITE_CLASSES)
    assert repo_scope.out_of_scope("include_risk_weighted_evaluation") == sorted(SPIDER_MITE_CLASSES)
    assert repo_scope.out_of_scope("include_diagnosis") == []


# --------------------------------------------------------------------------- #
# Default posture is inclusive; only recorded classes are narrowed.
# --------------------------------------------------------------------------- #
def test_unlisted_class_is_in_scope_everywhere(repo_scope):
    for layer in SCOPE_LAYERS:
        assert getattr(repo_scope, layer)("PlantDoc", "Corn rust leaf") is True


def test_missing_config_yields_a_fully_inclusive_scope(tmp_path):
    s = load_scope(tmp_path / "absent.yaml")
    assert len(s) == 0
    assert s.include_action_evaluation("PlantDoc", "anything") is True


def test_entry_that_narrows_nothing_is_flagged():
    s = EvaluationScope([ScopeEntry(
        dataset="D", dataset_class="C", exclusion_reason="r", policy_reference="p")])
    res = validate_scope(s)
    assert res.ok  # a warning, not an error
    assert any("narrows nothing" in w.message for w in res.warnings)


def test_entry_without_provenance_is_rejected():
    s = EvaluationScope([ScopeEntry(dataset="D", dataset_class="C",
                                    include_action_evaluation=False)])
    res = validate_scope(s)
    assert not res.ok
    assert any("exclusion_reason" in e.message for e in res.errors)
    assert any("policy_reference" in e.message for e in res.errors)


# --------------------------------------------------------------------------- #
# Effect on metrics: excluded from action accuracy and from harm.
# --------------------------------------------------------------------------- #
def _mite_mapping_df():
    """An APPROVED mite row -- the adversarial case the scope filter must stop.

    If scope were enforced only by "the row is not approved", approving this row
    later would silently pull the pest class into disease-action metrics.
    """
    mite = schema.empty_row(dataset="PlantDoc",
                            dataset_class="Tomato two spotted spider mites leaf",
                            canonical_crop="tomato",
                            canonical_disease="twospotted spider mite")
    mite.update({
        "pathogen_name": "PLACEHOLDER", "pathogen_type": "mite",
        "action_class": "monitor", "action_summary": "PLACEHOLDER",
        "source_name": "PLACEHOLDER", "source_url": "https://example.org/p",
        "source_identifier": "PLACEHOLDER", "evidence_summary": "PLACEHOLDER",
        "evidence_checked_at": "2026-07-28", "mapping_confidence": "medium",
        "review_status": "approved",
    })
    disease = schema.empty_row(dataset="PlantDoc", dataset_class="Corn rust leaf",
                               canonical_crop="corn", canonical_disease="common rust")
    disease.update({
        "pathogen_name": "PLACEHOLDER", "pathogen_type": "fungal",
        "action_class": "fungicide", "action_summary": "PLACEHOLDER",
        "source_name": "PLACEHOLDER", "source_url": "https://example.org/p",
        "source_identifier": "PLACEHOLDER", "evidence_summary": "PLACEHOLDER",
        "evidence_checked_at": "2026-07-28", "mapping_confidence": "high",
        "review_status": "approved",
    })
    return schema.new_template([mite, disease])


def test_scope_drops_an_approved_mite_row_from_the_action_lookup(repo_scope):
    df = _mite_mapping_df()
    unscoped = validation.action_lookup(df, require_approved=True)
    assert ("PlantDoc", "Tomato two spotted spider mites leaf") in unscoped

    scoped = validation.action_lookup(df, require_approved=True, scope=repo_scope)
    assert ("PlantDoc", "Tomato two spotted spider mites leaf") not in scoped
    assert ("PlantDoc", "Corn rust leaf") in scoped


def test_mite_samples_are_excluded_from_action_accuracy(repo_scope):
    lut = validation.action_lookup(_mite_mapping_df(), require_approved=True,
                                   scope=repo_scope)
    y = ["Corn rust leaf", "Tomato two spotted spider mites leaf"]
    out = action_accuracy(y, y, "PlantDoc", lut)
    assert out["n_total"] == 2
    assert out["n_included"] == 1      # only the disease sample is scored
    assert out["n_excluded"] == 1      # the pest sample is dropped, not counted wrong
    assert out["action_accuracy"] == 1.0


def test_mite_samples_are_excluded_from_risk_weighted_harm(repo_scope):
    df = _mite_mapping_df()
    lut = validation.action_lookup(df, require_approved=True)
    risk_lut = repo_scope.filter_risk_weighted_lookup(lut)
    y = ["Corn rust leaf", "Tomato two spotted spider mites leaf"]
    true_actions = project_labels(y, "PlantDoc", risk_lut)
    pred_actions = project_labels(y, "PlantDoc", risk_lut)
    out = harm.harm_weighted_error(true_actions, pred_actions,
                                   harm.EXAMPLE_DEV_HARM_MATRIX)
    assert out["n_included"] == 1
    assert out["n_excluded"] == 1


def test_diagnosis_labels_are_never_removed(repo_scope, repo_root):
    """Scope is an evaluation decision: no manifest row disappears."""
    import csv

    for dataset, dataset_class, manifest in [
        ("PlantDoc", "Tomato two spotted spider mites leaf",
         "data/manifests/plantdoc_manifest.csv"),
        ("PlantVillage", "Tomato___Spider_mites Two-spotted_spider_mite",
         "data/manifests/plantvillage_manifest.csv"),
    ]:
        with open(repo_root / manifest, newline="", encoding="utf-8") as fh:
            n = sum(1 for r in csv.DictReader(fh) if r["class_label"] == dataset_class)
        assert n > 0, f"{dataset_class} vanished from {manifest}"
        assert repo_scope.include_diagnosis(dataset, dataset_class) is True
