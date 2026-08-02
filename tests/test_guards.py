"""Durable training-source guard: Master Plant Disease is never trainable."""
from __future__ import annotations

import pytest

from ica26.datasets.guards import (
    TrainingDataPolicyError, assert_trainable, is_forbidden_training_source,
)


@pytest.mark.parametrize("name", [
    "master",
    "Master",
    "Master Plant Disease Dataset",
    "master_plant_disease",
    "harisri2005/plant-disease-processed",
    "plant-disease-processed",
])
def test_master_is_forbidden(name):
    assert is_forbidden_training_source(name)
    with pytest.raises(TrainingDataPolicyError):
        assert_trainable(name)


@pytest.mark.parametrize("name", ["PlantVillage", "PlantDoc", "PlantWild", "Cassava", "FieldPlant"])
def test_allowed_datasets_are_trainable(name):
    assert not is_forbidden_training_source(name)
    assert_trainable(name)  # must not raise
