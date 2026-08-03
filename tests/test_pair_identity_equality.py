"""Fresh-vs-persisted canonical identity-set equality (R1-CRIT-001).

R1 reconciled fresh detection against the persisted pair table by COUNT. The
re-audit exploited that directly: one true exact pair ``one -> one``, a forged
table naming an unrelated existing pair ``other -> other`` with the same row
count, and a matching forged exclusion produced ``status=pass`` with zero
violations. Counting cannot see substitution.

These tests reproduce that exploit and pin the fix: the gate compares canonical
identity SETS, and refuses to run review or exclusion arithmetic at all when they
differ.
"""
from __future__ import annotations

import csv

import numpy as np
import pytest
from PIL import Image

from ica26.datasets import manifest as M
from ica26.leakage.gate import (
    CANONICAL_PAIR_SCHEMA,
    GateInputs,
    PairIdentity,
    build_authoritative_pairs,
    build_fresh_pairs,
    compute_gate,
    display_pair_ids,
    reconcile_pair_sets,
)

PAIR_TABLE_COLUMNS = [
    "canonical_pair_id", "pair_schema", "training_relpath", "evaluation_relpath",
    "training_class", "evaluation_class", "training_sha256", "evaluation_sha256",
    "hamming_distance", "classification",
]
EXACT_EXCL_COLUMNS = [
    "canonical_pair_id", "evaluation_dataset", "evaluation_relpath", "evaluation_class",
    "evaluation_sha256", "training_dataset", "training_relpath", "training_class",
    "training_sha256", "hamming_distance",
]
NEAR_REVIEW_COLUMNS = ["canonical_pair_id", "pair_id", "training_relative_path",
                       "evaluation_relative_path", "human_decision", "final_disposition"]
REVIEWED_EXCL_COLUMNS = ["pair_id", "training_relative_path", "evaluation_relative_path"]


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return path


