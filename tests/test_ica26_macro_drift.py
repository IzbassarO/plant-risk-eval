"""Drift reporting must separate "a table number moved" from "a claim moved".

The paper's prose is hand-written around generated values. When a rebuild moves
a value, the surrounding sentence may or may not still be true, and only the
author can judge which. The tool's job is therefore to point precisely at the
sentences that need re-reading -- not to rewrite them, and not to bury them in a
list of table cells that no sentence cites.

The subtle failure mode is the citation match. ``\\AccXdRn`` is a prefix of
``\\AccXdRnMean``, so a naive substring search reports the wrong sentence, or
reports one where none exists.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "ica26_macro_drift", REPO / "scripts/ica26_macro_drift.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


drift = _load()


# --------------------------------------------------------------------------- #
# citation matching
# --------------------------------------------------------------------------- #
def test_a_macro_cited_in_the_paper_is_found():
    """\\NSharedClasses appears in the abstract; if this stops matching, the
    whole report silently becomes empty."""
    hits = drift.citations("NSharedClasses")
    assert hits, "expected \\NSharedClasses to be cited in the paper"
    assert all(len(h) == 3 for h in hits)
    assert all(h[0].endswith(".tex") for h in hits)


def test_a_macro_that_exists_only_in_tables_is_not_reported_as_cited():
    """Table values are \\input from generated files, not written into prose."""
    assert drift.citations("BrierPvInTEb") == []


def test_a_prefix_macro_does_not_match_its_longer_sibling(tmp_path, monkeypatch):
    """\\AccXdRn must not match \\AccXdRnMean -- the bug this regex guards."""
    paper = tmp_path / "fake.tex"
    paper.write_text(
        "Line one cites \\AccXdRnMean{} only.\n"
        "Line two cites \\AccXdRn{} itself.\n"
    )
    monkeypatch.setattr(drift, "REPO", tmp_path)
    monkeypatch.setattr(drift, "TEX_SOURCES", ["fake.tex"])

    short = drift.citations("AccXdRn")
    long = drift.citations("AccXdRnMean")
    assert [h[1] for h in short] == [2], "\\AccXdRn matched its longer sibling"
    assert [h[1] for h in long] == [1]


def test_commented_out_lines_are_not_treated_as_citations(tmp_path, monkeypatch):
    """A macro mentioned in a comment is not a claim a reader will see."""
    paper = tmp_path / "fake.tex"
    paper.write_text(
        "% explanatory note about \\NPv{} in a comment\n"
        "Real prose citing \\NPv{} here.\n"
    )
    monkeypatch.setattr(drift, "REPO", tmp_path)
    monkeypatch.setattr(drift, "TEX_SOURCES", ["fake.tex"])
    assert [h[1] for h in drift.citations("NPv")] == [2]


def test_a_macro_cited_nowhere_returns_no_hits():
    assert drift.citations("ThisMacroDoesNotExistAnywhere") == []


# --------------------------------------------------------------------------- #
# the generated values are readable
# --------------------------------------------------------------------------- #
def test_current_macros_parse_into_name_value_pairs():
    macros = drift.current_macros()
    assert macros, "no macros parsed"
    assert "NSharedClasses" in macros
    assert all(name.isalpha() for name in macros)


def test_snapshot_round_trips_without_drift(tmp_path, monkeypatch):
    """Snapshotting then comparing immediately must report nothing."""
    import json

    snap = tmp_path / "snapshot.json"
    monkeypatch.setattr(drift, "SNAPSHOT", snap)
    macros = drift.current_macros()
    snap.write_text(json.dumps({"macros": macros}))
    before = json.loads(snap.read_text())["macros"]
    assert before == macros


def test_context_window_returns_surrounding_lines(tmp_path, monkeypatch):
    paper = tmp_path / "fake.tex"
    paper.write_text("alpha\nbeta\ngamma \\NPv{} delta\nepsilon\nzeta\n")
    monkeypatch.setattr(drift, "REPO", tmp_path)
    text = drift.sentence_around("fake.tex", 3, span=1)
    assert "gamma" in text and "beta" in text and "epsilon" in text
    assert "alpha" not in text
