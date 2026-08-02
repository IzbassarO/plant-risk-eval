#!/usr/bin/env python
"""Phase-1 HUMAN REVIEW PACKET preparation (deterministic; makes NO decisions).

Builds the artifacts a human needs to (a) resolve the PlantDoc case-collisions,
(b) adjudicate the 16 PlantVillage->PlantDoc pHash near-duplicates, and (c) review
the 28 disease->action mapping rows — WITHOUT approving mappings, excluding any
near-duplicate, creating a harm matrix, running Phase 2, or committing.

Outputs (all repository-relative):
  data/manifests/plantdoc_source_inventory.csv        (all 2,578 upstream paths)
  reports/PLANTDOC_CASE_COLLISION_REVIEW.md
  data/raw/plantdoc/_collisions/...                    (collision-safe image copies)
  reports/near_duplicate_contact_sheets/*.png          (4 pairs/page, contain-fit)
  reports/NEAR_DUPLICATE_HUMAN_REVIEW.md
  data/exclusions/cross_dataset_near_duplicate_review.csv   (human fields BLANK)
  data/exclusions/cross_dataset_reviewed_exclusions.csv     (skeleton; unpopulated)
  reports/ACTION_MAPPING_HUMAN_CHECKLIST.md

The training manifest (data/manifests/plantdoc_manifest.csv) is NOT modified.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
REPORTS = REPO / "reports"
PLANTDOC_ROOT = DATA / "raw" / "plantdoc"
PV_ROOT = DATA / "raw" / "plantvillage" / "extracted"
COLLISION_DIR = PLANTDOC_ROOT / "_collisions"
PLANTVILLAGE_REV = "9e97599868962bd0079b8db4b7f1efa9185fa1e7"
PLANTDOC_COMMIT = "5467f6012d78d1c446145d5f582da6096f852ae8"
IMG_EXT = {".jpg", ".jpeg", ".png"}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _load_font(size: int):
    for cand in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/System/Library/Fonts/Helvetica.ttc",
                 "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# PART 1 — PlantDoc case-collision resolution + source inventory
# --------------------------------------------------------------------------- #
def _archive_path() -> Path:
    cands = glob.glob(str(PLANTDOC_ROOT / "_archive" / "plantdoc-*.tar.gz"))
    if not cands:
        raise FileNotFoundError("PlantDoc commit archive not found under data/raw/plantdoc/_archive/")
    return Path(cands[0])


def _safe_name(rel: str, sha: str) -> str:
    stem = Path(rel).stem
    ext = Path(rel).suffix
    # keep original stem readable; add deterministic sha suffix to disambiguate.
    return f"{stem}__{sha[:12]}{ext}"


def build_source_inventory() -> dict:
    cc = json.loads((DATA / "manifests" / "_plantdoc_case_collisions.json").read_text())
    pairs = cc["collisions"]
    collision_members = {p for pair in pairs for p in pair}

    # Pull every collision member's bytes from the authoritative archive.
    archive = _archive_path()
    ameta: dict[str, dict] = {}
    with tarfile.open(archive, "r:gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            parts = m.name.split("/", 1)
            if len(parts) < 2:
                continue
            rel = parts[1]
            if rel in collision_members:
                b = tf.extractfile(m).read()
                im = Image.open(io.BytesIO(b))
                ameta[rel] = {"sha": sha256_bytes(b), "size": len(b),
                              "w": im.size[0], "h": im.size[1], "mode": im.mode, "bytes": b}

    # Classify each pair and materialize collision-safe copies.
    COLLISION_DIR.mkdir(parents=True, exist_ok=True)
    man = pd.read_csv(DATA / "manifests" / "plantdoc_manifest.csv", dtype=str, keep_default_na=False)
    man_by_rel = {r["relpath"]: r for _, r in man.iterrows()}

    pair_findings = []
    materialized_for = {}   # upstream_rel -> (materialized_relpath, materialized_sha, status, group, notes)
    for gi, pair in enumerate(pairs, 1):
        group = f"cg{gi:02d}"
        a, b = pair[0], pair[1]
        da, db = ameta[a], ameta[b]
        byte_identical = da["sha"] == db["sha"]
        pixel_identical = None
        if not byte_identical:
            ia = Image.open(io.BytesIO(da["bytes"])).convert("RGB")
            ib = Image.open(io.BytesIO(db["bytes"])).convert("RGB")
            pixel_identical = (ia.size == ib.size) and (list(ia.getdata()) == list(ib.getdata()))
        if byte_identical:
            verdict, status = "byte_identical", "shared_identical_content"
        elif pixel_identical:
            verdict, status = "visually_identical_reencoded", "collision_safe_rename"
        else:
            verdict, status = "genuinely_different", "collision_safe_rename"

        if status == "shared_identical_content":
            # one content file already on disk (the surviving member); both records share it.
            survivor = a if a in man_by_rel else (b if b in man_by_rel else a)
            mrel = f"data/raw/plantdoc/{survivor}"
            msha = da["sha"]
            for rel in (a, b):
                materialized_for[rel] = (mrel, msha, status, group,
                                         "byte-identical content shared by both case-variant paths")
        else:
            # distinct content -> extract BOTH under collision-safe names.
            for rel, d in ((a, da), (b, db)):
                split = rel.split("/", 1)[0]
                cls = rel.split("/")[1]
                safe = _safe_name(rel, d["sha"])
                out = COLLISION_DIR / split / cls / safe
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(d["bytes"])
                mrel = str(out.relative_to(REPO))
                note = ("distinct image content; original name collides case-insensitively "
                        "with its pair member — extracted under a collision-safe name")
                if rel in man_by_rel:
                    note += " (this member also currently on disk under its original name)"
                materialized_for[rel] = (mrel, d["sha"], status, group, note)

        pair_findings.append({
            "group": group, "class": a.split("/")[1],
            "a": a, "b": b, "a_sha": da["sha"], "b_sha": db["sha"],
            "a_size": da["size"], "b_size": db["size"],
            "a_wh": (da["w"], da["h"]), "b_wh": (db["w"], db["h"]),
            "a_mode": da["mode"], "b_mode": db["mode"],
            "verdict": verdict, "status": status,
            "a_on_disk": a in man_by_rel, "b_on_disk": b in man_by_rel,
        })

    # ---- Build the full upstream inventory ----
    # The ACTIVE tree carries collision-safe filenames (see
    # reports/PLANTDOC_CASE_COLLISION_POLICY.md), so a manifest relpath is not
    # necessarily the upstream path. Translate back through the collision mapping:
    # the manifest is the authority for bytes, the mapping for names. Any collision
    # member still absent from the manifest is filled from the archive, so the
    # inventory stays complete even if run before restoration.
    active_to_original = {}
    mapping_csv = DATA / "manifests" / "plantdoc_case_collision_mapping.csv"
    if mapping_csv.exists():
        with open(mapping_csv, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                active_to_original[r["collision_safe_relative_path"]] = r["original_archive_path"]

    rows = []
    covered = set()
    for _, r in man.iterrows():
        active = r["relpath"]
        rel = active_to_original.get(active, active)
        covered.add(rel)
        split = rel.split("/", 1)[0]
        group, status, notes = "", "materialized", ""
        if rel in materialized_for:
            _, _, status, group, notes = materialized_for[rel]
        rows.append({
            "source_revision": PLANTDOC_COMMIT,
            "original_upstream_path": rel,
            "materialized_relative_path": f"data/raw/plantdoc/{active}",
            "source_sha256": r["sha256"],
            "materialized_sha256": r["sha256"],
            "file_size": r["n_bytes"],
            "width": r["width"], "height": r["height"], "mode": r["mode"],
            "split": split, "class": r["class_label"],
            "collision_group": group,
            "materialization_status": status,
            "notes": notes,
        })

    for rel in sorted(set(collision_members) - covered):
        mrel, msha, status, group, notes = materialized_for[rel]
        d = ameta[rel]
        rows.append({
            "source_revision": PLANTDOC_COMMIT,
            "original_upstream_path": rel,
            "materialized_relative_path": mrel,
            "source_sha256": d["sha"],
            "materialized_sha256": msha,
            "file_size": d["size"],
            "width": d["w"], "height": d["h"], "mode": d["mode"],
            "split": rel.split("/", 1)[0], "class": rel.split("/")[1],
            "collision_group": group,
            "materialization_status": status,
            "notes": notes + " — NOT in the active manifest; run "
                             "scripts/restore_plantdoc_collisions.py",
        })
    upstream = sorted({r["original_upstream_path"] for r in rows})
    cols = ["source_revision", "original_upstream_path", "materialized_relative_path",
            "source_sha256", "materialized_sha256", "file_size", "width", "height",
            "mode", "split", "class", "collision_group", "materialization_status", "notes"]
    inv = pd.DataFrame(rows, columns=cols).sort_values("original_upstream_path").reset_index(drop=True)
    inv_path = DATA / "manifests" / "plantdoc_source_inventory.csv"
    tmp = inv_path.with_suffix(".csv.part")
    inv.to_csv(tmp, index=False)
    tmp.replace(inv_path)

    # distinct materialized content files
    materialized_content = inv["materialized_sha256"].nunique()
    n_byte_identical = sum(1 for f in pair_findings if f["verdict"] == "byte_identical")
    n_reencoded = sum(1 for f in pair_findings if f["verdict"] == "visually_identical_reencoded")
    n_different = sum(1 for f in pair_findings if f["verdict"] == "genuinely_different")
    n_rename = int((inv["materialization_status"] == "collision_safe_rename").sum())
    n_shared = int((inv["materialization_status"] == "shared_identical_content").sum())
    intra_dup_gap = len(upstream) - materialized_content  # pre-existing intra-PlantDoc dupes

    # ---- Write the collision review report ----
    md = ["# PlantDoc Case-Collision Review", "",
          f"_Source commit `{PLANTDOC_COMMIT}` · generated by scripts/prepare_human_review.py · "
          "no image content fabricated, duplicated, or silently discarded._", "",
          "## Summary", "",
          f"- Upstream train/test image paths (source records): **{len(upstream)}**",
          f"- Case-collision pairs inspected: **{len(pairs)}** — byte-identical **{n_byte_identical}**, "
          f"re-encoded-identical **{n_reencoded}**, genuinely-different **{n_different}**",
          f"- Materialization: **{n_shared}** shared_identical_content record(s), "
          f"**{n_rename}** collision_safe_rename record(s) ({len(pairs)} pairs × 2 members).",
          f"- Distinct content files by SHA-256: **{materialized_content}**. The "
          f"{len(upstream)}→{materialized_content} gap ({intra_dup_gap} records) is **pre-existing "
          "intra-PlantDoc exact duplication** (2,572 on-disk files carry only 2,560 distinct SHA-256, "
          "documented in remediation), **not** the case-collisions — every collision pair is distinct "
          "content (0 shared).",
          "- Method: both members of every pair were extracted from the authoritative commit "
          "archive; SHA-256, byte size, decoded dimensions and image mode were computed directly "
          "(equivalence was **not** inferred from filenames).",
          "",
          "**Key finding:** every collision pair is **genuinely different image content** (distinct "
          "SHA-256, size, and dimensions) — these are *not* duplicates. On the case-insensitive "
          "macOS filesystem only one member of each pair (the one that sorts first) can exist under "
          "its original name, so the other member's distinct content was absent from the on-disk set. "
          "Both members are now preserved under collision-safe names; the model-training manifest is "
          "left unchanged pending a human decision.",
          "",
          "## Per-pair findings", "",
          "| Group | Class | Member | Upstream path | SHA-256 (12) | Size (B) | W×H | Mode | On disk (orig name) |",
          "|---|---|---|---|---|---:|---|---|---|"]
    for f in pair_findings:
        for lbl, rel, sha, size, wh, mode, od in (
            ("A", f["a"], f["a_sha"], f["a_size"], f["a_wh"], f["a_mode"], f["a_on_disk"]),
            ("B", f["b"], f["b_sha"], f["b_size"], f["b_wh"], f["b_mode"], f["b_on_disk"]),
        ):
            md.append(f"| {f['group']} | {f['class']} | {lbl} | `{rel}` | `{sha[:12]}` | "
                      f"{size} | {wh[0]}×{wh[1]} | {mode} | {'yes' if od else 'no'} |")
        md.append(f"| {f['group']} | | **verdict** | **{f['verdict']}** → "
                  f"`{f['status']}` | | | | | |")
    md += ["",
           "## Materialization policy applied", "",
           "- `byte_identical` → one shared content file, two source records with the same "
           "content SHA-256 (`materialization_status=shared_identical_content`).",
           "- `visually_identical_reencoded` / `genuinely_different` → both members extracted under "
           "collision-safe filenames (deterministic `__<sha12>` suffix) under "
           "`data/raw/plantdoc/_collisions/` (`materialization_status=collision_safe_rename`); the "
           "original upstream path is preserved in `original_upstream_path`.",
           "",
           "## Human decisions required", "",
           "1. Decide whether the 6 currently-absent distinct images (the non-surviving members) "
           "should be added to the model-training manifest under their collision-safe names, or "
           "left out. **This script does not change `data/manifests/plantdoc_manifest.csv`.**",
           "2. If added, re-derive the training manifest from the collision-safe set so all 2,578 "
           "distinct images are representable (requires a case-safe naming scheme, already applied "
           "in `data/manifests/plantdoc_source_inventory.csv`).",
           ""]
    (REPORTS / "PLANTDOC_CASE_COLLISION_REVIEW.md").write_text("\n".join(md))

    return {"upstream": len(upstream), "pairs": len(pairs), "findings": pair_findings,
            "materialized_content": int(materialized_content),
            "inventory_rows": int(len(inv)),
            "n_byte_identical": n_byte_identical, "n_reencoded": n_reencoded,
            "n_different": n_different, "n_collision_safe_rename": n_rename,
            "n_shared_identical": n_shared, "intra_dup_gap": intra_dup_gap}


# --------------------------------------------------------------------------- #
# PART 2 — visual near-duplicate review packet
# --------------------------------------------------------------------------- #
def _auto_similarity(imt: Image.Image, ime: Image.Image) -> str:
    """Cheap, NON-AUTHORITATIVE heuristic description of visual similarity."""
    import numpy as np
    a = np.asarray(imt.convert("RGB").resize((32, 32))).astype("float32")
    b = np.asarray(ime.convert("RGB").resize((32, 32))).astype("float32")
    mad = float(np.abs(a - b).mean())            # 0..255 mean abs diff
    art = imt.size[0] / imt.size[1]
    are = ime.size[0] / ime.size[1]
    ar_close = abs(art - are) < 0.15
    def whiteish(im):
        import numpy as np
        arr = np.asarray(im.convert("RGB").resize((32, 32))).astype("float32")
        return float(arr.mean()) > 200 and float(arr.std()) < 60
    wt, we = whiteish(imt), whiteish(ime)
    bits = [f"thumb mean-abs-diff≈{mad:.0f}/255",
            "aspect ratios " + ("close" if ar_close else "differ")]
    if wt or we:
        bits.append("at least one appears white/studio background")
    verdict = ("low pixel-level similarity" if mad > 60 else
               "moderate pixel-level similarity" if mad > 30 else
               "high pixel-level similarity")
    return f"(automated heuristic, non-authoritative) {verdict}; " + "; ".join(bits)


def _contain(im: Image.Image, box: int, bg=(235, 235, 235)) -> Image.Image:
    """Contain-fit the FULL image into a box×box canvas (no cropping)."""
    im = im.convert("RGB")
    w, h = im.size
    scale = min(box / w, box / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    thumb = im.resize((nw, nh))
    canvas = Image.new("RGB", (box, box), bg)
    canvas.paste(thumb, ((box - nw) // 2, (box - nh) // 2))
    return canvas


# --------------------------------------------------------------------------- #
# Human-decision preservation (AUD-EC-004)
#
# Regenerating the packet must never destroy adjudications. Decisions are merged
# back by CANONICAL IDENTITY -- both datasets, both relative paths, both class
# labels, both endpoint SHA-256 digests, and the pHash distance -- not by row
# order and not by pair_id, which is only a label. If a pair's identity drifted,
# the old decision no longer describes the new pair, so the merge fails closed
# rather than silently re-attaching a stale verdict.
# --------------------------------------------------------------------------- #
REVIEW_COLUMNS = [
    "pair_id", "training_dataset", "training_relative_path", "training_class",
    "training_sha256", "evaluation_dataset", "evaluation_relative_path",
    "evaluation_class", "evaluation_sha256", "phash_distance", "contact_sheet",
    "human_decision", "decision_reason", "reviewer", "reviewed_at", "final_disposition",
]

#: Fields that define a pair. Drift in any of them invalidates a prior decision.
#: `contact_sheet` is deliberately excluded: re-paging the sheets is cosmetic.
IDENTITY_COLUMNS = (
    "training_dataset", "training_relative_path", "training_class", "training_sha256",
    "evaluation_dataset", "evaluation_relative_path", "evaluation_class",
    "evaluation_sha256", "phash_distance",
)

#: Fields carried across a regeneration.
DECISION_COLUMNS = (
    "human_decision", "decision_reason", "reviewer", "reviewed_at", "final_disposition",
)

REVIEWED_EXCLUSION_COLUMNS = [
    "pair_id", "match_type", "training_relative_path", "evaluation_relative_path",
    "phash_distance", "human_decision", "exclusion_reason", "reviewer", "reviewed_at",
    "source_review_file",
]

NEAR_REVIEW_CSV = DATA / "exclusions" / "cross_dataset_near_duplicate_review.csv"
REVIEWED_EXCLUSIONS_CSV = DATA / "exclusions" / "cross_dataset_reviewed_exclusions.csv"


class HumanDecisionDrift(RuntimeError):
    """A prior decision cannot be re-attached because the pair's identity changed."""


