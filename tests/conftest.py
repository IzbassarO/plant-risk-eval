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


# --------------------------------------------------------------------------- #
# PlantDoc pixel prerequisite
#
# `data/raw/` is gitignored, so a fresh clone legitimately has no PlantDoc
# acquisition. A handful of tests re-derive duplicate groups, which decodes every
# member's pixels; without the acquisition those tests report a *content*
# mismatch, which reads like a data-integrity failure but is really a missing
# prerequisite.
#
# The gate below asks one narrow question: was PlantDoc acquired at all? It is
# deliberately NOT a completeness check. If any image is present the tests run
# and a partial, corrupt, or mismatched tree fails exactly as before -- an
# integrity failure must never be laundered into a skip.
# --------------------------------------------------------------------------- #
PLANTDOC_RAW_RELPATH = "data/raw/plantdoc"
_PLANTDOC_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def plantdoc_acquisition_present(repo_root: Path) -> tuple[bool, str]:
    """(present, reason_if_absent) for the pinned PlantDoc acquisition.

    Present means "the acquisition exists on disk", not "the acquisition is
    complete". One image is enough to make every dependent test run for real.
    """
    root = Path(repo_root) / PLANTDOC_RAW_RELPATH
    hint = (
        f"pinned PlantDoc acquisition absent at {PLANTDOC_RAW_RELPATH}/ "
        "(data/raw/ is gitignored; see DATA_ACCESS.md, or run "
        "`python scripts/run_phase1_local.py --steps plantdoc`). "
        "This test needs the real image pixels, not the manifest alone."
    )
    if not root.is_dir():
        return False, hint
    for split in ("train", "test"):
        base = root / split
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in _PLANTDOC_IMAGE_SUFFIXES:
                return True, ""
    return False, hint


@pytest.fixture(scope="session")
def plantdoc_pixels(repo_root) -> Path:
    """Skip the requesting test unless PlantDoc image pixels are on disk."""
    present, reason = plantdoc_acquisition_present(repo_root)
    if not present:
        pytest.skip(reason)
    return repo_root / PLANTDOC_RAW_RELPATH


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
