"""Manifest construction: hashing, corrupt detection, duplicate-path detection."""
from __future__ import annotations

import numpy as np
import pandas as pd
from PIL import Image

from ica26.datasets import manifest as M
from ica26.schemas import IMAGE_MANIFEST_COLUMNS


def _write_img(path, seed=0, size=32):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path)


def test_sha256_is_stable_and_wellformed(tmp_path):
    p = tmp_path / "a.png"
    _write_img(p, seed=3)
    h1 = M.sha256_of_file(p)
    h2 = M.sha256_of_file(p)
    assert h1 == h2 and len(h1) == 64


def test_image_meta_valid_and_corrupt(tmp_path):
    good = tmp_path / "good.png"
    _write_img(good, seed=4, size=48)
    w, h, mode, corrupt = M.read_image_meta(good)
    assert (w, h, mode, corrupt) == (48, 48, "RGB", False)

    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"this is definitely not an image")
    w, h, mode, corrupt = M.read_image_meta(bad)
    assert corrupt is True and w is None


def test_build_manifest_flags_corrupt_not_dropped(tmp_path):
    root = tmp_path / "ds"
    _write_img(root / "train" / "classA" / "ok1.png", seed=1)
    _write_img(root / "train" / "classA" / "ok2.png", seed=2)
    (root / "train" / "classA" / "broken.jpg").write_bytes(b"garbage-not-image")

    df = M.build_split_class_manifest(
        root=root, dataset="ds", source_url="http://x", split_dirs=["train"],
        acquired_at_utc="2026-01-01T00:00:00+00:00",
    )
    assert len(df) == 3                    # corrupt file recorded, not dropped
    assert int(df["is_corrupt"].sum()) == 1
    assert list(df.columns)[: len(IMAGE_MANIFEST_COLUMNS)] == list(IMAGE_MANIFEST_COLUMNS)

    summary = M.manifest_summary(df, "ds")
    assert summary["n_corrupt_total"] == 1
    assert summary["per_split"]["train"]["n_images"] == 3


def test_duplicate_path_detection():
    df = pd.DataFrame({
        "dataset": ["d", "d"],
        "split": ["train", "train"],
        "class_label": ["a", "a"],
        "relpath": ["train/a/1.png", "train/a/1.png"],  # duplicate
        "sha256": ["0" * 64, "1" * 64],
        "width": [10, 10], "height": [10, 10], "mode": ["RGB", "RGB"],
        "n_bytes": [1, 1], "is_corrupt": [False, False],
        "source_url": ["u", "u"], "acquired_at_utc": ["t", "t"],
    })
    dups = M.find_duplicate_paths(df)
    assert dups == ["train/a/1.png"]
    res = M.validate_manifest(df)
    assert not res.ok
    assert any("duplicate" in i.message for i in res.errors)


def test_valid_manifest_passes(tmp_path):
    root = tmp_path / "ds"
    _write_img(root / "test" / "c" / "1.png", seed=7)
    df = M.build_split_class_manifest(root=root, dataset="ds", source_url="u", split_dirs=["test"])
    assert M.validate_manifest(df).ok
