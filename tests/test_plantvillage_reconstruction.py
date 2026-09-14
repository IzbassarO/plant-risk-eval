"""Exact PlantVillage manifest reconstruction (R2B.2 Part 5).

The persisted provenance strongly authenticated the *downloaded components*, and
then bound the manifest by its own SHA-256. The audit pointed out what that
misses: a digest proves a file has not changed since someone hashed it, and
nothing more. A fabricated one-row manifest with a self-consistent digest passed
every check, because no check ever asked what the file should contain.

The fix is to re-derive the answer. ``reconstruct_manifest_identities`` reads the
pinned split files and leaf map and rebuilds all 54,305 record identities from
scratch, so the expected record count is a *result* rather than a number written
down and trusted. These tests exercise that path against forgeries the digest
check alone would have accepted.

The pixel-materialization predicate is fixed here too: it used ``.any()``, so a
single materialized image in a 54,305-record manifest reported the whole dataset
as materialized.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from ica26.datasets import plantvillage as PV

PINNED = PV.PLANTVILLAGE_REVISION
IDENTITY_COLUMNS = PV.RECONSTRUCTED_IDENTITY_COLUMNS


# --------------------------------------------------------------------------- #
# A small pinned hub, so these tests need no network and no HF dependency
# --------------------------------------------------------------------------- #
@pytest.fixture
def hub(tmp_path):
    content = {
        "splits/color_train.txt": (
            "raw/color/Alpha___healthy/a___L1.jpg\n"
            "raw/color/Beta___blight/b___L2.jpg\n"
            "raw/color/Beta___blight/c___L3.jpg\n"
        ),
        "splits/color_test.txt": "raw/color/Alpha___healthy/d___L4.jpg\n",
        "leaf_grouping/leaf-map.json": json.dumps(
            {"l1": ["Alpha___healthy:::1.0"], "l2": ["Beta___blight:::2.0"]}),
        "data.zip": b"fake-pinned-plantvillage-archive",
    }
    pinned_dir = tmp_path / "pinned"
    for name, payload in content.items():
        p = pinned_dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(payload if isinstance(payload, bytes)
                      else payload.encode("utf-8"))

    def download(repo, path, repo_type=None, revision=None, **kw):
        if revision != PINNED:
            raise AssertionError(f"unpinned fetch of {path} at revision {revision}")
        target = pinned_dir / path
        if not target.exists():
            raise FileNotFoundError(path)
        return str(target)

    download.digests = {
        name: hashlib.sha256((pinned_dir / name).read_bytes()).hexdigest()
        for name in content}
    download.pinned_dir = pinned_dir
    return download


@pytest.fixture
def pinned_hub(hub, monkeypatch):
    monkeypatch.setattr(PV, "PINNED_COMPONENT_DIGESTS", dict(hub.digests))
    monkeypatch.setattr(
        PV, "PINNED_COMPONENT_BYTE_COUNTS",
        {name: (hub.pinned_dir / name).stat().st_size for name in hub.digests})
    return hub


@pytest.fixture
def manifest_frame(pinned_hub):
    """The authentic manifest the pinned sources produce."""
    rows, _ = PV.reconstruct_manifest_identities("color", downloader=pinned_hub)
    frame = pd.DataFrame(rows)
    # Everything is text, exactly as a manifest CSV round-trips it. Keeping a
    # native bool column here would make the tampering tests fight pandas dtypes
    # rather than exercise the validator.
    frame["has_leaf_id"] = frame["has_leaf_id"].map(lambda b: str(bool(b)))
    frame = frame.astype(str)
    frame["sha256"] = ["a" * 64] * len(frame)
    for column, value in (("width", "10"), ("height", "10"), ("mode", "RGB"),
                          ("n_bytes", "100"), ("is_corrupt", "False"),
                          ("source_url", "https://example.org"),
                          ("acquired_at_utc", "2026-07-30T07:43:13+00:00")):
        frame[column] = value
    return frame


def _write(frame: pd.DataFrame, tmp_path) -> "object":
    path = tmp_path / "plantvillage_manifest.csv"
    frame.to_csv(path, index=False)
    return path


def _validate(path, hub, **kw):
    return PV.validate_manifest_reconstruction(path, config="color",
                                               downloader=hub, **kw)


# --------------------------------------------------------------------------- #
# Reconstruction derives the answer rather than reading it
# --------------------------------------------------------------------------- #
def test_reconstruction_derives_records_from_the_pinned_sources(pinned_hub):
    rows, meta = PV.reconstruct_manifest_identities("color", downloader=pinned_hub)
    assert meta["n_records"] == len(rows) == 4
    assert meta["n_train"] == 3 and meta["n_test"] == 1
    assert meta["immutable_revision"] == PINNED
    assert {r["class_label"] for r in rows} == {"Alpha___healthy", "Beta___blight"}
    # Leaf metadata comes from the leaf map, not from the filename alone.
    by_path = {r["relpath"]: r for r in rows}
    assert by_path["raw/color/Alpha___healthy/a___L1.jpg"]["has_leaf_id"] is True
    assert by_path["raw/color/Alpha___healthy/d___L4.jpg"]["has_leaf_id"] is False


def test_reconstruction_is_deterministically_ordered(pinned_hub):
    first, _ = PV.reconstruct_manifest_identities("color", downloader=pinned_hub)
    second, _ = PV.reconstruct_manifest_identities("color", downloader=pinned_hub)
    assert first == second
    assert first == sorted(
        first, key=lambda r: (r["split"], r["class_label"], r["relpath"]))


def test_an_authentic_manifest_reconstructs_exactly(manifest_frame, pinned_hub, tmp_path):
    problems, report = _validate(_write(manifest_frame, tmp_path), pinned_hub)
    assert problems == []
    assert report["equal"] is True
    assert report["expected_records"] == report["persisted_records"] == 4
    assert report["missing_records"] == report["extra_records"] == 0
    assert report["value_mismatches"] == 0
    assert report["order_matches"] is True


# --------------------------------------------------------------------------- #
# The forgeries a digest check alone accepted
# --------------------------------------------------------------------------- #
def test_a_fabricated_one_row_manifest_is_refused(manifest_frame, pinned_hub, tmp_path):
    """The audit's exact adversary: self-consistent digest, wrong contents."""
    forged = manifest_frame.iloc[:1].copy()
    path = _write(forged, tmp_path)
    # Its digest is perfectly self-consistent -- that was always the point.
    assert len(hashlib.sha256(path.read_bytes()).hexdigest()) == 64

    problems, report = _validate(path, pinned_hub)
    assert problems
    assert report["missing_records"] == 3
    assert any("omits 3 reconstructed record" in p for p in problems)


