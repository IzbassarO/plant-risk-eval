"""Mandatory metric controls: action accuracy never stands alone."""
from __future__ import annotations

from ica26.evaluation import action_metrics as am

LUT = {
    ("PlantDoc", "rust"): "fungicide",
    ("PlantDoc", "scab"): "fungicide",
    ("PlantDoc", "mosaic"): "remove_vector",
    ("PlantDoc", "healthy"): "monitor",
}


def test_action_report_includes_all_controls():
    yt = ["rust", "scab", "mosaic", "healthy"]
    yp = ["scab", "mosaic", "rust", "healthy"]
    rep = am.action_report(yt, yp, "PlantDoc", LUT)
    # controls that must always accompany action accuracy
    for key in ("disease_top1_accuracy", "action", "majority_baseline",
                "true_action_distribution", "pred_action_distribution",
                "projection_inflation", "action_confusion"):
        assert key in rep, key


def test_projection_inflation_is_reported_and_nonnegative():
    # disease acc 0.25 (only 'healthy' exact); action acc higher due to collapse
    yt = ["rust", "scab", "mosaic", "healthy"]
    yp = ["scab", "rust", "mosaic", "healthy"]  # rust<->scab both fungicide
    rep = am.action_report(yt, yp, "PlantDoc", LUT)
    infl = rep["projection_inflation"]
    assert infl["action_accuracy"] >= infl["disease_accuracy"]
    assert infl["absolute_gain_from_collapse"] >= 0


def test_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        am.disease_top1_accuracy(["a", "b"], ["a"])
    with pytest.raises(ValueError):
        am.action_accuracy(["rust", "scab"], ["rust"], "PlantDoc", LUT)


def test_true_action_distribution_counts():
    yt = ["rust", "scab", "healthy"]  # fungicide, fungicide, monitor
    rep = am.action_report(yt, yt, "PlantDoc", LUT)
    assert rep["true_action_distribution"]["fungicide"] == 2
    assert rep["majority_baseline"]["majority_action"] == "fungicide"
