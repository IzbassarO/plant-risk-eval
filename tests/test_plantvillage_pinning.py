"""PlantVillage immutable revision pinning (R2B.1 Finding 3).

The image archive was pinned; the split files and the leaf map were not. Those
three files decide which records exist, which split each lands in, and which are
leaf-grouped — so a build could take its pixels from a frozen commit and its
membership from whatever ``main`` pointed at that morning, and nothing recorded
the difference.

These tests use a fake downloader that serves *different content* for a moving
ref than for the pinned commit. If any acquisition path ever drops the revision
again, the fake refuses to serve and the test fails loudly rather than silently
building from the wrong bytes.

No network access, and no dataset is modified.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from ica26.datasets import plantvillage as PV

PINNED = PV.PLANTVILLAGE_REVISION


# --------------------------------------------------------------------------- #
# What counts as a pin
# --------------------------------------------------------------------------- #
def test_the_pinned_revision_is_a_full_commit_sha():
    assert len(PINNED) == 40
    assert all(c in "0123456789abcdef" for c in PINNED)


@pytest.mark.parametrize("moving", [
    "main", "master", "MAIN", "HEAD", "head", "latest", "default", "trunk",
    "refs/heads/main", "", "   ", None,
])
def test_a_moving_reference_is_refused(moving):
    with pytest.raises(PV.SourcePinError):
        PV.assert_immutable_revision(moving)


@pytest.mark.parametrize("bad", ["9e9759", "v1.0", "2026-07-30", "z" * 40, PINNED[:39]])
def test_a_non_commit_reference_is_refused(bad):
    with pytest.raises(PV.SourcePinError):
        PV.assert_immutable_revision(bad)


def test_the_pinned_revision_is_accepted():
    assert PV.assert_immutable_revision(PINNED) == PINNED


def test_every_metadata_component_has_a_recorded_digest():
    for component in ("splits/color_train.txt", "splits/color_test.txt",
                      "leaf_grouping/leaf-map.json", "data.zip"):
        digest = PV.PINNED_COMPONENT_DIGESTS[component]
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)


# --------------------------------------------------------------------------- #
# A fake hub that serves different bytes per revision
# --------------------------------------------------------------------------- #
@pytest.fixture
def hub(tmp_path):
    """Serves pinned content for PINNED and DIFFERENT content for anything else."""
    pinned_dir, moving_dir = tmp_path / "pinned", tmp_path / "moving"
    calls: list[dict] = []

    content: dict[str, str | bytes] = {
        "splits/color_train.txt": "color/Alpha___healthy/a___1.jpg\n"
                                  "color/Beta___blight/b___2.jpg\n",
        "splits/color_test.txt": "color/Alpha___healthy/c___3.jpg\n",
        "leaf_grouping/leaf-map.json": json.dumps({"1": ["x"], "2": ["y"], "3": ["z"]}),
        # It need not be a real archive for these metadata-only tests: the
        # production code verifies its bytes before extraction, and the
        # materialization tests below only exercise that binding.
        "data.zip": b"fake-pinned-plantvillage-archive",
    }
    moving_content = {
        # A plausible-looking edit: one extra record and a dropped leaf group.
        "splits/color_train.txt": "color/Alpha___healthy/a___1.jpg\n"
                                  "color/Beta___blight/b___2.jpg\n"
                                  "color/Gamma___rot/d___4.jpg\n",
        "splits/color_test.txt": "color/Alpha___healthy/c___3.jpg\n",
        "leaf_grouping/leaf-map.json": json.dumps({"1": ["x"]}),
    }
    for d, mapping in ((pinned_dir, content), (moving_dir, moving_content)):
        for name, payload in mapping.items():
            p = d / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(payload, bytes):
                p.write_bytes(payload)
            else:
                p.write_text(payload, encoding="utf-8")

    def download(repo, path, repo_type=None, revision=None, **kw):
        calls.append({"repo": repo, "path": path, "revision": revision})
        if revision is None:
            raise AssertionError(
                f"UNPINNED FETCH of '{path}': acquisition called the hub with no "
                "revision; a moving branch would have been served")
        root = pinned_dir if revision == PINNED else moving_dir
        target = root / path
        if not target.exists():
            raise FileNotFoundError(f"{path} not present at revision {revision}")
        return str(target)

    digests = {name: hashlib.sha256((pinned_dir / name).read_bytes()).hexdigest()
               for name in content}
    download.calls = calls
    download.digests = digests
    download.pinned_dir = pinned_dir
    return download


@pytest.fixture
def patched_digests(hub, monkeypatch):
    """Point the expected-digest table at the fake hub's pinned content."""
    monkeypatch.setattr(PV, "PINNED_COMPONENT_DIGESTS", dict(hub.digests))
    monkeypatch.setattr(
        PV, "PINNED_COMPONENT_BYTE_COUNTS",
        {name: (hub.pinned_dir / name).stat().st_size for name in hub.digests},
    )
    return hub