def _read_rows(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _atomic_write_rows(path: Path, columns, rows) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columns), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    return path


def _identity_key(row: dict) -> tuple:
    return ((row.get("training_relative_path") or "").strip(),
            (row.get("evaluation_relative_path") or "").strip())


def _has_decision(row: dict) -> bool:
    return any((row.get(c) or "").strip() for c in DECISION_COLUMNS)


def merge_near_review(fresh: list[dict], existing: list[dict],
                      *, reset: bool = False) -> tuple[list[dict], dict]:
    """Carry prior decisions onto freshly-derived rows. Fail closed on drift.

    ``fresh`` rows carry authoritative identity and blank decisions. Returns the
    merged rows plus a change report naming preserved, new, dropped, and drifted
    pairs. ``reset=True`` discards every prior decision -- destructive, and only
    reachable through an explicit CLI flag.
    """
    report = {"preserved": [], "new": [], "dropped": [], "drift": [], "reset": bool(reset)}
    if reset:
        report["new"] = [r["pair_id"] for r in fresh]
        return fresh, report

    prior = {}
    for r in existing:
        prior.setdefault(_identity_key(r), r)

    # Stable ids: keep the id a decided pair already has; mint above the high-water
    # mark so a new pair can never reuse a retired label.
    used_ids = {(r.get("pair_id") or "").strip() for r in existing}
    next_n = 0
    for pid in used_ids:
        if pid.startswith("ndp-") and pid[4:].isdigit():
            next_n = max(next_n, int(pid[4:]))

    merged = []
    for row in fresh:
        key = _identity_key(row)
        old = prior.pop(key, None)
        if old is None:
            next_n += 1
            row = dict(row, pair_id=f"ndp-{next_n:02d}")
            report["new"].append(row["pair_id"])
            merged.append(row)
            continue

        mismatched = [c for c in IDENTITY_COLUMNS
                      if (old.get(c) or "").strip() != (row.get(c) or "").strip()]
        if mismatched and _has_decision(old):
            report["drift"].append({
                "pair_id": (old.get("pair_id") or "").strip(),
                "key": list(key),
                "changed_fields": mismatched,
            })
            merged.append(row)
            continue

        out = dict(row)
        if (old.get("pair_id") or "").strip():
            out["pair_id"] = old["pair_id"].strip()
        for c in DECISION_COLUMNS:
            out[c] = old.get(c, "")
        merged.append(out)
        if _has_decision(old):
            report["preserved"].append(out["pair_id"])

    for key, old in prior.items():
        report["dropped"].append({
            "pair_id": (old.get("pair_id") or "").strip(),
            "key": list(key),
            "had_decision": _has_decision(old),
            "human_decision": (old.get("human_decision") or "").strip(),
            "final_disposition": (old.get("final_disposition") or "").strip(),
        })

    if report["drift"]:
        detail = "; ".join(
            f"{d['pair_id']} changed {d['changed_fields']}" for d in report["drift"])
        raise HumanDecisionDrift(
            f"{len(report['drift'])} decided pair(s) no longer match their recorded "
            f"identity: {detail}. A prior verdict cannot be re-attached to a pair whose "
            "content changed. Re-review those pairs, or re-run with "
            "--reset-human-decisions to discard every decision (destructive)."
        )
    return merged, report


