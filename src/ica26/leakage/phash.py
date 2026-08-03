"""Perceptual-hash leakage detection (imagehash.phash) — scalable index.

Finds identical and near-duplicate images WITHIN one dataset or ACROSS two
datasets. Cross-dataset near-duplicates between a training source and an
evaluation set are the ones that invalidate a generalization claim.

Design (replaces the previous O(N^2) all-pairs scan):
  * **exact** duplicates via a hash -> members dictionary (O(N));
  * **near** duplicates via recursively partitioned exact Hamming search;
  * a brute-force reference (`brute_force_duplicates`) exists for test parity;
  * configurable threshold; exact and near reported separately;
  * no self-pairs, no reversed A-B / B-A duplicates; deterministic ordering;
  * every pair carries dataset, split, class and relative path for both sides;
  * corrupt/missing files are reported, not silently skipped;
  * images are hashed one at a time — pixels never all held in memory.
"""
from __future__ import annotations

import argparse
import json
import operator
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

PHASH_ALGORITHM = "imagehash.phash"
DEFAULT_HASH_SIZE = 8  # 64-bit hash
# Keep this contract in the result and in the persisted cross-dataset summary.
# It is deliberately separate from ``PHASH_ALGORITHM``: imagehash describes
# how a hash is made, while this versioned value describes how candidate pairs
# were found.  Bump it when the candidate-search semantics change so an audit
# can distinguish a changed implementation from a changed input population.
CANDIDATE_SEARCH_SCHEMA_VERSION = "ica26.leakage.candidate-search/2"
CANDIDATE_SEARCH_ALGORITHM = "exact-hash-map+recursive-striped-hamming-partition"
CANDIDATE_SEARCH_EXACT_STRATEGY = "hash-to-record-members"
CANDIDATE_SEARCH_NEAR_STRATEGY = "recursive-pigeonhole-partition+bounded-leaf-verification"
CANDIDATE_SEARCH_NEAR_INPUT = "distinct-hash-values"
CANDIDATE_SEARCH_VERIFICATION_UNIT = (
    "distinct-hash pairs reaching a bounded recursive leaf"
)
DEFAULT_LEAF_PAIR_LIMIT = 512
INDEX_COLUMNS = ["dataset", "split", "class_label", "path", "phash"]
PAIR_COLUMNS = [
    "dataset_a", "split_a", "class_a", "path_a",
    "dataset_b", "split_b", "class_b", "path_b",
    "distance",
]


# --------------------------------------------------------------------------- #
# Hashing
# --------------------------------------------------------------------------- #
def phash_hex(image_or_path, hash_size: int = DEFAULT_HASH_SIZE) -> str:
    import imagehash
    from PIL import Image

    if hasattr(image_or_path, "convert"):
        img = image_or_path
    else:
        img = Image.open(image_or_path)
    return str(imagehash.phash(img.convert("RGB"), hash_size=hash_size))


def _hex_to_uint64(hex_series: Sequence[str]) -> np.ndarray:
    return np.array([int(h, 16) for h in hex_series], dtype=np.uint64)


def _popcount64(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.uint64)
    m1 = np.uint64(0x5555555555555555)
    m2 = np.uint64(0x3333333333333333)
    m4 = np.uint64(0x0F0F0F0F0F0F0F0F)
    h01 = np.uint64(0x0101010101010101)
    x = x - ((x >> np.uint64(1)) & m1)
    x = (x & m2) + ((x >> np.uint64(2)) & m2)
    x = (x + (x >> np.uint64(4))) & m4
    return ((x * h01) >> np.uint64(56)) & np.uint64(0xFF)


def hamming_int(a: int, b: int) -> int:
    # int.bit_count() (Py3.10+) is a C-level popcount.
    return (int(a) ^ int(b)).bit_count()


def hamming_hex(a: str, b: str) -> int:
    return hamming_int(int(a, 16), int(b, 16))


class HashParameterError(ValueError):
    """Raised for a hash width or threshold that cannot be searched exactly."""