# --------------------------------------------------------------------------- #
# Every component is fetched from the one immutable revision
# --------------------------------------------------------------------------- #
def test_all_components_are_fetched_from_one_pinned_revision(patched_digests):
    hub = patched_digests
    df, meta = PV.build_manifest_from_repo(config="color", downloader=hub)

    assert meta["revision"] == PINNED
    assert {c["revision"] for c in meta["components"]} == {PINNED}
    assert {c["path"] if "path" in c else c["component"] for c in meta["components"]} == {
        "splits/color_train.txt", "splits/color_test.txt", "leaf_grouping/leaf-map.json"}
    assert {c["revision"] for c in hub.calls} == {PINNED}
    assert len(df) == 3


def _verified_component(name: str, *, digest: str | None = None, **over) -> dict:
    """A minimal, independently checkable component provenance record."""
    expected = digest or PV.PINNED_COMPONENT_DIGESTS[name]
    record = {
        "component": name,
        "source_repository": PV.HF_REPO,
        "immutable_revision": PINNED,
        "source_path": name,
        "resolved_locator": PV._source_locator(PV.HF_REPO, PINNED, name),
        "repo": PV.HF_REPO,
        "revision": PINNED,
        "requested_path": name,
        "resolved_url": PV._source_locator(PV.HF_REPO, PINNED, name),
        "expected_sha256": expected,
        "observed_sha256": expected,
        "byte_count": PV.PINNED_COMPONENT_BYTE_COUNTS[name],
        "digest_verified": True,
        "verification_status": "verified",
    }
    record.update(over)
    return record


def test_complete_component_provenance_is_accepted():
    components = [_verified_component(name) for name in PV.PINNED_COMPONENT_DIGESTS]
    assert PV.validate_component_provenance(components) == []


@pytest.mark.parametrize("mutate,expected", [
    (lambda c: c.pop("data.zip"), "missing required pinned component"),
    (lambda c: c.__setitem__("data.zip", _verified_component("data.zip", digest="0" * 64)),
     "does not record its pinned expected SHA-256"),
    (lambda c: c["data.zip"].__setitem__("observed_sha256", "0" * 64),
     "observed SHA-256 does not match"),
    (lambda c: c["data.zip"].__setitem__("digest_verified", False),
     "not marked digest_verified=true"),
    (lambda c: c["data.zip"].__setitem__("immutable_revision", "0" * 40),
     "not pinned"),
])
def test_component_provenance_rejects_each_unverifiable_archive_binding(mutate, expected):
    by_name = {name: _verified_component(name) for name in PV.PINNED_COMPONENT_DIGESTS}
    mutate(by_name)
    problems = PV.validate_component_provenance(list(by_name.values()))
    assert any(expected in problem for problem in problems), problems


def test_materialized_images_require_an_archive_provenance_record(patched_digests, tmp_path):
    with pytest.raises(PV.SourcePinError, match="pixel materialization requires"):
        PV.build_manifest_from_repo(
            config="color", images_root=tmp_path / "images", downloader=patched_digests)


def test_materialized_images_accept_only_a_verified_pinned_archive(patched_digests, tmp_path):
    hub = patched_digests
    _, archive_component = PV.fetch_pinned("data.zip", downloader=hub)
    _, meta = PV.build_manifest_from_repo(
        config="color", images_root=tmp_path / "images", downloader=hub,
        archive_component=archive_component)
    assert {component["component"] for component in meta["components"]} == {
        "data.zip", "splits/color_train.txt", "splits/color_test.txt",
        "leaf_grouping/leaf-map.json",
    }