def _img(path, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(path)


@pytest.fixture
def exploit_env(tmp_path):
    """One TRUE exact pair (`one`), plus an unrelated pair of files (`other`).

    ``train/c/one.png`` and ``test/c/one.png`` share bytes -> a real exact
    duplicate. ``other.png`` differs on each side and is not a duplicate.
    """
    tr_root = tmp_path / "train_ds"
    ev_root = tmp_path / "eval_ds"
    _img(tr_root / "train" / "c" / "one.png", 1)
    _img(tr_root / "train" / "c" / "other.png", 2)
    _img(ev_root / "test" / "c" / "one.png", 1)          # same bytes as training
    _img(ev_root / "test" / "c" / "other.png", 40)       # unrelated

    mans = {}
    for name, root in (("train_ds", tr_root), ("eval_ds", ev_root)):
        df = M.build_split_class_manifest(
            root=root, dataset=name, source_url="u", split_dirs=["train", "test"],
            acquired_at_utc="2026-01-01T00:00:00+00:00")
        mans[name] = tmp_path / f"{name}_manifest.csv"
        M.write_manifest(df, mans[name])

    env = {
        "tr_root": tr_root, "ev_root": ev_root,
        "tr_man": mans["train_ds"], "ev_man": mans["eval_ds"],
        "pair_table": tmp_path / "pairs.csv",
        "near_review": _write_csv(tmp_path / "near.csv", NEAR_REVIEW_COLUMNS, []),
        "reviewed_excl": _write_csv(tmp_path / "rexcl.csv", REVIEWED_EXCL_COLUMNS, []),
        "exact_excl": tmp_path / "exact.csv",
    }
    _write_csv(env["exact_excl"], EXACT_EXCL_COLUMNS, [])
    return env


def _sha(manifest, relpath):
    with open(manifest, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["relpath"] == relpath:
                return r["sha256"]
    return ""


def _identity(env, t_rel, e_rel, distance, kind):
    return PairIdentity(
        training_dataset="train_ds", training_relpath=t_rel, training_class="c",
        training_sha256=_sha(env["tr_man"], t_rel),
        evaluation_dataset="eval_ds", evaluation_relpath=e_rel, evaluation_class="c",
        evaluation_sha256=_sha(env["ev_man"], e_rel),
        phash_distance=distance, classification=kind)


def _table_row(ident, **over):
    row = {
        "canonical_pair_id": ident.canonical_pair_id,
        "pair_schema": CANONICAL_PAIR_SCHEMA,
        "training_relpath": ident.training_relpath,
        "evaluation_relpath": ident.evaluation_relpath,
        "training_class": ident.training_class,
        "evaluation_class": ident.evaluation_class,
        "training_sha256": ident.training_sha256,
        "evaluation_sha256": ident.evaluation_sha256,
        "hamming_distance": str(ident.phash_distance),
        "classification": ident.classification,
    }
    row.update(over)
    return row


def _exclusion_row(ident, **over):
    row = {
        "canonical_pair_id": ident.canonical_pair_id,
        "evaluation_dataset": "eval_ds", "evaluation_relpath": ident.evaluation_relpath,
        "evaluation_class": ident.evaluation_class,
        "evaluation_sha256": ident.evaluation_sha256,
        "training_dataset": "train_ds", "training_relpath": ident.training_relpath,
        "training_class": ident.training_class, "training_sha256": ident.training_sha256,
        "hamming_distance": str(ident.phash_distance),
    }
    row.update(over)
    return row


def _compute(env):
    gate, _ = compute_gate(
        training_manifest=env["tr_man"], training_root=env["tr_root"],
        training_dataset="train_ds",
        evaluation_manifest=env["ev_man"], evaluation_root=env["ev_root"],
        evaluation_dataset="eval_ds",
        pair_table=env["pair_table"], near_review=env["near_review"],
        reviewed_exclusions=env["reviewed_excl"], exact_exclusions=env["exact_excl"],
        threshold=6)
    return gate


# --------------------------------------------------------------------------- #
# The re-audit's exploit
# --------------------------------------------------------------------------- #
def test_forged_same_count_exact_table_is_rejected(exploit_env):
    """THE R1-CRIT-001 exploit: right count, wrong pairs, matching exclusion."""
    env = exploit_env
    true_pair = _identity(env, "train/c/one.png", "test/c/one.png", 0, "exact")
    forged = _identity(env, "train/c/other.png", "test/c/other.png", 0, "exact")

    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS, [_table_row(forged)])
    _write_csv(env["exact_excl"], EXACT_EXCL_COLUMNS, [_exclusion_row(forged)])

    gate = _compute(env)
    # Same row count as the real detection -- the old count check saw no problem.
    assert gate.exact_duplicate_count == 1
    assert gate.status != "pass"
    assert gate.status == "incomplete"
    assert gate.authorization_violations
    joined = " ".join(gate.authorization_violations)
    assert true_pair.canonical_pair_id in joined      # the real pair is missing
    assert forged.canonical_pair_id in joined         # the forged one is surplus
    # Authorization arithmetic must not have run on the wrong identities.
    assert gate.exact_excluded_count == 0
    assert gate.unresolved_pair_count >= 1


def test_honest_table_and_record_passes(exploit_env):
    """Control: the same environment authorises when the table is truthful."""
    env = exploit_env
    true_pair = _identity(env, "train/c/one.png", "test/c/one.png", 0, "exact")
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS, [_table_row(true_pair)])
    _write_csv(env["exact_excl"], EXACT_EXCL_COLUMNS, [_exclusion_row(true_pair)])
    gate = _compute(env)
    assert gate.authorization_violations == []
    assert gate.exact_duplicate_count == 1 and gate.exact_excluded_count == 1
    assert gate.status == "pass"


def test_empty_table_against_a_real_pair_is_rejected(exploit_env):
    env = exploit_env
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS, [])
    gate = _compute(env)
    assert gate.status == "incomplete"
    assert any("absent from the persisted pair table" in v
               for v in gate.authorization_violations)


@pytest.mark.parametrize("field,value", [
    ("training_class", "WRONG"),
    ("evaluation_class", "WRONG"),
    ("training_sha256", "0" * 64),
    ("evaluation_sha256", "0" * 64),
    ("hamming_distance", "3"),
    ("classification", "near"),
])
def test_any_mutated_table_field_breaks_set_equality(exploit_env, field, value):
    """Same row count, one mutated field -> the canonical id no longer matches."""
    env = exploit_env
    true_pair = _identity(env, "train/c/one.png", "test/c/one.png", 0, "exact")
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS,
               [_table_row(true_pair, **{field: value})])
    _write_csv(env["exact_excl"], EXACT_EXCL_COLUMNS, [_exclusion_row(true_pair)])
    gate = _compute(env)
    assert gate.status == "incomplete", field
    assert gate.authorization_violations


def test_surplus_table_row_breaks_set_equality(exploit_env):
    env = exploit_env
    true_pair = _identity(env, "train/c/one.png", "test/c/one.png", 0, "exact")
    ghost = _identity(env, "train/c/other.png", "test/c/other.png", 4, "near")
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS,
               [_table_row(true_pair), _table_row(ghost)])
    gate = _compute(env)
    assert gate.status == "incomplete"
    assert any("fresh detection did not produce" in v
               for v in gate.authorization_violations)


