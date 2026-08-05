"""The paper's numbers must come from the run artifacts, and only from them.

The paper cites macros rather than literals, so the macro file is the single
place a wrong number could enter the PDF unnoticed. These tests treat it as
exactly that: an independent recomputation from the source JSON, a check that a
missing run produces a visible [PENDING] marker rather than a plausible value,
and a check that every macro the paper references actually exists.

A LaTeX build already fails on an undefined control sequence. What it cannot
catch is a macro that is defined, typesets cleanly, and is wrong -- which is the
failure these tests exist for.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
MACRO_FILE = REPO / "paper/generated/results_macros.tex"
PAPER_TEX = REPO / "paper/ica2026.tex"
METRICS = REPO / "experiments/ica26/metrics"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "ica26_build_paper_macros", REPO / "scripts/ica26_build_paper_macros.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


mac = _load_script()

MACRO_RE = re.compile(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}$", re.MULTILINE)


def parse_macros(text: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in MACRO_RE.finditer(text)}


@pytest.fixture(scope="module")
def macros() -> dict[str, str]:
    text, _ = mac.build()
    return parse_macros(text)


@pytest.fixture(scope="module")
def runs() -> dict:
    return mac.load_runs()


# --------------------------------------------------------------------------- #
# the generated file is current
# --------------------------------------------------------------------------- #
def test_committed_macro_file_matches_a_fresh_build():
    """A stale macro file means the paper cites superseded numbers."""
    if not MACRO_FILE.exists():
        pytest.skip("macro file not generated yet")
    text, _ = mac.build()
    assert MACRO_FILE.read_text() == text, (
        "paper/generated/results_macros.tex is stale; "
        "run python scripts/ica26_build_paper_macros.py"
    )


def test_no_macro_is_defined_twice():
    text, _ = mac.build()
    names = MACRO_RE.findall(text)
    assert len(names) == len({n for n, _ in names})


def test_macro_names_are_letters_only():
    """LaTeX control sequences cannot contain digits or underscores; a name
    that does would silently truncate at the first offending character."""
    text, _ = mac.build()
    for name, _ in MACRO_RE.findall(text):
        assert name.isalpha(), f"\\{name} is not a valid control sequence name"


# --------------------------------------------------------------------------- #
# values trace back to the run artifacts
# --------------------------------------------------------------------------- #
def _numbers_in(body: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+\.\d+", body)]


@pytest.mark.parametrize(
    "macro,prefix,model,eval_key,field",
    [
        ("AccPvInRn", "pv", "resnet50", "in_domain_test", "accuracy"),
        ("MacroFPvInEb", "pv", "efficientnet_b0", "in_domain_test", "macro_f1"),
        ("AccXdRn", "pv", "resnet50", "cross_domain_plantdoc_core", "accuracy"),
        ("MacroFXdMn", "pv", "mobilenet_v3_small", "cross_domain_plantdoc_core", "macro_f1"),
        ("AccPdcInRn", "pdc", "resnet50", "in_domain_test", "accuracy"),
        ("MacroFPdcInMn", "pdc", "mobilenet_v3_small", "in_domain_test", "macro_f1"),
    ],
)
def test_headline_macro_equals_the_mean_of_its_runs(macros, runs, macro, prefix,
                                                    model, eval_key, field):
    """Recompute the mean straight from the result files and compare."""
    blocks = mac.blocks_for(runs, prefix, model, eval_key)
    if not blocks:
        pytest.skip(f"{prefix}_{model} has no {eval_key} results yet")
    expected = sum(b[field] for b in blocks) / len(blocks)
    got = _numbers_in(macros[macro])
    assert got, f"\\{macro} carries no number: {macros[macro]!r}"
    assert got[0] == pytest.approx(expected, abs=5e-5)


def test_aggregated_macros_carry_a_spread_exactly_when_seeds_allow_one(macros, runs):
    """One seed must print a bare mean; two or more must print mean ± std.

    Printing ± 0.0000 for a single run would assert a variance estimate that
    does not exist, which is the specific dishonesty this convention prevents.
    """
    checked = 0
    for model, mtag in mac.MODEL_TAG.items():
        blocks = mac.blocks_for(runs, "pv", model, "in_domain_test")
        if not blocks:
            continue
        body = macros[f"AccPvIn{mtag}"]
        if len(blocks) == 1:
            assert r"\pm" not in body, f"single seed must not print a spread: {body!r}"
        else:
            assert r"\pm" in body, f"{len(blocks)} seeds must print a spread: {body!r}"
        checked += 1
    assert checked, "no PlantVillage in-domain results to check"


def test_dataset_counts_match_the_lock(macros):
    lock = json.loads((REPO / "data/manifests/ica26_core_experiment_lock.json").read_text())
    pv = lock["corpora"]["plantvillage"]

    def as_int(body: str) -> int:
        return int(re.sub(r"[^0-9]", "", body))

    assert as_int(macros["NPv"]) == pv["n_records"]
    assert as_int(macros["NPvTrain"]) == pv["split_counts"]["train"]
    assert as_int(macros["NPvTest"]) == pv["split_counts"]["test"]
    assert as_int(macros["NPdc"]) == lock["corpora"]["plantdoc_core"]["n_records"]
    assert as_int(macros["NSharedClasses"]) == lock["cross_domain_mapping"]["n_shared_classes"]


def test_leakage_macros_report_zero_exact_overlap(macros):
    """The paper's central control. If this ever becomes non-zero the
    cross-domain claim changes, and it must not be able to change silently."""
    assert macros["NLeakExactCore"] == "0"
    assert macros["NLeakExactAcq"] == "0"
    assert macros["NLeakUnresolved"] == "0"


def test_degradation_macro_is_paired_within_seed(macros, runs):
    """Averaging per-seed drops is not the same as differencing seed-averages
    once seeds differ; the paper claims the former."""
    per_seed = []
    for seed in mac.SEEDS:
        res = runs.get(f"pv_resnet50_s{seed}")
        if not res:
            continue
        ind = res["evaluations"].get("in_domain_test")
        xd = res["evaluations"].get("cross_domain_plantdoc_core")
        if ind and xd:
            per_seed.append((ind["macro_f1"] - xd["macro_f1"]) / ind["macro_f1"] * 100)
    if not per_seed:
        pytest.skip("no paired PlantVillage results yet")
    expected = sum(per_seed) / len(per_seed)
    assert _numbers_in(macros["RelDropFRn"])[0] == pytest.approx(expected, abs=0.05)


# --------------------------------------------------------------------------- #
# a missing result never becomes a number
# --------------------------------------------------------------------------- #
def test_absent_values_become_a_visible_pending_marker():
    """The property that makes an incomplete draft safe to circulate."""
    m = mac.Macros()
    m.add("Fabricated", None)
    body = dict(MACRO_RE.findall(m.render([])))
    assert body["Fabricated"] == r"\ResultPending"
    assert m.n_pending == 1


def test_pending_marker_is_defined_so_the_document_still_compiles():
    text, _ = mac.build()
    assert r"\providecommand{\ResultPending}" in text


def test_aggregation_of_nothing_is_pending_not_zero():
    assert mac.agg([]) is None
    assert mac.mean_only([]) is None
    assert mac.num(None) is None
    assert mac.integer(None) is None


def test_duplicate_macro_definition_is_an_error():
    m = mac.Macros()
    m.add("Same", "1")
    with pytest.raises(RuntimeError, match="defined twice"):
        m.add("Same", "2")


# --------------------------------------------------------------------------- #
# the paper only cites macros that exist
# --------------------------------------------------------------------------- #
# Control sequences from the document class, loaded packages, and the included
# generated tables. A name here is asserted to be LaTeX's, not a result macro.
KNOWN_LATEX = {
    "documentclass", "usepackage", "graphicspath", "input", "begin", "end",
    "title", "author", "institute", "maketitle", "keywords", "and", "section",
    "subsection", "subsubsection", "label", "ref", "cite", "item", "emph",
    "textbf", "textit", "texttt", "bibliographystyle", "bibliography", "times",
    "leq", "geq", "pm", "rightarrow", "to", "noindent", "ResultPending", "circ",
    "infty", "sqrt", "frac", "cdot", "times", "ldots", "dots",
    "caption", "toprule", "midrule", "bottomrule", "hline", "includegraphics",
    "centering", "figure", "table", "tabular", "textwidth", "linewidth",
    "url", "footnote", "quad", "qquad", ",", ";", ":", "%", "&", "_", "#",
}


def test_every_macro_the_paper_uses_is_defined(macros):
    if not PAPER_TEX.exists():
        pytest.skip("paper source not present")
    body = PAPER_TEX.read_text()
    # Strip comments so a commented-out draft macro is not treated as a use.
    body = re.sub(r"(?<!\\)%.*", "", body)
    used = set(re.findall(r"\\([A-Za-z]+)", body))
    unknown = sorted(used - set(macros) - KNOWN_LATEX)
    assert not unknown, (
        "paper references control sequences that are neither result macros nor "
        f"known LaTeX: {unknown}"
    )


# --------------------------------------------------------------------------- #
# structural well-formedness, without invoking a TeX engine
# --------------------------------------------------------------------------- #
TEX_SOURCES = ["paper/ica2026.tex", "paper/supplementary.tex"]


def _strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


@pytest.mark.parametrize("relpath", TEX_SOURCES)
def test_braces_balance(relpath):
    """An unbalanced brace is a compile error that no macro check would catch."""
    path = REPO / relpath
    if not path.exists():
        pytest.skip(f"{relpath} not present")
    depth = 0
    for line_no, line in enumerate(_strip_comments(path.read_text()).splitlines(), 1):
        # \{ and \} are literal braces, not grouping.
        for char in re.sub(r"\\[{}]", "", line):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
        assert depth >= 0, f"{relpath}:{line_no}: closing brace with no opener"
    assert depth == 0, f"{relpath}: {depth} unclosed brace(s)"


@pytest.mark.parametrize("relpath", TEX_SOURCES)
def test_environments_are_balanced_and_correctly_nested(relpath):
    path = REPO / relpath
    if not path.exists():
        pytest.skip(f"{relpath} not present")
    stack: list[tuple[str, int]] = []
    for line_no, line in enumerate(_strip_comments(path.read_text()).splitlines(), 1):
        for kind, name in re.findall(r"\\(begin|end)\{([^}]+)\}", line):
            if kind == "begin":
                stack.append((name, line_no))
            else:
                assert stack, f"{relpath}:{line_no}: \\end{{{name}}} with nothing open"
                opened, opened_at = stack.pop()
                assert opened == name, (
                    f"{relpath}:{line_no}: \\end{{{name}}} closes "
                    f"\\begin{{{opened}}} from line {opened_at}"
                )
    assert not stack, f"{relpath}: unclosed environments {stack}"


@pytest.mark.parametrize("relpath", TEX_SOURCES)
def test_every_input_and_includegraphics_target_exists(relpath):
    """A missing \\input is a hard compile error; a missing figure is a silent
    placeholder box in some engines."""
    path = REPO / relpath
    if not path.exists():
        pytest.skip(f"{relpath} not present")
    body = _strip_comments(path.read_text())
    missing = []
    for target in re.findall(r"\\input\{([^}]+)\}", body):
        candidate = (path.parent / target).resolve()
        if not (candidate.exists() or candidate.with_suffix(".tex").exists()):
            missing.append(f"\\input{{{target}}}")
    for target in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
        if not (REPO / "experiments/ica26/figures" / target).exists():
            missing.append(f"\\includegraphics{{{target}}}")
    assert not missing, f"{relpath} references missing files: {missing}"


@pytest.mark.parametrize("relpath", TEX_SOURCES)
def test_every_label_reference_resolves(relpath):
    """An unresolved \\ref typesets as `??' rather than failing the build."""
    path = REPO / relpath
    if not path.exists():
        pytest.skip(f"{relpath} not present")
    body = _strip_comments(path.read_text())
    labels = set(re.findall(r"\\label\{([^}]+)\}", body))
    # Table labels come from the generated .tex files that get \input.
    for target in re.findall(r"\\input\{([^}]+)\}", body):
        included = (path.parent / target)
        if included.suffix != ".tex":
            included = included.with_suffix(".tex")
        if included.exists():
            labels |= set(re.findall(r"\\label\{([^}]+)\}", included.read_text()))
    referenced = set(re.findall(r"\\ref\{([^}]+)\}", body))
    assert not (referenced - labels), (
        f"{relpath} references undefined labels: {sorted(referenced - labels)}"
    )


def test_paper_defines_no_results_of_its_own():
    """All result definitions live in the generated file, so regenerating it
    updates every number in the paper. A \\newcommand in the body would escape
    that and quietly freeze a stale value."""
    if not PAPER_TEX.exists():
        pytest.skip("paper source not present")
    body = re.sub(r"(?<!\\)%.*", "", PAPER_TEX.read_text())
    assert not re.search(r"\\newcommand", body), (
        "define result macros in scripts/ica26_build_paper_macros.py, not in the paper"
    )
