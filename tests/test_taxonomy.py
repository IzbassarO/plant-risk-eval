"""Action-taxonomy validation."""
from __future__ import annotations

from ica26.config import validate_taxonomy
from ica26.schemas import ACTION_CLASSES


def test_repo_taxonomy_is_valid():
    res = validate_taxonomy("configs/action_taxonomy.yaml")
    assert res.ok, res.summary()


def test_taxonomy_requires_exactly_four_in_order():
    good = {"action_classes": [{"name": a, "description": "d"} for a in ACTION_CLASSES]}
    assert validate_taxonomy(good).ok


def test_taxonomy_rejects_wrong_set():
    bad = {"action_classes": [{"name": a, "description": "d"} for a in ("fungicide", "monitor")]}
    assert not validate_taxonomy(bad).ok


def test_taxonomy_rejects_missing_description():
    bad = {"action_classes": [{"name": a, "description": ""} for a in ACTION_CLASSES]}
    assert not validate_taxonomy(bad).ok


def test_taxonomy_rejects_forbidden_class():
    names = ("fungicide", "copper_sanitation", "remove_vector", "abiotic_correction")
    bad = {"action_classes": [{"name": a, "description": "d"} for a in names]}
    assert not validate_taxonomy(bad).ok
