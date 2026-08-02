"""Gate-enforced cross-dataset evaluation: fails closed without gate/mapping."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from ica26.datasets import manifest as M
from ica26.leakage.gate import LeakageGateError, compute_gate
from ica26.mapping import schema
from ica26.mapping.validation import NoApprovedMappingError
from ica26.evaluation import harm
from ica26.evaluation.cross_dataset import guarded_cross_dataset_action_evaluation
from ica26.schemas import ACTION_CLASSES


def _ds(tmp_path, name, split, seeds):
    root = tmp_path / name
    for s in seeds:
        d = root / split / "rust"
        d.mkdir(parents=True, exist_ok=True)
        rng = np.random.default_rng(s)
        Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(d / f"{s}.png")
    df = M.build_split_class_manifest(root=root, dataset=name, source_url="u",
                                      split_dirs=["train", "test"],
                                      acquired_at_utc="2026-01-01T00:00:00+00:00")
    man = tmp_path / f"{name}.csv"; M.write_manifest(df, man)
    return root, man


def _valid_gate(tmp_path):
    tr_root, tr_man = _ds(tmp_path, "train_ds", "train", [1, 2])
    ev_root, ev_man = _ds(tmp_path, "eval_ds", "test", [30, 40])
    gate, _ = compute_gate(
        training_manifest=tr_man, training_root=tr_root, training_dataset="train_ds",
        evaluation_manifest=ev_man, evaluation_root=ev_root, evaluation_dataset="eval_ds",
        threshold=6, generated_at="2026-01-01T00:00:00+00:00",
    )
    gp = tmp_path / "gate.json"; gate.write(gp)
    return gp, tr_man, ev_man


def _approved_mapping():
    row = schema.empty_row(dataset="eval_ds", dataset_class="rust",
                           canonical_crop="apple", canonical_disease="rust")
    row.update({
        "pathogen_name": "Gymnosporangium", "pathogen_type": "fungal",
        "action_class": "fungicide", "action_summary": "apply fungicide",
        "source_name": "UC IPM", "source_url": "https://ipm.ucanr.edu/x",
        "source_identifier": "UCIPM-X", "evidence_summary": "fungal rust -> fungicide",
        "evidence_checked_at": "2026-07-28", "mapping_confidence": "high",
        "review_status": "approved",
    })
    return schema.new_template([row])


def test_blocks_without_gate(tmp_path):
    _, tr_man, ev_man = _valid_gate(tmp_path)
    with pytest.raises(LeakageGateError):
        guarded_cross_dataset_action_evaluation(
            y_true=["rust"], y_pred=["rust"], dataset="eval_ds",
            mapping_df=_approved_mapping(),
            gate_path=tmp_path / "absent.json",
            training_manifest=tr_man, evaluation_manifest=ev_man,
        )


def test_blocks_without_approved_mapping(tmp_path):
    gp, tr_man, ev_man = _valid_gate(tmp_path)
    empty = schema.new_template([schema.empty_row(dataset="eval_ds", dataset_class="rust")])  # pending
    with pytest.raises(NoApprovedMappingError):
        guarded_cross_dataset_action_evaluation(
            y_true=["rust"], y_pred=["rust"], dataset="eval_ds", mapping_df=empty,
            gate_path=gp, training_manifest=tr_man, evaluation_manifest=ev_man,
        )


def test_succeeds_with_gate_and_mapping(tmp_path):
    gp, tr_man, ev_man = _valid_gate(tmp_path)
    report = guarded_cross_dataset_action_evaluation(
        y_true=["rust"], y_pred=["rust"], dataset="eval_ds", mapping_df=_approved_mapping(),
        gate_path=gp, training_manifest=tr_man, evaluation_manifest=ev_man,
    )
    assert report["action"]["action_accuracy"] == 1.0
    assert "majority_baseline" in report            # mandatory control present
    assert "projection_inflation" in report


def test_example_harm_matrix_rejected(tmp_path):
    gp, tr_man, ev_man = _valid_gate(tmp_path)
    with pytest.raises(harm.HarmMatrixError):
        guarded_cross_dataset_action_evaluation(
            y_true=["rust"], y_pred=["rust"], dataset="eval_ds", mapping_df=_approved_mapping(),
            gate_path=gp, training_manifest=tr_man, evaluation_manifest=ev_man,
            harm_matrix=harm.EXAMPLE_DEV_REVIEWED_MATRIX,
        )


def test_dev_override_allows_run(tmp_path, capsys):
    _, tr_man, ev_man = _valid_gate(tmp_path)
    report = guarded_cross_dataset_action_evaluation(
        y_true=["rust"], y_pred=["rust"], dataset="eval_ds", mapping_df=_approved_mapping(),
        gate_path=tmp_path / "absent.json",
        training_manifest=tr_man, evaluation_manifest=ev_man,
        allow_missing_leakage_gate=True,
    )
    assert "DEV-ONLY OVERRIDE" in capsys.readouterr().err
    assert report["action"]["action_accuracy"] == 1.0