def test_a_deleted_row_is_refused(manifest_frame, pinned_hub, tmp_path):
    truncated = manifest_frame.drop(manifest_frame.index[1]).reset_index(drop=True)
    problems, report = _validate(_write(truncated, tmp_path), pinned_hub)
    assert report["missing_records"] == 1
    assert any("omits 1 reconstructed record" in p for p in problems)


def test_an_added_row_is_refused(manifest_frame, pinned_hub, tmp_path):
    extra = manifest_frame.iloc[[0]].copy()
    extra["relpath"] = "raw/color/Alpha___healthy/invented___L9.jpg"
    padded = pd.concat([manifest_frame, extra], ignore_index=True)
    problems, report = _validate(_write(padded, tmp_path), pinned_hub)
    assert report["extra_records"] == 1
    assert any("the pinned sources do not produce" in p for p in problems)


def test_a_duplicated_identity_is_refused(manifest_frame, pinned_hub, tmp_path):
    doubled = pd.concat([manifest_frame, manifest_frame.iloc[[0]]], ignore_index=True)
    problems, report = _validate(_write(doubled, tmp_path), pinned_hub)
    assert report["duplicated_identities"] == 1
    assert any("repeats 1 record identity" in p for p in problems)


def test_a_changed_class_label_is_refused(manifest_frame, pinned_hub, tmp_path):
    tampered = manifest_frame.copy()
    tampered.loc[0, "class_label"] = "Alpha___blight"
    problems, report = _validate(_write(tampered, tmp_path), pinned_hub)
    assert report["value_mismatches"] >= 1
    assert any("class_label" in p for p in problems)


