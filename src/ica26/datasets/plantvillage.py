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

#: Machine-readable persisted-provenance contract.  ``components`` used by
#: earlier snapshots described a useful fetch log, but did not itself establish
#: that a materialized manifest came from every pinned component.  A Dataset V1
#: artifact now records the complete source chain under this versioned schema.
PROVENANCE_SCHEMA_VERSION = "ica26.plantvillage.acquisition-provenance/1"

#: Byte counts recorded from the immutable source revision.  They are an
#: additional provenance cross-check, not a replacement for SHA-256.  The
#: archive count was measured from the retained, digest-verified local archive;
#: the small metadata files were independently fetched from their immutable
#: resolve URLs when this record was migrated.
PINNED_COMPONENT_BYTE_COUNTS: dict[str, int] = {
    "data.zip": 2_184_723_441,
    "splits/color_train.txt": 4_151_500,
    "splits/color_test.txt": 1_018_650,
    "leaf_grouping/leaf-map.json": 2_429_879,
}

PERSISTED_PROVENANCE_FIELDS = (
    "schema_version",
    "dataset",
    "immutable_revision",
    "source_components",
    "all_components_pinned",
    "all_component_digests_verified",
    "pixels_materialized",
    "manifest_digest",
    "generated_from_pinned_sources",
)


def _is_sha256(value: object) -> bool:
    value = str(value or "").strip().lower()
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _source_locator(repo: str, revision: str, path: str) -> str:
    return f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}"


def _component_is_pinned(component: object, *, name: str, revision: str) -> bool:
    if not isinstance(component, dict):
        return False
    return (
        component.get("component") == name
        and component.get("source_repository") == HF_REPO
        and component.get("immutable_revision") == revision
        and component.get("source_path") == name
    )


def validate_component_provenance(
    components: object,
    *,
    revision: str = PLANTVILLAGE_REVISION,
    required_components: Optional[set[str]] = None,
) -> list[str]:
    """Validate the recorded immutable-source chain for a materialized build.

    A configured revision is not provenance.  For a future auditor to establish
    what actually entered a manifest, every remotely read component must name
    the frozen repository/revision and reproduce the digest fixed in this module.
    The return value is deliberately a list of concrete defects rather than a
    boolean so callers can report a fail-closed reason without guessing.

    ``required_components`` is useful for structural (metadata-only) callers;
    a pixel-materialized Dataset V1 build uses the complete pinned component
    set: archive, train split, test split, and leaf map.
    """
    required = set(required_components or PINNED_COMPONENT_DIGESTS)
    problems: list[str] = []
    if not isinstance(components, list):
        return ["source component provenance is not a list"]

    by_name: dict[str, dict] = {}
    for i, component in enumerate(components):
        if not isinstance(component, dict):
            problems.append(f"component entry {i} is not an object")
            continue
        name = str(component.get("component") or "").strip()
        if not name:
            problems.append(f"component entry {i} has no component name")
            continue
        if name in by_name:
            problems.append(f"component '{name}' is recorded more than once")
            continue
        by_name[name] = component

    missing = sorted(required - set(by_name))
    if missing:
        problems.append(f"missing required pinned component(s): {missing}")
    unexpected = sorted(set(by_name) - set(PINNED_COMPONENT_DIGESTS))
    if unexpected:
        problems.append(f"unrecognised pinned component(s): {unexpected}")

    for name in sorted(required & set(by_name)):
        component = by_name[name]
        expected = PINNED_COMPONENT_DIGESTS.get(name)
        if expected is None:
            problems.append(f"component '{name}' has no pinned expected SHA-256")
            continue
        if component.get("source_repository") != HF_REPO:
            problems.append(
                f"component '{name}' names source_repository "
                f"{component.get('source_repository')!r}, not {HF_REPO!r}")
        if component.get("immutable_revision") != revision:
            problems.append(
                f"component '{name}' names immutable_revision "
                f"{component.get('immutable_revision')!r}, "
                f"not pinned {revision!r}")
        if component.get("source_path") != name:
            problems.append(f"component '{name}' has no matching repository-relative source_path")
        locator = str(component.get("resolved_locator") or "")
        if locator != _source_locator(HF_REPO, revision, name):
            problems.append(f"component '{name}' has no immutable resolved_locator")
        if component.get("expected_sha256") != expected:
            problems.append(f"component '{name}' does not record its pinned expected SHA-256")
        if component.get("observed_sha256") != expected:
            problems.append(f"component '{name}' observed SHA-256 does not match the pinned bytes")
        if component.get("digest_verified") is not True:
            problems.append(f"component '{name}' is not marked digest_verified=true")
        if component.get("verification_status") != "verified":
            problems.append(f"component '{name}' does not record verification_status='verified'")
        expected_bytes = PINNED_COMPONENT_BYTE_COUNTS.get(name)
        if component.get("byte_count") != expected_bytes:
            problems.append(
                f"component '{name}' byte_count {component.get('byte_count')!r} "
                f"does not match pinned byte count {expected_bytes!r}")
    return problems


