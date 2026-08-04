"""Regression coverage for the Phase-1 acceptance control plane.

``run_phase1_checks.sh`` used to recompute a weaker mapping predicate and treat
the mere existence of ``dataset_v1_freeze.json`` as an accepted freeze.  The
status heredoc is exercised here without running the checker's full (and
recursive) pytest invocation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT = "scripts/run_phase1_checks.sh"
HEREDOC_MARKER = (
    'READINESS_CHECK_RC="$READINESS_CHECK_RC" FREEZE_CHECK_RC="$FREEZE_CHECK_RC" '
    '"$PY" - <<\'PYEOF\'\n'
)


def _status_program(repo_root: Path) -> str:
    text = (repo_root / SCRIPT).read_text(encoding="utf-8")
    assert HEREDOC_MARKER in text
    return text.split(HEREDOC_MARKER, 1)[1].split("\nPYEOF\n", 1)[0]


def _write_json(root: Path, relpath: str, payload: dict) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _run_status(program: str, cwd: Path, check_rc: int, freeze_check_rc: int = 1):
    env = dict(os.environ, READINESS_CHECK_RC=str(check_rc),
               FREEZE_CHECK_RC=str(freeze_check_rc))
    return subprocess.run([sys.executable, "-"], input=program, text=True,
                          cwd=cwd, env=env, capture_output=True)


def test_the_checker_invokes_a_fresh_strict_readiness_check(repo_root):
    text = (repo_root / SCRIPT).read_text(encoding="utf-8")

    assert 'scripts/build_dataset_v1_freeze_readiness.py --check' in text
    assert 'scripts/materialize_dataset_v1_freeze.py --check' in text
    assert 'scientific = "ACCEPTED" if technical_freeze_valid else "BLOCKED"' in text
    assert 'v1_status = "PASS" if os.path.exists("data/manifests/dataset_v1_freeze.json")' not in text
    assert 'needs = sum(1 for r in mapping if r.get("review_status") == "needs_review")' not in text
    assert 'pv_mapped = {r["dataset_class"]' not in text
    assert 'open("/tmp/ica_verdict.txt"' not in text


def test_a_hand_created_freeze_file_cannot_override_not_ready(tmp_path, repo_root):
    """This fixture satisfies every former shell predicate except strict readiness.

    In the old checker, the empty mapping table (no literal ``needs_review``),
    absent PlantVillage classes, passing raw gates, and an arbitrary freeze file
    yielded ``ACCEPTED``.  The strict readiness artifact still names a blocked
    mapping condition, so the new control-plane program must exit blocked.
    """
    _write_json(tmp_path, "data/manifests/plantdoc_summary.json", {"complete": True})
    _write_json(tmp_path, "data/manifests/plantvillage_summary.json",
                {"pixels_materialized": True})
    _write_json(tmp_path, "reports/leakage_gate.json", {"status": "pass"})
    _write_json(tmp_path, "reports/plantdoc_internal_duplicate_gate.json", {
        "status": "pass", "schema_version": "2.0",
        "remediation": {"evaluated": True, "ok": True},
        "identity_reconciliation": {"equal": True},
    })
    _write_json(tmp_path, "data/manifests/dataset_v1_freeze.json", {"fabricated": True})
    _write_json(tmp_path, "reports/dataset_v1_freeze_readiness.json", {
        "status": "not_ready", "satisfied": 9, "blocked": 1,
        "blockers": ["disease_action_mapping_reviewed"],
        "conditions": [{
            "id": "disease_action_mapping_reviewed",
            "kind": "human_scientific", "status": "blocked",
            "detail": "a human mapping decision is still required",
        }],
    })

    result = _run_status(_status_program(repo_root), tmp_path, check_rc=1)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "DATASET V1 FREEZE READINESS .... BLOCKED" in result.stdout
    assert "SCIENTIFIC PHASE-1 STATUS ...... BLOCKED" in result.stdout


def test_a_stale_assessment_cannot_authorize_a_freeze(tmp_path, repo_root):
    _write_json(tmp_path, "reports/dataset_v1_freeze_readiness.json", {
        "status": "ready", "satisfied": 1, "blocked": 0,
        "blockers": [],
        "conditions": [{"id": "plantdoc_acquired", "status": "satisfied"}],
    })

    result = _run_status(_status_program(repo_root), tmp_path, check_rc=3)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "UNVERIFIABLE" in result.stdout
    assert "STALE" not in result.stdout  # no stale artifact can be reported as ready


def test_a_ready_predecision_assessment_without_a_technical_record_stays_blocked(tmp_path, repo_root):
    _write_json(tmp_path, "reports/dataset_v1_freeze_readiness.json", {
        "status": "ready", "satisfied": 2, "blocked": 0,
        "blockers": [],
        "conditions": [
            {"id": "plantdoc_acquired", "status": "satisfied"},
            {"id": "freeze_approval_recorded", "status": "satisfied"},
        ],
    })

    result = _run_status(_status_program(repo_root), tmp_path, check_rc=0, freeze_check_rc=1)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "DATASET V1 FREEZE READINESS .... READY_FOR_FREEZE" in result.stdout
    assert "SCIENTIFIC PHASE-1 STATUS ...... BLOCKED" in result.stdout


def test_a_present_but_invalid_freeze_record_is_a_hard_control_failure(
        tmp_path, repo_root):
    _write_json(tmp_path, "reports/dataset_v1_freeze_readiness.json", {
        "status": "ready", "satisfied": 2, "blocked": 0,
        "blockers": [],
        "conditions": [
            {"id": "plantdoc_acquired", "status": "satisfied"},
            {"id": "freeze_approval_recorded", "status": "satisfied"},
        ],
    })
    _write_json(tmp_path, "data/manifests/dataset_v1_freeze.json", {})

    result = _run_status(
        _status_program(repo_root), tmp_path, check_rc=0, freeze_check_rc=3)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "DATASET V1 FREEZE READINESS .... UNVERIFIABLE" in result.stdout
    assert "hard-failure exit 3" in result.stdout
    assert "SCIENTIFIC PHASE-1 STATUS ...... BLOCKED" in result.stdout


def test_a_fresh_fully_satisfied_assessment_and_validated_record_are_required(tmp_path, repo_root):
    _write_json(tmp_path, "reports/dataset_v1_freeze_readiness.json", {
        "status": "ready", "satisfied": 2, "blocked": 0,
        "blockers": [],
        "conditions": [
            {"id": "plantdoc_acquired", "status": "satisfied"},
            {"id": "freeze_approval_recorded", "status": "satisfied"},
        ],
    })

    result = _run_status(_status_program(repo_root), tmp_path, check_rc=0, freeze_check_rc=0)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "DATASET V1 FREEZE READINESS .... FROZEN" in result.stdout
    assert "SCIENTIFIC PHASE-1 STATUS ...... ACCEPTED" in result.stdout


# --------------------------------------------------------------------------- #
# HARD 8 must compare the committed manifest to the filesystem, not the
# filesystem to itself.
# --------------------------------------------------------------------------- #
HARD8_MARKER = ('"$PY" - <<\'PYEOF\' || fail "PlantDoc filesystem/manifest '
                'mismatch"\n')

PLANTDOC_MANIFEST = "data/manifests/plantdoc_manifest.csv"


def _hard8_program(repo_root: Path) -> str:
    text = (repo_root / SCRIPT).read_text(encoding="utf-8")
    assert HARD8_MARKER in text
    return text.split(HARD8_MARKER, 1)[1].split("\nPYEOF\n", 1)[0]


def _run_hard8(program: str, cwd: Path, repo_root: Path):
    env = dict(os.environ, PYTHONPATH=str(repo_root / "src"))
    return subprocess.run([sys.executable, "-"], input=program, text=True,
                          cwd=cwd, env=env, capture_output=True)


def _plantdoc_repo(root: Path, *, materialize: bool) -> None:
    rows = ["dataset,split,class_label,relpath,sha256",
            "PlantDoc,train,Apple leaf,train/Apple leaf/a.jpg,",
            "PlantDoc,test,Apple leaf,test/Apple leaf/b.jpg,"]
    manifest = root / PLANTDOC_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(rows) + "\n", encoding="utf-8")
    for rel in ("train/Apple leaf/a.jpg", "test/Apple leaf/b.jpg"):
        target = root / "data/raw/plantdoc" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if materialize:
            target.write_bytes(b"pixels")


def test_hard8_reads_the_committed_manifest_rather_than_rebuilding_it(repo_root):
    """It used to build the manifest FROM the tree it then compared against.

    The symmetric difference of a scan with itself is always empty, so the
    check passed on an empty ``data/raw/plantdoc`` while a 2,578-row manifest
    sat on disk unread.
    """
    program = _hard8_program(repo_root)
    assert PLANTDOC_MANIFEST in program
    assert "build_manifest(" not in program


def test_hard8_fails_when_the_manifest_names_files_that_are_absent(tmp_path, repo_root):
    _plantdoc_repo(tmp_path, materialize=False)

    result = _run_hard8(_hard8_program(repo_root), tmp_path, repo_root)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "rows_missing_files: 2" in result.stdout


def test_hard8_passes_when_the_manifest_matches_the_filesystem(tmp_path, repo_root):
    _plantdoc_repo(tmp_path, materialize=True)

    result = _run_hard8(_hard8_program(repo_root), tmp_path, repo_root)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "rows_missing_files: 0 | files_missing_from_manifest: 0" in result.stdout
