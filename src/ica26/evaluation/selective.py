"""Selective prediction / abstention: coverage-conditioned metrics.

Given per-sample confidences, a threshold tau retains samples with
``confidence >= tau`` (coverage) and abstains on the rest. We report how
disease accuracy, action accuracy, and harm behave as coverage shrinks.

Thresholds are emitted in a deterministic, ascending order so that repeated
runs and unit tests are stable.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd


def _as_float_array(x) -> np.ndarray:
    return np.asarray(list(x), dtype=float)


def default_thresholds(confidences: Sequence[float]) -> np.ndarray:
    """Deterministic ascending thresholds: unique confidences plus 0 and max."""
    conf = _as_float_array(confidences)
    if conf.size == 0:
        return np.array([0.0])
    grid = np.concatenate([[0.0], conf, [float(conf.max())]])
    return np.unique(grid)  # np.unique returns sorted ascending -> deterministic


def coverage_at(confidences: Sequence[float], tau: float) -> float:
    conf = _as_float_array(confidences)
    if conf.size == 0:
        return 0.0
    return float(np.mean(conf >= tau))


def selective_mean(
    confidences: Sequence[float],
    values: Sequence[float],
    tau: float,
) -> float:
    """Mean of ``values`` over samples with confidence >= tau (NaN if none)."""
    conf = _as_float_array(confidences)
    vals = _as_float_array(values)
    mask = conf >= tau
    return float(vals[mask].mean()) if mask.any() else float("nan")


def risk_coverage_table(
    confidences: Sequence[float],
    correct: Optional[Sequence[bool]] = None,
    harm: Optional[Sequence[float]] = None,
    thresholds: Optional[Sequence[float]] = None,
    metric_name: str = "selective_accuracy",
) -> pd.DataFrame:
    """Risk-coverage table.

    Columns: threshold, coverage, n_covered, and (if provided)
    ``metric_name`` (from ``correct``) and/or ``selective_harm`` (from ``harm``).
    Rows are ordered by ascending threshold (=> descending coverage).
    """
    conf = _as_float_array(confidences)
    n = conf.size
    taus = default_thresholds(conf) if thresholds is None else np.sort(np.unique(_as_float_array(thresholds)))

    correct_arr = None if correct is None else np.asarray(list(correct), dtype=bool)
    harm_arr = None if harm is None else _as_float_array(harm)

    rows = []
    for t in taus:
        mask = conf >= t
        n_cov = int(mask.sum())
        row = {
            "threshold": float(t),
            "coverage": (n_cov / n) if n else 0.0,
            "n_covered": n_cov,
            "n_deferred": int(n - n_cov),   # explicitly report abstentions
        }
        if correct_arr is not None:
            row[metric_name] = float(correct_arr[mask].mean()) if n_cov else float("nan")
        if harm_arr is not None:
            row["selective_harm"] = float(harm_arr[mask].mean()) if n_cov else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def selective_disease_accuracy(
    confidences: Sequence[float],
    y_true: Sequence[str],
    y_pred: Sequence[str],
    thresholds: Optional[Sequence[float]] = None,
) -> pd.DataFrame:
    correct = [str(a) == str(b) for a, b in zip(y_true, y_pred)]
    return risk_coverage_table(confidences, correct=correct, thresholds=thresholds,
                               metric_name="selective_disease_accuracy")


def selective_action_accuracy(
    confidences: Sequence[float],
    true_actions: Sequence[Optional[str]],
    pred_actions: Sequence[Optional[str]],
    thresholds: Optional[Sequence[float]] = None,
    unmapped_pred_correct: bool = False,
) -> dict:
    """Selective action accuracy with **preserved accounting**.

    Samples whose TRUE action is unmapped cannot be scored and are excluded from
    the risk-coverage curve, but their count is **not lost** — it is returned so
    the original total is always recoverable. Unmapped predictions count as
    incorrect unless ``unmapped_pred_correct``.

    Returns a dict: ``risk_coverage`` (DataFrame), ``n_total`` (original),
    ``n_scored``, ``n_unmapped_true_excluded``.
    """
    conf, correct = [], []
    n_total = 0
    n_unmapped_true = 0
    for c, t, p in zip(confidences, true_actions, pred_actions):
        n_total += 1
        if t is None:
            n_unmapped_true += 1
            continue
        conf.append(c)
        correct.append(bool(unmapped_pred_correct) if p is None else (t == p))
    table = risk_coverage_table(conf, correct=correct, thresholds=thresholds,
                                metric_name="selective_action_accuracy")
    return {
        "risk_coverage": table,
        "n_total": n_total,
        "n_scored": len(conf),
        "n_unmapped_true_excluded": n_unmapped_true,
    }


def selective_harm(
    confidences: Sequence[float],
    per_sample_harm: Sequence[float],
    thresholds: Optional[Sequence[float]] = None,
) -> pd.DataFrame:
    return risk_coverage_table(confidences, harm=per_sample_harm, thresholds=thresholds)


def operating_point(
    table: pd.DataFrame,
    metric_col: str,
    min_metric: float,
) -> Optional[dict]:
    """Highest-coverage row whose ``metric_col`` >= ``min_metric`` (or None)."""
    if metric_col not in table.columns:
        return None
    ok = table[table[metric_col] >= min_metric]
    if not len(ok):
        return None
    best = ok.sort_values("coverage", ascending=False).iloc[0]
    return best.to_dict()
