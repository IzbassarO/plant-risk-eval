#!/usr/bin/env python3
"""Emit every number the paper cites as a LaTeX macro, from verified artifacts.

    python scripts/ica26_build_paper_macros.py            # write the macro file
    python scripts/ica26_build_paper_macros.py --check    # rebuild and compare

The paper's ``.tex`` sources contain no literal experimental number. They cite
macros, and this script is the only thing that defines them, reading from:

    data/manifests/ica26_core_experiment_lock.json   dataset composition
    experiments/ica26/metrics/<run>.json             per-run results
    experiments/ica26/metrics/significance.json      McNemar p-values, BCa CIs

A number that does not exist yet does not become a guess. Its macro is defined
as ``\\ResultPending``, which typesets a conspicuous ``[PENDING]`` marker, so an
incomplete draft is obvious on the page instead of silently plausible. The
count of pending macros is printed and recorded in the file header.

Aggregated values carry ``mean ± sample standard deviation`` once more than one
seed has finished, and the bare mean while only one has. That is the same
convention the tables use, for the same reason: one run has no variance
estimate and printing ``± 0.0000`` would claim it does.

Exit codes: 0 written / current, 1 --check found a difference.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ica26.experiments.latexfmt import fmt_int  # noqa: E402

METRICS = REPO / "experiments/ica26/metrics"
LOCK = REPO / "data/manifests/ica26_core_experiment_lock.json"
OUT = REPO / "paper/generated/results_macros.tex"

SEEDS = [42, 1337, 2026]
# LaTeX control sequences are letters only, so models and settings get short
# alphabetic tags rather than the run ids used everywhere else.
MODEL_TAG = {"resnet50": "Rn", "efficientnet_b0": "Eb", "mobilenet_v3_small": "Mn"}
SETTINGS = {
    "PvIn": ("pv", "in_domain_test"),
    "PvInT": ("pv", "in_domain_test_temperature_scaled"),
    "PdcIn": ("pdc", "in_domain_test"),
    "PdcInT": ("pdc", "in_domain_test_temperature_scaled"),
    "Xd": ("pv", "cross_domain_plantdoc_core"),
    "XdT": ("pv", "cross_domain_plantdoc_core_temperature_scaled"),
}
SIG_SETTING_TAG = {
    "PlantVillage in-domain": "PvIn",
    "PlantDoc Core in-domain": "PdcIn",
    "PlantVillage -> PlantDoc Core": "Xd",
}
SIG_MODEL_TAG = {
    "ResNet-50": "Rn", "EfficientNet-B0": "Eb", "MobileNetV3-Small": "Mn",
}
PENDING = r"\ResultPending"


class Macros:
    """Ordered macro accumulator that refuses to define the same name twice."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []   # (name, body, section)
        self._seen: set[str] = set()
        self.n_pending = 0

    def add(self, name: str, body, section: str = "") -> None:
        if name in self._seen:
            raise RuntimeError(f"macro \\{name} defined twice")
        self._seen.add(name)
        if body is None:
            body = PENDING
            self.n_pending += 1
        self.items.append((name, str(body), section))

    def render(self, header: list[str]) -> str:
        lines = list(header)
        current = None
        for name, body, section in self.items:
            if section != current:
                lines += ["", f"% --- {section} " + "-" * max(0, 68 - len(section))]
                current = section
            lines.append(f"\\newcommand{{\\{name}}}{{{body}}}")
        return "\n".join(lines) + "\n"


def num(x, places: int = 4) -> str | None:
    return None if x is None else f"{float(x):.{places}f}"


def integer(x) -> str | None:
    """Thousands-separated integer. Shared with the table generator so one
    quantity cannot read two ways on facing pages."""
    return None if x is None else fmt_int(x)


def agg(values, places: int = 4) -> str | None:
    """``mean ± std`` over the seeds present, as an ensuremath body."""
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    arr = np.asarray(vals, dtype=float)
    if len(arr) == 1:
        return rf"\ensuremath{{{arr[0]:.{places}f}}}"
    return (rf"\ensuremath{{{arr.mean():.{places}f} \pm "
            rf"{arr.std(ddof=1):.{places}f}}}")


