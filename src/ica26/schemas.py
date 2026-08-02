"""Central, authoritative definitions shared across the ica26 package.

These constants encode the Phase-1 NON-NEGOTIABLE research constraints so that
every module (datasets, mapping, evaluation, leakage) agrees on the same
vocabulary. Changing an action class or a review-status value here changes it
everywhere -- that is deliberate.

Governing constraints (see reports/PHASE1_REPORT.md for provenance):
  * Exactly four action classes; ``abiotic_correction`` is intentionally absent.
  * A mapping row may be ``approved`` only if it carries verifiable evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# --------------------------------------------------------------------------- #
# Action taxonomy -- EXACTLY these four. Do not add abiotic_correction.
# --------------------------------------------------------------------------- #
ACTION_CLASSES: tuple[str, ...] = (
    "fungicide",
    "copper_sanitation",
    "remove_vector",
    "monitor",
)

#: Explicitly forbidden action labels (guards against regressions).
FORBIDDEN_ACTION_CLASSES: frozenset[str] = frozenset({"abiotic_correction"})


def is_valid_action(action: str) -> bool:
    return action in ACTION_CLASSES


# --------------------------------------------------------------------------- #
# Mapping review workflow
# --------------------------------------------------------------------------- #
REVIEW_STATUSES: tuple[str, ...] = ("pending", "needs_review", "approved", "excluded")
MAPPING_CONFIDENCES: tuple[str, ...] = ("low", "medium", "high")

#: Columns of data/mapping/action_mapping_template.csv, in order.
MAPPING_COLUMNS: tuple[str, ...] = (
    "dataset",
    "dataset_class",
    "canonical_crop",
    "canonical_disease",
    "pathogen_name",
    "pathogen_type",
    "action_class",
    "action_summary",
    "source_name",
    "source_url",
    "source_identifier",
    "evidence_summary",
    "evidence_checked_at",
    "mapping_confidence",
    "review_status",
    "review_notes",
)

#: Fields that MUST be non-empty before a row may be marked ``approved``.
#: This is the evidence gate: no verifiable evidence -> cannot be approved.
EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL: tuple[str, ...] = (
    "pathogen_type",
    "action_class",
    "action_summary",
    "source_name",
    "source_url",
    "source_identifier",
    "evidence_summary",
    "evidence_checked_at",
)

# --------------------------------------------------------------------------- #
# Healthy-class exemption -- see reports/HEALTHY_CLASS_ACTION_POLICY.md
#
# A healthy class is a NEGATIVE diagnosis class, not a pathogen of unknown type.
# There is no pathogen to cite, so the pathogen-specific half of the evidence
# gate is unsatisfiable by construction -- and fabricating a pathogen, pathogen
# type, source, or URL to satisfy it would be scientific misconduct. The
# exemption below is deliberately NARROW: it applies only to
# ``canonical_disease == 'healthy'`` mapped to ``monitor``, it still demands
# non-empty action/evidence prose and an explicit policy reference, and it
# additionally FORBIDS pathogen fields (so no row can quietly fabricate one).
# --------------------------------------------------------------------------- #

#: The exact canonical_disease value that triggers the healthy policy.
HEALTHY_CANONICAL_DISEASE: str = "healthy"

#: The only action class a healthy class may carry.
HEALTHY_ACTION_CLASS: str = "monitor"

#: Stable identifier a healthy row must cite (source_identifier or review_notes).
HEALTHY_POLICY_ID: str = "policy:healthy-monitor-v1"

#: Fields that MUST be non-empty before an approved HEALTHY row is accepted.
#: Note this is the full evidence gate MINUS the pathogen-specific fields.
HEALTHY_EVIDENCE_FIELDS_REQUIRED_FOR_APPROVAL: tuple[str, ...] = (
    "action_class",
    "action_summary",
    "evidence_summary",
    "evidence_checked_at",
)

#: Fields an approved healthy row MUST leave blank -- a healthy negative class
#: has no pathogen, so a value here can only be fabricated.
HEALTHY_FORBIDDEN_FIELDS: tuple[str, ...] = ("pathogen_name", "pathogen_type")


def is_healthy_disease(canonical_disease) -> bool:
    """True only for the exact canonical healthy label (case/space-insensitive)."""
    return str(canonical_disease or "").strip().lower() == HEALTHY_CANONICAL_DISEASE

#: Recognised pathogen types (used only to VALIDATE human-entered values;
#: the pipeline never auto-assigns one).
PATHOGEN_TYPES: tuple[str, ...] = (
    "fungal",
    "bacterial",
    "viral",
    "oomycete",
    "mite",
    "abiotic",
    "unknown",
)


# --------------------------------------------------------------------------- #
# Image manifest schema (shared by PlantDoc / PlantVillage acquisition)
# --------------------------------------------------------------------------- #
#: Columns common to every per-image manifest.
IMAGE_MANIFEST_COLUMNS: tuple[str, ...] = (
    "dataset",
    "split",
    "class_label",
    "relpath",
    "sha256",
    "width",
    "height",
    "mode",
    "n_bytes",
    "is_corrupt",
    "source_url",
    "acquired_at_utc",
)

#: Extra columns specific to PlantVillage (leaf-grouped splitting).
PLANTVILLAGE_EXTRA_COLUMNS: tuple[str, ...] = (
    "leaf_id",
    "has_leaf_id",
)

IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif", ".webp"}
)


@dataclass(frozen=True)
class DatasetSource:
    """Provenance for an acquired dataset -- recorded verbatim in manifests."""

    name: str
    url: str
    license: str
    citation: str = ""


# Canonical, non-fabricated provenance for the datasets used in Phase 1.
PLANTDOC_SOURCE = DatasetSource(
    name="PlantDoc",
    url="https://github.com/pratikkayal/PlantDoc-Dataset",
    license="CC BY 4.0",
    citation="Singh et al. 2020, CoDS-COMAD, DOI 10.1145/3371158.3371196",
)
PLANTVILLAGE_SOURCE = DatasetSource(
    name="PlantVillage",
    url="https://huggingface.co/datasets/mohanty/PlantVillage",
    license="CC BY-SA 3.0",
    citation="Mohanty, Hughes, Salathe 2016, Front. Plant Sci., DOI 10.3389/fpls.2016.01419",
)


@dataclass
class ValidationIssue:
    """A single problem found by a validator."""

    level: str  # "error" | "warning"
    where: str  # row index, column, or file
    message: str


@dataclass
class ValidationResult:
    """Aggregate result returned by validators. Truthy == passed (no errors)."""

    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, level: str, where: str, message: str) -> None:
        self.issues.append(ValidationIssue(level, where, message))

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.ok

    def summary(self) -> str:
        return f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
