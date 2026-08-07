"""Escaping and number formatting for generated LaTeX.

Two defects reached a compiled PDF and are pinned here.

The first was double escaping. A generated table mixes data read from artifacts
with markup the generator author wrote, and pandas' ``escape=True`` cannot tell
them apart: it rewrote the heading ``$\\Delta$ acc.`` into a literal
``\\textbackslash Delta``, which is what the reader then saw on the page. The
subtle part is that a type marker alone does not survive the round trip --
``DataFrame.rename`` and ``Series.replace`` hand back plain ``str`` -- so
recognition has to work by content as well.

The second was two spellings of one quantity: ``results_macros.tex`` wrote
``54\\,305`` while the table beside it wrote ``54305``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest

from ica26.experiments.latexfmt import Raw, cell, fmt_int, is_raw, latex_escape

REPO = Path(__file__).resolve().parent.parent
TABLES = REPO / "experiments/ica26/tables"


# --------------------------------------------------------------------------- #
# data is escaped
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("50%", r"50\%"),
    ("a_b", r"a\_b"),
    ("R&D", r"R\&D"),
    ("$5", r"\$5"),
    ("#1", r"\#1"),
    ("{x}", r"\{x\}"),
])
def test_specials_in_data_are_escaped(raw, expected):
    assert latex_escape(raw) == expected


def test_backslash_is_escaped_before_the_rules_that_add_backslashes():
    """Order matters: escaping `%` first would corrupt the backslash rule."""
    assert latex_escape("\\") == r"\textbackslash{}"
    assert latex_escape("\\%") == r"\textbackslash{}\%"


def test_unicode_the_generator_emits_becomes_math_mode():
    assert latex_escape("0.5 ± 0.1") == r"0.5 $\pm$ 0.1"
    assert latex_escape("PV → PDC") == r"PV $\rightarrow$ PDC"


def test_arrow_never_survives_as_a_raw_byte():
    """U+2192 is undefined under pdflatex's utf8 inputenc."""
    assert "→" not in latex_escape("a → b")


# --------------------------------------------------------------------------- #
# authored markup is not escaped
# --------------------------------------------------------------------------- #
def test_raw_markup_passes_through_untouched():
    assert cell(Raw(r"$\Delta$ acc.")) == r"$\Delta$ acc."
    assert cell(Raw(r"Rel. drop (\%)")) == r"Rel. drop (\%)"


def test_the_same_text_as_data_is_escaped():
    """The distinction is the marker, not the content."""
    assert cell("100%") == r"100\%"


def test_raw_is_recognised_after_pandas_strips_the_subclass():
    """The load-bearing case: pandas rebuilds these as plain str.

    Without content registration the heading arrives at the escaper looking
    like data, which is exactly how `$\\Delta$ acc.` became
    `\\textbackslash Delta`.
    """
    heading = Raw(r"$\Delta$ acc.")
    df = pd.DataFrame({"x": [1]}).rename(columns={"x": heading})
    recovered = df.columns[0]
    assert not isinstance(recovered, Raw), "pandas unexpectedly preserved the subclass"
    assert is_raw(recovered)
    assert cell(recovered) == r"$\Delta$ acc."


def test_raw_survives_series_replace():
    marker = Raw(r"PV $\rightarrow$ PDC")
    s = pd.Series(["PlantVillage → PlantDoc Core"]).replace(
        {"PlantVillage → PlantDoc Core": marker})
    assert cell(s.iloc[0]) == r"PV $\rightarrow$ PDC"


def test_none_renders_empty():
    assert cell(None) == ""


# --------------------------------------------------------------------------- #
# integers
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n,expected", [
    (0, "0"), (42, "42"), (999, "999"),
    (1951, r"1\,951"), (54305, r"54\,305"), (10000, r"10\,000"),
    (1234567, r"1\,234\,567"),
])
def test_fmt_int_uses_a_thin_space(n, expected):
    assert fmt_int(n) == expected


def test_fmt_int_of_none_is_empty():
    assert fmt_int(None) == ""


# --------------------------------------------------------------------------- #
# regression over the artifacts on disk
# --------------------------------------------------------------------------- #
def _generated_tex() -> list[Path]:
    return sorted(TABLES.glob("*.tex"))


def test_there_are_generated_tables_to_check():
    assert _generated_tex(), "no generated .tex found; run scripts/ica26_build_tables.py"


@pytest.mark.parametrize("path", _generated_tex(), ids=lambda p: p.name)
def test_no_double_escaping_in_generated_tables(path):
    src = path.read_text()
    assert r"\textbackslash" not in src, f"{path.name}: double escaping"
    # A legitimately escaped dollar would be `\$` in *data*; none of these
    # tables carry a currency value, so any `\$` here is escaped math markup.
    assert r"\$" not in src, f"{path.name}: escaped math delimiter"


@pytest.mark.parametrize("path", _generated_tex(), ids=lambda p: p.name)
def test_no_bare_unicode_in_generated_tables(path):
    """Anything non-ASCII would depend on the engine's inputenc coverage."""
    src = path.read_text()
    offenders = sorted({c for c in src if ord(c) > 127})
    assert not offenders, f"{path.name}: non-ASCII {offenders}"


@pytest.mark.parametrize("path", _generated_tex(), ids=lambda p: p.name)
def test_large_integers_carry_a_thousands_separator(path):
    """The same quantity must not read two ways on facing pages.

    Seeds are identifiers rather than counts and are excluded; so are the
    four-digit years that appear in captions.
    """
    src = re.sub(r"\\caption\{.*?\}\n", "", path.read_text(), flags=re.S)
    body = src[src.find(r"\midrule"):] if r"\midrule" in src else src
    # A run of >=4 digits that is not already separated, is not part of a
    # decimal (`9472.31` is a measurement, not a count), and is not a seed.
    for match in re.finditer(r"(?<![\d\\,.])(\d{4,})(?![\d,.])", body):
        value = match.group(1)
        if value in {"42", "1337", "2026"}:
            continue
        assert False, f"{path.name}: {value} lacks a thousands separator"
