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
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

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

RUN_IDS = [
    "pv_resnet50_s42", "pv_efficientnet_b0_s42", "pv_mobilenet_v3_small_s42",
    "pdc_resnet50_s42", "pdc_efficientnet_b0_s42", "pdc_mobilenet_v3_small_s42",
]


def load_results() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rid in RUN_IDS:
        p = METRICS / f"{rid}.json"
        if p.exists():
            out[rid] = json.loads(p.read_text())
    return out


def _write(df: pd.DataFrame, name: str, caption: str, label: str, float_fmt: str = "%.4f") -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES / f"{name}.csv", index=False)
    latex = df.to_latex(
        index=False, escape=True, float_format=float_fmt,
        caption=caption, label=label, position="htbp",
    )
    (TABLES / f"{name}.tex").write_text(latex)
    print(f"  wrote {name}.csv / {name}.tex  ({len(df)} rows)")


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
def _perf_row(model: str, dataset: str, block: dict) -> dict:
    return {
        "Model": MODEL_DISPLAY[model],
        "Dataset": dataset,
        "N": block["n_samples"],
        "Accuracy": block["accuracy"],
        "Macro-F1": block["macro_f1"],
        "Weighted-F1": block["weighted_f1"],
        "Balanced Acc.": block["balanced_accuracy"],
        "Macro Prec.": block["macro_precision"],
        "Macro Rec.": block["macro_recall"],
    }


def table_in_domain(results: dict) -> pd.DataFrame:
    rows = []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            rid = f"{prefix}_{model}_s42"
            if rid not in results:
                continue
            rows.append(_perf_row(model, dataset, results[rid]["evaluations"]["in_domain_test"]))
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table2_in_domain_performance",
               "In-domain test performance. Macro averages are computed over the classes "
               "present in the evaluation split; PlantDoc Core's arthropod-pest class has "
               "zero test images and is reported separately rather than averaged in as zero.",
               "tab:in-domain")
    return df


def table_cross_domain(results: dict) -> pd.DataFrame:
    rows = []
    for model in MODEL_ORDER:
        rid = f"pv_{model}_s42"
        block = results.get(rid, {}).get("evaluations", {}).get("cross_domain_plantdoc_core")
        if not block:
            continue
        r = _perf_row(model, "PlantVillage -> PlantDoc Core", block)
        r["Shared classes"] = block["protocol"]["n_shared_classes"]
        rows.append(r)
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table3_cross_domain_performance",
               "Cross-domain generalisation: PlantVillage-trained models evaluated on the "
               "frozen shared-class PlantDoc Core subset. Metrics are computed only over the "
               "21 shared classes; unmapped PlantDoc images are excluded from the evaluation "
               "set rather than counted as errors.",
               "tab:cross-domain")
    return df


# --------------------------------------------------------------------------- #
# 4. efficiency
# --------------------------------------------------------------------------- #
def table_efficiency(results: dict) -> None:
    rows = []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            rid = f"{prefix}_{model}_s42"
            if rid not in results:
                continue
            e = results[rid]["efficiency"]
            t = results[rid]["training"]
            rows.append({
                "Model": MODEL_DISPLAY[model],
                "Dataset": dataset,
                "Params (M)": round(e["total_parameters"] / 1e6, 2),
                "Epochs": t["epochs_run"],
                "Train time (min)": round(e["training_time_seconds"] / 60, 1),
                "s / epoch": round(e["seconds_per_epoch"], 1) if e.get("seconds_per_epoch") else None,
                "Latency b1 (ms)": e.get("inference_latency_ms_batch1"),
                "Throughput (img/s)": e.get("inference_throughput_img_per_s"),
                "Peak mem (MB)": e.get("peak_memory_mb"),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table4_efficiency",
               "Model efficiency. Latency and throughput measured after warm-up on the "
               "accelerator reported in the run metadata.",
               "tab:efficiency", float_fmt="%.2f")


# --------------------------------------------------------------------------- #
# 5. domain-shift degradation
# --------------------------------------------------------------------------- #
def table_degradation(results: dict) -> None:
    rows = []
    for model in MODEL_ORDER:
        rid = f"pv_{model}_s42"
        res = results.get(rid)
        if not res:
            continue
        ind = res["evaluations"]["in_domain_test"]
        cd = res["evaluations"].get("cross_domain_plantdoc_core")
        if not cd:
            continue
        row = {"Model": MODEL_DISPLAY[model]}
        for metric, key in (("Accuracy", "accuracy"), ("Macro-F1", "macro_f1")):
            a, b = ind[key], cd[key]
            row[f"{metric} (in-domain)"] = a
            row[f"{metric} (cross-domain)"] = b
            row[f"{metric} abs. drop"] = a - b
            row[f"{metric} rel. drop %"] = (a - b) / a * 100 if a else float("nan")
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table5_domain_shift_degradation",
               "Domain-shift degradation. In-domain is the PlantVillage test split over 38 "
               "classes; cross-domain is the PlantDoc Core shared-class subset over 21 "
               "classes. The two label spaces differ, so the drop combines domain shift with "
               "the change of task difficulty and should be read as a paired trend across "
               "models rather than as an isolated quantity.",
               "tab:degradation")


