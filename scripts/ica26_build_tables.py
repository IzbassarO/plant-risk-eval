#!/usr/bin/env python3
"""Generate the ICA 2026 paper tables and figures from result files.

Every number is read from experiments/ica26/metrics/*.json. Nothing is typed in
by hand and nothing is estimated: a run that has not finished is reported as
missing, never filled in.

    python scripts/ica26_build_tables.py

Outputs CSV + LaTeX under experiments/ica26/tables and PNG under
experiments/ica26/figures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

# Figures are emitted as vector PDF for the camera-ready. These must be set
# before any figure is created, or they apply only to figures built afterwards.
# Type 42 embeds TrueType outlines rather than referencing Type 3 bitmaps, which
# is what Springer's production check flags as a missing font.
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["pdf.compression"] = 9
matplotlib.rcParams["font.family"] = "serif"
matplotlib.rcParams["font.size"] = 8

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# LNCS text width is 122 mm = 4.8 in. Figures are authored at exactly that width
# so \includegraphics[width=\textwidth] applies no scaling and an 8 pt label
# renders at 8 pt. Sizing a figure larger and letting LaTeX shrink it is how
# figure text ends up smaller than the caption beneath it.
TEXT_WIDTH_IN = 4.8
FIG_SINGLE = (TEXT_WIDTH_IN, 3.2)        # one panel
FIG_ROW3 = (TEXT_WIDTH_IN, 1.8)          # three panels side by side
FIG_GRID22 = (TEXT_WIDTH_IN, 3.6)        # two rows of two
FIG_CONFUSION = (TEXT_WIDTH_IN, 4.4)     # near-square, dense tick labels

# Paper-facing summary figures also get a PNG, purely so the repository and any
# reviewer packet can be skimmed without a PDF viewer. The per-run diagnostic
# figures (confusion matrices, reliability diagrams) are PDF-only: there are
# dozens of them and duplicating every one buys nothing.
PREVIEW_PNG = {"fig_training_curves", "fig_risk_coverage", "fig_seed_spread"}


def _save(fig, name: str, raster_dpi: int | None = None) -> None:
    """Write a figure as vector PDF, plus a PNG preview for paper-facing ones.

    ``raster_dpi`` applies to figures containing an ``imshow`` image, which
    stays a raster inside the PDF however it is saved; the DPI then decides
    whether that embedded raster is print quality.
    """
    FIGURES.mkdir(parents=True, exist_ok=True)
    kwargs = {"bbox_inches": "tight"}
    if raster_dpi is not None:
        kwargs["dpi"] = raster_dpi
    fig.savefig(FIGURES / f"{name}.pdf", **kwargs)
    if name in PREVIEW_PNG:
        fig.savefig(FIGURES / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

METRICS = REPO / "experiments/ica26/metrics"
TABLES = REPO / "experiments/ica26/tables"
FIGURES = REPO / "experiments/ica26/figures"

MODEL_ORDER = ["resnet50", "efficientnet_b0", "mobilenet_v3_small"]
MODEL_DISPLAY = {
    "resnet50": "ResNet-50",
    "efficientnet_b0": "EfficientNet-B0",
    "mobilenet_v3_small": "MobileNetV3-Small",
}
DATASET_DISPLAY = {"plantvillage": "PlantVillage", "plantdoc_core": "PlantDoc Core"}

# Seed 42 was the initial single-seed matrix; 1337 and 2026 are the repetitions
# derived by scripts/ica26_make_seed_configs.py. Reported metrics are aggregated
# across whichever of these actually produced a result file.
SEEDS = [42, 1337, 2026]
CONFIGS = [
    (prefix, model)
    for prefix in ("pv", "pdc")
    for model in MODEL_ORDER
]
RUN_IDS = [f"{prefix}_{model}_s{seed}" for prefix, model in CONFIGS for seed in SEEDS]
DATASET_OF_PREFIX = {"pv": "PlantVillage", "pdc": "PlantDoc Core"}


def load_results() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rid in RUN_IDS:
        p = METRICS / f"{rid}.json"
        if p.exists():
            out[rid] = json.loads(p.read_text())
    return out


def seed_results(results: dict, prefix: str, model: str) -> list[tuple[int, dict]]:
    """Every completed seed for one (dataset, backbone) cell, in seed order."""
    return [(s, results[f"{prefix}_{model}_s{s}"])
            for s in SEEDS if f"{prefix}_{model}_s{s}" in results]


def _agg(values) -> dict:
    """Mean and sample standard deviation over the seeds that produced a value.

    ``std`` is ``None`` for a single seed rather than 0.0: one run has no
    variance estimate, and printing 0.0 would claim it does.
    """
    vals = [float(v) for v in values if v is not None and not pd.isna(v)]
    if not vals:
        return {"mean": None, "std": None, "n": 0}
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else None,
        "n": len(arr),
    }


def _pm(agg: dict, places: int = 4) -> str:
    """Format an aggregate as ``mean ± std``; a lone seed prints just the mean."""
    if agg["mean"] is None:
        return "—"
    if agg["std"] is None:
        return f"{agg['mean']:.{places}f}"
    return f"{agg['mean']:.{places}f} ± {agg['std']:.{places}f}"


def _agg_pm(values, places: int = 4) -> str:
    return _pm(_agg(values), places)


def _write(df: pd.DataFrame, name: str, caption: str, label: str, float_fmt: str = "%.4f") -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / f"{name}.csv", index=False)
    latex = df.to_latex(
        index=False, escape=True, float_format=float_fmt,
        caption=caption, label=label, position="htbp",
    )
    # pandas escapes LaTeX specials but passes non-ASCII through as raw bytes,
    # and U+2192 in particular is undefined under pdflatex's utf8 inputenc.
    # Swapping the few characters this script deliberately introduces for their
    # math-mode equivalents after escaping keeps the CSV readable and the .tex
    # portable across pdflatex, xelatex, and lualatex. `>` is escaped too: it is
    # only ever the ranking separator here, and it renders as an inverted
    # question mark under the OT1 encoding.
    for raw, tex in (("±", r"$\pm$"), ("→", r"$\rightarrow$"), (" > ", r" $>$ ")):
        latex = latex.replace(raw, tex)
    (TABLES / f"{name}.tex").write_text(latex)
    print(f"  wrote {name}.csv / {name}.tex  ({len(df)} rows)")


def _write_per_seed(rows: list[dict], name: str) -> None:
    """Per-seed long-format companion to an aggregated table.

    The aggregated tables are what the paper cites; these files are what make
    the aggregation auditable, so a reader can recompute every mean and standard
    deviation without rerunning anything.
    """
    if not rows:
        return
    TABLES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(TABLES / f"{name}.csv", index=False)
    print(f"  wrote {name}.csv  ({len(rows)} rows, per-seed)")


# --------------------------------------------------------------------------- #
# 1. dataset statistics
# --------------------------------------------------------------------------- #
def table_dataset_statistics() -> None:
    lock = json.loads((REPO / "data/manifests/ica26_core_experiment_lock.json").read_text())
    rows = []
    for key, disp in DATASET_DISPLAY.items():
        c = lock["corpora"][key]
        rows.append({
            "Dataset": disp,
            "Images": c["n_records"],
            "Train": c["split_counts"].get("train", 0),
            "Test": c["split_counts"].get("test", 0),
            "Classes": c["n_classes"],
        })
    cd = lock["cross_domain_mapping"]
    df = pd.DataFrame(rows)
    _write(df, "table1_dataset_statistics",
           "Dataset composition after leakage control and conservative exclusion. "
           f"The cross-domain evaluation subset holds {cd['n_evaluable_plantdoc_core_images']} "
           f"PlantDoc Core images over {cd['n_shared_classes']} shared classes.",
           "tab:dataset-stats", float_fmt="%.0f")

    ex = lock["expected_counts"]
    prov = pd.DataFrame([
        {"Quantity": "PlantDoc acquired (source)", "Value": ex["plantdoc"]["source"]},
        {"Quantity": "PlantDoc previous effective", "Value": ex["plantdoc"]["previous_effective"]},
        {"Quantity": "PlantDoc Core", "Value": ex["plantdoc"]["core"]},
        {"Quantity": "PlantDoc non-reviewed unchanged", "Value": ex["plantdoc"]["non_reviewed_unchanged"]},
        {"Quantity": "PlantDoc retained reviewed", "Value": ex["plantdoc"]["retained_reviewed"]},
        {"Quantity": "PlantDoc excluded reviewed", "Value": ex["plantdoc"]["excluded_reviewed"]},
        {"Quantity": "Cross-dataset exact duplicates (acquired)", "Value": ex["leakage"]["acquired"]["exact"]},
        {"Quantity": "Cross-dataset near duplicates (acquired)", "Value": ex["leakage"]["acquired"]["near"]},
        {"Quantity": "Cross-dataset exact duplicates (Core)", "Value": ex["leakage"]["core"]["exact"]},
        {"Quantity": "Cross-dataset near duplicates (Core)", "Value": ex["leakage"]["core"]["near"]},
        {"Quantity": "Unresolved leakage pairs", "Value": ex["leakage"]["core"]["unresolved"]},
        {"Quantity": "Shared cross-domain classes", "Value": cd["n_shared_classes"]},
        {"Quantity": "Cross-domain evaluation images", "Value": cd["n_evaluable_plantdoc_core_images"]},
    ])
    _write(prov, "table1b_dataset_provenance",
           "Dataset provenance and leakage control. Perceptual-hash Hamming threshold 6; "
           "all 16 near pairs human-adjudicated as clearly different.",
           "tab:dataset-provenance", float_fmt="%.0f")


# --------------------------------------------------------------------------- #
# 2 & 3. in-domain and cross-domain performance
# --------------------------------------------------------------------------- #
PERF_METRICS = [
    ("Accuracy", "accuracy"),
    ("Macro-F1", "macro_f1"),
    ("Weighted-F1", "weighted_f1"),
    ("Balanced Acc.", "balanced_accuracy"),
    ("Macro Prec.", "macro_precision"),
    ("Macro Rec.", "macro_recall"),
]


def _perf_agg_row(model: str, dataset: str, blocks: list[tuple[int, dict]]) -> dict:
    """One aggregated table row over the seeds available for this cell."""
    row = {
        "Model": MODEL_DISPLAY[model],
        "Dataset": dataset,
        "Seeds": len(blocks),
        # The evaluation split is fixed by the dataset lock, so N is identical
        # across seeds by construction; assert that rather than averaging it.
        "N": blocks[0][1]["n_samples"],
    }
    for disp, key in PERF_METRICS:
        row[disp] = _agg_pm([b[key] for _, b in blocks])
    return row


def _perf_seed_rows(model: str, dataset: str, blocks: list[tuple[int, dict]]) -> list[dict]:
    return [
        {"Model": MODEL_DISPLAY[model], "Dataset": dataset, "Seed": seed,
         "N": b["n_samples"], **{disp: b[key] for disp, key in PERF_METRICS}}
        for seed, b in blocks
    ]


def table_in_domain(results: dict) -> pd.DataFrame:
    rows, per_seed = [], []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            runs = seed_results(results, prefix, model)
            blocks = [(s, r["evaluations"]["in_domain_test"]) for s, r in runs
                      if "in_domain_test" in r["evaluations"]]
            if not blocks:
                continue
            n_values = {b["n_samples"] for _, b in blocks}
            if len(n_values) > 1:
                raise RuntimeError(
                    f"{prefix}_{model}: in-domain test size differs across seeds {n_values}; "
                    "the evaluation split is locked and must not vary"
                )
            rows.append(_perf_agg_row(model, dataset, blocks))
            per_seed += _perf_seed_rows(model, dataset, blocks)
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table2_in_domain_performance",
               "In-domain test performance, mean $\\pm$ sample standard deviation over "
               "independent training seeds (42, 1337, 2026). Macro averages are computed over "
               "the classes present in the evaluation split; PlantDoc Core's arthropod-pest "
               "class has zero test images and is reported separately rather than averaged in "
               "as zero.",
               "tab:in-domain")
        _write_per_seed(per_seed, "table2_in_domain_performance_per_seed")
    return df


def table_cross_domain(results: dict) -> pd.DataFrame:
    rows, per_seed = [], []
    for model in MODEL_ORDER:
        runs = seed_results(results, "pv", model)
        blocks = [(s, r["evaluations"]["cross_domain_plantdoc_core"]) for s, r in runs
                  if "cross_domain_plantdoc_core" in r["evaluations"]]
        if not blocks:
            continue
        r = _perf_agg_row(model, "PlantVillage → PlantDoc Core", blocks)
        r["Shared classes"] = blocks[0][1]["protocol"]["n_shared_classes"]
        r["Retained prob. mass"] = _agg_pm(
            [b["protocol"]["mean_retained_probability_mass_before_renormalisation"]
             for _, b in blocks]
        )
        rows.append(r)
        per_seed += _perf_seed_rows(model, "PlantVillage → PlantDoc Core", blocks)
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table3_cross_domain_performance",
               "Cross-domain generalisation, mean $\\pm$ sample standard deviation over three "
               "seeds: PlantVillage-trained models evaluated on the frozen shared-class "
               "PlantDoc Core subset. Metrics are computed only over the 21 shared classes; "
               "unmapped PlantDoc images are excluded from the evaluation set rather than "
               "counted as errors. Retained probability mass is the share of the source "
               "model's belief falling inside the shared space before renormalisation.",
               "tab:cross-domain")
        _write_per_seed(per_seed, "table3_cross_domain_performance_per_seed")
    return df


# --------------------------------------------------------------------------- #
# 4. efficiency
# --------------------------------------------------------------------------- #
def table_efficiency(results: dict) -> None:
    rows, per_seed = [], []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            runs = seed_results(results, prefix, model)
            if not runs:
                continue
            effs = [r["efficiency"] for _, r in runs]
            trains = [r["training"] for _, r in runs]
            rows.append({
                "Model": MODEL_DISPLAY[model],
                "Dataset": dataset,
                "Seeds": len(runs),
                # Parameter count is a property of the architecture, not the run.
                "Params (M)": round(effs[0]["total_parameters"] / 1e6, 2),
                "Epochs": _agg_pm([t["epochs_run"] for t in trains], places=1),
                "Train time (min)": _agg_pm(
                    [e["training_time_seconds"] / 60 for e in effs], places=1),
                "s / epoch": _agg_pm(
                    [e.get("seconds_per_epoch") for e in effs], places=1),
                "Latency b1 (ms)": _agg_pm(
                    [e.get("inference_latency_ms_batch1") for e in effs], places=2),
                "Throughput (img/s)": _agg_pm(
                    [e.get("inference_throughput_img_per_s") for e in effs], places=1),
                "Peak mem (MB)": _agg_pm([e.get("peak_memory_mb") for e in effs], places=1),
            })
            per_seed += [
                {"Model": MODEL_DISPLAY[model], "Dataset": dataset, "Seed": seed,
                 "Params (M)": round(r["efficiency"]["total_parameters"] / 1e6, 2),
                 "Epochs": r["training"]["epochs_run"],
                 "Train time (min)": round(r["efficiency"]["training_time_seconds"] / 60, 2),
                 "s / epoch": r["efficiency"].get("seconds_per_epoch"),
                 "Latency b1 (ms)": r["efficiency"].get("inference_latency_ms_batch1"),
                 "Throughput (img/s)": r["efficiency"].get("inference_throughput_img_per_s"),
                 "Peak mem (MB)": r["efficiency"].get("peak_memory_mb")}
                for seed, r in runs
            ]
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table4_efficiency",
               "Model efficiency, mean $\\pm$ sample standard deviation over three seeds. "
               "Epoch counts vary between seeds because early stopping fires at different "
               "points, so training time is reported alongside seconds per epoch. Latency and "
               "throughput are measured after warm-up on the accelerator reported in the run "
               "metadata.",
               "tab:efficiency", float_fmt="%.2f")
        _write_per_seed(per_seed, "table4_efficiency_per_seed")


# --------------------------------------------------------------------------- #
# 5. domain-shift degradation
# --------------------------------------------------------------------------- #
def table_degradation(results: dict) -> None:
    rows, per_seed = [], []
    for model in MODEL_ORDER:
        paired = []
        for seed, res in seed_results(results, "pv", model):
            ind = res["evaluations"].get("in_domain_test")
            cd = res["evaluations"].get("cross_domain_plantdoc_core")
            if ind and cd:
                paired.append((seed, ind, cd))
        if not paired:
            continue
        row = {"Model": MODEL_DISPLAY[model], "Seeds": len(paired)}
        seed_row = {}
        for metric, key in (("Accuracy", "accuracy"), ("Macro-F1", "macro_f1")):
            # Drops are computed within a seed and then averaged. Differencing
            # the two seed-averages instead would discard the pairing, which is
            # the only thing that makes the drop a per-model quantity.
            ins = [ind[key] for _, ind, _ in paired]
            outs = [cd[key] for _, _, cd in paired]
            abs_drop = [a - b for a, b in zip(ins, outs)]
            rel_drop = [(a - b) / a * 100 for a, b in zip(ins, outs) if a]
            row[f"{metric} (in-domain)"] = _agg_pm(ins)
            row[f"{metric} (cross-domain)"] = _agg_pm(outs)
            row[f"{metric} abs. drop"] = _agg_pm(abs_drop)
            row[f"{metric} rel. drop %"] = _agg_pm(rel_drop, places=2)
            seed_row[key] = (ins, outs, abs_drop, rel_drop)
        rows.append(row)
        for i, (seed, _, _) in enumerate(paired):
            entry = {"Model": MODEL_DISPLAY[model], "Seed": seed}
            for metric, key in (("Accuracy", "accuracy"), ("Macro-F1", "macro_f1")):
                ins, outs, abs_drop, rel_drop = seed_row[key]
                entry[f"{metric} (in-domain)"] = ins[i]
                entry[f"{metric} (cross-domain)"] = outs[i]
                entry[f"{metric} abs. drop"] = abs_drop[i]
                entry[f"{metric} rel. drop %"] = rel_drop[i] if i < len(rel_drop) else None
            per_seed.append(entry)
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table5_domain_shift_degradation",
               "Domain-shift degradation, mean $\\pm$ sample standard deviation over three "
               "seeds. Drops are computed within each seed and then averaged, preserving the "
               "pairing between a checkpoint and its own cross-domain evaluation. In-domain is "
               "the PlantVillage test split over 38 classes; cross-domain is the PlantDoc Core "
               "shared-class subset over 21 classes. The two label spaces differ, so the drop "
               "combines domain shift with the change of task difficulty and should be read as "
               "a paired trend across models rather than as an isolated quantity.",
               "tab:degradation")
        _write_per_seed(per_seed, "table5_domain_shift_degradation_per_seed")


# --------------------------------------------------------------------------- #
# 6. calibration
# --------------------------------------------------------------------------- #
CALIBRATION_SETTINGS = (
    ("in_domain_test", "in-domain"),
    ("in_domain_test_temperature_scaled", "in-domain (T-scaled)"),
    ("cross_domain_plantdoc_core", "cross-domain"),
    ("cross_domain_plantdoc_core_temperature_scaled", "cross-domain (T-scaled)"),
)
CALIBRATION_METRICS = [
    ("NLL", lambda b: b["probabilistic"]["negative_log_likelihood"]),
    ("Brier", lambda b: b["probabilistic"]["brier_score"]),
    ("ECE", lambda b: b["probabilistic"]["expected_calibration_error"]),
    ("MCE", lambda b: b["probabilistic"]["maximum_calibration_error"]),
    ("AURC", lambda b: b.get("selective_prediction", {}).get("area_under_risk_coverage")),
    # Read the temperature the block actually used. Inferring it from the row
    # label previously reported T=1.0 for cross-domain rows that had in fact
    # been temperature-scaled.
    ("T", lambda b: b.get("temperature") or 1.0),
]


def table_calibration(results: dict) -> None:
    rows, per_seed = [], []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            runs = seed_results(results, prefix, model)
            for eval_name, disp in CALIBRATION_SETTINGS:
                blocks = [(s, r["evaluations"][eval_name]) for s, r in runs
                          if eval_name in r["evaluations"]
                          and "probabilistic" in r["evaluations"][eval_name]]
                if not blocks:
                    continue
                row = {"Model": MODEL_DISPLAY[model], "Dataset": dataset,
                       "Setting": disp, "Seeds": len(blocks)}
                for name, getter in CALIBRATION_METRICS:
                    row[name] = _agg_pm([getter(b) for _, b in blocks])
                rows.append(row)
                per_seed += [
                    {"Model": MODEL_DISPLAY[model], "Dataset": dataset, "Setting": disp,
                     "Seed": seed, **{name: getter(b) for name, getter in CALIBRATION_METRICS}}
                    for seed, b in blocks
                ]
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table6_calibration",
               "Confidence calibration and selective prediction, mean $\\pm$ sample standard "
               "deviation over three seeds. Temperature is fitted on the held-out validation "
               "split only and applied unchanged to test and cross-domain logits; it is never "
               "refitted on evaluation data. AURC is the area under the risk-coverage curve; "
               "lower is better.",
               "tab:calibration")
        _write_per_seed(per_seed, "table6_calibration_per_seed")


# --------------------------------------------------------------------------- #
# 7. ranking stability across seeds
# --------------------------------------------------------------------------- #
RANKING_SETTINGS = [
    ("PlantVillage in-domain", "pv", "in_domain_test"),
    ("PlantVillage → PlantDoc Core", "pv", "cross_domain_plantdoc_core"),
    ("PlantDoc Core in-domain", "pdc", "in_domain_test"),
]


def _macro_f1_by_model(results: dict, prefix: str, eval_name: str) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for model in MODEL_ORDER:
        per_seed = {}
        for seed, res in seed_results(results, prefix, model):
            block = res["evaluations"].get(eval_name)
            if block:
                per_seed[seed] = block["macro_f1"]
        if per_seed:
            out[model] = per_seed
    return out


def table_ranking_stability(results: dict) -> None:
    """Does the backbone ordering survive reseeding, and does it survive the shift?

    A ranking flip between two evaluation settings is only a finding if the gap
    that produces it is larger than the gap the seed alone produces. This table
    reports the per-seed ordering next to the between-model margin and the seed
    spread, so the two can be compared directly rather than asserted.
    """
    rank_rows, margin_rows = [], []

    for disp, prefix, eval_name in RANKING_SETTINGS:
        by_model = _macro_f1_by_model(results, prefix, eval_name)
        if len(by_model) < 2:
            continue
        seeds_here = sorted(set.intersection(*(set(v) for v in by_model.values())))

        orderings = []
        for seed in seeds_here:
            order = sorted(by_model, key=lambda m: by_model[m][seed], reverse=True)
            orderings.append(tuple(order))
            rank_rows.append({
                "Setting": disp,
                "Seed": seed,
                "Ranking (macro-F1; best first)": " > ".join(MODEL_DISPLAY[m] for m in order),
                **{f"{MODEL_DISPLAY[m]} macro-F1": round(by_model[m][seed], 4) for m in MODEL_ORDER
                   if m in by_model},
            })
        if orderings:
            modal = max(set(orderings), key=orderings.count)
            rank_rows.append({
                "Setting": disp,
                "Seed": "all",
                "Ranking (macro-F1; best first)": (
                    f"{'STABLE' if len(set(orderings)) == 1 else 'UNSTABLE'}: "
                    f"{orderings.count(modal)}/{len(orderings)} seeds give "
                    + " > ".join(MODEL_DISPLAY[m] for m in modal)
                ),
                **{f"{MODEL_DISPLAY[m]} macro-F1": round(
                    float(np.mean([by_model[m][s] for s in seeds_here])), 4)
                   for m in MODEL_ORDER if m in by_model},
            })

        # Pairwise margins against seed noise.
        models_here = [m for m in MODEL_ORDER if m in by_model]
        for i, a in enumerate(models_here):
            for b in models_here[i + 1:]:
                diffs = [by_model[a][s] - by_model[b][s] for s in seeds_here]
                agg_d = _agg(diffs)
                spread = _agg([by_model[a][s] for s in seeds_here])["std"]
                spread_b = _agg([by_model[b][s] for s in seeds_here])["std"]
                pooled = (None if spread is None or spread_b is None
                          else float(np.sqrt((spread ** 2 + spread_b ** 2) / 2)))
                n_pos = sum(1 for d in diffs if d > 0)
                margin_rows.append({
                    "Setting": disp,
                    "Comparison": f"{MODEL_DISPLAY[a]} - {MODEL_DISPLAY[b]}",
                    "Seeds": len(diffs),
                    "Mean margin": _pm(agg_d),
                    "Pooled seed SD": "—" if pooled is None else f"{pooled:.4f}",
                    "|Margin| / seed SD": (
                        "—" if not pooled or agg_d["mean"] is None
                        else f"{abs(agg_d['mean']) / pooled:.2f}"),
                    "Sign consistent": f"{max(n_pos, len(diffs) - n_pos)}/{len(diffs)}",
                })

    if rank_rows:
        _write(pd.DataFrame(rank_rows), "table7_ranking_stability",
               "Backbone ranking by macro-F1 under each evaluation setting, per seed. A "
               "setting is STABLE when all seeds agree on the ordering. This is the direct "
               "test of whether the in-domain ranking predicts the cross-domain ranking, or "
               "whether an apparent reordering is within seed noise.",
               "tab:ranking-stability")
    if margin_rows:
        _write(pd.DataFrame(margin_rows), "table7b_ranking_margins",
               "Pairwise macro-F1 margins against seed noise. The margin is computed within "
               "each seed and then averaged. Pooled seed SD is the root-mean-square of the two "
               "models' across-seed standard deviations. A margin comfortably exceeding the "
               "seed SD, with a consistent sign across all seeds, is a difference the seed "
               "alone does not explain; one below it is not claimed. With three seeds these "
               "are descriptive ratios, not significance tests.",
               "tab:ranking-margins")


# --------------------------------------------------------------------------- #
# figures
# --------------------------------------------------------------------------- #
MODEL_COLOUR = {
    "resnet50": "#1f77b4",
    "efficientnet_b0": "#d62728",
    "mobilenet_v3_small": "#2ca02c",
}
SEED_STYLE = {42: "-", 1337: "--", 2026: ":"}


def figure_training_curves(results: dict) -> None:
    """One panel per (corpus, quantity); colour is the backbone, dash is the seed.

    Eighteen runs on two axes is unreadable, and averaging epoch-indexed curves
    across seeds would be worse: early stopping fires at different epochs, so a
    mean curve would silently shorten to the earliest stop. Every seed is drawn.
    """
    if not results:
        return
    fig, axes = plt.subplots(2, 2, figsize=FIG_GRID22)
    handles: dict[str, object] = {}
    for row, (prefix, corpus) in enumerate((("pv", "PlantVillage"), ("pdc", "PlantDoc Core"))):
        for model in MODEL_ORDER:
            for seed, res in seed_results(results, prefix, model):
                hist = res["training"]["history"]
                ep = [h["epoch"] for h in hist]
                style = dict(color=MODEL_COLOUR[model], ls=SEED_STYLE.get(seed, "-"),
                             lw=0.9, marker="o", ms=1.6)
                axes[row][0].plot(ep, [h["train_loss"] for h in hist], **style)
                line, = axes[row][1].plot(ep, [h["val_macro_f1"] for h in hist], **style)
                handles.setdefault(f"{MODEL_DISPLAY[model]} s{seed}", line)
        axes[row][0].set_title(f"{corpus} — training loss", fontsize=7)
        axes[row][1].set_title(f"{corpus} — validation macro-F1", fontsize=7)
        axes[row][0].set_ylabel("train loss", fontsize=7)
        axes[row][1].set_ylabel("val macro-F1", fontsize=7)
        for ax in axes[row]:
            ax.set_xlabel("epoch", fontsize=7)
            ax.tick_params(labelsize=6)
            ax.grid(alpha=0.3, lw=0.4)
    # One shared legend below the grid: nine per-axes entries at this width
    # would cover the curves they describe.
    if handles:
        fig.legend(handles.values(), handles.keys(), fontsize=5, ncol=3,
                   loc="upper center", bbox_to_anchor=(0.5, 0.03), frameon=False)
    fig.tight_layout()
    _save(fig, "fig_training_curves")
    print("  wrote fig_training_curves.pdf (+png preview)")


def figure_seed_spread(results: dict) -> None:
    """Between-model margins next to across-seed spread, for the ranking claim."""
    panels = [(d, p, e) for d, p, e in RANKING_SETTINGS
              if len(_macro_f1_by_model(results, p, e)) >= 2]
    if not panels:
        return
    fig, axes = plt.subplots(1, len(panels), figsize=FIG_ROW3, squeeze=False)
    # Backbone names do not fit under a 1.6 in panel, so the x axis carries
    # short codes and a shared legend expands them once.
    short = {"resnet50": "R50", "efficientnet_b0": "EB0", "mobilenet_v3_small": "MNv3"}
    for ax, (disp, prefix, eval_name) in zip(axes[0], panels):
        by_model = _macro_f1_by_model(results, prefix, eval_name)
        models_here = [m for m in MODEL_ORDER if m in by_model]
        for x, model in enumerate(models_here):
            vals = [by_model[model][s] for s in sorted(by_model[model])]
            agg = _agg(vals)
            ax.errorbar(x, agg["mean"], yerr=(agg["std"] or 0.0), fmt="o", ms=3.5,
                        capsize=2.5, color=MODEL_COLOUR[model], lw=1.0)
            # Every seed drawn beside the mean: with n=3 the individual points
            # are more informative than the error bar computed from them.
            ax.scatter([x + 0.16] * len(vals), vals, s=5, alpha=0.65,
                       color=MODEL_COLOUR[model], zorder=3)
        ax.set_xticks(range(len(models_here)))
        ax.set_xticklabels([short[m] for m in models_here], fontsize=6)
        ax.set_xlim(-0.5, len(models_here) - 0.3)
        ax.tick_params(labelsize=6)
        ax.set_title(disp, fontsize=6)
        ax.grid(alpha=0.3, axis="y", lw=0.4)
    axes[0][0].set_ylabel("macro-F1", fontsize=7)
    fig.legend(
        handles=[plt.Line2D([], [], color=MODEL_COLOUR[m], marker="o", ms=3, lw=0,
                            label=f"{short[m]} = {MODEL_DISPLAY[m]}") for m in MODEL_ORDER],
        fontsize=5, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 0.06), frameon=False,
    )
    fig.tight_layout()
    _save(fig, "fig_seed_spread")
    print("  wrote fig_seed_spread.pdf (+png preview)")


def figure_confusion(results: dict) -> None:
    """Row-normalised confusion matrices, one per run and evaluation.

    ``imshow`` produces an embedded raster no matter how the figure is saved,
    so these are the one case where save DPI still decides print quality.
    ``interpolation="nearest"`` keeps cell boundaries crisp instead of letting
    the viewer smooth a 38x38 grid into mush.
    """
    n_written = 0
    for rid, res in results.items():
        for eval_name in ("in_domain_test", "cross_domain_plantdoc_core"):
            block = res["evaluations"].get(eval_name)
            if not block:
                continue
            cm = np.array(block["confusion_matrix"], dtype=float)
            labels = block["confusion_matrix_labels"]
            with np.errstate(invalid="ignore"):
                norm = cm / np.maximum(cm.sum(axis=1, keepdims=True), 1)
            n = len(labels)
            fig, ax = plt.subplots(figsize=FIG_CONFUSION)
            im = ax.imshow(norm, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
            ax.set_xticks(range(n)); ax.set_yticks(range(n))
            # 38 class names at text width cannot be legible; they are kept
            # because the reader needs to identify a cell, not read the axis.
            tick = 3.2 if n > 24 else 4.5
            ax.set_xticklabels(labels, rotation=90, fontsize=tick)
            ax.set_yticklabels(labels, fontsize=tick)
            ax.set_xlabel("predicted", fontsize=7)
            ax.set_ylabel("true", fontsize=7)
            ax.set_title(f"{rid} — {eval_name} (row-normalised)", fontsize=6)
            cb = fig.colorbar(im, ax=ax, fraction=0.046)
            cb.ax.tick_params(labelsize=5)
            fig.tight_layout()
            _save(fig, f"fig_confusion_{rid}_{eval_name}", raster_dpi=300)
            n_written += 1
    print(f"  wrote {n_written} confusion matrices (pdf, 300 dpi raster)")


def figure_reliability(results: dict) -> None:
    n_written = 0
    for rid, res in results.items():
        blocks = [(n, b) for n, b in res["evaluations"].items() if "probabilistic" in b]
        if not blocks:
            continue
        fig, axes = plt.subplots(1, len(blocks), figsize=(TEXT_WIDTH_IN, 1.6), squeeze=False)
        for ax, (name, block) in zip(axes[0], blocks):
            rel = block["probabilistic"]["reliability"]
            xs, ys = [], []
            for b in rel["bins"]:
                if b["count"]:
                    xs.append(b["avg_confidence"]); ys.append(b["accuracy"])
            ax.plot([0, 1], [0, 1], "k--", lw=0.6)
            ax.plot(xs, ys, marker="o", ms=1.8, lw=0.9)
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.set_xlabel("confidence", fontsize=6)
            ax.tick_params(labelsize=5)
            ax.set_title(
                f"{name}\nECE={block['probabilistic']['expected_calibration_error']:.4f}",
                fontsize=5)
            ax.grid(alpha=0.3, lw=0.4)
        axes[0][0].set_ylabel("accuracy", fontsize=6)
        fig.tight_layout()
        _save(fig, f"fig_reliability_{rid}")
        n_written += 1
    print(f"  wrote {n_written} reliability diagrams (pdf)")


def figure_risk_coverage(results: dict) -> None:
    """Seed-averaged risk-coverage curves, one panel per evaluation setting.

    Thirty-six individual curves cannot be read. Each seed's curve is
    interpolated onto a common coverage grid and averaged, with a shaded band at
    ± one seed standard deviation so the averaging never hides disagreement.
    """
    grid = np.linspace(0.05, 1.0, 96)
    panels = [
        ("PlantVillage in-domain", "pv", "in_domain_test"),
        ("PlantVillage → PlantDoc Core", "pv", "cross_domain_plantdoc_core"),
        ("PlantDoc Core in-domain", "pdc", "in_domain_test"),
    ]
    fig, axes = plt.subplots(1, len(panels), figsize=FIG_ROW3, squeeze=False)
    drew_any = False
    handles: dict[str, object] = {}
    for ax, (disp, prefix, eval_name) in zip(axes[0], panels):
        for model in MODEL_ORDER:
            curves = []
            for _, res in seed_results(results, prefix, model):
                block = res["evaluations"].get(eval_name)
                if not block or "selective_prediction" not in block:
                    continue
                pts = block["selective_prediction"]["points"]
                cov = np.asarray([p["coverage"] for p in pts], dtype=float)
                acc = np.asarray([p["selective_accuracy"] for p in pts], dtype=float)
                order = np.argsort(cov)
                curves.append(np.interp(grid, cov[order], acc[order]))
            if not curves:
                continue
            stack = np.vstack(curves)
            mean = stack.mean(axis=0)
            line, = ax.plot(grid, mean, lw=0.9, color=MODEL_COLOUR[model])
            handles.setdefault(MODEL_DISPLAY[model], line)
            if len(curves) > 1:
                sd = stack.std(axis=0, ddof=1)
                ax.fill_between(grid, mean - sd, mean + sd, alpha=0.18,
                                color=MODEL_COLOUR[model], lw=0)
            drew_any = True
        ax.set_xlabel("coverage", fontsize=6)
        ax.tick_params(labelsize=5)
        ax.set_title(disp, fontsize=6)
        ax.grid(alpha=0.3, lw=0.4)
    if not drew_any:
        plt.close(fig)
        return
    axes[0][0].set_ylabel("selective accuracy", fontsize=6)
    fig.legend(handles.values(), handles.keys(), fontsize=5, ncol=3,
               loc="upper center", bbox_to_anchor=(0.5, 0.06), frameon=False)
    fig.tight_layout()
    _save(fig, "fig_risk_coverage")
    print("  wrote fig_risk_coverage.pdf (+png preview)")


def write_environment(results: dict) -> None:
    if not results:
        return
    any_res = next(iter(results.values()))
    digests = sorted({r.get("experiment_lock_digest") for r in results.values()})
    commits = sorted({r.get("git_commit") for r in results.values() if r.get("git_commit")})
    if len(digests) > 1:
        # Runs trained against different corpora cannot be pooled into one mean.
        raise RuntimeError(
            f"runs disagree on experiment_lock_digest {digests}; "
            "results across different locked corpora must not be aggregated"
        )
    env = {
        "schema": "ica26.experiment_environment/2",
        "hardware": any_res["hardware"],
        "experiment_lock_digest": digests[0],
        # Seeds were run across more than one commit; every commit that produced
        # a pooled result is recorded rather than collapsed to the first.
        "git_commits": commits,
        "seeds_expected": SEEDS,
        "seeds_present": sorted({r["config"]["seed"] for r in results.values()}),
        "runs_present": sorted(results),
        "runs_expected": RUN_IDS,
        "runs_missing": sorted(set(RUN_IDS) - set(results)),
    }
    (REPO / "experiments/ica26/metrics/environment.json").write_text(
        json.dumps(env, indent=2, sort_keys=True) + "\n")
    print("  wrote environment.json")


TABLE_SPECS = [
    ("Table 1", "Dataset statistics", "table1_dataset_statistics"),
    ("Table 1b", "Dataset provenance and leakage control", "table1b_dataset_provenance"),
    ("Table 2", "In-domain performance", "table2_in_domain_performance"),
    ("Table 3", "Cross-domain performance", "table3_cross_domain_performance"),
    ("Table 4", "Efficiency", "table4_efficiency"),
    ("Table 5", "Domain-shift degradation", "table5_domain_shift_degradation"),
    ("Table 6", "Calibration and selective prediction", "table6_calibration"),
    ("Table 7", "Backbone ranking stability across seeds", "table7_ranking_stability"),
    ("Table 7b", "Pairwise ranking margins against seed noise", "table7b_ranking_margins"),
]

# Vector PDF is the submission format; the .png beside three of these is a
# preview only and is never what LaTeX includes.
FIGURE_SPECS = [
    ("Figure 1", "Training curves (loss and validation macro-F1)", "fig_training_curves.pdf"),
    ("Figure 2", "Confusion matrices", "fig_confusion_*.pdf"),
    ("Figure 3", "Reliability diagrams", "fig_reliability_*.pdf"),
    ("Figure 4", "Risk-coverage (confidence-abstention) curves", "fig_risk_coverage.pdf"),
    ("Figure 5", "Backbone macro-F1 mean, seed SD, and individual seeds", "fig_seed_spread.pdf"),
]


def write_placeholders(results: dict) -> None:
    """Regenerate paper/RESULTS_PLACEHOLDERS.md from what actually exists.

    A slot flips from PENDING to a real path only when the file is on disk. No
    number is ever written here by hand.
    """
    paper = REPO / "paper"
    paper.mkdir(parents=True, exist_ok=True)
    missing = sorted(set(RUN_IDS) - set(results))

    lines = [
        "# ICA 2026 — results placeholders",
        "",
        "Generated by `scripts/ica26_build_tables.py`. **Do not edit by hand.**",
        "A slot flips from `PENDING` to a real path only once the artifact exists on",
        "disk; nothing here is ever filled in by estimate.",
        "",
        f"Runs complete: **{len(results)}/{len(RUN_IDS)}**",
        "",
    ]

    lines += ["## Run status", "", "| Run ID | Status |", "|---|---|"]
    for rid in RUN_IDS:
        lines.append(f"| `{rid}` | {'COMPLETE' if rid in results else '**PENDING**'} |")
    lines += [""]

    lines += ["## Tables", "", "| Slot | Content | CSV | LaTeX | Status |", "|---|---|---|---|---|"]
    for slot, desc, name in TABLE_SPECS:
        csv_p = TABLES / f"{name}.csv"
        tex_p = TABLES / f"{name}.tex"
        ok = csv_p.exists() and tex_p.exists()
        lines.append(
            f"| {slot} | {desc} | "
            f"{'`experiments/ica26/tables/' + name + '.csv`' if ok else '—'} | "
            f"{'`experiments/ica26/tables/' + name + '.tex`' if ok else '—'} | "
            f"{'GENERATED' if ok else '**PENDING**'} |"
        )
    lines += [""]

    lines += ["## Figures", "", "| Slot | Content | Path | Status |", "|---|---|---|---|"]
    for slot, desc, pattern in FIGURE_SPECS:
        hits = sorted(FIGURES.glob(pattern))
        lines.append(
            f"| {slot} | {desc} | "
            f"{'`experiments/ica26/figures/' + pattern + '`' if hits else '—'} | "
            f"{f'GENERATED ({len(hits)} file(s))' if hits else '**PENDING**'} |"
        )
    lines += [""]

    if missing:
        lines += [
            "## Not yet available",
            "",
            "These runs have not produced a result file. Any table or figure that depends",
            "on them is incomplete, and no value for them appears anywhere in this",
            "repository:",
            "",
        ] + [f"- `{m}`" for m in missing] + [""]
    else:
        lines += ["All six runs are complete. Every table and figure above is generated "
                  "from real result files.", ""]

    lines += [
        "## Provenance",
        "",
        "Every number in every table is read from `experiments/ica26/metrics/*.json`,",
        "which are written directly by `scripts/ica26_train.py`. To regenerate:",
        "",
        "```bash",
        "python scripts/ica26_build_tables.py",
        "```",
        "",
    ]
    (paper / "RESULTS_PLACEHOLDERS.md").write_text("\n".join(lines))
    print("  wrote paper/RESULTS_PLACEHOLDERS.md")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-all", action="store_true",
                    help="exit non-zero unless all six runs are present")
    args = ap.parse_args()

    results = load_results()
    missing = sorted(set(RUN_IDS) - set(results))
    print(f"results found: {len(results)}/{len(RUN_IDS)}")
    if missing:
        print(f"MISSING (not fabricated, simply absent): {', '.join(missing)}")
    if not results:
        print("no results yet; nothing to build")
        write_placeholders(results)
        return 1 if args.require_all else 0

    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    print("tables:")
    table_dataset_statistics()
    table_in_domain(results)
    table_cross_domain(results)
    table_efficiency(results)
    table_degradation(results)
    table_calibration(results)
    table_ranking_stability(results)
    print("figures:")
    figure_training_curves(results)
    figure_confusion(results)
    figure_reliability(results)
    figure_risk_coverage(results)
    figure_seed_spread(results)
    write_environment(results)
    write_placeholders(results)

    if missing and args.require_all:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
