"""Governance validators: what a machine may conclude from a human's decision.

Two things live here, and they share one rule — **absence blocks**.

:mod:`~ica26.governance.mapping` decides whether a disease-to-action mapping
table is complete enough to support a freeze. :mod:`~ica26.governance.approvals`
decides whether a human approval or audit sign-off artifact is real.

Both were added after an audit found the previous predicates failing *open*:
mapping readiness was inferred from ``needs_review == 0``, which a renamed
status silently satisfied, and an approval was accepted from
``{"approved": true}`` — a file with no reviewer, no scope, no timestamp, and no
binding to what it claimed to approve. A predicate that can be satisfied by
accident is not a gate.

The rules here are therefore explicit rather than inferred: an allow-list of
terminal statuses, a required field set, a versioned artifact schema, and an
integrity binding to the exact digest of the thing being approved. Nothing
defaults to satisfied, and no code path may manufacture a human decision.
"""
from __future__ import annotations

from .approvals import (
    APPROVAL_SCHEMA,
    ApprovalSpec,
    ApprovalVerdict,
    AUDIT_SIGNOFF_SPEC,
    FREEZE_APPROVAL_SPEC,
    SECOND_REVIEW_SCHEMA_VERSION,
    SECOND_REVIEW_SPEC,
    is_placeholder,
    validate_approval_file,
)
from .mapping import (
    MAPPING_READINESS_SCHEMA,
    MappingReadiness,
    TERMINAL_STATUSES,
    evaluate_mapping_readiness,
)
from .freeze import (
    DATASET_FINGERPRINT_SCHEMA,
    FREEZE_ARTIFACT_PATH,
    FREEZE_SCHEMA,
    FreezeVerdict,
    build_dataset_fingerprint,
    build_freeze_payload,
    validate_freeze_file,
)

__all__ = [
    "APPROVAL_SCHEMA", "ApprovalSpec", "ApprovalVerdict", "AUDIT_SIGNOFF_SPEC",
    "FREEZE_APPROVAL_SPEC", "SECOND_REVIEW_SCHEMA_VERSION", "SECOND_REVIEW_SPEC",
    "is_placeholder",
    "validate_approval_file", "MAPPING_READINESS_SCHEMA", "MappingReadiness",
    "TERMINAL_STATUSES", "evaluate_mapping_readiness", "FREEZE_ARTIFACT_PATH",
    "FREEZE_SCHEMA", "DATASET_FINGERPRINT_SCHEMA", "FreezeVerdict",
    "build_dataset_fingerprint", "build_freeze_payload", "validate_freeze_file",
]
