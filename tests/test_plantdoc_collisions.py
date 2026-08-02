"""PlantDoc case-collision integrity (AUD-EC-003).

The upstream tree is case-sensitive; a case-insensitive filesystem silently
collapses paths differing only by letter case, so six DISTINCT images never
reached the active manifest. These tests pin the collision-safe layout and the
resulting 2,578-record dataset.

See reports/PLANTDOC_CASE_COLLISION_POLICY.md.
"""
from __future__ import annotations

import csv
from collections import Counter

import pandas as pd
import pytest

from ica26.datasets.plantdoc import (
    assert_collision_safe,
    assert_no_casefold_collisions,
    casefold_collisions,
    casefold_key,
    collision_safe_relpath,
    collision_safe_shortfall,
)

#: The six images the audit proved absent from the 2,572-row manifest.
SIX_RESTORED = {
    "ff8e845061e3": "train/Apple rust leaf/CAR1.jpg",
    "a488765c32aa": "train/Blueberry leaf/blueberry-leaf.jpg",
    "2e99aae9cb26": "train/Blueberry leaf/blueberry-leaves.jpg",
    "2c2cc7cec2c4": "train/Corn leaf blight/northern-corn-leaf-blight.jpg",
    "0571261a682b": "train/Peach leaf/peach-leaf.jpg",
    "0ea1317f5e20": ("train/Potato leaf early blight/potato-blight-phytophora-infestans-"
                     "close-up-of-infected-leaf-showing-a60hxn.jpg"),
}


@pytest.fixture(scope="module")
def manifest(repo_root):
    return list(csv.DictReader(
        open(repo_root / "data/manifests/plantdoc_manifest.csv", newline="", encoding="utf-8")))


@pytest.fixture(scope="module")
def inventory(repo_root):
    return list(csv.DictReader(
        open(repo_root / "data/manifests/plantdoc_source_inventory.csv",
             newline="", encoding="utf-8")))


@pytest.fixture(scope="module")
def collision_map(repo_root):
    return list(csv.DictReader(
        open(repo_root / "data/manifests/plantdoc_case_collision_mapping.csv",
             newline="", encoding="utf-8")))


# --------------------------------------------------------------------------- #
# Path primitives
# --------------------------------------------------------------------------- #
def test_casefold_key_is_case_insensitive():
    assert casefold_key("train/A/CAR1.jpg") == casefold_key("train/a/car1.JPG")


def test_casefold_key_normalises_unicode():
    # NFC vs NFD spelling of the same character must collide, as on APFS.
    assert casefold_key("a/é.jpg") == casefold_key("a/é.jpg")


def test_collision_safe_relpath_disambiguates_by_content():
    a = collision_safe_relpath("train/Apple rust leaf/CAR1.jpg", "ff8e845061e3aaaa" + "0" * 48)
    b = collision_safe_relpath("train/Apple rust leaf/car1.jpg", "da3a9af451c8bbbb" + "0" * 48)
    assert a == "train/Apple rust leaf/CAR1__ff8e845061e3.jpg"
    assert b == "train/Apple rust leaf/car1__da3a9af451c8.jpg"
    assert casefold_key(a) != casefold_key(b)   # the whole point


def test_collision_safe_relpath_preserves_directory_and_extension():
    out = collision_safe_relpath("train/Corn leaf blight/x.JPEG", "a" * 64)
    assert out.startswith("train/Corn leaf blight/")
    assert out.endswith(".JPEG")


def test_collision_safe_relpath_requires_a_real_digest():
    with pytest.raises(ValueError):
        collision_safe_relpath("a/b.jpg", "")


def test_casefold_collisions_groups_only_real_clashes():
    groups = casefold_collisions(["a/X.jpg", "a/x.jpg", "a/y.jpg"])
    assert len(groups) == 1
    assert sorted(next(iter(groups.values()))) == ["a/X.jpg", "a/x.jpg"]


def test_assert_no_casefold_collisions_raises_on_a_clash():
    with pytest.raises(ValueError):
        assert_no_casefold_collisions(["a/X.jpg", "a/x.jpg"])


# --------------------------------------------------------------------------- #
# The shipped dataset
# --------------------------------------------------------------------------- #
def test_inventory_holds_all_upstream_records(inventory):
    assert len(inventory) == 2578


