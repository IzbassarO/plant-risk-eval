"""ICA 2026 paper experiments: leakage-controlled cross-domain evaluation.

This package carries the training and evaluation pipeline for the ICA 2026
paper only. It reads the dataset exclusively through the manifests bound by
``data/manifests/ica26_core_experiment_lock.json`` and never rescans image
directories, so a silent change to the corpus cannot reach a training run.

Nothing in this package modifies dataset labels, splits, exclusions, image
bytes, pHash decisions, or Risk Evaluation Layer artifacts.
"""
from __future__ import annotations

SCHEMA_LOCK = "ica26.paper_experiment_dataset_lock/1"
SCHEMA_MAPPING = "ica26.cross_domain_class_mapping/1"

__all__ = ["SCHEMA_LOCK", "SCHEMA_MAPPING"]
