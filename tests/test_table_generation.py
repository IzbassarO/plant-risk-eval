"""Regression tests for the two defects that shipped in a compiled PDF.

Both had already come back once after being fixed, which is why they are pinned
here rather than only repaired.

**Double escaping.** Headings carrying intentional LaTeX were run through
pandas' ``escape=True``, so ``$\\Delta$ acc.`` reached the page as literal
``\\textbackslash Delta``.

**Unresolved Unicode.** The generators build ``0.9945 ± 0.0021`` with a real
``±``, and pandas leaves it alone. A replacement loop used to convert it; when
that loop was removed the conversion had to move into ``cell()``. If it had not,
every table would have carried raw UTF-8 that pdfLaTeX rejects outright with
"Unicode character ± not set up for use with LaTeX".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from ica26.experiments.latexfmt import Raw, cell, fmt_int

REPO = Path(__file__).resolve().parent.parent
TABLES = REPO / "experiments/ica26/tables"

# Everything the removed replacement loop used to convert, plus its neighbours.
UNICODE_TRAPS = "±→≤≥×−–—"


def _tables() -> list[Path]:
    return sorted(TABLES.glob("*.tex"))


def test_generated_tables_exist():
    assert _tables(), "run scripts/ica26_build_tables.py first"


@pytest.mark.parametrize("path", _tables(), ids=lambda p: p.name)
def test_no_double_escaping(path):
    src = path.read_text()
    assert r"\textbackslash" not in src
    assert not re.search(r"\\\$\\\\", src)


@pytest.mark.parametrize("path", _tables(), ids=lambda p: p.name)
def test_no_unresolved_unicode(path):
    """pdfLaTeX refuses these outright; there is no partial-credit failure."""
    src = path.read_text()
    for ch in UNICODE_TRAPS:
        assert ch not in src, f"{ch!r} not converted to LaTeX in {path.name}"


def test_identifier_columns_not_separated():
    """A seed names a run, it does not count anything."""
    src = (TABLES / "table7_ranking_stability.tex").read_text()
    assert r"1\,337" not in src
    assert r"2\,026" not in src
    # ...and the seeds are actually present, so the check is not vacuous.
    assert "1337" in src and "2026" in src


def test_counts_are_separated_the_same_way_as_the_macros():
    """The defect was one quantity reading two ways on facing pages."""
    macros = (REPO / "paper/generated/results_macros.tex").read_text()
    tables = "\n".join(p.read_text() for p in _tables())
    for value in (r"54\,305", r"43\,596", r"1\,951"):
        assert value in macros, f"{value} missing from results_macros.tex"
    assert r"54\,305" in tables, "corpus size not separated in any table"
    assert not re.search(r"(?<![\d\\,.])54305(?![\d.])", tables)


# --------------------------------------------------------------------------- #
# latexfmt units
# --------------------------------------------------------------------------- #
def test_raw_passes_through():
    assert cell(Raw(r"$\Delta$")) == r"$\Delta$"


def test_data_is_escaped():
    assert cell("50% drop") == r"50\% drop"


def test_bool_is_not_an_integer():
    """isinstance(True, int) is True, so a bare int branch would print 1."""
    assert "1" not in cell(True)


def test_fmt_int_matches_macros():
    assert fmt_int(54305) == r"54\,305"


def test_unicode_map_covers_every_trap():
    """Whatever a generator emits, cell() must resolve it."""
    for ch in UNICODE_TRAPS:
        assert ch not in cell(f"a{ch}b"), f"{ch!r} survived cell()"


# --------------------------------------------------------------------------- #
# the compact tables the page budget depends on
# --------------------------------------------------------------------------- #
def test_compact_calibration_is_transposed():
    """Row-per-setting is eighteen rows and costs roughly a page."""
    src = (TABLES / "table6_calibration_compact.tex").read_text()
    body = src[src.index(r"\midrule"):src.index(r"\bottomrule")]
    assert body.count(r"\\") == 3, "expected one row per backbone"
    assert r"\multicolumn{2}{c}{PlantVillage test}" in src


def test_compact_significance_is_transposed():
    src = (TABLES / "table9_significance_across_seeds_compact.tex").read_text()
    body = src[src.index(r"\midrule"):src.index(r"\bottomrule")]
    assert body.count(r"\\") == 3, "expected one row per evaluation setting"
    assert src.count(r"\multicolumn{3}{c}") == 3, "expected three pair groups"


@pytest.mark.parametrize("stem", [
    "table6_calibration_compact",
    "table9_significance_across_seeds_compact",
])
def test_transposed_tables_carry_every_cell_of_the_full_form(stem):
    """Transposing buys pages; it must not drop evidence."""
    src = (TABLES / f"{stem}.tex").read_text()
    body = src[src.index(r"\midrule"):src.index(r"\bottomrule")]
    numbers = re.findall(r"[-+]?\d+\.\d+", body)
    assert len(numbers) >= 9, f"{stem}: only {len(numbers)} values survived"
