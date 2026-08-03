"""Persisted pHash candidate-search telemetry is an audit contract.

Both Phase-1 entry points call the same detector, but historically each rebuilt
its leakage summary by hand and silently dropped the detector's scalability
telemetry.  The shared data-completion entry point also used to downgrade
canonical pair/exclusion artifacts to a legacy path-only shape.  These tests
keep emitted reports bound to the algorithm result and control-plane records.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

from ica26.leakage.gate import CANONICAL_PAIR_SCHEMA
from ica26.leakage.phash import (
    CANDIDATE_SEARCH_ALGORITHM,
    CANDIDATE_SEARCH_SCHEMA_VERSION,
    build_index,
)


def _load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_manifest(path: Path, *, relpath: str, dataset: str, sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=("dataset", "split", "class_label", "relpath", "is_corrupt", "sha256"),
        )
        writer.writeheader()
        writer.writerow({
            "dataset": dataset,
            "split": "test",
            "class_label": "leaf",
            "relpath": relpath,
            "is_corrupt": "False",
            "sha256": sha256,
        })


def _tiny_cross_dataset_layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    data_dir = tmp_path / "data"
    repo_dir = tmp_path / "repo"
    train_root = data_dir / "raw" / "plantvillage" / "color"
    eval_root = data_dir / "raw" / "plantdoc"
    train_root.mkdir(parents=True)
    eval_root.mkdir(parents=True)
    # Identical pixels are intentional: the entry points should preserve pair
    # output behavior while we inspect only the added summary telemetry.
    Image.new("RGB", (32, 32), color=(12, 34, 56)).save(train_root / "train.png")
    Image.new("RGB", (32, 32), color=(12, 34, 56)).save(eval_root / "eval.png")
    manifests = data_dir / "manifests"
    _write_manifest(
        manifests / "plantvillage_manifest.csv",
        relpath="train.png", dataset="PlantVillage", sha256="a" * 64,
    )
    _write_manifest(
        manifests / "plantdoc_manifest.csv",
        relpath="eval.png", dataset="PlantDoc", sha256="b" * 64,
    )
    return data_dir, repo_dir, train_root, eval_root


def _assert_candidate_search_contract(summary: dict) -> None:
    assert summary["candidate_search_schema_version"] == CANDIDATE_SEARCH_SCHEMA_VERSION
    assert summary["candidate_search_algorithm"] == CANDIDATE_SEARCH_ALGORITHM
    assert summary["candidate_search_exact_strategy"] == "hash-to-record-members"
    assert summary["candidate_search_near_strategy"] == (
        "recursive-pigeonhole-partition+bounded-leaf-verification")
    assert summary["candidate_search_near_input"] == "distinct-hash-values"
    assert summary["candidate_search_verification_unit"]
    assert summary["n_distinct_hashes_a"] == 1  # side A = PlantVillage training
    assert summary["n_distinct_hashes_b"] == 1  # side B = PlantDoc evaluation
    assert isinstance(summary["n_near_verifications"], int)
    assert summary["n_near_verifications"] >= 0
    assert summary["n_candidate_checks"] == summary["n_distance_evaluations"]
    assert summary["n_near_verifications"] == summary["n_distance_evaluations"]
    assert summary["n_partition_tasks"] >= 0
    assert summary["n_recursive_partitions"] >= 0
    assert summary["n_partition_memberships"] >= 0
    assert summary["max_leaf_pair_count"] >= 0


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or ()), list(reader)


def test_data_completion_leakage_summary_persists_candidate_search_telemetry(
    repo_root, tmp_path,
):
    driver = _load_script(
        "phase1_data_completion_telemetry_test",
        repo_root / "scripts" / "run_phase1_data_completion.py",
    )
    data_dir, repo_dir, train_root, _ = _tiny_cross_dataset_layout(tmp_path)

    driver.step_leakage(data_dir, repo_dir, train_root, threshold=1)

    summary = json.loads(
        (repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_summary.json").read_text())
    _assert_candidate_search_contract(summary)

    pair_columns, pair_rows = _read_rows(
        repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_pairs.csv")
    assert pair_columns == [
        "canonical_pair_id", "pair_schema",
        "training_relpath", "evaluation_relpath", "training_class", "evaluation_class",
        "training_sha256", "evaluation_sha256",
        "training_phash", "evaluation_phash", "hamming_distance", "classification",
        "review_status", "proposed_disposition", "notes",
    ]
    assert len(pair_rows) == 1
    assert pair_rows[0]["canonical_pair_id"].startswith("exact-")
    assert pair_rows[0]["pair_schema"] == CANONICAL_PAIR_SCHEMA
    assert pair_rows[0]["training_sha256"] == "a" * 64
    assert pair_rows[0]["evaluation_sha256"] == "b" * 64

    exclusion_columns, exclusion_rows = _read_rows(
        data_dir / "exclusions" / "cross_dataset_exact_exclusions.csv")
    assert exclusion_columns == [
        "canonical_pair_id", "pair_schema",
        "evaluation_dataset", "evaluation_relpath", "evaluation_class", "evaluation_sha256",
        "training_dataset", "training_relpath", "training_class", "training_sha256",
        "hamming_distance", "reason", "provenance", "action", "status",
    ]
    assert len(exclusion_rows) == 1
    assert exclusion_rows[0]["canonical_pair_id"] == pair_rows[0]["canonical_pair_id"]
    assert exclusion_rows[0]["pair_schema"] == CANONICAL_PAIR_SCHEMA


def test_local_leakage_summary_persists_candidate_search_telemetry(repo_root, tmp_path):
    driver = _load_script(
        "phase1_local_telemetry_test",
        repo_root / "scripts" / "run_phase1_local.py",
    )
    data_dir, repo_dir, _, _ = _tiny_cross_dataset_layout(tmp_path)
    indexes = data_dir / "indexes"
    indexes.mkdir(parents=True)
    build_index([{
        "dataset": "PlantVillage", "split": "test", "class_label": "leaf",
        "path": "train.png", "phash": "0000000000000000",
    }]).to_csv(indexes / "phash_index_plantvillage.csv", index=False)
    build_index([{
        "dataset": "PlantDoc", "split": "test", "class_label": "leaf",
        "path": "eval.png", "phash": "0000000000000000",
    }]).to_csv(indexes / "phash_index_plantdoc.csv", index=False)

    driver.step_leakage(data_dir, repo_dir, threshold=1)

    summary = json.loads(
        (repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_summary.json").read_text())
    _assert_candidate_search_contract(summary)


def test_audit_projection_refuses_an_incomplete_detector_summary():
    from ica26.leakage.phash import candidate_search_audit_fields

    try:
        candidate_search_audit_fields({"n_near_verifications": 0})
    except ValueError as exc:
        assert "missing audit field" in str(exc)
    else:  # pragma: no cover - an explicit guard for fail-closed behavior
        raise AssertionError("incomplete detector telemetry was accepted")


def test_audit_projection_refuses_tampered_algorithm_or_operation_counts():
    from ica26.leakage.phash import candidate_search_audit_fields, find_duplicates

    index = build_index([{
        "dataset": "A", "path": "a", "phash": "0000000000000000",
    }])
    summary = find_duplicates(index, threshold=6)["summary"]
    for field, value in (
        ("candidate_search_algorithm", "unreviewed-search"),
        ("n_distance_evaluations", -1),
        ("n_candidate_checks", 1),
        ("max_leaf_pair_count", 999_999),
    ):
        tampered = {**summary, field: value}
        with pytest.raises(ValueError):
            candidate_search_audit_fields(tampered)


def test_committed_leakage_summary_uses_the_current_auditable_contract(repo_root):
    from ica26.leakage.phash import candidate_search_audit_fields

    summary = json.loads(
        (repo_root / "reports/leakage_plantvillage_vs_plantdoc_summary.json").read_text())
    audit = candidate_search_audit_fields(summary)
    assert audit["n_distance_evaluations"] == 655_317
    assert summary["n_exact_pairs"] == 0
    assert summary["n_near_pairs"] == 16


def test_data_completion_refuses_to_downgrade_artifacts_from_an_identityless_manifest(
    repo_root, tmp_path,
):
    driver = _load_script(
        "phase1_data_completion_identity_guard_test",
        repo_root / "scripts" / "run_phase1_data_completion.py",
    )
    data_dir, repo_dir, train_root, _ = _tiny_cross_dataset_layout(tmp_path)
    # A blank endpoint digest used to yield the legacy, path-only output shape.
    # The new producer must fail before it replaces either control-plane file.
    manifest = data_dir / "manifests" / "plantvillage_manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    rows[0]["sha256"] = ""
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    pair_path = repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_pairs.csv"
    exclusion_path = data_dir / "exclusions" / "cross_dataset_exact_exclusions.csv"
    pair_path.parent.mkdir(parents=True)
    exclusion_path.parent.mkdir(parents=True)
    pair_path.write_text("canonical-pair-sentinel\n", encoding="utf-8")
    exclusion_path.write_text("canonical-exclusion-sentinel\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="refusing to write leakage control-plane artifacts"):
        driver.step_leakage(data_dir, repo_dir, train_root, threshold=1)

    assert pair_path.read_text(encoding="utf-8") == "canonical-pair-sentinel\n"
    assert exclusion_path.read_text(encoding="utf-8") == "canonical-exclusion-sentinel\n"