def test_a_changed_split_is_refused(manifest_frame, pinned_hub, tmp_path):
    tampered = manifest_frame.copy()
    test_row = tampered.index[tampered["split"] == "test"][0]
    tampered.loc[test_row, "split"] = "train"
    problems, report = _validate(_write(tampered, tmp_path), pinned_hub)
    # Moving a record across the split changes its identity, so it reads as one
    # record missing from test and one unexpected record in train.
    assert problems
    assert report["missing_records"] == 1 and report["extra_records"] == 1


def test_changed_leaf_metadata_is_refused(manifest_frame, pinned_hub, tmp_path):
    # Pick rows whose value actually differs from the tampered value, otherwise
    # the "tampering" is a no-op and the test proves nothing.
    leafed = manifest_frame.index[manifest_frame["has_leaf_id"] == "True"][0]
    for column, value, row in (("leaf_id", "NOT_THE_TAG", leafed),
                               ("has_leaf_id", "False", leafed)):
        tampered = manifest_frame.copy()
        tampered.loc[row, column] = value
        problems, report = _validate(_write(tampered, tmp_path), pinned_hub)
        assert report["value_mismatches"] >= 1, column
        assert any(column in p for p in problems), column


def test_a_reordered_manifest_is_refused(manifest_frame, pinned_hub, tmp_path):
    shuffled = manifest_frame.iloc[::-1].reset_index(drop=True)
    problems, report = _validate(_write(shuffled, tmp_path), pinned_hub)
    assert report["order_matches"] is False
    assert any("row order" in p for p in problems)


def test_an_absent_manifest_is_refused(pinned_hub, tmp_path):
    problems, report = _validate(tmp_path / "nope.csv", pinned_hub)
    assert problems and report["reconstructed"] is False


# --------------------------------------------------------------------------- #
# Image materialization must mean EVERY image
# --------------------------------------------------------------------------- #
def _materialize(frame, root, only_first=False):
    root.mkdir(parents=True, exist_ok=True)
    digests = []
    for i, rel in enumerate(frame["relpath"]):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = f"image-{i}".encode()
        if only_first and i > 0:
            digests.append(hashlib.sha256(payload).hexdigest())
            continue
        target.write_bytes(payload)
        digests.append(hashlib.sha256(payload).hexdigest())
    frame = frame.copy()
    frame["sha256"] = digests
    return frame


def test_every_required_image_must_be_present(manifest_frame, pinned_hub, tmp_path):
    root = tmp_path / "images"
    frame = _materialize(manifest_frame, root)
    problems, report = _validate(_write(frame, tmp_path), pinned_hub, images_root=root)
    assert problems == []
    assert report["pixel_verification"]["verified"] == 4
    assert report["pixel_verification"]["problems"] == 0


def test_one_present_image_does_not_make_the_dataset_materialized(
    manifest_frame, pinned_hub, tmp_path,
):
    """The `.any()` bug, stated as a test: 1 of 4 is not materialized."""
    root = tmp_path / "images"
    frame = _materialize(manifest_frame, root, only_first=True)
    problems, report = _validate(_write(frame, tmp_path), pinned_hub, images_root=root)
    assert problems
    assert report["pixel_verification"]["problems"] == 3
    assert any("required PlantVillage image(s) are absent" in p for p in problems)


def test_a_missing_image_fails_closed(manifest_frame, pinned_hub, tmp_path):
    root = tmp_path / "images"
    frame = _materialize(manifest_frame, root)
    (root / frame["relpath"].iloc[2]).unlink()
    problems, report = _validate(_write(frame, tmp_path), pinned_hub, images_root=root)
    assert problems
    assert report["pixel_verification"]["problems"] == 1


