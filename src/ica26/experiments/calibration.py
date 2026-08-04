"""Temperature scaling for post-hoc confidence calibration.

A single scalar T is fitted on held-out validation logits by minimising NLL.
T does not change the argmax, so accuracy and F1 are untouched; only the
confidence distribution moves. The fitted T is applied unchanged to the test and
cross-domain logits — it is never refitted on evaluation data.
"""
from __future__ import annotations

import numpy as np
import torch


def fit_temperature(
    val_logits: np.ndarray,
    val_labels: np.ndarray,
    max_iter: int = 200,
    lr: float = 0.01,
) -> dict:
    """Fit the scalar temperature that minimises validation NLL.

    Optimises log(T) so T stays strictly positive under an unconstrained
    optimiser. Returns the temperature plus before/after NLL as evidence the fit
    actually helped.
    """
    logits = torch.as_tensor(np.asarray(val_logits), dtype=torch.float64)
    labels = torch.as_tensor(np.asarray(val_labels), dtype=torch.long)
    loss_fn = torch.nn.CrossEntropyLoss()

    nll_before = float(loss_fn(logits, labels).item())

    log_t = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    optimiser = torch.optim.LBFGS([log_t], lr=lr, max_iter=max_iter)

    def closure():
        optimiser.zero_grad()
        loss = loss_fn(logits / torch.exp(log_t), labels)
        loss.backward()
        return loss

    optimiser.step(closure)

    temperature = float(torch.exp(log_t.detach()).item())
    nll_after = float(loss_fn(logits / temperature, labels).item())

    return {
        "temperature": temperature,
        "val_nll_before": nll_before,
        "val_nll_after": nll_after,
        "improved": bool(nll_after <= nll_before),
        "n_val_samples": int(labels.numel()),
    }


def apply_temperature(logits: np.ndarray, temperature: float) -> np.ndarray:
    """Softmax over temperature-scaled logits, in float64 for stable NLL."""
    z = np.asarray(logits, dtype=np.float64) / float(temperature)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def softmax(logits: np.ndarray) -> np.ndarray:
    return apply_temperature(logits, 1.0)
