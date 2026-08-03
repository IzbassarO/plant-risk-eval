"""Leakage-gate: fail-closed behaviour, identity authentication, input binding.

Schema 2.0 hardens the three critical audit findings:

* **AUD-EC-001** a near-review row is authenticated against the full canonical
  pair identity, and the review set must be in strict bijection with the
  authoritative near set. Forgery attempts do not merely lose credit -- they
  force the gate to ``fail``.
* **AUD-EC-002** exact-exclusion credit comes from RECORDS. No caller-supplied
  integer exists any more, so no integer can waive a real overlap.
* **AUD-EC-008** the gate binds a digest of every input and is byte-deterministic.
"""
from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from PIL import Image

from ica26.datasets import manifest as M
from ica26.leakage.gate import (
    GATE_INPUT_NAMES,
    GateInputs,
    LeakageGate,
    LeakageGateError,
    PairIdentity,
    authenticate_exact_exclusions,
    authenticate_near_review,
    build_authoritative_pairs,
    compute_gate,
    compute_input_digests,
    require_valid_gate,
    validate_gate,
)

# --------------------------------------------------------------------------- #
# Fixtures: synthetic datasets, manifests, pair table, review + exclusion files
# --------------------------------------------------------------------------- #
PAIR_TABLE_COLUMNS = [
    "canonical_pair_id", "pair_schema",
    "training_relpath", "evaluation_relpath", "training_class", "evaluation_class",
    "training_sha256", "evaluation_sha256",
    "training_phash", "evaluation_phash", "hamming_distance", "classification",
    "review_status", "proposed_disposition", "notes",
]
REVIEW_COLUMNS = [
    "canonical_pair_id", "pair_id",
    "training_dataset", "training_relative_path", "training_class",
    "training_sha256", "evaluation_dataset", "evaluation_relative_path",
    "evaluation_class", "evaluation_sha256", "phash_distance", "contact_sheet",
    "human_decision", "decision_reason", "reviewer", "reviewed_at", "final_disposition",
]
REVIEWED_EXCL_COLUMNS = [
    "pair_id", "match_type", "training_relative_path", "evaluation_relative_path",
    "phash_distance", "human_decision", "exclusion_reason", "reviewer", "reviewed_at",
    "source_review_file",
]
EXACT_EXCL_COLUMNS = [
    "canonical_pair_id", "pair_schema",
    "evaluation_dataset", "evaluation_relpath", "evaluation_class", "evaluation_sha256",
    "training_dataset", "training_relpath", "training_class", "training_sha256",
    "hamming_distance", "reason", "provenance", "action", "status",
]


def _img(path, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(path)


def _write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})
    return path


def make_dataset(tmp_path, name, specs):
    """specs: list of (split, cls, seed). Returns (root, manifest_path)."""
    root = tmp_path / name
    for split, cls, seed in specs:
        _img(root / split / cls / f"{seed}.png", seed)
    df = M.build_split_class_manifest(
        root=root, dataset=name, source_url="u", split_dirs=["train", "test"],
        acquired_at_utc="2026-01-01T00:00:00+00:00",
    )
    man = tmp_path / f"{name}_manifest.csv"
    M.write_manifest(df, man)
    return root, man


