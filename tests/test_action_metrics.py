"""Disease/action metrics: projection, accuracy, majority baseline, missing maps."""
from __future__ import annotations

import math

from ica26.evaluation import action_metrics as am


LUT = {
    ("PlantDoc", "rust"): "fungicide",
    ("PlantDoc", "yellow_virus"): "remove_vector",
    ("PlantDoc", "healthy"): "monitor",
}


def test_disease_top1_accuracy():
    assert am.disease_top1_accuracy(["a", "b", "c"], ["a", "b", "x"]) == 2 / 3
    assert math.isnan(am.disease_top1_accuracy([], []))


def test_projection():
    labels = ["rust", "healthy", "unknown_disease"]
    actions = am.project_labels(labels, "PlantDoc", LUT)
    assert actions == ["fungicide", "monitor", None]  # unmapped -> None


def test_action_accuracy_all_mapped():
    yt = ["rust", "healthy", "yellow_virus"]
    yp = ["rust", "healthy", "yellow_virus"]
    r = am.action_accuracy(yt, yp, "PlantDoc", LUT)
    assert r["action_accuracy"] == 1.0
    assert r["n_included"] == 3 and r["n_excluded"] == 0


def test_action_accuracy_counts_confusion():
    yt = ["rust", "healthy"]
    yp = ["healthy", "healthy"]  # first wrong action, second right
    r = am.action_accuracy(yt, yp, "PlantDoc", LUT)
    assert r["n_included"] == 2 and r["n_correct"] == 1
    assert r["action_accuracy"] == 0.5


def test_missing_true_mapping_is_excluded_not_dropped_silently():
    yt = ["rust", "unknown"]  # 'unknown' true label -> cannot score
    yp = ["rust", "rust"]
    r = am.action_accuracy(yt, yp, "PlantDoc", LUT)
    assert r["n_total"] == 2
    assert r["n_excluded"] == 1          # the unmapped-true sample
    assert r["n_true_unmapped"] == 1
    assert r["n_included"] == 1          # only the mapped one scored
    assert r["n_included"] + r["n_excluded"] == r["n_total"]


def test_unmapped_pred_policy_incorrect_vs_exclude():
    yt = ["rust", "rust"]
    yp = ["rust", "unknown"]  # second pred unmapped
    inc = am.action_accuracy(yt, yp, "PlantDoc", LUT, unmapped_pred="incorrect")
    exc = am.action_accuracy(yt, yp, "PlantDoc", LUT, unmapped_pred="exclude")
    assert inc["n_included"] == 2 and inc["n_correct"] == 1  # unmapped pred = wrong
    assert exc["n_included"] == 1 and exc["n_excluded"] == 1  # unmapped pred dropped
    assert inc["n_pred_unmapped"] == 1


def test_majority_action_baseline():
    yt = ["rust", "rust", "healthy"]  # actions: fungicide,fungicide,monitor
    r = am.majority_action_baseline(yt, "PlantDoc", LUT)
    assert r["majority_action"] == "fungicide"
    assert r["action_accuracy"] == 2 / 3
    assert r["n_mapped"] == 3


def test_action_confusion_matrix_shape_and_unmapped_col():
    yt = ["rust", "healthy"]
    yp = ["rust", "unknown"]  # second pred unmapped
    cm = am.action_confusion_matrix(yt, yp, "PlantDoc", LUT)
    assert cm.loc["fungicide", "fungicide"] == 1
    assert cm.loc["monitor", am.UNMAPPED] == 1
