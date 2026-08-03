"""pHash candidate generation: exact, bounded, deterministic (R2B.1 Finding 4).

The previous near-duplicate search enumerated **every pair inside every band
bucket** into one shared candidate set before verifying any of them — a
Theta(m^2) structure in time *and* memory per bucket, built whether or not the
bucket held a single real pair. Buckets are exactly where duplicates pile up, so
the worst case arrived precisely when the data was most degenerate.

The replacement collapses identical hashes first and searches each bucket with a
BK-tree, so nothing larger than the output is ever materialised. These tests
prove the two things that matter about that change: **the answers are
identical**, and the work is no longer quadratic in bucket size.

The differential oracle is `brute_force_duplicates`, which compares every pair.
If the index and the oracle ever disagree, the index is wrong.
"""
from __future__ import annotations

import random

import pytest

from ica26.leakage.phash import (
    DEFAULT_HASH_SIZE,
    HashParameterError,
    brute_force_duplicates,
    build_index,
    find_duplicates,
    hamming_int,
    hash_bits,
    validate_search_params,
)

HEX = 16          # 64-bit hashes


def _index(keys, dataset="A", width=HEX):
    return build_index([{"dataset": dataset, "path": f"{dataset}/{i:05d}",
                         "phash": format(int(k), f"0{width}x")}
                        for i, k in enumerate(keys)])


def _same(got, want, kind):
    cols = ["path_a", "path_b", "distance"]
    return got[kind][cols].reset_index(drop=True).equals(
        want[kind][cols].reset_index(drop=True))


def _assert_matches_oracle(index_a, index_b=None, threshold=6):
    got = find_duplicates(index_a, index_b, threshold=threshold)
    want = brute_force_duplicates(index_a, index_b, threshold=threshold)
    assert _same(got, want, "exact"), "exact pairs differ from brute force"
    assert _same(got, want, "near"), "near pairs differ from brute force"
    return got


def _perturb(rng, key, flips, bits=64):
    for _ in range(flips):
        key ^= 1 << rng.randrange(bits)
    return key


# --------------------------------------------------------------------------- #
# Differential correctness against the brute-force oracle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seed", range(12))
def test_intra_matches_brute_force_on_random_fixtures(seed):
    rng = random.Random(seed)
    anchors = [rng.getrandbits(64) for _ in range(rng.randint(1, 6))]
    keys = []
    for _ in range(rng.randint(2, 70)):
        roll = rng.random()
        if roll < 0.35:
            keys.append(_perturb(rng, rng.choice(anchors), rng.randint(0, 9)))
        elif roll < 0.55:
            keys.append(rng.choice(anchors))          # exact duplicate
        else:
            keys.append(rng.getrandbits(64))
    _assert_matches_oracle(_index(keys), threshold=rng.randint(1, 8))


@pytest.mark.parametrize("seed", range(12))
def test_cross_matches_brute_force_on_random_fixtures(seed):
    rng = random.Random(1000 + seed)
    a = [rng.getrandbits(64) for _ in range(rng.randint(2, 50))]
    b = [rng.choice(a) if rng.random() < 0.3
         else _perturb(rng, rng.choice(a), rng.randint(0, 9))
         for _ in range(rng.randint(2, 50))]
    _assert_matches_oracle(_index(a, "A"), _index(b, "B"), threshold=rng.randint(1, 8))


@pytest.mark.parametrize("threshold", range(0, 12))
def test_every_threshold_matches_brute_force(threshold):
    rng = random.Random(99)
    anchor = rng.getrandbits(64)
    keys = [anchor] + [_perturb(rng, anchor, d) for d in range(1, 14)]
    keys += [rng.getrandbits(64) for _ in range(10)]
    got = find_duplicates(_index(keys), threshold=threshold)
    want = brute_force_duplicates(_index(keys), threshold=threshold)
    assert _same(got, want, "exact") and _same(got, want, "near")


# --------------------------------------------------------------------------- #
# Threshold boundaries
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("distance", [1, 2, 3, 4, 5, 6, 7])
def test_a_pair_exactly_at_the_threshold_is_found(distance):
    rng = random.Random(distance)
    anchor = rng.getrandbits(64)
    partner = anchor
    for bit in range(distance):
        partner ^= 1 << (bit * 7 % 64)
    assert hamming_int(anchor, partner) == distance
    res = find_duplicates(_index([anchor, partner]), threshold=distance)
    assert len(res["near"]) == 1
    assert int(res["near"].iloc[0]["distance"]) == distance