class Env:
    """A complete, self-consistent gate environment under tmp_path."""

    # the one exact pair present when overlap=True
    T_REL, E_REL = "train/c/1.png", "test/c/1.png"

    def __init__(self, tmp_path, overlap=False):
        self.tmp = tmp_path
        self.tr_root, self.tr_man = make_dataset(
            tmp_path, "train_ds", [("train", "c", 1), ("train", "c", 2)])
        ev_specs = [("test", "c", 1 if overlap else 30), ("test", "c", 40)]
        self.ev_root, self.ev_man = make_dataset(tmp_path, "eval_ds", ev_specs)
        self.overlap = overlap
        self.pair_table = tmp_path / "pairs.csv"
        self.near_review = tmp_path / "near_review.csv"
        self.reviewed_excl = tmp_path / "reviewed_excl.csv"
        self.exact_excl = tmp_path / "exact_excl.csv"
        self.gate_path = tmp_path / "gate.json"
        self.write_pair_table()
        _write_csv(self.near_review, REVIEW_COLUMNS, [])
        _write_csv(self.reviewed_excl, REVIEWED_EXCL_COLUMNS, [])
        _write_csv(self.exact_excl, EXACT_EXCL_COLUMNS, [])

    def write_pair_table(self, rows=None):
        if rows is None:
            rows = ([{"training_relpath": self.T_REL, "evaluation_relpath": self.E_REL,
                      "training_class": "c", "evaluation_class": "c",
                      "hamming_distance": "0", "classification": "exact"}]
                    if self.overlap else [])
        _write_csv(self.pair_table, PAIR_TABLE_COLUMNS, rows)

    def _sha(self, manifest, relpath):
        import csv as _csv
        with open(manifest, newline="", encoding="utf-8") as fh:
            for r in _csv.DictReader(fh):
                if r["relpath"] == relpath:
                    return r["sha256"]
        return ""

    def exact_identity(self):
        from ica26.leakage.gate import PairIdentity
        return PairIdentity(
            training_dataset="train_ds", training_relpath=self.T_REL, training_class="c",
            training_sha256=self._sha(self.tr_man, self.T_REL),
            evaluation_dataset="eval_ds", evaluation_relpath=self.E_REL,
            evaluation_class="c", evaluation_sha256=self._sha(self.ev_man, self.E_REL),
            phash_distance=0, classification="exact")

    def write_exact_exclusion(self, **over):
        ident = self.exact_identity()
        row = {"canonical_pair_id": ident.canonical_pair_id,
               "pair_schema": "ica26.leakage.pair/1",
               "evaluation_dataset": "eval_ds", "evaluation_relpath": self.E_REL,
               "evaluation_class": "c", "evaluation_sha256": ident.evaluation_sha256,
               "training_dataset": "train_ds",
               "training_relpath": self.T_REL, "training_class": "c",
               "training_sha256": ident.training_sha256,
               "hamming_distance": "0", "reason": "exact duplicate",
               "provenance": "test", "action": "propose_exclude_from_evaluation",
               "status": "proposed"}
        row.update(over)
        _write_csv(self.exact_excl, EXACT_EXCL_COLUMNS, [row])

    @property
    def inputs(self) -> GateInputs:
        return GateInputs(
            training_manifest=self.tr_man, evaluation_manifest=self.ev_man,
            pair_table=self.pair_table, near_review=self.near_review,
            reviewed_exclusions=self.reviewed_excl, exact_exclusions=self.exact_excl,
        )

    def compute(self):
        gate, _ = compute_gate(
            training_manifest=self.tr_man, training_root=self.tr_root,
            training_dataset="train_ds",
            evaluation_manifest=self.ev_man, evaluation_root=self.ev_root,
            evaluation_dataset="eval_ds",
            pair_table=self.pair_table, near_review=self.near_review,
            reviewed_exclusions=self.reviewed_excl, exact_exclusions=self.exact_excl,
            threshold=6,
        )
        return gate


@pytest.fixture
def clean_env(tmp_path):
    return Env(tmp_path, overlap=False)


@pytest.fixture
def overlap_env(tmp_path):
    return Env(tmp_path, overlap=True)


# --------------------------------------------------------------------------- #
# Baseline fail-closed behaviour
# --------------------------------------------------------------------------- #
def test_clean_environment_passes(clean_env):
    gate = clean_env.compute()
    assert gate.status == "pass"
    assert gate.authorization_violations == []
    assert validate_gate(gate, clean_env.inputs).ok
    gate.write(clean_env.gate_path)
    assert require_valid_gate(clean_env.gate_path, clean_env.inputs).status == "pass"


def test_gate_absent_blocks(clean_env):
    with pytest.raises(LeakageGateError):
        require_valid_gate(clean_env.tmp / "nope.json", clean_env.inputs)