def hash_bits(hash_size: int = DEFAULT_HASH_SIZE) -> int:
    """Bit width of an ``imagehash.phash`` of side ``hash_size``."""
    try:
        size = operator.index(hash_size)
    except TypeError as exc:
        raise HashParameterError(
            f"hash_size must be an integer, got {hash_size!r}") from exc
    if size < 1:
        raise HashParameterError(f"hash_size must be >= 1, got {hash_size!r}")
    return size * size


def validate_search_params(threshold: int, bits: int) -> None:
    """Validate the declared Hamming space and inclusive radius."""
    try:
        width = operator.index(bits)
    except TypeError as exc:
        raise HashParameterError(f"hash width must be an integer, got {bits!r}") from exc
    try:
        radius = operator.index(threshold)
    except TypeError as exc:
        raise HashParameterError(
            f"threshold must be an integer, got {threshold!r}") from exc
    if width < 1:
        raise HashParameterError(f"hash width must be >= 1 bit, got {bits!r}")
    if radius < 0:
        raise HashParameterError(f"threshold must be >= 0, got {threshold!r}")
    if radius >= width:
        raise HashParameterError(
            f"threshold {threshold} is not less than the {width}-bit hash width; "
            "every pair would match and the result would be meaningless")


def _partition_bits(positions: Sequence[int], parts: int) -> tuple[tuple[int, ...], ...]:
    """Deterministically stripe bit positions across ``parts`` non-empty blocks.

    Striping is deliberate.  A long shared contiguous bit band is distributed
    across the blocks instead of becoming one pathological bucket.  The
    completeness argument depends only on disjoint coverage, not contiguity.
    """
    if parts < 1 or parts > len(positions):
        raise HashParameterError(
            f"cannot partition {len(positions)} bit positions into {parts} blocks")
    return tuple(tuple(positions[offset::parts]) for offset in range(parts))


def _block_value(key: int, positions: Sequence[int]) -> int:
    value = 0
    for output_bit, input_bit in enumerate(positions):
        value |= ((key >> input_bit) & 1) << output_bit
    return value


def _band_defs(threshold: int, bits: int = 64) -> list[tuple[int, int]]:
    """Compatibility helper exposing the top-level contiguous band widths.

    Candidate search itself uses :func:`_partition_bits`; callers that used this
    private helper for diagnostics still receive ``threshold + 1`` complete,
    non-overlapping bands.
    """
    validate_search_params(threshold, bits)
    b = threshold + 1
    base = bits // b
    defs, shift = [], 0
    for i in range(b):
        width = base + ((bits - base * b) if i == b - 1 else 0)
        defs.append((shift, (1 << width) - 1))
        shift += width
    return defs


# --------------------------------------------------------------------------- #
# Indexing
# --------------------------------------------------------------------------- #
def build_index(records: Iterable[dict]) -> pd.DataFrame:
    """records: iterable of dicts with at least {dataset, path, phash};
    optional {split, class_label}. Deterministically ordered."""
    rows = []
    for r in records:
        rows.append({
            "dataset": r.get("dataset", ""),
            "split": r.get("split", ""),
            "class_label": r.get("class_label", r.get("class", "")),
            "path": r.get("path", ""),
            "phash": r["phash"],
        })
    df = pd.DataFrame(rows, columns=INDEX_COLUMNS)
    if len(df):
        df = df.sort_values(["dataset", "split", "class_label", "path"]).reset_index(drop=True)
    return df


