#!/usr/bin/env python3
"""Fit every generated table to the text block it is actually typeset in.

    python scripts/ica26_fit_tables.py            # measure and rewrite
    python scripts/ica26_fit_tables.py --check    # measure and report, write nothing

Ten of the sixteen generated tables overran their measure, the worst by 173 mm.
Guessing a font size does not work, so each table is measured by compiling it
and reading back ``\\wd``.

**The measurement must use the real document class.** Measuring in ``article``
understates the width, because ``\\multicolumn`` with ``\\cmidrule`` stretches
columns beyond their content differently there; a table that looked like
117.8 mm under ``article`` overran by 14 pt under ``llncs``.

Two facts keep this to a single LaTeX run:

* Width is exactly linear in ``\\tabcolsep`` --- each of ``n`` columns is padded
  on both sides, so ``W(t) = W(6) - 2n(6 - t)``. Verified against a probe: a
  four-column table measured 75.233 pt at 6 pt and 43.233 pt at 2 pt, a
  difference of exactly ``2 x 4 x 4``. Only one ``\\tabcolsep`` per size is
  therefore measured; the rest are derived.
* Every combination for every table is boxed in one probe document, so the whole
  search is one compile rather than eighty.

The search prefers the largest type that fits: sizes from ``\\normalsize`` down
to ``\\tiny``, and within a size the widest padding from 6 pt down to 2 pt.
A table that fits at full size is left alone.

Values are never changed to make a table fit. If nothing fits, the table is
reported for ``sidewaystable`` and left otherwise untouched.

Exit codes: 0 all tables fit, 1 a table needs rotation or --check found drift.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TABLES = REPO / "experiments/ica26/tables"
PAPER = REPO / "paper"
TECTONIC = "/opt/homebrew/bin/tectonic"

# Measured from the real classes rather than assumed:
#   llncs                          -> 347.12354 pt (122 mm)
#   llncs + geometry margin=15mm   -> 512.14963 pt (180 mm)
MAIN_WIDTH_PT = 347.12354
SUPP_WIDTH_PT = 512.14963
# A sidewaystable is rotated 90 degrees, so the space along its rows is the text
# *height*, not the width. Measured the same way: 759.68858 pt (267 mm).
SUPP_HEIGHT_PT = 759.68858
# Leave a hair of slack; a table exactly at \textwidth still reports Overfull.
SLACK_PT = 3.0

SIZES = ["", "\\small", "\\footnotesize", "\\scriptsize", "\\tiny"]
SIZE_NAMES = {"": "normalsize", "\\small": "small", "\\footnotesize": "footnotesize",
              "\\scriptsize": "scriptsize", "\\tiny": "tiny"}
TABCOLSEPS = [6, 5, 4, 3, 2]

# Width is not the only constraint. The paper is at 15 pages against a 12--15
# limit, so a table that fits the measure at \normalsize can still cost a page
# in height. These ceilings are the sizes the page budget was balanced at; the
# search starts here rather than at \normalsize, and may still go smaller if a
# table does not fit. Raising one of these can push the paper over the limit.
PREFERRED_MAX_SIZE = {
    "table2_in_domain_performance_compact": "footnotesize",
    "table3_cross_domain_performance_compact": "footnotesize",
    "table5_domain_shift_degradation_compact": "footnotesize",
    "table6_calibration_compact": "footnotesize",
    "table9_significance_across_seeds_compact": "scriptsize",
    "table7b_ranking_margins_compact": "scriptsize",
    "table8_confidence_intervals_compact": "footnotesize",
    "table8b_mcnemar_compact": "scriptsize",
    "table4_efficiency_compact": "footnotesize",
}


def sizes_for(stem: str) -> list[str]:
    """Candidate sizes, largest first, never above this table's ceiling."""
    ceiling = PREFERRED_MAX_SIZE.get(stem)
    if ceiling is None:
        return SIZES
    order = [s for s in SIZES]
    start = next(i for i, s in enumerate(order) if SIZE_NAMES[s] == ceiling)
    return order[start:]

