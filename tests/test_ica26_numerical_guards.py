"""Guards against a run that dies numerically and reports anyway.

Background: on MPS there is no ``GradScaler``, so nothing inspected gradients
for overflow. One fp16 gradient reaching Inf entered AdamW, whose update
``m / sqrt(v)`` evaluates to Inf/Inf = NaN, and the parameter stayed NaN for the
rest of the run. Seed 42 never overflowed and seed 1337 did, on its first epoch.

What made it dangerous rather than merely annoying is that nothing failed. Train
accuracy is computed from batch statistics and still read 0.93. A NaN model
predicts one constant class, so it does not score zero --- it scores near the
majority-class rate, which looks like a weak result rather than a broken one.
The run would have written a normal-looking ``result.json`` straight into a
paper mean.

The central property tested here is that the fix is a *no-op* on a healthy run.
Anything that changed the numerics of every step --- switching precision, or
clipping gradients --- would make later seeds incomparable to the already
validated seed-42 runs. Skipping only the steps that would corrupt the model
leaves a non-overflowing run bit-identical.
"""
from __future__ import annotations

import math

import pytest
import torch
import torch.nn as nn

from ica26.experiments.train import (
    _assert_reportable,
    assert_finite_state,
    gradient_norm,
)


def _model_with_grads(seed: int = 0) -> nn.Module:
    torch.manual_seed(seed)
    model = nn.Sequential(nn.Linear(6, 12), nn.ReLU(), nn.Linear(12, 4))
    x = torch.randn(16, 6)
    y = torch.randint(0, 4, (16,))
    nn.CrossEntropyLoss()(model(x), y).backward()
    return model


# --------------------------------------------------------------------------- #
# the guard must not perturb a healthy run
# --------------------------------------------------------------------------- #
def test_measuring_the_gradient_norm_leaves_every_gradient_bit_identical():
    """The property that preserves comparability with the seed-42 runs."""
    model = _model_with_grads()
    before = [p.grad.clone() for p in model.parameters()]
    gradient_norm(model)
    for original, current in zip(before, model.parameters()):
        assert torch.equal(original, current.grad)


def test_repeated_measurement_does_not_drift():
    model = _model_with_grads()
    first = float(gradient_norm(model))
    for _ in range(5):
        assert float(gradient_norm(model)) == first


def test_norm_matches_the_explicit_computation():
    model = _model_with_grads()
    expected = torch.sqrt(sum((p.grad ** 2).sum() for p in model.parameters()))
    assert float(gradient_norm(model)) == pytest.approx(float(expected), rel=1e-6)


def test_a_healthy_gradient_is_finite_so_the_step_is_taken():
    assert torch.isfinite(gradient_norm(_model_with_grads()))


# --------------------------------------------------------------------------- #
# ...and must catch the case that killed the run
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan")])
def test_a_single_poisoned_gradient_element_is_detected(bad):
    """One element out of hundreds is enough to destroy the parameter."""
    model = _model_with_grads()
    model[0].weight.grad[0, 0] = bad
    assert not torch.isfinite(gradient_norm(model))


def test_detection_does_not_depend_on_which_tensor_is_poisoned():
    for index in (0, 2):
        model = _model_with_grads()
        list(model[index].parameters())[0].grad[0] = float("inf")
        assert not torch.isfinite(gradient_norm(model))


def test_adamw_turns_an_infinite_gradient_into_a_permanent_nan():
    """The mechanism itself, so the regression is recognisable if it returns.

    This is why skipping the step is the only repair: once the update lands,
    no later finite gradient recovers the parameter.
    """
    model = nn.Linear(3, 2)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    model.weight.grad = torch.full_like(model.weight, float("inf"))
    model.bias.grad = torch.zeros_like(model.bias)
    opt.step()
    assert torch.isnan(model.weight).all()

    # A clean gradient afterwards does not bring it back.
    model.weight.grad = torch.ones_like(model.weight)
    opt.step()
    assert torch.isnan(model.weight).all()