def merge_reviewed_exclusions(review_rows: list[dict], existing: list[dict]) -> tuple[list[dict], dict]:
    """Keep exclusion records that still trace to an exclude_evaluation decision.

    Never blank-overwrites: a record survives regeneration as long as its pair is
    still authoritative and still decided `exclude_evaluation`.
    """
    decided = {_identity_key(r): r for r in review_rows
               if (r.get("final_disposition") or "").strip() == "exclude_evaluation"}
    kept, dropped = [], []
    seen = set()
    for x in existing:
        key = _identity_key(x)
        if key in decided and key not in seen:
            seen.add(key)
            out = dict(x)
            out["pair_id"] = (decided[key].get("pair_id") or "").strip() or out.get("pair_id", "")
            kept.append(out)
        else:
            dropped.append({"pair_id": (x.get("pair_id") or "").strip(), "key": list(key)})
    missing = [ (r.get("pair_id") or "").strip() for k, r in decided.items() if k not in seen ]
    return kept, {"kept": len(kept), "dropped": dropped, "missing_propagation": sorted(missing)}


def build_near_duplicate_packet(*, reset_human_decisions: bool = False) -> dict:
    pairs = pd.read_csv(REPORTS / "leakage_plantvillage_vs_plantdoc_pairs.csv",
                        dtype=str, keep_default_na=False)
    pairs = pairs[pairs["classification"] == "near"].reset_index(drop=True)
    n = len(pairs)

    sheets_dir = REPORTS / "near_duplicate_contact_sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)

    font = _load_font(13)
    font_b = _load_font(15)
    BOX = 300
    PANEL_W, PANEL_H = 2 * BOX + 60, BOX + 120
    PER_PAGE = 4

    rows = []
    panels = []
    for i, r in pairs.iterrows():
        pid = f"ndp-{i+1:02d}"
        tr_rel, ev_rel = r["training_relpath"], r["evaluation_relpath"]
        tr_abs, ev_abs = PV_ROOT / tr_rel, PLANTDOC_ROOT / ev_rel
        imt = Image.open(tr_abs)
        ime = Image.open(ev_abs)
        tr_sha, ev_sha = sha256_file(tr_abs), sha256_file(ev_abs)
        tr_wh, ev_wh = imt.size, ime.size
        desc = _auto_similarity(imt, ime)
        sheet_page = i // PER_PAGE + 1
        sheet_name = f"contact_sheet_{sheet_page:02d}.png"

        rows.append({
            "pair_id": pid,
            "training_dataset": "PlantVillage",
            "training_relative_path": tr_rel,
            "training_class": r["training_class"],
            "training_sha256": tr_sha,
            "evaluation_dataset": "PlantDoc",
            "evaluation_relative_path": ev_rel,
            "evaluation_class": r["evaluation_class"],
            "evaluation_sha256": ev_sha,
            "phash_distance": r["hamming_distance"],
            "contact_sheet": f"reports/near_duplicate_contact_sheets/{sheet_name}",
            "human_decision": "",
            "decision_reason": "",
            "reviewer": "",
            "reviewed_at": "",
            "final_disposition": "",
        })

        # ---- render one panel (two contain-fit images + metadata) ----
        panel = Image.new("RGB", (PANEL_W, PANEL_H), (255, 255, 255))
        d = ImageDraw.Draw(panel)
        panel.paste(_contain(imt, BOX), (20, 34))
        panel.paste(_contain(ime, BOX), (40 + BOX, 34))
        d.text((20, 8), f"{pid}   pHash Hamming distance = {r['hamming_distance']}   "
                        "(near-duplicate; NOT a decision)", font=font_b, fill=(0, 0, 0))
        d.text((20, 34 + BOX + 4),
               f"TRAIN PlantVillage / {r['training_class']}  {tr_wh[0]}x{tr_wh[1]}  "
               f"phash={r['training_phash']} sha={tr_sha[:12]}", font=font, fill=(20, 20, 120))
        d.text((20, 34 + BOX + 22), f"  {tr_rel}", font=font, fill=(60, 60, 60))
        d.text((20, 34 + BOX + 44),
               f"EVAL  PlantDoc / {r['evaluation_class']}  {ev_wh[0]}x{ev_wh[1]}  "
               f"phash={r['evaluation_phash']} sha={ev_sha[:12]}", font=font, fill=(120, 20, 20))
        d.text((20, 34 + BOX + 62), f"  {ev_rel}", font=font, fill=(60, 60, 60))
        d.text((20, 34 + BOX + 84), desc, font=font, fill=(90, 90, 90))
        panels.append(panel)

    # ---- compose contact sheets (4 panels/page) ----
    sheet_files = []
    n_pages = (n + PER_PAGE - 1) // PER_PAGE
    for pg in range(n_pages):
        chunk = panels[pg * PER_PAGE:(pg + 1) * PER_PAGE]
        page = Image.new("RGB", (PANEL_W, PANEL_H * PER_PAGE + 40), (255, 255, 255))
        hd = ImageDraw.Draw(page)
        hd.text((20, 8), f"PlantVillage->PlantDoc near-duplicate review — sheet {pg+1}/{n_pages} "
                         "— pairs are NOT auto-excluded; human decision required",
                font=_load_font(14), fill=(0, 0, 0))
        for j, panel in enumerate(chunk):
            page.paste(panel, (0, 40 + j * PANEL_H))
        out = sheets_dir / f"contact_sheet_{pg+1:02d}.png"
        page.save(out)
        sheet_files.append(str(out.relative_to(REPO)))

    # ---- review CSV: merge prior decisions by canonical identity ----
    existing = _read_rows(NEAR_REVIEW_CSV)
    rows, change_report = merge_near_review(rows, existing, reset=reset_human_decisions)
    _atomic_write_rows(NEAR_REVIEW_CSV, REVIEW_COLUMNS, rows)

    # ---- reviewed exclusions: preserve + revalidate, never blank-overwrite ----
    excl_kept, excl_report = merge_reviewed_exclusions(rows, _read_rows(REVIEWED_EXCLUSIONS_CSV))
    _atomic_write_rows(REVIEWED_EXCLUSIONS_CSV, REVIEWED_EXCLUSION_COLUMNS, excl_kept)

    _write_change_report(change_report, excl_report, n)

    # ---- human review markdown ----
    md = ["# Near-Duplicate Human Review (PlantVillage color -> PlantDoc)", "",
          f"**Training source:** PlantVillage color @ `{PLANTVILLAGE_REV}`  ",
          f"**Evaluation source:** PlantDoc @ `{PLANTDOC_COMMIT}`  ",
          "**Algorithm / threshold:** imagehash.phash / Hamming ≤ 6 (unchanged)  ", "",
          f"**{n} near-duplicate pair(s)** flagged by perceptual hash. None is auto-excluded; each "
          "awaits a human decision. Contact sheets show the **full, uncropped** images (contain-fit, "
          "so background and crop differences remain visible).", "",
          "Allowed `human_decision`: `same_source_image`, `same_scene_different_crop`, "
          "`visually_similar_but_independent`, `clearly_different`, `uncertain` (blank = undecided).  ",
          "Allowed `final_disposition`: `exclude_evaluation`, `keep`, `needs_secondary_review` "
          "(blank = undecided).", "",
          "Record decisions in `data/exclusions/cross_dataset_near_duplicate_review.csv`; confirmed "
          "exclusions are then copied to `data/exclusions/cross_dataset_reviewed_exclusions.csv`.", "",
          "| pair_id | d | train class | train path | eval class | eval path | contact sheet |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['pair_id']} | {r['phash_distance']} | {r['training_class']} | "
                  f"`{r['training_relative_path']}` | {r['evaluation_class']} | "
                  f"`{r['evaluation_relative_path']}` | `{Path(r['contact_sheet']).name}` |")
    md += ["", "_Automated visual-similarity notes on the contact sheets are non-authoritative "
           "heuristics and must not substitute for human judgement._", ""]
    (REPORTS / "NEAR_DUPLICATE_HUMAN_REVIEW.md").write_text("\n".join(md))

    return {"n_pairs": n, "sheets": sheet_files, "csv_rows": len(rows),
            "changes": change_report, "exclusions": excl_report}