def test_incomplete_when_image_unhashable(tmp_path):
    env = Env(tmp_path, overlap=False)
    (env.tr_root / "train" / "c" / "broken.png").write_bytes(b"not an image at all")
    df = M.build_split_class_manifest(
        root=env.tr_root, dataset="train_ds", source_url="u",
        split_dirs=["train", "test"], acquired_at_utc="2026-01-01T00:00:00+00:00")
    M.write_manifest(df, env.tr_man)
    gate = env.compute()
    assert gate.status == "incomplete"
    assert not validate_gate(gate, env.inputs).ok


def test_dev_override_bypasses_with_warning(clean_env, capsys):
    assert require_valid_gate(clean_env.tmp / "absent.json", clean_env.inputs,
                              allow_missing_leakage_gate=True) is None
    assert "DEV-ONLY OVERRIDE" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# AUD-EC-002 — exact exclusions come from records, never an integer
# --------------------------------------------------------------------------- #
def test_no_integer_parameter_can_waive_an_exact_pair():
    """The forged-count attack is impossible: the parameter no longer exists."""
    import inspect

    params = inspect.signature(compute_gate).parameters
    assert "excluded_pair_count" not in params
    assert "excluded_pairs" not in params


def test_detected_exact_pair_without_record_fails(overlap_env):
    gate = overlap_env.compute()
    assert gate.exact_duplicate_count == 1
    assert gate.exact_excluded_count == 0
    assert gate.unresolved_pair_count == 1
    assert gate.status == "fail"
    assert any("no exclusion record" in v for v in gate.authorization_violations)


def test_detected_exact_pair_with_valid_record_passes(overlap_env):
    overlap_env.write_exact_exclusion()
    gate = overlap_env.compute()
    assert gate.exact_duplicate_count == 1
    assert gate.exact_excluded_count == 1
    assert gate.unresolved_pair_count == 0
    assert gate.authorization_violations == []
    assert gate.status == "pass"


@pytest.mark.parametrize("forged", [1, 999])
def test_forged_count_cannot_substitute_for_a_record(overlap_env, forged):
    """Historic attack: `--excluded-pairs 1` / `999` cleared a true overlap."""
    gate = overlap_env.compute()
    assert gate.status == "fail"
    # Even hand-forging the counts into the artifact cannot make it validate,
    # because the recorded violations survive.
    gate.exact_excluded_count = forged
    gate.unresolved_pair_count = 0
    gate.status = "pass"
    assert not validate_gate(gate, overlap_env.inputs).ok


def test_duplicate_exact_exclusion_rejected(overlap_env):
    row = {"evaluation_dataset": "eval_ds", "evaluation_relpath": overlap_env.E_REL,
           "evaluation_class": "c", "training_dataset": "train_ds",
           "training_relpath": overlap_env.T_REL, "training_class": "c",
           "hamming_distance": "0"}
    _write_csv(overlap_env.exact_excl, EXACT_EXCL_COLUMNS, [row, row])
    gate = overlap_env.compute()
    assert gate.status == "fail"
    assert any("duplicate exclusion" in v for v in gate.authorization_violations)


def test_unknown_exact_exclusion_rejected(overlap_env):
    overlap_env.write_exact_exclusion(training_relpath="train/c/999.png")
    gate = overlap_env.compute()
    assert gate.status == "fail"
    assert any("does not correspond to any detected exact pair" in v
               for v in gate.authorization_violations)


def test_exact_exclusion_identity_mismatch_rejected(overlap_env):
    overlap_env.write_exact_exclusion(training_class="WRONG")
    gate = overlap_env.compute()
    assert gate.status == "fail"
    assert any("training_class is 'WRONG'" in v for v in gate.authorization_violations)


def test_surplus_exclusion_on_clean_environment_rejected(clean_env):
    _write_csv(clean_env.exact_excl, EXACT_EXCL_COLUMNS, [{
        "evaluation_dataset": "eval_ds", "evaluation_relpath": "test/c/40.png",
        "evaluation_class": "c", "training_dataset": "train_ds",
        "training_relpath": "train/c/2.png", "training_class": "c",
        "hamming_distance": "0"}])
    gate = clean_env.compute()
    assert gate.status == "fail"
    assert gate.authorization_violations