def index_from_manifest(
    manifest: str | Path | pd.DataFrame,
    root: str | Path,
    dataset: Optional[str] = None,
    hash_size: int = DEFAULT_HASH_SIZE,
) -> tuple[pd.DataFrame, list[str]]:
    """Compute a phash index for every non-corrupt image in a manifest.

    Streams images one at a time (pixels never all in memory). Returns
    (index_df, skipped_paths); missing/corrupt files are reported, not dropped.
    """
    from PIL import Image

    if isinstance(manifest, (str, Path)):
        man = pd.read_csv(manifest, dtype=str, keep_default_na=False)
    else:
        man = manifest
    root = Path(root)
    recs, skipped = [], []
    for _, row in man.iterrows():
        ds = dataset or row.get("dataset", "dataset")
        rel = row["relpath"]
        if str(row.get("is_corrupt", "False")).lower() == "true":
            skipped.append(rel)
            continue
        abspath = root / rel
        try:
            with Image.open(abspath) as im:
                h = phash_hex(im, hash_size)
            recs.append({
                "dataset": ds, "split": row.get("split", ""),
                "class_label": row.get("class_label", ""), "path": rel, "phash": h,
            })
        except Exception:
            skipped.append(rel)
    return build_index(recs), skipped


# --------------------------------------------------------------------------- #
# Duplicate search (dict for exact + BK-tree for near)
# --------------------------------------------------------------------------- #
def _row_fields(df: pd.DataFrame, i: int, side: str) -> dict:
    r = df.iloc[i]
    return {
        f"dataset_{side}": r["dataset"], f"split_{side}": r["split"],
        f"class_{side}": r["class_label"], f"path_{side}": r["path"],
    }


def _distinct_keys(keys: Sequence[int]) -> dict[int, list[int]]:
    """``hash value -> record indices``. Collapses identical hashes."""
    out: dict[int, list[int]] = {}
    for i, k in enumerate(keys):
        out.setdefault(k, []).append(i)
    return out


def _validated_hash_keys(frame: pd.DataFrame, *, bits: int, side: str) -> list[int]:
    """Parse a frame's hashes while enforcing the declared fixed width."""
    if "phash" not in frame.columns:
        raise HashParameterError(f"index {side} is missing required column 'phash'")
    digits = (bits + 3) // 4
    allowed = frozenset("0123456789abcdefABCDEF")
    keys: list[int] = []
    for row_number, raw in enumerate(frame["phash"]):
        if not isinstance(raw, str):
            raise HashParameterError(
                f"index {side} row {row_number} phash must be a {digits}-digit "
                f"hex string, got {raw!r}")
        if len(raw) != digits or any(char not in allowed for char in raw):
            raise HashParameterError(
                f"index {side} row {row_number} phash must be exactly {digits} "
                f"hex digits for a {bits}-bit hash, got {raw!r}")
        key = int(raw, 16)
        if key.bit_length() > bits:
            raise HashParameterError(
                f"index {side} row {row_number} contains a {key.bit_length()}-bit "
                f"hash, wider than the declared {bits}-bit width")
        keys.append(key)
    return keys


