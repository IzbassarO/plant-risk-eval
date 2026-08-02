"""Durable data-usage guards.

The Master Plant Disease Dataset must never be used as a training source: it
merges seven public sources (almost certainly including PlantVillage and the
evaluation sets), so training on it would contaminate every cross-dataset
number. It is permitted only as a label-vocabulary reference. This guard makes
that restriction durable and testable rather than a matter of discipline.
"""
from __future__ import annotations

import re

# Canonical forbidden-for-TRAINING dataset identifiers (matched loosely).
FORBIDDEN_TRAINING_DATASETS = frozenset({
    "master",
    "master plant disease",
    "master plant disease dataset",
    "master_plant_disease",
    "plant-disease-processed",
    "harisri2005/plant-disease-processed",
})


class TrainingDataPolicyError(RuntimeError):
    """Raised when a forbidden dataset is used as a training source."""


def _normalize(name: str) -> str:
    return re.sub(r"[\s_\-]+", " ", str(name).strip().lower())


def is_forbidden_training_source(name: str) -> bool:
    n = _normalize(name)
    for f in FORBIDDEN_TRAINING_DATASETS:
        fn = _normalize(f)
        if n == fn or fn in n:
            return True
    return False


def assert_trainable(dataset_name: str) -> None:
    """Raise if ``dataset_name`` may not be used for training."""
    if is_forbidden_training_source(dataset_name):
        raise TrainingDataPolicyError(
            f"'{dataset_name}' is forbidden as a training source (Master Plant "
            f"Disease Dataset is vocabulary-only; it likely contains PlantVillage "
            f"and the evaluation sets and would contaminate cross-dataset metrics)."
        )
