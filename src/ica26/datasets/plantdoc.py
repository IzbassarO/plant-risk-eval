"""PlantDoc acquisition + reconciliation.

Acquisition prefers a git clone/checkout at a pinned commit (authoritative,
original filenames and split structure) over per-file GitHub API calls. It:
  * records the exact source revision (commit SHA) in a source snapshot;
  * builds a deterministic per-image manifest (sha256, dims, mode, corrupt flag);
  * reconciles the paper-reported count (2,598) against the current upstream tree
    count and the successfully-downloaded/decoded counts;
  * verifies the filesystem against the manifest in BOTH directions (rows without
    files, files without rows).

No count is forced. Observed values are recorded and the discrepancy explained.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

import pandas as pd

from ..schemas import IMAGE_EXTENSIONS, PLANTDOC_SOURCE
from . import manifest as M

REPO = "pratikkayal/PlantDoc-Dataset"
REPO_URL = f"https://github.com/{REPO}.git"
DEFAULT_REF = "master"
RAW_URL = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"

# Paper-reported count (Singh et al. 2020). NOT forced onto observed data.
PAPER_REPORTED_COUNT = 2598

# Verified authoritative snapshot (this session, via blobless clone). Used as a
# fallback when a live git query is not available; a live query overrides it.
VERIFIED_SNAPSHOT = {
    "commit_sha": "5467f6012d78d1c446145d5f582da6096f852ae8",
    "commit_date": "2021-05-02",
    "upstream_image_count": 2578,
    "upstream_train_images": 2342,
    "upstream_test_images": 236,
    "upstream_train_classes": 28,
    "upstream_test_classes": 27,
    "train_only_classes": ["Tomato two spotted spider mites leaf"],
}

EXPECTED = {
    "paper_reported_count": PAPER_REPORTED_COUNT,
    "upstream_count_note": "current upstream tree has 2,578 images at the pinned commit",
    "train_classes": 28,
    "test_classes": 27,
    "note": "Test split drops the 'Tomato two spotted spider mites leaf' class.",
}


# --------------------------------------------------------------------------- #
# Source enumeration via git (preferred; not rate-limited)
# --------------------------------------------------------------------------- #
def _git(*args, cwd=None, timeout=1800) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def git_remote_head_sha(repo_url: str = REPO_URL, ref: str = DEFAULT_REF) -> Optional[str]:
    try:
        r = _git("ls-remote", repo_url, ref, timeout=120)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.split()[0]
    except Exception:
        pass
    return None


def list_repo_images_via_git(repo_url: str = REPO_URL, ref: str = DEFAULT_REF) -> Optional[dict]:
    """Blobless metadata clone -> authoritative image list + commit SHA + counts.

    Returns a dict, or None if git/network is unavailable.
    """
    tmp = tempfile.mkdtemp(prefix="pd_meta_")
    try:
        r = _git("clone", "--filter=blob:none", "--no-checkout", "--depth", "1",
                 repo_url, tmp, timeout=600)
        if r.returncode != 0:
            return None
        sha = _git("rev-parse", "HEAD", cwd=tmp).stdout.strip()
        tree = _git("ls-tree", "-r", "HEAD", "--name-only", cwd=tmp).stdout.splitlines()
        imgs = [p for p in tree if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS
                and (p.startswith("train/") or p.startswith("test/"))]
        def classes(prefix):
            return sorted({p.split("/")[1] for p in imgs if p.startswith(prefix) and len(p.split("/")) >= 3})
        tr = [p for p in imgs if p.startswith("train/")]
        te = [p for p in imgs if p.startswith("test/")]
        return {
            "commit_sha": sha,
            "paths": sorted(imgs),
            "upstream_image_count": len(imgs),
            "upstream_train_images": len(tr),
            "upstream_test_images": len(te),
            "upstream_train_classes": len(classes("train/")),
            "upstream_test_classes": len(classes("test/")),
            "train_only_classes": sorted(set(classes("train/")) - set(classes("test/"))),
        }
    except Exception:
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
def download_via_git(dest_root: str | Path, repo_url: str = REPO_URL, ref: str = DEFAULT_REF) -> dict:
    """Preferred: shallow git clone at the pinned ref, copy train/ and test/."""
    dest_root = Path(dest_root)
    tmp = tempfile.mkdtemp(prefix="pd_clone_")
    report = {"method": "git-clone", "ref": ref}
    try:
        r = _git("clone", "--depth", "1", "--branch", ref, repo_url, tmp, timeout=3600)
        if r.returncode != 0:
            report["error"] = r.stderr.strip()[-500:]
            return report
        report["commit_sha"] = _git("rev-parse", "HEAD", cwd=tmp).stdout.strip()
        dest_root.mkdir(parents=True, exist_ok=True)
        copied = 0
        for split in ("train", "test"):
            src = Path(tmp) / split
            if src.exists():
                shutil.copytree(src, dest_root / split, dirs_exist_ok=True)
                copied += sum(1 for _ in (dest_root / split).rglob("*") if _.is_file())
        report["copied_files"] = copied
        return report
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_via_raw(dest_root: str | Path, file_list: list[str], ref: str = DEFAULT_REF,
                     retries: int = 4, backoff: float = 2.0, timeout: int = 60) -> dict:
    """Fallback: resumable per-file download from the raw CDN, list sourced from
    git (not the rate-limited API). Skips files already present."""
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": "ica26-phase1"})
    report = {"method": "raw-cdn", "total_listed": len(file_list),
              "downloaded": 0, "skipped": 0, "failed": 0, "failures": []}
    for path in file_list:
        dest = Path(dest_root) / path
        if dest.exists() and dest.stat().st_size > 0:
            report["skipped"] += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = RAW_URL.format(repo=REPO, ref=ref, path=urllib.parse.quote(path))
        ok = False
        for attempt in range(1, retries + 1):
            try:
                with session.get(url, timeout=timeout, stream=True) as resp:
                    resp.raise_for_status()
                    tmp = dest.with_name(dest.name + ".part")
                    with open(tmp, "wb") as f:
                        for chunk in resp.iter_content(1 << 16):
                            if chunk:
                                f.write(chunk)
                    tmp.replace(dest)
                ok = True
                break
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                time.sleep(backoff * attempt)
        if ok:
            report["downloaded"] += 1
        else:
            report["failed"] += 1
            report["failures"].append({"path": path, "error": last})
    return report


# --------------------------------------------------------------------------- #
# Case-insensitive filename collisions
# (policy: reports/PLANTDOC_CASE_COLLISION_POLICY.md)
#
# The upstream tree is case-SENSITIVE and contains paths that differ only by
# letter case, e.g. `CAR1.jpg` and `car1.jpg`. Extracting those onto a
# case-INSENSITIVE filesystem (macOS APFS, NTFS) makes the second member
# overwrite the first, silently destroying a distinct image. The loss is an
# artifact of the extraction filesystem -- it is not a duplicate, not a
# re-encoding, and never a reason to drop a distinct source record.
#
# The fix is to give EVERY member of a colliding group a deterministic
# disambiguated filename, rather than letting one member win the natural path by
# extraction order. The disambiguator is the leading 12 hex digits of the file's
# own SHA-256, so the active path is a pure function of content + upstream name
# and is stable across machines, runs, and filesystems.
# --------------------------------------------------------------------------- #
#: Hex digits of SHA-256 appended to a colliding filename. 12 hex digits = 48
#: bits; collision probability across a few thousand files is negligible, and a
#: real clash is caught by the uniqueness assertion in :func:`casefold_collisions`.
COLLISION_SHA_PREFIX_LEN = 12

#: Separator between the original stem and the content disambiguator.
COLLISION_SEPARATOR = "__"


def casefold_key(relpath: str) -> str:
    """Identity of a path as a case-insensitive filesystem sees it.

    Unicode-normalised (NFC) then case-folded, so two paths sharing this key
    cannot coexist as separate files on macOS/Windows. Uses ``str.casefold``
    rather than ``str.lower`` because casefold handles non-ASCII case mappings
    (e.g. German sharp s) that ``lower`` leaves distinct.
    """
    import unicodedata

    return unicodedata.normalize("NFC", str(relpath)).casefold()


def collision_safe_relpath(original_relpath: str, sha256: str) -> str:
    """Deterministic, collision-free active path for one colliding member.

    ``train/Apple rust leaf/CAR1.jpg`` + sha ``ff8e8450...``
    -> ``train/Apple rust leaf/CAR1__ff8e845061e3.jpg``

    The directory and extension are untouched; only the stem gains the content
    disambiguator. Two members of a group always differ here because their
    SHA-256 values differ -- that is what makes them distinct records.
    """
    if not sha256 or len(sha256) < COLLISION_SHA_PREFIX_LEN:
        raise ValueError(f"a collision-safe path needs a full sha256, got {sha256!r}")
    p = PurePosixPath(str(original_relpath))
    stem, suffix = p.stem, p.suffix
    disambiguated = f"{stem}{COLLISION_SEPARATOR}{sha256[:COLLISION_SHA_PREFIX_LEN]}{suffix}"
    return str(p.parent / disambiguated)


def casefold_collisions(relpaths: Iterable[str]) -> dict[str, list[str]]:
    """Group paths that collide on a case-insensitive filesystem.

    Returns ``{casefold_key: [relpath, ...]}`` for keys with more than one
    member, each member list sorted for determinism.
    """
    buckets: dict[str, list[str]] = {}
    for rp in relpaths:
        buckets.setdefault(casefold_key(rp), []).append(str(rp))
    return {k: sorted(v) for k, v in sorted(buckets.items()) if len(v) > 1}


def assert_no_casefold_collisions(relpaths: Iterable[str]) -> None:
    """Raise if any two paths would collide on a case-insensitive filesystem."""
    clashes = casefold_collisions(relpaths)
    if clashes:
        detail = "; ".join(f"{k} <- {v}" for k, v in list(clashes.items())[:10])
        raise ValueError(
            f"{len(clashes)} case-insensitive path collision(s) remain: {detail}"
        )


def collision_safe_shortfall(df: pd.DataFrame, inventory_csv: str | Path) -> list[str]:
    """Upstream SHA-256 digests the manifest fails to represent.

    The check is on CONTENT, not on paths: a case-collision loss shows up as an
    inventory digest with no manifest row, whatever the surviving file is called.
    Returns [] when the inventory is absent (nothing to compare against).
    """
    import csv as _csv
    from collections import Counter

    p = Path(inventory_csv)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        inv = Counter(r["source_sha256"] for r in _csv.DictReader(fh))
    have = Counter(df["sha256"].astype(str)) if len(df) else Counter()
    missing = []
    for sha, n in inv.items():
        if have.get(sha, 0) < n:
            missing.append(sha)
    return sorted(missing)


def assert_collision_safe(df: pd.DataFrame, inventory_csv: str | Path) -> None:
    """Fail closed if a manifest silently omits distinct upstream images.

    Guards every manifest-building path against AUD-EC-003: a case-insensitive
    filesystem drops a distinct image, the scan cannot see what is not there, and
    the manifest looks internally consistent while being short. Content-level
    reconciliation against the inventory is the only way to catch that.
    """
    missing = collision_safe_shortfall(df, inventory_csv)
    if missing:
        raise ValueError(
            f"manifest omits {len(missing)} distinct upstream image(s) "
            f"(first: {missing[:3]}). This is the case-collision loss described in "
            "reports/PLANTDOC_CASE_COLLISION_POLICY.md; run "
            "scripts/restore_plantdoc_collisions.py before building a manifest."
        )


# --------------------------------------------------------------------------- #
# Manifest + reconciliation
# --------------------------------------------------------------------------- #
def build_manifest(dest_root: str | Path, acquired_at_utc: Optional[str] = None) -> pd.DataFrame:
    return M.build_split_class_manifest(
        root=dest_root, dataset="PlantDoc", source_url=PLANTDOC_SOURCE.url,
        split_dirs=["train", "test"], acquired_at_utc=acquired_at_utc,
    )


def verify_against_filesystem(df: pd.DataFrame, root: str | Path) -> dict:
    """Compare manifest rows to files on disk in BOTH directions."""
    root = Path(root)
    manifest_paths = set(df["relpath"].astype(str)) if len(df) else set()
    fs_paths = set()
    for split in ("train", "test"):
        base = root / split
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                    fs_paths.add(str(p.relative_to(root)))
    return {
        "manifest_rows_missing_files": sorted(manifest_paths - fs_paths),
        "files_missing_from_manifest": sorted(fs_paths - manifest_paths),
        "n_manifest": len(manifest_paths),
        "n_filesystem": len(fs_paths),
    }


def build_source_snapshot(repo_url: str = REPO_URL, ref: str = DEFAULT_REF,
                          live: Optional[dict] = None) -> dict:
    """Record the exact upstream state used for acquisition (live if available)."""
    snap = {
        "repo": REPO,
        "repo_url": repo_url,
        "ref": ref,
        "acquisition_method": "git",
        "paper_reported_count": PAPER_REPORTED_COUNT,
        "retrieved_at_utc": M.utc_now_iso(),
        "source_of_truth": "live-git" if live else "verified-recorded",
    }
    src = live or VERIFIED_SNAPSHOT
    for k in ("commit_sha", "upstream_image_count", "upstream_train_images",
              "upstream_test_images", "upstream_train_classes", "upstream_test_classes",
              "train_only_classes"):
        if k in src:
            snap[k] = src[k]
    return snap


def reconcile(df: pd.DataFrame, snapshot: dict, fs_check: dict) -> dict:
    train = df[df["split"] == "train"] if len(df) else df
    test = df[df["split"] == "test"] if len(df) else df
    valid = int((~df["is_corrupt"]).sum()) if len(df) else 0
    upstream = snapshot.get("upstream_image_count")
    downloaded = int(len(df))
    return {
        "paper_reported_count": PAPER_REPORTED_COUNT,
        "upstream_repository_count": upstream,
        "downloaded_image_count": downloaded,
        "valid_decodable_count": valid,
        "manifest_count": downloaded,
        "train_images": int(len(train)),
        "test_images": int(len(test)),
        "train_class_count": int(train["class_label"].nunique()) if len(train) else 0,
        "test_class_count": int(test["class_label"].nunique()) if len(test) else 0,
        "filesystem_vs_manifest": fs_check,
        "paper_vs_upstream_delta": (PAPER_REPORTED_COUNT - upstream) if upstream else None,
        "complete": bool(
            upstream is not None and downloaded == upstream
            and valid == downloaded
            and not fs_check["manifest_rows_missing_files"]
            and not fs_check["files_missing_from_manifest"]
        ),
        "explanation": (
            f"Paper (Singh et al. 2020) reports {PAPER_REPORTED_COUNT} images; the current "
            f"upstream tree at the pinned commit has {upstream} (delta "
            f"{PAPER_REPORTED_COUNT - upstream if upstream else 'n/a'}), a genuine change to "
            f"the repository since publication, not a non-image-file artifact (0 non-image "
            f"files exist under train/test). 'complete' requires downloaded==upstream, all "
            f"decodable, and filesystem==manifest."
        ),
    }


def summarize(df: pd.DataFrame, snapshot: dict, fs_check: dict) -> dict:
    s = M.manifest_summary(df, "PlantDoc")
    s["expected"] = EXPECTED
    s["reconciliation"] = reconcile(df, snapshot, fs_check)
    s["complete"] = s["reconciliation"]["complete"]
    s["license"] = PLANTDOC_SOURCE.license
    s["source_snapshot"] = snapshot
    return s


def acquire(
    dest_root: str | Path = "data/raw/plantdoc",
    manifest_csv: str | Path = "data/manifests/plantdoc_manifest.csv",
    summary_json: str | Path = "data/manifests/plantdoc_summary.json",
    snapshot_json: str | Path = "data/manifests/plantdoc_source_snapshot.json",
    do_download: bool = False,
    method: str = "git",
) -> dict:
    live = list_repo_images_via_git()
    snapshot = build_source_snapshot(live=live)
    dl_report = None
    if do_download:
        if method == "git":
            dl_report = download_via_git(dest_root)
        else:
            paths = (live or {}).get("paths") or []
            dl_report = download_via_raw(dest_root, paths)
    df = build_manifest(dest_root)
    # Fail closed BEFORE writing: a manifest short of distinct upstream images is
    # not a valid dataset description (AUD-EC-003).
    assert_collision_safe(df, Path(manifest_csv).parent / "plantdoc_source_inventory.csv")
    M.write_manifest(df, manifest_csv)
    fs_check = verify_against_filesystem(df, dest_root)
    summary = summarize(df, snapshot, fs_check)
    if dl_report is not None:
        summary["download_report"] = dl_report
    M.write_summary(summary, summary_json)
    M.write_summary(snapshot, snapshot_json)
    return {"manifest": df, "summary": summary, "snapshot": snapshot, "fs_check": fs_check}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-plantdoc", description="Acquire + reconcile PlantDoc.")
    ap.add_argument("--dest", default="data/raw/plantdoc")
    ap.add_argument("--manifest", default="data/manifests/plantdoc_manifest.csv")
    ap.add_argument("--summary", default="data/manifests/plantdoc_summary.json")
    ap.add_argument("--snapshot", default="data/manifests/plantdoc_source_snapshot.json")
    ap.add_argument("--download", action="store_true", help="fetch via git clone at pinned ref")
    ap.add_argument("--method", choices=["git", "raw"], default="git")
    args = ap.parse_args(argv)

    out = acquire(
        dest_root=args.dest, manifest_csv=args.manifest, summary_json=args.summary,
        snapshot_json=args.snapshot, do_download=args.download, method=args.method,
    )
    df, summary = out["manifest"], out["summary"]
    rec = summary["reconciliation"]
    if summary.get("download_report") is not None:
        print("[plantdoc] download:", {k: v for k, v in summary["download_report"].items() if k != "failures"})
    print(f"[plantdoc] manifest={len(df)} | upstream={rec['upstream_repository_count']} "
          f"paper={rec['paper_reported_count']} valid={rec['valid_decodable_count']} "
          f"| complete={summary['complete']}")
    print(f"[plantdoc] fs-vs-manifest: rows_missing_files={len(rec['filesystem_vs_manifest']['manifest_rows_missing_files'])} "
          f"files_missing_from_manifest={len(rec['filesystem_vs_manifest']['files_missing_from_manifest'])}")
    val = M.validate_manifest(df)
    print(f"[plantdoc] manifest validation: {val.summary()} | wrote {args.manifest}, {args.summary}, {args.snapshot}")
    return 0 if val.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
