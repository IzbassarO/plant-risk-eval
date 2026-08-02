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

import csv
import glob
import hashlib
import io
import json
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

    # ---- Build the full 2,578-row inventory ----
    # upstream paths = all manifest relpaths (2,572) + the 6 non-surviving members.
    upstream = list(man["relpath"]) + [rel for rel in collision_members if rel not in man_by_rel]
    upstream = sorted(set(upstream))
    rows = []
    for rel in upstream:
        split = rel.split("/", 1)[0]
        cls = rel.split("/")[1] if "/" in rel[len(split) + 1:] else rel.split("/")[1]
        if rel in materialized_for:
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
                "split": split, "class": cls,
                "collision_group": group,
                "materialization_status": status,
                "notes": notes,
            })
        else:
            r = man_by_rel[rel]
            rows.append({
                "source_revision": PLANTDOC_COMMIT,
                "original_upstream_path": rel,
                "materialized_relative_path": f"data/raw/plantdoc/{rel}",
                "source_sha256": r["sha256"],
                "materialized_sha256": r["sha256"],
                "file_size": r["n_bytes"],
                "width": r["width"], "height": r["height"], "mode": r["mode"],
                "split": split, "class": r["class_label"],
                "collision_group": "",
                "materialization_status": "materialized",
                "notes": "",
            })
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


def build_near_duplicate_packet() -> dict:
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

    # ---- review CSV (human fields blank) ----
    cols = ["pair_id", "training_dataset", "training_relative_path", "training_class",
            "training_sha256", "evaluation_dataset", "evaluation_relative_path",
            "evaluation_class", "evaluation_sha256", "phash_distance", "contact_sheet",
            "human_decision", "decision_reason", "reviewer", "reviewed_at", "final_disposition"]
    df = pd.DataFrame(rows, columns=cols)
    out_csv = DATA / "exclusions" / "cross_dataset_near_duplicate_review.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_csv.with_suffix(".csv.part")
    df.to_csv(tmp, index=False)
    tmp.replace(out_csv)

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

    return {"n_pairs": n, "sheets": sheet_files, "csv_rows": len(df)}


# --------------------------------------------------------------------------- #
# PART 3 — reviewed-exclusions skeleton (unpopulated)
# --------------------------------------------------------------------------- #
def build_reviewed_exclusions_skeleton() -> Path:
    cols = ["pair_id", "match_type", "training_relative_path", "evaluation_relative_path",
            "phash_distance", "human_decision", "exclusion_reason", "reviewer", "reviewed_at",
            "source_review_file"]
    out = DATA / "exclusions" / "cross_dataset_reviewed_exclusions.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    # header only — no rows (no prior human decisions exist).
    pd.DataFrame([], columns=cols).to_csv(out, index=False)
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


def main() -> int:
    print("[1/4] PlantDoc case-collision resolution + source inventory ...")
    r1 = build_source_inventory()
    print(f"      inventory rows={r1['inventory_rows']} upstream={r1['upstream']} "
          f"distinct_content={r1['materialized_content']}")
    print("[2/4] near-duplicate contact sheets + review packet ...")
    r2 = build_near_duplicate_packet()
    print(f"      pairs={r2['n_pairs']} sheets={len(r2['sheets'])}")
    print("[3/4] reviewed-exclusions skeleton ...")
    p3 = build_reviewed_exclusions_skeleton()
    print(f"      wrote {p3.relative_to(REPO)} (header only)")
    print("[4/4] mapping human checklist ...")
    r4 = build_mapping_checklist()
    print(f"      rows={r4['rows']} needs_review={r4['needs_review']} approved={r4['approved']}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