def agg_from(mean: float | None, sd: float | None, places: int = 4) -> str | None:
    """Format an already-computed mean and standard deviation.

    Same convention as :func:`agg`: a missing standard deviation prints the bare
    mean rather than claiming a variance estimate that does not exist.
    """
    if mean is None:
        return None
    if sd is None:
        return rf"\ensuremath{{{mean:.{places}f}}}"
    return rf"\ensuremath{{{mean:.{places}f} \pm {sd:.{places}f}}}"


def mean_only(values, places: int = 4) -> str | None:
    vals = [float(v) for v in values if v is not None]
    return None if not vals else f"{float(np.mean(vals)):.{places}f}"


def load_runs() -> dict[str, dict]:
    out = {}
    for p in sorted(METRICS.glob("*.json")):
        if p.name in {"environment.json", "significance.json", "smoke_test_report.json"}:
            continue
        payload = json.loads(p.read_text())
        if "experiment_id" in payload:
            out[payload["experiment_id"]] = payload
    return out


def blocks_for(runs: dict, prefix: str, model: str, eval_key: str) -> list[dict]:
    """Every seed's evaluation block for one cell, in seed order."""
    out = []
    for seed in SEEDS:
        res = runs.get(f"{prefix}_{model}_s{seed}")
        if res and eval_key in res.get("evaluations", {}):
            out.append(res["evaluations"][eval_key])
    return out