def _near_key_pairs(
    uniq_a: dict[int, list[int]],
    uniq_b: dict[int, list[int]],
    *,
    threshold: int,
    bits: int,
    intra: bool,
    leaf_pair_limit: int = DEFAULT_LEAF_PAIR_LIMIT,
) -> tuple[dict[tuple[int, int], int], dict[str, int]]:
    """Find near pairs between distinct hashes by exact recursive partitioning.

    At every non-leaf task, the still-unresolved bit positions are divided into
    ``threshold + 1`` disjoint striped blocks.  A pair at Hamming distance at
    most ``threshold`` must be identical on at least one block (pigeonhole), so
    following every equal-block bucket has complete recall.  That block is
    removed before recursion because all pairs in the child are known to agree
    there.  A false-dense bucket is partitioned again; it is never expanded into
    a quadratic candidate list and there is no insertion-order-sensitive tree.

    Recursion stops only when the bucket's pair product is explicitly bounded,
    or when no more than ``threshold`` unresolved bits remain.  In the latter
    case every pair in the bucket is a true output, so quadratic work is
    output-required rather than an indexing artefact.  ``found`` contains only
    authenticated output key pairs; no all-candidates set is materialised.

    ``stats`` is deterministic operation telemetry.  In particular,
    ``n_distance_evaluations`` counts every full Hamming popcount and lets tests
    distinguish this search from an all-pairs implementation without a timing
    assertion.
    """
    found: dict[tuple[int, int], int] = {}
    stats = {
        "n_candidate_checks": 0,
        "n_distance_evaluations": 0,
        "n_partition_tasks": 0,
        "n_recursive_partitions": 0,
        "n_partition_memberships": 0,
        "max_leaf_pair_count": 0,
    }
    if threshold < 1 or not uniq_a or not uniq_b:
        return found, stats
    try:
        limit = operator.index(leaf_pair_limit)
    except TypeError as exc:
        raise HashParameterError(
            f"leaf_pair_limit must be an integer, got {leaf_pair_limit!r}") from exc
    if limit < 1:
        raise HashParameterError(
            f"leaf_pair_limit must be >= 1, got {leaf_pair_limit!r}")

    def pair_count(keys_a: Sequence[int], keys_b: Sequence[int], same: bool) -> int:
        if same:
            return len(keys_a) * (len(keys_a) - 1) // 2
        return len(keys_a) * len(keys_b)

    def verify(keys_a: Sequence[int], keys_b: Sequence[int], same: bool) -> None:
        if same:
            pairs = ((keys_a[i], keys_a[j])
                     for i in range(len(keys_a))
                     for j in range(i + 1, len(keys_a)))
        else:
            pairs = ((key_a, key_b) for key_a in keys_a for key_b in keys_b)
        for key_a, key_b in pairs:
            pair = ((key_a, key_b) if not same or key_a < key_b
                    else (key_b, key_a))
            if pair in found:
                continue
            stats["n_candidate_checks"] += 1
            stats["n_distance_evaluations"] += 1
            distance = hamming_int(key_a, key_b)
            if 0 < distance <= threshold:
                found[pair] = distance

    def group(keys: Sequence[int], block: Sequence[int]) -> dict[int, tuple[int, ...]]:
        buckets: dict[int, list[int]] = {}
        for key in keys:
            buckets.setdefault(_block_value(key, block), []).append(key)
        return {value: tuple(members) for value, members in buckets.items()}

    def search(
        keys_a: tuple[int, ...],
        keys_b: tuple[int, ...],
        positions: tuple[int, ...],
        same: bool,
    ) -> None:
        count = pair_count(keys_a, keys_b, same)
        if count == 0:
            return
        stats["n_partition_tasks"] += 1
        if count <= limit or len(positions) <= threshold:
            stats["max_leaf_pair_count"] = max(
                stats["max_leaf_pair_count"], count)
            verify(keys_a, keys_b, same)
            return

        blocks = _partition_bits(positions, threshold + 1)
        stats["n_recursive_partitions"] += 1
        for block in blocks:
            remaining_set = set(block)
            remaining = tuple(bit for bit in positions if bit not in remaining_set)
            groups_a = group(keys_a, block)
            stats["n_partition_memberships"] += len(keys_a)
            if same:
                for value in sorted(groups_a):
                    members = groups_a[value]
                    if len(members) > 1:
                        search(members, members, remaining, True)
                continue

            groups_b = group(keys_b, block)
            stats["n_partition_memberships"] += len(keys_b)
            for value in sorted(groups_a.keys() & groups_b.keys()):
                search(groups_a[value], groups_b[value], remaining, False)

    keys_a = tuple(sorted(uniq_a))
    keys_b = keys_a if intra else tuple(sorted(uniq_b))
    search(keys_a, keys_b, tuple(range(bits)), intra)
    return found, stats


