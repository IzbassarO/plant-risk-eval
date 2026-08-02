"""Gate-enforced cross-dataset evaluation entry point.

This is the ONLY sanctioned way to compute cross-dataset action metrics. It
fails closed unless (1) a valid, current leakage gate exists, and (2) at least
one disease-to-action mapping is human-approved. When a harm matrix is supplied
it must be an approved ReviewedHarmMatrix, and the harm-weighted error is then
mandatory. It is impossible to reach the metrics without clearing these guards,
except via the explicit development-only leakage override.
"""
from __future__ import annotations

from typing import Optional, Sequence

from ..leakage.gate import require_valid_gate
from ..mapping.validation import require_approved_lookup
from .action_metrics import action_report, project_labels
from .harm import ReviewedHarmMatrix, require_production_matrix


def guarded_cross_dataset_action_evaluation(
    *,
    y_true: Sequence[str],
    y_pred: Sequence[str],
    dataset: str,
    mapping_df,
    gate_path,
    training_manifest,
    evaluation_manifest,
    harm_matrix: Optional[ReviewedHarmMatrix] = None,
    confidences: Optional[Sequence[float]] = None,
    allow_missing_leakage_gate: bool = False,
) -> dict:
    """Run cross-dataset action evaluation behind the leakage + mapping gates.

    Raises:
        LeakageGateError -- gate missing/stale/not passing (unless dev override).
        NoApprovedMappingError -- no approved disease->action mappings.
        HarmMatrixError -- a non-approved harm matrix was supplied.
    """
    # 1) Leakage clearance (fail closed; dev-only override warns loudly).
    require_valid_gate(
        gate_path, training_manifest, evaluation_manifest,
        allow_missing_leakage_gate=allow_missing_leakage_gate,
    )

    # 2) Approved mapping is a hard stop.
    lookup = require_approved_lookup(mapping_df)

    # 3) Canonical action report (disease acc + action acc + majority baseline +
    #    distributions + projection inflation + confusion, all together).
    report = action_report(y_true, y_pred, dataset, lookup)

    # 4) Harm-weighted error is MANDATORY once a matrix is supplied, and the
    #    matrix must be production-approved.
    if harm_matrix is not None:
        m = require_production_matrix(harm_matrix)
        ta = project_labels(y_true, dataset, lookup)
        pa = project_labels(y_pred, dataset, lookup)
        report["harm_weighted_error"] = m.mean_harm(ta, pa)
        report["harm_matrix_id"] = m.matrix_id

    # 5) Optional selective / risk-coverage curves.
    if confidences is not None:
        from .selective import selective_action_accuracy, selective_disease_accuracy
        ta = project_labels(y_true, dataset, lookup)
        pa = project_labels(y_pred, dataset, lookup)
        report["selective_disease"] = selective_disease_accuracy(confidences, y_true, y_pred)
        report["selective_action"] = selective_action_accuracy(confidences, ta, pa)

    return report