@pytest.mark.parametrize("distance", [1, 2, 3, 4, 5, 6, 7])
def test_a_pair_one_beyond_the_threshold_is_not_found(distance):
    rng = random.Random(100 + distance)
    anchor = rng.getrandbits(64)
    partner = anchor
    for bit in range(distance):
        partner ^= 1 << (bit * 7 % 64)
    res = find_duplicates(_index([anchor, partner]), threshold=distance - 1)
    assert len(res["near"]) == 0


def test_threshold_zero_reports_only_exact():
    res = find_duplicates(_index([5, 5, 7]), threshold=0)
    assert len(res["exact"]) == 1 and len(res["near"]) == 0


# --------------------------------------------------------------------------- #
# Duplicate hashes: the old degenerate case
# --------------------------------------------------------------------------- #
def test_identical_hashes_are_exact_never_near():
    res = find_duplicates(_index([9] * 6), threshold=6)
    assert len(res["exact"]) == 15          # C(6,2)
    assert len(res["near"]) == 0
    assert res["summary"]["n_distinct_hashes_a"] == 1


def test_a_wall_of_identical_hashes_costs_nothing_to_search():
    """300 identical records used to mean ~45k candidate pairs in one bucket."""
    res = find_duplicates(_index([0xdeadbeefcafef00d] * 300), threshold=6)
    assert res["summary"]["n_distinct_hashes_a"] == 1
    assert res["summary"]["n_near_verifications"] == 0
    assert len(res["exact"]) == 300 * 299 // 2
    assert len(res["near"]) == 0


def test_duplicates_of_a_near_pair_expand_to_every_record_pair():
    """Collapsing to distinct values must not lose record-level pairs."""
    a = 0b1010 << 40
    b = a ^ 1
    keys = [a, a, b, b, b]
    _assert_matches_oracle(_index(keys), threshold=2)
    res = find_duplicates(_index(keys), threshold=2)
    assert len(res["near"]) == 6            # 2 * 3
    assert len(res["exact"]) == 1 + 3       # C(2,2) + C(3,2)


def test_cross_duplicates_expand_on_both_sides():
    a = [7, 7]
    b = [6, 6, 6]
    _assert_matches_oracle(_index(a, "A"), _index(b, "B"), threshold=2)


# --------------------------------------------------------------------------- #
# Adversarial density: the reported worst case
# --------------------------------------------------------------------------- #
def test_a_dense_low_entropy_bucket_does_not_become_all_pairs():
    """Every hash shares the low 9 bits, so they all land in one band bucket.

    The pairs are still far apart, so there is almost no output -- which is
    exactly the case the old candidate set paid Theta(m^2) for anyway.
    """
    rng = random.Random(4242)
    n = 400
    keys = [(rng.getrandbits(46) << 9) for _ in range(n)]
    res = _assert_matches_oracle(_index(keys), threshold=6)
    all_pairs = n * (n - 1) // 2
    assert res["summary"]["n_near_verifications"] < all_pairs // 4, (
        "candidate generation is drifting back toward an all-pairs scan")


def test_a_dense_bucket_of_genuinely_near_hashes_is_still_exact():
    """When the output IS quadratic, the answer must still be complete."""
    rng = random.Random(7)
    anchor = rng.getrandbits(64)
    keys = [_perturb(rng, anchor, rng.randint(0, 2)) for _ in range(40)]
    _assert_matches_oracle(_index(keys), threshold=6)


def test_many_small_clusters_stay_exact():
    rng = random.Random(11)
    keys = []
    for _ in range(25):
        anchor = rng.getrandbits(64)
        keys += [_perturb(rng, anchor, rng.randint(0, 3)) for _ in range(6)]
    _assert_matches_oracle(_index(keys), threshold=5)


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
def test_output_is_deterministic_across_runs():
    rng = random.Random(3)
    anchor = rng.getrandbits(64)
    keys = [_perturb(rng, anchor, rng.randint(0, 4)) for _ in range(30)]
    first = find_duplicates(_index(keys), threshold=6)
    for _ in range(3):
        again = find_duplicates(_index(keys), threshold=6)
        assert first["exact"].equals(again["exact"])
        assert first["near"].equals(again["near"])
        assert first["summary"] == again["summary"]


