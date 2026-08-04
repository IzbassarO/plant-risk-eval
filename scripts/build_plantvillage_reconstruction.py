#!/usr/bin/env python
"""Record the PlantVillage exact-reconstruction result as evidence (R2B.2 Part 5).

    python scripts/build_plantvillage_reconstruction.py
    python scripts/build_plantvillage_reconstruction.py --check

Reconstruction re-derives all 54,305 record identities from the pinned split
files and leaf map, which is what closes the "fabricated manifest with a
self-consistent digest" hole. Doing that needs the pinned sources: the optional
``hf`` extra plus the Hugging Face cache at the pinned revision.

Readiness must not depend on whether those happen to be present. A fresh clone
with only the core dependencies would otherwise produce a *different* readiness
artifact from the same commit, which would make ``--check`` unpassable and teach
a reader to ignore it. So the reconstruction result is persisted here as
digest-bound evidence, exactly like every other artifact the readiness
assessment reads, and the readiness condition validates the evidence rather than
re-running the derivation.

The binding is what makes that safe: the record carries the SHA-256 of the
manifest it was computed from, so it cannot outlive the file it describes. Change
the manifest and the evidence goes stale; the condition then blocks until someone
with the pinned sources re-derives it.

Exit codes: 0 ok, 1 reconstruction failed or stale (--check), 2 sources absent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

MANIFEST = Path("data/manifests/plantvillage_manifest.csv")
IMAGES_ROOT = Path("data/raw/plantvillage/extracted")
OUT = Path("reports/plantvillage_manifest_reconstruction.json")


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def build(repo: Path = REPO, *, verify_pixels: bool = True) -> tuple[str, dict, list]:
    from ica26.datasets import plantvillage as PV

    images_root = repo / IMAGES_ROOT
    problems, report = PV.validate_manifest_reconstruction(
        repo / MANIFEST, config="color",
        images_root=images_root if (verify_pixels and images_root.is_dir()) else None)
    report = dict(report)
    report["problems"] = problems
    # Deliberately no wall-clock field: this artifact is committed and compared
    # byte-for-byte.
    return json.dumps(report, indent=2, sort_keys=True) + "\n", report, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plantvillage-reconstruction")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted record matches a fresh reconstruction")
    ap.add_argument("--skip-pixel-verification", action="store_true")
    args = ap.parse_args(argv)

    try:
        text, report, problems = build(
            REPO, verify_pixels=not args.skip_pixel_verification)
    except Exception as exc:  # noqa: BLE001
        print(f"[pv-reconstruction] pinned sources unavailable: "
              f"{type(exc).__name__}: {exc}")
        print("[pv-reconstruction] install the optional 'hf' extra and populate "
              "the Hugging Face cache at the pinned revision")
        return 2

    print(f"[pv-reconstruction] derived {report['expected_records']} record(s) "
          f"({report['expected_train']} train / {report['expected_test']} test) "
          f"from the pinned sources; persisted {report['persisted_records']}")
    print(f"[pv-reconstruction] missing={report['missing_records']} "
          f"extra={report['extra_records']} "
          f"duplicated={report['duplicated_identities']} "
          f"mismatches={report['value_mismatches']} "
          f"order_matches={report['order_matches']}")

    if problems:
        print(f"[pv-reconstruction] REFUSED — {len(problems)} problem(s)")
        for p in problems[:10]:
            print(f"  PROBLEM {p}")
        return 1

    if args.check:
        target = REPO / OUT
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print(f"[pv-reconstruction] CHECK FAILED — out of date: {OUT}")
            return 1
        print("[pv-reconstruction] check OK — record matches a fresh reconstruction")
        return 0

    atomic_write_text(REPO / OUT, text)
    print(f"[pv-reconstruction] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
