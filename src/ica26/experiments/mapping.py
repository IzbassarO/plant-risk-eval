"""The frozen PlantVillage <-> PlantDoc shared-class mapping.

The repository has no human-authored PlantVillage class mapping: PlantVillage
action-mapping coverage is 0/38 and is tracked as an open blocker (BLOCK-07 in
``reports/PHASE1_REVIEW_VALIDATION.md``). Nothing here authors one. The mapping
is assembled from exactly two pieces of evidence that already exist in the
repository, and every class it cannot justify is excluded with a recorded
reason rather than guessed at.

Evidence source 1 -- ``deterministic_normalizer_key_collision``
    ``ica26.mapping.crosswalk.normalize_crop`` / ``normalize_disease`` are the
    repository's own deterministic label normalisers. Applied unchanged to both
    label spaces, eleven ``(crop, disease)`` keys collide exactly. The function
    is the same on both sides, so no judgement enters.

Evidence source 2 -- ``human_approved_healthy_policy``
    ``policy:healthy-monitor-v1`` (``reports/HEALTHY_CLASS_ACTION_POLICY.md``)
    is a recorded human decision that each PlantDoc ``"<Crop> leaf"`` class has
    ``canonical_disease = healthy``; the ten rows carry ``review_status =
    approved`` in ``data/mapping/action_mapping_review.csv``. On the PlantVillage
    side the token ``healthy`` is literal in the label. Ten crops are shared.

Anything else -- including biologically plausible near-misses such as PlantDoc
``Corn Gray leaf spot`` against PlantVillage
``Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot`` -- is excluded. Asserting
those pairs would be a new semantic judgement, which this repository's
governance deliberately routes through human review.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

MAPPING_CSV = "data/mapping/ica26_cross_domain_class_mapping.csv"

MAPPING_COLUMNS = [
    "canonical_class_id",
    "plantvillage_label",
    "plantdoc_label",
    "crop",
    "disease_state",
    "mapping_evidence",
    "evidence_source",
    "inclusion_status",
    "exclusion_reason",
]

EVIDENCE_NORMALIZER = "deterministic_normalizer_key_collision"
EVIDENCE_HEALTHY_POLICY = "human_approved_healthy_policy"


@dataclass(frozen=True)
class CrossDomainMapping:
    """A loaded, validated shared-class mapping."""

    rows: list[dict]

    @property
    def included(self) -> list[dict]:
        return [r for r in self.rows if r["inclusion_status"] == "included"]

    @property
    def canonical_classes(self) -> list[str]:
        return sorted({r["canonical_class_id"] for r in self.included})

    @property
    def plantdoc_to_canonical(self) -> dict[str, str]:
        return {r["plantdoc_label"]: r["canonical_class_id"] for r in self.included}

    @property
    def plantvillage_to_canonical(self) -> dict[str, str]:
        return {r["plantvillage_label"]: r["canonical_class_id"] for r in self.included}

    @property
    def canonical_to_plantvillage(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in self.included:
            out.setdefault(r["canonical_class_id"], []).append(r["plantvillage_label"])
        return {k: sorted(v) for k, v in out.items()}

    @property
    def canonical_to_plantdoc(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for r in self.included:
            out.setdefault(r["canonical_class_id"], []).append(r["plantdoc_label"])
        return {k: sorted(v) for k, v in out.items()}


def load_mapping(repo_root: str | Path = ".") -> CrossDomainMapping:
    path = Path(repo_root) / MAPPING_CSV
    if not path.exists():
        raise FileNotFoundError(
            f"cross-domain class mapping absent: {path}. "
            "Build it with scripts/ica26_build_cross_domain_mapping.py"
        )
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path}: mapping is empty")
    missing = set(MAPPING_COLUMNS) - set(rows[0])
    if missing:
        raise ValueError(f"{path}: mapping missing columns {sorted(missing)}")

    mapping = CrossDomainMapping(rows=rows)
    _validate(mapping, path)
    return mapping


def _validate(mapping: CrossDomainMapping, path: Path) -> None:
    """A malformed mapping must stop a run, not silently shrink it."""
    included = mapping.included
    if not included:
        raise ValueError(f"{path}: no included rows; cross-domain evaluation impossible")

    for r in included:
        for field in ("canonical_class_id", "plantvillage_label", "plantdoc_label",
                      "crop", "disease_state", "evidence_source"):
            if not str(r.get(field, "")).strip():
                raise ValueError(f"{path}: included row missing {field}: {r}")
        if str(r.get("exclusion_reason", "")).strip():
            raise ValueError(f"{path}: included row carries an exclusion_reason: {r}")

    # One PlantDoc class must not resolve to two canonical classes, or the
    # cross-domain ground truth would be ambiguous.
    seen: dict[str, str] = {}
    for r in included:
        label = r["plantdoc_label"]
        if label in seen and seen[label] != r["canonical_class_id"]:
            raise ValueError(
                f"{path}: PlantDoc class {label!r} maps to two canonical classes"
            )
        seen[label] = r["canonical_class_id"]

    for r in mapping.rows:
        if r["inclusion_status"] == "excluded" and not str(r.get("exclusion_reason", "")).strip():
            raise ValueError(f"{path}: excluded row without a reason: {r}")
        if r["inclusion_status"] not in ("included", "excluded"):
            raise ValueError(f"{path}: bad inclusion_status {r['inclusion_status']!r}")