def test_output_does_not_depend_on_input_order():
    rng = random.Random(5)
    anchor = rng.getrandbits(64)
    keys = [_perturb(rng, anchor, rng.randint(0, 4)) for _ in range(20)]
    forward = find_duplicates(_index(keys), threshold=6)["near"]
    # Reversing the records renames the paths, so compare the distance multiset.
    reversed_ = find_duplicates(_index(list(reversed(keys))), threshold=6)["near"]
    assert sorted(forward["distance"].tolist()) == sorted(reversed_["distance"].tolist())
    assert len(forward) == len(reversed_)


def test_no_self_pairs_and_no_reversed_duplicates():
    rng = random.Random(13)
    anchor = rng.getrandbits(64)
    keys = [_perturb(rng, anchor, rng.randint(0, 3)) for _ in range(15)]
    res = find_duplicates(_index(keys), threshold=6)
    for frame in (res["exact"], res["near"]):
        pairs = list(zip(frame["path_a"], frame["path_b"]))
        assert all(a != b for a, b in pairs)
        assert len(set(pairs)) == len(pairs)
        assert not ({(b, a) for a, b in pairs} & set(pairs))


# --------------------------------------------------------------------------- #
# Invalid parameters fail loudly
# --------------------------------------------------------------------------- #
def test_hash_bits_is_derived_from_hash_size():
    assert hash_bits(8) == 64
    assert hash_bits(16) == 256
    with pytest.raises(HashParameterError):
        hash_bits(0)


@pytest.mark.parametrize("threshold,bits", [(64, 64), (65, 64), (100, 64), (8, 8)])
def test_a_threshold_the_hash_cannot_support_is_refused(threshold, bits):
    with pytest.raises(HashParameterError):
        validate_search_params(threshold, bits)


def test_a_negative_threshold_is_refused():
    with pytest.raises(HashParameterError):
        validate_search_params(-1, 64)


def test_find_duplicates_refuses_an_unsupportable_threshold():
    with pytest.raises(HashParameterError):
        find_duplicates(_index([1, 2, 3]), threshold=64)


def test_a_hash_wider_than_the_declared_size_is_refused():
    idx = _index([1 << 100], width=32)
    with pytest.raises(HashParameterError) as exc:
        find_duplicates(idx, threshold=6)
    assert "wider than the declared" in str(exc.value)


def test_a_wider_hash_size_is_searched_correctly():
    """256-bit hashes: banding must use the real width, not a hard-coded 64."""
    rng = random.Random(17)
    anchor = rng.getrandbits(256)
    keys = [anchor, anchor ^ 1, anchor ^ (1 << 200), rng.getrandbits(256)]
    idx = _index(keys, width=64)
    got = find_duplicates(idx, threshold=4, hash_size=16)
    want = brute_force_duplicates(idx, threshold=4)
    assert _same(got, want, "exact") and _same(got, want, "near")
    assert got["summary"]["hash_size_bits"] == 256


# --------------------------------------------------------------------------- #
# Summary bookkeeping
# --------------------------------------------------------------------------- #
def test_summary_reports_distinct_hashes_and_verification_count():
    res = find_duplicates(_index([1, 1, 2, 3]), threshold=6)
    s = res["summary"]
    assert s["n_a"] == 4 and s["n_distinct_hashes_a"] == 3
    assert s["n_near_verifications"] >= 0
    assert s["mode"] == "intra" and s["threshold"] == 6


def test_empty_and_single_record_indexes_are_handled():
    for keys in ([], [1]):
        res = find_duplicates(_index(keys), threshold=6)
        assert len(res["exact"]) == 0 and len(res["near"]) == 0


# --------------------------------------------------------------------------- #
# The live leakage result is unchanged
# --------------------------------------------------------------------------- #
def test_the_committed_leakage_gate_still_reports_16_near_pairs(repo_root):
    """R2B.1 must not change a single cross-dataset pair."""
    import json

    gate = json.loads((repo_root / "reports/leakage_gate.json").read_text())
    assert gate["exact_duplicate_count"] == 0
    assert gate["near_duplicate_count"] == 16
    assert gate["near_resolved_count"] == 16
    assert gate["unresolved_pair_count"] == 0
    assert gate["status"] == "pass"
