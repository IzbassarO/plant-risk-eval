#!/usr/bin/env python
"""Transcribe approved human-review rows into the canonical action mapping.

    python scripts/apply_action_mapping_review.py            # validate + write
    python scripts/apply_action_mapping_review.py --dry-run  # validate only
    python scripts/apply_action_mapping_review.py --check    # fail if output is stale

Reads (never writes):
    data/mapping/action_mapping_review.csv
    configs/evaluation_scope.yaml

Writes (atomically, only when validation is clean):
    data/mapping/action_mapping_approved.csv
    data/mapping/action_mapping_apply_summary.json

Guarantees:
  * ``candidate_action_class`` is copied to ``action_class`` ONLY for a row a
    human marked ``review_status=approved``.
  * ``needs_review`` / ``pending`` / ``excluded`` rows are never emitted.
  * Classes recorded out of action-evaluation scope are never emitted.
  * Every emitted row is re-validated by ``ica26.mapping.validation`` -- the same
    evidence gate (and the same narrow healthy exemption) used everywhere else.
  * Fail-closed: any error writes nothing and exits non-zero.
  * Deterministic: rows sorted by (dataset, dataset_class); the summary carries
    the input SHA-256 rather than a timestamp, so repeat runs are byte-identical.

Exit codes: 0 = ok, 1 = validation failed (nothing written), 2 = missing input,
3 = ``--check`` found the output out of date.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:  # run without installing the package
    sys.path.insert(0, str(SRC))

from ica26.evaluation.scope import load_scope, validate_scope  # noqa: E402
from ica26.mapping.review import (  # noqa: E402
    apply_review,
    read_review,
    write_canonical,
)

REVIEW_CSV = Path("data/mapping/action_mapping_review.csv")
SCOPE_YAML = Path("configs/evaluation_scope.yaml")
OUT_CSV = Path("data/mapping/action_mapping_approved.csv")
OUT_JSON = Path("data/mapping/action_mapping_apply_summary.json")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="apply-action-mapping-review",
        description="Transcribe approved review rows into the canonical action mapping.",
    )
    ap.add_argument("--review-csv", default=str(REVIEW_CSV))
    ap.add_argument("--scope-yaml", default=str(SCOPE_YAML))
    ap.add_argument("--out-csv", default=str(OUT_CSV))
    ap.add_argument("--out-json", default=str(OUT_JSON))
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and report; write nothing")
    ap.add_argument("--check", action="store_true",
                    help="validate and fail if the on-disk output differs (CI mode)")
    args = ap.parse_args(argv)

    review_path = (REPO / args.review_csv) if not Path(args.review_csv).is_absolute() else Path(args.review_csv)
    scope_path = (REPO / args.scope_yaml) if not Path(args.scope_yaml).is_absolute() else Path(args.scope_yaml)
    out_csv = (REPO / args.out_csv) if not Path(args.out_csv).is_absolute() else Path(args.out_csv)
    out_json = (REPO / args.out_json) if not Path(args.out_json).is_absolute() else Path(args.out_json)

    if not review_path.exists():
        print(f"[apply-mapping] review CSV not found: {args.review_csv}")
        return 2

    scope = None
    if scope_path.exists():
        scope_res = validate_scope(scope_path)
        for i in scope_res.errors:
            print(f"  ERROR  scope {i.where}: {i.message}")
        if not scope_res.ok:
            print("[apply-mapping] evaluation scope is invalid; nothing written")
            return 1
        scope = load_scope(scope_path)
    else:
        print(f"[apply-mapping] note: no scope config at {args.scope_yaml}; "
              "no class is treated as out of scope")

    review_df = read_review(review_path)
    canonical, res, summary = apply_review(
        review_df, scope=scope, review_source=args.review_csv,
    )

    summary = {
        "review_source": args.review_csv,
        "review_source_sha256": sha256_of(review_path),
        "scope_source": args.scope_yaml if scope is not None else None,
        "scope_source_sha256": sha256_of(scope_path) if scope is not None else None,
        "_determinism_note": "no timestamp is recorded; repeat runs on the same "
                             "inputs produce byte-identical output",
        **summary,
    }

    print(f"[apply-mapping] review rows={summary['review_rows']} "
          f"statuses={summary['review_status_counts']}")
    print(f"[apply-mapping] emitted={summary['emitted_rows']} "
          f"(healthy={summary['emitted_healthy_rows']}, "
          f"disease={summary['emitted_disease_rows']}) "
          f"actions={summary['action_class_counts']}")
    if summary["scope_out_of_action_evaluation"]:
        print("[apply-mapping] out of action-evaluation scope (never emitted): "
              + ", ".join(summary["scope_out_of_action_evaluation"]))
    for i in res.errors:
        print(f"  ERROR  {i.where}: {i.message}")
    for i in res.warnings:
        print(f"  WARN   {i.where}: {i.message}")

    if not res.ok:
        print(f"[apply-mapping] FAILED ({res.summary()}); nothing written")
        return 1

    csv_text = canonical.to_csv(index=False, lineterminator="\n")
    json_text = json.dumps(summary, indent=2, sort_keys=False) + "\n"

    if args.dry_run:
        print("[apply-mapping] dry-run: validation OK; nothing written")
        return 0

    if args.check:
        stale = []
        if not out_csv.exists() or out_csv.read_text(encoding="utf-8") != csv_text:
            stale.append(args.out_csv)
        if not out_json.exists() or out_json.read_text(encoding="utf-8") != json_text:
            stale.append(args.out_json)
        if stale:
            print("[apply-mapping] CHECK FAILED — out of date: " + ", ".join(stale))
            return 3
        print("[apply-mapping] check OK — output matches the review decisions")
        return 0

    write_canonical(canonical, out_csv)
    atomic_write_text(out_json, json_text)
    print(f"[apply-mapping] wrote {args.out_csv} and {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