def test_exact_near_type_substitution_is_rejected(exploit_env):
    """Reclassifying an exact pair as near changes its canonical namespace."""
    env = exploit_env
    true_pair = _identity(env, "train/c/one.png", "test/c/one.png", 0, "exact")
    as_near = _identity(env, "train/c/one.png", "test/c/one.png", 1, "near")
    assert true_pair.canonical_pair_id != as_near.canonical_pair_id
    assert true_pair.canonical_pair_id.startswith("exact-")
    assert as_near.canonical_pair_id.startswith("near-")
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS, [_table_row(as_near)])
    gate = _compute(env)
    assert gate.status == "incomplete"


# --------------------------------------------------------------------------- #
# reconcile_pair_sets in isolation
# --------------------------------------------------------------------------- #
def _pi(**over):
    base = dict(
        training_dataset="A", training_relpath="t/a.jpg", training_class="ca",
        training_sha256="a" * 64, evaluation_dataset="B", evaluation_relpath="e/b.jpg",
        evaluation_class="cb", evaluation_sha256="b" * 64, phash_distance=6,
        classification="near")
    base.update(over)
    return PairIdentity(**base)


def test_equal_sets_produce_no_violation():
    p = _pi()
    violations, report = reconcile_pair_sets({p.canonical_pair_id: p}, {p.key: p})
    assert violations == [] and report["equal"] is True
    assert report["fresh_only"] == [] and report["persisted_only"] == []


def test_same_count_different_identity_is_reported_both_ways():
    fresh = _pi()
    persisted = _pi(training_relpath="t/z.jpg")
    violations, report = reconcile_pair_sets(
        {fresh.canonical_pair_id: fresh}, {persisted.key: persisted})
    assert report["fresh_count"] == report["persisted_count"] == 1
    assert report["equal"] is False
    assert len(report["fresh_only"]) == 1 and len(report["persisted_only"]) == 1
    assert len(violations) == 2


def test_report_names_the_schema():
    violations, report = reconcile_pair_sets({}, {})
    assert report["schema"] == CANONICAL_PAIR_SCHEMA
    assert violations == []


# --------------------------------------------------------------------------- #
# Canonical identity properties
# --------------------------------------------------------------------------- #
def test_identity_is_independent_of_row_order():
    a, b = _pi(), _pi(training_relpath="t/b.jpg")
    assert display_pair_ids([a, b]) == display_pair_ids([b, a])


def test_every_immutable_field_changes_the_identity():
    base = _pi()
    for field, value in [
        ("training_dataset", "X"), ("training_relpath", "t/x.jpg"),
        ("training_class", "x"), ("training_sha256", "c" * 64),
        ("evaluation_dataset", "X"), ("evaluation_relpath", "e/x.jpg"),
        ("evaluation_class", "x"), ("evaluation_sha256", "c" * 64),
        ("phash_distance", 5), ("classification", "exact"),
        ("phash_algorithm", "other"), ("phash_bits", 128),
    ]:
        assert _pi(**{field: value}).canonical_pair_id != base.canonical_pair_id, field


def test_serialization_is_versioned():
    assert CANONICAL_PAIR_SCHEMA in _pi().canonical_serialization()


def test_fresh_pairs_take_class_and_sha_from_the_manifest(exploit_env):
    """A forged table cannot influence a fresh identity."""
    import pandas as pd

    env = exploit_env
    result = {
        "exact": pd.DataFrame([{"path_a": "train/c/one.png", "path_b": "test/c/one.png",
                                "class_a": "IGNORED", "class_b": "IGNORED", "distance": 0}]),
        "near": pd.DataFrame(columns=["path_a", "path_b", "class_a", "class_b", "distance"]),
    }
    fresh = build_fresh_pairs(result, env["tr_man"], env["ev_man"],
                              training_dataset="train_ds", evaluation_dataset="eval_ds")
    pair = next(iter(fresh.values()))
    assert pair.training_class == "c"          # from the manifest, not "IGNORED"
    assert pair.training_sha256 == _sha(env["tr_man"], "train/c/one.png")


def test_persisted_table_endpoint_absent_from_manifest_is_a_violation(exploit_env):
    env = exploit_env
    _write_csv(env["pair_table"], PAIR_TABLE_COLUMNS, [{
        "training_relpath": "train/c/ghost.png", "evaluation_relpath": "test/c/one.png",
        "training_class": "c", "evaluation_class": "c",
        "hamming_distance": "0", "classification": "exact"}])
    pairs, violations = build_authoritative_pairs(
        env["pair_table"], env["tr_man"], env["ev_man"],
        training_dataset="train_ds", evaluation_dataset="eval_ds")
    assert pairs == {}
    assert any("absent from the training manifest" in v for v in violations)
