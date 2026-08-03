#!/usr/bin/env python
"""Checksum manifest for the preserved human-review evidence.

    python scripts/build_human_review_evidence_manifest.py
    python scripts/build_human_review_evidence_manifest.py --check

`human_review/` is the archive of what a human was actually shown and what they
actually decided. Its value is entirely in being unaltered, so it carries the
same kind of manifest the review packets do: SHA-256 of every file, generated
rather than hand-written, with no wall-clock field so it is byte-deterministic
and can be re-derived and compared.

This script only digests. It never edits, moves, or normalises evidence.

Exit codes: 0 ok, 1 stale (--check), 2 nothing to digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = Path("human_review")
MANIFEST_NAME = "evidence_manifest.json"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render(root: Path) -> str:
    entries = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name == MANIFEST_NAME or p.name == ".DS_Store":
            continue
        entries[str(p.relative_to(root)).replace(os.sep, "/")] = sha256_of(p)
    return json.dumps({
        "_note": "SHA-256 of every preserved human-review artifact. Evidence is "
                 "append-only: a decision file is added beside the inputs the "
                 "reviewer saw, never over them. No wall-clock field, so this "
                 "manifest is byte-deterministic and can be re-derived.",
        "root": str(EVIDENCE_DIR),
        "file_count": len(entries),
        "artifacts": entries,
    }, indent=2, sort_keys=True) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build-human-review-evidence-manifest")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted manifest matches the files; write nothing")
    ap.add_argument("--root", default=str(EVIDENCE_DIR))
    args = ap.parse_args(argv)

    root = REPO / args.root
    if not root.exists():
        print(f"[evidence-manifest] no evidence directory at {args.root}")
        return 2

    text = render(root)
    target = root / MANIFEST_NAME
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print(f"[evidence-manifest] CHECK FAILED — {args.root}/{MANIFEST_NAME} is stale")
            return 1
        print("[evidence-manifest] check OK — every preserved artifact matches its digest")
        return 0

    tmp = target.with_name(target.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)
    print(f"[evidence-manifest] wrote {args.root}/{MANIFEST_NAME} "
          f"({json.loads(text)['file_count']} artifact(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
