"""Loading and validation of configs/action_taxonomy.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Union

import yaml

from .schemas import ACTION_CLASSES, FORBIDDEN_ACTION_CLASSES, ValidationResult

DEFAULT_TAXONOMY_PATH = "configs/action_taxonomy.yaml"


def load_taxonomy(path: Union[str, Path] = DEFAULT_TAXONOMY_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text())


def validate_taxonomy(taxonomy: Union[str, Path, dict]) -> ValidationResult:
    """Check the taxonomy defines EXACTLY the four action classes (in order),
    each with a description, and lists no forbidden class as active."""
    if isinstance(taxonomy, (str, Path)):
        taxonomy = load_taxonomy(taxonomy)
    res = ValidationResult()

    classes = taxonomy.get("action_classes")
    if not isinstance(classes, list):
        res.add("error", "action_classes", "must be a list")
        return res

    names = [str(c.get("name", "")).strip() for c in classes]
    if tuple(names) != ACTION_CLASSES:
        res.add(
            "error",
            "action_classes",
            f"names/order {names} must equal {list(ACTION_CLASSES)}",
        )
    for c in classes:
        name = str(c.get("name", "")).strip()
        if not str(c.get("description", "")).strip():
            res.add("error", name or "?", "missing description")
        if name in FORBIDDEN_ACTION_CLASSES:
            res.add("error", name, "forbidden action class present in action_classes")

    for f in taxonomy.get("forbidden_action_classes", []) or []:
        if f in names:
            res.add("error", str(f), "forbidden class also listed as active")

    return res
