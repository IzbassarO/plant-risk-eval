#!/usr/bin/env python
"""Restore case-collision-lost PlantDoc images to the ACTIVE dataset tree.

    python scripts/restore_plantdoc_collisions.py --dry-run   # plan only
    python scripts/restore_plantdoc_collisions.py             # materialize

Background (AUD-EC-003). The upstream PlantDoc tree is case-sensitive and holds
paths differing only by letter case (`CAR1.jpg` / `car1.jpg`). Extracted onto a
case-insensitive filesystem the second member overwrites the first, so six
DISTINCT images never reached `data/raw/plantdoc/{train,test}/` and therefore
never reached the manifest, the pHash index, or any split. They are not
duplicates: every member of every group differs in bytes, dimensions, and
decoded pixels.

This script gives every member of every colliding group a deterministic
content-disambiguated active path (`<stem>__<sha12><ext>`), so no member wins by
extraction order and no path collides under Unicode-normalised casefold.

Authority and safety:
  * The pinned source ARCHIVE is the authority for bytes. Every restored file is
    read from the archive and its SHA-256 verified against the inventory before
    it is written. Nothing is copied from the possibly-clobbered active tree.
  * The inventory (data/manifests/plantdoc_source_inventory.csv) is the authority
    for which records exist. Collision groups are recomputed from casefold keys
    and cross-checked against the recorded `collision_group` labels.
  * Fail-closed: any missing member, SHA mismatch, or residual casefold clash
    aborts before anything is written.
  * No source image is deleted. An ambiguous natural-path file is removed only
    after BOTH group members exist at verified collision-safe paths, and the
    independent `_collisions/` copies are left untouched.
  * Writes are atomic (temp file + os.replace).

Exit codes: 0 = ok, 1 = verification failed (nothing written), 2 = missing input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.plantdoc import (  # noqa: E402
    assert_no_casefold_collisions,
    casefold_collisions,
    casefold_key,
    collision_safe_relpath,
)

INVENTORY = Path("data/manifests/plantdoc_source_inventory.csv")
ARCHIVE_DIR = Path("data/raw/plantdoc/_archive")
DEST_ROOT = Path("data/raw/plantdoc")
MAPPING_CSV = Path("data/manifests/plantdoc_case_collision_mapping.csv")

MAPPING_COLUMNS = (
    "collision_group",
    "original_archive_path",
    "collision_safe_relative_path",
    "split",
    "class",
    "sha256",
    "n_bytes",
    "width",
    "height",
    "decoded_pixel_sha256",
    "restored",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decoded_pixel_sha256(data: bytes) -> str:
    """SHA-256 of the decoded RGB pixel buffer.

    Distinguishes a genuine re-encoding (same pixels, different bytes) from two
    genuinely different images. Computed, never fabricated; blank if undecodable.
    """
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return hashlib.sha256(im.convert("RGB").tobytes()).hexdigest()
    except Exception:
        return ""


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="restore-plantdoc-collisions")
    ap.add_argument("--dry-run", action="store_true", help="verify and plan; write nothing")
    ap.add_argument("--inventory", default=str(INVENTORY))
    ap.add_argument("--dest-root", default=str(DEST_ROOT))
    ap.add_argument("--mapping-out", default=str(MAPPING_CSV))
    args = ap.parse_args(argv)

    inv_path = REPO / args.inventory
    dest_root = REPO / args.dest_root
    if not inv_path.exists():
        print(f"[restore] inventory not found: {args.inventory}")
        return 2

    with open(inv_path, newline="", encoding="utf-8") as fh:
        inventory = list(csv.DictReader(fh))
    print(f"[restore] inventory records: {len(inventory)}")

    # ---- 1. Recompute collision groups from the inventory itself ----------- #
    groups = casefold_collisions(r["original_upstream_path"] for r in inventory)
    by_path = {r["original_upstream_path"]: r for r in inventory}
    print(f"[restore] casefold collision groups recomputed: {len(groups)}")

    # Cross-check against the recorded labels; disagreement is fail-closed.
    labelled = {r["original_upstream_path"] for r in inventory if r["collision_group"]}
    recomputed = {p for members in groups.values() for p in members}
    if labelled != recomputed:
        print("[restore] FAILED: recorded collision_group labels disagree with the "
              "recomputed casefold grouping")
        print(f"  only recorded:   {sorted(labelled - recomputed)}")
        print(f"  only recomputed: {sorted(recomputed - labelled)}")
        return 1

    members = sorted(recomputed)
    if not members:
        print("[restore] no collision groups; nothing to do")
        return 0

    # ---- 2. Plan deterministic collision-safe active paths ----------------- #
    plan = []
    for original in members:
        rec = by_path[original]
        safe = collision_safe_relpath(original, rec["source_sha256"])
        plan.append({"original": original, "safe": safe, "rec": rec})

    active_paths = [r["original_upstream_path"] for r in inventory
                    if r["original_upstream_path"] not in recomputed]
    active_paths += [p["safe"] for p in plan]
    try:
        assert_no_casefold_collisions(active_paths)
    except ValueError as e:
        print(f"[restore] FAILED: planned layout still collides: {e}")
        return 1
    print(f"[restore] planned active layout: {len(active_paths)} paths, 0 casefold collisions")

    # ---- 3. Read the authoritative bytes from the pinned archive ----------- #
    archives = sorted((REPO / ARCHIVE_DIR).glob("*.tar.gz")) if (REPO / ARCHIVE_DIR).exists() else []
    if not archives:
        print(f"[restore] FAILED: no pinned source archive under {ARCHIVE_DIR}. "
              "Cannot verify bytes against the authoritative source.")
        return 2
    archive = archives[0]
    print(f"[restore] authoritative archive: {archive.name} "
          f"({archive.stat().st_size / 1e6:.0f} MB)")

    wanted = {p["original"]: p for p in plan}
    found: dict[str, bytes] = {}
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)  # strip "PlantDoc-Dataset-<sha>/"
            if len(parts) < 2:
                continue
            rel = parts[1]
            if rel not in wanted:
                continue
            fobj = tf.extractfile(m)
            if fobj is None:
                continue
            found[rel] = fobj.read()
            if len(found) == len(wanted):
                break

    missing = sorted(set(wanted) - set(found))
    if missing:
        print(f"[restore] FAILED: {len(missing)} collision member(s) absent from the archive:")
        for p in missing:
            print(f"  - {p}")
        return 1
    print(f"[restore] read {len(found)} collision member(s) from the archive")

    # ---- 4. Verify every byte against the inventory ------------------------ #
    for item in plan:
        data = found[item["original"]]
        rec = item["rec"]
        actual = sha256_bytes(data)
        if actual != rec["source_sha256"]:
            print(f"[restore] FAILED: sha mismatch for {item['original']}\n"
                  f"  archive:   {actual}\n  inventory: {rec['source_sha256']}")
            return 1
        if str(len(data)) != str(rec["file_size"]):
            print(f"[restore] FAILED: size mismatch for {item['original']}: "
                  f"archive {len(data)} vs inventory {rec['file_size']}")
            return 1
        item["data"] = data
        item["decoded"] = decoded_pixel_sha256(data)
    print("[restore] all archive SHA-256 and byte sizes match the inventory")

    # Distinctness evidence: members of a group must differ in bytes AND pixels.
    for key, group_members in groups.items():
        shas = {by_path[p]["source_sha256"] for p in group_members}
        decoded = {i["decoded"] for i in plan if i["original"] in group_members}
        if len(shas) != len(group_members):
            print(f"[restore] FAILED: group {key} has repeated SHA-256 -- these would "
                  "be true duplicates, not a case collision")
            return 1
        if "" not in decoded and len(decoded) != len(group_members):
            print(f"[restore] FAILED: group {key} members share decoded pixels -- "
                  "re-encoding, not distinct images. Refusing to restore.")
            return 1

    # ---- 5. Materialize -------------------------------------------------- #
    if args.dry_run:
        print("\n[restore] DRY RUN — planned actions:")
        for item in sorted(plan, key=lambda i: i["original"]):
            exists = (dest_root / item["safe"]).exists()
            print(f"  {'keep ' if exists else 'write'} {item['safe']}  "
                  f"(sha {item['rec']['source_sha256'][:12]}, {item['rec']['file_size']} B)")
        naturals = sorted({i["original"] for i in plan if (dest_root / i["original"]).exists()})
        for n in naturals:
            print(f"  remove-ambiguous {n}")
        print(f"[restore] dry-run: {len(plan)} member(s), "
              f"{len(naturals)} ambiguous natural path(s); nothing written")
        return 0

    written = 0
    for item in plan:
        target = dest_root / item["safe"]
        if target.exists() and sha256_bytes(target.read_bytes()) == item["rec"]["source_sha256"]:
            continue
        atomic_write_bytes(target, item["data"])
        written += 1
    print(f"[restore] wrote {written} collision-safe file(s)")

    # Remove the ambiguous natural path ONLY once every member of its group is
    # verified present at a collision-safe path. The bytes survive there and in
    # data/raw/plantdoc/_collisions/, so no source content is destroyed.
    removed = 0
    for key, group_members in groups.items():
        safes = [dest_root / collision_safe_relpath(p, by_path[p]["source_sha256"])
                 for p in group_members]
        verified = all(
            s.exists() and sha256_bytes(s.read_bytes()) == by_path[p]["source_sha256"]
            for s, p in zip(safes, group_members)
        )
        if not verified:
            print(f"[restore] FAILED: group {key} not fully materialized; "
                  "leaving the natural path in place")
            return 1
        for p in group_members:
            natural = dest_root / p
            if natural.exists() and natural not in safes:
                natural.unlink()
                removed += 1
    print(f"[restore] removed {removed} ambiguous natural-path file(s) "
          "(content preserved at collision-safe paths and under _collisions/)")

    # ---- 6. Machine-readable mapping ------------------------------------- #
    label = {}
    for gi, (key, group_members) in enumerate(sorted(groups.items()), 1):
        for p in group_members:
            label[p] = by_path[p]["collision_group"] or f"cg{gi:02d}"

    rows = []
    for item in sorted(plan, key=lambda i: (label[i["original"]], i["original"])):
        rec = item["rec"]
        rows.append({
            "collision_group": label[item["original"]],
            "original_archive_path": item["original"],
            "collision_safe_relative_path": item["safe"],
            "split": rec["split"],
            "class": rec["class"],
            "sha256": rec["source_sha256"],
            "n_bytes": rec["file_size"],
            "width": rec["width"],
            "height": rec["height"],
            "decoded_pixel_sha256": item["decoded"],
            "restored": "true" if (dest_root / item["safe"]).exists() else "false",
        })
    out = REPO / args.mapping_out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(MAPPING_COLUMNS), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, out)
    print(f"[restore] wrote {args.mapping_out} ({len(rows)} rows, "
          f"{len(groups)} collision group(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
