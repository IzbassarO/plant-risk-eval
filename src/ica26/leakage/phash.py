"""Perceptual-hash leakage detection (imagehash.phash) — exact chunked search.

Finds identical and near-duplicate images WITHIN one dataset or ACROSS two
datasets. Cross-dataset near-duplicates between a training source and an
evaluation set are the ones that invalidate a generalization claim.

Why this is a full evaluation and not an index
----------------------------------------------
The previous implementation used a recursive striped pigeonhole partition. Its
completeness argument was sound, but its *work* was not bounded: a pair that
agrees on more than one block is re-visited through each of them, so on a dense
cluster of mutually-near hashes the traversal amplifies. Measured here at
threshold 6 over 64-bit hashes, 100 mutually-near values did not finish in 60
seconds, while a plain scan of the same input took 0.19 s. An index that is
slower than the scan it replaces -- precisely when there is real output to find
-- is a liability, so it is gone from the production path.

This module evaluates **every** pair exactly, in bounded chunks:

  * **exact** duplicates via a hash -> members dictionary (O(N), output-sized);
  * **near** duplicates by chunked exact Hamming evaluation over DISTINCT hash
    values -- XOR a block of left values against a block of right values,
    popcount, keep what falls within the radius;
  * cost is therefore ``O(N x M)`` cross-dataset and ``O(N^2 / 2)``
    intra-dataset. That is stated plainly rather than dressed up: it is
    predictable, it has no recursive amplification, and it cannot degrade on
    adversarial input. It is NOT subquadratic and does not claim to be;
  * peak memory is set by the chunk size, NOT by the input size. The full
    all-pairs matrix is never allocated;
  * a scalar brute-force reference (:func:`brute_force_duplicates`) is the
    oracle the chunked path is validated against.

Everything else is unchanged and load-bearing: configurable threshold; exact and
near reported separately; no self-pairs and no reversed A-B / B-A duplicates;
deterministic ordering; every pair carries dataset, split, class and relative
path for both sides; corrupt/missing files are reported, not silently skipped;
images are hashed one at a time so pixels are never all held in memory.
"""
from __future__ import annotations

import argparse
import json
import math
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
# 2: recursive striped pigeonhole partition. Withdrawn -- complete but
#    super-quadratic on dense true-output clusters (R2B.2 Finding 2).
# 3: exact chunked brute-force Hamming evaluation. Every pair is evaluated;
#    cost is quadratic and predictable, memory is bounded by the chunk.
CANDIDATE_SEARCH_SCHEMA_VERSION = "ica26.leakage.candidate-search/3"
CANDIDATE_SEARCH_ALGORITHM = "exact-hash-map+chunked-bruteforce-hamming"
CANDIDATE_SEARCH_EXACT_STRATEGY = "hash-to-record-members"
CANDIDATE_SEARCH_NEAR_STRATEGY = "chunked-exact-hamming-evaluation"
CANDIDATE_SEARCH_NEAR_INPUT = "distinct-hash-values"
CANDIDATE_SEARCH_VERIFICATION_UNIT = (
    "every distinct-hash pair, evaluated exactly in bounded chunks"
)
#: Complexity, recorded in the artifact so a reader never has to infer it.
CANDIDATE_SEARCH_COMPLEXITY_INTRA = "O(N^2 / 2) exact distance evaluations"
CANDIDATE_SEARCH_COMPLEXITY_CROSS = "O(N x M) exact distance evaluations"
CANDIDATE_SEARCH_IS_OUTPUT_SENSITIVE = False

#: Target pairs per chunk. Peak working memory is a function of THIS, not of the
#: input size. 2^20 pairs of 64-bit hashes is ~8 MB for the XOR block and, with
#: the popcount temporaries, tens of MB peak -- small enough to be irrelevant on
#: any machine that can hold the index, large enough to keep numpy efficient.
DEFAULT_CHUNK_PAIRS = 1 << 20