def test_provenance_records_url_and_both_digests(patched_digests):
    hub = patched_digests
    _, meta = PV.build_manifest_from_repo(config="color", downloader=hub)
    for c in meta["components"]:
        assert c["repo"] == PV.HF_REPO
        assert c["revision"] == PINNED
        assert c["source_repository"] == PV.HF_REPO
        assert c["immutable_revision"] == PINNED
        assert c["source_path"] == c["component"]
        assert c["resolved_locator"] == PV._source_locator(PV.HF_REPO, PINNED, c["component"])
        assert c["requested_path"] == c["component"]
        assert PINNED in c["resolved_url"] and c["component"] in c["resolved_url"]
        assert c["byte_count"] > 0
        assert len(c["observed_sha256"]) == 64
        assert c["expected_sha256"] == c["observed_sha256"]
        assert c["digest_verified"] is True
        assert c["verification_status"] == "verified"


def test_moving_metadata_cannot_enter_a_pinned_build(patched_digests):
    """The heart of the finding: `main` content must not be reachable."""
    hub = patched_digests
    pinned, _ = PV.build_manifest_from_repo(config="color", downloader=hub)

    # Force the moving branch: content differs, so the digest check must fire.
    with pytest.raises(PV.SourcePinError) as exc:
        PV.fetch_pinned("splits/color_train.txt", revision="f" * 40, downloader=hub)
    assert "did not come from the pinned revision" in str(exc.value)

    # And the pinned build is unaffected: 3 records, not the moving branch's 4.
    assert len(pinned) == 3


def test_a_branch_name_never_reaches_the_downloader(hub):
    with pytest.raises(PV.SourcePinError):
        PV.fetch_pinned("splits/color_train.txt", revision="main", downloader=hub)
    assert hub.calls == []          # refused before any network call


def test_a_digest_mismatch_stops_the_build(hub, monkeypatch):
    monkeypatch.setattr(PV, "PINNED_COMPONENT_DIGESTS", {"splits/color_train.txt": "a" * 64})
    with pytest.raises(PV.SourcePinError) as exc:
        PV.fetch_pinned("splits/color_train.txt", downloader=hub)
    assert "expected" in str(exc.value)


def test_an_unfetchable_component_does_not_fall_back(hub):
    with pytest.raises(PV.SourcePinError) as exc:
        PV.fetch_pinned("splits/nonexistent.txt", downloader=hub)
    assert "does not fall back" in str(exc.value)


def test_mixed_revisions_are_refused(hub, monkeypatch):
    """One component from another commit must fail the build, not be averaged in."""
    monkeypatch.setattr(PV, "PINNED_COMPONENT_DIGESTS", dict(hub.digests))
    monkeypatch.setattr(
        PV, "PINNED_COMPONENT_BYTE_COUNTS",
        {name: (hub.pinned_dir / name).stat().st_size for name in hub.digests},
    )
    original = PV.fetch_pinned
    seen = {"n": 0}

    def sneaky(path, **kw):
        seen["n"] += 1
        if seen["n"] == 3:                       # the leaf map
            local, prov = original(path, downloader=hub, **{k: v for k, v in kw.items()
                                                            if k != "downloader"})
            prov["immutable_revision"] = "0" * 40  # provenance says another commit
            return local, prov
        return original(path, **kw)

    monkeypatch.setattr(PV, "fetch_pinned", sneaky)
    with pytest.raises(PV.SourcePinError) as exc:
        PV.build_manifest_from_repo(config="color", downloader=hub)
    assert "mixed revisions" in str(exc.value)


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("func", ["acquire", "acquire_from_repo",
                                  "build_manifest_from_repo", "build_manifest_from_hf",
                                  "load_hf"])
def test_every_acquisition_entry_point_takes_a_revision(func):
    import inspect

    params = inspect.signature(getattr(PV, func)).parameters
    assert "revision" in params, f"{func} cannot be pinned"
    assert params["revision"].default == PINNED, f"{func} does not default to the pin"