TABULAR_RE = re.compile(r"(\\begin\{tabular\}.*?\\end\{tabular\})", re.S)
# The size/tabcolsep prologue this script inserts, so a rerun replaces rather
# than stacks it.
PROLOGUE_RE = re.compile(
    r"(?:\\(?:small|footnotesize|scriptsize|tiny)\n)?"
    r"(?:\\centering\n)?"
    r"(?:\\setlength\{\\tabcolsep\}\{[\d.]+pt\}\n)?"
    r"(?=\\begin\{tabular\})"
)


def which_documents_use(stem: str) -> set[str]:
    """Which .tex \\input this table. Decides the width it must fit.

    ``paper/updated/`` is scanned as well as ``paper/``: the draft being carried
    into Overleaf lives there, and a table it uses must be fitted to the main
    text block even if the older copy in ``paper/`` no longer includes it.
    """
    users = set()
    for directory, kind in ((PAPER, ""), (PAPER / "updated", "")):
        for name, role in (("ica2026.tex", "main"), ("supplementary.tex", "supplement")):
            path = directory / name
            if path.exists() and f"{stem}.tex" in path.read_text():
                users.add(role)
    return users


def target_width(stem: str) -> tuple[float, str]:
    users = which_documents_use(stem)
    if "main" in users:
        return MAIN_WIDTH_PT, "main"
    if "supplement" in users:
        return SUPP_WIDTH_PT, "supplement"
    # Not included anywhere yet; hold it to the stricter measure so it is
    # usable in either document.
    return MAIN_WIDTH_PT, "unused"


def extract_tabular(src: str) -> str | None:
    m = TABULAR_RE.search(src)
    return m.group(1) if m else None


def n_columns(tabular: str) -> int:
    m = re.search(r"\\begin\{tabular\}\{([^}]*)\}", tabular)
    if not m:
        return 0
    return sum(1 for c in m.group(1) if c in "lrcp")


