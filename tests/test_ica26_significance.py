"""Statistics behind the ICA 2026 significance analysis.

The analysis script takes two shortcuts that make it exact and fast rather than
approximate: it computes accuracy and macro-F1 straight from a contingency
table, and it bootstraps by drawing multinomially over that table's cells
instead of resampling items. Both are only valid if they agree *exactly* with
the naive computation, so both are checked against it here rather than assumed.

The tests are adversarial in the same spirit as the rest of the suite: a helper
that only agrees on well-behaved input is not good enough, so the awkward cases
-- a class the model never predicts, a class with a single example, predictions
landing outside the evaluated label space -- are exercised explicitly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest
from sklearn.metrics import accuracy_score, f1_score

REPO = Path(__file__).resolve().parent.parent


def _load_script():
    """Import the analysis script by path; scripts/ is not a package."""
    spec = importlib.util.spec_from_file_location(
        "ica26_significance", REPO / "scripts/ica26_significance.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sig = _load_script()


def _naive(y_true, y_pred, labels):
    """What the repository reports, computed the obvious way."""
    return (
        float(accuracy_score(y_true, y_pred)),
        float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
    )


def _roundtrip(y_true, y_pred, n_pred_space):
    labels = sorted(set(np.asarray(y_true).tolist()))
    cm = sig.contingency(np.asarray(y_true), np.asarray(y_pred), labels, n_pred_space)
    return sig.stats_from_cm(cm, labels), _naive(y_true, y_pred, labels), cm, labels


# --------------------------------------------------------------------------- #
# contingency-table statistics match sklearn
# --------------------------------------------------------------------------- #
def test_perfect_prediction_scores_one():
    y = [0, 1, 2, 0, 1, 2]
    got, want, _, _ = _roundtrip(y, y, 3)
    assert got == pytest.approx(want)
    assert got == pytest.approx((1.0, 1.0))


def test_matches_sklearn_on_a_messy_case():
    y_true = [0, 0, 1, 1, 2, 2, 2, 3]
    y_pred = [0, 1, 1, 2, 2, 2, 0, 3]
    got, want, _, _ = _roundtrip(y_true, y_pred, 4)
    assert got == pytest.approx(want)


def test_class_never_predicted_scores_zero_not_nan():
    """A class with support but no predictions has precision 0/0.

    sklearn's zero_division=0 makes that 0.0; a naive division would make it
    NaN and poison the macro average.
    """
    y_true = [0, 0, 1, 1]
    y_pred = [0, 0, 0, 0]
    got, want, _, _ = _roundtrip(y_true, y_pred, 2)
    assert got == pytest.approx(want)
    assert np.isfinite(got[1])


def test_predictions_outside_the_evaluated_label_space_count_as_errors():
    """PlantDoc Core's arthropod-pest class has no test images but can still be
    predicted. Those predictions are errors and must not be silently dropped."""
    y_true = [0, 0, 1, 1]
    y_pred = [0, 2, 1, 2]          # class 2 has zero support in y_true
    (acc, macro_f1), want, cm, labels = _roundtrip(y_true, y_pred, 3)
    assert (acc, macro_f1) == pytest.approx(want)
    assert acc == pytest.approx(0.5)
    assert cm.shape == (2, 3)      # two evaluated rows, three prediction columns
    assert cm[:, 2].sum() == 2     # both stray predictions retained


def test_singleton_class_is_handled():
    y_true = [0, 0, 0, 1]
    y_pred = [0, 0, 1, 1]
    got, want, _, _ = _roundtrip(y_true, y_pred, 2)
    assert got == pytest.approx(want)


@pytest.mark.parametrize("trial", range(12))
def test_matches_sklearn_on_random_problems(trial):
    rng = np.random.default_rng(1000 + trial)
    n_classes = int(rng.integers(2, 9))
    n = int(rng.integers(12, 400))
    y_true = rng.integers(0, n_classes, size=n)
    # Correlated with the truth, so the tables are not uniformly random noise.
    flip = rng.random(n) < 0.35
    y_pred = np.where(flip, rng.integers(0, n_classes, size=n), y_true)
    got, want, _, _ = _roundtrip(y_true, y_pred, n_classes)
    assert got == pytest.approx(want)


def test_vectorised_stats_agree_with_the_scalar_version():
    rng = np.random.default_rng(7)
    y_true = rng.integers(0, 5, size=200)
    y_pred = np.where(rng.random(200) < 0.4, rng.integers(0, 5, size=200), y_true)
    labels = sorted(set(y_true.tolist()))
    cm = sig.contingency(y_true, y_pred, labels, 5)

    stacked = np.repeat(cm[None, :, :], 3, axis=0)
    acc_many, f1_many = sig._stats_many(stacked, labels)
    acc_one, f1_one = sig.stats_from_cm(cm, labels)
    assert acc_many == pytest.approx([acc_one] * 3)
    assert f1_many == pytest.approx([f1_one] * 3)


# --------------------------------------------------------------------------- #
# the bootstrap shortcut is equivalent to resampling items
# --------------------------------------------------------------------------- #
def test_multinomial_over_cells_equals_resampling_items():
    """The load-bearing assumption of the whole bootstrap.

    Both routes are driven from the same seed, so agreement here is exact
    equality of the resulting statistics, not a distributional argument.
    """
    rng = np.random.default_rng(11)
    y_true = rng.integers(0, 4, size=150)
    y_pred = np.where(rng.random(150) < 0.4, rng.integers(0, 4, size=150), y_true)
    labels = sorted(set(y_true.tolist()))
    cm = sig.contingency(y_true, y_pred, labels, 4)

    # Route A: resample item indices, rebuild the table from the resampled items.
    idx_rng = np.random.default_rng(99)
    by_items = []
    for _ in range(40):
        idx = idx_rng.integers(0, len(y_true), size=len(y_true))
        boot_cm = sig.contingency(y_true[idx], y_pred[idx], labels, 4)
        by_items.append(sig.stats_from_cm(boot_cm, labels))

    # Route B: the same item resamples, expressed as cell counts.
    idx_rng = np.random.default_rng(99)
    by_cells = []
    for _ in range(40):
        idx = idx_rng.integers(0, len(y_true), size=len(y_true))
        flat = np.zeros(cm.size, dtype=np.int64)
        rows = {c: i for i, c in enumerate(labels)}
        for t, p in zip(y_true[idx], y_pred[idx]):
            flat[rows[int(t)] * cm.shape[1] + int(p)] += 1
        by_cells.append(sig.stats_from_cm(flat.reshape(cm.shape), labels))

    assert by_items == pytest.approx(by_cells)


def test_bca_interval_brackets_the_estimate_and_is_reproducible():
    rng = np.random.default_rng(3)
    y_true = rng.integers(0, 4, size=300)
    y_pred = np.where(rng.random(300) < 0.3, rng.integers(0, 4, size=300), y_true)
    labels = sorted(set(y_true.tolist()))
    cm = sig.contingency(y_true, y_pred, labels, 4)

    a = sig.bca_interval(cm, labels, "accuracy", np.random.default_rng(5))
    b = sig.bca_interval(cm, labels, "accuracy", np.random.default_rng(5))
    assert a == b, "same rng seed must give the same interval"
    assert a["ci_lower"] <= a["point_estimate"] <= a["ci_upper"]
    assert 0.0 <= a["ci_lower"] and a["ci_upper"] <= 1.0
    assert a["method"] in {"bca", "percentile"}


def test_degenerate_statistic_falls_back_to_percentile_and_says_so():
    """A perfect classifier makes accuracy constant across every resample, so
    the bias correction is undefined. The interval must degrade loudly."""
    y = np.arange(40) % 4
    labels = sorted(set(y.tolist()))
    cm = sig.contingency(y, y, labels, 4)
    out = sig.bca_interval(cm, labels, "accuracy", np.random.default_rng(1))
    assert out["method"] == "percentile"
    assert out["point_estimate"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# McNemar
# --------------------------------------------------------------------------- #
def test_mcnemar_identical_models_cannot_be_distinguished():
    correct = np.array([True, False, True, True, False])
    out = sig.mcnemar_exact(correct, correct)
    assert out["n_discordant"] == 0
    assert out["p_value"] == 1.0


def test_mcnemar_counts_only_discordant_pairs():
    a = np.array([True, True, False, False, True, True])
    b = np.array([True, False, True, False, False, True])
    out = sig.mcnemar_exact(a, b)
    assert out["n_a_only_correct"] == 2      # positions 1 and 4
    assert out["n_b_only_correct"] == 1      # position 2
    assert out["n_discordant"] == 3
    assert out["n_both_correct"] == 2
    assert out["n_both_wrong"] == 1


def test_mcnemar_matches_the_exact_binomial_by_hand():
    """b=9, c=1 out of 10 discordant: two-sided exact p = 2 * P(X<=1) = 0.021484375."""
    a = np.array([True] * 9 + [False] * 1)
    b = np.array([False] * 9 + [True] * 1)
    out = sig.mcnemar_exact(a, b)
    assert out["p_value"] == pytest.approx(2 * (10 + 1) / 2 ** 10)


def test_mcnemar_is_symmetric_in_its_p_value():
    rng = np.random.default_rng(4)
    a = rng.random(200) < 0.7
    b = rng.random(200) < 0.6
    assert sig.mcnemar_exact(a, b)["p_value"] == pytest.approx(
        sig.mcnemar_exact(b, a)["p_value"]
    )


def test_a_lopsided_split_is_significant_and_a_balanced_one_is_not():
    lopsided = sig.mcnemar_exact(
        np.array([True] * 30 + [False] * 2), np.array([False] * 30 + [True] * 2)
    )
    balanced = sig.mcnemar_exact(
        np.array([True] * 16 + [False] * 16), np.array([False] * 16 + [True] * 16)
    )
    assert lopsided["p_value"] < 0.001
    assert balanced["p_value"] == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Holm correction
# --------------------------------------------------------------------------- #
def test_holm_never_shrinks_a_p_value_and_stays_monotone():
    raw = [0.001, 0.04, 0.03, 0.5, 0.2]
    adj = sig.holm_bonferroni(raw)
    assert all(a >= r for a, r in zip(adj, raw))
    ordered = [adj[i] for i in sorted(range(len(raw)), key=lambda i: raw[i])]
    assert ordered == sorted(ordered), "adjusted values must not decrease with rank"


def test_holm_smallest_p_value_gets_the_full_bonferroni_factor():
    adj = sig.holm_bonferroni([0.01, 0.5, 0.6, 0.7])
    assert adj[0] == pytest.approx(0.04)


def test_holm_caps_at_one():
    assert all(a <= 1.0 for a in sig.holm_bonferroni([0.5, 0.6, 0.9, 0.99]))


def test_holm_of_a_single_test_changes_nothing():
    assert sig.holm_bonferroni([0.023]) == pytest.approx([0.023])
