"""Leakage-gate: fail-closed behaviour across all required states."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from ica26.datasets import manifest as M
from ica26.leakage.gate import (
    LeakageGate, LeakageGateError, compute_gate, require_valid_gate, validate_gate,
)


def _img(path, seed, corrupt=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        path.write_bytes(b"not an image at all")
        return
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(path)


def make_dataset(tmp_path, name, specs):
    """specs: list of (split, cls, seed, corrupt). Returns (root, manifest_path)."""
    root = tmp_path / name
    for split, cls, seed, corrupt in specs:
        _img(root / split / cls / f"{seed}.png", seed, corrupt)
    df = M.build_split_class_manifest(
        root=root, dataset=name, source_url="u", split_dirs=["train", "test"],
        acquired_at_utc="2026-01-01T00:00:00+00:00",
    )
    man = tmp_path / f"{name}_manifest.csv"
    M.write_manifest(df, man)
    return root, man


def _passing_gate(tmp_path):
    tr_root, tr_man = make_dataset(tmp_path, "train_ds", [("train", "c", 1, False), ("train", "c", 2, False)])
    ev_root, ev_man = make_dataset(tmp_path, "eval_ds", [("test", "c", 30, False), ("test", "c", 40, False)])
    gate, _ = compute_gate(
        training_manifest=tr_man, training_root=tr_root, training_dataset="train_ds",
        evaluation_manifest=ev_man, evaluation_root=ev_root, evaluation_dataset="eval_ds",
        threshold=6, generated_at="2026-01-01T00:00:00+00:00",
    )
    return gate, tr_man, ev_man, tr_root, ev_root


def test_valid_gate_authorises(tmp_path):
    gate, tr_man, ev_man, *_ = _passing_gate(tmp_path)
    assert gate.status == "pass"
    assert validate_gate(gate, tr_man, ev_man).ok
    gp = tmp_path / "gate.json"; gate.write(gp)
    assert require_valid_gate(gp, tr_man, ev_man).status == "pass"


def test_gate_absent_blocks(tmp_path):
    _, tr_man, ev_man, *_ = _passing_gate(tmp_path)
    with pytest.raises(LeakageGateError):
        require_valid_gate(tmp_path / "does_not_exist.json", tr_man, ev_man)


def test_stale_manifest_blocks(tmp_path):
    gate, tr_man, ev_man, *_ = _passing_gate(tmp_path)
    gp = tmp_path / "gate.json"; gate.write(gp)
    # mutate the training manifest -> sha256 no longer matches the gate
    tr_man.write_text(tr_man.read_text() + "\n# changed\n")
    assert not validate_gate(gate, tr_man, ev_man).ok
    with pytest.raises(LeakageGateError):
        require_valid_gate(gp, tr_man, ev_man)


def test_unresolved_duplicates_fail(tmp_path):
    # eval shares image seed 1 with training -> exact cross duplicate -> unresolved
    tr_root, tr_man = make_dataset(tmp_path, "train_ds", [("train", "c", 1, False), ("train", "c", 2, False)])
    ev_root, ev_man = make_dataset(tmp_path, "eval_ds", [("test", "c", 1, False), ("test", "c", 40, False)])
    gate, _ = compute_gate(
        training_manifest=tr_man, training_root=tr_root, training_dataset="train_ds",
        evaluation_manifest=ev_man, evaluation_root=ev_root, evaluation_dataset="eval_ds",
        threshold=6, generated_at="2026-01-01T00:00:00+00:00",
    )
    assert gate.unresolved_pair_count >= 1
    assert gate.status == "fail"
    assert not validate_gate(gate, tr_man, ev_man).ok


def test_unresolved_cleared_by_exclusion(tmp_path):
    # same overlap, but declare the pair excluded -> unresolved 0 -> pass
    tr_root, tr_man = make_dataset(tmp_path, "train_ds", [("train", "c", 1, False)])
    ev_root, ev_man = make_dataset(tmp_path, "eval_ds", [("test", "c", 1, False), ("test", "c", 9, False)])
    gate, _ = compute_gate(
        training_manifest=tr_man, training_root=tr_root, training_dataset="train_ds",
        evaluation_manifest=ev_man, evaluation_root=ev_root, evaluation_dataset="eval_ds",
        threshold=6, excluded_pair_count=1, generated_at="2026-01-01T00:00:00+00:00",
    )
    assert gate.unresolved_pair_count == 0
    assert gate.status == "pass"


def test_incomplete_when_image_unhashable(tmp_path):
    # a corrupt image -> skipped -> status incomplete -> blocked
    tr_root, tr_man = make_dataset(tmp_path, "train_ds", [("train", "c", 1, True)])
    ev_root, ev_man = make_dataset(tmp_path, "eval_ds", [("test", "c", 5, False)])
    gate, _ = compute_gate(
        training_manifest=tr_man, training_root=tr_root, training_dataset="train_ds",
        evaluation_manifest=ev_man, evaluation_root=ev_root, evaluation_dataset="eval_ds",
        threshold=6, generated_at="2026-01-01T00:00:00+00:00",
    )
    assert gate.status == "incomplete"
    assert not validate_gate(gate, tr_man, ev_man).ok


def test_dev_override_bypasses_with_warning(tmp_path, capsys):
    _, tr_man, ev_man, *_ = _passing_gate(tmp_path)
    # no gate file, but explicit dev override -> returns None, prints banner
    result = require_valid_gate(tmp_path / "absent.json", tr_man, ev_man,
                                allow_missing_leakage_gate=True)
    assert result is None
    assert "DEV-ONLY OVERRIDE" in capsys.readouterr().err