def validate_persisted_provenance(
    provenance: object,
    *,
    manifest_path: Optional[str | Path] = None,
) -> list[str]:
    """Validate a persisted Dataset V1 PlantVillage provenance artifact.

    This validates the machine-readable artifact itself, not merely a runtime
    configuration flag.  A true ``pixels_materialized`` boolean alone is never
    sufficient: the exact manifest bytes must reconcile to a complete,
    digest-verified immutable source chain.
    """
    if not isinstance(provenance, dict):
        return ["persisted PlantVillage provenance is not a JSON object"]

    problems: list[str] = []
    missing = [key for key in PERSISTED_PROVENANCE_FIELDS if key not in provenance]
    if missing:
        problems.append(f"persisted provenance omits required field(s): {missing}")
    if provenance.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        problems.append("persisted provenance has an unrecognised schema_version")
    if provenance.get("dataset") != "PlantVillage":
        problems.append("persisted provenance does not identify dataset='PlantVillage'")
    if provenance.get("immutable_revision") != PLANTVILLAGE_REVISION:
        problems.append("persisted provenance immutable_revision is not the PlantVillage pin")
    if provenance.get("all_components_pinned") is not True:
        problems.append("persisted provenance all_components_pinned is not true")
    if provenance.get("all_component_digests_verified") is not True:
        problems.append("persisted provenance all_component_digests_verified is not true")
    if provenance.get("pixels_materialized") is not True:
        problems.append("persisted provenance pixels_materialized is not true")
    if provenance.get("generated_from_pinned_sources") is not True:
        problems.append("persisted provenance generated_from_pinned_sources is not true")

    manifest_digest = provenance.get("manifest_digest")
    if not _is_sha256(manifest_digest):
        problems.append("persisted provenance manifest_digest is absent or malformed")
    elif manifest_path is not None:
        path = Path(manifest_path)
        if not path.is_file():
            problems.append("PlantVillage manifest required by provenance is absent")
        elif M.sha256_of_file(path) != str(manifest_digest).lower():
            problems.append("persisted provenance manifest_digest is stale")

    problems.extend(validate_component_provenance(provenance.get("source_components")))
    return problems


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

    verified = bool(expected) and observed == expected
    locator = _source_locator(repo, rev, path)
    return local_path, {
        # Versioned persisted-provenance keys.
        "component": path,
        "source_repository": repo,
        "immutable_revision": rev,
        "source_path": path,
        "resolved_locator": locator,
        "expected_sha256": expected or "",
        "observed_sha256": observed,
        "byte_count": int(local_path.stat().st_size),
        "digest_verified": verified,
        "verification_status": "verified" if verified else "unverified",
        # Compatibility aliases retained for existing non-freeze reports.
        "repo": repo,
        "revision": rev,
        "requested_path": path,
        "resolved_url": locator,
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
                          observed_head: Optional[str] = None,
                          pixels_materialized: bool = False,
                          manifest_digest: Optional[str] = None) -> dict:
    """Provenance for one acquisition.

    ``revision`` is the revision actually READ FROM, and it is pinned.
    ``observed_head`` is where the repo's branch happened to point at the time;
    it is recorded so drift is visible, and is never what was acquired.
    """
    source_components = sorted((components or []), key=lambda c: str(c.get("component", ""))) \
        if isinstance(components, list) else []
    component_problems = validate_component_provenance(
        source_components, revision=revision or PLANTVILLAGE_REVISION)
    fully_pinned = bool(source_components) and not component_problems
    snap = {
        # Persisted, freeze-relevant provenance.  These fields are consumed by
        # ``validate_persisted_provenance``; do not infer them from a human-
        # readable note or a materialized-pixels boolean.
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "dataset": "PlantVillage",
        "immutable_revision": revision or "unknown",
        "source_components": source_components,
        "all_components_pinned": fully_pinned,
        "all_component_digests_verified": fully_pinned,
        "pixels_materialized": bool(pixels_materialized),
        "manifest_digest": manifest_digest or "",
        "generated_from_pinned_sources": bool(pixels_materialized) and fully_pinned
                                         and _is_sha256(manifest_digest),
        # Compatibility fields retained for ordinary acquisition diagnostics.
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
        snap["components"] = source_components
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
    archive_component: Optional[dict] = None,
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

    When pixel fields are materialized, ``archive_component`` is mandatory.  It
    is the digest-verified provenance record returned by :func:`fetch_pinned`
    for ``data.zip``.  Accepting an arbitrary image directory while recording a
    pinned metadata revision would make the source chain look reproducible when
    it was not, so that state is refused rather than described optimistically.
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
    if images_root is not None:
        if not isinstance(archive_component, dict):
            raise SourcePinError(
                "pixel materialization requires the digest-verified 'data.zip' "
                "provenance record; refusing an unbound images_root")
        archive_problems = validate_component_provenance(
            [archive_component], revision=rev, required_components={"data.zip"})
        if archive_problems:
            raise SourcePinError(
                "pixel archive provenance is not a verified frozen component: "
                + "; ".join(archive_problems))
        components.append(dict(archive_component))

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
    revisions = {c.get("immutable_revision") for c in components}
    if revisions != {rev}:
        raise SourcePinError(
            f"components were fetched from mixed revisions {sorted(revisions)}; a "
            f"pinned build requires exactly one ({rev})")

    required = set(PINNED_COMPONENT_DIGESTS) if images_root is not None else {
        f"splits/{config}_train.txt", f"splits/{config}_test.txt", LEAF_MAP_PATH,
    }
    provenance_problems = validate_component_provenance(
        components, revision=rev, required_components=required)
    if provenance_problems:
        raise SourcePinError(
            "component provenance is not a complete verified pinned source chain: "
            + "; ".join(provenance_problems))

    return df, {"leaf_map_entries": len(lmap), "revision": rev,
                "components": sorted(components, key=lambda c: c["component"])}


#: Versioned identity of the reconstruction check. Bump rather than editing
#: which columns count as identity -- that changes what "reconstructed" means.
MANIFEST_RECONSTRUCTION_SCHEMA = "ica26.plantvillage.manifest_reconstruction/1"

#: Columns a reconstruction independently derives from the pinned sources and
#: compares field-for-field. These are the manifest's SCIENTIFIC content: which
#: image, called what, on which side of the split, with what leaf grouping.
#:
#: Pixel-derived columns (sha256, width, height, mode, n_bytes, is_corrupt) are
#: deliberately excluded here and checked separately against the images on disk:
#: they describe the bytes, not the dataset's structure. ``acquired_at_utc`` is
#: acquisition metadata -- a re-acquisition is not a different dataset.
RECONSTRUCTED_IDENTITY_COLUMNS = (
    "dataset", "split", "class_label", "relpath", "leaf_id", "has_leaf_id",
)


def all_pixels_materialized(df: "pd.DataFrame") -> bool:
    """True only if EVERY record carries a full-length digest.

    This used to be ``.any()``, which meant one materialized image in a
    54,305-record manifest reported the whole dataset as materialized. It also
    used to accept ``len > 0`` in two of its three call sites, so a truncated or
    garbage digest counted. A Dataset V1 claim has to mean every record.
    """
    if df is None or not len(df):
        return False
    return bool(df["sha256"].astype(str).str.len().eq(64).all())


def reconstruct_manifest_identities(
    config: str = "color",
    *,
    revision: str = PLANTVILLAGE_REVISION,
    downloader=None,
) -> tuple[list[dict], dict]:
    """Derive every PlantVillage record from the pinned sources alone.

    This is the independent half of manifest validation. It reads the frozen
    split files and leaf map at the pinned revision and rebuilds the full record
    identity set from scratch, without consulting the persisted manifest at all.
    The expected record count is therefore a *result* of reconstruction rather
    than a number written down somewhere and trusted.

    That is what closes the forgery the audit found: a one-row manifest with a
    self-consistent digest passes every digest check, because a digest only
    proves a file has not changed since someone hashed it. Only re-deriving the
    contents proves the file is the right file.

    Returns ``(rows, meta)`` where rows are ordered exactly as the builder orders
    them, so the comparison is positional as well as set-based.
    """
    import json

    rev = assert_immutable_revision(revision)
    components: list[dict] = []

    def _pinned(path: str) -> Path:
        local, prov = fetch_pinned(path, revision=rev, downloader=downloader)
        components.append(prov)
        return local

    train_path = _pinned(f"splits/{config}_train.txt")
    test_path = _pinned(f"splits/{config}_test.txt")
    leaf_path = _pinned(LEAF_MAP_PATH)

    with open(train_path) as fh:
        train = [line.strip() for line in fh if line.strip()]
    with open(test_path) as fh:
        test = [line.strip() for line in fh if line.strip()]
    with open(leaf_path) as fh:
        leaf_map = json.load(fh)
    leafkeys = {str(k).strip().lower() for k in leaf_map}

    rows: list[dict] = []
    for split, paths in (("train", train), ("test", test)):
        for rel in paths:
            parts = rel.split("/")
            tag = _leaf_tag(rel)
            rows.append({
                "dataset": "PlantVillage",
                "split": split,
                "class_label": parts[-2] if len(parts) >= 2 else "?",
                "relpath": rel,
                "leaf_id": tag,
                "has_leaf_id": bool(tag) and (tag.lower() in leafkeys),
            })

    # Same ordering the builder applies, so a positional comparison is
    # meaningful and a reordered manifest is caught rather than sorted away.
    rows.sort(key=lambda r: (r["split"], r["class_label"], r["relpath"]))

    problems = validate_component_provenance(
        components, revision=rev,
        required_components={f"splits/{config}_train.txt",
                             f"splits/{config}_test.txt", LEAF_MAP_PATH})
    if problems:
        raise SourcePinError(
            "reconstruction sources are not a complete verified pinned chain: "
            + "; ".join(problems))

    meta = {
        "schema": MANIFEST_RECONSTRUCTION_SCHEMA,
        "config": config,
        "immutable_revision": rev,
        "leaf_map_entries": len(leaf_map),
        "n_train": len(train),
        "n_test": len(test),
        "n_records": len(rows),
        "source_components": sorted(
            (c["component"] for c in components)),
    }
    return rows, meta


def validate_manifest_reconstruction(
    manifest_path: str | Path,
    *,
    config: str = "color",
    revision: str = PLANTVILLAGE_REVISION,
    images_root: Optional[str | Path] = None,
    downloader=None,
    max_examples: int = 5,
) -> tuple[list[str], dict]:
    """Compare the persisted manifest against an independent reconstruction.

    Checks, in order of what each one catches:

    * **no missing rows / no additional rows** -- set difference on the record
      identity ``(split, relpath)``, which catches the fabricated one-row
      manifest, a deleted row, and an inserted row;
    * **no duplicated identities** -- the same image may not appear twice;
    * **exact values for every semantically relevant column** -- a changed
      class, split, or leaf metadata is a mismatch, not a rounding difference;
    * **deterministic ordering** -- the persisted row order must equal the
      reconstruction's canonical order;
    * **expected image presence** -- when ``images_root`` is given, every
      required image must exist and its recorded digest must match its bytes.

    Returns ``(problems, report)``. An empty problem list is the only pass.
    """
    path = Path(manifest_path)
    if not path.is_file():
        return ([f"PlantVillage manifest is absent at {path}"],
                {"schema": MANIFEST_RECONSTRUCTION_SCHEMA, "reconstructed": False})

    expected_rows, meta = reconstruct_manifest_identities(
        config, revision=revision, downloader=downloader)
    persisted = pd.read_csv(path, dtype=str, keep_default_na=False)

    problems: list[str] = []
    missing_columns = [c for c in RECONSTRUCTED_IDENTITY_COLUMNS
                       if c not in persisted.columns]
    if missing_columns:
        return ([f"persisted manifest is missing column(s): {missing_columns}"],
                {"schema": MANIFEST_RECONSTRUCTION_SCHEMA, "reconstructed": False,
                 "expected_records": len(expected_rows)})

    def _identity(row) -> tuple[str, str]:
        return (str(row["split"]), str(row["relpath"]))

    persisted_rows = persisted.to_dict("records")
    expected_index = {_identity(r): r for r in expected_rows}
    persisted_index: dict[tuple[str, str], dict] = {}
    duplicated: list[tuple[str, str]] = []
    for row in persisted_rows:
        key = _identity(row)
        if key in persisted_index:
            duplicated.append(key)
        persisted_index[key] = row

    missing = sorted(set(expected_index) - set(persisted_index))
    extra = sorted(set(persisted_index) - set(expected_index))
    if missing:
        problems.append(
            f"persisted manifest omits {len(missing)} reconstructed record(s), "
            f"e.g. {[m[1] for m in missing[:max_examples]]}")
    if extra:
        problems.append(
            f"persisted manifest contains {len(extra)} record(s) the pinned "
            f"sources do not produce, e.g. {[e[1] for e in extra[:max_examples]]}")
    if duplicated:
        problems.append(
            f"persisted manifest repeats {len(duplicated)} record identity(ies), "
            f"e.g. {[d[1] for d in duplicated[:max_examples]]}")

    mismatched: list[str] = []
    for key in sorted(set(expected_index) & set(persisted_index)):
        want, got = expected_index[key], persisted_index[key]
        for column in RECONSTRUCTED_IDENTITY_COLUMNS:
            expected_value = want[column]
            actual = str(got.get(column, ""))
            if column == "has_leaf_id":
                if actual.strip().lower() != str(bool(expected_value)).lower():
                    mismatched.append(
                        f"{key[1]}: {column} is '{actual}', reconstruction "
                        f"derives '{expected_value}'")
            elif actual != str(expected_value):
                mismatched.append(
                    f"{key[1]}: {column} is '{actual}', reconstruction derives "
                    f"'{expected_value}'")
    if mismatched:
        problems.append(
            f"{len(mismatched)} reconstructed value mismatch(es), e.g. "
            + "; ".join(mismatched[:max_examples]))

    ordered = (not missing and not extra and not duplicated
               and [_identity(r) for r in persisted_rows]
               == [_identity(r) for r in expected_rows])
    if not missing and not extra and not duplicated and not ordered:
        problems.append(
            "persisted manifest row order does not match the deterministic "
            "reconstruction order")

    pixels_report = {"checked": False, "verified": 0, "problems": 0}
    if images_root is not None:
        root = Path(images_root)
        absent: list[str] = []
        wrong: list[str] = []
        for row in persisted_rows:
            rel = str(row["relpath"])
            target = root / rel
            if not target.is_file():
                absent.append(rel)
                continue
            declared = str(row.get("sha256", ""))
            if len(declared) != 64:
                wrong.append(f"{rel}: no full-length digest recorded")
            elif M.sha256_of_file(target) != declared:
                wrong.append(f"{rel}: bytes do not match the recorded digest")
        pixels_report = {
            "checked": True,
            "verified": len(persisted_rows) - len(absent) - len(wrong),
            "problems": len(absent) + len(wrong),
        }
        if absent:
            problems.append(
                f"{len(absent)} required PlantVillage image(s) are absent, e.g. "
                f"{absent[:max_examples]}")
        if wrong:
            problems.append(
                f"{len(wrong)} PlantVillage image(s) do not match their recorded "
                f"identity, e.g. {wrong[:max_examples]}")

    # Digest completeness is a property of the manifest alone, so it is checked
    # whether or not the pixels are on this machine. Gating it behind
    # ``images_root`` meant a fresh clone -- which never has the raw tree --
    # accepted a manifest asserting 54,305 images while binding none of them.
    if not all_pixels_materialized(persisted):
        incomplete = int((persisted["sha256"].astype(str).str.len() != 64).sum())
        problems.append(
            f"{incomplete} persisted record(s) carry no full-length pixel "
            "digest; the manifest asserts images it does not bind")

    report = {
        "schema": MANIFEST_RECONSTRUCTION_SCHEMA,
        "reconstructed": True,
        "config": config,
        "immutable_revision": meta["immutable_revision"],
        "source_components": meta["source_components"],
        "leaf_map_entries": meta["leaf_map_entries"],
        # Derived, never hardcoded: this is what the pinned sources actually say.
        "expected_records": meta["n_records"],
        "expected_train": meta["n_train"],
        "expected_test": meta["n_test"],
        "persisted_records": len(persisted_rows),
        "missing_records": len(missing),
        "extra_records": len(extra),
        "duplicated_identities": len(duplicated),
        "value_mismatches": len(mismatched),
        "order_matches": bool(ordered),
        "manifest_sha256": M.sha256_of_file(path),
        "all_pixels_materialized": all_pixels_materialized(persisted),
        "pixel_verification": pixels_report,
        "equal": not problems,
    }
    return problems, report


def repo_summary(df: pd.DataFrame, config: str, leaf_map_entries: int, snapshot: dict) -> dict:
    n = int(len(df))
    per_split = {str(s): {"n_images": int(len(g)), "n_classes": int(g["class_label"].nunique())}
                 for s, g in df.groupby("split")}
    n_with = int(df["has_leaf_id"].sum()) if n else 0
    n_without = n - n_with
    pixels = all_pixels_materialized(df)
    summary = {
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
    # Persist the freeze-relevant source chain at the summary's top level too.
    # The standalone snapshot and summary must make the same claim, allowing an
    # auditor to detect a summary that was copied from a different acquisition.
    for field in PERSISTED_PROVENANCE_FIELDS:
        summary[field] = snapshot.get(field)
    return summary


def acquire_from_repo(
    config: str = "color",
    images_root: Optional[str | Path] = None,
    manifest_csv: str | Path = "data/manifests/plantvillage_manifest.csv",
    summary_json: str | Path = "data/manifests/plantvillage_summary.json",
    snapshot_json: str | Path = "data/manifests/plantvillage_source_snapshot.json",
    revision: str = PLANTVILLAGE_REVISION,
    archive_component: Optional[dict] = None,
    acquired_at_utc: Optional[str] = None,
) -> dict:
    import time
    t0 = time.perf_counter()
    df, meta = build_manifest_from_repo(config=config, images_root=images_root,
                                        revision=revision,
                                        archive_component=archive_component,
                                        acquired_at_utc=acquired_at_utc)
    secs = time.perf_counter() - t0
    M.write_manifest(df, manifest_csv)
    pixels = all_pixels_materialized(df)
    mode = "repo-files+pixels" if pixels else "repo-files-structural"
    components = meta.get("components") or []
    manifest_digest = M.sha256_of_file(manifest_csv)
    snapshot = build_source_snapshot(
        config, meta["revision"], mode, seconds=secs, components=components,
        observed_head=hf_head_revision(), pixels_materialized=pixels,
        manifest_digest=manifest_digest)
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
    pixels = all_pixels_materialized(df)
    snapshot = build_source_snapshot(config, rev, mode, disk_bytes=disk, seconds=secs,
                                     observed_head=hf_head_revision(),
                                     pixels_materialized=pixels,
                                     manifest_digest=M.sha256_of_file(manifest_csv))
    summary["source_snapshot"] = snapshot
    for field in PERSISTED_PROVENANCE_FIELDS:
        summary[field] = snapshot.get(field)
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
