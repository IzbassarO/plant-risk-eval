"""ICA 2026 paper experiment pipeline: lock, mapping, splitting, metrics.

None of these tests need image pixels. They run in a fresh clone, because the
artifacts they assert on -- the experiment lock, the shared-class mapping -- are
committed, and everything else is synthetic.

The emphasis is adversarial: a lock that only passes when nothing has changed is
worthless unless it also *fails* when something has. Each mutation below is
applied to a throwaway copy of the repository's manifests.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from ica26.experiments import calibration as calib
from ica26.experiments import data as dmod
from ica26.experiments import lock as L
from ica26.experiments import metrics as mmod
from ica26.experiments.mapping import MAPPING_CSV, load_mapping

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
LOCK_INPUT_FILES = [
    "data/manifests",
    "data/exclusions",
    "data/mapping",
    "configs",
    "reports",
]


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory, repo_root):
    """A throwaway copy of every input the lock reads, safe to mutate."""
    dest = tmp_path_factory.mktemp("lock_sandbox")
    for rel in LOCK_INPUT_FILES:
        src = repo_root / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.png", "near_duplicate_contact_sheets"))
    # No .git copy: validation reads files and manifests, never the repository.
    return dest


# --------------------------------------------------------------------------- #
# The lock accepts the real corpus
# --------------------------------------------------------------------------- #
def test_the_lock_validates_against_the_committed_corpus(repo_root):
    report = L.validate(repo_root)
    assert report["ok"], report["violations"]


def test_the_lock_is_not_a_governance_freeze(repo_root):
    """The lock must never present itself as the formal governance freeze."""
    payload = L.load_lock(repo_root)
    assert payload["is_formal_governance_freeze"] is False
    assert payload["formal_governance_freeze_status"] == "pending"
    assert payload["assertions"]["formal_governance_freeze_still_pending"] is True
    assert payload["lock_kind"] == "scientific_experiment_lock"


def test_the_lock_carries_no_human_audit_signature(repo_root):
    """No field may imply a human audit sign-off or freeze approval."""
    text = json.dumps(L.load_lock(repo_root)).lower()
    for forbidden in ("audit_signoff", "audit_sign_off", "freeze_approval",
                      "independent_audit_signature", "approved_by_auditor"):
        assert forbidden not in text, f"lock contains {forbidden!r}"


def test_the_lock_owner_is_pseudonymous(repo_root):
    payload = L.load_lock(repo_root)
    assert payload["dataset_owner"] == "dataset_owner_1"
    assert payload["owner_authorization"]["authorized_by"] == "dataset_owner_1"


def test_the_lock_records_the_verified_counts(repo_root):
    exp = L.load_lock(repo_root)["expected_counts"]
    assert exp["plantvillage"] == {"total": 54305, "train": 43596, "test": 10709, "classes": 38}
    assert exp["plantdoc"]["source"] == 2578
    assert exp["plantdoc"]["previous_effective"] == 2564
    assert exp["plantdoc"]["core"] == 2561
    assert exp["plantdoc"]["train"] == 2336
    assert exp["plantdoc"]["test"] == 225
    assert exp["plantdoc"]["classes"] == 28
    assert exp["plantdoc"]["non_reviewed_unchanged"] == 2554
    assert exp["plantdoc"]["retained_reviewed"] == 7
    assert exp["plantdoc"]["excluded_reviewed"] == 17
    for population in ("acquired", "core"):
        assert exp["leakage"][population] == {"exact": 0, "near": 16, "unresolved": 0}


# --------------------------------------------------------------------------- #
# The lock REJECTS a changed corpus. Without these it proves nothing.
# --------------------------------------------------------------------------- #
CORE = "data/manifests/plantdoc_core_effective_manifest.csv"


def _mutate(sandbox, relpath, fn):
    """Apply fn to a CSV in the sandbox, then restore it afterwards."""
    path = sandbox / relpath
    original = path.read_bytes()
    df = pd.read_csv(path)
    fn(df).to_csv(path, index=False)
    return original


def test_lock_rejects_a_dropped_record(sandbox):
    original = _mutate(sandbox, CORE, lambda df: df.iloc[:-1])
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert any("record count 2560" in v for v in report["violations"])
    finally:
        (sandbox / CORE).write_bytes(original)


def test_lock_rejects_a_relabelled_record(sandbox):
    def relabel(df):
        df = df.copy()
        df.loc[0, "class_label"] = df.loc[len(df) - 1, "class_label"]
        return df

    original = _mutate(sandbox, CORE, relabel)
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert any("identity assignment digest differs" in v for v in report["violations"])
    finally:
        (sandbox / CORE).write_bytes(original)


def test_lock_rejects_a_record_moved_between_splits(sandbox):
    def move(df):
        df = df.copy()
        idx = df.index[df["split"] == "train"][0]
        df.loc[idx, "split"] = "test"
        return df

    original = _mutate(sandbox, CORE, move)
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert any("split counts" in v for v in report["violations"])
    finally:
        (sandbox / CORE).write_bytes(original)


def test_lock_rejects_changed_image_content(sandbox):
    """A changed content digest is caught even when counts and labels hold."""
    def tamper(df):
        df = df.copy()
        df.loc[0, "sha256"] = "0" * 64
        return df

    original = _mutate(sandbox, CORE, tamper)
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert any("identity assignment digest differs" in v for v in report["violations"])
    finally:
        (sandbox / CORE).write_bytes(original)


def test_lock_tolerates_pure_row_reordering(sandbox):
    """Row order is presentation, not content: reordering must still validate."""
    original = _mutate(sandbox, CORE, lambda df: df.iloc[::-1])
    try:
        report = L.validate(sandbox)
        digest_problems = [v for v in report["violations"] if "identity assignment digest" in v]
        assert digest_problems == [], digest_problems
    finally:
        (sandbox / CORE).write_bytes(original)


def test_lock_rejects_a_missing_bound_artifact(sandbox):
    target = sandbox / "data/exclusions/cross_dataset_exact_exclusions.csv"
    original = target.read_bytes()
    target.unlink()
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert any("missing from disk" in v for v in report["violations"])
    finally:
        target.write_bytes(original)


def test_require_valid_lock_raises_on_violation(sandbox):
    original = _mutate(sandbox, CORE, lambda df: df.iloc[:-2])
    try:
        with pytest.raises(L.LockValidationError):
            L.require_valid_lock(sandbox)
    finally:
        (sandbox / CORE).write_bytes(original)


def test_validate_reports_every_violation_not_just_the_first(sandbox):
    original_core = (sandbox / CORE).read_bytes()
    target = sandbox / "data/exclusions/cross_dataset_exact_exclusions.csv"
    original_excl = target.read_bytes()
    pd.read_csv(sandbox / CORE).iloc[:-1].to_csv(sandbox / CORE, index=False)
    target.unlink()
    try:
        report = L.validate(sandbox)
        assert not report["ok"]
        assert len(report["violations"]) >= 2
    finally:
        (sandbox / CORE).write_bytes(original_core)
        target.write_bytes(original_excl)


# --------------------------------------------------------------------------- #
# The cross-domain mapping
# --------------------------------------------------------------------------- #
def test_mapping_has_21_shared_classes_from_two_evidence_sources(repo_root):
    mapping = load_mapping(repo_root)
    assert len(mapping.canonical_classes) == 21
    sources = {r["evidence_source"] for r in mapping.included}
    assert sources == {"deterministic_normalizer_key_collision",
                       "human_approved_healthy_policy"}
    counts = {s: sum(1 for r in mapping.included if r["evidence_source"] == s) for s in sources}
    assert counts["deterministic_normalizer_key_collision"] == 11
    assert counts["human_approved_healthy_policy"] == 10


def test_mapping_excludes_both_arthropod_pest_classes(repo_root):
    rows = load_mapping(repo_root).rows
    excluded = {(r["plantvillage_label"] or r["plantdoc_label"]): r["exclusion_reason"]
                for r in rows if r["inclusion_status"] == "excluded"}
    assert excluded["Tomato two spotted spider mites leaf"] == "arthropod_pest_out_of_disease_scope"
    assert excluded["Tomato___Spider_mites Two-spotted_spider_mite"] == "arthropod_pest_out_of_disease_scope"


def test_every_excluded_row_states_a_reason(repo_root):
    for r in load_mapping(repo_root).rows:
        if r["inclusion_status"] == "excluded":
            assert r["exclusion_reason"].strip(), r


def test_mapping_covers_every_class_in_both_label_spaces(repo_root):
    """No class may be silently absent: each appears included or excluded."""
    rows = load_mapping(repo_root).rows
    pv_seen = {r["plantvillage_label"] for r in rows if r["plantvillage_label"]}
    pd_seen = {r["plantdoc_label"] for r in rows if r["plantdoc_label"]}
    pv_all = set(pd.read_csv(repo_root / "data/manifests/plantvillage_manifest.csv")["class_label"])
    pd_all = set(pd.read_csv(repo_root / CORE)["class_label"])
    assert pv_seen == pv_all
    assert pd_seen == pd_all


def test_no_plantdoc_class_maps_to_two_canonical_classes(repo_root):
    mapping = load_mapping(repo_root)
    seen: dict[str, str] = {}
    for r in mapping.included:
        label = r["plantdoc_label"]
        assert seen.setdefault(label, r["canonical_class_id"]) == r["canonical_class_id"]


def test_mapping_rebuilds_byte_identically(repo_root):
    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts/ica26_build_cross_domain_mapping.py"), "--check"],
        cwd=str(repo_root), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_mapping_loader_rejects_an_included_row_without_evidence(repo_root, tmp_path):
    import csv

    with (repo_root / MAPPING_CSV).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for r in rows:
        if r["inclusion_status"] == "included":
            r["evidence_source"] = ""
            break

    broken = tmp_path / MAPPING_CSV
    broken.parent.mkdir(parents=True, exist_ok=True)
    with broken.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="evidence_source"):
        load_mapping(tmp_path)


def test_mapping_loader_rejects_an_excluded_row_without_a_reason(repo_root, tmp_path):
    import csv

    with (repo_root / MAPPING_CSV).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    for r in rows:
        if r["inclusion_status"] == "excluded":
            r["exclusion_reason"] = ""
            break

    broken = tmp_path / MAPPING_CSV
    broken.parent.mkdir(parents=True, exist_ok=True)
    with broken.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="without a reason"):
        load_mapping(tmp_path)


# --------------------------------------------------------------------------- #
# Validation splitting
# --------------------------------------------------------------------------- #
def _frame(n_classes=4, per_class=20, groups_per_class=5):
    rows = []
    for c in range(n_classes):
        for i in range(per_class):
            rows.append({
                "relpath": f"train/c{c}/img{i}.jpg",
                "split": "train",
                "class_label": f"class_{c}",
                "sha256": f"{c:02d}{i:062d}",
                "leaf_id": f"leaf_{c}_{i % groups_per_class}",
            })
    return pd.DataFrame(rows)


def test_grouped_split_never_puts_a_group_on_both_sides():
    train, val = dmod.grouped_validation_split(_frame(), 0.2, seed=42, group_column="leaf_id")
    assert set(train["leaf_id"]) & set(val["leaf_id"]) == set()
    assert len(train) + len(val) == 80


def test_grouped_split_is_deterministic():
    a = dmod.grouped_validation_split(_frame(), 0.2, 42, "leaf_id")
    b = dmod.grouped_validation_split(_frame(), 0.2, 42, "leaf_id")
    assert list(a[1]["relpath"]) == list(b[1]["relpath"])


def test_grouped_split_is_insensitive_to_row_order():
    base = _frame()
    a = dmod.grouped_validation_split(base, 0.2, 42, "leaf_id")[1]
    b = dmod.grouped_validation_split(base.iloc[::-1].reset_index(drop=True), 0.2, 42, "leaf_id")[1]
    assert sorted(a["relpath"]) == sorted(b["relpath"])


def test_a_class_too_small_keeps_every_example_in_training():
    """PlantDoc Core's 2-image arthropod-pest class must not lose half its data.

    The tiny class sits alongside normal ones, as it does in the real corpus.
    """
    df = pd.concat([
        _frame(n_classes=3, per_class=20, groups_per_class=10),
        pd.DataFrame([
            {"relpath": f"train/tiny/img{i}.jpg", "split": "train",
             "class_label": "tiny_class", "sha256": f"ff{i:062d}", "leaf_id": f"tiny_{i}"}
            for i in range(2)
        ]),
    ], ignore_index=True)
    train, val = dmod.grouped_validation_split(df, 0.1, 42, group_column="leaf_id")
    assert "tiny_class" not in set(val["class_label"])
    assert (train["class_label"] == "tiny_class").sum() == 2


def test_an_all_tiny_corpus_refuses_rather_than_training_without_validation():
    """Model selection needs a validation set; an empty one must not pass silently."""
    df = _frame(n_classes=2, per_class=2, groups_per_class=2)
    with pytest.raises(ValueError, match="empty side"):
        dmod.grouped_validation_split(df, 0.1, 42, group_column=None)


def test_class_index_is_sorted_and_deterministic():
    idx = dmod.build_class_index(["zebra", "apple", "Mango"])
    assert idx == {"Mango": 0, "apple": 1, "zebra": 2}
    assert dmod.class_index_digest(idx) == dmod.class_index_digest(dict(reversed(list(idx.items()))))


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def test_zero_support_class_is_reported_not_averaged_in():
    """A class absent from y_true must not drag macro-F1 down as a hard 0.0."""
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 0, 1, 1])
    out = mmod.evaluate_classification(y_true, y_pred, ["a", "b", "c"])
    assert out["macro_f1"] == 1.0                      # over the supported space
    assert out["n_supported_classes"] == 2
    assert out["n_declared_classes"] == 3
    assert [z["class_name"] for z in out["zero_support_classes"]] == ["c"]
    assert out["full_label_space"]["macro_f1"] < 1.0   # the other view is still shown


def test_predictions_into_a_zero_support_class_are_counted():
    y_true = np.array([0, 0, 1, 1])
    y_pred = np.array([0, 2, 1, 2])
    out = mmod.evaluate_classification(y_true, y_pred, ["a", "b", "c"])
    assert out["predictions_into_zero_support_classes"] == 2


def test_perfect_confidence_gives_zero_calibration_error():
    probs = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]])
    y = np.array([0, 1, 0])
    cal = mmod.expected_calibration_error(y, probs, n_bins=10)
    assert cal["expected_calibration_error"] == pytest.approx(0.0, abs=1e-9)


def test_ece_matches_its_own_reliability_bins():
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(500, 5))
    probs = calib.softmax(logits)
    y = rng.integers(0, 5, size=500)
    cal = mmod.expected_calibration_error(y, probs, n_bins=15)
    n = len(y)
    recomputed = sum(
        (b["count"] / n) * abs(b["avg_confidence"] - b["accuracy"])
        for b in cal["bins"] if b["count"]
    )
    assert cal["expected_calibration_error"] == pytest.approx(recomputed, abs=1e-12)


def test_brier_score_of_a_perfect_prediction_is_zero():
    probs = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert mmod.brier_score(np.array([0, 1]), probs) == pytest.approx(0.0)


def test_selective_accuracy_at_full_coverage_equals_accuracy():
    rng = np.random.default_rng(1)
    probs = calib.softmax(rng.normal(size=(200, 4)))
    y = rng.integers(0, 4, size=200)
    curve = mmod.confidence_abstention_curve(y, probs)
    full = [p for p in curve["points"] if p["coverage"] == 1.0][0]
    assert full["selective_accuracy"] == pytest.approx(float((probs.argmax(1) == y).mean()))


# --------------------------------------------------------------------------- #
# Temperature scaling
# --------------------------------------------------------------------------- #
def test_temperature_scaling_never_changes_the_prediction():
    rng = np.random.default_rng(3)
    logits = rng.normal(size=(300, 6)) * 3
    before = calib.softmax(logits).argmax(1)
    for t in (0.5, 1.5, 4.0):
        assert (calib.apply_temperature(logits, t).argmax(1) == before).all()


def test_temperature_fit_reduces_validation_nll():
    rng = np.random.default_rng(4)
    y = rng.integers(0, 5, size=800)
    logits = rng.normal(size=(800, 5))
    logits[np.arange(800), y] += 2.0
    fit = calib.fit_temperature(logits * 4.0, y)   # deliberately over-confident
    assert fit["val_nll_after"] <= fit["val_nll_before"] + 1e-9
    assert fit["temperature"] > 0


def test_probabilities_sum_to_one():
    rng = np.random.default_rng(5)
    p = calib.apply_temperature(rng.normal(size=(50, 7)), 1.7)
    assert np.allclose(p.sum(axis=1), 1.0)