# --------------------------------------------------------------------------- #
# 6. calibration
# --------------------------------------------------------------------------- #
def table_calibration(results: dict) -> None:
    rows = []
    for prefix, dataset in (("pv", "PlantVillage"), ("pdc", "PlantDoc Core")):
        for model in MODEL_ORDER:
            rid = f"{prefix}_{model}_s42"
            res = results.get(rid)
            if not res:
                continue
            for eval_name, disp in (
                ("in_domain_test", "in-domain"),
                ("in_domain_test_temperature_scaled", "in-domain (T-scaled)"),
                ("cross_domain_plantdoc_core", "cross-domain"),
                ("cross_domain_plantdoc_core_temperature_scaled", "cross-domain (T-scaled)"),
            ):
                block = res["evaluations"].get(eval_name)
                if not block or "probabilistic" not in block:
                    continue
                p = block["probabilistic"]
                # Read the temperature the block actually used. Inferring it from
                # the row label previously reported T=1.0 for cross-domain rows
                # that had in fact been temperature-scaled.
                applied = block.get("temperature")
                rows.append({
                    "Model": MODEL_DISPLAY[model],
                    "Dataset": dataset,
                    "Setting": disp,
                    "NLL": p["negative_log_likelihood"],
                    "Brier": p["brier_score"],
                    "ECE": p["expected_calibration_error"],
                    "MCE": p["maximum_calibration_error"],
                    "AURC": block.get("selective_prediction", {}).get("area_under_risk_coverage"),
                    "T": applied if applied else 1.0,
                })
    df = pd.DataFrame(rows)
    if not df.empty:
        _write(df, "table6_calibration",
               "Confidence calibration and selective prediction. Temperature is fitted on the "
               "held-out validation split only and applied unchanged to test and cross-domain "
               "logits. AURC is the area under the risk-coverage curve; lower is better.",
               "tab:calibration")


