"""Portability / anonymity validator.

Fails when paper-facing generated artifacts contain machine-specific or personal
identifiers (absolute home paths, usernames, emails, scratch mounts). Manifests,
mappings, leakage outputs and remediation reports must use repository-relative or
dataset-relative paths only. This protects the double-blind submission.

By default it scans the GENERATED artifacts (manifests, mappings, leakage
outputs, remediation reports, package source) and NOT the human-authored source
documents that legitimately quote a machine path while describing the problem
(the audit report, the brief). Those are listed in DEFAULT_EXCLUDES.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable

from .schemas import ValidationResult

# Personal / machine-specific patterns that must not appear in paper artifacts.
FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    ("unix_home", r"/Users/[^/\s\"']+"),
    ("linux_home", r"/home/[^/\s\"']+"),
    ("windows_home", r"[A-Za-z]:\\\\Users\\\\[^\\\s\"']+"),
    ("scratch_mount", r"/private/tmp/claude[^\s\"']*"),
    ("username", r"\bizbassar\b"),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
]
# Emails that are legitimately public (conference contacts) — allow-list.
ALLOWED_EMAILS = {"ica@iitrpr.ac.in", "enquiries@cabi.org", "noreply@anthropic.com"}

_COMPILED = [(name, re.compile(pat)) for name, pat in FORBIDDEN_PATTERNS]

# Paper-facing generated artifacts to scan by default.
DEFAULT_INCLUDE_GLOBS = [
    "data/manifests/*.csv", "data/manifests/*.json",
    "data/mapping/*.csv",
    "data/exclusions/*.csv",
    "data/interim/*.csv",
    # Preserved human-review evidence is submitted alongside the paper, and a
    # reviewer's scratch path or account name would deanonymise them as surely
    # as it would us.
    "human_review/**/*.csv", "human_review/**/*.json", "human_review/**/*.md",
    "reports/leakage_*.csv", "reports/leakage_*.json",
    "reports/*REMEDIATION*.md",
    # Freeze-readiness and governance artifacts quote artifact paths back to the
    # reader; an unrelativised one would leak a home directory.
    "reports/dataset_v1_*.json", "reports/DATASET_V1_*.md",
    "reports/plantdoc_*_gate.json",
    "reports/plantdoc_label_second_review/*.csv",
    "reports/plantdoc_label_second_review/*.json",
    "reports/plantdoc_label_second_review/*.md",
    "reports/PLANTDOC_COUNT_RECONCILIATION.md",
    "reports/ACTION_MAPPING_REVIEW_PACKET.md",
    "src/**/*.py",
]
# Human-authored inputs that legitimately quote a machine path while *describing*
# the problem, plus backups — excluded from the gate.
DEFAULT_EXCLUDES = [
    "reports/PHASE1_CODEX_AUDIT.md",
    "reports/PHASE1_REPORT.md",
    "PROJECT_BRIEF.md",
    "DATASETS.md",
    "src/ica26/portability.py",   # this file defines the patterns -> self-match
]


def scan_text(text: str) -> list[tuple[str, str]]:
    """Return (pattern_name, matched_substring) for each forbidden hit."""
    hits: list[tuple[str, str]] = []
    for name, rx in _COMPILED:
        for m in rx.finditer(text):
            s = m.group(0)
            if name == "email" and s in ALLOWED_EMAILS:
                continue
            hits.append((name, s))
    return hits


def scan_file(path: str | Path) -> list[tuple[str, str]]:
    try:
        text = Path(path).read_text(errors="ignore")
    except Exception:
        return []
    return scan_text(text)


def _iter_files(include: Iterable[str], excludes: Iterable[str], root: Path) -> list[Path]:
    exclude_set = {str((root / e)) for e in excludes}
    files: list[Path] = []
    for pattern in include:
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            if "_remediation_backup_" in str(p) or "/.venv/" in str(p) or "__pycache__" in str(p):
                continue
            if str(p) in exclude_set:
                continue
            files.append(p)
    return files


def validate_portability(
    root: str | Path = ".",
    include: Iterable[str] = DEFAULT_INCLUDE_GLOBS,
    excludes: Iterable[str] = DEFAULT_EXCLUDES,
) -> ValidationResult:
    root = Path(root)
    res = ValidationResult()
    for f in _iter_files(include, excludes, root):
        for name, sample in scan_file(f):
            res.add("error", str(f.relative_to(root)), f"{name}: '{sample}'")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-portability", description="Fail on machine-specific paths in paper artifacts.")
    ap.add_argument("--root", default=".")
    ap.add_argument("paths", nargs="*", help="optional explicit files to scan instead of default globs")
    args = ap.parse_args(argv)
    if args.paths:
        res = ValidationResult()
        for p in args.paths:
            for name, sample in scan_file(p):
                res.add("error", p, f"{name}: '{sample}'")
    else:
        res = validate_portability(args.root)
    if res.ok:
        print("[portability] OK — no machine-specific/personal identifiers in scanned artifacts")
        return 0
    for i in res.errors:
        print(f"  LEAK  {i.where}: {i.message}")
    print(f"[portability] FAIL — {len(res.errors)} machine-specific/personal identifier(s) found")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
