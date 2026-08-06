"""LaTeX escaping and number formatting shared by both paper generators.

Two separate problems live here because both are caused by the same thing:
strings flowing into a ``.tex`` file without anyone tracking whether they are
*data* or *markup*.

**Escaping.** A generated table mixes two kinds of string. Values read from a
CSV or a result file are data: a stray ``%`` or ``_`` in one of them must be
escaped or LaTeX misreads it. Column headings, captions, and abbreviations are
markup the generator author wrote: ``$\\Delta$``, ``\\%``, ``$\\rightarrow$``
are meant to reach the typesetter intact. Escaping everything turns the second
kind into literal ``\\textbackslash Delta``; escaping nothing lets the first
kind break the build. The two streams are therefore distinguished explicitly:
anything wrapped in :class:`Raw` is passed through untouched, everything else is
escaped.

**Integers.** ``results_macros.tex`` wrote ``54\\,305`` while ``tables/*.tex``
wrote ``54305``, so one quantity appeared two ways on facing pages. Both
generators now call :func:`fmt_int`.
"""
from __future__ import annotations

__all__ = ["Raw", "is_raw", "latex_escape", "cell", "fmt_int", "UNICODE_MATH"]


# Every Raw string ever constructed, by content.
#
# The type alone is not enough. ``DataFrame.rename`` and ``Series.replace``
# rebuild their targets and hand back plain ``str``, so a Raw heading loses its
# class somewhere inside pandas and arrives at the escaper looking like data.
# Registering the content at construction makes recognition survive that round
# trip. These strings are distinctive LaTeX fragments, so a data value colliding
# with one is not a practical concern.
_RAW_REGISTRY: set[str] = set()


class Raw(str):
    """A string that is already LaTeX and must never be escaped.

    Use for anything the generator author wrote as markup --- column headings,
    captions, unit symbols --- and never for a value read from an artifact.
    """

    __slots__ = ()

    def __new__(cls, value: object = "") -> "Raw":
        obj = super().__new__(cls, value)
        _RAW_REGISTRY.add(str(obj))
        return obj


def is_raw(value: object) -> bool:
    return isinstance(value, Raw) or str(value) in _RAW_REGISTRY


# Applied in a single pass over the input, never as sequential replacements.
# Sequential replacement is subtly wrong here: the backslash rule emits
# `\textbackslash{}`, and a later rule for `{` would then escape the braces it
# just introduced. One pass reads each source character exactly once, so a
# replacement can never be rewritten by a rule that runs after it.
_ESCAPES: dict[str, str] = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Characters the generators deliberately emit into *data* cells, mapped to
# math-mode equivalents. Applied after escaping, so a literal backslash in the
# data cannot be confused with one of these. U+2192 in particular is undefined
# under pdflatex's utf8 inputenc, so passing it through would break the build
# on the engine Springer expects.
UNICODE_MATH: tuple[tuple[str, str], ...] = (
    ("±", r"$\pm$"),        # +/-
    ("→", r"$\rightarrow$"),
    ("≤", r"$\leq$"),
    ("≥", r"$\geq$"),
    ("×", r"$\times$"),
    ("−", "-"),             # U+2212 minus sign, not the ASCII hyphen
    ("—", "---"),           # em dash
    ("–", "--"),            # en dash
)


def latex_escape(text: str) -> str:
    """Escape LaTeX specials in a data value, then lift the Unicode we emit."""
    lifted = dict(UNICODE_MATH)
    out: list[str] = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif char in lifted:
            out.append(lifted[char])
        else:
            out.append(char)
    return "".join(out)


def cell(value) -> str:
    """Render one table cell: authored markup passes through, data escapes."""
    if value is None:
        return ""
    if is_raw(value):
        return str(value)
    return latex_escape(str(value))


def fmt_int(n) -> str:
    """Thousands-separated integer using a LaTeX thin space.

    The single definition both generators use, so a count reads identically in
    running text and in the table beside it.
    """
    if n is None:
        return ""
    return f"{int(n):,}".replace(",", r"\,")
