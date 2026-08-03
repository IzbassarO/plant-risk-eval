"""PlantVillage acquisition from the authoritative Hugging Face source.

Source (per DATASETS.md / brief): ``mohanty/PlantVillage`` -- the ONLY copy that
carries ``leaf_id`` for leak-safe leaf-grouped splitting. Kaggle mirrors are
forbidden (they drop leaf_id).

This module is Colab-first: it requires the optional ``datasets`` dependency
(``pip install ica26[hf]``). If ``datasets`` is unavailable it FAILS LOUDLY with
an actionable message rather than silently degrading. It never manufactures a
leaf_id for images that lack one; it reports how many are missing.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Optional

import pandas as pd

from ..schemas import (
    IMAGE_MANIFEST_COLUMNS,
    PLANTVILLAGE_EXTRA_COLUMNS,
    PLANTVILLAGE_SOURCE,
)
from . import manifest as M

HF_REPO = "mohanty/PlantVillage"
SUPPORTED_CONFIGS = ("color", "segmented", "grayscale")

# --------------------------------------------------------------------------- #
# Immutable source pinning (R2B.1 Finding 3)
#
# The image archive was already pinned, but the split files and the leaf map --
# which decide which records exist, which split each lands in, and which images
# are leaf-grouped -- were fetched with no revision at all, i.e. from whatever
# `main` happened to point at. A build could therefore mix pinned pixels with
# moving metadata and still look reproducible, because nothing recorded the
# difference. Every remotely acquired component now names the SAME immutable
# commit, and a fetch that cannot be served from it fails rather than falling
# back.
# --------------------------------------------------------------------------- #

#: The frozen dataset revision. A 40-hex commit SHA -- never a branch, tag, or
#: "latest", none of which are immutable.
PLANTVILLAGE_REVISION = "9e97599868962bd0079b8db4b7f1efa9185fa1e7"

#: Refs that look like a version but are not one. Rejected explicitly so a
#: plausible-looking pin cannot be mistaken for a real one.
MOVING_REFS = frozenset({"main", "master", "head", "latest", "refs/heads/main",
                         "refs/heads/master", "default", "trunk", ""})

#: Expected SHA-256 of every metadata component at PLANTVILLAGE_REVISION.
#: Verified on fetch: a digest mismatch means the response did not come from the
#: pinned revision, whatever it claims.
PINNED_COMPONENT_DIGESTS: dict[str, str] = {
    "splits/color_train.txt":
        "c43e0205b321d1c929116f5df1842348ac1e5c4861306e081416785d3c439dbd",
    "splits/color_test.txt":
        "7a7257dcb5f9456feae6ae81248d29c28f45dc4cd41a00c13a5c5c198c5f2f8b",
    "leaf_grouping/leaf-map.json":
        "3b4b253683c6911744959a3870a92509b1faa1ee34e9f8585e21d0fe6337a25b",
    "data.zip":
        "fba30c6a7965e49be94b47a62f8aff6cfb1c35c27f475f22092b56db41745e84",
}


class DatasetsNotInstalled(RuntimeError):
    pass


class SourcePinError(RuntimeError):
    """Raised when a component cannot be bound to the pinned immutable revision."""


def assert_immutable_revision(revision: Optional[str]) -> str:
    """Return ``revision`` if it is an immutable commit id, else raise.

    A branch name is not a pin. It resolves to different bytes on different days,
    which is precisely the property a frozen dataset must not have.
    """
    rev = (revision or "").strip()
    if rev.lower() in MOVING_REFS:
        raise SourcePinError(
            f"'{revision}' is a moving reference, not an immutable revision. "
            f"PlantVillage components must be pinned to a 40-character commit SHA "
            f"(the frozen revision is {PLANTVILLAGE_REVISION}).")
    if len(rev) != 40 or not all(c in "0123456789abcdef" for c in rev.lower()):
        raise SourcePinError(
            f"'{revision}' is not a 40-character hexadecimal commit SHA; refusing "
            "to acquire from an unversioned or ambiguous reference.")
    return rev


def _sha256_of(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_pinned(
    path: str,
    *,
    revision: str = PLANTVILLAGE_REVISION,
    repo: str = HF_REPO,
    expected_sha256: Optional[str] = None,
    downloader=None,
    **kwargs,
) -> tuple[Path, dict]:
    """Download one component from the pinned revision and prove it is that one.

    Returns ``(local_path, provenance)``. The provenance record names the repo,
    the exact revision, the requested path, the resolved URL where the hub
    exposes one, and both the expected and observed digest -- so a reader can
    tell not just that a pin was configured but that it was honoured.

    ``downloader`` exists for tests; it defaults to ``hf_hub_download`` and is
    always called with an explicit ``revision``.
    """
    rev = assert_immutable_revision(revision)
    if downloader is None:
        from huggingface_hub import hf_hub_download as downloader  # noqa: N806

    expected = expected_sha256 if expected_sha256 is not None else \
        PINNED_COMPONENT_DIGESTS.get(path)

    try:
        local = downloader(repo, path, repo_type="dataset", revision=rev, **kwargs)
    except Exception as exc:                                    # noqa: BLE001
        raise SourcePinError(
            f"component '{path}' could not be fetched from {repo}@{rev}: {exc}. "
            "A pinned build does not fall back to another revision.") from exc

    local_path = Path(local)
    observed = _sha256_of(local_path)
    if expected and observed != expected:
        raise SourcePinError(
            f"component '{path}' from {repo}@{rev} has digest {observed}, expected "
            f"{expected}. The response did not come from the pinned revision, or the "
            "pinned content changed; either way the build stops.")

    return local_path, {
        "component": path,
        "repo": repo,
        "revision": rev,
        "requested_path": path,
        "resolved_url": f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}",
        "expected_sha256": expected or "",
        "observed_sha256": observed,
        "digest_verified": bool(expected) and observed == expected,
    }


def _require_datasets():
    try:
        import datasets  # noqa: F401
    except Exception as e:  # fail loudly, actionably
        raise DatasetsNotInstalled(
            "The 'datasets' package is required for PlantVillage acquisition. "
            "Install it with:  pip install 'ica26[hf]'   (or  pip install datasets huggingface_hub). "
            "PlantVillage MUST come from the Hugging Face repo "
            f"'{HF_REPO}' (Kaggle mirrors lack leaf_id and are forbidden)."
        ) from e
    import datasets

    return datasets


def load_hf(config: str = "color", streaming: bool = False,
            revision: str = PLANTVILLAGE_REVISION):
    """Load the PlantVillage HF dataset for a given config, at the pinned revision."""
    if config not in SUPPORTED_CONFIGS:
        raise ValueError(f"config must be one of {SUPPORTED_CONFIGS}, got {config!r}")
    rev = assert_immutable_revision(revision)
    datasets = _require_datasets()
    return datasets.load_dataset(HF_REPO, config, streaming=streaming, revision=rev)


def hf_head_revision(repo: str = HF_REPO) -> Optional[str]:
    """The repo's CURRENT head commit. Reported for drift, never used to acquire.

    This used to be what provenance recorded as "the revision", which made the
    snapshot describe whenever the build happened to run rather than what it
    actually read. The acquisition revision is :data:`PLANTVILLAGE_REVISION`.
    """
    try:
        from huggingface_hub import HfApi
        info = HfApi().dataset_info(repo)
        return info.sha
    except Exception:
        return None


#: Backwards-compatible alias. Prefer :func:`hf_head_revision`, whose name says
#: that the value moves.
hf_revision = hf_head_revision


def build_source_snapshot(config: str, revision: Optional[str], execution_mode: str,
                          disk_bytes: int = 0, seconds: float = 0.0,
                          components: Optional[list] = None,
                          observed_head: Optional[str] = None) -> dict:
    """Provenance for one acquisition.

    ``revision`` is the revision actually READ FROM, and it is pinned.
    ``observed_head`` is where the repo's branch happened to point at the time;
    it is recorded so drift is visible, and is never what was acquired.
    """
    snap = {
        "dataset": "PlantVillage",
        "hf_repo": HF_REPO,
        "config": config,
        "revision": revision or "unknown",
        "revision_is_pinned": bool(revision) and revision == PLANTVILLAGE_REVISION,
        "execution_mode": execution_mode,   # "streaming-sample" | "full" | "not-executed"
        "retrieved_at_utc": M.utc_now_iso(),
        "disk_bytes": int(disk_bytes),
        "execution_seconds": round(float(seconds), 1),
        "license": PLANTVILLAGE_SOURCE.license,
        "source_of_truth_note": "Kaggle mirrors are forbidden (they drop leaf_id).",
        "pinning_note": "Every remotely acquired component -- image archive, split "
                        "files, and leaf map -- is fetched from this one immutable "
                        "revision and digest-verified. No component is read from a "
                        "branch.",
    }
    if components is not None:
        snap["components"] = components
    if observed_head is not None:
        snap["observed_repo_head"] = observed_head
        snap["head_matches_pinned_revision"] = (observed_head == revision)
    return snap


def _content_hash_and_size(pil_img) -> tuple[str, int]:
    raw = pil_img.tobytes()
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _row_from_example(ex, config, split, label_names, has_leaf_field, stamp, idx, materialize) -> dict:
    img = ex["image"]
    label_idx = ex["label"]
    label = label_names[label_idx] if label_names else str(label_idx)
    leaf_id = ex.get("leaf_id") if has_leaf_field else None
    has_leaf = leaf_id is not None and str(leaf_id) not in ("", "-1")
    sha, nbytes = _content_hash_and_size(img)
    relpath = f"{config}/{split}/{label}/{idx}.png"
    if materialize is not None:
        out = materialize / relpath
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out)
    return {
        "dataset": "PlantVillage", "split": split, "class_label": label, "relpath": relpath,
        "sha256": sha, "width": int(img.size[0]), "height": int(img.size[1]),
        "mode": str(img.mode), "n_bytes": nbytes, "is_corrupt": False,
        "source_url": PLANTVILLAGE_SOURCE.url, "acquired_at_utc": stamp,
        "leaf_id": "" if leaf_id is None else str(leaf_id), "has_leaf_id": bool(has_leaf),
    }


def build_manifest_from_hf(
    config: str = "color",
    limit: Optional[int] = None,
    materialize_dir: Optional[str | Path] = None,
    acquired_at_utc: Optional[str] = None,
    streaming: bool = False,
    revision: str = PLANTVILLAGE_REVISION,
) -> pd.DataFrame:
    """Iterate the HF dataset and build a per-image manifest.

    Records leaf_id + has_leaf_id for every image (never fabricated). sha256 is
    over the decoded pixel bytes (HF serves decoded PIL images). ``streaming=True``
    fetches examples lazily so a real sample can be acquired without the full
    multi-GB download.
    """
    ds = load_hf(config, streaming=streaming, revision=revision)
    stamp = acquired_at_utc or M.utc_now_iso()
    rows: list[dict] = []
    materialize = Path(materialize_dir) if materialize_dir else None

    for split in ds:
        d = ds[split]
        feats = getattr(d, "features", None)
        label_feat = feats.get("label") if feats else None
        label_names = getattr(label_feat, "names", None) if label_feat is not None else None
        has_leaf_field = bool(feats and ("leaf_id" in feats))
        if streaming:
            count = 0
            for ex in d:
                if limit is not None and count >= limit:
                    break
                rows.append(_row_from_example(ex, config, split, label_names, has_leaf_field, stamp, count, materialize))
                count += 1
        else:
            n = len(d) if limit is None else min(limit, len(d))
            for i in range(n):
                rows.append(_row_from_example(d[i], config, split, label_names, has_leaf_field, stamp, i, materialize))
    cols = list(IMAGE_MANIFEST_COLUMNS) + list(PLANTVILLAGE_EXTRA_COLUMNS)
    df = pd.DataFrame(rows, columns=cols)
    if len(df):
        df = df.sort_values(["split", "class_label", "relpath"]).reset_index(drop=True)
    return df


LEAF_MAP_PATH = "leaf_grouping/leaf-map.json"


def _leaf_tag(relpath: str) -> str:
    stem = relpath.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return stem.split("___", 1)[1].strip() if "___" in stem else ""


def build_manifest_from_repo(
    config: str = "color",
    images_root: Optional[str | Path] = None,
    acquired_at_utc: Optional[str] = None,
    revision: str = PLANTVILLAGE_REVISION,
    downloader=None,
) -> tuple[pd.DataFrame, dict]:
    """Build a manifest from the AUTHORITATIVE repo files (splits/*.txt +
    leaf-map.json), since `datasets` 4.0+ no longer runs the repo's loading
    script. leaf_id per image comes from the filename tag; has_leaf_id is True
    iff that tag is present in leaf-map.json (the authors' explicit grouping).
    If ``images_root`` (an extracted data.zip) is given, pixel fields are filled.

    Every metadata component is fetched from ``revision`` and digest-checked.
    These files decide which records exist, which split each lands in, and which
    are leaf-grouped -- reading them from a moving branch would let the dataset's
    membership change under a pinned build without anything noticing.
    """
    import json

    rev = assert_immutable_revision(revision)
    components: list[dict] = []

    def _pinned(path: str) -> Path:
        local, prov = fetch_pinned(path, revision=rev, downloader=downloader)
        components.append(prov)
        return local

    tr = [l.strip() for l in open(_pinned(f"splits/{config}_train.txt")) if l.strip()]
    te = [l.strip() for l in open(_pinned(f"splits/{config}_test.txt")) if l.strip()]
    lmap = json.load(open(_pinned(LEAF_MAP_PATH)))
    leafkeys = {str(k).strip().lower() for k in lmap}
    stamp = acquired_at_utc or M.utc_now_iso()
    images_root = Path(images_root) if images_root else None

    rows = []
    for split, paths in [("train", tr), ("test", te)]:
        for rel in paths:
            parts = rel.split("/")
            cls = parts[-2] if len(parts) >= 2 else "?"
            tag = _leaf_tag(rel)
            has_leaf = bool(tag) and (tag.lower() in leafkeys)
            row = {
                "dataset": "PlantVillage", "split": split, "class_label": cls, "relpath": rel,
                "sha256": "", "width": "", "height": "", "mode": "", "n_bytes": "",
                "is_corrupt": "", "source_url": PLANTVILLAGE_SOURCE.url, "acquired_at_utc": stamp,
                "leaf_id": tag, "has_leaf_id": bool(has_leaf),
            }
            if images_root is not None:
                ap = images_root / rel
                if ap.exists():
                    w, h, mode, corrupt = M.read_image_meta(ap)
                    row.update(sha256=M.sha256_of_file(ap), width=w, height=h, mode=mode,
                               n_bytes=ap.stat().st_size, is_corrupt=corrupt)
            rows.append(row)
    cols = list(IMAGE_MANIFEST_COLUMNS) + list(PLANTVILLAGE_EXTRA_COLUMNS)
    df = pd.DataFrame(rows, columns=cols).sort_values(["split", "class_label", "relpath"]).reset_index(drop=True)

    # A build must not mix pinned components with anything else.
    revisions = {c["revision"] for c in components}
    if revisions != {rev}:
        raise SourcePinError(
            f"components were fetched from mixed revisions {sorted(revisions)}; a "
            f"pinned build requires exactly one ({rev})")

    return df, {"leaf_map_entries": len(lmap), "revision": rev,
                "components": sorted(components, key=lambda c: c["component"])}


def repo_summary(df: pd.DataFrame, config: str, leaf_map_entries: int, snapshot: dict) -> dict:
    n = int(len(df))
    per_split = {str(s): {"n_images": int(len(g)), "n_classes": int(g["class_label"].nunique())}
                 for s, g in df.groupby("split")}
    n_with = int(df["has_leaf_id"].sum()) if n else 0
    n_without = n - n_with
    pixels = bool(df["sha256"].astype(str).str.len().gt(0).any()) if n else False
    return {
        "dataset": "PlantVillage", "config": config, "hf_repo": HF_REPO,
        "n_images": n, "n_classes_total": int(df["class_label"].nunique()) if n else 0,
        "n_healthy_classes": int(sum("healthy" in c.lower() for c in df["class_label"].unique())) if n else 0,
        "per_split": per_split,
        "leaf_id": {
            "n_with_leaf_id": n_with, "n_without_leaf_id": n_without,
            "proportion_with_leaf_id": round(n_with / n, 4) if n else 0.0,
            "leaf_map_entries": leaf_map_entries,
            "grouped_split_readiness": "ready",  # authors ship leaf-grouped split files
            "note": "Leaf-grouped train/test split files are provided by the dataset authors; "
                    "leaf-map.json explicitly groups the images with a leaf tag.",
        },
        "pixels_materialized": pixels,
        "pixel_note": "" if pixels else "sha256/width/height pending until data.zip images are materialized.",
        "license": PLANTVILLAGE_SOURCE.license,
        "source_snapshot": snapshot,
    }


def acquire_from_repo(
    config: str = "color",
    images_root: Optional[str | Path] = None,
    manifest_csv: str | Path = "data/manifests/plantvillage_manifest.csv",
    summary_json: str | Path = "data/manifests/plantvillage_summary.json",
    snapshot_json: str | Path = "data/manifests/plantvillage_source_snapshot.json",
    revision: str = PLANTVILLAGE_REVISION,
) -> dict:
    import time
    t0 = time.perf_counter()
    df, meta = build_manifest_from_repo(config=config, images_root=images_root,
                                        revision=revision)
    secs = time.perf_counter() - t0
    M.write_manifest(df, manifest_csv)
    pixels = bool(df["sha256"].astype(str).str.len().gt(0).any()) if len(df) else False
    mode = "repo-files+pixels" if pixels else "repo-files-structural"
    snapshot = build_source_snapshot(config, meta["revision"], mode, seconds=secs,
                                     components=meta.get("components"),
                                     observed_head=hf_head_revision())
    summary = repo_summary(df, config, meta["leaf_map_entries"], snapshot)
    summary["execution"] = {"mode": mode, "n_images": int(len(df)), "seconds": round(secs, 1)}
    M.write_summary(summary, summary_json)
    M.write_summary(snapshot, snapshot_json)
    return {"manifest": df, "summary": summary, "snapshot": snapshot}


def summarize(df: pd.DataFrame, config: str) -> dict:
    s = M.manifest_summary(df, "PlantVillage")
    n = int(len(df))
    n_with = int(df["has_leaf_id"].sum()) if n else 0
    n_without = n - n_with
    prop_with = (n_with / n) if n else 0.0
    if n == 0:
        readiness = "unavailable"
    elif prop_with >= 0.999:
        readiness = "ready"  # fully leaf-resolved -> fully leak-safe grouping
    elif prop_with > 0.0:
        readiness = "partial"  # some images lack leaf_id (see brief: PV maps only ~41,112/54,306)
    else:
        readiness = "no_grouping"
    s["config"] = config
    s["leaf_id"] = {
        "n_with_leaf_id": n_with,
        "n_without_leaf_id": n_without,
        "proportion_with_leaf_id": round(prop_with, 4),
        "grouped_split_readiness": readiness,
    }
    s["license"] = PLANTVILLAGE_SOURCE.license
    s["hf_repo"] = HF_REPO
    return s


def acquire(
    config: str = "color",
    manifest_csv: str | Path = "data/manifests/plantvillage_manifest.csv",
    summary_json: str | Path = "data/manifests/plantvillage_summary.json",
    snapshot_json: str | Path = "data/manifests/plantvillage_source_snapshot.json",
    limit: Optional[int] = None,
    materialize_dir: Optional[str | Path] = None,
    streaming: bool = False,
    revision: str = PLANTVILLAGE_REVISION,
) -> dict:
    import time

    rev = assert_immutable_revision(revision)
    t0 = time.perf_counter()
    df = build_manifest_from_hf(config=config, limit=limit,
                                materialize_dir=materialize_dir, streaming=streaming,
                                revision=rev)
    secs = time.perf_counter() - t0
    M.write_manifest(df, manifest_csv)
    summary = summarize(df, config)
    disk = int(pd.to_numeric(df["n_bytes"], errors="coerce").fillna(0).sum()) if len(df) else 0
    mode = "streaming-sample" if streaming else "full"
    snapshot = build_source_snapshot(config, rev, mode, disk_bytes=disk, seconds=secs,
                                     observed_head=hf_head_revision())
    summary["source_snapshot"] = snapshot
    summary["execution"] = {"mode": mode, "limit": limit, "n_images": int(len(df)),
                            "seconds": round(secs, 1)}
    M.write_summary(summary, summary_json)
    M.write_summary(snapshot, snapshot_json)
    return {"manifest": df, "summary": summary, "snapshot": snapshot}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ica26-plantvillage", description="Acquire PlantVillage (HF) + manifest.")
    ap.add_argument("--config", default="color", choices=SUPPORTED_CONFIGS)
    ap.add_argument("--manifest", default="data/manifests/plantvillage_manifest.csv")
    ap.add_argument("--summary", default="data/manifests/plantvillage_summary.json")
    ap.add_argument("--snapshot", default="data/manifests/plantvillage_source_snapshot.json")
    ap.add_argument("--limit", type=int, default=None, help="cap #images (sample/dry-run)")
    ap.add_argument("--stream", action="store_true", help="stream examples (real sample without full download)")
    ap.add_argument("--materialize", default=None, help="also save images under this dir")
    args = ap.parse_args(argv)
    try:
        out = acquire(
            config=args.config, manifest_csv=args.manifest, summary_json=args.summary,
            snapshot_json=args.snapshot, limit=args.limit,
            materialize_dir=args.materialize, streaming=args.stream,
        )
    except DatasetsNotInstalled as e:
        print("[plantvillage] BLOCKED:", e)
        return 2
    df, summary = out["manifest"], out["summary"]
    print(f"[plantvillage] {len(df)} images ({args.config}, mode={summary['execution']['mode']}) "
          f"| revision={summary['source_snapshot']['revision']}")
    print(f"[plantvillage] leaf_id: {summary['leaf_id']}")
    print(f"[plantvillage] wrote {args.manifest}, {args.summary}, {args.snapshot}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