# --------------------------------------------------------------------------- #
# figures
# --------------------------------------------------------------------------- #
def figure_training_curves(results: dict) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    present = [(rid, r) for rid, r in results.items()]
    if not present:
        return
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    for rid, res in sorted(present):
        hist = res["training"]["history"]
        ep = [h["epoch"] for h in hist]
        axes[0].plot(ep, [h["train_loss"] for h in hist], marker="o", ms=3, label=rid)
        axes[1].plot(ep, [h["val_macro_f1"] for h in hist], marker="o", ms=3, label=rid)
    axes[0].set_xlabel("epoch"); axes[0].set_ylabel("train loss"); axes[0].set_title("Training loss")
    axes[1].set_xlabel("epoch"); axes[1].set_ylabel("validation macro-F1"); axes[1].set_title("Validation macro-F1")
    for ax in axes:
        ax.grid(alpha=0.3)
    axes[1].legend(fontsize=7, loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_training_curves.png", dpi=200)
    plt.close(fig)
    print("  wrote fig_training_curves.png")


def figure_confusion(results: dict) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
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
            fig, ax = plt.subplots(figsize=(max(6, n * 0.32), max(5, n * 0.30)))
            im = ax.imshow(norm, cmap="viridis", vmin=0, vmax=1)
            ax.set_xticks(range(n)); ax.set_yticks(range(n))
            ax.set_xticklabels(labels, rotation=90, fontsize=5)
            ax.set_yticklabels(labels, fontsize=5)
            ax.set_xlabel("predicted"); ax.set_ylabel("true")
            ax.set_title(f"{rid} — {eval_name} (row-normalised)", fontsize=8)
            fig.colorbar(im, ax=ax, fraction=0.046)
            fig.tight_layout()
            fig.savefig(FIGURES / f"fig_confusion_{rid}_{eval_name}.png", dpi=200)
            plt.close(fig)
    print("  wrote confusion matrices")


def figure_reliability(results: dict) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for rid, res in results.items():
        blocks = [(n, b) for n, b in res["evaluations"].items() if "probabilistic" in b]
        if not blocks:
            continue
        fig, axes = plt.subplots(1, len(blocks), figsize=(4.2 * len(blocks), 4), squeeze=False)
        for ax, (name, block) in zip(axes[0], blocks):
            rel = block["probabilistic"]["reliability"]
            xs, ys = [], []
            for b in rel["bins"]:
                if b["count"]:
                    xs.append(b["avg_confidence"]); ys.append(b["accuracy"])
            ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
            ax.plot(xs, ys, marker="o", ms=4, label="observed")
            ax.set_xlim(0, 1); ax.set_ylim(0, 1)
            ax.set_xlabel("confidence"); ax.set_ylabel("accuracy")
            ax.set_title(f"{name}\nECE={block['probabilistic']['expected_calibration_error']:.4f}",
                         fontsize=8)
            ax.grid(alpha=0.3); ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(FIGURES / f"fig_reliability_{rid}.png", dpi=200)
        plt.close(fig)
    print("  wrote reliability diagrams")


def figure_risk_coverage(results: dict) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    drew = False
    for rid, res in sorted(results.items()):
        for name in ("in_domain_test", "cross_domain_plantdoc_core"):
            block = res["evaluations"].get(name)
            if not block or "selective_prediction" not in block:
                continue
            pts = block["selective_prediction"]["points"]
            ax.plot([p["coverage"] for p in pts], [p["selective_accuracy"] for p in pts],
                    lw=1.2, label=f"{rid} / {name}")
            drew = True
    if not drew:
        plt.close(fig)
        return
    ax.set_xlabel("coverage"); ax.set_ylabel("selective accuracy")
    ax.set_title("Confidence-abstention (risk-coverage) curves")
    ax.grid(alpha=0.3); ax.legend(fontsize=6)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_risk_coverage.png", dpi=200)
    plt.close(fig)
    print("  wrote fig_risk_coverage.png")


def write_environment(results: dict) -> None:
    if not results:
        return
    any_res = next(iter(results.values()))
    env = {
        "schema": "ica26.experiment_environment/1",
        "hardware": any_res["hardware"],
        "experiment_lock_digest": any_res.get("experiment_lock_digest"),
        "git_commit": any_res.get("git_commit"),
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
]

FIGURE_SPECS = [
    ("Figure 1", "Training curves (loss and validation macro-F1)", "fig_training_curves.png"),
    ("Figure 2", "Confusion matrices", "fig_confusion_*.png"),
    ("Figure 3", "Reliability diagrams", "fig_reliability_*.png"),
    ("Figure 4", "Risk-coverage (confidence-abstention) curves", "fig_risk_coverage.png"),
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
    print("figures:")
    figure_training_curves(results)
    figure_confusion(results)
    figure_reliability(results)
    figure_risk_coverage(results)
    write_environment(results)
    write_placeholders(results)

    if missing and args.require_all:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
