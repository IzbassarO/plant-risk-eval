#!/usr/bin/env python3
"""Paired significance tests and BCa confidence intervals for the ICA 2026 runs.

    python scripts/ica26_significance.py                 # seed 42 (default)
    python scripts/ica26_significance.py --seed 1337
    python scripts/ica26_significance.py --check         # recompute, compare, write nothing

Three evaluation settings, three backbone pairs each:

    PlantVillage in-domain            pv_*  / predictions_in_domain_test.npz
    PlantDoc Core in-domain           pdc_* / predictions_in_domain_test.npz
    PlantVillage -> PlantDoc Core     pv_*  / predictions_cross_domain.npz

**McNemar's exact test** answers whether two backbones differ on the *same
items*. The unpaired alternative — comparing two accuracies as if they came
from independent samples — throws away the pairing and is the wrong test for
two models scored on one evaluation set. The exact binomial form is used rather
than the chi-square approximation because the discordant counts here are small
enough that the approximation is not safe.

**BCa bootstrap** gives an interval for accuracy and macro-F1 that is
second-order accurate and transformation-respecting, which the percentile
bootstrap is not. Both the bias correction (z0) and the acceleration (a) are
computed; if either is undefined the interval degrades to a plain percentile
interval and says so in the output rather than silently pretending otherwise.

Two facts make all of this exact and cheap. Accuracy and macro-F1 over a fixed
label set depend on the data *only* through the (true, predicted) contingency
table, so:

  * a bootstrap resample of n items is exactly a multinomial draw over that
    table's cells, and
  * leaving one item out has at most ``n_true x n_pred`` distinct outcomes, so
    the jackknife needs that many evaluations rather than n.

The label set is held fixed at the classes present in the *original* evaluation,
matching what ``evaluate_classification`` reports. Letting each replicate pick
its own supported classes would change the statistic's definition between
replicates and make the interval incoherent.

Exit codes: 0 written / verified, 1 a precondition or comparison failed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

RUNS = REPO / "experiments/ica26/runs"
METRICS = REPO / "experiments/ica26/metrics"
TABLES = REPO / "experiments/ica26/tables"
OUT = METRICS / "significance.json"

MODEL_ORDER = ["resnet50", "efficientnet_b0", "mobilenet_v3_small"]
MODEL_DISPLAY = {
    "resnet50": "ResNet-50",
    "efficientnet_b0": "EfficientNet-B0",
    "mobilenet_v3_small": "MobileNetV3-Small",
}

# (display, run prefix, dump file, result.json evaluation key)
SETTINGS = [
    ("PlantVillage in-domain", "pv", "predictions_in_domain_test.npz", "in_domain_test"),
    ("PlantDoc Core in-domain", "pdc", "predictions_in_domain_test.npz", "in_domain_test"),
    ("PlantVillage -> PlantDoc Core", "pv", "predictions_cross_domain.npz",
     "cross_domain_plantdoc_core"),
]

N_BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 20260805      # fixed so the intervals are reproducible
CONF = 0.95
# Recomputation must land on the reported number to within float noise; a real
# disagreement means the dump and the result file describe different runs.
TOLERANCE = 1e-9


# --------------------------------------------------------------------------- #
# statistics over a contingency table
# --------------------------------------------------------------------------- #
def contingency(y_true: np.ndarray, y_pred: np.ndarray,
                labels: list[int], n_pred_space: int) -> np.ndarray:
    """Counts of (true, predicted) over a fixed label set.

    Rows are the evaluated (supported) classes; columns span the full
    prediction space, because a model may predict a class the split cannot
    contain and that prediction is still an error.
    """
    idx = {c: i for i, c in enumerate(labels)}
    cm = np.zeros((len(labels), n_pred_space), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        cm[idx[int(t)], int(p)] += 1
    return cm


def stats_from_cm(cm: np.ndarray, labels: list[int]) -> tuple[float, float]:
    """Accuracy and macro-F1 over the fixed label set, matching sklearn's
    ``zero_division=0`` convention."""
    n = cm.sum()
    if n == 0:
        return float("nan"), float("nan")
    diag = np.array([cm[i, c] for i, c in enumerate(labels)], dtype=np.float64)
    accuracy = diag.sum() / n

    pred_totals = cm.sum(axis=0)                      # over the prediction space
    true_totals = cm.sum(axis=1).astype(np.float64)   # over the evaluated classes
    fp = np.array([pred_totals[c] for c in labels], dtype=np.float64) - diag
    fn = true_totals - diag

    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(diag + fp > 0, diag / (diag + fp), 0.0)
        rec = np.where(diag + fn > 0, diag / (diag + fn), 0.0)
        f1 = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)
    return float(accuracy), float(f1.mean())


def _stats_many(cms: np.ndarray, labels: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised ``stats_from_cm`` over a stack of contingency tables."""
    lab = np.asarray(labels)
    n = cms.sum(axis=(1, 2)).astype(np.float64)
    diag = cms[:, np.arange(len(labels)), lab].astype(np.float64)
    accuracy = diag.sum(axis=1) / np.maximum(n, 1)

    pred_totals = cms.sum(axis=1)[:, lab].astype(np.float64)
    true_totals = cms.sum(axis=2).astype(np.float64)
    fp = pred_totals - diag
    fn = true_totals - diag
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(diag + fp > 0, diag / (diag + fp), 0.0)
        rec = np.where(diag + fn > 0, diag / (diag + fn), 0.0)
        f1 = np.where(prec + rec > 0, 2 * prec * rec / (prec + rec), 0.0)
    return accuracy, f1.mean(axis=1)


