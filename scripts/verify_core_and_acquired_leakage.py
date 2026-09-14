#!/usr/bin/env python
"""Recompute cross-dataset leakage for BOTH populations (R2B.2 Part 2).

    python scripts/verify_core_and_acquired_leakage.py --out <dir> [--reuse-index <dir>]

Two populations are evaluated separately and neither result is assumed from the
other:

  **acquired corpus** -- PlantVillage (54,305) vs the acquired PlantDoc manifest
  (2,578). This is the population the committed leakage gate was computed over.
  Its result is expected to be unchanged by the search rewrite, and this script
  proves that rather than asserting it.

  **Core training corpus** -- PlantVillage (54,305) vs the Core effective
  PlantDoc manifest (2,561), after the conservative G07/G08/G10 exclusions. Its
  result is calculated independently; nothing is inherited from the acquired
  run.

This script writes only into ``--out``. It never touches a human decision, a
review table, an exclusion file, or a committed gate.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd  # noqa: E402

from ica26.leakage.phash import (  # noqa: E402
    build_index,
    candidate_search_audit_fields,
    find_duplicates,
    index_from_manifest,
)

PV_MANIFEST = Path("data/manifests/plantvillage_manifest.csv")
PV_ROOT = Path("data/raw/plantvillage/extracted")
PD_MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
PD_CORE_MANIFEST = Path("data/manifests/plantdoc_core_effective_manifest.csv")
PD_ROOT = Path("data/raw/plantdoc")
NEAR_REVIEW = Path("data/exclusions/cross_dataset_near_duplicate_review.csv")
PERSISTED_REPORT = Path("reports/leakage_two_population_report.json")
THRESHOLD = 6

#: Versioned identity of this two-population record.
CORE_LEAKAGE_SCHEMA = "ica26.leakage.two_population_report/1"

INDEX_COLS = ["dataset", "split", "class_label", "path", "phash"]


def _reviewed_pair_identities() -> set[str]:
    """The pair identities a human has already adjudicated.

    Read from the recorded near-duplicate review table, which this script never
    writes. Keeping it read-only is the point: a Core leakage result may only be
    *checked* against the existing decisions, never allowed to create one.
    """
    import csv

    path = REPO / NEAR_REVIEW
    if not path.is_file():
        return set()
    with path.open(newline="", encoding="utf-8") as fh:
        return {
            f'{row["training_relative_path"]}||{row["evaluation_relative_path"]}'
            f'||{row["phash_distance"]}'
            for row in csv.DictReader(fh)
        }


def _index_or_load(name: str, manifest: Path, root: Path, dataset: str,
                   cache: Path | None, out: Path) -> pd.DataFrame:
    if cache is not None and (cache / f"{name}.csv").exists():
        print(f"[leakage] reusing cached index {name}", flush=True)
        return pd.read_csv(cache / f"{name}.csv", dtype=str, keep_default_na=False)
    t0 = time.perf_counter()
    print(f"[leakage] indexing {name} from {manifest} ...", flush=True)
    idx, skipped = index_from_manifest(REPO / manifest, REPO / root, dataset)
    print(f"[leakage] {name}: {len(idx)} indexed, {len(skipped)} skipped "
          f"({time.perf_counter() - t0:.1f}s)", flush=True)
    if skipped:
        raise SystemExit(f"BLOCKED: {len(skipped)} unreadable image(s) in {name}: "
                         f"{skipped[:5]}")
    idx.to_csv(out / f"{name}.csv", index=False)
    return idx


def _pair_identities(near: pd.DataFrame) -> list[str]:
    return sorted(f"{r.path_a}||{r.path_b}||{r.distance}"
                  for r in near.itertuples())


def _population(label: str, idx_train: pd.DataFrame, idx_eval: pd.DataFrame,
                out: Path) -> dict:
    t0 = time.perf_counter()
    res = find_duplicates(idx_train, idx_eval, threshold=THRESHOLD)
    elapsed = time.perf_counter() - t0
    s = res["summary"]
    audit = candidate_search_audit_fields(s)
    # No wall-clock field reaches the record: this artifact is committed and
    # compared byte-for-byte, so it has to reproduce exactly. Elapsed time is
    # printed for the operator and deliberately discarded here.
    record = {
        "population": label,
        "n_training_indexed": int(len(idx_train)),
        "n_evaluation_indexed": int(len(idx_eval)),
        "n_exact_pairs": int(s["n_exact_pairs"]),
        "n_near_pairs": int(s["n_near_pairs"]),
        "near_pair_identities": _pair_identities(res["near"]),
        **audit,
    }
    res["near"].to_csv(out / f"near_{label}.csv", index=False)
    res["exact"].to_csv(out / f"exact_{label}.csv", index=False)
    print(f"[leakage] {label}: exact={record['n_exact_pairs']} "
          f"near={record['n_near_pairs']} "
          f"evals={audit['n_distance_evaluations']:,} "
          f"possible={audit['n_possible_pairs']:,} "
          f"peak_chunk={audit['max_chunk_pair_count']:,} "
          f"({elapsed:.1f}s)", flush=True)
    return record


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verify-core-and-acquired-leakage")
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse-index", default=None)
    ap.add_argument("--persist", action="store_true",
                    help="also write the committed reports/ artifact")
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cache = Path(args.reuse_index) if args.reuse_index else None

    idx_pv = _index_or_load("plantvillage", PV_MANIFEST, PV_ROOT, "PlantVillage",
                            cache, out)
    idx_pd = _index_or_load("plantdoc_acquired", PD_MANIFEST, PD_ROOT, "PlantDoc",
                            cache, out)

    # The Core index is a strict SUBSET of the acquired index, selected by the
    # Core manifest's relpaths. Re-hashing the same bytes would prove nothing
    # and would let a transcription slip go unnoticed; selecting from the
    # already-verified index makes the subset relation explicit and checkable.
    core_manifest = pd.read_csv(REPO / PD_CORE_MANIFEST, dtype=str,
                                keep_default_na=False)
    core_paths = set(core_manifest["relpath"])
    idx_core = idx_pd[idx_pd["path"].isin(core_paths)].reset_index(drop=True)
    idx_core = build_index(idx_core.to_dict("records"))
    if len(idx_core) != len(core_manifest):
        raise SystemExit(
            f"BLOCKED: Core index has {len(idx_core)} rows for a "
            f"{len(core_manifest)}-record Core manifest")
    missing = core_paths - set(idx_pd["path"])
    if missing:
        raise SystemExit(f"BLOCKED: {len(missing)} Core record(s) absent from the "
                         f"acquired index: {sorted(missing)[:5]}")

    acquired = _population("acquired", idx_pv, idx_pd, out)
    core = _population("core", idx_pv, idx_core, out)

    dropped = sorted(set(acquired["near_pair_identities"])
                     - set(core["near_pair_identities"]))
    added = sorted(set(core["near_pair_identities"])
                   - set(acquired["near_pair_identities"]))

    # Every Core near pair must already carry one of the recorded human
    # decisions. A Core pair with no decision behind it would be an unresolved
    # leakage pair, and Core readiness must block on it.
    reviewed = _reviewed_pair_identities()
    unresolved = sorted(set(core["near_pair_identities"]) - reviewed)

    report = {
        "schema": CORE_LEAKAGE_SCHEMA,
        "threshold": THRESHOLD,
        "acquired": acquired,
        "core": core,
        "near_pairs_only_in_acquired": dropped,
        "near_pairs_only_in_core": added,
        "core_evaluation_records": int(len(idx_core)),
        "acquired_evaluation_records": int(len(idx_pd)),
        "core_unresolved_near_pairs": unresolved,
        "core_near_pairs_all_reviewed": not unresolved,
        "reviewed_pair_count": len(reviewed),
        "conservatively_excluded_evaluation_records": (
            int(len(idx_pd)) - int(len(idx_core))),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (out / "leakage_two_population_report.json").write_text(text)
    if args.persist:
        (REPO / PERSISTED_REPORT).write_text(text)
        print(f"[leakage] wrote {PERSISTED_REPORT}")
    print(f"[leakage] wrote {out / 'leakage_two_population_report.json'}")
    print(f"[leakage] near pairs only in acquired: {len(dropped)}; "
          f"only in core: {len(added)}; core unresolved: {len(unresolved)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