#: Live uint64 temporaries inside :func:`_popcount64` plus the XOR block and the
#: accumulator. Used only to REPORT an estimated peak; it is a documented
#: approximation, not a measurement.
_PEAK_BYTES_PER_PAIR_WORD = 8 * 7

#: Wall-clock search duration. Informational, and the only non-reproducible
#: field a search summary carries.
SEARCH_SECONDS_FIELD = "search_seconds"

#: Fields stripped before a summary is written anywhere digest-bound. Every
#: persisted artifact in this repository must reproduce byte-for-byte, so a
#: timing field may be reported but never stored.
NON_DETERMINISTIC_SUMMARY_FIELDS = (SEARCH_SECONDS_FIELD,)


def deterministic_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """A search summary with every non-reproducible field removed."""
    return {k: v for k, v in summary.items()
            if k not in NON_DETERMINISTIC_SUMMARY_FIELDS}
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


def hash_words(bits: int) -> int:
    """Number of 64-bit words needed to hold a ``bits``-wide hash."""
    return (int(bits) + 63) // 64


def _keys_to_matrix(keys: Sequence[int], bits: int) -> np.ndarray:
    """Pack hash values into an ``(n, words)`` uint64 matrix, low word first.

    Working in fixed-width words rather than Python ints is what makes the
    evaluation vectorisable, and it generalises past 64 bits without changing
    the algorithm: a wider hash is simply more words to XOR and popcount.
    """
    words = hash_words(bits)
    matrix = np.zeros((len(keys), words), dtype=np.uint64)
    mask = (1 << 64) - 1
    for row, key in enumerate(keys):
        value = int(key)
        for word in range(words):
            matrix[row, word] = np.uint64((value >> (64 * word)) & mask)
    return matrix


def _chunk_side(chunk_pairs: int) -> int:
    """Square chunk edge for a pair budget. At least 1, so progress is assured."""
    return max(1, int(math.isqrt(max(1, int(chunk_pairs)))))


