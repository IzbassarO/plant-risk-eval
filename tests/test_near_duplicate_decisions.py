"""The 16 recorded near-duplicate decisions, and their end-to-end authentication.

Unit-level forgery cases live in tests/test_leakage_gate.py. This module pins the
SHIPPED decisions and proves they still authenticate against the CURRENT
repository artifacts -- the rebuilt PlantDoc manifest (2,578 images), the
authoritative pair table, and the reviewed-exclusions file.
"""
from __future__ import annotations

import csv

import pytest

from ica26.leakage.gate import (
    NEAR_REVIEW_DECISIONS,
    NEAR_REVIEW_DISPOSITIONS,
    authenticate_exact_exclusions,
    authenticate_near_review,
    build_authoritative_pairs,
)

REVIEW_CSV = "data/exclusions/cross_dataset_near_duplicate_review.csv"
REVIEWED_EXCL_CSV = "data/exclusions/cross_dataset_reviewed_exclusions.csv"
EXACT_EXCL_CSV = "data/exclusions/cross_dataset_exact_exclusions.csv"
PAIR_TABLE = "reports/leakage_plantvillage_vs_plantdoc_pairs.csv"
PV_MANIFEST = "data/manifests/plantvillage_manifest.csv"
PD_MANIFEST = "data/manifests/plantdoc_manifest.csv"


@pytest.fixture(scope="module")
def recorded(repo_root):
    with open(repo_root / REVIEW_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="module")
def authoritative(repo_root):
    pairs, violations = build_authoritative_pairs(
        repo_root / PAIR_TABLE, repo_root / PV_MANIFEST, repo_root / PD_MANIFEST,
        training_dataset="PlantVillage", evaluation_dataset="PlantDoc")
    assert violations == [], violations
    return pairs


# --------------------------------------------------------------------------- #
# The recorded decisions
# --------------------------------------------------------------------------- #
def test_all_sixteen_pairs_are_adjudicated(recorded):
    assert len(recorded) == 16
    assert [r["pair_id"] for r in recorded] == [f"ndp-{i:02d}" for i in range(1, 17)]
    for r in recorded:
        assert r["human_decision"] in NEAR_REVIEW_DECISIONS
        assert r["final_disposition"] in NEAR_REVIEW_DISPOSITIONS


def test_recorded_decisions_match_the_confirmed_review(recorded):
    by_id = {r["pair_id"]: r for r in recorded}
    for i in range(1, 16):
        assert by_id[f"ndp-{i:02d}"]["human_decision"] == "clearly_different"
    assert by_id["ndp-16"]["human_decision"] == "visually_similar_but_independent"
    assert {r["final_disposition"] for r in recorded} == {"keep"}


def test_aggregate_counts(recorded):
    assert sum(r["final_disposition"] == "keep" for r in recorded) == 16
    assert sum(r["final_disposition"] == "exclude_evaluation" for r in recorded) == 0
    assert sum(r["human_decision"] == "uncertain" for r in recorded) == 0
    assert sum(r["final_disposition"] == "needs_secondary_review" for r in recorded) == 0


def test_every_decision_is_attributed_anonymously(recorded):
    for r in recorded:
        assert r["reviewer"] == "human_reviewer_1"
        assert r["reviewed_at"] == "2026-08-02T21:10:00+05:00"
        assert r["decision_reason"].strip()


def test_no_pair_was_excluded_so_the_exclusions_file_stays_empty(repo_root):
    with open(repo_root / REVIEWED_EXCL_CSV, newline="", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh)) == []


# --------------------------------------------------------------------------- #
# End-to-end authentication against the CURRENT artifacts
# --------------------------------------------------------------------------- #
def test_pair_table_reconciles_with_the_rebuilt_manifests(authoritative):
    near = {k: v for k, v in authoritative.items() if v.classification == "near"}
    exact = {k: v for k, v in authoritative.items() if v.classification == "exact"}
    assert len(near) == 16
    assert len(exact) == 0


def test_recorded_decisions_authenticate_after_the_plantdoc_rebuild(repo_root, authoritative):
    """Restoring six images must not have invalidated any recorded decision."""
    near = {k: v for k, v in authoritative.items() if v.classification == "near"}
    auth = authenticate_near_review(
        repo_root / REVIEW_CSV, near, repo_root / REVIEWED_EXCL_CSV)
    assert auth.violations == []
    assert auth.resolved == 16
    assert auth.kept == 16
    assert auth.excluded == 0
    assert auth.unresolved == 0


def test_review_sha256_fields_match_the_current_manifests(recorded, authoritative):
    """The recorded digests are the manifests' digests, not free-text."""
    for r in recorded:
        pair = authoritative[(r["training_relative_path"], r["evaluation_relative_path"])]
        assert r["training_sha256"] == pair.training_sha256
        assert r["evaluation_sha256"] == pair.evaluation_sha256
        assert int(r["phash_distance"]) == pair.phash_distance
        assert r["training_class"] == pair.training_class
        assert r["evaluation_class"] == pair.evaluation_class


def test_no_exact_pairs_and_no_exact_exclusions(repo_root, authoritative):
    exact = {k: v for k, v in authoritative.items() if v.classification == "exact"}
    auth = authenticate_exact_exclusions(repo_root / EXACT_EXCL_CSV, exact)
    assert auth.detected == 0
    assert auth.excluded == 0
    assert auth.violations == []


def test_identity_fields_are_intact(recorded):
    for r in recorded:
        assert r["training_dataset"] == "PlantVillage"
        assert r["evaluation_dataset"] == "PlantDoc"
        assert len(r["training_sha256"]) == 64
        assert len(r["evaluation_sha256"]) == 64
        assert 0 < int(r["phash_distance"]) <= 6


def test_every_reviewed_endpoint_still_exists_in_its_manifest(repo_root, recorded):
    with open(repo_root / PD_MANIFEST, newline="", encoding="utf-8") as fh:
        pd_paths = {r["relpath"] for r in csv.DictReader(fh)}
    with open(repo_root / PV_MANIFEST, newline="", encoding="utf-8") as fh:
        pv_paths = {r["relpath"] for r in csv.DictReader(fh)}
    for r in recorded:
        assert r["training_relative_path"] in pv_paths
        assert r["evaluation_relative_path"] in pd_paths


# --------------------------------------------------------------------------- #
# The persisted gate agrees with all of the above
# --------------------------------------------------------------------------- #
def test_persisted_gate_matches_the_recorded_review(repo_root):
    import json

    gate = json.loads((repo_root / "reports/leakage_gate.json").read_text())
    assert gate["schema_version"] == "2.0"
    assert gate["near_duplicate_count"] == 16
    assert gate["near_resolved_count"] == 16
    assert gate["near_kept_count"] == 16
    assert gate["near_excluded_count"] == 0
    assert gate["exact_duplicate_count"] == 0
    assert gate["exact_excluded_count"] == 0
    assert gate["unresolved_pair_count"] == 0
    assert gate["authorization_violations"] == []
    assert gate["status"] == "pass"
    assert "generated_at" not in gate
