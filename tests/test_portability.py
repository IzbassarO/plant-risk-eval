"""Path-portability / anonymity validator."""
from __future__ import annotations

from ica26 import portability as P


def test_detects_personal_paths():
    hits = dict(P.scan_text("file at /Users/testuser/Documents/x.png here"))
    assert "unix_home" in hits or "username" in hits


def test_detects_scratch_and_email():
    assert any(n == "scratch_mount" for n, _ in P.scan_text("/private/tmp/claude-501/abc"))
    assert any(n == "email" for n, _ in P.scan_text("contact me at person@example.com"))


def test_allows_conference_email():
    assert P.scan_text("questions to ica@iitrpr.ac.in") == []


def test_clean_relative_path_passes():
    assert P.scan_text("data/raw/plantdoc/test/Apple/1.jpg") == []


def test_validate_portability_on_dir(tmp_path):
    (tmp_path / "data" / "manifests").mkdir(parents=True)
    good = tmp_path / "data" / "manifests" / "m.csv"
    good.write_text("relpath\ntrain/apple/1.jpg\n")
    assert P.validate_portability(tmp_path, include=["data/manifests/*.csv"]).ok

    bad = tmp_path / "data" / "manifests" / "bad.csv"
    bad.write_text("relpath\n/Users/testuser/x/1.jpg\n")
    res = P.validate_portability(tmp_path, include=["data/manifests/*.csv"])
    assert not res.ok


def test_repo_artifacts_are_portable():
    """The real generated artifacts in this repo must be machine-path-free."""
    res = P.validate_portability(".")
    assert res.ok, "; ".join(f"{i.where}: {i.message}" for i in res.errors[:10])
