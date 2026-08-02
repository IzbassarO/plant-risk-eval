"""Action-level metrics.

Disease predictions are projected to action classes through an APPROVED
disease-to-action mapping (see ica26.mapping). Unmapped/unapproved labels are
handled explicitly and counted -- never silently dropped.
"""
from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import pandas as pd

from ..schemas import ACTION_CLASSES

Label = str
Lookup = dict  # {(dataset, dataset_class) -> action_class}

UNMAPPED = "__unmapped__"


def _check_lengths(y_true: Sequence, y_pred: Sequence) -> None:
    if len(y_true) != len(y_pred):
        raise ValueError(f"y_true and y_pred length mismatch: {len(y_true)} != {len(y_pred)}")


def disease_top1_accuracy(y_true: Sequence[Label], y_pred: Sequence[Label]) -> float:
    _check_lengths(y_true, y_pred)
    yt = np.asarray(list(y_true), dtype=object)
    yp = np.asarray(list(y_pred), dtype=object)
    if len(yt) == 0:
        return float("nan")
    return float(np.mean(yt == yp))


def project_labels(labels: Sequence[Label], dataset: str, lookup: Lookup) -> list[Optional[str]]:
    """Map each disease label to an action via lookup; None if unmapped."""
    return [lookup.get((dataset, str(l))) for l in labels]


def action_accuracy(
    y_true: Sequence[Label],
    y_pred: Sequence[Label],
    dataset: str,
    lookup: Lookup,
    unmapped_pred: str = "incorrect",
) -> dict:
    """Action accuracy with explicit accounting.

    A sample can be scored only if its TRUE label maps to an action. If the
    PREDICTED label is unmapped, ``unmapped_pred`` decides:
      * "incorrect" -> counts as a wrong action (default), or
      * "exclude"   -> dropped from the denominator (but still counted).
    Returns a dict of the metric and all counts.
    """
    if unmapped_pred not in ("incorrect", "exclude"):
        raise ValueError("unmapped_pred must be 'incorrect' or 'exclude'")
    _check_lengths(y_true, y_pred)
    ta = project_labels(y_true, dataset, lookup)
    pa = project_labels(y_pred, dataset, lookup)
    n = len(ta)
    n_true_unmapped = sum(a is None for a in ta)
    n_pred_unmapped = sum(a is None for a in pa)

    included = correct = excluded = 0
    for t, p in zip(ta, pa):
        if t is None:
            excluded += 1  # cannot score without a true action
            continue
        if p is None:
            if unmapped_pred == "exclude":
                excluded += 1
                continue
            included += 1  # counts as incorrect (correct not incremented)
            continue
        included += 1
        if t == p:
            correct += 1

    return {
        "action_accuracy": (correct / included) if included else float("nan"),
        "n_total": n,
        "n_included": included,
        "n_excluded": excluded,
        "n_correct": correct,
        "n_true_unmapped": n_true_unmapped,
        "n_pred_unmapped": n_pred_unmapped,
        "unmapped_pred_policy": unmapped_pred,
    }


def majority_action_baseline(
    y_true: Sequence[Label],
    dataset: str,
    lookup: Lookup,
) -> dict:
    """Always predict the most frequent TRUE action. Accuracy over mapped samples."""
    ta = [a for a in project_labels(y_true, dataset, lookup) if a is not None]
    n_mapped = len(ta)
    if n_mapped == 0:
        return {"majority_action": None, "action_accuracy": float("nan"),
                "n_mapped": 0, "n_total": len(y_true)}
    s = pd.Series(ta)
    counts = s.value_counts()
    # deterministic tie-break: highest count, then action-name order
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    acc = float((s == top).mean())
    return {
        "majority_action": top,
        "action_accuracy": acc,
        "n_mapped": n_mapped,
        "n_total": len(y_true),
        "action_distribution": counts.to_dict(),
    }


def action_confusion_matrix(
    y_true: Sequence[Label],
    y_pred: Sequence[Label],
    dataset: str,
    lookup: Lookup,
    include_unmapped_pred: bool = True,
) -> pd.DataFrame:
    """Confusion over action classes (rows=true, cols=pred).

    Only samples with a mapped TRUE action are included (rows). Unmapped
    predictions go to an ``__unmapped__`` column when ``include_unmapped_pred``.
    """
    ta = project_labels(y_true, dataset, lookup)
    pa = project_labels(y_pred, dataset, lookup)
    cols = list(ACTION_CLASSES) + ([UNMAPPED] if include_unmapped_pred else [])
    mat = pd.DataFrame(0, index=list(ACTION_CLASSES), columns=cols, dtype=int)
    for t, p in zip(ta, pa):
        if t is None:
            continue
        pcol = p if p in ACTION_CLASSES else (UNMAPPED if include_unmapped_pred else None)
        if pcol is None:
            continue
        mat.loc[t, pcol] += 1
    return mat


def action_distribution(labels: Sequence[Label], dataset: str, lookup: Lookup) -> dict:
    """Distribution over action classes for a set of disease labels (mapped only)."""
    acts = [a for a in project_labels(labels, dataset, lookup) if a is not None]
    return pd.Series(acts, dtype=object).value_counts().to_dict()


def action_report(
    y_true: Sequence[Label],
    y_pred: Sequence[Label],
    dataset: str,
    lookup: Lookup,
    unmapped_pred: str = "incorrect",
) -> dict:
    """Canonical action-level report.

    Action accuracy is **never** returned alone: the action-class distribution,
    the mandatory majority-action baseline, and the projection-induced inflation
    (action accuracy is mechanically >= disease accuracy under label collapse)
    are always included in the same object.
    """
    disease_acc = disease_top1_accuracy(y_true, y_pred)
    act = action_accuracy(y_true, y_pred, dataset, lookup, unmapped_pred)
    majority = majority_action_baseline(y_true, dataset, lookup)
    action_acc = act["action_accuracy"]
    inflation = (
        None if (action_acc != action_acc or disease_acc != disease_acc)  # NaN guard
        else round(float(action_acc) - float(disease_acc), 6)
    )
    return {
        "disease_top1_accuracy": disease_acc,
        "action": act,
        "majority_baseline": majority,                 # mandatory floor
        "true_action_distribution": action_distribution(y_true, dataset, lookup),
        "pred_action_distribution": action_distribution(y_pred, dataset, lookup),
        "projection_inflation": {                       # explicitly reported
            "disease_accuracy": disease_acc,
            "action_accuracy": action_acc,
            "absolute_gain_from_collapse": inflation,
            "note": "action accuracy >= disease accuracy is expected under "
                    "label->action collapse; interpret with the majority baseline.",
        },
        "action_confusion": action_confusion_matrix(y_true, y_pred, dataset, lookup),
    }
