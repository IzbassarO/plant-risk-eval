#!/usr/bin/env python
"""Phase-1 data completion driver (local + Colab).

Single orchestrator that both the local shell and the Colab fallback notebook
call, so there is exactly one implementation of the data-completion logic.

Steps (each independently selectable via --steps):
  plantdoc     resume PlantDoc to the frozen upstream snapshot (commit 5467f601),
               resumable per-file raw-CDN download, rebuild manifest + reconcile.
  plantvillage materialize PlantVillage *color* pixels from the authoritative HF
               data.zip (revision 9e975998), fill sha256/dims/corrupt, verify.
  leakage      cross-dataset perceptual-hash comparison (PlantVillage color =
               training source, PlantDoc = evaluation) + duplicate disposition.
  gate         (re)generate reports/leakage_gate.json (fail-closed).
  checks       run scripts/run_phase1_checks.sh.
  package      zip reports + manifests + indexes + exclusions (NEVER raw images).

No count is forced. Nothing is fabricated. leaf_id is preserved when present and
left missing when absent. This module contains no personal paths or credentials;
all locations are derived from --repo-dir / --data-dir.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

# --------------------------------------------------------------------------- #
# Frozen source revisions (authoritative; see PROJECT_BRIEF.md / remediation).
# --------------------------------------------------------------------------- #
PLANTDOC_COMMIT = "5467f6012d78d1c446145d5f582da6096f852ae8"
PLANTDOC_REPO_URL = "https://github.com/pratikkayal/PlantDoc-Dataset.git"
PLANTVILLAGE_REPO = "mohanty/PlantVillage"
PLANTVILLAGE_REV = "9e97599868962bd0079b8db4b7f1efa9185fa1e7"
PHASH_THRESHOLD = 6  # brief §8.4 / reviewed leakage config; do not silently change.


def log(msg: str) -> None:
    print(f"[phase1-data] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# PlantDoc
# --------------------------------------------------------------------------- #
def _git(*args, cwd=None, timeout=1800):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def list_plantdoc_at_commit(commit: str = PLANTDOC_COMMIT) -> dict | None:
    """Authoritative image list at the *frozen commit* (not just HEAD).

    Blobless clone + fetch the exact commit + ls-tree, so the file set is pinned
    even if the upstream default branch later moves. Returns None on failure.
    """
    from ica26.schemas import IMAGE_EXTENSIONS

    tmp = tempfile.mkdtemp(prefix="pd_meta_")
    try:
        if _git("clone", "--filter=blob:none", "--no-checkout", PLANTDOC_REPO_URL, tmp,
                timeout=600).returncode != 0:
            return None
        # Ensure the exact commit is present, then enumerate its tree.
        _git("fetch", "--filter=blob:none", "origin", commit, cwd=tmp, timeout=600)
        tree = _git("ls-tree", "-r", commit, "--name-only", cwd=tmp)
        if tree.returncode != 0:
            return None
        paths = [p for p in tree.stdout.splitlines()
                 if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS
                 and (p.startswith("train/") or p.startswith("test/"))]

        def classes(prefix):
            return sorted({p.split("/")[1] for p in paths
                           if p.startswith(prefix) and len(p.split("/")) >= 3})

        return {
            "commit_sha": commit,
            "paths": sorted(paths),
            "upstream_image_count": len(paths),
            "upstream_train_images": sum(p.startswith("train/") for p in paths),
            "upstream_test_images": sum(p.startswith("test/") for p in paths),
            "upstream_train_classes": len(classes("train/")),
            "upstream_test_classes": len(classes("test/")),
            "train_only_classes": sorted(set(classes("train/")) - set(classes("test/"))),
        }
    except Exception as e:  # pragma: no cover - network dependent
        log(f"PlantDoc listing error: {type(e).__name__}: {e}")
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def step_plantdoc(data_dir: Path, do_download: bool = True) -> dict:
    from ica26.datasets import plantdoc as PD

    dest = data_dir / "raw" / "plantdoc"
    man_dir = data_dir / "manifests"
    dest.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    # Clean stale .part temp files from interrupted writes (never leave partials).
    for p in dest.rglob("*.part"):
        log(f"removing stale partial: {p.name}")
        p.unlink()

    live = list_plantdoc_at_commit(PLANTDOC_COMMIT)
    if do_download:
        if not live:
            log("PlantDoc: could not enumerate upstream tree (network?). Skipping download.")
        else:
            paths = live["paths"]
            present = sum(1 for r in paths if (dest / r).exists() and (dest / r).stat().st_size > 0)
            log(f"PlantDoc: {present}/{len(paths)} present; resuming {len(paths) - present} missing "
                f"(pinned to {PLANTDOC_COMMIT[:8]})")
            t0 = time.perf_counter()
            rep = PD.download_via_raw(dest, paths, ref=PLANTDOC_COMMIT, retries=5, backoff=2.0, timeout=60)
            log(f"PlantDoc download: +{rep['downloaded']} skipped={rep['skipped']} "
                f"failed={rep['failed']} in {time.perf_counter() - t0:.0f}s")

    # Rebuild manifest/summary/snapshot + reconciliation from the filesystem.
    out = PD.acquire(
        dest_root=dest,
        manifest_csv=man_dir / "plantdoc_manifest.csv",
        summary_json=man_dir / "plantdoc_summary.json",
        snapshot_json=man_dir / "plantdoc_source_snapshot.json",
        do_download=False,
    )
    rec = out["summary"]["reconciliation"]
    log(f"PlantDoc: manifest={rec['manifest_count']} valid={rec['valid_decodable_count']} "
        f"upstream={rec['upstream_repository_count']} complete={out['summary']['complete']}")
    return {"summary": out["summary"], "reconciliation": rec}


# --------------------------------------------------------------------------- #
# PlantVillage (color pixel materialization)
# --------------------------------------------------------------------------- #
def _find_images_root(extract_dir: Path, sample_rel: str) -> Path | None:
    """Locate the directory D such that D/<sample_rel> exists."""
    if (extract_dir / sample_rel).exists():
        return extract_dir
    tail = Path(sample_rel)
    for cand in extract_dir.rglob(tail.name):
        # walk up len(tail.parts) levels to the notional root
        root = cand
        for _ in range(len(tail.parts)):
            root = root.parent
        if (root / sample_rel).exists():
            return root
    return None


def step_plantvillage(data_dir: Path, config: str = "color", do_download: bool = True) -> dict:
    from huggingface_hub import hf_hub_download
    from ica26.datasets import plantvillage as PV
    from ica26.datasets import manifest as M

    pv_root = data_dir / "raw" / "plantvillage"
    hf_dir = pv_root / "_hf"
    extract_dir = pv_root / "extracted"
    man_dir = data_dir / "manifests"
    for d in (hf_dir, extract_dir, man_dir):
        d.mkdir(parents=True, exist_ok=True)

    acq_cmd = (f"hf_hub_download('{PLANTVILLAGE_REPO}','data.zip',repo_type='dataset',"
               f"revision='{PLANTVILLAGE_REV}')")
    t0 = time.perf_counter()
    if do_download:
        log("PlantVillage: downloading data.zip (authoritative HF; ~2 GB, resumable)")
        zip_path = hf_hub_download(PLANTVILLAGE_REPO, "data.zip", repo_type="dataset",
                                   revision=PLANTVILLAGE_REV, local_dir=str(hf_dir))
    else:
        zip_path = str(hf_dir / "data.zip")
        if not Path(zip_path).exists():
            raise FileNotFoundError(f"data.zip not present at {zip_path}; run with download enabled")

    # Determine the color relpaths from the authoritative split files.
    tr = hf_hub_download(PLANTVILLAGE_REPO, f"splits/{config}_train.txt", repo_type="dataset",
                         revision=PLANTVILLAGE_REV)
    sample_rel = next(l.strip() for l in open(tr) if l.strip())

    # Extract only the requested config's members (keeps disk down).
    log(f"PlantVillage: extracting '{config}' members from data.zip")
    with zipfile.ZipFile(zip_path) as zf:
        members = [n for n in zf.namelist() if (f"/{config}/" in n or n.startswith(f"{config}/"))
                   and not n.endswith("/")]
        if not members:  # unknown layout -> extract all, then locate
            zf.extractall(extract_dir)
        else:
            zf.extractall(extract_dir, members=members)
    images_root = _find_images_root(extract_dir, sample_rel)
    if images_root is None:
        raise RuntimeError(f"could not locate images root for sample '{sample_rel}' under {extract_dir}")
    log(f"PlantVillage: images_root={images_root}")

    out = PV.acquire_from_repo(
        config=config, images_root=images_root,
        manifest_csv=man_dir / "plantvillage_manifest.csv",
        summary_json=man_dir / "plantvillage_summary.json",
        snapshot_json=man_dir / "plantvillage_source_snapshot.json",
    )
    df = out["manifest"]
    secs = time.perf_counter() - t0

    # Independent verification + enrichment of the summary.
    import pandas as pd
    n = len(df)
    has_sha = df["sha256"].astype(str).str.len().eq(64)
    n_pixels = int(has_sha.sum())
    n_bytes = pd.to_numeric(df["n_bytes"], errors="coerce").fillna(0)
    n_corrupt = int((df["is_corrupt"].astype(str).str.lower() == "true").sum())
    zero_byte = int((n_bytes == 0).sum())
    dup_paths = df["relpath"][df["relpath"].duplicated()].tolist()

    # Deterministic decode + sha samples (>=100 each).
    order = df.sort_values("relpath").reset_index(drop=True)
    step = max(1, n // 100)
    sample_idx = list(range(0, n, step))[:max(100, 0)] if n else []
    if len(sample_idx) < min(100, n):
        sample_idx = list(range(min(100, n)))
    from PIL import Image
    decode_ok = sha_ok = sha_checked = 0
    for i in sample_idx:
        row = order.iloc[i]
        ap = images_root / row["relpath"]
        try:
            with Image.open(ap) as im:
                im.verify()
            decode_ok += 1
        except Exception:
            pass
        if str(row["sha256"]):
            sha_checked += 1
            if M.sha256_of_file(ap) == row["sha256"]:
                sha_ok += 1

    disk_bytes = int(sum(f.stat().st_size for f in images_root.rglob("*") if f.is_file()))
    summary = out["summary"]
    summary["pixel_verification"] = {
        "filesystem_image_count": int(sum(1 for _ in images_root.rglob("*") if _.is_file())),
        "manifest_rows": n,
        "pixels_materialized_count": n_pixels,
        "valid_decodable_count": n - n_corrupt,
        "n_corrupt": n_corrupt,
        "zero_byte_files": zero_byte,
        "duplicate_relpaths": dup_paths[:50],
        "duplicate_relpath_count": len(dup_paths),
        "decode_sample_size": len(sample_idx),
        "decode_sample_ok": decode_ok,
        "sha_sample_size": sha_checked,
        "sha_sample_ok": sha_ok,
    }
    summary["acquisition_command"] = acq_cmd
    summary["execution_seconds"] = round(secs, 1)
    summary["disk_bytes"] = disk_bytes
    summary["source_revision"] = PLANTVILLAGE_REV
    M.write_summary(summary, man_dir / "plantvillage_summary.json")
    log(f"PlantVillage: rows={n} pixels={n_pixels} corrupt={n_corrupt} "
        f"decode {decode_ok}/{len(sample_idx)} sha {sha_ok}/{sha_checked} "
        f"leaf_id+={int(df['has_leaf_id'].astype(str).str.lower().eq('true').sum())}")
    return {"summary": summary, "images_root": str(images_root)}


# --------------------------------------------------------------------------- #
# Cross-dataset leakage + duplicate disposition
# --------------------------------------------------------------------------- #
def step_leakage(data_dir: Path, repo_dir: Path, pv_images_root: Path,
                 threshold: int = PHASH_THRESHOLD) -> dict:
    import pandas as pd
    from ica26.leakage.phash import index_from_manifest, find_duplicates

    man_dir = data_dir / "manifests"
    reports = repo_dir / "reports"
    excl_dir = data_dir / "exclusions"
    reports.mkdir(parents=True, exist_ok=True)
    excl_dir.mkdir(parents=True, exist_ok=True)

    pv_man = man_dir / "plantvillage_manifest.csv"
    pd_man = man_dir / "plantdoc_manifest.csv"
    pd_root = data_dir / "raw" / "plantdoc"

    log("leakage: indexing PlantVillage (color, training source)")
    idx_train, skip_train = index_from_manifest(pv_man, pv_images_root, "PlantVillage")
    log("leakage: indexing PlantDoc (evaluation source)")
    idx_eval, skip_eval = index_from_manifest(pd_man, pd_root, "PlantDoc")

    # Persist portable indexes for return.
    interim = data_dir / "interim"
    interim.mkdir(parents=True, exist_ok=True)
    idx_train.to_csv(interim / "phash_index_plantvillage.csv", index=False)
    idx_eval.to_csv(interim / "phash_index_plantdoc.csv", index=False)

    res = find_duplicates(idx_train, idx_eval, threshold=threshold)
    hmap_a = dict(zip(idx_train["path"], idx_train["phash"]))
    hmap_b = dict(zip(idx_eval["path"], idx_eval["phash"]))

    def rows(df, classification):
        out = []
        for _, r in df.iterrows():
            pending = classification == "near"
            out.append({
                "training_relpath": r["path_a"],
                "evaluation_relpath": r["path_b"],
                "training_class": r["class_a"],
                "evaluation_class": r["class_b"],
                "training_phash": hmap_a.get(r["path_a"], ""),
                "evaluation_phash": hmap_b.get(r["path_b"], ""),
                "hamming_distance": int(r["distance"]),
                "classification": classification,
                "review_status": "pending" if pending else "exact_auto_flagged",
                "proposed_disposition": ("manual_review_required" if pending
                                         else "exclude_evaluation_image"),
                "notes": ("near-duplicate (0<d<=%d); NOT auto-excluded, awaits human review" % threshold
                          if pending else
                          "exact perceptual-hash match (d=0); proposed exclusion from evaluation set"),
            })
        return out

    all_rows = rows(res["exact"], "exact") + rows(res["near"], "near")
    cols = ["training_relpath", "evaluation_relpath", "training_class", "evaluation_class",
            "training_phash", "evaluation_phash", "hamming_distance", "classification",
            "review_status", "proposed_disposition", "notes"]
    pairs_df = pd.DataFrame(all_rows, columns=cols)
    if len(pairs_df):
        pairs_df = pairs_df.sort_values(
            ["classification", "hamming_distance", "training_relpath", "evaluation_relpath"]
        ).reset_index(drop=True)
    pairs_csv = reports / "leakage_plantvillage_vs_plantdoc_pairs.csv"
    pairs_df.to_csv(pairs_csv, index=False)

    n_exact = int(res["summary"]["n_exact_pairs"])
    n_near = int(res["summary"]["n_near_pairs"])
    n_pending = n_near  # near pairs remain pending until human review

    summary = {
        "training_dataset": "PlantVillage",
        "training_config": "color",
        "evaluation_dataset": "PlantDoc",
        "phash_algorithm": res["summary"]["phash_algorithm"],
        "hash_size_bits": res["summary"]["hash_size_bits"],
        "threshold": threshold,
        "n_training_indexed": int(len(idx_train)),
        "n_evaluation_indexed": int(len(idx_eval)),
        "skipped_training": len(skip_train),
        "skipped_evaluation": len(skip_eval),
        "skipped_training_paths": skip_train[:50],
        "skipped_evaluation_paths": skip_eval[:50],
        "n_exact_pairs": n_exact,
        "n_near_pairs": n_near,
        "n_pending_review": n_pending,
        "self_pairs": 0,
        "reversed_duplicates": 0,
        "pairs_csv": str(pairs_csv.relative_to(repo_dir)) if str(pairs_csv).startswith(str(repo_dir)) else str(pairs_csv),
    }
    summary_json = reports / "leakage_plantvillage_vs_plantdoc_summary.json"
    summary_json.write_text(json.dumps(summary, indent=2))

    # ---- Duplicate disposition ----
    # Exact cross-dataset duplicates -> proposed exclusion of the EVALUATION image.
    excl_rows = []
    for _, r in res["exact"].iterrows():
        excl_rows.append({
            "evaluation_dataset": "PlantDoc",
            "evaluation_relpath": r["path_b"],
            "evaluation_class": r["class_b"],
            "training_dataset": "PlantVillage",
            "training_relpath": r["path_a"],
            "training_class": r["class_a"],
            "hamming_distance": int(r["distance"]),
            "reason": "exact cross-dataset perceptual-hash duplicate with a training image",
            "provenance": f"{res['summary']['phash_algorithm']} d=0 vs PlantVillage color @ {PLANTVILLAGE_REV[:8]}",
            "action": "propose_exclude_from_evaluation",
            "status": "proposed",
        })
    excl_df = pd.DataFrame(excl_rows, columns=[
        "evaluation_dataset", "evaluation_relpath", "evaluation_class",
        "training_dataset", "training_relpath", "training_class",
        "hamming_distance", "reason", "provenance", "action", "status"])
    if len(excl_df):
        excl_df = excl_df.sort_values(["evaluation_relpath", "training_relpath"]).reset_index(drop=True)
    excl_csv = excl_dir / "cross_dataset_exact_exclusions.csv"
    excl_df.to_csv(excl_csv, index=False)

    # Near duplicates -> human review manifest (pending). If none, say so.
    review_md = reports / "CROSS_DATASET_NEAR_DUPLICATE_REVIEW.md"
    lines = [
        "# Cross-Dataset Near-Duplicate Review",
        "",
        f"**Training source:** PlantVillage (color) @ `{PLANTVILLAGE_REV}`  ",
        f"**Evaluation source:** PlantDoc @ `{PLANTDOC_COMMIT}`  ",
        f"**Algorithm / threshold:** {res['summary']['phash_algorithm']} / Hamming ≤ {threshold}  ",
        "",
        "Near-duplicates (0 < Hamming ≤ threshold) are **not** automatically treated "
        "as true duplicates. Each pair below is `review_status=pending` and must be "
        "adjudicated by a human before the leakage gate may pass.",
        "",
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
    review_md.write_text("\n".join(lines))

    log(f"leakage: exact={n_exact} near={n_near} pending={n_pending} "
        f"skipped_train={len(skip_train)} skipped_eval={len(skip_eval)}")
    return {"summary": summary, "n_exact": n_exact, "n_near": n_near,
            "n_pending": n_pending, "n_excluded": len(excl_df),
            "skipped": len(skip_train) + len(skip_eval),
            "pv_images_root": str(pv_images_root)}


def step_gate(data_dir: Path, repo_dir: Path, pv_images_root: Path,
              threshold: int = PHASH_THRESHOLD, excluded_pairs: int = 0) -> dict:
    from ica26.leakage.gate import compute_gate

    man_dir = data_dir / "manifests"
    excl_dir = data_dir / "exclusions"
    gate, _ = compute_gate(
        training_manifest=man_dir / "plantvillage_manifest.csv",
        training_root=pv_images_root, training_dataset="PlantVillage",
        evaluation_manifest=man_dir / "plantdoc_manifest.csv",
        evaluation_root=data_dir / "raw" / "plantdoc", evaluation_dataset="PlantDoc",
        threshold=threshold, excluded_pair_count=excluded_pairs,
        near_duplicate_review=excl_dir / "cross_dataset_near_duplicate_review.csv",
        reviewed_exclusions=excl_dir / "cross_dataset_reviewed_exclusions.csv",
        provenance={"command": "run_phase1_data_completion.py:gate",
                    "training_config": "color"},
    )
    gate.write(repo_dir / "reports" / "leakage_gate.json")
    log(f"gate: status={gate.status} exact={gate.exact_duplicate_count} "
        f"near={gate.near_duplicate_count} resolved={gate.resolved_pair_count} "
        f"unresolved={gate.unresolved_pair_count}")
    return {"status": gate.status}


def step_checks(repo_dir: Path) -> int:
    script = repo_dir / "scripts" / "run_phase1_checks.sh"
    env = dict(os.environ, PYTHON=sys.executable)
    r = subprocess.run(["bash", str(script)], cwd=str(repo_dir), env=env)
    log(f"checks: exit={r.returncode}")
    return r.returncode


def step_package(data_dir: Path, repo_dir: Path, out_zip: Path) -> Path:
    """Package ONLY reports + manifests + indexes + exclusions. Never raw images."""
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    include = [
        repo_dir / "reports",
        data_dir / "manifests",
        data_dir / "interim",
        data_dir / "exclusions",
        data_dir / "mapping",
    ]
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for base in include:
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if not f.is_file():
                    continue
                # Never package image bytes.
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".zip"}:
                    continue
                zf.write(f, f.relative_to(repo_dir) if str(f).startswith(str(repo_dir))
                         else Path("data") / f.relative_to(data_dir))
    log(f"package: wrote {out_zip}")
    return out_zip


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_phase1_data_completion")
    ap.add_argument("--repo-dir", default=".", help="repository root")
    ap.add_argument("--data-dir", default=None, help="persistent data dir (default: <repo>/data)")
    ap.add_argument("--steps", default="all",
                    help="comma list of: plantdoc,plantvillage,leakage,gate,checks,package (or 'all')")
    ap.add_argument("--threshold", type=int, default=PHASH_THRESHOLD)
    ap.add_argument("--no-download", action="store_true",
                    help="use already-present raw data; do not fetch")
    ap.add_argument("--package-out", default=None)
    args = ap.parse_args(argv)

    repo_dir = Path(args.repo_dir).resolve()
    data_dir = Path(args.data_dir).resolve() if args.data_dir else (repo_dir / "data")
    steps = ("plantdoc", "plantvillage", "leakage", "gate", "checks", "package") \
        if args.steps == "all" else tuple(s.strip() for s in args.steps.split(",") if s.strip())
    do_download = not args.no_download
    log(f"repo_dir={repo_dir} data_dir={data_dir} steps={steps} download={do_download}")

    state: dict = {"pv_images_root": data_dir / "raw" / "plantvillage" / "extracted"}

    if "plantdoc" in steps:
        state["plantdoc"] = step_plantdoc(data_dir, do_download=do_download)
    if "plantvillage" in steps:
        pv = step_plantvillage(data_dir, config="color", do_download=do_download)
        state["plantvillage"] = pv
        state["pv_images_root"] = Path(pv["images_root"])
    if "leakage" in steps:
        state["leakage"] = step_leakage(data_dir, repo_dir, state["pv_images_root"], args.threshold)
    if "gate" in steps:
        excluded = state.get("leakage", {}).get("n_excluded", 0)
        state["gate"] = step_gate(data_dir, repo_dir, state["pv_images_root"],
                                  args.threshold, excluded_pairs=excluded)
    if "checks" in steps:
        state["checks_exit"] = step_checks(repo_dir)
    if "package" in steps:
        out = Path(args.package_out).resolve() if args.package_out else \
            (repo_dir / "reports" / "phase1_data_completion_return.zip")
        step_package(data_dir, repo_dir, out)

    log("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
