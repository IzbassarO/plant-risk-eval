"""Evaluation scope: which layers an original dataset class participates in.

Some dataset classes are legitimate *diagnosis* targets while being outside the
scope of a *plant-disease* action metric -- the arthropod-pest classes are the
motivating case (see ``reports/ARTHROPOD_PEST_EVALUATION_SCOPE.md``). Scoping is
never a data deletion: images and diagnosis-manifest rows are untouched, and the
class remains fully classifiable. Only the metric layers named in
``configs/evaluation_scope.yaml`` are switched off, and only by an explicit human
decision that cites a policy document.

Default posture is INCLUSIVE: a class with no entry participates in every layer.
That keeps the file honest -- narrowing scope requires writing it down.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional, Union

import yaml

from ..schemas import ValidationResult

DEFAULT_SCOPE_PATH = "configs/evaluation_scope.yaml"

#: The evaluation layers a scope entry may switch off.
SCOPE_LAYERS: tuple[str, ...] = (
    "include_diagnosis",
    "include_action_evaluation",
    "include_risk_weighted_evaluation",
)

#: Fields every out-of-scope entry must carry (provenance is mandatory).
REQUIRED_ENTRY_FIELDS: tuple[str, ...] = (
    "dataset",
    "dataset_class",
    "exclusion_reason",
    "policy_reference",
)

ClassKey = tuple[str, str]


@dataclass(frozen=True)
class ScopeEntry:
    """One recorded scope decision for a single original dataset class."""

    dataset: str
    dataset_class: str
    include_diagnosis: bool = True
    include_action_evaluation: bool = True
    include_risk_weighted_evaluation: bool = True
    exclusion_reason: str = ""
    policy_reference: str = ""
    decided_by: str = ""
    decided_at: str = ""
    notes: str = ""

    @property
    def key(self) -> ClassKey:
        return (self.dataset, self.dataset_class)


class EvaluationScope:
    """Lookup over :class:`ScopeEntry` records. Unknown classes are in scope."""

    def __init__(self, entries: Iterable[ScopeEntry] = (), *, source: str = ""):
        self.source = source
        self._entries: dict[ClassKey, ScopeEntry] = {}
        for e in entries:
            self._entries[e.key] = e

    # -- introspection ----------------------------------------------------- #
    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._entries)

    @property
    def entries(self) -> dict[ClassKey, ScopeEntry]:
        return dict(self._entries)

    def entry(self, dataset: str, dataset_class: str) -> Optional[ScopeEntry]:
        return self._entries.get((str(dataset), str(dataset_class)))

    # -- layer predicates (default True == in scope) ------------------------ #
    def _flag(self, dataset: str, dataset_class: str, layer: str) -> bool:
        e = self.entry(dataset, dataset_class)
        return True if e is None else bool(getattr(e, layer))

    def include_diagnosis(self, dataset: str, dataset_class: str) -> bool:
        return self._flag(dataset, dataset_class, "include_diagnosis")

    def include_action_evaluation(self, dataset: str, dataset_class: str) -> bool:
        return self._flag(dataset, dataset_class, "include_action_evaluation")

    def include_risk_weighted_evaluation(self, dataset: str, dataset_class: str) -> bool:
        return self._flag(dataset, dataset_class, "include_risk_weighted_evaluation")

    # -- projection filters ------------------------------------------------- #
    def filter_action_lookup(self, lookup: Mapping[ClassKey, str]) -> dict[ClassKey, str]:
        """Drop classes that are out of scope for ACTION-level evaluation.

        A dropped class projects to ``None``, so :mod:`ica26.evaluation.action_metrics`
        counts it as unmapped and excludes it from the denominator instead of
        silently scoring it.
        """
        return {k: v for k, v in lookup.items()
                if self.include_action_evaluation(k[0], k[1])}

    def filter_risk_weighted_lookup(self, lookup: Mapping[ClassKey, str]) -> dict[ClassKey, str]:
        """Drop classes that are out of scope for RISK-WEIGHTED (harm) evaluation."""
        return {k: v for k, v in lookup.items()
                if self.include_risk_weighted_evaluation(k[0], k[1])}

    def out_of_scope(self, layer: str) -> list[ClassKey]:
        """Sorted keys explicitly switched off for ``layer``."""
        if layer not in SCOPE_LAYERS:
            raise ValueError(f"unknown scope layer '{layer}' (allowed: {list(SCOPE_LAYERS)})")
        return sorted(k for k, e in self._entries.items() if not getattr(e, layer))


# --------------------------------------------------------------------------- #
# IO + validation
# --------------------------------------------------------------------------- #
def _as_bool(value, default: bool = True) -> Optional[bool]:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return None  # signals "not a boolean" to the validator


def load_scope(path: Union[str, Path] = DEFAULT_SCOPE_PATH) -> EvaluationScope:
    """Load a scope config. A missing file yields an EMPTY (fully inclusive) scope.

    An empty scope is the safe default here: it narrows nothing, so no metric can
    silently lose samples because a config went missing.
    """
    p = Path(path)
    if not p.exists():
        return EvaluationScope(source=str(path))
    data = yaml.safe_load(p.read_text()) or {}
    entries = []
    for raw in data.get("out_of_scope_classes") or []:
        entries.append(ScopeEntry(
            dataset=str(raw.get("dataset", "")).strip(),
            dataset_class=str(raw.get("dataset_class", "")).strip(),
            include_diagnosis=bool(_as_bool(raw.get("include_diagnosis"))),
            include_action_evaluation=bool(_as_bool(raw.get("include_action_evaluation"))),
            include_risk_weighted_evaluation=bool(_as_bool(raw.get("include_risk_weighted_evaluation"))),
            exclusion_reason=str(raw.get("exclusion_reason", "")).strip(),
            policy_reference=str(raw.get("policy_reference", "")).strip(),
            decided_by=str(raw.get("decided_by", "")).strip(),
            decided_at=str(raw.get("decided_at", "")).strip(),
            notes=str(raw.get("notes", "")).strip(),
        ))
    return EvaluationScope(entries, source=str(path))


def validate_scope(scope: Union[str, Path, EvaluationScope]) -> ValidationResult:
    """Every entry must be identified, provenance-bearing, and actually narrowing."""
    if isinstance(scope, (str, Path)):
        path = Path(scope)
        res = ValidationResult()
        if not path.exists():
            res.add("error", str(path), "scope config not found")
            return res
        data = yaml.safe_load(path.read_text()) or {}
        raw_entries = data.get("out_of_scope_classes") or []
        for i, raw in enumerate(raw_entries):
            where = f"out_of_scope_classes[{i}]"
            for layer in SCOPE_LAYERS:
                if layer in raw and not isinstance(raw[layer], bool):
                    res.add("error", where, f"'{layer}' must be a boolean, got {raw[layer]!r}")
        scope = load_scope(path)
    else:
        res = ValidationResult()

    seen: set[ClassKey] = set()
    for key, e in sorted(scope.entries.items()):
        where = f"{e.dataset}/{e.dataset_class}"
        for fld in REQUIRED_ENTRY_FIELDS:
            if not str(getattr(e, fld, "")).strip():
                res.add("error", where, f"scope entry field '{fld}' is empty")
        if key in seen:
            res.add("error", where, "duplicate scope entry")
        seen.add(key)
        if all(getattr(e, layer) for layer in SCOPE_LAYERS):
            res.add("warning", where,
                    "entry narrows nothing (every layer is included); remove it "
                    "or switch a layer off")
    return res
