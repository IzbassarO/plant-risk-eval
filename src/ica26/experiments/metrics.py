"""Classification, probabilistic, and calibration metrics.

Everything a table or figure reports is computed here from stored predictions,
so a table can always be regenerated from a run's ``predictions.npz`` without
re-running the model.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)


def _as_int_array(x) -> np.ndarray:
    return np.asarray(x, dtype=np.int64).reshape(-1)


def classification_metrics(
    y_true, y_pred, class_names: Sequence[str], labels: Optional[Sequence[int]] = None
) -> dict:
    """Headline and per-class classification metrics.

    ``labels`` fixes the label space explicitly so that a class with zero
    support in this evaluation still appears in the per-class table and still
    counts toward macro averages, rather than silently vanishing.
    """
    y_true = _as_int_array(y_true)
    y_pred = _as_int_array(y_pred)
    if labels is None:
        labels = list(range(len(class_names)))
    labels = list(labels)

    prec, rec, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=labels, average=None, zero_division=0
    )
    cm = confusion_matrix(y_true, y_pred, labels=labels)

    per_class = [
        {
            "class_index": int(idx),
            "class_name": str(class_names[i]),
            "precision": float(prec[i]),
            "recall": float(rec[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, idx in enumerate(labels)
    ]

    return {
        "n_samples": int(y_true.size),
        "n_classes": len(labels),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, labels=labels, average="weighted", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_precision": float(precision_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        "per_class": per_class,
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": [str(class_names[i]) for i in range(len(labels))],
    }


def evaluate_classification(y_true, y_pred, class_names: Sequence[str]) -> dict:
    """Classification metrics reported over the *supported* label space.

    Macro averages run over the classes that actually occur in ``y_true``. A
    class the evaluation split cannot exercise (PlantDoc Core's arthropod-pest
    class has zero test images) would otherwise contribute a hard 0.0 to every
    macro average and silently depress the headline number, which would say more
    about the split than about the model.

    Both views are returned: ``metrics`` over the supported space, and
    ``full_label_space`` over all declared classes, so nothing is hidden.
    """
    y_true = _as_int_array(y_true)
    y_pred = _as_int_array(y_pred)
    all_labels = list(range(len(class_names)))
    supported = sorted(set(y_true.tolist()))
    zero_support = [i for i in all_labels if i not in set(supported)]

    primary = classification_metrics(y_true, y_pred, class_names, labels=supported)
    primary["evaluated_label_space"] = "supported_classes"
    primary["n_declared_classes"] = len(all_labels)
    primary["n_supported_classes"] = len(supported)
    primary["zero_support_classes"] = [
        {"class_index": int(i), "class_name": str(class_names[i])} for i in zero_support
    ]
    # Predictions that land on a class the split cannot contain are still errors
    # against the true class; this counts them explicitly rather than by omission.
    primary["predictions_into_zero_support_classes"] = int(
        np.isin(y_pred, np.asarray(zero_support, dtype=np.int64)).sum()
    ) if zero_support else 0

    primary["full_label_space"] = classification_metrics(
        y_true, y_pred, class_names, labels=all_labels
    )
    return primary


def negative_log_likelihood(y_true, probs, eps: float = 1e-12) -> float:
    y_true = _as_int_array(y_true)
    probs = np.asarray(probs, dtype=np.float64)
    p = np.clip(probs[np.arange(y_true.size), y_true], eps, 1.0)
    return float(-np.mean(np.log(p)))


def brier_score(y_true, probs) -> float:
    """Multi-class Brier score: mean squared error against the one-hot target."""
    y_true = _as_int_array(y_true)
    probs = np.asarray(probs, dtype=np.float64)
    onehot = np.zeros_like(probs)
    onehot[np.arange(y_true.size), y_true] = 1.0
    return float(np.mean(np.sum((probs - onehot) ** 2, axis=1)))


def expected_calibration_error(y_true, probs, n_bins: int = 15) -> dict:
    """Top-label ECE with equal-width confidence bins.

    Also returns the per-bin table the reliability diagram is drawn from, so the
    figure and the scalar can never disagree.
    """
    y_true = _as_int_array(y_true)
    probs = np.asarray(probs, dtype=np.float64)
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    correct = (pred == y_true).astype(np.float64)

    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    mce = 0.0
    bins = []
    n = y_true.size
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (conf > lo) & (conf <= hi) if i > 0 else (conf >= lo) & (conf <= hi)
        count = int(sel.sum())
        if count == 0:
            bins.append(
                {"bin_lower": float(lo), "bin_upper": float(hi), "count": 0,
                 "avg_confidence": None, "accuracy": None}
            )
            continue
        avg_conf = float(conf[sel].mean())
        acc = float(correct[sel].mean())
        gap = abs(avg_conf - acc)
        ece += (count / n) * gap
        mce = max(mce, gap)
        bins.append(
            {"bin_lower": float(lo), "bin_upper": float(hi), "count": count,
             "avg_confidence": avg_conf, "accuracy": acc}
        )

    return {
        "expected_calibration_error": float(ece),
        "maximum_calibration_error": float(mce),
        "n_bins": n_bins,
        "bins": bins,
    }


def probabilistic_metrics(y_true, probs, n_bins: int = 15) -> dict:
    cal = expected_calibration_error(y_true, probs, n_bins=n_bins)
    return {
        "negative_log_likelihood": negative_log_likelihood(y_true, probs),
        "brier_score": brier_score(y_true, probs),
        "expected_calibration_error": cal["expected_calibration_error"],
        "maximum_calibration_error": cal["maximum_calibration_error"],
        "reliability": cal,
    }


def confidence_abstention_curve(y_true, probs, n_points: int = 21) -> dict:
    """Selective prediction: accuracy against coverage as a confidence threshold
    sweeps from accept-everything to accept-only-the-most-confident."""
    y_true = _as_int_array(y_true)
    probs = np.asarray(probs, dtype=np.float64)
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y_true).astype(np.float64)

    order = np.argsort(-conf)
    conf_sorted = conf[order]
    correct_sorted = correct[order]
    n = y_true.size

    points = []
    for frac in np.linspace(1.0, 0.05, n_points):
        k = max(1, int(round(frac * n)))
        points.append(
            {
                "coverage": float(k / n),
                "n_accepted": int(k),
                "threshold": float(conf_sorted[k - 1]),
                "selective_accuracy": float(correct_sorted[:k].mean()),
                "risk": float(1.0 - correct_sorted[:k].mean()),
            }
        )
    # Area under the risk-coverage curve: lower is a better confidence ranking.
    cov = np.array([p["coverage"] for p in points])[::-1]
    risk = np.array([p["risk"] for p in points])[::-1]
    aurc = float(np.trapezoid(risk, cov) / (cov[-1] - cov[0])) if cov[-1] > cov[0] else float("nan")
    return {"points": points, "area_under_risk_coverage": aurc}


def efficiency_metrics(
    total_parameters: int,
    trainable_parameters: int,
    train_seconds: float,
    epochs_run: int,
    inference: dict,
    peak_memory_bytes: Optional[int],
) -> dict:
    out = {
        "total_parameters": int(total_parameters),
        "trainable_parameters": int(trainable_parameters),
        "training_time_seconds": float(train_seconds),
        "epochs_run": int(epochs_run),
        "seconds_per_epoch": float(train_seconds / epochs_run) if epochs_run else None,
        "peak_memory_bytes": int(peak_memory_bytes) if peak_memory_bytes else None,
        "peak_memory_mb": round(peak_memory_bytes / 1024**2, 1) if peak_memory_bytes else None,
    }
    out.update(inference)
    return out