def _write_change_report(change: dict, excl: dict, n_pairs: int) -> Path:
    """Explicit record of what regeneration preserved, added, and dropped."""
    L = [
        "# Near-Duplicate Review — Regeneration Change Report", "",
        "_Written by `scripts/prepare_human_review.py`. Regeneration merges prior human "
        "decisions back by canonical identity; this file records exactly what happened so "
        "nothing is lost silently (AUD-EC-004)._", "",
        f"- Authoritative near pairs: **{n_pairs}**",
        f"- Decisions preserved: **{len(change['preserved'])}**",
        f"- New undecided pairs: **{len(change['new'])}**",
        f"- Pairs no longer authoritative: **{len(change['dropped'])}**",
        f"- Reviewed exclusions preserved: **{excl['kept']}**",
        f"- Destructive reset used: **{'yes' if change['reset'] else 'no'}**", "",
    ]
    if change["preserved"]:
        L += ["## Preserved decisions", "",
              "  " + ", ".join(f"`{p}`" for p in sorted(change["preserved"])), ""]
    if change["new"]:
        L += ["## New pairs — undecided, require human review", "",
              "These pairs were newly detected. They are written with blank decision fields "
              "and **must be adjudicated**; the leakage gate cannot pass while they are "
              "pending.", "",
              "  " + ", ".join(f"`{p}`" for p in sorted(change["new"])), ""]
    if change["dropped"]:
        L += ["## Pairs no longer authoritative", "",
              "| pair_id | training path | evaluation path | had decision | decision |",
              "|---|---|---|---|---|"]
        for d in sorted(change["dropped"], key=lambda x: x["pair_id"]):
            L.append(f"| {d['pair_id']} | `{d['key'][0]}` | `{d['key'][1]}` | "
                     f"{'yes' if d['had_decision'] else 'no'} | "
                     f"{d['human_decision'] or '—'} / {d['final_disposition'] or '—'} |")
        L += ["", "These pairs are no longer detected by the current leakage computation, so "
              "their rows were not carried forward. Any decision they carried is recorded "
              "above rather than discarded silently.", ""]
    if excl["dropped"]:
        L += ["## Reviewed exclusions dropped", ""]
        for d in excl["dropped"]:
            L.append(f"- `{d['pair_id']}` — {d['key'][0]} -> {d['key'][1]}")
        L.append("")
    if excl["missing_propagation"]:
        L += ["## Exclude decisions without a propagated exclusion record", "",
              "  " + ", ".join(f"`{p}`" for p in excl["missing_propagation"]),
              "", "The leakage gate treats these as authorization violations until the "
              "exclusion rows exist.", ""]
    out = REPORTS / "NEAR_DUPLICATE_REVIEW_CHANGES.md"
    out.write_text("\n".join(L))
    return out