# --------------------------------------------------------------------------- #
# AUD-EC-001 — near-review identity authentication
# --------------------------------------------------------------------------- #
NEAR = PairIdentity(
    training_dataset="PlantVillage", training_relpath="t/a.jpg", training_class="A",
    training_sha256="a" * 64,
    evaluation_dataset="PlantDoc", evaluation_relpath="e/b.jpg", evaluation_class="B",
    evaluation_sha256="b" * 64,
    phash_distance=6, classification="near",
)
AUTHORITATIVE = {NEAR.key: NEAR}


def _review_row(**over):
    row = {
        "canonical_pair_id": NEAR.canonical_pair_id,
        "pair_id": "ndp-01",
        "training_dataset": NEAR.training_dataset,
        "training_relative_path": NEAR.training_relpath,
        "training_class": NEAR.training_class,
        "training_sha256": NEAR.training_sha256,
        "evaluation_dataset": NEAR.evaluation_dataset,
        "evaluation_relative_path": NEAR.evaluation_relpath,
        "evaluation_class": NEAR.evaluation_class,
        "evaluation_sha256": NEAR.evaluation_sha256,
        "phash_distance": str(NEAR.phash_distance),
        "contact_sheet": "reports/sheet.png",
        "human_decision": "clearly_different",
        "decision_reason": "distinct source images",
        "reviewer": "human_reviewer_1",
        "reviewed_at": "2026-08-02T21:10:00+05:00",
        "final_disposition": "keep",
    }
    row.update(over)
    return row


def _auth(tmp_path, rows, exclusions=None, authoritative=None):
    rp = _write_csv(tmp_path / "r.csv", REVIEW_COLUMNS, rows)
    xp = _write_csv(tmp_path / "x.csv", REVIEWED_EXCL_COLUMNS, exclusions or [])
    return authenticate_near_review(
        rp, AUTHORITATIVE if authoritative is None else authoritative, xp)


def test_valid_review_row_resolves(tmp_path):
    a = _auth(tmp_path, [_review_row()])
    assert a.ok and a.resolved == 1 and a.kept == 1 and a.unresolved == 0


@pytest.mark.parametrize("field,value", [
    ("training_sha256", "c" * 64),
    ("evaluation_sha256", "d" * 64),
    ("phash_distance", "999"),
    ("training_class", "WRONG"),
    ("evaluation_class", "WRONG"),
    ("training_dataset", "WRONG"),
    ("evaluation_dataset", "WRONG"),
])
def test_identity_mutation_is_a_violation(tmp_path, field, value):
    """Every immutable identity field is authenticated, not just the paths."""
    a = _auth(tmp_path, [_review_row(**{field: value})])
    assert not a.ok
    assert any("identity mismatch" in v for v in a.violations)
    assert a.resolved == 0


def test_changed_path_is_an_unknown_pair(tmp_path):
    a = _auth(tmp_path, [_review_row(training_relative_path="t/other.jpg")])
    assert not a.ok
    assert any("does not correspond to any authoritative near pair" in v for v in a.violations)


def test_duplicate_pair_id_is_a_violation(tmp_path):
    a = _auth(tmp_path, [_review_row(), _review_row(training_relative_path="t/z.jpg")])
    assert not a.ok
    assert any("duplicate pair_id" in v for v in a.violations)


def test_duplicate_identity_is_a_violation(tmp_path):
    """A second row for the same pair under a different display label."""
    a = _auth(tmp_path, [_review_row(), _review_row(pair_id="ndp-02")])
    assert not a.ok
    assert any("duplicate canonical_pair_id" in v for v in a.violations)
    assert a.resolved == 1