def test_an_image_that_does_not_match_its_digest_fails_closed(
    manifest_frame, pinned_hub, tmp_path,
):
    root = tmp_path / "images"
    frame = _materialize(manifest_frame, root)
    (root / frame["relpath"].iloc[0]).write_bytes(b"different bytes entirely")
    problems, _ = _validate(_write(frame, tmp_path), pinned_hub, images_root=root)
    assert any("do not match their recorded identity" in p for p in problems)


@pytest.mark.parametrize("digests,expected", [
    (["a" * 64] * 4, True),
    (["a" * 64, "a" * 64, "", "a" * 64], False),      # one absent
    ([""] * 4, False),
    (["a" * 63] * 4, False),                           # truncated, not 64 chars
    (["a" * 64, "", "", ""], False),                   # the `.any()` case
])
def test_all_pixels_materialized_requires_every_record(digests, expected):
    frame = pd.DataFrame({"sha256": digests})
    assert PV.all_pixels_materialized(frame) is expected


def test_all_pixels_materialized_is_false_for_an_empty_manifest():
    assert PV.all_pixels_materialized(pd.DataFrame({"sha256": []})) is False
    assert PV.all_pixels_materialized(None) is False


@pytest.mark.parametrize("bad", ["a" * 63, "", "   "])
def test_an_incomplete_digest_is_refused_without_the_pixels(
    manifest_frame, pinned_hub, tmp_path, bad,
):
    """Digest completeness is a property of the manifest, not of this machine.

    The check used to sit behind ``images_root``, so a fresh clone -- which
    never has the raw tree -- accepted a manifest asserting 54,305 images while
    binding none of them. ``problems`` was empty and ``equal`` was True.
    """
    tampered = manifest_frame.copy()
    tampered.loc[0, "sha256"] = bad
    problems, report = _validate(_write(tampered, tmp_path), pinned_hub)
    assert report["all_pixels_materialized"] is False
    assert report["equal"] is False
    assert any("no full-length pixel digest" in p for p in problems)


def test_a_complete_manifest_still_validates_without_the_pixels(
    manifest_frame, pinned_hub, tmp_path,
):
    """The guard must not fire on the honest case a fresh clone actually has."""
    problems, report = _validate(_write(manifest_frame, tmp_path), pinned_hub)
    assert problems == []
    assert report["all_pixels_materialized"] is True
    assert report["pixel_verification"]["checked"] is False


# --------------------------------------------------------------------------- #
# The real committed manifest
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    __import__("importlib").util.find_spec("huggingface_hub") is None,
    reason="pinned-source reconstruction needs the optional 'hf' extra")
def test_the_committed_manifest_reconstructs_all_54305_records(repo_root):
    """The live check, against the real pinned sources.

    Skipped when the optional `hf` extra is absent so a fresh clone with only
    the declared core dependencies still passes; the count below is asserted
    against reconstruction output, never used as its input.
    """
    manifest = repo_root / "data/manifests/plantvillage_manifest.csv"
    try:
        problems, report = PV.validate_manifest_reconstruction(
            manifest, config="color")
    except Exception as exc:  # noqa: BLE001 - offline/no-cache is not a failure
        pytest.skip(f"pinned sources unavailable: {type(exc).__name__}: {exc}")

    assert problems == []
    assert report["expected_records"] == 54_305
    assert report["persisted_records"] == 54_305
    assert report["expected_train"] == 43_596
    assert report["expected_test"] == 10_709
    assert report["missing_records"] == 0
    assert report["extra_records"] == 0
    assert report["duplicated_identities"] == 0
    assert report["value_mismatches"] == 0
    assert report["order_matches"] is True
    assert report["all_pixels_materialized"] is True
    assert report["manifest_sha256"] == (
        "b9acc43637ef2e930bd9e5e8a09b1d5025c720d65f9dd3fc9aabdfbd7e399591")