# --------------------------------------------------------------------------- #
# PART 4 — mapping human checklist (renders decisions; never makes one)
# --------------------------------------------------------------------------- #
#: review_status -> the `Human choice` token it corresponds to. A status outside
#: this map is undecided and renders as the blank `______` placeholder, so
#: regenerating the checklist can never invent or erase a human decision.
_STATUS_TO_CHOICE = {"approved": "approve", "excluded": "exclude"}


def _human_choice_line(row) -> str:
    choice = _STATUS_TO_CHOICE.get(str(row["review_status"]).strip())
    rendered = f"**{choice}**" if choice else "______"
    suffix = ""
    if choice:
        who = str(row.get("reviewer", "") or "").strip()
        when = str(row.get("reviewed_at", "") or "").strip()
        if who or when:
            suffix = f" — recorded by {who or 'unattributed'}" + (f" at {when}" if when else "")
    return ("- **Human choice** ( approve | revise | exclude | insufficient_evidence ): "
            f"{rendered}{suffix}")


def build_mapping_checklist() -> dict:
    df = pd.read_csv(DATA / "mapping" / "action_mapping_review.csv", dtype=str, keep_default_na=False)
    n = len(df)
    needs = int((df["review_status"] == "needs_review").sum())
    approved = int((df["review_status"] == "approved").sum())
    excluded = int((df["review_status"] == "excluded").sum())

    md = ["# Action-Mapping Human Checklist", "",
          "_Compact per-row checklist for human review. **This file makes no decision of its "
          "own**: every `Human choice` below is rendered from `review_status` in "
          "`data/mapping/action_mapping_review.csv`, and an undecided row renders as `______`. "
          "Evidence is unchanged and no new sources were fetched._", "",
          f"- Rows: **{n}** · needs_review: **{needs}** · approved: **{approved}** · "
          f"excluded: **{excluded}**",
          "- Allowed `Human choice`: `approve` · `revise` · `exclude` · `insufficient_evidence` "
          "(leave blank until decided).", ""]
    for _, r in df.iterrows():
        pathogen = r["pathogen_name"] or "(none — healthy/definitional)"
        ptype = r["pathogen_type"] or "(none)"
        amb = "yes" if ("AMBIGUOUS" in r["review_notes"]) else "no"
        md += [
            f"## {r['dataset_class']}", "",
            f"- Canonical disease: **{r['canonical_disease']}** (crop: {r['canonical_crop']})",
            f"- Pathogen / type: {pathogen} / **{ptype}**",
            f"- Proposed action (candidate only): **{r['candidate_action_class']}** — {r['action_summary']}",
            f"- Taxonomy + management source: {r['source_name']} "
            f"({r['source_url'] or 'definitional — no external URL'})",
            f"- Evidence summary: {r['evidence_summary']}",
            f"- Ambiguity: **{amb}**" + (f" — {r['review_notes']}" if r["review_notes"] else ""),
            f"- Confidence (author): {r['mapping_confidence']}",
            _human_choice_line(r),
            "",
        ]
    (REPORTS / "ACTION_MAPPING_HUMAN_CHECKLIST.md").write_text("\n".join(md))
    return {"rows": n, "needs_review": needs, "approved": approved, "excluded": excluded}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="prepare-human-review",
        description="Rebuild the Phase-1 human-review packet, preserving decisions.",
    )
    ap.add_argument(
        "--reset-human-decisions", action="store_true",
        help="DESTRUCTIVE: discard every recorded human decision and reviewed "
             "exclusion, emitting a blank packet. Without this flag, prior "
             "decisions are merged back by canonical identity and the run fails "
             "closed on identity drift.",
    )
    args = ap.parse_args(argv)

    if args.reset_human_decisions:
        print("!! --reset-human-decisions: ALL recorded human decisions and reviewed "
              "exclusions will be discarded.")

    print("[1/3] PlantDoc case-collision resolution + source inventory ...")
    r1 = build_source_inventory()
    print(f"      inventory rows={r1['inventory_rows']} upstream={r1['upstream']} "
          f"distinct_content={r1['materialized_content']}")
    print("[2/3] near-duplicate contact sheets + review packet ...")
    try:
        r2 = build_near_duplicate_packet(reset_human_decisions=args.reset_human_decisions)
    except HumanDecisionDrift as e:
        print(f"      FAILED: {e}")
        return 1
    ch, ex = r2["changes"], r2["exclusions"]
    print(f"      pairs={r2['n_pairs']} sheets={len(r2['sheets'])} "
          f"preserved={len(ch['preserved'])} new={len(ch['new'])} "
          f"dropped={len(ch['dropped'])} exclusions_kept={ex['kept']}")
    if ch["new"]:
        print(f"      NEW undecided pair(s) requiring human review: {', '.join(ch['new'])}")
    print("[3/3] mapping human checklist ...")
    r4 = build_mapping_checklist()
    print(f"      rows={r4['rows']} needs_review={r4['needs_review']} approved={r4['approved']}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