def test_unknown_pair_id_row_is_a_violation(tmp_path):
    a = _auth(tmp_path, [_review_row(), _review_row(
        pair_id="ndp-99", canonical_pair_id="near-ffffffffffffffff",
        training_relative_path="t/ghost.jpg",
        evaluation_relative_path="e/ghost.jpg")])
    assert not a.ok
    assert any("unknown or surplus review row" in v for v in a.violations)


def test_missing_authoritative_pair_is_a_violation(tmp_path):
    """Deleting an authoritative pair must not quietly drive unresolved to zero."""
    two = dict(AUTHORITATIVE)
    other = PairIdentity(
        training_dataset="PlantVillage", training_relpath="t/c.jpg", training_class="A",
        training_sha256="e" * 64, evaluation_dataset="PlantDoc",
        evaluation_relpath="e/d.jpg", evaluation_class="B", evaluation_sha256="f" * 64,
        phash_distance=5, classification="near")
    two[other.key] = other
    # `other` sorts first (distance 5), so NEAR's authoritative display id is ndp-02.
    a = _auth(tmp_path, [_review_row(pair_id="ndp-02")], authoritative=two)
    assert not a.ok
    assert any("has no review row" in v for v in a.violations)
    assert a.unresolved == 1


def test_blank_pair_id_is_a_violation(tmp_path):
    a = _auth(tmp_path, [_review_row(pair_id="")])
    assert not a.ok
    assert any("blank pair_id" in v for v in a.violations)


@pytest.mark.parametrize("over", [
    {"human_decision": "", "final_disposition": ""},
    {"human_decision": "uncertain"},
    {"final_disposition": "needs_secondary_review"},
])
def test_non_terminal_states_resolve_nothing_without_violation(tmp_path, over):
    a = _auth(tmp_path, [_review_row(**over)])
    assert a.ok            # pending/deferred is legitimate, just not resolved
    assert a.resolved == 0
    assert a.unresolved == 1


@pytest.mark.parametrize("over", [
    {"human_decision": "looks_fine"},
    {"final_disposition": "probably_ok"},
])
def test_unsupported_vocabulary_is_a_violation(tmp_path, over):
    a = _auth(tmp_path, [_review_row(**over)])
    assert not a.ok
    assert a.resolved == 0


@pytest.mark.parametrize("field", ["reviewer", "reviewed_at", "decision_reason"])
def test_terminal_decision_needs_attribution(tmp_path, field):
    a = _auth(tmp_path, [_review_row(**{field: ""})])
    assert not a.ok
    assert any("without attribution" in v for v in a.violations)


def test_exclude_without_propagation_is_a_violation(tmp_path):
    a = _auth(tmp_path, [_review_row(human_decision="same_source_image",
                                     final_disposition="exclude_evaluation")])
    assert not a.ok
    assert any("expected exactly 1" in v for v in a.violations)
    assert a.resolved == 0


def test_exclude_with_propagation_resolves(tmp_path):
    a = _auth(tmp_path,
              [_review_row(human_decision="same_source_image",
                           final_disposition="exclude_evaluation")],
              exclusions=[{"pair_id": "ndp-01",
                           "training_relative_path": NEAR.training_relpath,
                           "evaluation_relative_path": NEAR.evaluation_relpath,
                           "phash_distance": "6"}])
    assert a.ok and a.resolved == 1 and a.excluded == 1


def test_reviewed_exclusion_without_human_exclude_is_a_violation(tmp_path):
    """A bogus exclusion row must not pass merely because the pair is decided."""
    a = _auth(tmp_path, [_review_row()],  # decided KEEP
              exclusions=[{"pair_id": "ndp-01",
                           "training_relative_path": NEAR.training_relpath,
                           "evaluation_relative_path": NEAR.evaluation_relpath,
                           "phash_distance": "6"}])
    assert not a.ok
    assert any("not decided exclude_evaluation" in v for v in a.violations)