# --------------------------------------------------------------------------- #
# BCa bootstrap
# --------------------------------------------------------------------------- #
def bca_interval(cm: np.ndarray, labels: list[int], which: str,
                 rng: np.random.Generator) -> dict:
    """Bias-corrected and accelerated bootstrap interval for one statistic."""
    n = int(cm.sum())
    shape = cm.shape
    flat = cm.reshape(-1).astype(np.float64)
    probs = flat / n

    theta_hat = stats_from_cm(cm, labels)[0 if which == "accuracy" else 1]

    # Bootstrap: resampling n items with replacement is a multinomial draw over
    # the contingency cells, so no per-item resampling is needed.
    draws = rng.multinomial(n, probs, size=N_BOOTSTRAP).reshape(N_BOOTSTRAP, *shape)
    acc_b, f1_b = _stats_many(draws, labels)
    theta_b = acc_b if which == "accuracy" else f1_b
    theta_b = theta_b[np.isfinite(theta_b)]

    # Jackknife: leaving one item out has at most (n_true x n_pred) distinct
    # outcomes, each occurring as many times as that cell is populated.
    occupied = np.flatnonzero(flat > 0)
    jack_vals, jack_w = [], []
    for k in occupied:
        reduced = flat.copy()
        reduced[k] -= 1
        jack_vals.append(
            stats_from_cm(reduced.reshape(shape).astype(np.int64), labels)[
                0 if which == "accuracy" else 1]
        )
        jack_w.append(flat[k])
    jack_vals = np.asarray(jack_vals, dtype=np.float64)
    jack_w = np.asarray(jack_w, dtype=np.float64)

    alpha = (1 - CONF) / 2
    z_lo, z_hi = stats.norm.ppf(alpha), stats.norm.ppf(1 - alpha)

    n_less = float((theta_b < theta_hat).sum() + 0.5 * (theta_b == theta_hat).sum())
    prop = n_less / len(theta_b)
    method = "bca"
    z0 = stats.norm.ppf(prop) if 0 < prop < 1 else np.nan

    jack_mean = float((jack_w * jack_vals).sum() / jack_w.sum())
    d = jack_mean - jack_vals
    num = float((jack_w * d ** 3).sum())
    den = float((jack_w * d ** 2).sum())
    a = num / (6 * den ** 1.5) if den > 0 else np.nan

    if not np.isfinite(z0) or not np.isfinite(a):
        # Degenerate correction (a statistic that never moved, or every replicate
        # on one side of the estimate). Fall back and label the fallback.
        method = "percentile"
        lo_q, hi_q = alpha, 1 - alpha
    else:
        def adjust(z):
            return stats.norm.cdf(z0 + (z0 + z) / (1 - a * (z0 + z)))
        lo_q, hi_q = adjust(z_lo), adjust(z_hi)
        if not (0 < lo_q < hi_q < 1):
            method = "percentile"
            lo_q, hi_q = alpha, 1 - alpha

    lo, hi = np.quantile(theta_b, [lo_q, hi_q])
    return {
        "statistic": which,
        "point_estimate": round(float(theta_hat), 6),
        "ci_lower": round(float(lo), 6),
        "ci_upper": round(float(hi), 6),
        "confidence_level": CONF,
        "method": method,
        "n_bootstrap": int(len(theta_b)),
        "bias_correction_z0": None if not np.isfinite(z0) else round(float(z0), 6),
        "acceleration_a": None if not np.isfinite(a) else round(float(a), 6),
        "bootstrap_std_error": round(float(theta_b.std(ddof=1)), 6),
    }


