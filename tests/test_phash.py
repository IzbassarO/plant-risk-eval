"""Perceptual-hash duplicate / near-duplicate detection."""
from __future__ import annotations

from ica26.leakage import phash


def test_identical_images_hash_equal(gradient_image, tmp_path):
    a = gradient_image(seed=1)
    b = gradient_image(seed=1)  # identical
    ha, hb = phash.phash_hex(a), phash.phash_hex(b)
    assert ha == hb
    assert phash.hamming_hex(ha, hb) == 0


def test_exact_duplicate_detected_intra():
    # crafted identical hashes -> exact pair, no near pair
    idx = phash.build_index([
        {"dataset": "A", "path": "x", "phash": "ffffffffffffffff"},
        {"dataset": "A", "path": "y", "phash": "ffffffffffffffff"},
        {"dataset": "A", "path": "z", "phash": "0000000000000000"},
    ])
    r = phash.find_duplicates(idx, threshold=3)
    assert r["summary"]["n_exact_pairs"] == 1
    assert r["summary"]["n_near_pairs"] == 0
    assert r["exact"].iloc[0]["path_a"] == "x" and r["exact"].iloc[0]["path_b"] == "y"


def test_near_duplicate_threshold_boundary():
    # differ by exactly 2 bits (0x3 = 0b11)
    idx = phash.build_index([
        {"dataset": "A", "path": "a", "phash": "0000000000000000"},
        {"dataset": "B", "path": "b", "phash": "0000000000000003"},
    ])
    # threshold 1 -> not detected; threshold 2 -> near; never exact
    assert phash.find_duplicates(idx, threshold=1)["summary"]["n_near_pairs"] == 0
    r2 = phash.find_duplicates(idx, threshold=2)
    assert r2["summary"]["n_near_pairs"] == 1
    assert r2["summary"]["n_exact_pairs"] == 0
    assert int(r2["near"].iloc[0]["distance"]) == 2


def test_cross_dataset_exact_and_paths():
    a = phash.build_index([{"dataset": "train", "path": "t1", "phash": "abcdabcdabcdabcd"}])
    b = phash.build_index([{"dataset": "eval", "path": "e1", "phash": "abcdabcdabcdabcd"}])
    r = phash.find_duplicates(a, b, threshold=0)
    assert r["summary"]["mode"] == "cross"
    assert r["summary"]["n_exact_pairs"] == 1
    row = r["exact"].iloc[0]
    assert row["dataset_a"] == "train" and row["dataset_b"] == "eval"


def test_image_based_duplicate_detection(textured_image, tmp_path):
    """A re-encoded/resized copy is caught as a duplicate; an unrelated image is not.

    This is the realistic leakage case: the *same* photo re-appears across
    datasets after JPEG re-compression or resizing. (The strict near-duplicate
    boundary is tested deterministically in test_near_duplicate_threshold_boundary.)
    """
    import io

    from PIL import Image

    base = textured_image(seed=1)
    buf = io.BytesIO()
    base.save(buf, format="JPEG", quality=90)  # re-encoded copy
    near = Image.open(buf)
    resized = base.resize((32, 32)).resize((128, 128))  # resized copy
    different = textured_image(seed=2)

    hb = phash.phash_hex(base)
    hn = phash.phash_hex(near)
    hr = phash.phash_hex(resized)
    hd = phash.phash_hex(different)

    assert phash.hamming_hex(hb, hn) <= 4          # re-encoded copy ~ identical
    assert phash.hamming_hex(hb, hr) <= 4          # resized copy ~ identical
    assert phash.hamming_hex(hb, hd) > phash.hamming_hex(hb, hn)  # unrelated is far

    # cross-dataset pipeline: train image vs an eval set containing a copy + a distractor
    a = phash.build_index([{"dataset": "train", "path": "t", "phash": hb}])
    b = phash.build_index([
        {"dataset": "eval", "path": "copy", "phash": hn},
        {"dataset": "eval", "path": "distractor", "phash": hd},
    ])
    r = phash.find_duplicates(a, b, threshold=4)
    total = r["summary"]["n_exact_pairs"] + r["summary"]["n_near_pairs"]
    assert total == 1  # only the copy is flagged
    matched = pd_first_path(r)
    assert matched == "copy"


def pd_first_path(result):
    import pandas as pd
    both = pd.concat([result["exact"], result["near"]], ignore_index=True)
    return both.iloc[0]["path_b"]


def test_output_ordering_is_deterministic():
    idx = phash.build_index([
        {"dataset": "A", "path": "b", "phash": "0000000000000000"},
        {"dataset": "A", "path": "a", "phash": "0000000000000000"},
        {"dataset": "A", "path": "c", "phash": "0000000000000000"},
    ])
    r1 = phash.find_duplicates(idx, threshold=0)["exact"]
    r2 = phash.find_duplicates(idx, threshold=0)["exact"]
    assert r1.equals(r2)
    # sorted by (dataset_a, path_a, dataset_b, path_b)
    assert list(zip(r1["path_a"], r1["path_b"])) == sorted(zip(r1["path_a"], r1["path_b"]))
