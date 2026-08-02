"""Asymmetric harm-weighted error."""
from __future__ import annotations

import math

import pandas as pd

from ica26.evaluation import harm
from ica26.schemas import ACTION_CLASSES


def test_example_matrix_is_flagged_example():
    assert harm.EXAMPLE_DEV_HARM_MATRIX.is_example is True


def test_matrix_is_asymmetric():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    # asymmetry: cost of remove_vector->monitor differs from monitor->remove_vector
    assert m.loss("remove_vector", "monitor") != m.loss("monitor", "remove_vector")


def test_zero_diagonal_and_nonnegative():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    for a in ACTION_CLASSES:
        assert m.loss(a, a) == 0.0
    assert (m.matrix.values >= 0).all()
    assert m.validate().ok


def test_mean_harm_correct_actions_is_zero():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    r = m.mean_harm(["fungicide", "monitor"], ["fungicide", "monitor"])
    assert r["harm_weighted_error"] == 0.0
    assert r["n_included"] == 2


def test_mean_harm_uses_asymmetric_costs():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    # true=remove_vector, pred=monitor -> cost 5 (from example matrix)
    r = m.mean_harm(["remove_vector"], ["monitor"])
    assert r["harm_weighted_error"] == 5.0


def test_mean_harm_excludes_unmapped_true():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    r = m.mean_harm([None, "fungicide"], ["monitor", "fungicide"])
    assert r["n_excluded"] == 1 and r["n_included"] == 1
    assert r["harm_weighted_error"] == 0.0


def test_mean_harm_unmapped_pred_cost():
    m = harm.EXAMPLE_DEV_HARM_MATRIX
    excl = m.mean_harm(["fungicide"], [None])
    assert excl["n_excluded"] == 1 and math.isnan(excl["harm_weighted_error"])
    withcost = m.mean_harm(["fungicide"], [None], unmapped_pred_cost=9.0)
    assert withcost["harm_weighted_error"] == 9.0


def test_matrix_missing_entry_raises():
    partial = pd.DataFrame(
        [[0, 1], [1, 0]],
        index=["fungicide", "monitor"],
        columns=["fungicide", "monitor"],
    )
    try:
        harm.HarmMatrix(partial)
    except ValueError:
        return
    raise AssertionError("expected ValueError for incomplete harm matrix")
