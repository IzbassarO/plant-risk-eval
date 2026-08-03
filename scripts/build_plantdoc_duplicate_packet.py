#!/usr/bin/env python
"""Build the PlantDoc byte-exact duplicate HUMAN-REVIEW packet (makes NO decision).

    python scripts/build_plantdoc_duplicate_packet.py
    python scripts/build_plantdoc_duplicate_packet.py --check   # fail if stale

Addresses R1-CRIT-002. The restored PlantDoc V1 contains groups of records whose
FILE BYTES are identical. Most straddle the train/test boundary, and most assign
two different diagnosis labels to identical pixels. Byte identity is already
machine-proved; what remains is scientific and belongs to a human:

  * evaluation inclusion policy -- may a test record that is byte-identical to a
    training record count as held-out?
  * group-aware split handling -- if kept, must all members sit on one side?
  * contradictory-label adjudication -- identical pixels, two diagnoses.

This script deliberately cannot answer any of those. Every decision column is
emitted blank, the contact sheets carry no recommendation, and nothing in the
dataset is deleted, relabelled, moved between splits, or excluded.

Outputs under reports/plantdoc_exact_duplicate_review/:
    plantdoc_exact_duplicate_groups.csv     one row per group, decisions blank
    plantdoc_exact_duplicate_members.csv    two immutable rows per group
    PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md
    contact_sheet_*.png                     both members, full and uncropped
    packet_manifest.json                    SHA-256 of every packet artifact
    README.md                               how to review the packet

Deterministic: identical inputs produce byte-identical outputs, so the packet can
be re-derived and compared. Exit codes: 0 ok, 1 stale (--check), 2 missing input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.duplicates import (  # noqa: E402
    DUPLICATE_GROUP_SCHEMA,
    GROUP_HANDLING_DECISIONS,
    SPLIT_HANDLING_DECISIONS,
    aggregate,
    display_group_ids,
    find_duplicate_groups,
    member_ids,
)

MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
INVENTORY = Path("data/manifests/plantdoc_source_inventory.csv")
COLLISION_MAP = Path("data/manifests/plantdoc_case_collision_mapping.csv")
ACTIVE_ROOT = Path("data/raw/plantdoc")
PACKET_DIR = Path("reports/plantdoc_exact_duplicate_review")
SOURCE_REVISION = "5467f6012d78d1c446145d5f582da6096f852ae8"

GROUP_COLUMNS = [
    "group_id", "display_group_id", "canonical_content_id", "byte_sha256",
    "decoded_rgb_sha256", "member_count", "crosses_split", "crosses_class",
    "train_count", "test_count", "class_count", "class_labels", "current_status",
    # ---- human decision fields: MUST be left blank by this script ----
    "group_handling_decision", "canonical_label_decision", "split_handling_decision",
    "decision_reason", "reviewer", "reviewed_at",
]

MEMBER_COLUMNS = [
    "group_id", "display_group_id", "member_id", "dataset", "original_archive_path",
    "active_relative_path", "split", "class_label", "byte_sha256",
    "decoded_rgb_sha256", "byte_size", "width", "height", "mode", "source_revision",
]

DECISION_COLUMNS = ("group_handling_decision", "canonical_label_decision",
                    "split_handling_decision", "decision_reason", "reviewer",
                    "reviewed_at")


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def render_csv(columns, rows) -> str:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Contact sheets
# --------------------------------------------------------------------------- #
def _font(size: int):
    from PIL import ImageFont

    for cand in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                 "/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _contain(im, box: int, bg=(235, 235, 235)):
    """Contain-fit the FULL image; never crop, so nothing is hidden from review."""
    from PIL import Image

    im = im.convert("RGB")
    w, h = im.size
    scale = min(box / w, box / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    canvas = Image.new("RGB", (box, box), bg)
    canvas.paste(im.resize((nw, nh)), ((box - nw) // 2, (box - nh) // 2))
    return canvas


def build_contact_sheets(groups, display, out_dir: Path, per_page: int = 3) -> list[str]:
    from PIL import Image, ImageDraw

    BOX = 300
    PANEL_W, PANEL_H = 2 * BOX + 60, BOX + 140
    font, font_b = _font(13), _font(15)

    panels = []
    for g in groups:
        panel = Image.new("RGB", (PANEL_W, PANEL_H), (255, 255, 255))
        d = ImageDraw.Draw(panel)
        flags = []
        flags.append("CROSS-SPLIT (train/test)" if g.crosses_split else "same split")
        flags.append("CROSS-CLASS (contradictory labels)" if g.crosses_class else "same class")
        d.text((20, 8), f"{display[g.canonical_content_id]}  {g.canonical_content_id}  "
                        f"byte-identical  |  {'  |  '.join(flags)}",
               font=font_b, fill=(0, 0, 0))
        for j, m in enumerate(g.members[:2]):
            with Image.open(REPO / ACTIVE_ROOT / m.active_relative_path) as im:
                panel.paste(_contain(im, BOX), (20 + j * (BOX + 20), 34))
        y = 34 + BOX + 6
        for j, m in enumerate(g.members[:2]):
            colour = (20, 20, 120) if m.split == "train" else (120, 20, 20)
            d.text((20, y), f"[{m.split}] {m.class_label}   {m.width}x{m.height}   "
                            f"{m.byte_size:,} B   sha={m.byte_sha256[:12]}",
                   font=font, fill=colour)
            d.text((20, y + 16), f"  {m.active_relative_path}", font=font, fill=(60, 60, 60))
            y += 38
        d.text((20, y), "No automated recommendation. Byte identity is machine-verified; "
                        "inclusion, split and label are human decisions.",
               font=font, fill=(90, 90, 90))
        panels.append(panel)

    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    n_pages = (len(panels) + per_page - 1) // per_page
    for pg in range(n_pages):
        chunk = panels[pg * per_page:(pg + 1) * per_page]
        page = Image.new("RGB", (PANEL_W, PANEL_H * per_page + 40), (255, 255, 255))
        hd = ImageDraw.Draw(page)
        hd.text((20, 10), f"PlantDoc byte-exact duplicate review — sheet {pg + 1}/{n_pages} "
                          "— NOT auto-excluded; human decision required",
                font=_font(14), fill=(0, 0, 0))
        for j, panel in enumerate(chunk):
            page.paste(panel, (0, 40 + j * PANEL_H))
        name = f"contact_sheet_{pg + 1:02d}.png"
        tmp = out_dir / (name + ".part.png")
        page.save(tmp)
        os.replace(tmp, out_dir / name)
        sheets.append(name)
    return sheets


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def render_markdown(groups, display, agg, sheets) -> str:
    L = [
        "# PlantDoc Byte-Exact Duplicate — Human Review", "",
        "_Generated by `scripts/build_plantdoc_duplicate_packet.py`. **This packet makes no "
        "decision.** Every decision column is blank and no recommendation is offered._", "",
        "## What is already machine-verified", "",
        "For every group below, the members' **file bytes are identical** (same SHA-256) and "
        "their **decoded RGB pixels are identical** (same pixel-buffer digest). That is not in "
        "question and needs no human judgement.", "",
        "## What requires a human decision", "",
        "1. **Evaluation inclusion policy.** May a test record that is byte-identical to a "
        "training record count as held out? Accuracy measured on it can be memorisation.",
        "2. **Group-aware split handling.** If records are kept, must every member of a group "
        "sit on the same side of the split?",
        "3. **Contradictory-label adjudication.** Where identical pixels carry two different "
        "diagnosis labels, at most one can be right; this packet does not say which.", "",
        "None of these is answered here. Record decisions in "
        "`plantdoc_exact_duplicate_groups.csv`.", "",
        "## Scope of the problem", "",
        f"- Duplicate groups: **{agg['groups']}**",
        f"- Records involved: **{agg['records']}**",
        f"- Groups crossing train/test: **{agg['cross_split_groups']}**",
        f"- Groups with contradictory class labels: **{agg['cross_class_groups']}**", "",
        "| Category | Groups |",
        "|---|---:|",
        f"| Same class, same split | {agg['same_class_same_split']} |",
        f"| Same class, cross split | {agg['same_class_cross_split']} |",
        f"| Cross class, same split | {agg['cross_class_same_split']} |",
        f"| Cross class, cross split | {agg['cross_class_cross_split']} |", "",
        "## Groups", "",
    ]
    for g in groups:
        gid = display[g.canonical_content_id]
        flags = []
        if g.crosses_split:
            flags.append("**crosses train/test**")
        if g.crosses_class:
            flags.append("**contradictory labels**")
        L += [f"### {gid} — `{g.canonical_content_id}`", "",
              f"- byte SHA-256: `{g.byte_sha256}`",
              f"- decoded RGB SHA-256: `{g.decoded_rgb_sha256}`",
              f"- members: {g.member_count} · train {g.train_count} / test {g.test_count} · "
              f"classes {g.class_count}",
              f"- flags: {', '.join(flags) if flags else 'same class, same split'}", "",
              "| split | class | size | dimensions | active path |",
              "|---|---|---:|---:|---|"]
        for m in g.members:
            L.append(f"| {m.split} | {m.class_label} | {m.byte_size:,} B | "
                     f"{m.width}x{m.height} | `{m.active_relative_path}` |")
        L += ["", "- **Group handling decision** "
              f"( {' | '.join(GROUP_HANDLING_DECISIONS)} ): ______",
              "- **Canonical label decision** ( exact class name | not_applicable ): ______",
              "- **Split handling decision** "
              f"( {' | '.join(SPLIT_HANDLING_DECISIONS)} ): ______",
              "- **Decision reason**: ______",
              "- **Reviewer** (anonymous id): ______",
              "- **Reviewed at** (ISO-8601 with timezone offset): ______", ""]

    L += ["## Contact sheets", "",
          "Full, uncropped images of both members, with split, class, size and SHA prefix, and "
          "explicit cross-split / cross-class flags. No recommendation is printed.", ""]
    L += [f"- `{s}`" for s in sheets]
    L += ["", "## What this packet does NOT do", "",
          "- It deletes no image and removes no manifest row.",
          "- It changes no class label and moves nothing between splits.",
          "- It excludes nothing from evaluation.",
          "- It infers no canonical diagnosis for a contradictory pair.",
          "- It writes no reviewer, timestamp, or decision.", ""]
    return "\n".join(L)


def render_readme(agg, sheets) -> str:
    return "\n".join([
        "# How to review this packet", "",
        "_This directory is a decision-neutral review packet for the byte-exact duplicate "
        "records inside PlantDoc (R1-CRIT-002). Nothing in it has been decided._", "",
        "## Files", "",
        "| File | Purpose |",
        "|---|---|",
        "| `PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md` | The checklist. Read this first. |",
        "| `plantdoc_exact_duplicate_groups.csv` | One row per group. **Write decisions here.** |",
        "| `plantdoc_exact_duplicate_members.csv` | Two immutable evidence rows per group. Do not edit. |",
        "| `contact_sheet_*.png` | Full uncropped images of both members of each group. |",
        "| `packet_manifest.json` | SHA-256 of every artifact above, for integrity checking. |", "",
        "## Steps", "",
        "1. Open the contact sheets and look at each pair. The bytes are already proved "
        "identical; you are judging what that means scientifically.",
        "2. For each group, fill in these columns of `plantdoc_exact_duplicate_groups.csv`:",
        "   `group_handling_decision`, `canonical_label_decision`, `split_handling_decision`, "
        "`decision_reason`, `reviewer`, `reviewed_at`.",
        "3. Use an anonymous reviewer identifier (e.g. `human_reviewer_1`) — the submission is "
        "double-blind. Never write a real name, email, or account.",
        "4. `reviewed_at` must be strict ISO-8601 **with a timezone offset**, e.g. "
        "`2026-08-03T14:30:00+05:00`. Blank, naive, or future timestamps are rejected.",
        "5. Leave `plantdoc_exact_duplicate_members.csv` untouched; it is evidence, not a form.",
        "6. Re-run `python scripts/build_plantdoc_internal_duplicate_gate.py` to see the status "
        "move from `incomplete` toward `pass`.", "",
        "## Rules", "",
        f"- All **{agg['groups']}** groups need a terminal decision; a partially decided packet "
        "stays `incomplete`.",
        "- `needs_further_review` is allowed but resolves nothing.",
        "- Do not delete, relabel, or move any record by hand. Record the decision here; the "
        "pipeline applies it in a later, separately audited step.", "",
        "## Regenerating", "",
        "`python scripts/build_plantdoc_duplicate_packet.py` is deterministic and preserves any "
        "decisions already recorded in the groups CSV. `--check` verifies the packet is current "
        "without writing.", "",
    ])


# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build-plantdoc-duplicate-packet")
    ap.add_argument("--check", action="store_true",
                    help="verify the packet matches current data; write nothing")
    ap.add_argument("--packet-dir", default=str(PACKET_DIR))
    args = ap.parse_args(argv)

    manifest_path = REPO / MANIFEST
    if not manifest_path.exists():
        print(f"[dup-packet] manifest not found: {MANIFEST}")
        return 2
    manifest = read_csv(manifest_path)

    original_of = {}
    if (REPO / COLLISION_MAP).exists():
        for r in read_csv(REPO / COLLISION_MAP):
            original_of[r["collision_safe_relative_path"]] = r["original_archive_path"]

    groups = find_duplicate_groups(
        manifest, dataset="PlantDoc", source_revision=SOURCE_REVISION,
        active_root=REPO / ACTIVE_ROOT, original_path_of=original_of)
    agg = aggregate(groups)
    print(f"[dup-packet] groups={agg['groups']} records={agg['records']} "
          f"cross_split={agg['cross_split_groups']} cross_class={agg['cross_class_groups']}")

    # Human-friendly labels, assigned from a canonical sort so they are stable.
    # Derived from the shared helper so the packet, the remediation and the gate
    # can never disagree about which group is G07.
    ordered = sorted(groups, key=lambda g: g.byte_sha256)
    display = display_group_ids(groups)

    packet = REPO / args.packet_dir
    groups_csv = packet / "plantdoc_exact_duplicate_groups.csv"

    # Preserve any decisions already recorded, keyed by canonical content id.
    prior = {}
    if groups_csv.exists():
        for r in read_csv(groups_csv):
            prior[(r.get("canonical_content_id") or "").strip()] = r

    group_rows = []
    for g in ordered:
        cid = g.canonical_content_id
        old = prior.get(cid, {})
        row = {
            "group_id": cid,
            "display_group_id": display[cid],
            "canonical_content_id": cid,
            "byte_sha256": g.byte_sha256,
            "decoded_rgb_sha256": g.decoded_rgb_sha256,
            "member_count": g.member_count,
            "crosses_split": "true" if g.crosses_split else "false",
            "crosses_class": "true" if g.crosses_class else "false",
            "train_count": g.train_count,
            "test_count": g.test_count,
            "class_count": g.class_count,
            "class_labels": " | ".join(g.classes),
            "current_status": "unresolved",
        }
        # Decisions are carried over if a human already wrote them; this script
        # never originates one.
        for c in DECISION_COLUMNS:
            row[c] = (old.get(c) or "").strip()
        if (row.get("group_handling_decision") or "").strip():
            row["current_status"] = "decision_recorded"
        group_rows.append(row)

    member_rows = []
    for g in ordered:
        cid = g.canonical_content_id
        ids = member_ids(g, display[cid])
        for m in g.members:
            member_rows.append({
                "group_id": cid, "display_group_id": display[cid],
                "member_id": ids[m.active_relative_path], **m.as_dict(),
            })

    sheets = ([] if args.check
              else build_contact_sheets(ordered, display, packet))
    if args.check:
        sheets = sorted(p.name for p in packet.glob("contact_sheet_*.png"))

    artifacts = {
        "plantdoc_exact_duplicate_groups.csv": render_csv(GROUP_COLUMNS, group_rows),
        "plantdoc_exact_duplicate_members.csv": render_csv(MEMBER_COLUMNS, member_rows),
        "PLANTDOC_EXACT_DUPLICATE_HUMAN_REVIEW.md": render_markdown(ordered, display, agg, sheets),
        "README.md": render_readme(agg, sheets),
    }

    if args.check:
        stale = [n for n, text in artifacts.items()
                 if not (packet / n).exists() or (packet / n).read_text(encoding="utf-8") != text]
        if stale:
            print("[dup-packet] CHECK FAILED — out of date: " + ", ".join(stale))
            return 1
        print("[dup-packet] check OK — packet matches current data")
        return 0

    for name, text in artifacts.items():
        atomic_write_text(packet / name, text)

    manifest_entries = {}
    for name in sorted(list(artifacts) + sheets):
        manifest_entries[name] = sha256_of(packet / name)
    atomic_write_text(packet / "packet_manifest.json", json.dumps({
        "_note": "SHA-256 of every packet artifact. No wall-clock field, so the "
                 "packet is byte-deterministic and can be re-derived and compared.",
        "dataset": "PlantDoc",
        "source_revision": SOURCE_REVISION,
        "group_schema": DUPLICATE_GROUP_SCHEMA,
        "aggregate": agg,
        "artifacts": manifest_entries,
    }, indent=2, sort_keys=True) + "\n")

    print(f"[dup-packet] wrote {len(artifacts) + len(sheets) + 1} artifact(s) to "
          f"{args.packet_dir}")
    # Report what the decision columns actually hold. A hard-coded "no decision
    # was made" would keep printing after a human had decided, which is exactly
    # the kind of stale reassurance this packet exists to avoid.
    decided = sum(1 for r in group_rows if r["group_handling_decision"])
    print(f"[dup-packet] decisions carried over from the existing packet: "
          f"{decided} recorded, {len(group_rows) - decided} blank — this script "
          "originated none of them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
