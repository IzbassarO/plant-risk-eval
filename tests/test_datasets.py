"""Dataset acquisition: filesystem/manifest reconciliation, snapshot schema,
PlantVillage leaf_id accounting."""
from __future__ import annotations

import numpy as np
import pandas as pd
from PIL import Image

from ica26.datasets import manifest as M
from ica26.datasets import plantdoc, plantvillage
from ica26.schemas import IMAGE_MANIFEST_COLUMNS, PLANTVILLAGE_EXTRA_COLUMNS


def _img(path, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (16, 16, 3), dtype=np.uint8)).save(path)


def test_filesystem_vs_manifest_mismatch(tmp_path):
    root = tmp_path / "plantdoc"
    _img(root / "test" / "apple" / "1.png", 1)
    _img(root / "test" / "apple" / "2.png", 2)
    df = plantdoc.build_manifest(root)
    # baseline: agree
    chk = plantdoc.verify_against_filesystem(df, root)
    assert chk["manifest_rows_missing_files"] == []
    assert chk["files_missing_from_manifest"] == []
    # a manifest row whose file was deleted
    (root / "test" / "apple" / "1.png").unlink()
    chk2 = plantdoc.verify_against_filesystem(df, root)
    assert "test/apple/1.png" in chk2["manifest_rows_missing_files"]
    # a file present on disk but absent from the manifest
    _img(root / "test" / "apple" / "3.png", 3)
    chk3 = plantdoc.verify_against_filesystem(df, root)
    assert "test/apple/3.png" in chk3["files_missing_from_manifest"]


def test_source_snapshot_schema():
    snap = plantdoc.build_source_snapshot(live=None)  # uses verified recorded values
    for key in ("repo", "repo_url", "ref", "acquisition_method", "paper_reported_count",
                "commit_sha", "upstream_image_count", "upstream_train_images",
                "upstream_test_images", "upstream_train_classes", "upstream_test_classes"):
        assert key in snap, key
    assert snap["paper_reported_count"] == 2598
    assert snap["upstream_image_count"] == 2578          # reconciled fact
    assert len(snap["commit_sha"]) == 40


def test_reconcile_reports_all_counts(tmp_path):
    root = tmp_path / "plantdoc"
    _img(root / "train" / "apple" / "1.png", 1)
    _img(root / "test" / "apple" / "2.png", 2)
    df = plantdoc.build_manifest(root)
    snap = plantdoc.build_source_snapshot(live=None)
    fs = plantdoc.verify_against_filesystem(df, root)
    rec = plantdoc.reconcile(df, snap, fs)
    for key in ("paper_reported_count", "upstream_repository_count", "downloaded_image_count",
                "valid_decodable_count", "manifest_count", "train_class_count", "test_class_count"):
        assert key in rec, key
    assert rec["downloaded_image_count"] == 2
    assert rec["complete"] is False                      # 2 != 2578


def _pv_manifest():
    cols = list(IMAGE_MANIFEST_COLUMNS) + list(PLANTVILLAGE_EXTRA_COLUMNS)
    rows = [
        {**{c: "" for c in cols}, "dataset": "PlantVillage", "split": "train",
         "class_label": "Apple_scab", "relpath": f"c/train/Apple_scab/{i}.png",
         "sha256": "0" * 64, "width": 256, "height": 256, "mode": "RGB", "n_bytes": 1,
         "is_corrupt": False, "leaf_id": lid, "has_leaf_id": has}
        for i, (lid, has) in enumerate([("L1", True), ("", False), ("L2", True)])
    ]
    return pd.DataFrame(rows, columns=cols)


def test_plantvillage_missing_leaf_id_stays_missing():
    df = _pv_manifest()
    s = plantvillage.summarize(df, "color")
    assert s["leaf_id"]["n_with_leaf_id"] == 2
    assert s["leaf_id"]["n_without_leaf_id"] == 1        # not fabricated away
    assert s["leaf_id"]["grouped_split_readiness"] == "partial"


def test_plantvillage_fully_grouped_is_ready():
    df = _pv_manifest()
    df["has_leaf_id"] = True
    s = plantvillage.summarize(df, "color")
    assert s["leaf_id"]["grouped_split_readiness"] == "ready"