def test_exclusion_pair_id_mismatch_is_a_violation(tmp_path):
    a = _auth(tmp_path,
              [_review_row(human_decision="same_source_image",
                           final_disposition="exclude_evaluation")],
              exclusions=[{"pair_id": "ndp-77",
                           "training_relative_path": NEAR.training_relpath,
                           "evaluation_relative_path": NEAR.evaluation_relpath,
                           "phash_distance": "6"}])
    assert not a.ok
    assert any("pair_id" in v and "does not match" in v for v in a.violations)


def test_orphan_reviewed_exclusion_is_a_violation(tmp_path):
    a = _auth(tmp_path, [_review_row()],
              exclusions=[{"pair_id": "ndp-50",
                           "training_relative_path": "t/ghost.jpg",
                           "evaluation_relative_path": "e/ghost.jpg",
                           "phash_distance": "6"}])
    assert not a.ok
    assert any("does not correspond to any review row" in v for v in a.violations)


def test_missing_review_file_is_a_violation(tmp_path):
    a = authenticate_near_review(tmp_path / "absent.csv", AUTHORITATIVE, None)
    assert not a.ok
    assert a.resolved == 0 and a.unresolved == 1


# --------------------------------------------------------------------------- #
# Authoritative pair table reconciliation
# --------------------------------------------------------------------------- #
def test_pair_table_endpoint_absent_from_manifest_is_a_violation(clean_env):
    clean_env.write_pair_table([{
        "training_relpath": "train/c/ghost.png", "evaluation_relpath": "test/c/40.png",
        "training_class": "c", "evaluation_class": "c",
        "hamming_distance": "3", "classification": "near"}])
    pairs, violations = build_authoritative_pairs(
        clean_env.pair_table, clean_env.tr_man, clean_env.ev_man,
        training_dataset="train_ds", evaluation_dataset="eval_ds")
    assert pairs == {}
    assert any("absent from the training manifest" in v for v in violations)


def test_pair_table_disagreeing_with_fresh_computation_is_incomplete(clean_env):
    """A stale pair table means we would authenticate against the wrong identities."""
    clean_env.write_pair_table([{
        "training_relpath": "train/c/1.png", "evaluation_relpath": "test/c/40.png",
        "training_class": "c", "evaluation_class": "c",
        "hamming_distance": "3", "classification": "near"}])
    gate = clean_env.compute()
    assert gate.status == "incomplete"
    assert any("which fresh detection did not produce" in v
               for v in gate.authorization_violations)


# --------------------------------------------------------------------------- #
# AUD-EC-008 — input binding and byte-determinism
# --------------------------------------------------------------------------- #
def test_gate_binds_every_input(clean_env):
    gate = clean_env.compute()
    assert set(gate.input_digests) == set(GATE_INPUT_NAMES)


@pytest.mark.parametrize("name", [n for n in GATE_INPUT_NAMES if n != "leakage_config"])
def test_mutating_any_bound_input_makes_the_gate_stale(clean_env, name):
    gate = clean_env.compute()
    assert validate_gate(gate, clean_env.inputs).ok
    target = clean_env.inputs.paths()[name]
    target.write_text(target.read_text() + "\n# mutated after generation\n")
    res = validate_gate(gate, clean_env.inputs)
    assert not res.ok
    assert any("stale gate" in i.message for i in res.errors)


def test_config_change_makes_the_gate_stale(clean_env):
    gate = clean_env.compute()
    gate.threshold = 5  # a different leakage configuration
    assert not validate_gate(gate, clean_env.inputs).ok


def test_old_schema_gate_is_rejected(clean_env):
    gate = clean_env.compute()
    gate.schema_version = "1.1"
    res = validate_gate(gate, clean_env.inputs)
    assert not res.ok
    assert any("unsupported gate schema" in i.message for i in res.errors)


def test_gate_without_bindings_is_rejected(clean_env):
    gate = clean_env.compute()
    gate.input_digests = {}
    assert not validate_gate(gate, clean_env.inputs).ok


def test_recorded_violations_block_validation(clean_env):
    gate = clean_env.compute()
    gate.authorization_violations = ["synthetic violation"]
    res = validate_gate(gate, clean_env.inputs)
    assert not res.ok
    assert any("authorization violation" in i.message for i in res.errors)


