#!/usr/bin/env python3
"""Report which generated numbers moved, and which prose sentences cite them.

    python scripts/ica26_macro_drift.py --snapshot   # record current values
    python scripts/ica26_macro_drift.py              # regenerate and compare

The paper's prose is written by hand around values that this repository
generates. When a rebuild changes a value --- a new seed landing, a rerun
replacing a result --- the surrounding sentence can quietly stop being true:
"significantly better" survives a third decimal place moving, but not a sign
flip or a p-value crossing 0.05.

Rewriting that sentence automatically would be worse than leaving it wrong,
because only the author knows what the sentence was meant to claim. So this
tool does not touch the prose. It reports, for every macro whose value moved,
the exact lines of the paper that cite it, so the author can decide.

Snapshots live in ``experiments/ica26/metrics/macro_snapshot.json``.

Exit codes: 0 no drift, 1 drift found (or no snapshot to compare against).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = REPO / "experiments/ica26/metrics/macro_snapshot.json"
TEX_SOURCES = ["paper/ica2026.tex", "paper/supplementary.tex"]

MACRO_DEF = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$", re.MULTILINE)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "ica26_build_paper_macros", REPO / "scripts/ica26_build_paper_macros.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def current_macros() -> dict[str, str]:
    """Build macros in memory; does not write the macro file."""
    text, _ = _load_generator().build()
    return {m.group(1): m.group(2) for m in MACRO_DEF.finditer(text)}


def citations(macro: str) -> list[tuple[str, int, str]]:
    """Every prose line citing this macro, as (file, line number, text).

    Matched with a trailing non-letter so ``\\AccXdRn`` does not also match
    ``\\AccXdRnMean``.
    """
    pattern = re.compile(rf"\\{macro}(?![A-Za-z])")
    hits = []
    for relpath in TEX_SOURCES:
        path = REPO / relpath
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("%"):
                continue
            if pattern.search(line):
                hits.append((relpath, line_no, line.strip()))
    return hits


def sentence_around(relpath: str, line_no: int, span: int = 2) -> str:
    """A few lines of context, since a claim rarely fits on one line."""
    lines = (REPO / relpath).read_text().splitlines()
    lo = max(0, line_no - 1 - span)
    hi = min(len(lines), line_no + span)
    return " ".join(l.strip() for l in lines[lo:hi] if not l.lstrip().startswith("%"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true",
                    help="record current macro values as the comparison baseline")
    ap.add_argument("--context", action="store_true",
                    help="print surrounding prose for each cited change")
    args = ap.parse_args()

    macros = current_macros()

    if args.snapshot:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps({
            "schema": "ica26.macro_snapshot/1",
            "created_at_utc": dt.datetime.now(dt.timezone.utc)
                                .replace(microsecond=0).isoformat(),
            "macros": macros,
        }, indent=2, sort_keys=True) + "\n")
        print(f"snapshot written: {SNAPSHOT.relative_to(REPO)}")
        print(f"macros recorded : {len(macros)}")
        return 0

    if not SNAPSHOT.exists():
        print(f"no snapshot at {SNAPSHOT.relative_to(REPO)}; "
              "run with --snapshot first", file=sys.stderr)
        return 1

    before = json.loads(SNAPSHOT.read_text())["macros"]
    added = sorted(set(macros) - set(before))
    removed = sorted(set(before) - set(macros))
    changed = sorted(k for k in set(macros) & set(before) if macros[k] != before[k])

    print(f"baseline : {SNAPSHOT.relative_to(REPO)}")
    print(f"macros   : {len(before)} -> {len(macros)}")
    print(f"changed  : {len(changed)} | added: {len(added)} | removed: {len(removed)}")

    if removed:
        print("\nREMOVED (a citing sentence would fail to compile):")
        for name in removed:
            cites = citations(name)
            marker = f"  <-- CITED at {len(cites)} place(s)" if cites else ""
            print(f"  \\{name}{marker}")
            for relpath, line_no, _ in cites:
                print(f"      {relpath}:{line_no}")

    cited_changes = [(k, citations(k)) for k in changed]
    with_cites = [(k, c) for k, c in cited_changes if c]
    without = [k for k, c in cited_changes if not c]

    if with_cites:
        print(f"\nCHANGED AND CITED IN PROSE ({len(with_cites)}) "
              "-- review the surrounding claim:")
        for name, cites in with_cites:
            print(f"\n  \\{name}")
            print(f"    was : {before[name]}")
            print(f"    now : {macros[name]}")
            for relpath, line_no, text in cites:
                print(f"    {relpath}:{line_no}")
                if args.context:
                    print(f"      ...{sentence_around(relpath, line_no)}...")
                else:
                    print(f"      {text[:110]}")

    if without:
        print(f"\nCHANGED, NOT CITED IN PROSE ({len(without)}) "
              "-- tables only, no sentence to review:")
        for name in without:
            print(f"  \\{name}: {before[name]} -> {macros[name]}")

    if added:
        print(f"\nADDED ({len(added)}):")
        for name in added:
            print(f"  \\{name} = {macros[name]}")

    if not (changed or added or removed):
        print("\nno drift")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