def _block_distances(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Exact Hamming distances between every row of ``left`` and of ``right``.

    Accumulates one 64-bit word at a time so the only arrays proportional to the
    chunk area are the current XOR block, its popcount, and the running total.
    """
    rows, cols = left.shape[0], right.shape[0]
    total = np.zeros((rows, cols), dtype=np.int32)
    for word in range(left.shape[1]):
        xor = left[:, word][:, None] ^ right[:, word][None, :]
        total += _popcount64(xor).astype(np.int32)
    return total


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
    chunk_pairs: int = DEFAULT_CHUNK_PAIRS,
) -> tuple[dict[tuple[int, int], int], dict[str, object]]:
    """Find near pairs between distinct hashes by exact chunked evaluation.

    Every pair is evaluated exactly once: the upper triangle for an
    intra-dataset search, the full Cartesian product for a cross-dataset one.
    There is no candidate set, no pruning, and therefore no completeness
    argument to get wrong -- ``n_distance_evaluations`` equals
    ``n_possible_pairs`` by construction, and the tests assert that identity.

    Work proceeds in square chunks of at most ``chunk_pairs`` pairs. Only the
    current chunk is ever materialised, so peak memory is a function of the
    chunk size and the hash width, not of the input size.

    ``stats`` is deterministic operation telemetry. It is reported alongside the
    result so a reader can see what was actually computed rather than trusting
    a claim about it.
    """
    keys_a = tuple(sorted(uniq_a))
    keys_b = keys_a if intra else tuple(sorted(uniq_b))
    n_a, n_b = len(keys_a), len(keys_b)
    words = hash_words(bits)
    side = _chunk_side(chunk_pairs)
    possible = (n_a * (n_a - 1) // 2) if intra else (n_a * n_b)

    stats: dict[str, object] = {
        "n_possible_pairs": int(possible),
        "n_distance_evaluations": 0,
        "n_chunks": 0,
        "chunk_rows": int(min(side, n_a) if n_a else 0),
        "chunk_cols": int(min(side, n_b) if n_b else 0),
        "chunk_pair_budget": int(chunk_pairs),
        "max_chunk_pair_count": 0,
        "estimated_peak_chunk_bytes": 0,
        "hash_words": int(words),
    }

    found: dict[tuple[int, int], int] = {}
    # ``possible == 0`` covers empty inputs and the single-distinct-hash intra
    # case, where the only chunk would be a 1x1 diagonal block with nothing
    # above its diagonal. Returning here keeps the peak-chunk telemetry honest:
    # no block was materialised, so none is reported.
    if threshold < 1 or possible == 0:
        return found, stats

    matrix_a = _keys_to_matrix(keys_a, bits)
    matrix_b = matrix_a if intra else _keys_to_matrix(keys_b, bits)

    for i0 in range(0, n_a, side):
        i1 = min(i0 + side, n_a)
        # Intra-dataset: the upper triangle only, so a pair is never evaluated
        # twice and a value is never compared with itself.
        j_start = i0 if intra else 0
        for j0 in range(j_start, n_b, side):
            j1 = min(j0 + side, n_b)
            block = _block_distances(matrix_a[i0:i1], matrix_b[j0:j1])
            if intra:
                # Keep strictly-upper entries; on a diagonal block that is
                # j > i, off-diagonal blocks are already wholly upper.
                rows = np.arange(i0, i1)[:, None]
                cols = np.arange(j0, j1)[None, :]
                keep = cols > rows
                evaluated = int(keep.sum())
                hits = np.nonzero(keep & (block > 0) & (block <= threshold))
            else:
                evaluated = int(block.size)
                hits = np.nonzero((block > 0) & (block <= threshold))

            stats["n_chunks"] = int(stats["n_chunks"]) + 1
            stats["n_distance_evaluations"] = (
                int(stats["n_distance_evaluations"]) + evaluated)
            stats["max_chunk_pair_count"] = max(
                int(stats["max_chunk_pair_count"]), int(block.size))

            for local_i, local_j in zip(*hits):
                key_x = keys_a[i0 + int(local_i)]
                key_y = keys_b[j0 + int(local_j)]
                pair = ((key_x, key_y) if not intra or key_x < key_y
                        else (key_y, key_x))
                found[pair] = int(block[local_i, local_j])

    stats["estimated_peak_chunk_bytes"] = int(
        stats["max_chunk_pair_count"]) * _PEAK_BYTES_PER_PAIR_WORD
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
    expected_text = {
        "candidate_search_schema_version": CANDIDATE_SEARCH_SCHEMA_VERSION,
        "candidate_search_algorithm": CANDIDATE_SEARCH_ALGORITHM,
        "candidate_search_exact_strategy": CANDIDATE_SEARCH_EXACT_STRATEGY,
        "candidate_search_near_strategy": CANDIDATE_SEARCH_NEAR_STRATEGY,
        "candidate_search_near_input": CANDIDATE_SEARCH_NEAR_INPUT,
        "candidate_search_verification_unit": CANDIDATE_SEARCH_VERIFICATION_UNIT,
        "candidate_search_complexity": CANDIDATE_SEARCH_COMPLEXITY_INTRA,
        "candidate_search_complexity_cross": CANDIDATE_SEARCH_COMPLEXITY_CROSS,
    }
    numeric_fields = (
        "hash_size_bits",
        "hash_words",
        "threshold",
        "n_distinct_hashes_a",
        "n_distinct_hashes_b",
        "n_possible_pairs",
        "n_possible_record_pairs",
        "n_distance_evaluations",
        "n_output_pairs",
        "n_chunks",
        "chunk_rows",
        "chunk_cols",
        "chunk_pair_budget",
        "max_chunk_pair_count",
        "estimated_peak_chunk_bytes",
    )
    required = tuple(expected_text) + numeric_fields + (
        "candidate_search_output_sensitive",)
    missing = [key for key in required if key not in search_summary]
    if missing:
        raise ValueError(
            "duplicate-search summary is missing audit field(s): "
            + ", ".join(missing))
    for field, expected in expected_text.items():
        if field == "candidate_search_complexity":
            # Intra and cross searches legitimately report different complexity.
            if search_summary[field] not in (CANDIDATE_SEARCH_COMPLEXITY_INTRA,
                                             CANDIDATE_SEARCH_COMPLEXITY_CROSS):
                raise ValueError(
                    "duplicate-search summary has unsupported "
                    f"candidate_search_complexity: {search_summary[field]!r}")
            continue
        if search_summary[field] != expected:
            raise ValueError(
                f"duplicate-search summary has unsupported {field}: "
                f"expected {expected!r}, got {search_summary[field]!r}")
    if search_summary["candidate_search_output_sensitive"] is not False:
        raise ValueError(
            "exact chunked search is not output-sensitive; a summary claiming "
            "otherwise did not come from this detector")

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

    # The defining property of an exact full evaluation: every possible pair was
    # actually measured. If these ever disagree, something pruned, and the
    # completeness claim in the report is void.
    if numbers["n_distance_evaluations"] != numbers["n_possible_pairs"]:
        raise ValueError(
            "exact chunked search must evaluate every possible pair: "
            f"{numbers['n_distance_evaluations']} evaluations for "
            f"{numbers['n_possible_pairs']} possible pairs")
    if numbers["max_chunk_pair_count"] > numbers["chunk_pair_budget"]:
        raise ValueError(
            "reported peak chunk exceeds the detector's configured pair budget")
    # Compared at the RECORD level, which is the unit output pairs are counted
    # in. Comparing against the distinct-hash space would be a unit error and
    # would fire on any input containing a repeated hash.
    if numbers["n_output_pairs"] > numbers["n_possible_record_pairs"]:
        raise ValueError("more output pairs than possible record pairs")
    return {**{k: search_summary[k] for k in expected_text},
            "candidate_search_output_sensitive": False,
            **numbers,
            # Legacy field name, retained so an older reader of a persisted
            # summary still finds the count it expects. Under an exact search it
            # is simply the evaluation count under its previous spelling.
            "n_near_verifications": numbers["n_distance_evaluations"]}


def find_duplicates(
    index_a: pd.DataFrame,
    index_b: Optional[pd.DataFrame] = None,
    threshold: int = 5,
    hash_size: int = DEFAULT_HASH_SIZE,
    chunk_pairs: int = DEFAULT_CHUNK_PAIRS,
) -> dict:
    """Exact (distance 0) and near (0 < d <= threshold) duplicate pairs.

    ``index_b=None`` -> intra-dataset (i<j, no self/reversed pairs). Otherwise
    cross-dataset. Exact matches come from a hash dictionary; near matches from
    exact chunked Hamming evaluation over DISTINCT hash values (see
    :func:`_near_key_pairs`). Every possible distinct-hash pair is evaluated.

    ``chunk_pairs`` bounds peak working memory and nothing else: the result is
    invariant to it, which the tests assert directly.

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

    # ---- near: exact chunked evaluation over distinct values ----
    import time

    _t0 = time.perf_counter()
    key_pairs, search_stats = _near_key_pairs(
        uniq_a, uniq_b, threshold=threshold, bits=bits, intra=intra,
        chunk_pairs=chunk_pairs)
    _elapsed = time.perf_counter() - _t0

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
        "candidate_search_complexity": (CANDIDATE_SEARCH_COMPLEXITY_INTRA if intra
                                        else CANDIDATE_SEARCH_COMPLEXITY_CROSS),
        "candidate_search_complexity_cross": CANDIDATE_SEARCH_COMPLEXITY_CROSS,
        "candidate_search_output_sensitive": CANDIDATE_SEARCH_IS_OUTPUT_SENSITIVE,
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "datasets_a": sorted(a["dataset"].unique().tolist()) if len(a) else [],
        "datasets_b": sorted(b["dataset"].unique().tolist()) if len(b) else [],
        "n_exact_pairs": int(len(exact)),
        "n_near_pairs": int(len(near)),
        "n_output_pairs": int(len(exact)) + int(len(near)),
        "n_distinct_hashes_a": int(len(uniq_a)),
        "n_distinct_hashes_b": int(len(uniq_b)),
        # Two different units, both reported because conflating them is how a
        # telemetry claim goes quietly wrong.  ``n_possible_pairs`` (below, from
        # the search) counts DISTINCT-HASH pairs -- the actual search space, and
        # what the evaluation count must equal.  This one counts RECORD pairs,
        # which is larger whenever two records share a hash.
        "n_possible_record_pairs": (int(len(a)) * (int(len(a)) - 1) // 2 if intra
                                    else int(len(a)) * int(len(b))),
        # Wall-clock, reported because the audit asked for it, and deliberately
        # the ONLY non-deterministic field here.  It is stripped by
        # :data:`NON_DETERMINISTIC_SUMMARY_FIELDS` before anything is persisted,
        # because every digest-bound artifact in this repository has to
        # reproduce byte-for-byte.  Operation counters, not seconds, are the
        # regression criterion.
        SEARCH_SECONDS_FIELD: round(_elapsed, 6),
        **search_stats,
        # Backward-compatible telemetry name.  Its meaning is now explicit:
        # every value is a full, exact Hamming popcount inside a bounded chunk.
        "n_near_verifications": int(search_stats["n_distance_evaluations"]),
    }
    return {"exact": exact, "near": near, "summary": summary}


