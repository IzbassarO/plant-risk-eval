"""Perceptual-hash leakage detection (imagehash.phash) — scalable index.

Finds identical and near-duplicate images WITHIN one dataset or ACROSS two
datasets. Cross-dataset near-duplicates between a training source and an
evaluation set are the ones that invalidate a generalization claim.

Design (replaces the previous O(N^2) all-pairs scan):
  * **exact** duplicates via a hash -> members dictionary (O(N));
  * **near** duplicates via a **BK-tree** over Hamming distance (sub-linear
    average query), so 54k-scale intra checks are feasible;
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
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

PHASH_ALGORITHM = "imagehash.phash"
DEFAULT_HASH_SIZE = 8  # 64-bit hash
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
    # int.bit_count() (Py3.10+) is a C-level popcount — far faster than numpy in
    # the BK-tree hot loop, which dominates near-duplicate query cost.
    return (int(a) ^ int(b)).bit_count()


def hamming_hex(a: str, b: str) -> int:
    return hamming_int(int(a, 16), int(b, 16))


def _band_defs(threshold: int, bits: int = 64) -> list[tuple[int, int]]:
    """Split ``bits`` into (threshold+1) contiguous bands. Returns [(shift, mask)].

    Pigeonhole: two hashes within Hamming ``threshold`` must match exactly on at
    least one band, so banding never misses a true near-duplicate.
    """
    b = threshold + 1
    base = bits // b
    defs, shift = [], 0
    for i in range(b):
        width = base + ((bits - base * b) if i == b - 1 else 0)
        defs.append((shift, (1 << width) - 1))
        shift += width
    return defs


# --------------------------------------------------------------------------- #
# BK-tree over Hamming distance (for near-duplicate queries)
# --------------------------------------------------------------------------- #
class BKTree:
    """Burkhard-Keller tree keyed by 64-bit integer hashes.

    Stores (key, payload) items; `query(key, max_dist)` returns all items within
    Hamming distance `max_dist`. Average query cost is sub-linear, far better
    than the all-pairs O(N^2) scan for large N.
    """

    __slots__ = ("_root",)

    def __init__(self):
        self._root = None  # (key, payload, {dist: child_node})

    def add(self, key: int, payload) -> None:
        key = int(key)
        if self._root is None:
            self._root = [key, payload, {}]
            return
        node = self._root
        while True:
            d = hamming_int(key, node[0])
            child = node[2].get(d)
            if child is None:
                node[2][d] = [key, payload, {}]
                return
            node = child

    def query(self, key: int, max_dist: int) -> list[tuple[int, object, int]]:
        key = int(key)
        if self._root is None:
            return []
        out: list[tuple[int, object, int]] = []
        stack = [self._root]
        while stack:
            node = stack.pop()
            d = hamming_int(key, node[0])
            if d <= max_dist:
                out.append((node[0], node[1], d))
            lo, hi = d - max_dist, d + max_dist
            for edge, child in node[2].items():
                if lo <= edge <= hi:
                    stack.append(child)
        return out


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


def find_duplicates(
    index_a: pd.DataFrame,
    index_b: Optional[pd.DataFrame] = None,
    threshold: int = 5,
    hash_size: int = DEFAULT_HASH_SIZE,
) -> dict:
    """Exact (distance 0) and near (0 < d <= threshold) duplicate pairs.

    ``index_b=None`` -> intra-dataset (i<j, no self/reversed pairs). Otherwise
    cross-dataset. Uses a hash-dictionary for exact and a BK-tree for near.
    Returns {"exact": DataFrame, "near": DataFrame, "summary": dict}.
    """
    a = index_a.reset_index(drop=True)
    intra = index_b is None
    b = a if intra else index_b.reset_index(drop=True)
    ka = [int(h, 16) for h in a["phash"]] if len(a) else []
    kb = [int(h, 16) for h in b["phash"]] if len(b) else []

    # ---- exact: hash -> member indices ----
    exact_pairs: list[tuple[int, int]] = []
    if intra:
        buckets: dict[int, list[int]] = {}
        for i, k in enumerate(ka):
            buckets.setdefault(k, []).append(i)
        for members in buckets.values():
            for x in range(len(members)):
                for y in range(x + 1, len(members)):
                    exact_pairs.append((members[x], members[y]))
    else:
        from_a: dict[int, list[int]] = {}
        for i, k in enumerate(ka):
            from_a.setdefault(k, []).append(i)
        for j, k in enumerate(kb):
            for i in from_a.get(k, []):
                exact_pairs.append((i, j))

    # ---- near: banded multi-index hashing (distribution-independent, ~O(N)) ----
    # Pigeonhole: if Hamming(a,b) <= t then a,b agree exactly on >=1 of (t+1)
    # bands. Bucket by band value, verify candidates. This avoids the BK-tree's
    # degenerate behaviour on far-apart (uniform) hashes.
    near_pairs: list[tuple[int, int, int]] = []
    if threshold >= 1 and ka and kb:
        bands = _band_defs(threshold)
        candidates: set[tuple[int, int]] = set()
        for shift, mask in bands:
            from_a: dict[int, list[int]] = {}
            for i, k in enumerate(ka):
                from_a.setdefault((k >> shift) & mask, []).append(i)
            if intra:
                for members in from_a.values():
                    m = len(members)
                    for x in range(m):
                        for y in range(x + 1, m):
                            i, j = members[x], members[y]
                            candidates.add((i, j) if i < j else (j, i))
            else:
                for j, k in enumerate(kb):
                    for i in from_a.get((k >> shift) & mask, []):
                        candidates.add((i, j))
        for i, j in candidates:
            d = hamming_int(ka[i], kb[j])
            if 0 < d <= threshold:
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
        "n_a": int(len(a)),
        "n_b": int(len(b)),
        "datasets_a": sorted(a["dataset"].unique().tolist()) if len(a) else [],
        "datasets_b": sorted(b["dataset"].unique().tolist()) if len(b) else [],
        "n_exact_pairs": int(len(exact)),
        "n_near_pairs": int(len(near)),
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
def benchmark(sizes: Sequence[int] = (636, 2600, 18000, 54000), threshold: int = 5, seed: int = 0) -> pd.DataFrame:
    """Measure BK-tree build+query time on synthetic 64-bit hashes."""
    import time

    rng = np.random.default_rng(seed)
    rows = []
    for n in sizes:
        keys = rng.integers(0, 2**64, size=n, dtype=np.uint64)
        idx = build_index([{"dataset": "synthetic", "path": str(i), "phash": format(int(k), "016x")}
                           for i, k in enumerate(keys)])
        t0 = time.perf_counter()
        res = find_duplicates(idx, threshold=threshold)
        dt = time.perf_counter() - t0
        rows.append({
            "n": n, "seconds": round(dt, 3),
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
    args = ap.parse_args(argv)

    if args.benchmark:
        print(benchmark().to_string(index=False))
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