def test_two_identical_builds_are_byte_identical(clean_env, tmp_path):
    a, b = clean_env.compute(), clean_env.compute()
    pa, pb = tmp_path / "a.json", tmp_path / "b.json"
    a.write(pa)
    b.write(pb)
    assert pa.read_bytes() == pb.read_bytes()
    assert "generated_at" not in json.loads(pa.read_text())


def test_gate_carries_no_wall_clock_field(clean_env):
    assert "generated_at" not in clean_env.compute().to_dict()


def test_digests_are_sorted_for_stable_serialization(clean_env):
    d = compute_input_digests(clean_env.inputs, threshold=6,
                              training_dataset="train_ds", evaluation_dataset="eval_ds")
    assert list(d) == sorted(d)


def test_from_dict_applies_defaults_for_absent_optional_fields():
    gate = LeakageGate.from_dict({
        "schema_version": "2.0", "training_dataset": "t", "evaluation_dataset": "e",
        "phash_algorithm": "p", "threshold": 6, "exact_duplicate_count": 0,
        "exact_excluded_count": 0, "near_duplicate_count": 0, "near_resolved_count": 0,
        "near_kept_count": 0, "near_excluded_count": 0, "unresolved_pair_count": 0,
        "status": "pass",
    })
    assert gate.authorization_violations == [] and gate.input_digests == {}


# --------------------------------------------------------------------------- #
# Exact-exclusion authenticator, in isolation
# --------------------------------------------------------------------------- #
EXACT = PairIdentity(
    training_dataset="PlantVillage", training_relpath="t/x.jpg", training_class="A",
    training_sha256="1" * 64, evaluation_dataset="PlantDoc", evaluation_relpath="e/y.jpg",
    evaluation_class="B", evaluation_sha256="2" * 64, phash_distance=0,
    classification="exact")


def test_exact_authenticator_requires_one_record_per_pair(tmp_path):
    p = _write_csv(tmp_path / "x.csv", EXACT_EXCL_COLUMNS, [])
    a = authenticate_exact_exclusions(p, {EXACT.key: EXACT})
    assert not a.ok and a.detected == 1 and a.excluded == 0


def test_exact_authenticator_accepts_a_matching_record(tmp_path):
    p = _write_csv(tmp_path / "x.csv", EXACT_EXCL_COLUMNS, [{
        "canonical_pair_id": EXACT.canonical_pair_id,
        "training_dataset": "PlantVillage", "training_relpath": "t/x.jpg",
        "training_class": "A", "training_sha256": EXACT.training_sha256,
        "evaluation_dataset": "PlantDoc", "evaluation_relpath": "e/y.jpg",
        "evaluation_class": "B", "evaluation_sha256": EXACT.evaluation_sha256,
        "hamming_distance": "0"}])
    a = authenticate_exact_exclusions(p, {EXACT.key: EXACT})
    assert a.ok and a.excluded == 1


def test_exact_authenticator_rejects_a_record_without_canonical_id(tmp_path):
    p = _write_csv(tmp_path / "x.csv", EXACT_EXCL_COLUMNS, [{
        "training_dataset": "PlantVillage", "training_relpath": "t/x.jpg",
        "training_class": "A", "training_sha256": EXACT.training_sha256,
        "evaluation_dataset": "PlantDoc", "evaluation_relpath": "e/y.jpg",
        "evaluation_class": "B", "evaluation_sha256": EXACT.evaluation_sha256,
        "hamming_distance": "0"}])
    a = authenticate_exact_exclusions(p, {EXACT.key: EXACT})
    assert not a.ok
    assert any("canonical_pair_id" in v for v in a.violations)


def test_exact_authenticator_with_no_pairs_and_no_records_is_clean(tmp_path):
    p = _write_csv(tmp_path / "x.csv", EXACT_EXCL_COLUMNS, [])
    a = authenticate_exact_exclusions(p, {})
    assert a.ok and a.detected == 0 and a.excluded == 0