def brute_force_duplicates(
    index_a: pd.DataFrame,
    index_b: Optional[pd.DataFrame] = None,
    threshold: int = 5,
) -> dict:
    """Scalar O(N*M) oracle in plain Python, used to validate the chunked path.

    Deliberately shares no code with :func:`find_duplicates`: it uses Python
    ints and ``int.bit_count`` rather than numpy words and chunking, so parity
    between the two is real evidence and not a tautology.
    """
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
    chunk_pairs: int = DEFAULT_CHUNK_PAIRS,
) -> pd.DataFrame:
    """Run a reproducible scalability benchmark with operation telemetry.

    Elapsed time is informational.  The deterministic operation counters and the
    peak chunk size are the non-fragile regression evidence: for an exact
    chunked search, evaluations always equal possible pairs, and the peak chunk
    never exceeds the configured budget however large the input grows.
    """
    import time

    rows = []
    for n in sizes:
        keys = _benchmark_keys(
            operator.index(n), fixture=fixture, threshold=threshold, seed=seed)
        idx = build_index([{"dataset": "synthetic", "path": str(i), "phash": format(int(k), "016x")}
                           for i, k in enumerate(keys)])
        t0 = time.perf_counter()
        res = find_duplicates(idx, threshold=threshold, chunk_pairs=chunk_pairs)
        dt = time.perf_counter() - t0
        s = res["summary"]
        rows.append({
            "fixture": fixture,
            "n": n,
            "possible_pairs": s["n_possible_pairs"],
            "exact_distance_evaluations": s["n_distance_evaluations"],
            "output_pairs": s["n_output_pairs"],
            "chunks": s["n_chunks"],
            "chunk_rows": s["chunk_rows"],
            "chunk_cols": s["chunk_cols"],
            "peak_chunk_pairs": s["max_chunk_pair_count"],
            "peak_chunk_bytes": s["estimated_peak_chunk_bytes"],
            "seconds": round(dt, 3),
            "exact_pairs": s["n_exact_pairs"],
            "near_pairs": s["n_near_pairs"],
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

    summary = deterministic_summary(result["summary"])
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
