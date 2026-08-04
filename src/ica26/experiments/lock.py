"""The ICA 2026 paper experiment dataset lock.

This lock is **not** the repository's formal governance freeze. It is a
reproducible scientific lock over the exact dataset inputs used by the ICA 2026
paper experiments. The formal Core Dataset governance freeze remains pending and
is not asserted, simulated, or implied anywhere in this module.

What the lock does: it binds a SHA-256 digest to every artifact a training run
reads, plus the verified record counts, class taxonomy, class-index mapping,
split assignment, and the cross-domain class mapping. ``validate`` recomputes all
of it and fails on the first difference, so a training run cannot silently
consume a corpus other than the one the paper reports.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

SCHEMA = "ica26.paper_experiment_dataset_lock/1"
LOCK_PATH = "data/manifests/ica26_core_experiment_lock.json"

DATASET_OWNER = "dataset_owner_1"

AUTHORIZED_USES = [
    "baseline_cv_training",
    "in_domain_evaluation",
    "cross_domain_evaluation",
    "calibration_experiments",
    "paper_table_and_figure_generation",
]

# Every artifact a training run may read, grouped by role. Paths are repository
# relative; each is digest-bound below.
LOCKED_ARTIFACTS: dict[str, list[str]] = {
    "plantvillage_committed_manifest": ["data/manifests/plantvillage_manifest.csv"],
    "plantvillage_pinned_reconstruction_evidence": [
        "reports/plantvillage_manifest_reconstruction.json",
        "data/manifests/plantvillage_source_snapshot.json",
        "data/manifests/plantvillage_summary.json",
    ],
    "plantdoc_acquired_manifest": [
        "data/manifests/plantdoc_manifest.csv",
        "data/manifests/plantdoc_source_snapshot.json",
        "data/manifests/plantdoc_summary.json",
    ],
    "plantdoc_effective_manifest": ["data/manifests/plantdoc_effective_manifest.csv"],
    "plantdoc_core_manifest": ["data/manifests/plantdoc_core_effective_manifest.csv"],
    "conservative_exclusion_artifact": [
        "data/exclusions/core_dataset_v1_conservative_exclusions.csv",
    ],
    "duplicate_exclusion_and_adjudication_artifacts": [
        "data/exclusions/plantdoc_internal_duplicate_resolution.csv",
        "data/exclusions/cross_dataset_exact_exclusions.csv",
        "data/exclusions/cross_dataset_reviewed_exclusions.csv",
        "data/exclusions/cross_dataset_near_duplicate_review.csv",
        "reports/plantdoc_internal_duplicate_gate.json",
        "data/manifests/plantdoc_case_collision_mapping.csv",
    ],
    "leakage_reports": [
        "reports/leakage_two_population_report.json",
        "reports/leakage_gate.json",
        "reports/leakage_plantvillage_vs_plantdoc_pairs.csv",
        "reports/leakage_plantvillage_vs_plantdoc_summary.json",
    ],
    "class_taxonomy": [
        "data/mapping/plantvillage_class_list.csv",
        "data/mapping/action_mapping_review.csv",
        "configs/evaluation_scope.yaml",
    ],
    "cross_domain_class_mapping": ["data/mapping/ica26_cross_domain_class_mapping.csv"],
}

# Counts independently verified before this lock was written. `validate`
# recomputes each from the manifests and refuses to proceed on any difference.
EXPECTED_COUNTS = {
    "plantvillage": {"total": 54305, "train": 43596, "test": 10709, "classes": 38},
    "plantdoc": {
        "source": 2578,
        "previous_effective": 2564,
        "core": 2561,
        "train": 2336,
        "test": 225,
        "classes": 28,
        "non_reviewed_unchanged": 2554,
        "retained_reviewed": 7,
        "excluded_reviewed": 17,
    },
    "leakage": {
        "acquired": {"exact": 0, "near": 16, "unresolved": 0},
        "core": {"exact": 0, "near": 16, "unresolved": 0},
    },
}

ASSERTIONS = [
    "no_source_image_was_deleted",
    "no_image_byte_was_modified",
    "g07_g08_g10_were_excluded_not_relabelled",
    "formal_governance_freeze_still_pending",
    "lock_scope_is_ica2026_paper_experiments_only",
]


class LockValidationError(RuntimeError):
    """Raised when the locked corpus and the on-disk corpus disagree."""


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit(repo_root: str | Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def _identity_digest(df: pd.DataFrame) -> str:
    """Digest over (relpath, split, class_label, sha256), sorted.

    Row order in the CSV cannot change this value, so a reordered but otherwise
    identical manifest still validates, while any changed label, split, identity,
    or content digest breaks it.
    """
    rows = sorted(
        f"{r.relpath}\t{r.split}\t{r.class_label}\t{r.sha256}"
        for r in df.itertuples(index=False)
    )
    return sha256_text("\n".join(rows))


def _class_index(labels: Iterable[str]) -> dict[str, int]:
    return {label: i for i, label in enumerate(sorted({str(x) for x in labels}))}


def _class_index_digest(index: dict[str, int]) -> str:
    return sha256_text("\n".join(f"{k}\t{v}" for k, v in sorted(index.items())))


def _split_counts(df: pd.DataFrame) -> dict[str, int]:
    return {str(k): int(v) for k, v in df["split"].value_counts().sort_index().items()}


def _per_class_split(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for (label, split), n in df.groupby(["class_label", "split"]).size().items():
        out.setdefault(str(label), {})[str(split)] = int(n)
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


@dataclass
class CorpusFacts:
    name: str
    manifest: str
    n_records: int
    splits: dict
    classes: list
    class_to_idx: dict
    class_index_digest: str
    identity_digest: str
    per_class_split_counts: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "manifest": self.manifest,
            "n_records": self.n_records,
            "split_counts": self.splits,
            "n_classes": len(self.classes),
            "classes": self.classes,
            "class_to_idx": self.class_to_idx,
            "class_index_digest": self.class_index_digest,
            "split_assignment_identity_digest": self.identity_digest,
            "per_class_split_counts": self.per_class_split_counts,
        }


def corpus_facts(name: str, manifest_relpath: str, repo_root: Path) -> CorpusFacts:
    df = pd.read_csv(repo_root / manifest_relpath)
    index = _class_index(df["class_label"])
    return CorpusFacts(
        name=name,
        manifest=manifest_relpath,
        n_records=len(df),
        splits=_split_counts(df),
        classes=sorted(index, key=lambda k: index[k]),
        class_to_idx=index,
        class_index_digest=_class_index_digest(index),
        identity_digest=_identity_digest(df),
        per_class_split_counts=_per_class_split(df),
    )


def build_lock(repo_root: str | Path = ".", created_at: str | None = None) -> dict:
    """Assemble the lock payload from the on-disk corpus."""
    repo_root = Path(repo_root)

    artifacts: dict[str, dict] = {}
    for role, paths in LOCKED_ARTIFACTS.items():
        artifacts[role] = {}
        for rel in paths:
            p = repo_root / rel
            if not p.exists():
                raise LockValidationError(f"locked artifact absent: {rel}")
            artifacts[role][rel] = {
                "sha256": sha256_file(p),
                "n_bytes": p.stat().st_size,
            }

    pv = corpus_facts("plantvillage", "data/manifests/plantvillage_manifest.csv", repo_root)
    pdc = corpus_facts("plantdoc_core", "data/manifests/plantdoc_core_effective_manifest.csv", repo_root)

    leak = json.loads((repo_root / "reports/leakage_two_population_report.json").read_text())

    from .mapping import load_mapping  # local import keeps module import cheap

    mapping = load_mapping(repo_root)
    core_df = pd.read_csv(repo_root / "data/manifests/plantdoc_core_effective_manifest.csv")
    shared_pd = set(mapping.plantdoc_to_canonical)
    cd_subset = core_df[core_df["class_label"].isin(shared_pd)]

    payload = {
        "schema": SCHEMA,
        "lock_kind": "scientific_experiment_lock",
        "is_formal_governance_freeze": False,
        "formal_governance_freeze_status": "pending",
        "purpose": (
            "Reproducible lock over the exact dataset inputs used by the ICA 2026 paper "
            "'Leakage-Controlled Cross-Domain Evaluation of Deep Learning Models for "
            "Plant Disease Classification'. This is not the repository's formal "
            "governance freeze and does not substitute for one."
        ),
        "dataset_owner": DATASET_OWNER,
        "owner_authorization": {
            "authorized_by": DATASET_OWNER,
            "authorized_uses": AUTHORIZED_USES,
            "statement": (
                f"The dataset owner ({DATASET_OWNER}) authorizes the exact locked Core "
                "Dataset for baseline CV training, in-domain evaluation, cross-domain "
                "evaluation, calibration experiments, and the generation of paper tables "
                "and figures. The formal Core Dataset governance freeze may remain pending "
                "without blocking these paper experiments."
            ),
            "not_authorized": [
                "risk_evaluation_layer_completion",
                "action_aware_training",
                "harm_weighted_evaluation",
                "treatment_recommendation",
            ],
        },
        "assertions": {
            "no_source_image_was_deleted": True,
            "no_image_byte_was_modified": True,
            "g07_g08_g10_were_excluded_not_relabelled": True,
            "formal_governance_freeze_still_pending": True,
            "lock_scope_is_ica2026_paper_experiments_only": True,
            "notes": (
                "Exclusion removes a record from the Core evaluation population only. "
                "The source manifest still carries all 2,578 acquired records and every "
                "image file remains on disk with its original bytes; digests in this lock "
                "are computed over those unmodified bytes."
            ),
        },
        "repository_commit": git_commit(repo_root),
        "created_at_utc": created_at,
        "artifacts": artifacts,
        "corpora": {"plantvillage": pv.to_dict(), "plantdoc_core": pdc.to_dict()},
        "expected_counts": EXPECTED_COUNTS,
        "leakage": {
            "acquired": {
                "population": "acquired",
                "n_evaluation_records": int(leak["acquired"]["n_evaluation_indexed"]),
                "exact": int(leak["acquired"]["n_exact_pairs"]),
                "near": int(leak["acquired"]["n_near_pairs"]),
                "unresolved": 0,
                "threshold": int(leak["acquired"]["threshold"]),
            },
            "core": {
                "population": "core",
                "n_evaluation_records": int(leak["core"]["n_evaluation_indexed"]),
                "exact": int(leak["core"]["n_exact_pairs"]),
                "near": int(leak["core"]["n_near_pairs"]),
                "unresolved": 0,
                "threshold": int(leak["core"]["threshold"]),
            },
        },
        "cross_domain_mapping": {
            "path": "data/mapping/ica26_cross_domain_class_mapping.csv",
            "n_shared_classes": len(mapping.canonical_classes),
            "shared_classes": mapping.canonical_classes,
            "plantdoc_to_canonical": mapping.plantdoc_to_canonical,
            "canonical_to_plantvillage": mapping.canonical_to_plantvillage,
            "n_evaluable_plantdoc_core_images": int(len(cd_subset)),
            "evaluable_split_counts": _split_counts(cd_subset),
            "n_excluded_plantdoc_core_images": int(len(core_df) - len(cd_subset)),
            "evidence_sources": sorted({r["evidence_source"] for r in mapping.included}),
        },
    }
    return payload


def canonical_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def lock_digest(payload: dict) -> str:
    """Digest of the lock content itself, excluding any self-referential field."""
    body = {k: v for k, v in payload.items() if k != "lock_digest"}
    return sha256_text(json.dumps(body, sort_keys=True, separators=(",", ":")))


def load_lock(repo_root: str | Path = ".") -> dict:
    path = Path(repo_root) / LOCK_PATH
    if not path.exists():
        raise LockValidationError(
            f"experiment dataset lock absent: {path}. "
            "Build it with scripts/ica26_build_experiment_lock.py"
        )
    return json.loads(path.read_text())


def validate(repo_root: str | Path = ".", check_pixels: bool = False) -> dict:
    """Recompute everything the lock binds and report every difference.

    Returns a report dict with ``ok`` and ``violations``. Raises nothing on a
    mismatch: the caller decides whether to abort, so a validation failure is
    always reported in full rather than truncated at the first problem.
    """
    repo_root = Path(repo_root)
    lock = load_lock(repo_root)
    violations: list[str] = []

    if lock.get("schema") != SCHEMA:
        violations.append(f"schema is {lock.get('schema')!r}, expected {SCHEMA!r}")
    if lock.get("is_formal_governance_freeze") is not False:
        violations.append("lock claims to be a formal governance freeze; it must not")

    # --- artifact digests ----------------------------------------------------
    for role, entries in lock.get("artifacts", {}).items():
        for rel, meta in entries.items():
            p = repo_root / rel
            if not p.exists():
                violations.append(f"{role}: locked artifact missing from disk: {rel}")
                continue
            actual = sha256_file(p)
            if actual != meta["sha256"]:
                violations.append(
                    f"{role}: digest changed for {rel}: "
                    f"locked {meta['sha256'][:16]}… actual {actual[:16]}…"
                )

    # --- corpus identity, counts, taxonomy, class index, splits --------------
    for key, manifest_key in (("plantvillage", "manifest"), ("plantdoc_core", "manifest")):
        locked = lock["corpora"][key]
        fresh = corpus_facts(key, locked[manifest_key], repo_root)
        if fresh.n_records != locked["n_records"]:
            violations.append(
                f"{key}: record count {fresh.n_records} != locked {locked['n_records']}"
            )
        if fresh.splits != locked["split_counts"]:
            violations.append(
                f"{key}: split counts {fresh.splits} != locked {locked['split_counts']}"
            )
        if fresh.classes != locked["classes"]:
            violations.append(f"{key}: class taxonomy differs from the locked taxonomy")
        if fresh.class_index_digest != locked["class_index_digest"]:
            violations.append(f"{key}: class-index mapping digest differs")
        if fresh.identity_digest != locked["split_assignment_identity_digest"]:
            violations.append(
                f"{key}: split/label/identity assignment digest differs "
                "(a record's split, label, or content digest changed)"
            )
        if fresh.per_class_split_counts != locked["per_class_split_counts"]:
            violations.append(f"{key}: per-class split counts differ")

    # --- the independently verified counts ----------------------------------
    exp = lock["expected_counts"]
    pv = lock["corpora"]["plantvillage"]
    pdc = lock["corpora"]["plantdoc_core"]
    checks = [
        ("plantvillage.total", pv["n_records"], exp["plantvillage"]["total"]),
        ("plantvillage.train", pv["split_counts"].get("train"), exp["plantvillage"]["train"]),
        ("plantvillage.test", pv["split_counts"].get("test"), exp["plantvillage"]["test"]),
        ("plantvillage.classes", pv["n_classes"], exp["plantvillage"]["classes"]),
        ("plantdoc.core", pdc["n_records"], exp["plantdoc"]["core"]),
        ("plantdoc.train", pdc["split_counts"].get("train"), exp["plantdoc"]["train"]),
        ("plantdoc.test", pdc["split_counts"].get("test"), exp["plantdoc"]["test"]),
        ("plantdoc.classes", pdc["n_classes"], exp["plantdoc"]["classes"]),
    ]
    for name, actual, expected in checks:
        if actual != expected:
            violations.append(f"count {name}: {actual} != expected {expected}")

    source_df = pd.read_csv(repo_root / "data/manifests/plantdoc_manifest.csv")
    effective_df = pd.read_csv(repo_root / "data/manifests/plantdoc_effective_manifest.csv")
    if len(source_df) != exp["plantdoc"]["source"]:
        violations.append(f"plantdoc source count {len(source_df)} != {exp['plantdoc']['source']}")
    if len(effective_df) != exp["plantdoc"]["previous_effective"]:
        violations.append(
            f"plantdoc previous-effective count {len(effective_df)} "
            f"!= {exp['plantdoc']['previous_effective']}"
        )

    # --- leakage -------------------------------------------------------------
    leak = json.loads((repo_root / "reports/leakage_two_population_report.json").read_text())
    for population in ("acquired", "core"):
        locked_leak = lock["leakage"][population]
        expected_leak = exp["leakage"][population]
        actual_exact = int(leak[population]["n_exact_pairs"])
        actual_near = int(leak[population]["n_near_pairs"])
        if actual_exact != expected_leak["exact"]:
            violations.append(
                f"leakage[{population}].exact {actual_exact} != {expected_leak['exact']}"
            )
        if actual_near != expected_leak["near"]:
            violations.append(
                f"leakage[{population}].near {actual_near} != {expected_leak['near']}"
            )
        if locked_leak["exact"] != expected_leak["exact"] or locked_leak["near"] != expected_leak["near"]:
            violations.append(f"leakage[{population}] locked values disagree with expected_counts")

    # --- cross-domain mapping ------------------------------------------------
    from .mapping import load_mapping

    try:
        mapping = load_mapping(repo_root)
    except Exception as exc:
        violations.append(f"cross-domain mapping unusable: {exc}")
    else:
        locked_cd = lock["cross_domain_mapping"]
        if mapping.canonical_classes != locked_cd["shared_classes"]:
            violations.append("cross-domain shared-class set differs from the locked set")
        if mapping.plantdoc_to_canonical != locked_cd["plantdoc_to_canonical"]:
            violations.append("cross-domain PlantDoc->canonical mapping differs")
        if mapping.canonical_to_plantvillage != locked_cd["canonical_to_plantvillage"]:
            violations.append("cross-domain canonical->PlantVillage mapping differs")

    # --- optional pixel verification ----------------------------------------
    if check_pixels and not violations:
        for name, manifest, root in (
            ("plantvillage", "data/manifests/plantvillage_manifest.csv",
             "data/raw/plantvillage/extracted"),
            ("plantdoc_core", "data/manifests/plantdoc_core_effective_manifest.csv",
             "data/raw/plantdoc"),
        ):
            df = pd.read_csv(repo_root / manifest)
            missing = [r for r in df["relpath"] if not (repo_root / root / r).exists()]
            if missing:
                violations.append(
                    f"{name}: {len(missing)} manifest row(s) have no file on disk "
                    f"(first: {missing[0]})"
                )

    return {
        "ok": not violations,
        "violations": violations,
        "schema": SCHEMA,
        "lock_digest": lock.get("lock_digest"),
        "repository_commit_at_lock_time": lock.get("repository_commit"),
        "checked_pixels": bool(check_pixels),
    }


def require_valid_lock(repo_root: str | Path = ".", check_pixels: bool = False) -> dict:
    """Abort unless the lock validates. Every training command calls this."""
    report = validate(repo_root, check_pixels=check_pixels)
    if not report["ok"]:
        raise LockValidationError(
            "ICA 2026 experiment dataset lock does not validate; refusing to train.\n  - "
            + "\n  - ".join(report["violations"])
        )
    return report