def candidate_search_audit_fields(search_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable candidate-search audit projection for leakage reports.

    ``find_duplicates`` labels its two inputs ``a`` and ``b`` because it also
    supports intra-dataset searches.  The Phase-1 leakage reports bind those
    sides to training and evaluation respectively, but retain the result-field
    names here so the telemetry can be traced directly to the algorithm output.

    Keeping this projection next to the algorithm prevents the two orchestration
    entry points from gradually persisting different subsets of the scalability
    evidence.
    """
    required = (
        "candidate_search_schema_version",
        "candidate_search_algorithm",
        "candidate_search_exact_strategy",
        "candidate_search_near_strategy",
        "candidate_search_near_input",
        "candidate_search_verification_unit",
        "n_distinct_hashes_a",
        "n_distinct_hashes_b",
        "n_candidate_checks",
        "n_distance_evaluations",
        "n_partition_tasks",
        "n_recursive_partitions",
        "n_partition_memberships",
        "max_leaf_pair_count",
        "n_near_verifications",
    )
    missing = [key for key in required if key not in search_summary]
    if missing:
        raise ValueError(
            "duplicate-search summary is missing audit field(s): "
            + ", ".join(missing))
    expected_text = {
        "candidate_search_schema_version": CANDIDATE_SEARCH_SCHEMA_VERSION,
        "candidate_search_algorithm": CANDIDATE_SEARCH_ALGORITHM,
        "candidate_search_exact_strategy": CANDIDATE_SEARCH_EXACT_STRATEGY,
        "candidate_search_near_strategy": CANDIDATE_SEARCH_NEAR_STRATEGY,
        "candidate_search_near_input": CANDIDATE_SEARCH_NEAR_INPUT,
        "candidate_search_verification_unit": CANDIDATE_SEARCH_VERIFICATION_UNIT,
    }
    for field, expected in expected_text.items():
        if search_summary[field] != expected:
            raise ValueError(
                f"duplicate-search summary has unsupported {field}: "
                f"expected {expected!r}, got {search_summary[field]!r}")

    numeric_fields = required[len(expected_text):]
    numbers: dict[str, int] = {}
    for field in numeric_fields:
        raw = search_summary[field]
        if isinstance(raw, bool):
            raise ValueError(
                f"duplicate-search summary field {field} must be a non-negative integer")
        try:
            value = operator.index(raw)
        except TypeError as exc:
            raise ValueError(
                f"duplicate-search summary field {field} must be a non-negative integer") from exc
        if value < 0:
            raise ValueError(
                f"duplicate-search summary field {field} must be non-negative")
        numbers[field] = value
    if numbers["n_candidate_checks"] != numbers["n_distance_evaluations"]:
        raise ValueError(
            "candidate-check and exact-distance-evaluation telemetry disagree")
    if numbers["n_near_verifications"] != numbers["n_distance_evaluations"]:
        raise ValueError(
            "legacy near-verification telemetry disagrees with exact evaluations")
    if numbers["max_leaf_pair_count"] > DEFAULT_LEAF_PAIR_LIMIT:
        raise ValueError(
            "reported leaf pair count exceeds the detector's configured bound")
    return {**expected_text, **numbers}


def find_duplicates(
    index_a: pd.DataFrame,
    index_b: Optional[pd.DataFrame] = None,
    threshold: int = 5,
    hash_size: int = DEFAULT_HASH_SIZE,
) -> dict:
    """Exact (distance 0) and near (0 < d <= threshold) duplicate pairs.

    ``index_b=None`` -> intra-dataset (i<j, no self/reversed pairs). Otherwise
    cross-dataset. Exact matches come from a hash dictionary; near matches from
    recursively partitioned exact Hamming search over DISTINCT hash values (see
    :func:`_near_key_pairs`).

    Raises :class:`HashParameterError` for a threshold that the hash width cannot
    support exactly, rather than silently returning a degraded result.

    Returns {"exact": DataFrame, "near": DataFrame, "summary": dict}.
    """
    missing_a = [column for column in INDEX_COLUMNS if column not in index_a.columns]
    if missing_a:
        raise HashParameterError(
            "index a is missing required column(s): " + ", ".join(missing_a))
    a = index_a.sort_values(INDEX_COLUMNS, kind="mergesort").reset_index(drop=True)
    intra = index_b is None
    if intra:
        b = a
    else:
        missing_b = [column for column in INDEX_COLUMNS if column not in index_b.columns]
        if missing_b:
            raise HashParameterError(
                "index b is missing required column(s): " + ", ".join(missing_b))
        b = index_b.sort_values(INDEX_COLUMNS, kind="mergesort").reset_index(drop=True)
    bits = hash_bits(hash_size)
    validate_search_params(threshold, bits)
    ka = _validated_hash_keys(a, bits=bits, side="a")
    kb = ka if intra else _validated_hash_keys(b, bits=bits, side="b")

    # ---- exact: hash -> member indices (O(N), output-sized) ----
    uniq_a = _distinct_keys(ka)
    uniq_b = uniq_a if intra else _distinct_keys(kb)

    exact_pairs: list[tuple[int, int]] = []
    if intra:
        for members in uniq_a.values():
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    exact_pairs.append((members[x], members[y]))
    else:
        for k, js in uniq_b.items():
            for i in uniq_a.get(k, []):
                for j in js:
                    exact_pairs.append((i, j))

    # ---- near: recursively partitioned exact search over distinct values ----
    key_pairs, search_stats = _near_key_pairs(
        uniq_a, uniq_b, threshold=threshold, bits=bits, intra=intra)

    near_pairs: list[tuple[int, int, int]] = []
    for (key_x, key_y), d in key_pairs.items():
        if intra:
            for i in uniq_a[key_x]:
                for j in uniq_a[key_y]:
                    near_pairs.append((i, j, d) if i < j else (j, i, d))
        else:
            for i in uniq_a[key_x]:
                for j in uniq_b[key_y]:
                    near_pairs.append((i, j, d))

    # ---- assemble frames ----
    def _mk(pairs_with_kind):
        rows = []
        for i, j, d in pairs_with_kind:
            rec = {}
            rec.update(_row_fields(a, i, "a"))
            rec.update(_row_fields(b, j, "b"))
            rec["distance"] = int(d)
            rows.append(rec)
        df = pd.DataFrame(rows, columns=PAIR_COLUMNS)
        if len(df):
            df = df.sort_values(PAIR_COLUMNS).reset_index(drop=True)
        return df

    exact = _mk([(i, j, 0) for (i, j) in exact_pairs])
    near = _mk(near_pairs)
    summary = {
        "phash_algorithm": PHASH_ALGORITHM,
        "hash_size_bits": hash_size * hash_size,
        "mode": "intra" if intra else "cross",
        "threshold": threshold,
        "candidate_search_schema_version": CANDIDATE_SEARCH_SCHEMA_VERSION,
        "candidate_search_algorithm": CANDIDATE_SEARCH_ALGORITHM,
        "candidate_search_exact_strategy": CANDIDATE_SEARCH_EXACT_STRATEGY,
        "candidate_search_near_strategy": CANDIDATE_SEARCH_NEAR_STRATEGY,
        "candidate_search_near_input": CANDIDATE_SEARCH_NEAR_INPUT,
        "candidate_search_verification_unit": CANDIDATE_SEARCH_VERIFICATION_UNIT,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "datasets_a": sorted(a["dataset"].unique().tolist()) if len(a) else [],
        "datasets_b": sorted(b["dataset"].unique().tolist()) if len(b) else [],
        "n_exact_pairs": int(len(exact)),
        "n_near_pairs": int(len(near)),
        "n_distinct_hashes_a": int(len(uniq_a)),
        "n_distinct_hashes_b": int(len(uniq_b)),
        **search_stats,
        # Backward-compatible telemetry name.  Its meaning is now explicit:
        # every value is a full, exact Hamming popcount at a bounded leaf.
        "n_near_verifications": int(search_stats["n_distance_evaluations"]),
    }
    return {"exact": exact, "near": near, "summary": summary}


def brute_force_duplicates(
    index_a: pd.DataFrame,
    index_b: Optional[pd.DataFrame] = None,
    threshold: int = 5,
) -> dict:
    """O(N*M) reference implementation, used only to validate the indexed path."""
    a = index_a.reset_index(drop=True)
    intra = index_b is None
    b = a if intra else index_b.reset_index(drop=True)
    ka = [int(h, 16) for h in a["phash"]]
    kb = [int(h, 16) for h in b["phash"]]
    exact, near = [], []
    for i in range(len(ka)):
        jrange = range(i + 1, len(kb)) if intra else range(len(kb))
        for j in jrange:
            d = hamming_int(ka[i], kb[j])
            if d > threshold:
                continue
            (exact if d == 0 else near).append((i, j, d))

    def _mk(pairs):
        rows = []
        for i, j, d in pairs:
            rec = {}
            rec.update(_row_fields(a, i, "a"))
            rec.update(_row_fields(b, j, "b"))
            rec["distance"] = int(d)
            rows.append(rec)
        df = pd.DataFrame(rows, columns=PAIR_COLUMNS)
        return df.sort_values(PAIR_COLUMNS).reset_index(drop=True) if len(df) else df

    return {"exact": _mk(exact), "near": _mk(near)}


# --------------------------------------------------------------------------- #
# Benchmark
# --------------------------------------------------------------------------- #
def _splitmix64(value: int) -> int:
    """Small deterministic permutation used to construct benchmark hashes."""
    mask = (1 << 64) - 1
    value = (value + 0x9E3779B97F4A7C15) & mask
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
    return (value ^ (value >> 31)) & mask


def _benchmark_keys(n: int, *, fixture: str, threshold: int, seed: int) -> list[int]:
    if n < 0:
        raise ValueError(f"benchmark size must be non-negative, got {n}")
    if fixture == "random":
        rng = np.random.default_rng(seed)
        return [int(key) for key in rng.integers(
            0, 2**64, size=n, dtype=np.uint64)]
    if fixture == "dense-band-near-empty":
        # Reproduce the metric-index failure: every hash agrees on one entire
        # contiguous top-level pigeonhole band, while the other bits are a
        # deterministic pseudo-random permutation.  De-duplication after the
        # band is cleared makes the requested item count exact.
        band_width = max(1, 64 // (threshold + 1))
        band_mask = (1 << band_width) - 1
        keys: list[int] = []
        seen: set[int] = set()
        counter = 0
        while len(keys) < n:
            key = _splitmix64(seed + counter) & ~band_mask
            counter += 1
            if key not in seen:
                seen.add(key)
                keys.append(key)
        return keys
    if fixture == "dense-true-output":
        # Values within radius floor(threshold/2) of one anchor are mutually
        # within threshold.  This fixture demonstrates that quadratic true
        # output is retained; callers should therefore use a modest size.
        import itertools

        radius = max(1, threshold // 2)
        anchor = _splitmix64(seed)
        keys = [anchor]
        for flips in range(1, radius + 1):
            for positions in itertools.combinations(range(64), flips):
                key = anchor
                for bit in positions:
                    key ^= 1 << bit
                keys.append(key)
                if len(keys) == n:
                    return keys
        if len(keys) < n:
            raise ValueError(
                f"dense-true-output fixture supports at most {len(keys)} unique "
                f"items at threshold {threshold}, requested {n}")
        return keys[:n]
    raise ValueError(f"unknown benchmark fixture {fixture!r}")


def benchmark(
    sizes: Sequence[int] = (1000, 10_000),
    threshold: int = 6,
    seed: int = 0,
    fixture: str = "dense-band-near-empty",
) -> pd.DataFrame:
    """Run a reproducible scalability benchmark with operation telemetry.

    Elapsed time is informational.  Candidate checks and exact distance
    evaluations are the non-fragile regression evidence.
    """
    import time

    rows = []
    for n in sizes:
        keys = _benchmark_keys(
            operator.index(n), fixture=fixture, threshold=threshold, seed=seed)
        idx = build_index([{"dataset": "synthetic", "path": str(i), "phash": format(int(k), "016x")}
                           for i, k in enumerate(keys)])
        t0 = time.perf_counter()
        res = find_duplicates(idx, threshold=threshold)
        dt = time.perf_counter() - t0
        rows.append({
            "fixture": fixture,
            "n": n,
            "candidate_checks": res["summary"]["n_candidate_checks"],
            "exact_distance_evaluations": res["summary"]["n_distance_evaluations"],
            "partition_tasks": res["summary"]["n_partition_tasks"],
            "partition_memberships": res["summary"]["n_partition_memberships"],
            "output_pairs": (
                res["summary"]["n_exact_pairs"] + res["summary"]["n_near_pairs"]),
            "seconds": round(dt, 3),
            "exact_pairs": res["summary"]["n_exact_pairs"],
            "near_pairs": res["summary"]["n_near_pairs"],
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-leakage", description="Perceptual-hash leakage check between manifests.")
    ap.add_argument("--manifest-a")
    ap.add_argument("--root-a", help="dir the manifest-a relpaths are relative to")
    ap.add_argument("--manifest-b", default=None)
    ap.add_argument("--root-b", default=None)
    ap.add_argument("--threshold", type=int, default=5)
    ap.add_argument("--out-pairs", default="reports/leakage_pairs.csv")
    ap.add_argument("--out-summary", default="reports/leakage_summary.json")
    ap.add_argument("--benchmark", action="store_true", help="run the scalability benchmark and exit")
    ap.add_argument(
        "--benchmark-fixture",
        choices=("random", "dense-band-near-empty", "dense-true-output"),
        default="dense-band-near-empty",
        help="deterministic benchmark fixture (default: dense-band-near-empty)")
    ap.add_argument(
        "--benchmark-sizes", default="1000,10000",
        help="comma-separated benchmark sizes (default: 1000,10000)")
    args = ap.parse_args(argv)

    if args.benchmark:
        try:
            sizes = tuple(int(value.strip()) for value in args.benchmark_sizes.split(",")
                          if value.strip())
        except ValueError as exc:
            ap.error(f"--benchmark-sizes must contain integers: {exc}")
        if not sizes:
            ap.error("--benchmark-sizes must name at least one size")
        print(benchmark(
            sizes=sizes,
            threshold=args.threshold,
            fixture=args.benchmark_fixture,
        ).to_string(index=False))
        return 0
    if not args.manifest_a or not args.root_a:
        ap.error("--manifest-a and --root-a are required (unless --benchmark)")

    idx_a, skip_a = index_from_manifest(args.manifest_a, args.root_a)
    idx_b = skip_b = None
    if args.manifest_b:
        if not args.root_b:
            ap.error("--root-b is required when --manifest-b is given")
        idx_b, skip_b = index_from_manifest(args.manifest_b, args.root_b)

    result = find_duplicates(idx_a, idx_b, threshold=args.threshold)
    all_pairs = pd.concat(
        [result["exact"].assign(kind="exact"), result["near"].assign(kind="near")],
        ignore_index=True,
    )
    Path(args.out_pairs).parent.mkdir(parents=True, exist_ok=True)
    all_pairs.to_csv(args.out_pairs, index=False)

    summary = result["summary"]
    summary["skipped_a"] = skip_a
    summary["skipped_b"] = skip_b or []
    summary["checked_pair"] = [args.manifest_a, args.manifest_b] if args.manifest_b else [args.manifest_a]
    Path(args.out_summary).write_text(json.dumps(summary, indent=2))

    print(f"[leakage] mode={summary['mode']} threshold={args.threshold} "
          f"| n_a={summary['n_a']} n_b={summary['n_b']}")
    print(f"[leakage] exact={summary['n_exact_pairs']} near={summary['n_near_pairs']} "
          f"| skipped_a={len(skip_a)} skipped_b={len(skip_b or [])}")
    print(f"[leakage] wrote {args.out_pairs} and {args.out_summary}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