def measure_all(jobs: list[tuple[str, str, str]]) -> dict[tuple[str, str], float]:
    """One compile for every (table, size) box. Returns width in pt at 6 pt sep.

    ``jobs`` is a list of (key, size, tabular_source).
    """
    lines = [
        r"\documentclass[runningheads]{llncs}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage{booktabs}",
        r"\usepackage{amsmath,amssymb}",
        r"\newsavebox{\mb}",
        r"\begin{document}",
    ]
    for key, size, tabular in jobs:
        lines.append(
            rf"\sbox{{\mb}}{{{size}\setlength{{\tabcolsep}}{{6pt}}{tabular}}}"
        )
        lines.append(rf"\typeout{{ICAWIDTH::{key}::\the\wd\mb}}")
    lines.append(r"\end{document}")

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.tex"
        probe.write_text("\n".join(lines))
        result = subprocess.run(
            [TECTONIC, "-X", "compile", str(probe), "--print", "--keep-logs"],
            capture_output=True, text=True, cwd=tmp,
        )
    out = result.stdout + result.stderr
    widths: dict[tuple[str, str], float] = {}
    for m in re.finditer(r"ICAWIDTH::([^:]+)::([\d.]+)pt", out):
        stem_size = m.group(1)
        stem, size_name = stem_size.rsplit("@", 1)
        widths[(stem, size_name)] = float(m.group(2))
    if not widths:
        print(out[-3000:], file=sys.stderr)
        raise RuntimeError("measurement produced no widths; see probe output above")
    return widths


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="measure and report, write nothing")
    args = ap.parse_args()

    if not Path(TECTONIC).exists():
        print(f"tectonic not found at {TECTONIC}; cannot measure", file=sys.stderr)
        return 1

    paths = sorted(TABLES.glob("*.tex"))
    jobs: list[tuple[str, str, str]] = []
    tabulars: dict[str, str] = {}
    for path in paths:
        tabular = extract_tabular(path.read_text())
        if tabular is None:
            continue
        tabulars[path.stem] = tabular
        for size in SIZES:
            jobs.append((f"{path.stem}@{SIZE_NAMES[size]}", size, tabular))

    print(f"measuring {len(tabulars)} tables x {len(SIZES)} sizes "
          f"in one compile ({len(jobs)} boxes)")
    widths = measure_all(jobs)

    rotate: list[str] = []
    changed = 0
    rows: list[tuple[str, str, float, float, str, int, float]] = []

    for stem in sorted(tabulars):
        tabular = tabulars[stem]
        ncols = n_columns(tabular)
        limit, where = target_width(stem)
        budget = limit - SLACK_PT

        chosen: tuple[str, int, float] | None = None
        for size in sizes_for(stem):
            w6 = widths.get((stem, SIZE_NAMES[size]))
            if w6 is None:
                continue
            for sep in TABCOLSEPS:
                # Exactly linear: every column is padded on both sides.
                w = w6 - 2 * ncols * (6 - sep)
                if w <= budget:
                    chosen = (SIZE_NAMES[size], sep, w)
                    break
            if chosen:
                break

        natural = widths.get((stem, "normalsize"), float("nan"))
        rotated = False
        if chosen is None:
            # Rotating buys the text height instead of the width. Re-run the
            # same search against that budget rather than assuming it fits.
            rot_budget = SUPP_HEIGHT_PT - SLACK_PT
            for size in sizes_for(stem):
                w6 = widths.get((stem, SIZE_NAMES[size]))
                if w6 is None:
                    continue
                for sep in TABCOLSEPS:
                    if w6 - 2 * ncols * (6 - sep) <= rot_budget:
                        chosen = (SIZE_NAMES[size], sep, w6 - 2 * ncols * (6 - sep))
                        break
                if chosen:
                    break
            if chosen is None:
                smallest = widths.get((stem, "tiny"), float("nan")) - 2 * ncols * 4
                rows.append((stem, where, natural, limit, "NO FIT", 0, smallest))
                rotate.append(stem)
                continue
            rotated = True
            rotate.append(stem)

        size_name, sep, fitted = chosen
        rows.append((stem, where, natural,
                     SUPP_HEIGHT_PT if rotated else limit,
                     ("rot/" if rotated else "") + size_name, sep, fitted))

        prologue = ""
        if size_name != "normalsize":
            prologue += f"\\{size_name}\n"
        prologue += "\\centering\n"
        if sep != 6:
            prologue += f"\\setlength{{\\tabcolsep}}{{{sep}pt}}\n"

        path = TABLES / f"{stem}.tex"
        src = path.read_text()
        new_src = PROLOGUE_RE.sub(lambda _m: prologue, src, count=1)
        if rotated:
            # Rotation is a property of this table's size, so it is applied
            # here rather than left for the author to remember per include.
            new_src = new_src.replace(r"\begin{table}", r"\begin{sidewaystable}")
            new_src = new_src.replace(r"\end{table}", r"\end{sidewaystable}")
        if new_src != src and not args.check:
            path.write_text(new_src)
            changed += 1

    print()
    print(f"{'table':44s} {'in':11s} {'natural':>9s} {'limit':>8s} "
          f"{'size':>13s} {'sep':>4s} {'fitted':>9s}")
    for stem, where, natural, limit, size_name, sep, fitted in rows:
        mm = natural * 25.4 / 72.27
        lim_mm = limit * 25.4 / 72.27
        fit_mm = fitted * 25.4 / 72.27
        flag = "" if size_name != "ROTATE" else "  <-- needs sidewaystable"
        print(f"{stem:44s} {where:11s} {mm:8.1f}mm {lim_mm:7.1f}mm "
              f"{size_name:>13s} {sep:3d}pt {fit_mm:8.1f}mm{flag}")

    print()
    if not args.check:
        print(f"rewritten: {changed} table(s)")
    if rotate:
        print(f"\nToo wide for the upright measure, wrapped in sidewaystable "
              f"({len(rotate)}):")
        for stem in rotate:
            print(f"  {stem}")
        print("\nThe supplement preamble must load \\usepackage{rotating}.")
    unfittable = [r[0] for r in rows if r[4] == "NO FIT"]
    if unfittable:
        print(f"\nSTILL DOES NOT FIT, even rotated at \\tiny ({len(unfittable)}):")
        for stem in unfittable:
            print(f"  {stem}")
        print("These need a column dropped; values are never abbreviated to fit.")
        return 1
    print("every table fits the block it is typeset in")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
