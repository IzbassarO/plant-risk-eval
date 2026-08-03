#!/usr/bin/env python
"""Apply the HUMAN adjudication of PlantDoc byte-exact duplicate groups (R2B).

    python scripts/apply_plantdoc_duplicate_adjudication.py
    python scripts/apply_plantdoc_duplicate_adjudication.py --check

Reads the decisions a human recorded in the review packet's groups CSV and
materialises two derived artifacts:

    data/exclusions/plantdoc_internal_duplicate_resolution.csv
        one row per reviewed record: what the decision was, which record was
        retained as canonical, which were removed, and with what label and split

    data/manifests/plantdoc_effective_manifest.csv
        the PlantDoc component of the effective Dataset V1 -- the manifest with
        the adjudicated exclusions removed and the adjudicated label and split
        applied to each retained canonical record

This script decides nothing. Every exclusion, label, and split it writes is read
from a decision row; a group without a terminal, remediable decision stops the
run. It also moves, deletes, and rewrites no image: the source manifest and the
pixels on disk are untouched, and the retained record's label and split are
*overridden* in the effective manifest with both values recorded in the
resolution table.

Idempotent and deterministic: the outputs are a pure function of the manifest
and the decisions, canonically ordered, with no wall-clock field, so a second
run reproduces them byte for byte.

Exit codes: 0 ok, 1 refused (unresolved or unauthorised decisions) or stale
(--check), 2 missing input.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.duplicate_remediation import (  # noqa: E402
    RESOLUTION_COLUMNS,
    apply_adjudication,
    build_effective_records,
    resolution_rows,
    verify_effective_records,
)
from ica26.datasets.duplicates import find_duplicate_groups  # noqa: E402
from ica26.schemas import IMAGE_MANIFEST_COLUMNS  # noqa: E402

MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
COLLISION_MAP = Path("data/manifests/plantdoc_case_collision_mapping.csv")
ACTIVE_ROOT = Path("data/raw/plantdoc")
GROUPS_CSV = Path("reports/plantdoc_exact_duplicate_review/plantdoc_exact_duplicate_groups.csv")
RESOLUTION = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
EFFECTIVE = Path("data/manifests/plantdoc_effective_manifest.csv")
SOURCE_REVISION = "5467f6012d78d1c446145d5f582da6096f852ae8"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def render_csv(columns, rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def build(repo: Path = REPO) -> tuple[str, str, dict]:
    """Render both artifacts and the verification report. Writes nothing."""
    manifest = read_csv(repo / MANIFEST)

    original_of = {}
    if (repo / COLLISION_MAP).exists():
        for r in read_csv(repo / COLLISION_MAP):
            original_of[r["collision_safe_relative_path"]] = r["original_archive_path"]

    groups = find_duplicate_groups(
        manifest, dataset="PlantDoc", source_revision=SOURCE_REVISION,
        active_root=repo / ACTIVE_ROOT, original_path_of=original_of)

    decisions = read_csv(repo / GROUPS_CSV) if (repo / GROUPS_CSV).exists() else []
    adj = apply_adjudication(groups, decisions)
    effective, build_violations = build_effective_records(manifest, adj)
    verify_violations, report = verify_effective_records(manifest, effective, adj, groups)

    report["violations"] = sorted(adj.violations + build_violations + verify_violations)
    report["ok"] = not report["violations"]
    return (render_csv(RESOLUTION_COLUMNS, resolution_rows(adj)),
            render_csv(IMAGE_MANIFEST_COLUMNS, effective),
            report)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apply-plantdoc-duplicate-adjudication")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted artifacts match a fresh rebuild; write nothing")
    args = ap.parse_args(argv)

    if not (REPO / MANIFEST).exists():
        print(f"[dup-remediation] manifest not found: {MANIFEST}")
        return 2
    if not (REPO / GROUPS_CSV).exists():
        print(f"[dup-remediation] no adjudication at {GROUPS_CSV}; nothing to apply. "
              "Run scripts/build_plantdoc_duplicate_packet.py and have a human decide.")
        return 2

    resolution_text, effective_text, report = build()

    print(f"[dup-remediation] groups={report['groups']} "
          f"reviewed_records={report['reviewed_records']} "
          f"retained={report['retained_records']} excluded={report['excluded_records']}")
    print(f"[dup-remediation] source_records={report['source_records']} -> "
          f"effective_records={report['effective_records']} "
          f"(removed {report['removed_records']}) "
          f"surviving_exact_duplicate_groups={report['surviving_exact_duplicate_groups']}")

    if not report["ok"]:
        print(f"[dup-remediation] REFUSED — {len(report['violations'])} violation(s); "
              "nothing was written")
        for v in report["violations"][:10]:
            print(f"  VIOLATION {v}")
        return 1

    if args.check:
        stale = []
        for path, text in ((RESOLUTION, resolution_text), (EFFECTIVE, effective_text)):
            target = REPO / path
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                stale.append(str(path))
        if stale:
            print("[dup-remediation] CHECK FAILED — out of date: " + ", ".join(stale))
            return 1
        print("[dup-remediation] check OK — persisted artifacts match a fresh rebuild")
        return 0

    atomic_write_text(REPO / RESOLUTION, resolution_text)
    atomic_write_text(REPO / EFFECTIVE, effective_text)
    print(f"[dup-remediation] wrote {RESOLUTION}")
    print(f"[dup-remediation] wrote {EFFECTIVE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
