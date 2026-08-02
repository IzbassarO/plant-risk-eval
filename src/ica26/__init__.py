"""ica26 -- reusable core for the ICA-2026 project
*From Diagnosis to Decision: An Action-Level and Risk-Weighted Evaluation
Framework for Deep Learning-Based Plant Disease Recognition.*

Phase-1 foundation package. Core logic lives here (not in notebooks) so that
notebooks and the Colab pipeline import one consistent implementation.
"""
from __future__ import annotations

from . import schemas
from .schemas import (
    ACTION_CLASSES,
    FORBIDDEN_ACTION_CLASSES,
    MAPPING_COLUMNS,
    REVIEW_STATUSES,
    MAPPING_CONFIDENCES,
    ValidationResult,
)

__version__ = "0.1.0"

__all__ = [
    "schemas",
    "ACTION_CLASSES",
    "FORBIDDEN_ACTION_CLASSES",
    "MAPPING_COLUMNS",
    "REVIEW_STATUSES",
    "MAPPING_CONFIDENCES",
    "ValidationResult",
    "__version__",
]
