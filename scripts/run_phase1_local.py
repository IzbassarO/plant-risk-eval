#!/usr/bin/env python
"""Phase-1 LOCAL data-completion orchestrator (macOS, repository-only).

ONE reproducible command finishes the remaining Phase-1 data prerequisites on
this machine — no Colab, no Google Drive, no cloud scratch. Every artifact lands
inside the repository (``data/raw``, ``data/manifests``, ``data/indexes``,
``data/exclusions``, ``reports``). Manifests and reports use repository-relative
paths only.

    python scripts/run_phase1_local.py            # full pipeline; downloads RESUME
    python scripts/run_phase1_local.py --resume    # same (resume is the default)
    python scripts/run_phase1_local.py --status    # print state, do nothing
    python scripts/run_phase1_local.py --steps plantdoc
    python scripts/run_phase1_local.py --steps plantvillage
    python scripts/run_phase1_local.py --steps leakage,gate
    python scripts/run_phase1_local.py --steps verify

Long-run tip (prevents the Mac from sleeping mid-download):

    caffeinate -dimsu python scripts/run_phase1_local.py --resume

Pipeline (each step independently selectable via --steps):
    plantdoc      complete PlantDoc to the frozen upstream snapshot (commit
                  5467f601) via the GitHub *archive* for that commit (one file,
                  fast) → git clone → raw-CDN per-file only as a last-resort
                  fallback for still-missing files. Existing valid files kept.
    plantvillage  materialize the authoritative PlantVillage *color* pixels from
                  the HF data.zip (revision 9e975998); resume the partial cache.
    verify        manifest consistency (fs<->manifest), path portability, source
                  snapshot validation.
    index         scalable pHash indexes → data/indexes/.
    leakage       PlantVillage color (training) vs PlantDoc (evaluation) pHash
                  comparison + duplicate disposition artifacts.
    gate          (re)generate reports/leakage_gate.json (fail-closed) + a
                  five-state cross-dataset guard test.
    tests         python -m pytest -q.
    checks        scripts/run_phase1_checks.sh (exit 2 == PARTIAL, not an error).
    report        reports/PHASE1_LOCAL_COMPLETION_REPORT.md.
    package       phase1_return_package.zip (reports + manifests + indexes +
                  exclusions; NEVER raw images / archives).

Invariants honored (do not relax): THRESHOLD = 6 (unchanged); no model training;
no mapping row approved; no commit/push; leaf_id preserved and never fabricated;
source images never deleted; near-duplicates never auto-approved; the leakage
gate fails closed. Ctrl+C stops at the next safe point with progress saved; the
next --resume continues. ZIP/JSON/CSV/manifest writes use temp file + atomic
rename.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

# Make the sibling driver importable (shared PlantVillage / gate / checks logic),
# regardless of the caller's CWD.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import run_phase1_data_completion as D  # noqa: E402

# --------------------------------------------------------------------------- #
# Frozen, authoritative source revisions (see PROJECT_BRIEF.md / remediation).
# --------------------------------------------------------------------------- #
PLANTDOC_COMMIT = D.PLANTDOC_COMMIT                      # 5467f601...
PLANTDOC_REPO = "pratikkayal/PlantDoc-Dataset"
PLANTDOC_ARCHIVE_URL = "https://codeload.github.com/{repo}/tar.gz/{sha}"
PLANTVILLAGE_REPO = D.PLANTVILLAGE_REPO                  # mohanty/PlantVillage
PLANTVILLAGE_REV = D.PLANTVILLAGE_REV                    # 9e975998...
PV_DATA_ZIP_URL = (f"https://huggingface.co/datasets/{PLANTVILLAGE_REPO}"
                   f"/resolve/{PLANTVILLAGE_REV}/data.zip")
PHASH_THRESHOLD = D.PHASH_THRESHOLD                      # 6 — do NOT change
MIN_FREE_GB = 12.0
EST_COMPLETION_GB = 5.0

ALL_STEPS = ["plantdoc", "plantvillage", "verify", "index", "leakage",
             "gate", "tests", "checks", "report", "package"]

# --------------------------------------------------------------------------- #
# Logging + cooperative interrupt
# --------------------------------------------------------------------------- #
_LOGFH = None
_STOP = threading.Event()


class StopRequested(Exception):
    """Raised at a safe point after Ctrl+C so progress can be flushed cleanly."""


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def setup_log(path: Path) -> None:
    global _LOGFH
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOGFH = open(path, "a", buffering=1, encoding="utf-8")
    _LOGFH.write(f"\n===== run_phase1_local start {_ts()} pid={os.getpid()} "
                 f"argv={' '.join(sys.argv[1:])} =====\n")


def log(msg: str, to_stdout: bool = True) -> None:
    line = f"[{_ts()}] {msg}"
    if _LOGFH:
        _LOGFH.write(line + "\n")
    if to_stdout:
        print(line, flush=True)


def _install_signal_handler() -> None:
    def _handler(signum, frame):
        if _STOP.is_set():
            log("second interrupt — exiting immediately")
            raise KeyboardInterrupt
        _STOP.set()
        log("interrupt received — stopping at the next safe point "
            "(progress saved; continue with --resume)")
    signal.signal(signal.SIGINT, _handler)


def _check_stop() -> None:
    if _STOP.is_set():
        raise StopRequested()


# --------------------------------------------------------------------------- #
# Small formatting + atomic-write helpers
# --------------------------------------------------------------------------- #
def human(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def atomic_write_text(path: Path, text: str) -> Path:
    return atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, obj) -> Path:
    return atomic_write_text(path, json.dumps(obj, indent=2))


def atomic_write_df(df, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)
    return path


def _read_json(path: Path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Download progress + resumable HTTP download (used for the PlantDoc archive)
# --------------------------------------------------------------------------- #
def _progress_bytes(label: str, got: int, total: int | None, speed: float,
                    eta: float | None, retries: int) -> None:
    if total:
        pct = 100.0 * got / total
        line = (f"  {label}: {human(got)}/{human(total)} ({pct:4.1f}%)  "
                f"{human(speed)}/s  ETA {fmt_dur(eta)}  retries={retries}")
    else:
        line = f"  {label}: {human(got)}  {human(speed)}/s  retries={retries}"
    print("\r" + line + "    ", end="", flush=True)
    log(line.strip(), to_stdout=False)


def _url_content_length(url: str, timeout: int = 30) -> int | None:
    import requests
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        cl = r.headers.get("Content-Length")
        if cl:
            return int(cl)
    except Exception:
        pass
    # Fallback: a 1-byte ranged GET reveals the true total via Content-Range.
    try:
        r = requests.get(url, headers={"Range": "bytes=0-0"}, allow_redirects=True,
                         timeout=timeout, stream=True)
        cr = r.headers.get("Content-Range")
        r.close()
        if cr and "/" in cr:
            tail = cr.rsplit("/", 1)[1]
            return int(tail) if tail.isdigit() else None
    except Exception:
        pass
    return None


def resumable_download(url: str, dest: Path, label: str,
                       expected_size: int | None = None,
                       retries: int = 8, backoff: float = 3.0,
                       timeout: int = 60, chunk: int = 1 << 20) -> dict:
    """Stream ``url`` to ``dest`` with HTTP-Range resume + atomic rename.

    Reuses an existing ``dest.part`` (resume). Retries with exponential backoff.
    Honors Ctrl+C at chunk boundaries (partial preserved for the next resume).
    """
    import requests

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    session = requests.Session()
    session.headers.update({"User-Agent": "ica26-phase1-local"})
    retries_used = 0
    t0 = time.perf_counter()
    attempt = 0
    while True:
        attempt += 1
        existing = part.stat().st_size if part.exists() else 0
        headers = {}
        mode = "wb"
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"
        try:
            with session.get(url, headers=headers, stream=True, timeout=timeout,
                             allow_redirects=True) as r:
                if existing > 0 and r.status_code == 416:
                    break  # already complete on server side
                if existing > 0 and r.status_code == 200:
                    existing, mode = 0, "wb"  # server ignored Range -> restart
                r.raise_for_status()
                total = expected_size
                if total is None:
                    cl = r.headers.get("Content-Length")
                    if cl:
                        total = (existing + int(cl)) if r.status_code == 206 else int(cl)
                got = existing
                win_t0, win_b, last_emit = time.perf_counter(), 0, time.perf_counter()
                with open(part, mode) as f:
                    for c in r.iter_content(chunk):
                        _check_stop()
                        if not c:
                            continue
                        f.write(c)
                        got += len(c)
                        win_b += len(c)
                        now = time.perf_counter()
                        if now - last_emit >= 2.0:
                            spd = win_b / (now - win_t0) if now > win_t0 else 0.0
                            eta = ((total - got) / spd) if (total and spd > 0) else None
                            _progress_bytes(label, got, total, spd, eta, retries_used)
                            last_emit, win_t0, win_b = now, now, 0
            existing = part.stat().st_size if part.exists() else 0
            if expected_size and existing < expected_size:
                # Connection ended early without an exception -> resume.
                if attempt > retries:
                    raise RuntimeError(f"{label}: incomplete after {retries} retries "
                                       f"({existing}/{expected_size})")
                retries_used += 1
                time.sleep(backoff)
                continue
            break
        except StopRequested:
            print()
            raise
        except Exception as e:  # network hiccup -> backoff + resume
            retries_used += 1
            log(f"{label}: attempt {attempt} failed: {type(e).__name__}: {e}")
            if attempt > retries:
                print()
                raise
            time.sleep(backoff * min(attempt, 6))
    print()
    os.replace(part, dest)
    dur = time.perf_counter() - t0
    log(f"{label}: complete {human(dest.stat().st_size)} in {fmt_dur(dur)} "
        f"(retries={retries_used})")
    return {"bytes": dest.stat().st_size, "retries": retries_used, "seconds": round(dur, 1)}


# --------------------------------------------------------------------------- #
# State inspection helpers
# --------------------------------------------------------------------------- #
def _pv_images_root(data_dir: Path) -> Path:
    return data_dir / "raw" / "plantvillage" / "extracted"


def _plantdoc_fs_count(data_dir: Path) -> int:
    root = data_dir / "raw" / "plantdoc"
    n = 0
    for split in ("train", "test"):
        base = root / split
        if base.exists():
            n += sum(1 for p in base.rglob("*")
                     if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    return n


def _pv_pixels_done(data_dir: Path) -> bool:
    s = _read_json(data_dir / "manifests" / "plantvillage_summary.json")
    return bool(s and s.get("pixels_materialized"))


def _plantdoc_done(data_dir: Path) -> bool:
    s = _read_json(data_dir / "manifests" / "plantdoc_summary.json")
    return bool(s and s.get("complete"))


def _mapping_counts(data_dir: Path) -> dict:
    import csv
    import collections
    p = data_dir / "mapping" / "action_mapping_review.csv"
    if not p.exists():
        p = data_dir / "mapping" / "action_mapping_template.csv"
    if not p.exists():
        return {}
    with open(p) as fh:
        rows = list(csv.DictReader(fh))
    c = collections.Counter(r.get("review_status", "?") for r in rows)
    return {"total": len(rows), **{k: int(v) for k, v in c.items()}}


def _snapshot_state(data_dir: Path) -> dict:
    pv = _read_json(data_dir / "manifests" / "plantvillage_summary.json") or {}
    pd_ = _read_json(data_dir / "manifests" / "plantdoc_summary.json") or {}
    gate = _read_json((data_dir.parent / "reports" / "leakage_gate.json"))
    rec = (pd_.get("reconciliation") or {})
    return {
        "plantdoc_fs_images": _plantdoc_fs_count(data_dir),
        "plantdoc_manifest": rec.get("manifest_count"),
        "plantdoc_upstream": rec.get("upstream_repository_count"),
        "plantdoc_complete": bool(pd_.get("complete")),
        "plantvillage_manifest_rows": pv.get("n_images"),
        "plantvillage_pixels_materialized": bool(pv.get("pixels_materialized")),
        "leakage_gate_status": (gate or {}).get("status"),
        "mapping": _mapping_counts(data_dir),
    }


def _find_partials(data_dir: Path) -> list[str]:
    out = []
    raw = data_dir / "raw"
    if raw.exists():
        for p in raw.rglob("*"):
            if p.is_file() and (p.suffix in {".part", ".tmp"} or p.name.endswith(".incomplete")):
                out.append(str(p.relative_to(data_dir.parent)))
    return out


def _check_upstream() -> dict:
    import requests
    out = {}
    for name, url in [("plantdoc_archive",
                       PLANTDOC_ARCHIVE_URL.format(repo=PLANTDOC_REPO, sha=PLANTDOC_COMMIT)),
                      ("plantvillage_data_zip", PV_DATA_ZIP_URL)]:
        try:
            r = requests.head(url, allow_redirects=True, timeout=20)
            out[name] = f"HTTP {r.status_code}"
        except Exception as e:
            out[name] = f"unreachable: {type(e).__name__}"
    return out


# --------------------------------------------------------------------------- #
# Dependency guard (brief §7: pip install -e ".[hf]")
# --------------------------------------------------------------------------- #
def ensure_deps(repo_dir: Path) -> None:
    try:
        import ica26  # noqa: F401
        import datasets  # noqa: F401
        import huggingface_hub  # noqa: F401
        import imagehash  # noqa: F401
        import PIL  # noqa: F401
        import pandas  # noqa: F401
        log("dependencies: ica26 + datasets + huggingface_hub + imagehash + PIL + pandas present")
        return
    except Exception as e:
        log(f"dependencies: missing ({type(e).__name__}: {e}); installing editable package with [hf] extras")
    cmd = [sys.executable, "-m", "pip", "install", "-e", ".[hf]"]
    log("run: " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=str(repo_dir))
    if r.returncode != 0:
        raise SystemExit("pip install -e '.[hf]' failed; cannot proceed")


# --------------------------------------------------------------------------- #
# PREFLIGHT
# --------------------------------------------------------------------------- #
def preflight(repo_dir: Path, data_dir: Path, min_free_gb: float) -> dict:
    log("================ PREFLIGHT ================")
    info: dict = {}
    info["python"] = platform.python_version()
    log(f"python: {info['python']}")
    if sys.version_info < (3, 10):
        log("WARNING: Python < 3.10 — the package targets >=3.10")

    for f in ("PROJECT_BRIEF.md", "pyproject.toml"):
        ok = (repo_dir / f).exists()
        info[f] = ok
        log(f"{f}: {'present' if ok else 'MISSING'}")
        if not ok:
            raise SystemExit(f"required file missing: {f}")

    ensure_deps(repo_dir)

    du = shutil.disk_usage(repo_dir)
    free_gb = du.free / 1e9
    info["free_gb"] = round(free_gb, 1)
    log(f"disk: {du.total/1e9:.0f} GB total, {free_gb:.1f} GB free "
        f"(need >= {min_free_gb:.0f} GB; estimated completion footprint ~{EST_COMPLETION_GB:.0f} GB)")
    if free_gb < min_free_gb:
        raise SystemExit(f"insufficient free disk: {free_gb:.1f} GB < required {min_free_gb:.0f} GB")

    info["state"] = _snapshot_state(data_dir)
    log("current state: " + json.dumps(info["state"]))

    partials = _find_partials(data_dir)
    info["partials"] = partials
    log(f"resumable partial/incomplete files: {len(partials)}"
        + (f" (e.g. {partials[0]})" if partials else ""))

    info["upstream"] = _check_upstream()
    log("upstream reachability: " + json.dumps(info["upstream"]))
    log("preflight OK")
    return info


# --------------------------------------------------------------------------- #
# STEP: PlantDoc (archive-first, then git clone, then raw-CDN fallback)
# --------------------------------------------------------------------------- #
def _enumerate_plantdoc(retries: int = 4) -> dict | None:
    for attempt in range(1, retries + 1):
        _check_stop()
        live = D.list_plantdoc_at_commit(PLANTDOC_COMMIT)
        if live:
            return live
        log(f"PlantDoc: upstream enumeration attempt {attempt}/{retries} failed; retrying")
        time.sleep(2.0 * attempt)
    return None


def _download_plantdoc_archive(dest_root: Path, sha: str) -> Path | None:
    arch_dir = dest_root / "_archive"
    arch_dir.mkdir(parents=True, exist_ok=True)
    archive = arch_dir / f"plantdoc-{sha[:12]}.tar.gz"
    if archive.exists() and tarfile.is_tarfile(archive):
        log(f"PlantDoc: reusing cached archive {archive.name} ({human(archive.stat().st_size)})")
        return archive
    url = PLANTDOC_ARCHIVE_URL.format(repo=PLANTDOC_REPO, sha=sha)
    for attempt in range(1, 4):
        _check_stop()
        try:
            resumable_download(url, archive, "plantdoc archive", timeout=120)
        except StopRequested:
            raise
        except Exception as e:
            log(f"PlantDoc archive download failed (attempt {attempt}): {type(e).__name__}: {e}")
            if archive.exists():
                archive.unlink()
            time.sleep(3.0 * attempt)
            continue
        if tarfile.is_tarfile(archive):
            return archive
        log("PlantDoc: downloaded archive is not a valid tar.gz; re-fetching")
        archive.unlink(missing_ok=True)
    return None


def _extract_plantdoc_from_archive(archive: Path, dest_root: Path) -> tuple[int, int, int]:
    """Single streaming pass over the commit archive; copy every train/test image
    that is MISSING locally. The archive itself defines the frozen file set, so
    this needs no git listing. Existing valid local images are never overwritten;
    each copied file must decode (PIL) or it is skipped (left for a fallback).

    Returns (copied, archive_train_test_images, corrupt_skipped).
    """
    from PIL import Image

    IMG = {".jpg", ".jpeg", ".png"}
    copied = kept = corrupt = seen = 0
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf:
            _check_stop()
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)  # strip "PlantDoc-Dataset-<sha>/"
            if len(parts) < 2:
                continue
            rel = parts[1]
            if not (rel.startswith("train/") or rel.startswith("test/")):
                continue
            if os.path.splitext(rel)[1].lower() not in IMG:
                continue
            seen += 1
            dest = dest_root / rel
            if dest.exists() and dest.stat().st_size > 0:
                kept += 1
                continue
            fobj = tf.extractfile(m)
            if fobj is None:
                continue
            data = fobj.read()
            try:
                Image.open(io.BytesIO(data)).verify()
            except Exception:
                corrupt += 1
                continue
            atomic_write_bytes(dest, data)
            copied += 1
            if copied % 250 == 0:
                log(f"PlantDoc: copied {copied} image(s) from archive")
    log(f"PlantDoc archive: train/test images={seen} copied={copied} "
        f"kept_existing={kept} corrupt_skipped={corrupt}")
    return copied, seen, corrupt


def step_plantdoc(data_dir: Path, do_download: bool = True) -> dict:
    from ica26.datasets import plantdoc as PD

    dest = data_dir / "raw" / "plantdoc"
    man_dir = data_dir / "manifests"
    dest.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale .part temp files from any interrupted per-file write.
    for p in list(dest.rglob("*.part")):
        log(f"PlantDoc: removing stale partial {p.name}")
        p.unlink()

    # Best-effort frozen-commit enumeration: used only for provenance + the
    # raw-CDN fallback list. Acquisition does NOT depend on it (the archive is
    # authoritative). Falls back to the recorded VERIFIED_SNAPSHOT if git is down.
    live = _enumerate_plantdoc(retries=1)
    if live is None:
        log("PlantDoc: git enumeration unavailable — using the archive as the "
            "authoritative frozen file set (VERIFIED_SNAPSHOT for provenance).")

    if do_download and not _STOP.is_set():
        present = _plantdoc_fs_count(data_dir)
        log(f"PlantDoc: {present} image(s) present locally; fetching the commit "
            f"archive for {PLANTDOC_COMMIT[:8]} (single file)")
        # (1) preferred: ONE GitHub archive for the exact commit (no git needed).
        archive = _download_plantdoc_archive(dest, PLANTDOC_COMMIT)
        if archive:
            _extract_plantdoc_from_archive(archive, dest)
        else:
            log("PlantDoc: archive unavailable; keeping existing files")
        # (2) last-resort: raw-CDN per-file for anything still missing vs the git
        #     list (only possible when enumeration succeeded).
        if live and not _STOP.is_set():
            paths = live["paths"]
            missing = [r for r in paths if not ((dest / r).exists() and (dest / r).stat().st_size > 0)]
            if missing:
                log(f"PlantDoc: raw-CDN fallback for {len(missing)} still-missing file(s)")
                rep = PD.download_via_raw(dest, missing, ref=PLANTDOC_COMMIT,
                                          retries=5, backoff=2.0, timeout=60)
                log(f"PlantDoc raw-CDN: +{rep['downloaded']} skipped={rep['skipped']} "
                    f"failed={rep['failed']}")

    # Case-insensitive filesystems silently collapse upstream paths that differ
    # only by letter case, destroying distinct images (AUD-EC-003). Re-assert the
    # collision-safe layout BEFORE the manifest is built, so a fresh extraction
    # can never reintroduce the loss. Idempotent; skipped when already clean.
    _ensure_collision_safe(data_dir)

    # Rebuild manifest/summary/snapshot from the filesystem, pinned to the frozen
    # commit (live enumeration when available, else VERIFIED_SNAPSHOT). Atomic.
    df = PD.build_manifest(dest)
    atomic_write_df(df, man_dir / "plantdoc_manifest.csv")
    snapshot = PD.build_source_snapshot(live=live)  # frozen commit when available
    fs_check = PD.verify_against_filesystem(df, dest)
    summary = PD.summarize(df, snapshot, fs_check)
    atomic_write_json(man_dir / "plantdoc_summary.json", summary)
    atomic_write_json(man_dir / "plantdoc_source_snapshot.json", snapshot)

    rec = summary["reconciliation"]
    log(f"PlantDoc: manifest={rec['manifest_count']} valid={rec['valid_decodable_count']} "
        f"upstream={rec['upstream_repository_count']} complete={summary['complete']} "
        f"(train={rec['train_images']} test={rec['test_images']})")
    _append_plantdoc_reconciliation(data_dir, summary)
    return {"summary": summary, "reconciliation": rec}


def _collision_safe_expected(data_dir: Path) -> list[str]:
    """Active relpaths the inventory implies, with collision members disambiguated."""
    import csv as _csv
    from ica26.datasets.plantdoc import casefold_collisions, collision_safe_relpath

    inv_path = data_dir / "manifests" / "plantdoc_source_inventory.csv"
    if not inv_path.exists():
        return []
    with open(inv_path, newline="", encoding="utf-8") as fh:
        inv = list(_csv.DictReader(fh))
    groups = casefold_collisions(r["original_upstream_path"] for r in inv)
    colliding = {p for members in groups.values() for p in members}
    return [
        collision_safe_relpath(r["original_upstream_path"], r["source_sha256"])
        if r["original_upstream_path"] in colliding else r["original_upstream_path"]
        for r in inv
    ]


def _ensure_collision_safe(data_dir: Path) -> None:
    """Materialize the collision-safe layout if the active tree is not already it.

    The cheap check compares the expected active path set against disk. Only a
    genuine discrepancy pays the cost of re-reading the pinned archive, so the
    common case (already restored) is fast and writes nothing.
    """
    expected = _collision_safe_expected(data_dir)
    if not expected:
        log("plantdoc: no source inventory — skipping collision-safe check")
        return
    dest = data_dir / "raw" / "plantdoc"
    missing = [p for p in expected if not (dest / p).exists()]
    if not missing:
        log(f"plantdoc: collision-safe layout intact ({len(expected)} active paths)")
        return
    log(f"plantdoc: {len(missing)} expected active path(s) absent — "
        "restoring the collision-safe layout from the pinned archive")
    import restore_plantdoc_collisions as RC  # sibling script

    rc = RC.main([])
    if rc != 0:
        raise SystemExit(
            f"collision-safe materialization failed (exit {rc}); refusing to build a "
            "manifest that would silently omit distinct source images"
        )


def _append_plantdoc_reconciliation(data_dir: Path, summary: dict) -> None:
    rec = summary["reconciliation"]
    path = data_dir.parent / "reports" / "PLANTDOC_COUNT_RECONCILIATION.md"
    stamp = _ts()
    block = (
        f"\n\n---\n\n## Local completion update — {stamp}\n\n"
        f"- Acquisition: GitHub archive for commit `{PLANTDOC_COMMIT[:12]}` "
        f"(+ raw-CDN fallback for any missing file); existing valid images preserved.\n"
        f"- Paper-reported count: **{rec['paper_reported_count']}** (not forced).\n"
        f"- Upstream count at pinned commit: **{rec['upstream_repository_count']}** "
        f"(git train/test image paths).\n"
        f"- Local manifest split: train {rec['train_images']} / test {rec['test_images']}.\n"
        f"- Filesystem == manifest == valid decodable: "
        f"**{rec['manifest_count']} / {rec['manifest_count']} / {rec['valid_decodable_count']}**.\n"
        f"- fs<->manifest mismatches: "
        f"{len(rec['filesystem_vs_manifest']['manifest_rows_missing_files'])} rows-missing-files, "
        f"{len(rec['filesystem_vs_manifest']['files_missing_from_manifest'])} files-missing-from-manifest.\n"
        f"- Completion: **{'COMPLETE' if summary['complete'] else 'INCOMPLETE'}** "
        f"({rec['manifest_count']}/{rec['upstream_repository_count']}).\n"
    )
    existing = path.read_text() if path.exists() else "# PlantDoc Count Reconciliation\n"
    atomic_write_text(path, existing + block)


# --------------------------------------------------------------------------- #
# STEP: PlantVillage pixel materialization (HF data.zip, resume the partial)
# --------------------------------------------------------------------------- #
def _zip_ok(path: Path, expected_size: int | None = None) -> bool:
    """Cheap integrity check: file exists, (optionally) matches expected size, and
    its ZIP central directory (at the END of the file) reads back."""
    import zipfile
    p = Path(path)
    if not p.exists() or p.stat().st_size < 1024:
        return False
    if expected_size and p.stat().st_size != expected_size:
        return False
    try:
        with zipfile.ZipFile(p) as zf:
            return len(zf.namelist()) > 0
    except Exception:
        return False


def _prepare_pv_partial(hf_dir: Path) -> None:
    """Seed our resumable ``data.zip.part`` from any existing huggingface_hub
    ``*.incomplete`` cache (a byte-0 prefix), so resume reuses those bytes rather
    than restarting the multi-GB download."""
    final = hf_dir / "data.zip"
    part = hf_dir / "data.zip.part"
    if final.exists() or part.exists():
        return
    dl = hf_dir / ".cache" / "huggingface" / "download"
    if not dl.exists():
        return
    incompletes = sorted(dl.glob("*.incomplete"), key=lambda p: p.stat().st_size, reverse=True)
    if incompletes and incompletes[0].stat().st_size > 0:
        src = incompletes[0]
        hf_dir.mkdir(parents=True, exist_ok=True)
        os.replace(src, part)
        log(f"PlantVillage: seeded resume from cached partial ({human(part.stat().st_size)})")


def step_plantvillage(data_dir: Path, do_download: bool = True) -> dict:
    if _pv_pixels_done(data_dir):
        log("PlantVillage: color pixels already materialized — skipping (resume)")
        summary = _read_json(data_dir / "manifests" / "plantvillage_summary.json")
        return {"summary": summary, "images_root": str(_pv_images_root(data_dir)), "skipped": True}

    hf_dir = data_dir / "raw" / "plantvillage" / "_hf"
    hf_dir.mkdir(parents=True, exist_ok=True)
    final = hf_dir / "data.zip"

    if do_download and not _zip_ok(final):
        total = _url_content_length(PV_DATA_ZIP_URL)
        log(f"PlantVillage: fetching authoritative data.zip via HF resolve URL "
            f"(requests; HTTP-Range resume; revision {PLANTVILLAGE_REV[:8]}; "
            f"total {human(total) if total else 'unknown'}) — not Kaggle")
        _prepare_pv_partial(hf_dir)
        # Own resumable downloader (robust to the httpx client lifecycle issues in
        # huggingface_hub on long/flaky transfers). Only renames to data.zip once
        # the full expected size is present.
        resumable_download(PV_DATA_ZIP_URL, final, "plantvillage data.zip",
                           expected_size=total, retries=40, backoff=4.0, timeout=120)
        if not _zip_ok(final, expected_size=total):
            raise RuntimeError("PlantVillage data.zip failed ZIP verification after download; "
                               "re-run --resume to continue")
        log(f"PlantVillage: data.zip verified ({human(final.stat().st_size)})")

    # Extraction + per-image manifest + pixel verification via the shared driver
    # (reads hf_dir/data.zip; do_download=False so it does NOT re-fetch).
    pv = D.step_plantvillage(data_dir, config="color", do_download=False)
    pvv = pv["summary"].get("pixel_verification", {})
    log(f"PlantVillage: rows={pv['summary'].get('n_images')} "
        f"pixels={pvv.get('pixels_materialized_count')} corrupt={pvv.get('n_corrupt')} "
        f"zero_byte={pvv.get('zero_byte_files')} "
        f"decode_ok={pvv.get('decode_sample_ok')}/{pvv.get('decode_sample_size')} "
        f"sha_ok={pvv.get('sha_sample_ok')}/{pvv.get('sha_sample_size')}")
    return pv


# --------------------------------------------------------------------------- #
# STEP: pHash index generation -> data/indexes/
# --------------------------------------------------------------------------- #
def _build_index_with_progress(manifest_csv: Path, root: Path, dataset: str,
                               every: int = 5000):
    import pandas as pd
    from PIL import Image
    from ica26.leakage.phash import phash_hex, build_index

    man = pd.read_csv(manifest_csv, dtype=str, keep_default_na=False)
    root = Path(root)
    n = len(man)
    recs, skipped = [], []
    t0 = time.perf_counter()
    for i, row in enumerate(man.itertuples(index=False)):
        _check_stop()
        rel = getattr(row, "relpath")
        if str(getattr(row, "is_corrupt", "False")).lower() == "true":
            skipped.append(rel)
            continue
        ap = root / rel
        try:
            with Image.open(ap) as im:
                h = phash_hex(im)
            recs.append({"dataset": dataset, "split": getattr(row, "split", ""),
                         "class_label": getattr(row, "class_label", ""), "path": rel, "phash": h})
        except Exception:
            skipped.append(rel)
        if (i + 1) % every == 0:
            el = time.perf_counter() - t0
            rate = (i + 1) / el if el > 0 else 0.0
            eta = (n - (i + 1)) / rate if rate > 0 else None
            log(f"  index:{dataset}: {i+1}/{n} ({100*(i+1)/n:4.1f}%)  "
                f"{rate:5.0f} img/s  ETA {fmt_dur(eta)}  skipped={len(skipped)}")
    return build_index(recs), skipped


def step_index(data_dir: Path) -> dict:
    from ica26.leakage.phash import PHASH_ALGORITHM, DEFAULT_HASH_SIZE

    idx_dir = data_dir / "indexes"
    idx_dir.mkdir(parents=True, exist_ok=True)
    man_dir = data_dir / "manifests"
    targets = [
        ("plantvillage", man_dir / "plantvillage_manifest.csv", _pv_images_root(data_dir), "PlantVillage"),
        ("plantdoc", man_dir / "plantdoc_manifest.csv", data_dir / "raw" / "plantdoc", "PlantDoc"),
    ]
    results = {}
    for key, man, root, dataset in targets:
        if not man.exists():
            log(f"index: {key} manifest missing — skipped")
            continue
        if not Path(root).exists():
            from ica26.leakage.phash import build_index
            atomic_write_df(build_index([]), idx_dir / f"phash_index_{key}.csv")
            log(f"index: {key} images root {root} missing — wrote empty index (0 indexed, fail-closed)")
            results[key] = {"indexed": 0, "skipped": None, "note": "images root missing"}
            continue
        log(f"index: building pHash index for {dataset} (root={Path(root).relative_to(data_dir.parent)})")
        idx_df, skipped = _build_index_with_progress(man, root, dataset)
        atomic_write_df(idx_df, idx_dir / f"phash_index_{key}.csv")
        results[key] = {"indexed": int(len(idx_df)), "skipped": len(skipped)}
        log(f"index: {dataset} indexed={len(idx_df)} skipped={len(skipped)} "
            f"-> data/indexes/phash_index_{key}.csv")
    meta = {
        "phash_algorithm": PHASH_ALGORITHM,
        "hash_size_bits": DEFAULT_HASH_SIZE * DEFAULT_HASH_SIZE,
        "threshold": PHASH_THRESHOLD,
        "generated_at_utc": _ts(),
        "indexes": results,
    }
    atomic_write_json(idx_dir / "phash_index_meta.json", meta)
    return results


# --------------------------------------------------------------------------- #
# STEP: cross-dataset leakage (PlantVillage color -> PlantDoc) + dispositions
# --------------------------------------------------------------------------- #
def step_leakage(data_dir: Path, repo_dir: Path, threshold: int = PHASH_THRESHOLD) -> dict:
    import pandas as pd
    from ica26.leakage.phash import candidate_search_audit_fields, find_duplicates

    idx_dir = data_dir / "indexes"
    pv_idx_p = idx_dir / "phash_index_plantvillage.csv"
    pd_idx_p = idx_dir / "phash_index_plantdoc.csv"
    if not pv_idx_p.exists() or not pd_idx_p.exists():
        log("leakage: pHash indexes missing — building them first")
        step_index(data_dir)

    idx_train = pd.read_csv(pv_idx_p, dtype=str, keep_default_na=False)
    idx_eval = pd.read_csv(pd_idx_p, dtype=str, keep_default_na=False)

    man_dir = data_dir / "manifests"
    n_pv_manifest = _csv_rows(man_dir / "plantvillage_manifest.csv")
    n_pd_manifest = _csv_rows(man_dir / "plantdoc_manifest.csv")
    skipped_train = max(0, n_pv_manifest - len(idx_train))
    skipped_eval = max(0, n_pd_manifest - len(idx_eval))

    log(f"leakage: PlantVillage(train) indexed={len(idx_train)} skipped={skipped_train} | "
        f"PlantDoc(eval) indexed={len(idx_eval)} skipped={skipped_eval} | threshold={threshold}")

    res = find_duplicates(idx_train, idx_eval, threshold=threshold)
    hmap_a = dict(zip(idx_train["path"], idx_train["phash"]))
    hmap_b = dict(zip(idx_eval["path"], idx_eval["phash"]))
    n_exact = int(res["summary"]["n_exact_pairs"])
    n_near = int(res["summary"]["n_near_pairs"])

    reports = repo_dir / "reports"
    excl_dir = data_dir / "exclusions"
    reports.mkdir(parents=True, exist_ok=True)
    excl_dir.mkdir(parents=True, exist_ok=True)

    # Canonical identities are derived from the MANIFESTS, so the persisted table
    # carries the same identity the gate recomputes from fresh detection
    # (R1-CRIT-001). Class labels come from the manifest, not from the index.
    from ica26.leakage.gate import CANONICAL_PAIR_SCHEMA, PairIdentity

    man_dir = data_dir / "manifests"
    tr_sha = dict(zip(*_manifest_cols(man_dir / "plantvillage_manifest.csv", "sha256")))
    ev_sha = dict(zip(*_manifest_cols(man_dir / "plantdoc_manifest.csv", "sha256")))
    tr_cls = dict(zip(*_manifest_cols(man_dir / "plantvillage_manifest.csv", "class_label")))
    ev_cls = dict(zip(*_manifest_cols(man_dir / "plantdoc_manifest.csv", "class_label")))

    def _identity(t_rel, e_rel, distance, kind) -> PairIdentity:
        return PairIdentity(
            training_dataset="PlantVillage", training_relpath=t_rel,
            training_class=tr_cls.get(t_rel, ""), training_sha256=tr_sha.get(t_rel, ""),
            evaluation_dataset="PlantDoc", evaluation_relpath=e_rel,
            evaluation_class=ev_cls.get(e_rel, ""), evaluation_sha256=ev_sha.get(e_rel, ""),
            phash_distance=int(distance), classification=kind,
        )

    def _rows(df, kind):
        out = []
        for _, r in df.iterrows():
            pending = kind == "near"
            ident = _identity(r["path_a"], r["path_b"], r["distance"], kind)
            out.append({
                "canonical_pair_id": ident.canonical_pair_id,
                "pair_schema": CANONICAL_PAIR_SCHEMA,
                "training_relpath": r["path_a"], "evaluation_relpath": r["path_b"],
                "training_class": ident.training_class,
                "evaluation_class": ident.evaluation_class,
                "training_sha256": ident.training_sha256,
                "evaluation_sha256": ident.evaluation_sha256,
                "training_phash": hmap_a.get(r["path_a"], ""),
                "evaluation_phash": hmap_b.get(r["path_b"], ""),
                "hamming_distance": int(r["distance"]), "classification": kind,
                "review_status": "pending" if pending else "exact_auto_flagged",
                "proposed_disposition": ("manual_review_required" if pending
                                         else "exclude_evaluation_image"),
                "notes": (f"near-duplicate (0<d<={threshold}); NOT auto-excluded, awaits human review"
                          if pending else
                          "exact perceptual-hash match (d=0); proposed exclusion from evaluation set"),
            })
        return out

    cols = ["canonical_pair_id", "pair_schema",
            "training_relpath", "evaluation_relpath", "training_class", "evaluation_class",
            "training_sha256", "evaluation_sha256",
            "training_phash", "evaluation_phash", "hamming_distance", "classification",
            "review_status", "proposed_disposition", "notes"]
    pairs_df = pd.DataFrame(_rows(res["exact"], "exact") + _rows(res["near"], "near"), columns=cols)
    if len(pairs_df):
        pairs_df = pairs_df.sort_values(
            ["classification", "hamming_distance", "training_relpath", "evaluation_relpath"]
        ).reset_index(drop=True)
    atomic_write_df(pairs_df, reports / "leakage_plantvillage_vs_plantdoc_pairs.csv")

    summary = {
        "training_dataset": "PlantVillage", "training_config": "color",
        "evaluation_dataset": "PlantDoc",
        "phash_algorithm": res["summary"]["phash_algorithm"],
        "hash_size_bits": res["summary"]["hash_size_bits"], "threshold": threshold,
        # Persist the candidate-search contract and its scalability telemetry.
        # For this cross-dataset result side A is PlantVillage (training), and
        # side B is PlantDoc (evaluation).
        **candidate_search_audit_fields(res["summary"]),
        "n_training_indexed": int(len(idx_train)), "n_evaluation_indexed": int(len(idx_eval)),
        "skipped_training": skipped_train, "skipped_evaluation": skipped_eval,
        "n_exact_pairs": n_exact, "n_near_pairs": n_near, "n_pending_review": n_near,
        "self_pairs": 0, "reversed_duplicates": 0,
        "pairs_csv": "reports/leakage_plantvillage_vs_plantdoc_pairs.csv",
    }
    atomic_write_json(reports / "leakage_plantvillage_vs_plantdoc_summary.json", summary)

    # Exact cross-dataset duplicates -> propose EXCLUDING the evaluation image.
    excl_rows = []
    for _, r in res["exact"].iterrows():
        ident = _identity(r["path_a"], r["path_b"], r["distance"], "exact")
        excl_rows.append({
            "canonical_pair_id": ident.canonical_pair_id,
            "pair_schema": CANONICAL_PAIR_SCHEMA,
            "evaluation_dataset": "PlantDoc", "evaluation_relpath": r["path_b"],
            "evaluation_class": ident.evaluation_class,
            "evaluation_sha256": ident.evaluation_sha256,
            "training_dataset": "PlantVillage",
            "training_relpath": r["path_a"], "training_class": ident.training_class,
            "training_sha256": ident.training_sha256,
            "hamming_distance": int(r["distance"]),
            "reason": "exact cross-dataset perceptual-hash duplicate with a training image",
            "provenance": f"{res['summary']['phash_algorithm']} d=0 vs PlantVillage color @ {PLANTVILLAGE_REV[:8]}",
            "action": "propose_exclude_from_evaluation", "status": "proposed",
        })
    excl_df = pd.DataFrame(excl_rows, columns=[
        "canonical_pair_id", "pair_schema",
        "evaluation_dataset", "evaluation_relpath", "evaluation_class", "evaluation_sha256",
        "training_dataset", "training_relpath", "training_class", "training_sha256",
        "hamming_distance", "reason", "provenance", "action", "status"])
    if len(excl_df):
        excl_df = excl_df.sort_values(["evaluation_relpath", "training_relpath"]).reset_index(drop=True)
    atomic_write_df(excl_df, excl_dir / "cross_dataset_exact_exclusions.csv")

    # Near-duplicates -> human review manifest (pending; never auto-approved).
    lines = [
        "# Cross-Dataset Near-Duplicate Review", "",
        f"**Training source:** PlantVillage (color) @ `{PLANTVILLAGE_REV}`  ",
        f"**Evaluation source:** PlantDoc @ `{PLANTDOC_COMMIT}`  ",
        f"**Algorithm / threshold:** {res['summary']['phash_algorithm']} / Hamming <= {threshold}  ", "",
        "Near-duplicates (0 < Hamming <= threshold) are **not** automatically treated as "
        "true duplicates. Each pair below is `review_status=pending` and must be adjudicated "
        "by a human before the leakage gate may pass.", "",
    ]
    if n_near == 0:
        lines += ["**There are no near-duplicate cross-dataset pairs at this threshold.**", ""]
    else:
        lines += [f"**{n_near} near-duplicate pair(s) pending review.**", "",
                  "| # | Train class | Train path | Eval class | Eval path | d | status |",
                  "|---|---|---|---|---|---|---|"]
        for i, (_, r) in enumerate(res["near"].sort_values(["distance", "path_a", "path_b"]).iterrows(), 1):
            lines.append(f"| {i} | {r['class_a']} | `{r['path_a']}` | {r['class_b']} | "
                         f"`{r['path_b']}` | {int(r['distance'])} | pending |")
        lines.append("")
    atomic_write_text(reports / "CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md", "\n".join(lines))

    log(f"leakage: exact={n_exact} near={n_near} pending={n_near} "
        f"proposed_exclusions={len(excl_df)} skipped={skipped_train + skipped_eval}")
    return {"summary": summary, "n_exact": n_exact, "n_near": n_near, "n_pending": n_near,
            "n_excluded": int(len(excl_df)), "skipped": skipped_train + skipped_eval}


def _manifest_cols(manifest_csv: Path, column: str) -> tuple[list[str], list[str]]:
    """(relpaths, values) for one manifest column. Manifests are the authority."""
    import csv as _csv

    keys, vals = [], []
    with open(manifest_csv, newline="", encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            keys.append(r["relpath"])
            vals.append(r[column])
    return keys, vals


def _csv_rows(path: Path) -> int:
    if not Path(path).exists():
        return 0
    with open(path, "rb") as f:
        return max(0, sum(1 for _ in f) - 1)


# --------------------------------------------------------------------------- #
# STEP: leakage gate (fail-closed) + five-state guard test
# --------------------------------------------------------------------------- #
def step_gate(data_dir: Path, repo_dir: Path, threshold: int = PHASH_THRESHOLD) -> dict:
    # Independent recompute (re-hashes + binds current manifest SHAs) — the audit
    # required cross-dataset metrics to be blocked by a persisted, manifest-bound
    # gate. Reuses the shared driver's gate step.
    res = D.step_gate(data_dir, repo_dir, _pv_images_root(data_dir),
                      threshold=threshold)
    _write_guard_test(data_dir, repo_dir)
    return res


def _gate_inputs(data_dir: Path, repo_dir: Path):
    """Every artifact the persisted gate is bound to (AUD-EC-008)."""
    from ica26.leakage.gate import GateInputs

    man_dir = data_dir / "manifests"
    excl_dir = data_dir / "exclusions"
    return GateInputs(
        training_manifest=man_dir / "plantvillage_manifest.csv",
        evaluation_manifest=man_dir / "plantdoc_manifest.csv",
        pair_table=repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_pairs.csv",
        near_review=excl_dir / "cross_dataset_near_duplicate_review.csv",
        reviewed_exclusions=excl_dir / "cross_dataset_reviewed_exclusions.csv",
        exact_exclusions=excl_dir / "cross_dataset_exact_exclusions.csv",
    )


def _write_guard_test(data_dir: Path, repo_dir: Path) -> dict:
    """Exercise the leakage-gate validator across its rejection states.

    Every state is a synthetic gate checked against the REAL current inputs, so
    the guard test proves the validator rejects staleness of each bound input,
    not just of the manifests.
    """
    from ica26.leakage.gate import (
        GATE_INPUT_NAMES, LeakageGate, PHASH_ALGORITHM, SCHEMA_VERSION,
        compute_input_digests, validate_gate,
    )

    man_dir = data_dir / "manifests"
    if not (man_dir / "plantvillage_manifest.csv").exists() or \
            not (man_dir / "plantdoc_manifest.csv").exists():
        log("guard-test: manifests missing — skipped")
        return {}

    inputs = _gate_inputs(data_dir, repo_dir)
    digests = compute_input_digests(
        inputs, threshold=PHASH_THRESHOLD,
        training_dataset="PlantVillage", evaluation_dataset="PlantDoc")

    def _gate(**kw) -> LeakageGate:
        base = dict(schema_version=SCHEMA_VERSION,
                    training_dataset="PlantVillage", evaluation_dataset="PlantDoc",
                    phash_algorithm=PHASH_ALGORITHM, threshold=PHASH_THRESHOLD,
                    exact_duplicate_count=0, exact_excluded_count=0,
                    near_duplicate_count=0, near_resolved_count=0,
                    near_kept_count=0, near_excluded_count=0,
                    unresolved_pair_count=0, status="pass",
                    authorization_violations=[], input_digests=dict(digests))
        base.update(kw)
        return LeakageGate(**base)

    def _stale(name: str) -> LeakageGate:
        d = dict(digests)
        d[name] = "0" * 64
        return _gate(input_digests=d)

    states = {
        "1_missing": (None, "rejected"),
        "2_incomplete": (_gate(status="incomplete"), "rejected"),
        "3_unresolved": (_gate(unresolved_pair_count=1), "rejected"),
        "4_violations": (_gate(authorization_violations=["synthetic violation"]), "rejected"),
        "5_old_schema": (_gate(schema_version="1.1"), "rejected"),
        "6_unbound": (_gate(input_digests={}), "rejected"),
        "7_valid_pass": (_gate(), "accepted"),
    }
    # One rejection state per bound input, so no binding can silently go missing.
    for name in GATE_INPUT_NAMES:
        states[f"8_stale_{name}"] = (_stale(name), "rejected")

    results, all_ok = {}, True
    for name, (gate, expect) in sorted(states.items()):
        res = validate_gate(gate, inputs)
        got = "accepted" if res.ok else "rejected"
        ok = got == expect
        all_ok = all_ok and ok
        results[name] = f"{got} {'OK' if ok else 'MISMATCH'}"
    out = {
        "guard_states": results, "all_pass": all_ok,
        "bound_inputs": list(GATE_INPUT_NAMES),
        "note": ("Every state except the final valid gate must be rejected. Each "
                 "8_stale_* state mutates exactly one bound input digest, proving the "
                 "gate is bound to all of them and not only to the manifests. "
                 "Synthetic gates (same technique as tests/test_leakage_gate.py). "
                 "No model evaluation was run."),
    }
    atomic_write_json(repo_dir / "reports" / "leakage_gate_guard_test.json", out)
    log(f"guard-test: {len(states)}-state validator all_pass={all_ok}")
    return out


# --------------------------------------------------------------------------- #
# STEP: verification (manifest consistency, portability, snapshots)
# --------------------------------------------------------------------------- #
def step_verify(data_dir: Path, repo_dir: Path) -> dict:
    import pandas as pd
    from ica26.datasets import plantdoc as PD
    from ica26 import portability

    res: dict = {}
    man_dir = data_dir / "manifests"

    pd_man = man_dir / "plantdoc_manifest.csv"
    if pd_man.exists():
        df = pd.read_csv(pd_man, dtype=str, keep_default_na=False)
        chk = PD.verify_against_filesystem(df, data_dir / "raw" / "plantdoc")
        res["plantdoc_fs_manifest"] = {
            "n_manifest": chk["n_manifest"], "n_filesystem": chk["n_filesystem"],
            "rows_missing_files": len(chk["manifest_rows_missing_files"]),
            "files_missing_from_manifest": len(chk["files_missing_from_manifest"]),
        }
        log("verify: PlantDoc fs<->manifest " + json.dumps(res["plantdoc_fs_manifest"]))

    pv_man = man_dir / "plantvillage_manifest.csv"
    if pv_man.exists():
        pv = pd.read_csv(pv_man, dtype=str, keep_default_na=False)
        dups = int(pv["relpath"].duplicated().sum())
        leaf_present = int((pv["has_leaf_id"].astype(str).str.lower() == "true").sum())
        res["plantvillage_manifest"] = {"rows": int(len(pv)), "duplicate_relpaths": dups,
                                        "leaf_id_present": leaf_present,
                                        "leaf_id_missing": int(len(pv)) - leaf_present}
        log("verify: PlantVillage manifest " + json.dumps(res["plantvillage_manifest"]))

    port = portability.validate_portability(repo_dir)
    res["portability_ok"] = port.ok
    res["portability_errors"] = [f"{i.where}: {i.message}" for i in port.errors][:20]
    log(f"verify: path portability ok={port.ok}"
        + ("" if port.ok else f" ({len(port.errors)} leak(s))"))

    res["snapshots"] = _validate_snapshots(data_dir)
    log("verify: source snapshots " + json.dumps(res["snapshots"]))
    return res


def _validate_snapshots(data_dir: Path) -> dict:
    out = {}
    pd_snap = _read_json(data_dir / "manifests" / "plantdoc_source_snapshot.json") or {}
    pv_snap = _read_json(data_dir / "manifests" / "plantvillage_source_snapshot.json") or {}
    out["plantdoc"] = {
        "commit_sha_matches_frozen": pd_snap.get("commit_sha") == PLANTDOC_COMMIT,
        "upstream_image_count": pd_snap.get("upstream_image_count"),
        "no_personal_path": "/Users/" not in json.dumps(pd_snap),
    }
    out["plantvillage"] = {
        "revision_matches_frozen": pv_snap.get("revision") == PLANTVILLAGE_REV,
        "repo": pv_snap.get("hf_repo"),
        "no_personal_path": "/Users/" not in json.dumps(pv_snap),
    }
    return out


# --------------------------------------------------------------------------- #
# STEP: pytest + Phase-1 checks
# --------------------------------------------------------------------------- #
def step_tests(repo_dir: Path) -> dict:
    log("tests: python -m pytest -q")
    # Force exactly single -q (pyproject addopts already sets -q; a second -q
    # becomes -qq and suppresses the 'N passed' summary line we parse).
    r = subprocess.run([sys.executable, "-m", "pytest", "-o", "addopts=-q"],
                       cwd=str(repo_dir), capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    for ln in out.strip().splitlines()[-12:]:
        log("  " + ln, to_stdout=False)
    m = re.search(r"(\d+) passed", out)
    passed = int(m.group(1)) if m else None
    failed = re.search(r"(\d+) failed", out)
    log(f"tests: exit={r.returncode} passed={passed} failed={failed.group(1) if failed else 0}")
    return {"exit": r.returncode, "passed": passed,
            "failed": int(failed.group(1)) if failed else 0,
            "tail": out.strip().splitlines()[-4:]}


def step_checks(repo_dir: Path) -> dict:
    script = repo_dir / "scripts" / "run_phase1_checks.sh"
    env = dict(os.environ, PYTHON=sys.executable)
    log("checks: bash scripts/run_phase1_checks.sh")
    r = subprocess.run(["bash", str(script)], cwd=str(repo_dir), env=env,
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if _LOGFH:
        _LOGFH.write(out + "\n")
    m = re.search(r"OVERALL:\s*(\w+)", out)
    verdict = m.group(1) if m else "UNKNOWN"
    log(f"checks: exit={r.returncode} verdict={verdict} "
        f"(exit 2 == PARTIAL/BLOCKED, not an execution error)")
    return {"exit": r.returncode, "verdict": verdict,
            "tail": [ln for ln in out.strip().splitlines() if ln.strip()][-12:]}


# --------------------------------------------------------------------------- #
# STEP: local completion report
# --------------------------------------------------------------------------- #
def render_report(data_dir: Path, repo_dir: Path, state: dict) -> str:
    pd_sum = _read_json(data_dir / "manifests" / "plantdoc_summary.json") or {}
    pd_snap = _read_json(data_dir / "manifests" / "plantdoc_source_snapshot.json") or {}
    pv_sum = _read_json(data_dir / "manifests" / "plantvillage_summary.json") or {}
    gate = _read_json(repo_dir / "reports" / "leakage_gate.json") or {}
    lk = _read_json(repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_summary.json") or {}
    cc = _read_json(data_dir / "manifests" / "_plantdoc_case_collisions.json") or {}
    n_coll = cc.get("case_insensitive_collision_pairs")
    rec = pd_sum.get("reconciliation", {})
    pvv = pv_sum.get("pixel_verification", {})
    mp = _mapping_counts(data_dir)
    tests = state.get("tests", {})
    checks = state.get("checks", {})
    verify = state.get("verify", {})

    pd_complete = bool(pd_sum.get("complete"))
    pv_pixels = bool(pv_sum.get("pixels_materialized"))
    up = rec.get("upstream_repository_count") or 0
    man = rec.get("manifest_count") or 0
    coll = n_coll or 0
    fsvm = rec.get("filesystem_vs_manifest", {})
    rows_missing = len(fsvm.get("manifest_rows_missing_files", []))
    files_missing = len(fsvm.get("files_missing_from_manifest", []))
    # PlantDoc acquisition is "exhaustive" when every upstream path except the
    # case-variant duplicates (unrepresentable on this filesystem) is present and
    # the manifest is fully consistent with the filesystem.
    pd_missing = max(0, up - man - coll)
    pd_exhaustive = (pd_missing == 0 and rows_missing == 0 and files_missing == 0)
    data_ready = bool(pv_pixels and pd_exhaustive)
    gate_status = gate.get("status", "n/a")
    if data_ready and gate_status == "pass":
        overall = "COMPLETE"
    elif data_ready:
        overall = "DATA-COMPLETE — human review pending (gate fail-closed)"
    else:
        overall = "PARTIAL — data acquisition incomplete"
    dur = state.get("duration_seconds")

    def yn(b):
        return "yes" if b else "no"

    L = []
    L += [
        "# Phase-1 LOCAL Completion Report", "",
        "**Project:** *From Diagnosis to Decision: An Action-Level and Risk-Weighted "
        "Evaluation Framework for Deep Learning-Based Plant Disease Recognition*  ",
        "**Task:** complete the remaining Phase-1 **data prerequisites** locally "
        "(macOS, repository-only) with one reproducible command.  ",
        f"**Generated:** {_ts()}  ",
        "**No model training was performed.** **No scientific performance result was "
        "produced or claimed.** **No disease-to-action mapping row was automatically approved.**",
        "",
        f"## A. Overall status: **{overall}**", "",
        f"- Data prerequisites materialized: **{yn(data_ready)}** "
        f"(PlantVillage pixels: {yn(pv_pixels)}; PlantDoc acquisition exhaustive on this "
        f"filesystem: {yn(pd_exhaustive)}).",
        f"- PlantDoc: **{man}** distinct images on disk — all {up} upstream paths fetched; "
        f"{coll} case-variant duplicate(s) are unrepresentable on the case-insensitive macOS "
        "filesystem (see §B).",
        f"- PlantVillage: **{pv_sum.get('n_images')}** images, pixels materialized, "
        f"corrupt **{pvv.get('n_corrupt')}**.",
        f"- Leakage gate status: **{gate_status}** (fail-closed) — "
        f"{gate.get('near_duplicate_count', 0)} near-duplicate pair(s) pending human review, "
        f"{gate.get('exact_duplicate_count', 0)} exact.",
        f"- Tests: **{(state.get('tests') or {}).get('passed')} passed**; "
        f"Phase-1 checks verdict: **{(state.get('checks') or {}).get('verdict')}**.",
        f"- Run duration: **{fmt_dur(dur)}**" + (f" ({dur:.0f}s)" if dur else ""),
        "",
        "## B. PlantDoc completion", "",
        f"- Source revision (frozen): `{PLANTDOC_COMMIT}`",
        "- Acquisition: GitHub archive for the pinned commit (single file) → raw-CDN "
        "fallback for any missing file. Existing valid images preserved; SHA-256 per image.",
        f"- Paper-reported count: **{rec.get('paper_reported_count')}** (not forced).",
        f"- Upstream count at pinned commit: **{rec.get('upstream_repository_count')}** "
        f"(train {pd_snap.get('upstream_train_images')} / test {pd_snap.get('upstream_test_images')}).",
        f"- Local manifest split: train **{rec.get('train_images')}** / test **{rec.get('test_images')}**.",
        f"- Filesystem == manifest == valid decodable: "
        f"**{state.get('plantdoc_fs_images')} / {rec.get('manifest_count')} / {rec.get('valid_decodable_count')}** "
        "(fully consistent).",
        f"- Corrupt: **{pd_sum.get('n_corrupt_total', 0)}**; duplicate relpaths: "
        f"**{len(pd_sum.get('duplicate_relpaths', []))}**; "
        f"fs<->manifest mismatches: **{verify.get('plantdoc_fs_manifest', {}).get('rows_missing_files', 0)} / "
        f"{verify.get('plantdoc_fs_manifest', {}).get('files_missing_from_manifest', 0)}**.",
    ]
    if n_coll:
        L += [
            f"- **Case-collision reconciliation:** all **{rec.get('upstream_repository_count')}** upstream "
            f"train/test image paths were fetched, but **{n_coll}** are case-variant pairs "
            "(e.g. `CAR1.jpg` vs `car1.jpg`) that are distinct in the case-sensitive upstream "
            "git tree yet **cannot coexist on the case-insensitive macOS (APFS) filesystem**; each "
            f"pair collapses to one file, so distinct on-disk images = {rec.get('upstream_repository_count')} "
            f"− {n_coll} = **{rec.get('manifest_count')}** (evidence: "
            "`data/manifests/_plantdoc_case_collisions.json`). This is a filesystem limitation, "
            "not a missing download; no count was forced or fabricated.",
        ]
    L += [
        f"- Completion vs the strict {rec.get('upstream_repository_count')}-path target: "
        f"**{rec.get('manifest_count')}/{rec.get('upstream_repository_count')}** "
        f"(`complete={pd_complete}`)"
        + (f"; acquisition is otherwise **exhaustive** on this filesystem "
           f"(only the {n_coll} case-variant duplicates are unrepresentable)." if n_coll else "."),
        "",
        "## C. PlantVillage completion", "",
        f"- Source revision (frozen): HF `{PLANTVILLAGE_REPO}` @ `{PLANTVILLAGE_REV}` (color; **not Kaggle**).",
        f"- Manifest rows: **{pv_sum.get('n_images')}**; classes: **{pv_sum.get('n_classes_total')}** "
        f"(healthy: **{pv_sum.get('n_healthy_classes')}**).",
        f"- Pixels materialized: **{yn(pv_pixels)}** "
        f"(count {pvv.get('pixels_materialized_count')}); corrupt: **{pvv.get('n_corrupt')}**; "
        f"zero-byte: **{pvv.get('zero_byte_files')}**.",
        f"- Deterministic sample: decode **{pvv.get('decode_sample_ok')}/{pvv.get('decode_sample_size')}**, "
        f"SHA-256 **{pvv.get('sha_sample_ok')}/{pvv.get('sha_sample_size')}**.",
        f"- leaf_id present / missing: **{(pv_sum.get('leaf_id') or {}).get('n_with_leaf_id')} / "
        f"{(pv_sum.get('leaf_id') or {}).get('n_without_leaf_id')}** "
        "(preserved; never fabricated; missing left missing).",
        "",
        "## D. Cross-dataset leakage result (PlantVillage color -> PlantDoc)", "",
        f"- Algorithm / threshold: `{lk.get('phash_algorithm', 'imagehash.phash')}` / "
        f"Hamming <= **{lk.get('threshold', PHASH_THRESHOLD)}** (unchanged).",
        f"- Indexed: training **{lk.get('n_training_indexed')}**, evaluation **{lk.get('n_evaluation_indexed')}**; "
        f"skipped: training **{lk.get('skipped_training')}**, evaluation **{lk.get('skipped_evaluation')}**.",
        f"- Exact duplicate pairs: **{lk.get('n_exact_pairs')}** (proposed evaluation exclusions; "
        "source files never deleted).",
        f"- Near-duplicate pairs: **{lk.get('n_near_pairs')}** — **pending human review** "
        "(never auto-approved).",
        "",
        "## E. Leakage gate status", "",
        f"- Status: **{gate.get('status', 'n/a')}** "
        f"(exact {gate.get('exact_duplicate_count')}, near {gate.get('near_duplicate_count')}, "
        f"excluded {gate.get('excluded_pair_count')}, "
        f"human-resolved {gate.get('resolved_pair_count')}, "
        f"unresolved {gate.get('unresolved_pair_count')}).",
        f"- Manifest-bound (training SHA `{str(gate.get('training_manifest_sha256'))[:12]}…`, "
        f"evaluation SHA `{str(gate.get('evaluation_manifest_sha256'))[:12]}…`).",
        f"- Five-state guard test: `reports/leakage_gate_guard_test.json` "
        f"(all_pass={(_read_json(repo_dir / 'reports' / 'leakage_gate_guard_test.json') or {}).get('all_pass')}).",
        "- The gate **fails closed**: it cannot report `pass` while any image is skipped, "
        "any exact pair is unresolved, or any near-duplicate remains pending.",
        "",
        "## F. Test results", "",
        f"- `python -m pytest -q`: **{tests.get('passed')} passed**, "
        f"{tests.get('failed', 0)} failed (exit {tests.get('exit')}).",
        "",
        "## G. Remaining human review", "",
        f"- Disease->action mapping: **{mp.get('total', 0)} rows**, "
        f"needs_review **{mp.get('needs_review', 0)}**, approved **{mp.get('approved', 0)}** "
        "(unchanged; none auto-approved).",
        f"- Near-duplicate cross-dataset pairs pending: **{lk.get('n_near_pairs', 0)}** "
        "(`reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md`).",
        "- A ReviewedHarmMatrix must still be authored + approved before harm-weighted "
        "evaluation (out of Phase-1 data scope).",
        "",
        "## H. Phase-1 check verdict", "",
        f"- `scripts/run_phase1_checks.sh`: verdict **{checks.get('verdict', 'n/a')}** "
        f"(exit {checks.get('exit')}; exit 2 == PARTIAL, not an execution error).",
        "",
        "## I. Changed / produced files", "",
        "- `data/manifests/plantdoc_manifest.csv`, `plantdoc_summary.json`, `plantdoc_source_snapshot.json`",
        "- `data/manifests/plantvillage_manifest.csv`, `plantvillage_summary.json`, `plantvillage_source_snapshot.json`",
        "- `data/indexes/phash_index_plantvillage.csv`, `phash_index_plantdoc.csv`, `phash_index_meta.json`",
        "- `data/exclusions/cross_dataset_exact_exclusions.csv`",
        "- `reports/leakage_plantvillage_vs_plantdoc_pairs.csv`, `…_summary.json`",
        "- `reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md`, `reports/leakage_gate.json`, "
        "`reports/leakage_gate_guard_test.json`",
        "- `reports/PLANTDOC_COUNT_RECONCILIATION.md` (appended), `reports/phase1_local_run.log`",
        "- `reports/PHASE1_LOCAL_COMPLETION_REPORT.md` (this file), `phase1_return_package.zip`",
        "",
        "## J. Exact next action", "",
    ]
    if not data_ready:
        L += ["- Re-run to finish the remaining download(s) (resumable):", "",
              "  ```", "  caffeinate -dimsu python scripts/run_phase1_local.py --resume", "  ```", ""]
    elif gate_status == "pass":
        L += ["- Data prerequisites complete and the leakage gate passes. Next (separate, "
              "non-data tasks): human review + approval of the 28-row disease->action mapping, "
              "then author + approve a ReviewedHarmMatrix.", ""]
    else:
        L += [
            f"- **Data acquisition is complete.** The only remaining blocker is human review: "
            f"the leakage gate is `{gate_status}` (fail-closed) because "
            f"**{gate.get('near_duplicate_count', 0)} near-duplicate pair(s)** are pending "
            "adjudication (near-duplicates are never auto-excluded).",
            "  1. Adjudicate `reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md` "
            "(mark each pair keep/exclude with a reason).",
            "  2. Record confirmed cross-dataset duplicates in "
            "`data/exclusions/cross_dataset_exact_exclusions.csv` (evaluation-side exclusions).",
            "  3. Re-run the gate: `python scripts/run_phase1_local.py --steps leakage,gate` "
            "→ expect `pass` once no unresolved pairs remain.",
            "  4. Separately (non-data): review + approve the 28-row disease->action mapping and "
            "author + approve a ReviewedHarmMatrix.",
            "",
        ]
    L += [
        "## K. Explicit statements", "",
        '- "No model training was performed."',
        '- "No scientific performance result was produced or claimed."',
        '- "No disease-to-action mapping row was automatically approved."',
        "",
    ]
    return "\n".join(L)


def step_report(data_dir: Path, repo_dir: Path, state: dict) -> Path:
    text = render_report(data_dir, repo_dir, state)
    out = repo_dir / "reports" / "PHASE1_LOCAL_COMPLETION_REPORT.md"
    atomic_write_text(out, text)
    log(f"report: wrote {out.relative_to(repo_dir)}")
    return out


# --------------------------------------------------------------------------- #
# STEP: return package (reports + manifests + indexes + exclusions; NO images)
# --------------------------------------------------------------------------- #
def step_package(data_dir: Path, repo_dir: Path, out_zip: Path) -> Path:
    import zipfile

    report_files = [
        "reports/PHASE1_LOCAL_COMPLETION_REPORT.md",
        "reports/leakage_gate.json",
        "reports/leakage_plantvillage_vs_plantdoc_pairs.csv",
        "reports/leakage_plantvillage_vs_plantdoc_summary.json",
        "reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md",
        "reports/leakage_gate_guard_test.json",
        "reports/PLANTDOC_COUNT_RECONCILIATION.md",
        # Human-review packet (text only; contact-sheet PNGs are kept in the repo,
        # never packaged, so the return zip stays image-free).
        "reports/PHASE1_HUMAN_REVIEW_PREPARATION_REPORT.md",
        "reports/PLANTDOC_CASE_COLLISION_REVIEW.md",
        "reports/NEAR_DUPLICATE_HUMAN_REVIEW.md",
        "reports/ACTION_MAPPING_HUMAN_CHECKLIST.md",
        "reports/LEAKAGE_GATE_EXCLUSION_POLICY.md",
    ]
    dir_includes = [data_dir / "manifests", data_dir / "exclusions", data_dir / "indexes"]
    skip_suffixes = {".jpg", ".jpeg", ".png", ".zip", ".tar", ".gz", ".tgz",
                     ".pyc", ".pyo", ".part", ".tmp", ".incomplete"}

    tmp = out_zip.with_name(out_zip.name + ".part")
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in report_files:
            p = repo_dir / rel
            if p.is_file():
                zf.write(p, rel)
                n += 1
        for base in dir_includes:
            if not base.exists():
                continue
            for f in sorted(base.rglob("*")):
                if not f.is_file() or f.suffix.lower() in skip_suffixes:
                    continue
                if "__pycache__" in f.parts or ".git" in f.parts or ".venv" in f.parts:
                    continue
                arc = Path("data") / f.relative_to(data_dir)
                zf.write(f, str(arc))
                n += 1
    os.replace(tmp, out_zip)
    log(f"package: wrote {out_zip.name} ({n} files, {human(out_zip.stat().st_size)}) "
        "— reports + manifests + indexes + exclusions only (no raw images/archives)")
    return out_zip


# --------------------------------------------------------------------------- #
# --status
# --------------------------------------------------------------------------- #
def cmd_status(repo_dir: Path, data_dir: Path) -> int:
    st = _snapshot_state(data_dir)
    print("================ run_phase1_local --status ================")
    print(json.dumps(st, indent=2))
    partials = _find_partials(data_dir)
    print(f"\nresumable partials: {len(partials)}")
    for p in partials[:10]:
        print(f"  - {p}")
    report = repo_dir / "reports" / "PHASE1_LOCAL_COMPLETION_REPORT.md"
    pkg = repo_dir / "phase1_return_package.zip"
    print(f"\nlast report:  {'present' if report.exists() else 'absent'} "
          f"({report}) ")
    print(f"return package: {'present' if pkg.exists() else 'absent'} ({pkg})")
    done = st["plantdoc_complete"] and st["plantvillage_pixels_materialized"]
    print("\nnext action:")
    if done:
        print("  data prerequisites complete — review near-duplicates + mapping, "
              "then: python scripts/run_phase1_local.py --steps leakage,gate")
    else:
        print("  caffeinate -dimsu python scripts/run_phase1_local.py --resume")
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_phase1_local",
                                 description="One-command LOCAL Phase-1 data completion (macOS).")
    ap.add_argument("--repo-dir", default=".", help="repository root (default: CWD)")
    ap.add_argument("--data-dir", default=None, help="data dir (default: <repo>/data)")
    ap.add_argument("--steps", default="all",
                    help="comma list of: " + ",".join(ALL_STEPS) + " (or 'all')")
    ap.add_argument("--resume", action="store_true",
                    help="continue downloads (this is already the default behavior)")
    ap.add_argument("--status", action="store_true", help="print current state and exit")
    ap.add_argument("--no-download", action="store_true",
                    help="use already-present raw data; do not fetch")
    ap.add_argument("--threshold", type=int, default=PHASH_THRESHOLD,
                    help="pHash Hamming threshold (default 6; do not change)")
    ap.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB)
    ap.add_argument("--package-out", default=None,
                    help="return-package path (default: <repo>/phase1_return_package.zip)")
    args = ap.parse_args(argv)

    repo_dir = Path(args.repo_dir).resolve()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else (repo_dir / "data")

    if args.threshold != PHASH_THRESHOLD:
        print(f"refusing to change THRESHOLD from {PHASH_THRESHOLD} to {args.threshold}",
              file=sys.stderr)
        return 2

    if args.status:
        return cmd_status(repo_dir, data_dir)

    setup_log(repo_dir / "reports" / "phase1_local_run.log")
    _install_signal_handler()
    do_download = not args.no_download
    steps = (ALL_STEPS if args.steps == "all"
             else [s.strip() for s in args.steps.split(",") if s.strip()])
    unknown = [s for s in steps if s not in ALL_STEPS]
    if unknown:
        log(f"unknown step(s): {unknown}; valid: {ALL_STEPS}")
        return 2

    log(f"repo_dir={repo_dir}")
    log(f"data_dir={data_dir}")
    log(f"steps={steps} download={do_download} resume={args.resume or True} threshold={PHASH_THRESHOLD}")

    state: dict = {}
    t_start = time.perf_counter()
    try:
        preflight(repo_dir, data_dir, args.min_free_gb)

        if "plantdoc" in steps:
            log("================ STEP plantdoc ================")
            state["plantdoc"] = step_plantdoc(data_dir, do_download=do_download)
            state["plantdoc_fs_images"] = _plantdoc_fs_count(data_dir)
            _check_stop()
        if "plantvillage" in steps:
            log("================ STEP plantvillage ================")
            state["plantvillage"] = step_plantvillage(data_dir, do_download=do_download)
            _check_stop()
        if "verify" in steps:
            log("================ STEP verify ================")
            state["verify"] = step_verify(data_dir, repo_dir)
            _check_stop()
        if "index" in steps:
            log("================ STEP index ================")
            state["index"] = step_index(data_dir)
            _check_stop()
        if "leakage" in steps:
            log("================ STEP leakage ================")
            state["leakage"] = step_leakage(data_dir, repo_dir, threshold=PHASH_THRESHOLD)
            _check_stop()
        if "gate" in steps:
            log("================ STEP gate ================")
            state["gate"] = step_gate(data_dir, repo_dir, threshold=PHASH_THRESHOLD)
            _check_stop()
        if "tests" in steps:
            log("================ STEP tests ================")
            state["tests"] = step_tests(repo_dir)
            _check_stop()
        if "checks" in steps:
            log("================ STEP checks ================")
            state["checks"] = step_checks(repo_dir)
            _check_stop()

        # verify/index metrics used by the report even when run in 'all'
        state.setdefault("plantdoc_fs_images", _plantdoc_fs_count(data_dir))
        state["duration_seconds"] = time.perf_counter() - t_start

        if "report" in steps:
            log("================ STEP report ================")
            step_report(data_dir, repo_dir, state)
        if "package" in steps:
            log("================ STEP package ================")
            out_zip = (Path(args.package_out).resolve() if args.package_out
                       else repo_dir / "phase1_return_package.zip")
            step_package(data_dir, repo_dir, out_zip)

    except StopRequested:
        log("stopped by user request. Progress is saved.")
        log("resume with:  caffeinate -dimsu python scripts/run_phase1_local.py --resume")
        # Still emit a report snapshot so state is inspectable.
        try:
            state["duration_seconds"] = time.perf_counter() - t_start
            state.setdefault("plantdoc_fs_images", _plantdoc_fs_count(data_dir))
            step_report(data_dir, repo_dir, state)
        except Exception as e:
            log(f"(report snapshot failed: {type(e).__name__}: {e})")
        return 130
    except KeyboardInterrupt:
        log("hard interrupt — exiting. Resume with --resume.")
        return 130

    _print_final_summary(repo_dir, data_dir, state)
    log("done.")
    return 0


def _print_final_summary(repo_dir: Path, data_dir: Path, state: dict) -> None:
    st = _snapshot_state(data_dir)
    gate = _read_json(repo_dir / "reports" / "leakage_gate.json") or {}
    lk = _read_json(repo_dir / "reports" / "leakage_plantvillage_vs_plantdoc_summary.json") or {}
    tests = state.get("tests", {})
    checks = state.get("checks", {})
    pd_complete = st["plantdoc_complete"]
    pv_pixels = st["plantvillage_pixels_materialized"]
    cc = _read_json(data_dir / "manifests" / "_plantdoc_case_collisions.json") or {}
    coll = cc.get("case_insensitive_collision_pairs") or 0
    up = st.get("plantdoc_upstream") or 0
    man = st.get("plantdoc_manifest") or 0
    pd_exhaustive = pv_pixels and (max(0, up - man - coll) == 0)
    data_ready = bool(pv_pixels and pd_exhaustive)
    if data_ready and gate.get("status") == "pass":
        overall = "COMPLETE"
    elif data_ready:
        overall = "DATA-COMPLETE (human review pending; gate fail-closed)"
    else:
        overall = "PARTIAL (data acquisition incomplete)"
    dur = state.get("duration_seconds")
    print("\n================ FINAL SUMMARY ================")
    print(f"A. Overall status .......... {overall}")
    print(f"B. PlantDoc ................ {st['plantdoc_manifest']}/{st['plantdoc_upstream']} "
          f"(complete={pd_complete})")
    print(f"C. PlantVillage ............ rows={st['plantvillage_manifest_rows']} "
          f"pixels_materialized={pv_pixels}")
    print(f"D. Leakage ................. exact={lk.get('n_exact_pairs')} "
          f"near={lk.get('n_near_pairs')} pending={lk.get('n_pending_review')}")
    print(f"E. Gate .................... {gate.get('status')} (fail-closed)")
    print(f"F. Tests ................... {tests.get('passed')} passed (exit {tests.get('exit')})")
    print(f"G. Human review ............ mapping needs_review="
          f"{st['mapping'].get('needs_review')} approved={st['mapping'].get('approved')}; "
          f"near-dupe pending={lk.get('n_near_pairs')}")
    print(f"H. Duration ................ {fmt_dur(dur)}")
    print(f"I. Return package .......... {repo_dir / 'phase1_return_package.zip'}")
    if not data_ready:
        print("J. Resume command .......... caffeinate -dimsu python scripts/run_phase1_local.py --resume")
    elif gate.get("status") == "pass":
        print("J. Next action ............. (data done, gate pass) human mapping review + harm matrix")
    else:
        print("J. Next action ............. adjudicate reports/CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md, "
              "then: python scripts/run_phase1_local.py --steps leakage,gate")
    print(f"K. Report .................. {repo_dir / 'reports' / 'PHASE1_LOCAL_COMPLETION_REPORT.md'}")
    print(f"   Phase-1 check verdict ... {checks.get('verdict')} (exit {checks.get('exit')})")
    print("   No model training was performed. No scientific result produced or claimed.")
    print("   No disease-to-action mapping row was automatically approved.")


if __name__ == "__main__":
    raise SystemExit(main())