def test_skipping_the_step_preserves_the_parameter():
    """The same situation, with the guard applied."""
    model = nn.Linear(3, 2)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
    original = model.weight.detach().clone()
    model.weight.grad = torch.full_like(model.weight, float("inf"))
    model.bias.grad = torch.zeros_like(model.bias)

    if torch.isfinite(gradient_norm(model)):
        opt.step()
    else:
        opt.zero_grad(set_to_none=True)

    assert torch.equal(model.weight.detach(), original)
    assert torch.isfinite(model.weight).all()


# --------------------------------------------------------------------------- #
# nothing derived from a dead model may be reported
# --------------------------------------------------------------------------- #
def test_a_clean_model_passes_the_state_gate():
    assert_finite_state(nn.Linear(3, 2), "clean") is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_poisoned_parameter_fails_the_state_gate(bad):
    model = nn.Linear(3, 2)
    model.weight.data[0, 0] = bad
    with pytest.raises(RuntimeError, match="NaN or Inf"):
        assert_finite_state(model, "poisoned")


def test_the_state_gate_inspects_buffers_not_only_parameters():
    """BatchNorm running statistics are buffers, and a NaN there is equally
    fatal at evaluation time even when every weight is clean."""
    model = nn.BatchNorm1d(4)
    model.running_mean[2] = float("nan")
    with pytest.raises(RuntimeError, match="NaN or Inf"):
        assert_finite_state(model, "buffer")


def test_the_state_gate_names_the_offending_tensor():
    model = nn.Linear(3, 2)
    model.weight.data[0, 0] = float("nan")
    with pytest.raises(RuntimeError, match="weight"):
        assert_finite_state(model, "named")


def test_finite_metrics_are_reportable():
    results = {"evaluations": {"in_domain_test": {
        "accuracy": 0.99, "macro_f1": 0.98,
        "probabilistic": {"negative_log_likelihood": 0.05, "brier_score": 0.01},
    }}}
    assert _assert_reportable(results, "ok") is None


@pytest.mark.parametrize("field", ["accuracy", "macro_f1", "balanced_accuracy"])
def test_a_non_finite_headline_metric_is_refused(field):
    results = {"evaluations": {"in_domain_test": {field: float("nan")}}}
    with pytest.raises(RuntimeError, match="not finite"):
        _assert_reportable(results, "bad")


def test_a_non_finite_probabilistic_metric_is_refused():
    """NaN logits do propagate here, unlike accuracy, which stays finite."""
    results = {"evaluations": {"cross_domain_plantdoc_core": {
        "accuracy": 0.02,
        "probabilistic": {"negative_log_likelihood": float("nan")},
    }}}
    with pytest.raises(RuntimeError, match="not finite"):
        _assert_reportable(results, "bad")


def test_the_reason_a_metric_gate_alone_is_insufficient():
    """A dead model's accuracy is finite, so only the state gate catches it.

    Documented as a test because it is the counter-intuitive part: the observed
    failure produced accuracy 0.0115, not NaN.
    """
    results = {"evaluations": {"in_domain_test": {
        "accuracy": 0.011463, "macro_f1": 0.000596,
    }}}
    assert _assert_reportable(results, "plausible-but-dead") is None


def test_a_missing_metric_is_not_treated_as_non_finite():
    assert _assert_reportable({"evaluations": {"x": {"accuracy": None}}}, "sparse") is None
    assert _assert_reportable({}, "empty") is None


# --------------------------------------------------------------------------- #
# the recorded evidence
# --------------------------------------------------------------------------- #
def test_a_clean_run_records_zero_skipped_steps():
    """Verified against the archive: re-running pdc_mobilenet_v3_small_s42 under
    the guard reproduced the byte-identical checkpoint with 0 of 363 steps
    skipped. This asserts the field exists and is read the same way."""
    import json
    from pathlib import Path

    result = (Path(__file__).resolve().parent.parent
              / "experiments/ica26/runs/pdc_mobilenet_v3_small_s42/result.json")
    if not result.exists():
        pytest.skip("run artifacts not present")
    training = json.loads(result.read_text())["training"]
    if "skipped_nonfinite_steps" not in training:
        pytest.skip("run predates the guard")
    assert training["skipped_nonfinite_steps"] == 0
    assert training["optimiser_steps"] > 0
    assert all(math.isfinite(h["train_loss"]) for h in training["history"])
