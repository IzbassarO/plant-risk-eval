#!/usr/bin/env python3
"""Validate the ICA 2026 paper experiment dataset lock.

Every training command runs this first. If any locked digest, identity set,
count, label, split, or class mapping has changed, it exits non-zero and the
training command aborts.

    python scripts/ica26_validate_experiment_lock.py
    python scripts/ica26_validate_experiment_lock.py --check-pixels

Exit codes: 0 valid, 1 one or more violations, 2 the lock is absent.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ica26.experiments import lock as L  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-pixels", action="store_true",
                    help="also confirm every manifest row resolves to a file on disk")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = ap.parse_args()

    try:
        report = L.validate(REPO, check_pixels=args.check_pixels)
    except L.LockValidationError as exc:
        print(f"LOCK ABSENT: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"schema        : {report['schema']}")
        print(f"lock_digest   : {report['lock_digest']}")
        print(f"built at commit: {report['repository_commit_at_lock_time']}")
        print(f"pixels checked: {report['checked_pixels']}")
        if report["ok"]:
            print("VALID: every locked digest, count, taxonomy, split, and mapping matches")
        else:
            print(f"INVALID: {len(report['violations'])} violation(s)", file=sys.stderr)
            for v in report["violations"]:
                print(f"  - {v}", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
