"""Scalable pHash index: parity, identity fields and deterministic pairs."""
from __future__ import annotations

import numpy as np

from ica26.leakage import phash


def _random_index(n, seed, dataset="d"):
    rng = np.random.default_rng(seed)
    keys = rng.integers(0, 2**64, size=n, dtype=np.uint64)
    return phash.build_index(
        [{"dataset": dataset, "split": "s", "class_label": "c",
          "path": f"{i}.png", "phash": format(int(k), "016x")} for i, k in enumerate(keys)]
    )


def _pair_set(df):
    return {(r["path_a"], r["path_b"], int(r["distance"])) for _, r in df.iterrows()}


def test_indexed_matches_brute_force_intra():
    # small n with a modest hash space so near-duplicates actually occur
    rng = np.random.default_rng(7)
    keys = rng.integers(0, 2**16, size=60, dtype=np.uint64)  # collisions/near-dups likely
    idx = phash.build_index(
        [{"dataset": "d", "path": f"{i}.png", "phash": format(int(k), "016x")} for i, k in enumerate(keys)]
    )
    for thr in (0, 2, 5, 10):
        fast = phash.find_duplicates(idx, threshold=thr)
        slow = phash.brute_force_duplicates(idx, threshold=thr)
        assert _pair_set(fast["exact"]) == _pair_set(slow["exact"]), thr
        assert _pair_set(fast["near"]) == _pair_set(slow["near"]), thr


def test_indexed_matches_brute_force_cross():
    rng = np.random.default_rng(11)
    a = phash.build_index([{"dataset": "A", "path": f"a{i}", "phash": format(int(k), "016x")}
                           for i, k in enumerate(rng.integers(0, 2**16, 40, dtype=np.uint64))])
    b = phash.build_index([{"dataset": "B", "path": f"b{i}", "phash": format(int(k), "016x")}
                           for i, k in enumerate(rng.integers(0, 2**16, 40, dtype=np.uint64))])
    for thr in (0, 3, 8):
        fast = phash.find_duplicates(a, b, threshold=thr)
        slow = phash.brute_force_duplicates(a, b, threshold=thr)
        assert _pair_set(fast["exact"]) == _pair_set(slow["exact"]), thr
        assert _pair_set(fast["near"]) == _pair_set(slow["near"]), thr


def test_no_self_pairs_and_no_reversed_pairs():
    idx = phash.build_index([
        {"dataset": "d", "path": "a", "phash": "0000000000000000"},
        {"dataset": "d", "path": "b", "phash": "0000000000000000"},
    ])
    res = phash.find_duplicates(idx, threshold=5)
    pairs = list(zip(res["exact"]["path_a"], res["exact"]["path_b"]))
    assert pairs == [("a", "b")]           # exactly one, a<b, no (a,a)/(b,b)/(b,a)


def test_recursive_hamming_search_query_correct():
    vals = [0x0, 0x1, 0x3, 0xFF, 0xFFFF]
    idx = phash.build_index([
        {"dataset": "d", "path": str(v), "phash": format(v, "016x")}
        for v in vals
    ])
    query = phash.build_index([
        {"dataset": "q", "path": "zero", "phash": "0000000000000000"}
    ])
    result = phash.find_duplicates(query, idx, threshold=2)
    got = {int(value) for value in result["exact"]["path_b"]}
    got.update(int(value) for value in result["near"]["path_b"])
    # within Hamming 2 of 0: 0 (0 bits), 1 (1 bit), 3 (2 bits)
    assert got == {0x0, 0x1, 0x3}


def test_benchmark_runs_small():
    df = phash.benchmark(sizes=(50, 200), threshold=5)
    assert list(df["n"]) == [50, 200]
    assert (df["seconds"] >= 0).all()


def test_pair_columns_carry_identity():
    a = phash.build_index([{"dataset": "train", "split": "train", "class_label": "apple",
                            "path": "train/apple/1.png", "phash": "abcdabcdabcdabcd"}])
    b = phash.build_index([{"dataset": "eval", "split": "test", "class_label": "apple",
                            "path": "test/apple/2.png", "phash": "abcdabcdabcdabcd"}])
    row = phash.find_duplicates(a, b, threshold=0)["exact"].iloc[0]
    assert row["dataset_a"] == "train" and row["split_a"] == "train" and row["class_a"] == "apple"
    assert row["dataset_b"] == "eval" and row["split_b"] == "test"