def test_manifest_holds_all_upstream_records(manifest):
    assert len(manifest) == 2578


def test_manifest_sha_multiset_equals_inventory(manifest, inventory):
    """Bijection on CONTENT: nothing dropped, nothing invented, nothing doubled."""
    assert (Counter(r["sha256"] for r in manifest)
            == Counter(r["source_sha256"] for r in inventory))


def test_no_upstream_image_is_missing(manifest, repo_root):
    df = pd.DataFrame(manifest)
    missing = collision_safe_shortfall(
        df, repo_root / "data/manifests/plantdoc_source_inventory.csv")
    assert missing == []
    assert_collision_safe(df, repo_root / "data/manifests/plantdoc_source_inventory.csv")


def test_active_paths_have_no_casefold_collision(manifest):
    assert_no_casefold_collisions(r["relpath"] for r in manifest)


def test_split_and_class_totals(manifest):
    splits = Counter(r["split"] for r in manifest)
    assert splits == {"train": 2342, "test": 236}
    assert len({r["class_label"] for r in manifest if r["split"] == "train"}) == 28
    assert len({r["class_label"] for r in manifest if r["split"] == "test"}) == 27


def test_no_corrupt_or_zero_byte_images(manifest):
    assert not [r for r in manifest if str(r["is_corrupt"]).lower() == "true"]
    assert not [r for r in manifest if int(r["n_bytes"]) == 0]


@pytest.mark.parametrize("sha_prefix,upstream", sorted(SIX_RESTORED.items()))
def test_each_previously_missing_image_is_present_exactly_once(
        manifest, collision_map, sha_prefix, upstream):
    rows = [r for r in manifest if r["sha256"].startswith(sha_prefix)]
    assert len(rows) == 1, f"{upstream} is not represented exactly once"
    mapped = [m for m in collision_map if m["original_archive_path"] == upstream]
    assert len(mapped) == 1
    assert mapped[0]["collision_safe_relative_path"] == rows[0]["relpath"]
    assert mapped[0]["sha256"] == rows[0]["sha256"]


def test_collision_mapping_covers_every_group_member(collision_map):
    assert len(collision_map) == 12
    assert len({m["collision_group"] for m in collision_map}) == 6
    for m in collision_map:
        assert m["restored"] == "true"
        assert m["original_archive_path"]
        assert m["collision_safe_relative_path"]
        assert len(m["sha256"]) == 64


def test_collision_group_members_are_genuinely_distinct(collision_map):
    """Not duplicates, not re-encodings -- different bytes AND different pixels."""
    by_group = {}
    for m in collision_map:
        by_group.setdefault(m["collision_group"], []).append(m)
    for group, members in by_group.items():
        assert len(members) == 2, group
        assert len({m["sha256"] for m in members}) == 2, f"{group}: identical bytes"
        decoded = {m["decoded_pixel_sha256"] for m in members}
        assert "" not in decoded, f"{group}: an image failed to decode"
        assert len(decoded) == 2, f"{group}: identical decoded pixels (re-encoding)"


def test_original_upstream_paths_are_retained_as_provenance(collision_map, inventory):
    inv_paths = {r["original_upstream_path"] for r in inventory}
    for m in collision_map:
        assert m["original_archive_path"] in inv_paths


def test_collision_members_collide_under_casefold_but_active_paths_do_not(collision_map):
    originals = [m["original_archive_path"] for m in collision_map]
    actives = [m["collision_safe_relative_path"] for m in collision_map]
    assert len(casefold_collisions(originals)) == 6      # the defect
    assert casefold_collisions(actives) == {}            # the fix


# --------------------------------------------------------------------------- #
# The guard that keeps it fixed
# --------------------------------------------------------------------------- #
def test_shortfall_detects_a_dropped_image(repo_root, manifest, tmp_path):
    """Simulate the regression: a manifest one image short must be rejected."""
    short = pd.DataFrame(manifest[1:])
    inv = repo_root / "data/manifests/plantdoc_source_inventory.csv"
    assert collision_safe_shortfall(short, inv), "a short manifest must be detected"
    with pytest.raises(ValueError, match="omits"):
        assert_collision_safe(short, inv)


def test_shortfall_is_silent_without_an_inventory(manifest, tmp_path):
    assert collision_safe_shortfall(pd.DataFrame(manifest), tmp_path / "absent.csv") == []
