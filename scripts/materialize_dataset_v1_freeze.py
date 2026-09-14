#!/usr/bin/env python
"""Materialize or validate the deterministic Dataset V1 technical freeze.

Usage::

    python scripts/materialize_dataset_v1_freeze.py --check
    python scripts/materialize_dataset_v1_freeze.py --write

``--write`` never creates a human approval.  It only writes the canonical
technical record after the separately recorded human approval, all bound inputs,
and the fully satisfied pre-decision readiness assessment have validated.  The
working tree must be clean before the write; commit the newly written record by
itself, then run ``--check`` from that committed checkout.
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

from ica26.governance.freeze import (  # noqa: E402
    FREEZE_ARTIFACT_PATH,
    FreezeError,
    _worktree_problem,
    build_freeze_payload,
    validate_freeze_file,
)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _check() -> int:
    try:
        verdict = validate_freeze_file(repo=REPO, require_clean_worktree=True)
    except Exception as exc:  # noqa: BLE001 - a checker crash is a hard refusal
        print("[dataset-v1-freeze] CHECK ERROR — technical validator failed: "
              f"{type(exc).__name__}: {exc}")
        return 3
    print(f"[dataset-v1-freeze] frozen={verdict.frozen}")
    if verdict.valid:
        print("[dataset-v1-freeze] CHECK OK — technical freeze record is current and auditable")
        return 0
    print("[dataset-v1-freeze] CHECK BLOCKED — " + verdict.detail())
    for issue in verdict.violations:
        print("  BLOCKED:", issue)
    # Absence means the scientific workflow has not frozen the dataset. A
    # present-but-invalid record is a hard control-plane failure, not merely an
    # outstanding human decision.
    return 3 if verdict.present else 1


def _write() -> int:
    target = REPO / FREEZE_ARTIFACT_PATH
    if target.exists():
        verdict = validate_freeze_file(repo=REPO, require_clean_worktree=True)
        if verdict.valid:
            print("[dataset-v1-freeze] existing technical freeze record is already valid; "
                  "refusing to rewrite it")
            return 0
        print("[dataset-v1-freeze] BLOCKED — an invalid freeze record already exists; "
              "refusing to overwrite audit evidence")
        for issue in verdict.violations:
            print("  BLOCKED:", issue)
        return 1

    dirty = _worktree_problem(REPO)
    if dirty:
        print("[dataset-v1-freeze] BLOCKED — " + dirty)
        print("  Commit the approved inputs and current readiness assessment before "
              "materializing the technical record.")
        return 1

    try:
        payload = build_freeze_payload(REPO)
    except FreezeError as exc:
        print("[dataset-v1-freeze] BLOCKED — " + str(exc))
        return 1

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_write(target, text)
    print(f"[dataset-v1-freeze] wrote {FREEZE_ARTIFACT_PATH}")
    print("[dataset-v1-freeze] no human decision was created or changed. Commit this "
          "one technical record, then run --check from the clean committed checkout.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="materialize-dataset-v1-freeze")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="validate an existing committed technical freeze record (default)")
    group.add_argument("--write", action="store_true",
                       help="write a new record only after all frozen inputs validate")
    args = parser.parse_args(argv)
    return _write() if args.write else _check()


if __name__ == "__main__":
    raise SystemExit(main())