def test_the_head_revision_helper_is_named_for_what_it_returns():
    """It moves. The old name `hf_revision` read like the acquisition revision."""
    assert PV.hf_head_revision.__doc__ and "CURRENT" in PV.hf_head_revision.__doc__
    assert PV.hf_revision is PV.hf_head_revision      # alias kept, meaning clarified


def test_the_snapshot_declares_whether_the_revision_is_pinned():
    snap = PV.build_source_snapshot("color", PINNED, "full")
    assert snap["revision"] == PINNED
    assert snap["revision_is_pinned"] is True

    drifting = PV.build_source_snapshot("color", "0" * 40, "full")
    assert drifting["revision_is_pinned"] is False


def test_the_snapshot_separates_the_pinned_revision_from_the_observed_head():
    snap = PV.build_source_snapshot("color", PINNED, "full", observed_head="0" * 40)
    assert snap["revision"] == PINNED                     # what was read
    assert snap["observed_repo_head"] == "0" * 40         # where the branch is now
    assert snap["head_matches_pinned_revision"] is False


# --------------------------------------------------------------------------- #
# The committed artifacts
# --------------------------------------------------------------------------- #
def test_the_committed_snapshot_records_the_pinned_revision(repo_root):
    snap = json.loads(
        (repo_root / "data/manifests/plantvillage_source_snapshot.json").read_text())
    assert snap["revision"] == PINNED
    assert snap["revision_is_pinned"] is True
    assert snap["hf_repo"] == PV.HF_REPO
    assert snap["schema_version"] == PV.PROVENANCE_SCHEMA_VERSION
    assert snap["immutable_revision"] == PINNED
    assert snap["all_components_pinned"] is True
    assert snap["all_component_digests_verified"] is True
    assert snap["pixels_materialized"] is True
    assert snap["generated_from_pinned_sources"] is True
    assert set(component["component"] for component in snap["source_components"]) == set(
        PV.PINNED_COMPONENT_DIGESTS)
    assert PV.validate_component_provenance(snap["source_components"]) == []
    assert PV.validate_persisted_provenance(
        snap, manifest_path=repo_root / "data/manifests/plantvillage_manifest.csv") == []


def _persisted_provenance(manifest_digest: str) -> dict:
    components = [_verified_component(name) for name in PV.PINNED_COMPONENT_DIGESTS]
    return {
        "schema_version": PV.PROVENANCE_SCHEMA_VERSION,
        "dataset": "PlantVillage",
        "immutable_revision": PINNED,
        "source_components": components,
        "all_components_pinned": True,
        "all_component_digests_verified": True,
        "pixels_materialized": True,
        "manifest_digest": manifest_digest,
        "generated_from_pinned_sources": True,
    }


@pytest.mark.parametrize("mutate, expected", [
    (lambda p: p.pop("source_components"), "omits required field"),
    (lambda p: p["source_components"].pop(), "missing required pinned component"),
    (lambda p: p.__setitem__("immutable_revision", "main"), "immutable_revision"),
    (lambda p: p.__setitem__("all_components_pinned", False), "all_components_pinned"),
    (lambda p: p.__setitem__("all_component_digests_verified", False),
     "all_component_digests_verified"),
    (lambda p: p.__setitem__("pixels_materialized", False), "pixels_materialized"),
    (lambda p: p.__setitem__("manifest_digest", "0" * 64), "manifest_digest is stale"),
    (lambda p: p.__setitem__("generated_from_pinned_sources", False),
     "generated_from_pinned_sources"),
])
def test_persisted_provenance_is_fail_closed_per_required_field(tmp_path, mutate, expected):
    manifest = tmp_path / "plantvillage_manifest.csv"
    manifest.write_text("manifest bytes\n", encoding="utf-8")
    provenance = _persisted_provenance(PV._sha256_of(manifest))
    mutate(provenance)
    problems = PV.validate_persisted_provenance(provenance, manifest_path=manifest)
    assert any(expected in problem for problem in problems), problems


def test_the_scripts_pin_agrees_with_the_module_pin(repo_root):
    text = (repo_root / "scripts/run_phase1_data_completion.py").read_text()
    assert f'PLANTVILLAGE_REV = "{PINNED}"' in text