def build() -> tuple[str, dict]:
    m = Macros()
    runs = load_runs()
    lock = json.loads(LOCK.read_text())
    sig_path = METRICS / "significance.json"
    sig = json.loads(sig_path.read_text()) if sig_path.exists() else None

    # ---- provenance -------------------------------------------------------- #
    seeds_done = sorted({r["config"]["seed"] for r in runs.values()})
    complete = [f"{p}_{mo}_s{s}" for p in ("pv", "pdc")
                for mo in MODEL_TAG for s in SEEDS
                if f"{p}_{mo}_s{s}" in runs]

    m.add("LockDigest", r"\texttt{" + lock["lock_digest"][:16] + r"}", "provenance")
    # A 64-character hex string in \texttt has no hyphenation points, so set as
    # one word it overruns the LNCS text block by roughly 160 pt. Break
    # opportunities every 16 characters let it wrap without inserting any
    # character into the digest itself.
    digest = lock["lock_digest"]
    chunks = [digest[i:i + 16] for i in range(0, len(digest), 16)]
    m.add("LockDigestFull",
          r"\texttt{" + r"\allowbreak ".join(chunks) + r"}", "provenance")
    m.add("NSeedsDone", len(seeds_done), "provenance")
    m.add("SeedList", ", ".join(str(s) for s in seeds_done) or PENDING, "provenance")
    m.add("NRunsDone", len(complete), "provenance")
    m.add("NRunsPlanned", len(SEEDS) * 6, "provenance")

    # ---- numerical-guard evidence ------------------------------------------- #
    # A run that skipped a step is not numerically identical to one that did
    # not, so the paper states which runs those were rather than pooling them
    # silently. Exposed as macros for the same reason as every other number.
    skipped = {rid: r["training"].get("skipped_nonfinite_steps")
               for rid, r in runs.items()
               if r["training"].get("skipped_nonfinite_steps")}
    # Only runs trained under the guard record a step count. Summing over all
    # runs would silently mix guarded and pre-guard ones and report a total far
    # below the true number of optimiser steps taken.
    guarded = {rid: r["training"]["optimiser_steps"] for rid, r in runs.items()
               if r["training"].get("optimiser_steps") is not None}
    m.add("NRunsWithSkippedSteps", len(skipped), "numerical guard")
    m.add("NSkippedSteps", sum(skipped.values()) if skipped else 0, "numerical guard")
    m.add("NGuardedRuns", len(guarded), "numerical guard")
    m.add("NGuardedOptimiserSteps",
          integer(sum(guarded.values())) if guarded else None, "numerical guard")
    listing = ", ".join(f"\\texttt{{{k.replace('_', '\\_')}}} ({v})"
                        for k, v in sorted(skipped.items()))
    m.add("RunsWithSkippedSteps", listing or "none", "numerical guard")
    # The whole clause is composed here rather than with a TeX \ifnum in the
    # paper: a conditional over a generated macro breaks the moment that macro
    # expands to \ResultPending instead of a bare integer.
    if not guarded:
        note = None
    elif not skipped:
        note = (rf"no run trained under the guard skipped a step "
                rf"({len(guarded)} run{'s' if len(guarded) != 1 else ''}, "
                rf"{integer(sum(guarded.values()))} steps)")
    else:
        note = (rf"{len(skipped)} of {len(guarded)} runs trained under the guard "
                rf"skipped a step, {sum(skipped.values())} in total out of "
                rf"{integer(sum(guarded.values()))}: {listing}")
    m.add("SkippedStepsNote", note, "numerical guard")

    # ---- dataset composition ----------------------------------------------- #
    pv, pdc = lock["corpora"]["plantvillage"], lock["corpora"]["plantdoc_core"]
    cd = lock["cross_domain_mapping"]
    ex = lock["expected_counts"]
    for name, value in [
        ("NPv", integer(pv["n_records"])),
        ("NPvTrain", integer(pv["split_counts"].get("train"))),
        ("NPvTest", integer(pv["split_counts"].get("test"))),
        ("NPvClasses", pv["n_classes"]),
        ("NPdcAcquired", integer(ex["plantdoc"]["source"])),
        ("NPdc", integer(pdc["n_records"])),
        ("NPdcTrain", integer(pdc["split_counts"].get("train"))),
        ("NPdcTest", integer(pdc["split_counts"].get("test"))),
        ("NPdcClasses", pdc["n_classes"]),
        ("NPdcExcludedDup", integer(ex["plantdoc"]["source"] - ex["plantdoc"]["previous_effective"])),
        ("NPdcExcludedReview", integer(ex["plantdoc"]["previous_effective"] - ex["plantdoc"]["core"])),
        ("NSharedClasses", cd["n_shared_classes"]),
        ("NXdImages", integer(cd["n_evaluable_plantdoc_core_images"])),
        ("NLeakExactAcq", ex["leakage"]["acquired"]["exact"]),
        ("NLeakNearAcq", ex["leakage"]["acquired"]["near"]),
        ("NLeakExactCore", ex["leakage"]["core"]["exact"]),
        ("NLeakNearCore", ex["leakage"]["core"]["near"]),
        ("NLeakUnresolved", ex["leakage"]["core"]["unresolved"]),
    ]:
        m.add(name, value, "dataset composition")

    # ---- leakage-audit parameters -------------------------------------------- #
    # Read from the audit's own summary rather than restated in prose, so a
    # changed threshold or a re-run search cannot leave the paper describing a
    # search that was not the one performed.
    leak_summary = REPO / "reports/leakage_plantvillage_vs_plantdoc_summary.json"
    if leak_summary.exists():
        ls = json.loads(leak_summary.read_text())
        n_eval = ls.get("n_distance_evaluations")
        m.add("NPhashComparisons", integer(n_eval), "leakage audit")
        # Also as a power of ten, which is what reads well in a sentence.
        m.add("NPhashComparisonsSci",
              None if not n_eval else
              rf"\ensuremath{{{n_eval / 10 ** int(np.log10(n_eval)):.2f} \times "
              rf"10^{{{int(np.log10(n_eval))}}}}}",
              "leakage audit")
        m.add("PhashBits", ls.get("hash_size_bits"), "leakage audit")
    else:
        for name in ("NPhashComparisons", "NPhashComparisonsSci", "PhashBits"):
            m.add(name, None, "leakage audit")
    m.add("LeakThreshold", lock["leakage"]["core"].get("threshold"), "leakage audit")

    # ---- corpus shape used in prose ------------------------------------------ #
    # PlantDoc Core train imbalance, derived from the locked manifest rather
    # than restated: "ninety times" is a claim about the corpus, not a constant.
    pdc_manifest = REPO / "data/manifests/plantdoc_core_effective_manifest.csv"
    if pdc_manifest.exists():
        frame = pd.read_csv(pdc_manifest)
        counts = frame[frame["split"] == "train"]["class_label"].value_counts()
        m.add("PdcImbalance", f"{counts.max() / counts.min():.0f}", "corpus shape")
        m.add("PdcLargestClass", integer(counts.max()), "corpus shape")
        m.add("PdcSmallestClass", integer(counts.min()), "corpus shape")
    else:
        for name in ("PdcImbalance", "PdcLargestClass", "PdcSmallestClass"):
            m.add(name, None, "corpus shape")

    # Classes the PlantDoc test split can actually exercise: the arthropod-pest
    # class has zero test images, so 28 declared but 27 evaluable.
    pdc_any = next((r for rid, r in runs.items()
                    if rid.startswith("pdc_") and "in_domain_test" in r["evaluations"]), None)
    m.add("NPdcTestClasses",
          None if pdc_any is None
          else pdc_any["evaluations"]["in_domain_test"]["n_supported_classes"],
          "corpus shape")

    # ---- per-cell results --------------------------------------------------- #
    for stag, (prefix, eval_key) in SETTINGS.items():
        for model, mtag in MODEL_TAG.items():
            blocks = blocks_for(runs, prefix, model, eval_key)
            section = f"results: {stag}"
            m.add(f"Acc{stag}{mtag}", agg([b["accuracy"] for b in blocks]), section)
            m.add(f"MacroF{stag}{mtag}", agg([b["macro_f1"] for b in blocks]), section)
            m.add(f"BalAcc{stag}{mtag}", agg([b["balanced_accuracy"] for b in blocks]), section)
            m.add(f"Ece{stag}{mtag}",
                  agg([b["probabilistic"]["expected_calibration_error"] for b in blocks]), section)
            m.add(f"Nll{stag}{mtag}",
                  agg([b["probabilistic"]["negative_log_likelihood"] for b in blocks], 3), section)
            m.add(f"Brier{stag}{mtag}",
                  agg([b["probabilistic"]["brier_score"] for b in blocks]), section)
            m.add(f"Aurc{stag}{mtag}",
                  agg([b.get("selective_prediction", {}).get("area_under_risk_coverage")
                       for b in blocks]), section)
            # Mean-only forms, for prose that compares two numbers inline and
            # would read badly with two ± terms in one sentence.
            m.add(f"AccMean{stag}{mtag}", mean_only([b["accuracy"] for b in blocks]), section)
            m.add(f"MacroFMean{stag}{mtag}", mean_only([b["macro_f1"] for b in blocks]), section)

    # ---- fitted temperature -------------------------------------------------- #
    for model, mtag in MODEL_TAG.items():
        for prefix, stag in (("pv", "Pv"), ("pdc", "Pdc")):
            temps = [runs[f"{prefix}_{model}_s{s}"]["calibration"]["temperature"]
                     for s in SEEDS
                     if f"{prefix}_{model}_s{s}" in runs
                     and "calibration" in runs[f"{prefix}_{model}_s{s}"]]
            m.add(f"Temp{stag}{mtag}", agg(temps), "calibration: fitted temperature")

    # ---- domain-shift degradation ------------------------------------------- #
    for model, mtag in MODEL_TAG.items():
        rel_acc, rel_f1, abs_f1 = [], [], []
        for seed in SEEDS:
            res = runs.get(f"pv_{model}_s{seed}")
            if not res:
                continue
            ind = res["evaluations"].get("in_domain_test")
            xd = res["evaluations"].get("cross_domain_plantdoc_core")
            if not (ind and xd):
                continue
            # Paired within a seed, then averaged: the drop belongs to a
            # checkpoint and its own cross-domain evaluation.
            rel_acc.append((ind["accuracy"] - xd["accuracy"]) / ind["accuracy"] * 100)
            rel_f1.append((ind["macro_f1"] - xd["macro_f1"]) / ind["macro_f1"] * 100)
            abs_f1.append(ind["macro_f1"] - xd["macro_f1"])
        section = "domain-shift degradation"
        m.add(f"RelDropAcc{mtag}", agg(rel_acc, 1), section)
        m.add(f"RelDropF{mtag}", agg(rel_f1, 1), section)
        m.add(f"AbsDropF{mtag}", agg(abs_f1), section)
        m.add(f"RelDropFMean{mtag}", mean_only(rel_f1, 1), section)

    # ---- majority-class baseline on the cross-domain set ---------------------- #
    # Derived from the frozen evaluation set's label distribution, not trained:
    # a predictor that always emits the most frequent shared class. Without it a
    # reader cannot tell whether 0.23 macro-F1 over 21 classes is good or awful.
    xd_any = next((blocks_for(runs, "pv", m, "cross_domain_plantdoc_core")
                   for m in MODEL_TAG if blocks_for(runs, "pv", m, "cross_domain_plantdoc_core")),
                  None)
    if xd_any:
        supports = {pc["class_name"]: pc["support"] for pc in xd_any[0]["per_class"]}
        n_total = sum(supports.values())
        n_classes = len(supports)
        majority = max(supports.values())
        acc = majority / n_total
        # Every prediction lands on one class: that class has recall 1 and
        # precision majority/n; every other class scores 0 under
        # zero_division=0, matching evaluate_classification.
        precision = majority / n_total
        f1_majority = 2 * precision / (precision + 1.0)
        m.add("AccXdMajority", num(acc), "cross-domain majority baseline")
        m.add("MacroFXdMajority", num(f1_majority / n_classes),
              "cross-domain majority baseline")
        m.add("XdMajorityClass",
              r"\texttt{" + max(supports, key=supports.get).replace("_", r"\_") + "}",
              "cross-domain majority baseline")
    else:
        for name in ("AccXdMajority", "MacroFXdMajority", "XdMajorityClass"):
            m.add(name, None, "cross-domain majority baseline")

    # ---- single-seed point estimates paired with the bootstrap intervals ------ #
    # The intervals are computed on one seed, so the point estimate quoted beside
    # them must be that seed's, not the across-seed mean.
    sig_seed = sig["seed"] if sig else None
    for model, mtag in MODEL_TAG.items():
        res = runs.get(f"pv_{model}_s{sig_seed}") if sig_seed else None
        block = (res or {}).get("evaluations", {}).get("cross_domain_plantdoc_core")
        m.add(f"MacroFXd{mtag}S", num(block["macro_f1"]) if block else None,
              "cross-domain, significance seed only")

    # ---- calibration transport ------------------------------------------------ #
    # How much worse the in-domain temperature makes out-of-domain calibration.
    # Computed within a seed and then averaged: the ratio belongs to a
    # checkpoint and its own two evaluations of the same images.
    for model, mtag in MODEL_TAG.items():
        ratios = []
        for seed in SEEDS:
            res = runs.get(f"pv_{model}_s{seed}")
            if not res:
                continue
            plain = res["evaluations"].get("cross_domain_plantdoc_core")
            scaled = res["evaluations"].get("cross_domain_plantdoc_core_temperature_scaled")
            if not (plain and scaled):
                continue
            base = plain["probabilistic"]["expected_calibration_error"]
            if base:
                ratios.append(
                    scaled["probabilistic"]["expected_calibration_error"] / base)
        m.add(f"EceRatio{mtag}", mean_only(ratios, 2), "calibration transport")

    # Largest across-seed spread of the fitted temperature, over the
    # PlantVillage-trained models only. Those are the checkpoints whose
    # temperature is transported across the shift, so they are what the claim
    # is about; the PlantDoc-trained temperatures are six times more variable
    # and pooling them would overstate the spread by an order of magnitude.
    temp_sds = []
    for model in MODEL_TAG:
        temps = [runs[f"pv_{model}_s{s}"]["calibration"]["temperature"]
                 for s in SEEDS
                 if f"pv_{model}_s{s}" in runs
                 and "calibration" in runs[f"pv_{model}_s{s}"]]
        if len(temps) > 1:
            temp_sds.append(float(np.std(temps, ddof=1)))
    m.add("TempSdMax", num(max(temp_sds), 4) if temp_sds else None,
          "calibration transport")

    # ---- 21-class in-domain control ------------------------------------------ #
    # PlantVillage test scored through the identical shared-space pipeline, so
    # the comparison is 21-way to 21-way and the label-space change is removed
    # from the drop. Written by scripts/ica26_shared_space_control.py.
    #
    # Aggregated here from the per-run entries, with the same helpers and the
    # same within-seed pairing as every other cell, rather than copied from the
    # file's own summary block. The summary is then required to agree, so a
    # summary edited out of step with its runs stops the build instead of
    # reaching the paper.
    control_path = METRICS / "shared_space_control.json"
    control = json.loads(control_path.read_text()) if control_path.exists() else None
    per_run_control = (control or {}).get("per_run", {})
    section = "21-class in-domain control"
    for model, mtag in MODEL_TAG.items():
        f1_shared, drops, masses = [], [], []
        for seed in SEEDS:
            rid = f"pv_{model}_s{seed}"
            entry = per_run_control.get(rid)
            xd = (runs.get(rid) or {}).get("evaluations", {}).get("cross_domain_plantdoc_core")
            if not entry:
                continue
            f1_shared.append(entry["macro_f1"])
            masses.append(entry["mean_retained_probability_mass_before_renormalisation"])
            if xd:
                drops.append((entry["macro_f1"] - xd["macro_f1"]) / entry["macro_f1"] * 100)
        s = (control or {}).get("summary", {}).get(model)
        if s and len(f1_shared) == len(SEEDS) and len(drops) == len(SEEDS):
            for key, value in (
                ("macro_f1_in_domain_shared_mean", float(np.mean(f1_shared))),
                ("macro_f1_in_domain_shared_sd", float(np.std(f1_shared, ddof=1))),
                ("relative_drop_percent_mean", float(np.mean(drops))),
                ("relative_drop_percent_sd", float(np.std(drops, ddof=1))),
            ):
                if abs(s[key] - value) > 1e-9:
                    raise RuntimeError(
                        f"shared_space_control.json summary.{model}.{key} = {s[key]} "
                        f"disagrees with its per_run entries ({value})")
        m.add(f"MacroFPvInShared{mtag}", agg(f1_shared), section)
        m.add(f"MacroFMeanPvInShared{mtag}", mean_only(f1_shared), section)
        m.add(f"RelDropFShared{mtag}", agg(drops, 1), section)
        m.add(f"RelDropFSharedMean{mtag}", mean_only(drops, 1), section)
        m.add(f"RetainedMassPvInShared{mtag}", agg(masses, 3), section)
    n_scored = {e["n_evaluated"] for e in per_run_control.values()}
    if len(n_scored) > 1:
        raise RuntimeError(f"shared-space control scored differing image counts: {n_scored}")
    m.add("NPvTestShared", integer(n_scored.pop()) if n_scored else None, section)

    # ---- retained probability mass ------------------------------------------ #
    for model, mtag in MODEL_TAG.items():
        blocks = blocks_for(runs, "pv", model, "cross_domain_plantdoc_core")
        m.add(f"RetainedMass{mtag}",
              agg([b["protocol"]["mean_retained_probability_mass_before_renormalisation"]
                   for b in blocks], 3),
              "cross-domain protocol")

    # ---- efficiency ---------------------------------------------------------- #
    param_totals: dict[str, int | None] = {}
    for model, mtag in MODEL_TAG.items():
        params, lat = None, []
        for prefix in ("pv", "pdc"):
            for seed in SEEDS:
                res = runs.get(f"{prefix}_{model}_s{seed}")
                if not res:
                    continue
                params = res["efficiency"]["total_parameters"]
                if res["efficiency"].get("inference_latency_ms_batch1") is not None:
                    lat.append(res["efficiency"]["inference_latency_ms_batch1"])
        m.add(f"Params{mtag}",
              None if params is None else f"{params / 1e6:.1f}", "efficiency")
        m.add(f"Latency{mtag}", agg(lat, 2), "efficiency")
        param_totals[model] = params

    # Capacity span across the backbones, as a claim derived from the counts
    # rather than a number recalled into the prose.
    if param_totals.get("resnet50") and param_totals.get("mobilenet_v3_small"):
        ratio = param_totals["resnet50"] / param_totals["mobilenet_v3_small"]
        m.add("ParamRatio", f"{ratio:.0f}", "efficiency")
    else:
        m.add("ParamRatio", None, "efficiency")

    # ---- significance -------------------------------------------------------- #
    if sig:
        m.add("SigSeed", sig["seed"], "significance")
        m.add("NBootstrap", integer(sig["method"]["n_bootstrap"]), "significance")
        for setting in sig["settings"]:
            stag = SIG_SETTING_TAG.get(setting["setting"])
            if not stag:
                continue
            for ci in setting["confidence_intervals"]:
                mtag = SIG_MODEL_TAG[ci["model"]]
                for key, ktag in (("accuracy", "Acc"), ("macro_f1", "F")):
                    c = ci[key]
                    m.add(f"Ci{ktag}{stag}{mtag}",
                          rf"\ensuremath{{[{c['ci_lower']:.4f},\, {c['ci_upper']:.4f}]}}",
                          f"significance: CIs {stag}")
            for pair in setting["pairwise_mcnemar"]:
                a, b = SIG_MODEL_TAG[pair["model_a"]], SIG_MODEL_TAG[pair["model_b"]]
                m.add(f"PMc{stag}{a}{b}", _fmt_p(pair["p_value"]),
                      f"significance: McNemar {stag}")
                m.add(f"PMcHolm{stag}{a}{b}", _fmt_p(pair.get("p_value_holm")),
                      f"significance: McNemar {stag}")
                m.add(f"NDisc{stag}{a}{b}", pair["n_discordant"],
                      f"significance: McNemar {stag}")
    else:
        m.add("SigSeed", None, "significance")
        m.add("NBootstrap", None, "significance")

    header = [
        "% ICA 2026 -- generated result macros. DO NOT EDIT BY HAND.",
        "%",
        "% Written by scripts/ica26_build_paper_macros.py from:",
        "%   data/manifests/ica26_core_experiment_lock.json",
        "%   experiments/ica26/metrics/*.json",
        "%   experiments/ica26/metrics/significance.json",
        "%   experiments/ica26/metrics/shared_space_control.json",
        "%",
        "% Regenerate after any run completes:",
        "%   python scripts/ica26_build_paper_macros.py",
        "%",
        f"% seeds complete : {seeds_done}",
        f"% runs complete  : {len(complete)}/{len(SEEDS) * 6}",
        f"% pending macros : {m.n_pending}",
        "",
        "% Typeset marker for a number that does not exist yet. A draft with any",
        "% of these is visibly incomplete rather than quietly wrong.",
        r"\providecommand{\ResultPending}{\textbf{[PENDING]}}",
    ]
    return m.render(header), {
        "n_macros": len(m.items),
        "n_pending": m.n_pending,
        "seeds_done": seeds_done,
        "runs_done": len(complete),
    }


def _fmt_p(p) -> str | None:
    if p is None:
        return None
    if p < 1e-4:
        return r"\ensuremath{<0.0001}"
    return rf"\ensuremath{{{p:.4f}}}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="rebuild and compare, write nothing")
    ap.add_argument("--out", type=Path, default=OUT,
                    help="macro file to write or check (default: %(default)s)")
    args = ap.parse_args()
    out = args.out if args.out.is_absolute() else REPO / args.out

    text, summary = build()

    if args.check:
        if not out.exists():
            print(f"MISSING {out}", file=sys.stderr)
            return 1
        if out.read_text() != text:
            print("CHECK FAILED: generated macros differ from the committed file",
                  file=sys.stderr)
            return 1
        print("check OK: macros are identical to the committed file")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote          : {out.relative_to(REPO) if out.is_relative_to(REPO) else out}")
    print(f"macros         : {summary['n_macros']}")
    print(f"pending        : {summary['n_pending']}")
    print(f"seeds complete : {summary['seeds_done']}")
    print(f"runs complete  : {summary['runs_done']}/{len(SEEDS) * 6}")
    if summary["n_pending"]:
        print("NOTE: pending macros typeset as [PENDING]; no value is invented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
