#!/usr/bin/env python3
"""Verify the table generator after the escaping and separator fixes.

Run this after regenerating. It is deliberately paranoid about the one thing
that matters most: a formatting fix must not move a single number.

    # before touching the generator, snapshot what is currently correct
    python scripts/ica26_verify_tables.py snapshot --tables experiments/ica26/tables

    # after regenerating
    python scripts/ica26_verify_tables.py check --tables experiments/ica26/tables

Checks
------
1. DOUBLE ESCAPING  -- no ``\\textbackslash`` and no ``\\$`` survives anywhere.
   This is the defect that already shipped twice.

2. UNRESOLVED UNICODE  -- no bare ``±``, ``→``, ``≤``, ``×``, ``−`` in the .tex.
   THIS IS THE REGRESSION TO WATCH. The old ica26_significance.py ended with

       for raw, tex in (("±", r"$\\pm$"), ("→", r"$\\rightarrow$"), ...):
           latex = latex.replace(raw, tex)

   That loop was doing real work: the DataFrames hold ``0.9945 ± 0.0021`` with a
   Unicode ``±``, and pandas' escape=True passes ``±`` through untouched, so the
   loop was what turned it into ``$\\pm$``. Removing the loop is correct ONLY if
   ``cell()`` now carries a Unicode-to-LaTeX map. If it does not, every table
   silently gains raw UTF-8 that pdfLaTeX rejects with
   "Unicode character ± not set up for use with LaTeX".

3. IDENTIFIERS NOT SEPARATED  -- a Seed column must contain 1337, never 1\\,337.

4. VALUES UNCHANGED  -- every numeric token in every table matches the snapshot
   once thousands separators are normalised away. A formatting change that moves
   a digit is not a formatting change.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOUBLE_ESCAPE = [
    (r"\textbackslash", "двойное экранирование: LaTeX-разметка была экранирована"),
    (r"\$\\", "экранированный $ перед управляющей последовательностью"),
]

# Anything the removed replace loop used to convert, plus the neighbours that
# reach a DataFrame the same way.
UNICODE_TRAPS = {
    "\u00b1": r"$\pm$",
    "\u2192": r"$\rightarrow$",
    "\u2264": r"$\leq$",
    "\u2265": r"$\geq$",
    "\u00d7": r"$\times$",
    "\u2212": "-",
    "\u2013": "--",
    "\u2014": "---",
}

IDENTIFIER_HINTS = ("seed",)

NUM = re.compile(r"\d+(?:\\,\d{3})*(?:\.\d+)?")


def numeric_tokens(src: str) -> list[str]:
    """Every number in the file, with thousands separators normalised away."""
    body = re.sub(r"\\caption\{.*?\}\n", "", src, flags=re.S)
    body = re.sub(r"\\label\{[^}]*\}", "", body)
    body = re.sub(r"\\setlength\{\\tabcolsep\}\{[^}]*\}", "", body)
    return [m.group(0).replace("\\,", "") for m in NUM.finditer(body)]


def check_file(path: Path) -> list[str]:
    src = path.read_text()
    problems: list[str] = []

    for needle, why in DOUBLE_ESCAPE:
        if re.search(re.escape(needle), src):
            problems.append(f"[1] {why}: найдено {needle!r}")

    for ch, want in UNICODE_TRAPS.items():
        if ch in src:
            n = src.count(ch)
            problems.append(
                f"[2] голый Unicode {ch!r} ×{n} — должно быть {want!r}. "
                "pdfLaTeX это не соберёт"
            )

    # Identifier columns must not carry a thin space.
    header = re.search(r"\\toprule\n(.*?)\\midrule", src, re.S)
    if header:
        cols = [c.strip() for c in header.group(1).split("&")]
        for i, col in enumerate(cols):
            if any(h in col.lower() for h in IDENTIFIER_HINTS):
                rows = re.search(r"\\midrule\n(.*?)\\bottomrule", src, re.S)
                if rows:
                    for line in rows.group(1).strip().split("\\\\"):
                        cells = line.split("&")
                        if len(cells) > i and "\\," in cells[i]:
                            problems.append(
                                f"[3] столбец {col!r} — идентификатор, "
                                f"а записан как {cells[i].strip()!r}"
                            )
                            break
    return problems


def cmd_snapshot(tables: Path, out: Path) -> int:
    snap = {p.name: numeric_tokens(p.read_text()) for p in sorted(tables.glob("*.tex"))}
    out.write_text(json.dumps(snap, indent=1))
    total = sum(len(v) for v in snap.values())
    print(f"снимок: {len(snap)} файлов, {total} числовых токенов -> {out}")
    return 0


def cmd_check(tables: Path, snap_path: Path) -> int:
    failures = 0

    for path in sorted(tables.glob("*.tex")):
        problems = check_file(path)
        if problems:
            failures += len(problems)
            print(f"\n{path.name}")
            for p in problems:
                print(f"    {p}")

    if snap_path.exists():
        snap = json.loads(snap_path.read_text())
        print()
        for path in sorted(tables.glob("*.tex")):
            before = snap.get(path.name)
            if before is None:
                print(f"[4] {path.name}: нет в снимке (новый файл)")
                continue
            after = numeric_tokens(path.read_text())
            if before != after:
                failures += 1
                moved = [(a, b) for a, b in zip(before, after) if a != b][:3]
                print(f"[4] {path.name}: ЗНАЧЕНИЯ ИЗМЕНИЛИСЬ "
                      f"({len(before)} -> {len(after)} токенов)")
                for a, b in moved:
                    print(f"        {a}  ->  {b}")
                if not moved:
                    print("        расходится только количество токенов")
    else:
        print(f"\n[4] пропущено: снимка нет ({snap_path}). "
              "Сделайте snapshot ДО правок генератора.")

    print()
    if failures:
        print(f"ПРОВАЛ: {failures} проблем")
        return 1
    print("OK: экранирование чистое, Unicode разрешён, значения не сдвинулись")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["snapshot", "check"])
    ap.add_argument("--tables", type=Path, default=Path("experiments/ica26/tables"))
    ap.add_argument("--snapshot", type=Path, default=Path("build/table_numbers.json"))
    args = ap.parse_args()

    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "snapshot":
        sys.exit(cmd_snapshot(args.tables, args.snapshot))
    sys.exit(cmd_check(args.tables, args.snapshot))


if __name__ == "__main__":
    main()