# --------------------------------------------------------------------------- #
# McNemar
# --------------------------------------------------------------------------- #
def mcnemar_exact(correct_a: np.ndarray, correct_b: np.ndarray) -> dict:
    """Exact (binomial) McNemar test on paired per-item correctness."""
    b = int(np.sum(correct_a & ~correct_b))     # A right, B wrong
    c = int(np.sum(~correct_a & correct_b))     # A wrong, B right
    n_disc = b + c
    if n_disc == 0:
        # The two models are right and wrong on exactly the same items. There is
        # no evidence of a difference and no test to run.
        p = 1.0
    else:
        p = float(stats.binomtest(b, n_disc, 0.5, alternative="two-sided").pvalue)
    return {
        "n_both_correct": int(np.sum(correct_a & correct_b)),
        "n_a_only_correct": b,
        "n_b_only_correct": c,
        "n_both_wrong": int(np.sum(~correct_a & ~correct_b)),
        "n_discordant": n_disc,
        "accuracy_a": round(float(correct_a.mean()), 6),
        "accuracy_b": round(float(correct_b.mean()), 6),
        "accuracy_difference": round(float(correct_a.mean() - correct_b.mean()), 6),
        "p_value": p,
        "test": "mcnemar_exact_binomial",
    }


def holm_bonferroni(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, order preserved, monotone enforced."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * p_values[i])
        running = max(running, val)
        adjusted[i] = running
    return adjusted


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_setting(prefix: str, dump: str, eval_key: str, seed: int) -> dict | None:
    """Load every model's predictions for one evaluation, and check the pairing.

    A paired test is only valid if all models were scored on the same items in
    the same order. The dumps carry no item identifiers, so the strongest
    available check is that the label vectors are identical — which they must be
    if the loaders walked one locked, deterministically ordered frame.
    """
    per_model = {}
    for model in MODEL_ORDER:
        run_dir = RUNS / f"{prefix}_{model}_s{seed}"
        path, result_path = run_dir / dump, run_dir / "result.json"
        if not path.exists() or not result_path.exists():
            continue
        d = np.load(path)
        labels = d["labels"].astype(np.int64)
        if "logits" in d.files:
            scores = d["logits"]
        elif "probs_canonical" in d.files:
            scores = d["probs_canonical"]
        else:
            raise RuntimeError(f"{path}: no logits or probs_canonical array")
        reported = json.loads(result_path.read_text())["evaluations"][eval_key]
        per_model[model] = {
            "y_true": labels,
            "y_pred": scores.argmax(axis=1).astype(np.int64),
            "n_pred_space": int(scores.shape[1]),
            "reported": reported,
        }
    if len(per_model) < 2:
        return None

    ref = per_model[MODEL_ORDER[0] if MODEL_ORDER[0] in per_model else next(iter(per_model))]
    for model, entry in per_model.items():
        if not np.array_equal(entry["y_true"], ref["y_true"]):
            raise RuntimeError(
                f"{prefix}/{model} seed {seed}: evaluation labels differ from the "
                "reference model; the runs are not scored on the same items in the "
                "same order and no paired test over them would be valid"
            )
    return per_model


def verify_against_reported(entry: dict, labels: list[int], model: str,
                            setting: str) -> tuple[float, float]:
    """Recompute the headline metrics and require them to match result.json."""
    cm = contingency(entry["y_true"], entry["y_pred"], labels, entry["n_pred_space"])
    acc, f1 = stats_from_cm(cm, labels)
    rep = entry["reported"]
    for name, got, want in (("accuracy", acc, rep["accuracy"]),
                            ("macro_f1", f1, rep["macro_f1"])):
        if abs(got - want) > TOLERANCE:
            raise RuntimeError(
                f"{setting} / {model}: recomputed {name} {got:.10f} != reported "
                f"{want:.10f}. The prediction dump and the result file disagree; "
                "no statistic derived from the dump can be trusted until that is "
                "resolved."
            )
    return acc, f1


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def analyse(seed: int) -> dict:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    settings_out = []
    all_p: list[tuple[int, int, float]] = []   # (setting index, pair index, p)

    for s_i, (disp, prefix, dump, eval_key) in enumerate(SETTINGS):
        loaded = load_setting(prefix, dump, eval_key, seed)
        if loaded is None:
            print(f"  {disp}: fewer than two models available at seed {seed}; skipped")
            continue

        y_true = next(iter(loaded.values()))["y_true"]
        labels = sorted(set(y_true.tolist()))
        n_pred_space = max(e["n_pred_space"] for e in loaded.values())

        intervals, correctness = [], {}
        for model in MODEL_ORDER:
            if model not in loaded:
                continue
            entry = loaded[model]
            acc, f1 = verify_against_reported(entry, labels, model, disp)
            cm = contingency(entry["y_true"], entry["y_pred"], labels, entry["n_pred_space"])
            correctness[model] = entry["y_pred"] == entry["y_true"]
            intervals.append({
                "model": MODEL_DISPLAY[model],
                "model_key": model,
                **{k: v for k, v in [("accuracy", bca_interval(cm, labels, "accuracy", rng)),
                                     ("macro_f1", bca_interval(cm, labels, "macro_f1", rng))]},
            })
            print(f"  {disp:30s} {MODEL_DISPLAY[model]:20s} "
                  f"acc={acc:.4f} macro-F1={f1:.4f}")

        pairs = []
        present = [m for m in MODEL_ORDER if m in correctness]
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                res = mcnemar_exact(correctness[a], correctness[b])
                res["model_a"] = MODEL_DISPLAY[a]
                res["model_b"] = MODEL_DISPLAY[b]
                all_p.append((s_i, len(pairs), res["p_value"]))
                pairs.append(res)

        settings_out.append({
            "setting": disp,
            "run_prefix": prefix,
            "evaluation": eval_key,
            "n_samples": int(y_true.size),
            "n_evaluated_classes": len(labels),
            "n_prediction_space": n_pred_space,
            "confidence_intervals": intervals,
            "pairwise_mcnemar": pairs,
        })

    # Holm correction across every pairwise test in this analysis: nine tests
    # over three settings, reported both raw and adjusted.
    if all_p:
        adjusted = holm_bonferroni([p for _, _, p in all_p])
        for (s_i, p_i, _), adj in zip(all_p, adjusted):
            target = next(s for s in settings_out
                          if s["setting"] == SETTINGS[s_i][0])
            target["pairwise_mcnemar"][p_i]["p_value_holm"] = float(adj)

    return {
        "schema": "ica26.significance/1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "seed": seed,
        "method": {
            "paired_test": "McNemar exact binomial on per-item correctness",
            "multiplicity": (
                f"Holm-Bonferroni across all {len(all_p)} pairwise tests in this file"
            ),
            "interval": (
                f"BCa bootstrap, {N_BOOTSTRAP} resamples, {int(CONF * 100)}% level, "
                f"rng seed {BOOTSTRAP_SEED}"
            ),
            "label_space": (
                "Fixed to the classes present in the original evaluation, matching "
                "evaluate_classification; held constant across all replicates."
            ),
            "resampling": (
                "Multinomial over the (true, predicted) contingency cells, which is "
                "exactly equivalent to resampling items with replacement for "
                "statistics that depend on the data only through that table."
            ),
        },
        "settings": settings_out,
    }


def write_tables(payload: dict) -> None:
    TABLES.mkdir(parents=True, exist_ok=True)

    ci_rows = []
    for s in payload["settings"]:
        for entry in s["confidence_intervals"]:
            row = {"Setting": s["setting"], "Model": entry["model"], "N": s["n_samples"]}
            for key, disp in (("accuracy", "Accuracy"), ("macro_f1", "Macro-F1")):
                ci = entry[key]
                row[disp] = f"{ci['point_estimate']:.4f}"
                row[f"{disp} 95% CI"] = f"[{ci['ci_lower']:.4f}, {ci['ci_upper']:.4f}]"
            ci_rows.append(row)

    mc_rows = []
    for s in payload["settings"]:
        for pair in s["pairwise_mcnemar"]:
            mc_rows.append({
                "Setting": s["setting"],
                "Comparison": f"{pair['model_a']} vs {pair['model_b']}",
                "Acc. A": f"{pair['accuracy_a']:.4f}",
                "Acc. B": f"{pair['accuracy_b']:.4f}",
                "Diff.": f"{pair['accuracy_difference']:+.4f}",
                "A only": pair["n_a_only_correct"],
                "B only": pair["n_b_only_correct"],
                "Discordant": pair["n_discordant"],
                "p (exact)": _fmt_p(pair["p_value"]),
                "p (Holm)": _fmt_p(pair.get("p_value_holm")),
            })

    _write_table(pd.DataFrame(ci_rows), "table8_confidence_intervals",
                 f"BCa bootstrap {int(CONF * 100)}\\% confidence intervals for accuracy and "
                 f"macro-F1, seed {payload['seed']}, {N_BOOTSTRAP} resamples. Intervals "
                 "describe sampling variability of the fixed evaluation set for one trained "
                 "checkpoint; they are not seed variance, which is reported separately.",
                 "tab:confidence-intervals",
                 compact={"Setting": "Setting", "Model": "Model",
                          "Accuracy 95% CI": "Accuracy 95\\% CI",
                          "Macro-F1 95% CI": "Macro-F1 95\\% CI"},
                 compact_caption=(
                     f"BCa bootstrap {int(CONF * 100)}\\% confidence intervals, seed "
                     f"{payload['seed']}, {N_BOOTSTRAP} resamples. These describe sampling "
                     "variability of a fixed evaluation set for one trained checkpoint, and "
                     "are not seed variance --- which is reported separately and answers a "
                     "different question. Point estimates are in Tables~\\ref{tab:in-domain} "
                     "and~\\ref{tab:cross-domain}."))
    _write_table(pd.DataFrame(mc_rows), "table8b_mcnemar",
                 f"Pairwise McNemar exact tests on per-item correctness, seed "
                 f"{payload['seed']}. `A only' and `B only' are the discordant counts the "
                 "test is computed from. Holm-adjusted p-values control the family-wise error "
                 "rate across all pairwise tests reported here.",
                 "tab:mcnemar",
                 compact={"Setting": "Setting", "Comparison": "Comparison",
                          "Diff.": "$\\Delta$ acc.", "Discordant": "Disc.",
                          "p (exact)": "$p$", "p (Holm)": "$p$ (Holm)"},
                 compact_caption=(
                     f"Pairwise McNemar exact tests on per-item correctness, seed "
                     f"{payload['seed']}. Two models scored on one evaluation set are not "
                     "independent samples, so the paired test is the correct instrument. "
                     "`Disc.' is the number of items the two models disagree on, which is "
                     "what the test is computed from. Holm adjustment controls the "
                     "family-wise error rate across all nine tests."))


def _fmt_p(p) -> str:
    if p is None:
        return "—"
    if p < 1e-4:
        return "<0.0001"
    return f"{p:.4f}"


# Corpus names repeat down the Setting column and are its widest cell.
COMPACT_ABBREV = {
    "PlantVillage -> PlantDoc Core": "PV $\\rightarrow$ PDC",
    "PlantVillage in-domain": "PV in-domain",
    "PlantDoc Core in-domain": "PDC in-domain",
}


def _write_table(df: pd.DataFrame, name: str, caption: str, label: str,
                 compact: dict[str, str] | None = None,
                 compact_caption: str | None = None) -> None:
    """Full table as evidence, plus a narrow variant that fits the text block.

    At the LNCS text width of 122 mm these tables overflow badly at full width.
    Shrinking one to fit would make its text smaller than its own caption, so
    the paper takes a column subset instead and the full table stays available
    as supplementary material.
    """
    if df.empty:
        return
    df.to_csv(TABLES / f"{name}.csv", index=False)
    _emit(df, name, caption, label)
    if compact:
        present = {src: dst for src, dst in compact.items() if src in df.columns}
        narrow = df[list(present)].rename(columns=present).replace(COMPACT_ABBREV)
        _emit(narrow, f"{name}_compact", compact_caption or caption,
              f"{label}-compact", small=True)


def _emit(df: pd.DataFrame, name: str, caption: str, label: str, small: bool = False) -> None:
    latex = df.to_latex(index=False, escape=True, caption=caption, label=label, position="htbp")
    for raw, tex in (("±", r"$\pm$"), ("→", r"$\rightarrow$"), ("->", r"$\rightarrow$")):
        latex = latex.replace(raw, tex)
    if small:
        latex = latex.replace(r"\begin{tabular}", "\\footnotesize\n\\centering\n\\begin{tabular}")
    (TABLES / f"{name}.tex").write_text(latex)
    print(f"  wrote {name}.tex  ({len(df)} rows{', compact' if small else ''})")


SEEDS = [42, 1337, 2026]
ALL_SEEDS_OUT = METRICS / "significance_all_seeds.json"


def available_seeds() -> list[int]:
    """Seeds whose full six-run matrix has produced dumps.

    A partially finished seed is excluded rather than analysed. Including one
    would make a comparison read "significant in 1 of 2 seeds" when the second
    seed had simply not trained that backbone yet -- a missing run reported as
    a negative result.
    """
    out = []
    for seed in SEEDS:
        complete = all(
            (RUNS / f"{prefix}_{model}_s{seed}" / "predictions_in_domain_test.npz").exists()
            for prefix in ("pv", "pdc") for model in MODEL_ORDER
        ) and all(
            (RUNS / f"pv_{model}_s{seed}" / "predictions_cross_domain.npz").exists()
            for model in MODEL_ORDER
        )
        if complete:
            out.append(seed)
    return out


def cross_seed_consistency(per_seed: dict[int, dict]) -> list[dict]:
    """Does each pairwise verdict hold in every seed, or only in one?

    A significance result computed on a single training run is a statement about
    that run. If a reviewer asks whether the conclusion is an artefact of the
    seed, the only honest answer is to recompute it per seed and report how
    often it holds -- including when it does not.
    """
    rows = []
    settings = [s[0] for s in SETTINGS]
    for setting in settings:
        pairs: dict[str, list[tuple[int, dict]]] = {}
        for seed, payload in sorted(per_seed.items()):
            block = next((s for s in payload["settings"] if s["setting"] == setting), None)
            if not block:
                continue
            for pair in block["pairwise_mcnemar"]:
                key = f"{pair['model_a']} vs {pair['model_b']}"
                pairs.setdefault(key, []).append((seed, pair))
        for key, entries in pairs.items():
            sig = [s for s, p in entries if p.get("p_value_holm", 1.0) < 0.05]
            diffs = [p["accuracy_difference"] for _, p in entries]
            n_pos = sum(1 for d in diffs if d > 0)
            verdict = ("significant in all seeds" if len(sig) == len(entries)
                       else "significant in no seed" if not sig
                       else f"significant in {len(sig)} of {len(entries)} seeds")
            rows.append({
                "setting": setting,
                "comparison": key,
                "n_seeds": len(entries),
                "seeds": [s for s, _ in entries],
                "n_significant_holm": len(sig),
                "significant_seeds": sig,
                "sign_consistent": max(n_pos, len(diffs) - n_pos) == len(diffs),
                "mean_accuracy_difference": round(float(np.mean(diffs)), 6),
                "per_seed_p_holm": {str(s): p.get("p_value_holm") for s, p in entries},
                "verdict": verdict,
            })
    return rows


def write_consistency_table(rows: list[dict]) -> None:
    if not rows:
        return
    df = pd.DataFrame([{
        "Setting": r["setting"],
        "Comparison": r["comparison"],
        "Seeds": r["n_seeds"],
        "Significant (Holm)": f"{r['n_significant_holm']}/{r['n_seeds']}",
        "Sign consistent": "yes" if r["sign_consistent"] else "no",
        "Mean acc. diff.": f"{r['mean_accuracy_difference']:+.4f}",
    } for r in rows])
    _write_table(df, "table9_significance_across_seeds",
                 "Stability of each pairwise verdict across independent training seeds. "
                 "Each seed's McNemar test is computed on that seed's own checkpoints and "
                 "Holm-adjusted within that seed. A comparison significant in every seed is "
                 "a conclusion about the architectures; one significant in a single seed is "
                 "a statement about that run.",
                 "tab:significance-across-seeds",
                 compact={"Setting": "Setting", "Comparison": "Comparison",
                          "Significant (Holm)": "Sig. (Holm)",
                          "Sign consistent": "Sign", "Mean acc. diff.": "$\\Delta$ acc."},
                 compact_caption=(
                     "Stability of each pairwise verdict across independent training seeds. "
                     "Each seed's McNemar test uses that seed's own checkpoints, Holm-adjusted "
                     "within the seed. A comparison significant in every seed is a conclusion "
                     "about the architectures; one significant in a single seed is a statement "
                     "about that run."))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42,
                    help="which seed's prediction dumps to analyse (default 42)")
    ap.add_argument("--all-seeds", action="store_true",
                    help="analyse every seed with dumps and report cross-seed consistency")
    ap.add_argument("--check", action="store_true",
                    help="recompute and compare against the existing file, write nothing")
    args = ap.parse_args()

    if args.all_seeds:
        seeds = available_seeds()
        if not seeds:
            print("no seed has prediction dumps", file=sys.stderr)
            return 1
        per_seed = {}
        for seed in seeds:
            print(f"analysing seed {seed}")
            per_seed[seed] = analyse(seed)
        rows = cross_seed_consistency(per_seed)
        payload = {
            "schema": "ica26.significance_across_seeds/1",
            "created_at_utc": dt.datetime.now(dt.timezone.utc)
                                .replace(microsecond=0).isoformat(),
            "seeds": seeds,
            "note": (
                "Each seed is analysed independently and Holm-adjusted within that "
                "seed. p-values are not pooled across seeds: three runs is far too "
                "few to justify a meta-analytic combination, and the useful question "
                "is whether a verdict is stable, not what its combined p-value is."
            ),
            "consistency": rows,
            "per_seed": per_seed,
        }
        ALL_SEEDS_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        write_consistency_table(rows)
        print(f"  wrote {ALL_SEEDS_OUT.relative_to(REPO)}")
        stable = sum(1 for r in rows if r["n_significant_holm"] == r["n_seeds"])
        never = sum(1 for r in rows if r["n_significant_holm"] == 0)
        print(f"comparisons        : {len(rows)} across {len(seeds)} seed(s)")
        print(f"significant always : {stable}")
        print(f"significant never  : {never}")
        print(f"seed-dependent     : {len(rows) - stable - never}")
        return 0

    print(f"analysing seed {args.seed}")
    payload = analyse(args.seed)
    if not payload["settings"]:
        print("no evaluation had two or more models available", file=sys.stderr)
        return 1

    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT}", file=sys.stderr)
            return 1
        existing = json.loads(OUT.read_text())
        a = {k: v for k, v in existing.items() if k != "created_at_utc"}
        b = {k: v for k, v in payload.items() if k != "created_at_utc"}
        if a != b:
            print("CHECK FAILED: recomputed significance differs from the committed file",
                  file=sys.stderr)
            return 1
        print("check OK: recomputed significance is identical to the committed file")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_tables(payload)
    print(f"  wrote {OUT.relative_to(REPO)}")

    n_tests = sum(len(s["pairwise_mcnemar"]) for s in payload["settings"])
    n_sig = sum(1 for s in payload["settings"] for p in s["pairwise_mcnemar"]
                if p.get("p_value_holm", 1.0) < 0.05)
    print(f"pairwise tests    : {n_tests}")
    print(f"significant (Holm): {n_sig} at the 0.05 level")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
