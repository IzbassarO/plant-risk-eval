"""Selective prediction / risk-coverage."""
from __future__ import annotations

import numpy as np

from ica26.evaluation import selective as sel


def test_default_thresholds_sorted_ascending():
    conf = [0.9, 0.1, 0.5, 0.5]
    t = sel.default_thresholds(conf)
    assert list(t) == sorted(t)
    assert t[0] == 0.0


def test_coverage_monotonic_non_increasing():
    conf = [0.2, 0.4, 0.6, 0.8, 1.0]
    table = sel.risk_coverage_table(conf, correct=[True] * 5)
    cov = table["coverage"].tolist()
    assert cov == sorted(cov, reverse=True)  # coverage falls as threshold rises


def test_risk_coverage_values():
    conf = [0.9, 0.4, 0.8, 0.3]
    correct = [True, False, True, False]
    table = sel.risk_coverage_table(conf, correct=correct)
    # at threshold 0 -> full coverage, accuracy = 2/4
    row0 = table.iloc[0]
    assert row0["coverage"] == 1.0
    assert abs(row0["selective_accuracy"] - 0.5) < 1e-9
    # at a high threshold only the 0.9 sample remains -> accuracy 1.0
    high = table[table["threshold"] > 0.8]
    assert (high["selective_accuracy"] == 1.0).all()


def test_selective_harm():
    conf = [0.9, 0.2]
    harm = [0.0, 4.0]
    table = sel.selective_harm(conf, harm)
    # full coverage mean harm = 2.0; covering only the confident one -> 0.0
    assert abs(table.iloc[0]["selective_harm"] - 2.0) < 1e-9
    assert table.iloc[-1]["selective_harm"] == 0.0


def test_selective_action_accuracy_preserves_counts():
    conf = [0.9, 0.8, 0.7]
    ta = ["fungicide", None, "monitor"]  # middle unscored (unmapped true)
    pa = ["fungicide", "monitor", "monitor"]
    out = sel.selective_action_accuracy(conf, ta, pa)
    # counts are preserved, not silently dropped (P1.4 fix)
    assert out["n_total"] == 3
    assert out["n_scored"] == 2
    assert out["n_unmapped_true_excluded"] == 1
    table = out["risk_coverage"]
    # only 2 scorable samples; at full coverage both correct -> 1.0
    assert abs(table.iloc[0]["selective_action_accuracy"] - 1.0) < 1e-9
    # deferred count is reported in the risk-coverage table
    assert "n_deferred" in table.columns


def test_operating_point():
    conf = [0.9, 0.4, 0.8, 0.3]
    correct = [True, False, True, False]
    table = sel.risk_coverage_table(conf, correct=correct)
    op = sel.operating_point(table, "selective_accuracy", 0.99)
    assert op is not None and op["selective_accuracy"] >= 0.99


def test_deterministic_repeatability():
    conf = [0.5, 0.1, 0.9, 0.3, 0.7]
    correct = [True, False, True, False, True]
    t1 = sel.risk_coverage_table(conf, correct=correct)
    t2 = sel.risk_coverage_table(conf, correct=correct)
    assert t1.equals(t2)
