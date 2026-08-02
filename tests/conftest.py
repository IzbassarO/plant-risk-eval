"""Shared pytest fixtures: synthetic images and mapping rows (no downloads)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from ica26.mapping import schema


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root, so tests can assert on the shipped review artifacts."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def gradient_image():
    """A deterministic, structured RGB image (good phash target)."""
    def _make(seed=0, size=64):
        rng = np.random.default_rng(seed)
        x = np.linspace(0, 255, size, dtype=np.uint8)
        base = np.stack([np.tile(x, (size, 1)),
                         np.tile(x[:, None], (1, size)),
                         np.full((size, size), 128, np.uint8)], axis=-1)
        # a little structured variation so phash is non-degenerate
        base = (base.astype(int) + (rng.integers(0, 8, base.shape))).clip(0, 255).astype(np.uint8)
        return Image.fromarray(base)
    return _make


@pytest.fixture
def textured_image():
    """Low-frequency textured RGB image -> phash-stable (unlike flat gradients)."""
    def _make(seed=0, size=128):
        rng = np.random.default_rng(seed)
        base = rng.normal(0, 1, (8, 8, 3))
        norm = (base - base.min()) / (np.ptp(base)) * 255
        return Image.fromarray(norm.astype(np.uint8)).resize((size, size))
    return _make


@pytest.fixture
def pending_row():
    return schema.empty_row(
        dataset="PlantDoc",
        dataset_class="Tomato leaf yellow virus",
        canonical_crop="tomato",
        canonical_disease="yellow virus",
    )


@pytest.fixture
def approved_row_with_evidence():
    """A syntactically-complete APPROVED row (fake but non-blank evidence).

    Used ONLY to prove the validator ACCEPTS a fully-populated approved row.
    The evidence text is placeholder, not a scientific claim.
    """
    row = schema.empty_row(dataset="PlantDoc", dataset_class="Corn rust leaf",
                           canonical_crop="corn", canonical_disease="rust")
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
    return row


@pytest.fixture
def mapping_df(pending_row):
    return schema.new_template([pending_row])
