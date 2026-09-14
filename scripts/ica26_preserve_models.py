#!/usr/bin/env python3
"""Preserve the ICA 2026 trained models outside the repository, with digests.

    python scripts/ica26_preserve_models.py                # archive + write manifest
    python scripts/ica26_preserve_models.py --verify       # re-hash, compare, write nothing

Why this exists: `*.pt` and `experiments/ica26/runs/**/*.npz` are gitignored, so
the checkpoints and raw prediction dumps live in exactly one place — the working
tree. A `git clean`, a branch switch, or a re-run under a colliding
``experiment_id`` would destroy training that costs hours per run and cannot be
reproduced bit-for-bit on a different machine.

The split of responsibility is deliberate:

  * the **bytes** go to an archive outside the repository, so no git operation
    can reach them;
  * the **digests** go to a manifest inside the repository, so the archive can
    be proven intact — or proven damaged — from a clean checkout that does not
    contain the weights at all.

A digest recorded here binds a checkpoint to the ``experiment_lock_digest`` and
``git_commit`` its own ``result.json`` recorded at training time. That chain is
what lets a paper number be traced back to a specific weight file.

Archiving is copy-only. Nothing in ``experiments/ica26/runs`` is moved, renamed,
or deleted, and an existing archived file is replaced only when the live file's
digest differs from the archived one.

Exit codes: 0 success / verified, 1 verification failed, 2 nothing to preserve.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "experiments/ica26/runs"
MANIFEST = REPO / "reports/ica26_model_preservation.json"
DEFAULT_ARCHIVE = Path.home() / "ICA2026_model_archive"

# Per-run artifacts worth preserving. The checkpoint is the irreplaceable one;
# the prediction dumps are gitignored too and regenerating them requires the
# checkpoint anyway. The small JSON files are already tracked by git, but are
# copied alongside so the archive is self-describing without the repository.
ARTIFACTS = [
    "best.pt",
    "predictions_in_domain_test.npz",
    "predictions_validation.npz",
    "predictions_cross_domain.npz",
    "result.json",
    "history.json",
    "config.resolved.json",
]
SCHEMA = "ica26.model_preservation/1"


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def run_provenance(run_dir: Path) -> dict:
    """Read the training-time provenance a checkpoint must stay bound to."""
    result = run_dir / "result.json"
    if not result.exists():
        return {"experiment_lock_digest": None, "git_commit": None, "config": None}
    payload = json.loads(result.read_text())
    cfg = payload.get("config") or {}
    return {
        "experiment_lock_digest": payload.get("experiment_lock_digest"),
        "git_commit": payload.get("git_commit"),
        "seed": cfg.get("seed"),
        "dataset": cfg.get("dataset"),
        "model": cfg.get("model"),
        "best_epoch": (payload.get("training") or {}).get("best_epoch"),
        "best_val_macro_f1": (payload.get("training") or {}).get("best_val_macro_f1"),
    }


def scan_runs() -> dict[str, dict]:
    """Digest every preservable artifact in every run directory."""
    out: dict[str, dict] = {}
    if not RUNS.exists():
        return out
    for run_dir in sorted(p for p in RUNS.iterdir() if p.is_dir()):
        files = {}
        for name in ARTIFACTS:
            f = run_dir / name
            if f.exists():
                files[name] = {
                    "sha256": sha256(f),
                    "bytes": f.stat().st_size,
                }
        if files:
            out[run_dir.name] = {"provenance": run_provenance(run_dir), "files": files}
    return out


def archive_runs(runs: dict[str, dict], archive: Path) -> tuple[int, int]:
    """Copy artifacts into the archive. Returns (copied, already_current)."""
    copied = current = 0
    for run_id, entry in runs.items():
        dest_dir = archive / run_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name, meta in entry["files"].items():
            src, dest = RUNS / run_id / name, dest_dir / name
            # Re-copy only when the archived bytes differ. Hashing the
            # destination is cheaper than rewriting 98 MB, and it turns a
            # partially-written previous archive into a self-healing one.
            if dest.exists() and sha256(dest) == meta["sha256"]:
                current += 1
                continue
            tmp = dest.with_suffix(dest.suffix + ".partial")
            shutil.copy2(src, tmp)
            if sha256(tmp) != meta["sha256"]:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"copy of {src} did not match its source digest")
            os.replace(tmp, dest)
            copied += 1
    return copied, current


def verify(manifest: dict, archive: Path) -> list[str]:
    """Check live tree and archive against the recorded digests."""
    problems: list[str] = []
    for run_id, entry in manifest["runs"].items():
        for name, meta in entry["files"].items():
            for where, base in (("live", RUNS), ("archive", archive)):
                f = base / run_id / name
                if not f.exists():
                    problems.append(f"MISSING {where}: {run_id}/{name}")
                elif sha256(f) != meta["sha256"]:
                    problems.append(f"DIGEST MISMATCH {where}: {run_id}/{name}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE,
                    help=f"archive root outside the repository (default: {DEFAULT_ARCHIVE})")
    ap.add_argument("--verify", action="store_true",
                    help="re-hash live and archived copies against the manifest; write nothing")
    args = ap.parse_args()

    if args.verify:
        if not MANIFEST.exists():
            print(f"MISSING manifest {MANIFEST}", file=sys.stderr)
            return 1
        manifest = json.loads(MANIFEST.read_text())
        archive = Path(manifest.get("archive_root", args.archive)).expanduser()
        problems = verify(manifest, archive)
        n_files = sum(len(e["files"]) for e in manifest["runs"].values())
        print(f"manifest    : {MANIFEST.relative_to(REPO)}")
        print(f"archive     : {archive}")
        print(f"checked     : {n_files} artifacts x 2 locations across {len(manifest['runs'])} runs")
        if problems:
            print(f"FAILED      : {len(problems)} problem(s)")
            for p in problems:
                print(f"  {p}")
            return 1
        print("OK          : every recorded digest matches in both locations")
        return 0

    runs = scan_runs()
    if not runs:
        print(f"no run artifacts under {RUNS}; nothing to preserve", file=sys.stderr)
        return 2

    archive = args.archive.expanduser()
    archive.mkdir(parents=True, exist_ok=True)
    copied, already = archive_runs(runs, archive)

    total_bytes = sum(m["bytes"] for e in runs.values() for m in e["files"].values())
    payload = {
        "schema": SCHEMA,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "archive_root": str(archive),
        "note": (
            "Checkpoints and prediction dumps are gitignored; the bytes live in "
            "archive_root and only their digests are tracked here. Verify with "
            "scripts/ica26_preserve_models.py --verify."
        ),
        "n_runs": len(runs),
        "n_artifacts": sum(len(e["files"]) for e in runs.values()),
        "total_bytes": total_bytes,
        "runs": runs,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"archive     : {archive}")
    print(f"runs        : {len(runs)}")
    print(f"artifacts   : {payload['n_artifacts']} ({total_bytes / 1e6:.1f} MB)")
    print(f"copied      : {copied} new/changed, {already} already current")
    print(f"manifest    : {MANIFEST.relative_to(REPO)}")
    for run_id, entry in runs.items():
        ck = entry["files"].get("best.pt")
        prov = entry["provenance"]
        if ck:
            print(f"  {run_id:30s} seed={prov.get('seed')} "
                  f"best_epoch={prov.get('best_epoch')} sha256={ck['sha256'][:16]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
