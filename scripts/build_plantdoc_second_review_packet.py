#!/usr/bin/env python
"""Second-review packet for the PlantDoc canonical RELABELS. Decides nothing.

    python scripts/build_plantdoc_second_review_packet.py
    python scripts/build_plantdoc_second_review_packet.py --check

R2B applied twelve human duplicate decisions. Most left the retained record's own
label alone. Three changed it — adjudicating, on identical pixels, between two
contradictory diagnoses:

    G07  Potato leaf early blight   ->  Potato leaf late blight     (in_group)
    G10  Tomato Septoria leaf spot  ->  Tomato leaf bacterial spot  (in_group)
    G08  Potato leaf early blight   ->  Tomato leaf late blight     (outside_group;
                                                                     the crop changes too)

The groups are derived from the resolution table by comparing each retained
record's effective label against its own source label, not hard-coded — a future
adjudication that relabels a different group cannot escape this review by being
unlisted.

Each rests on one anonymous reviewer's written rationale with no independently
citable diagnostic source. That is enough to remove a duplicate; the audit found
it is not enough to assert a diagnosis that will be trained on and reported.

This script builds the packet a second, independent reviewer needs — the images,
both original labels, the digests, the decision currently in force, and the first
reviewer's reasoning quoted verbatim — with every second-review field left blank.

It does not diagnose, propose, weigh, or hint. It changes no decision: G07, G08
and G10 remain exactly as adjudicated. The packet is **pending** by
construction, satisfies no readiness condition, and cannot be completed by any
code path in this repository.

Exit codes: 0 ok, 1 stale (--check), 2 missing input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

RESOLUTION = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
PACKET_DIR = Path("reports/plantdoc_label_second_review")
REVIEW_CSV = "plantdoc_label_second_review.csv"
MEMBERS_CSV = "plantdoc_label_second_review_members.csv"
CHECKLIST_MD = "PLANTDOC_LABEL_SECOND_REVIEW.md"
MANIFEST_JSON = "packet_manifest.json"
PACKET_SCHEMA = "ica26.governance.plantdoc_label_second_review_packet/1"

#: Where the completed, human-authored verdict is expected. Never written here.
COMPLETED_ARTIFACT = Path("human_review/plantdoc_label_second_review/second_review.json")

#: Fields the INDEPENDENT reviewer fills. Emitted blank, always.
SECOND_REVIEW_FIELDS = (
    "independent_reviewer_id",
    "independent_reviewer_role",
    "independent_reviewed_at",
    "agreement",                        # agree | disagree | uncertain
    "proposed_canonical_label",
    "confidence",                       # low | moderate | high
    "diagnostic_evidence_citation",
    "diagnostic_evidence_url",
    "recommended_action_if_unresolved",  # exclude_record | retain_with_flag | escalate
    "independent_notes",
)

REVIEW_COLUMNS = (
    "display_group_id", "group_id", "byte_sha256", "decoded_rgb_sha256",
    "member_count", "source_class_labels", "source_splits",
    "applied_canonical_label", "applied_canonical_split", "relabel_kind",
    "retained_record_source_label", "applied_record_relpath",
    "applied_effective_record_id", "first_reviewer_id", "first_reviewed_at",
    "first_reviewer_rationale", "second_review_status",
) + SECOND_REVIEW_FIELDS

MEMBER_COLUMNS = (
    "display_group_id", "member_id", "active_relative_path", "original_archive_path",
    "source_split", "source_class_label", "byte_sha256", "decoded_rgb_sha256",
    "byte_size", "width", "height", "mode", "remediation_action",
    "effective_split", "effective_class_label",
)


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def render_csv(columns, rows) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r.get(c, "") for c in columns})
    return buf.getvalue()


def atomic_write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def relabel_kind(members: list[dict]) -> str:
    """How far the canonical decision moved the retained record's label.

    ``in_group`` — the retained record took the OTHER copy's label. A diagnosis
    was still chosen between two contradictory ones.
    ``outside_group`` — the retained record took a label neither copy carried.
    ``unchanged`` — the retained record kept its own label; no relabel occurred.
    """
    kept = [m for m in members if m["remediation_action"] == "retain_canonical"]
    if not kept:
        return "unchanged"
    applied = kept[0]["effective_class_label"]
    if applied == kept[0]["source_class_label"]:
        return "unchanged"
    return "in_group" if applied in {m["source_class_label"] for m in members} \
        else "outside_group"


def relabelled_groups(resolution_rows: list[dict]) -> list[str]:
    """Display ids whose RETAINED record was given a different label.

    The test is the retained record's OWN label changing — not whether the new
    label appears somewhere in the group. Taking the other copy's label is still
    adjudicating between two contradictory diagnoses on identical pixels, and
    that is exactly the judgement under review.

    Derived from the resolution table rather than hard-coded, so a future
    adjudication that relabels a different group cannot quietly escape review.
    """
    by_group: dict[str, list[dict]] = {}
    for r in resolution_rows:
        by_group.setdefault(r["display_group_id"], []).append(r)
    return [gid for gid, members in sorted(by_group.items())
            if relabel_kind(members) != "unchanged"]


def build(repo: Path | None = None) -> tuple[dict[str, str], dict]:
    """Render every packet artifact. Writes nothing."""
    repo = repo or REPO
    rows = read_csv(repo / RESOLUTION)
    targets = relabelled_groups(rows)
    by_group: dict[str, list[dict]] = {}
    for r in rows:
        if r["display_group_id"] in targets:
            by_group.setdefault(r["display_group_id"], []).append(r)

    review_rows, member_rows = [], []
    for gid in targets:
        members = sorted(by_group[gid], key=lambda m: m["member_id"])
        kept = next(m for m in members if m["remediation_action"] == "retain_canonical")
        review_rows.append({
            "display_group_id": gid,
            "group_id": kept["group_id"],
            "byte_sha256": kept["byte_sha256"],
            "decoded_rgb_sha256": kept["decoded_rgb_sha256"],
            "member_count": len(members),
            "source_class_labels": " | ".join(sorted({m["source_class_label"] for m in members})),
            "source_splits": " | ".join(sorted({m["source_split"] for m in members})),
            "applied_canonical_label": kept["effective_class_label"],
            "applied_canonical_split": kept["effective_split"],
            "relabel_kind": relabel_kind(members),
            "retained_record_source_label": kept["source_class_label"],
            "applied_record_relpath": kept["active_relative_path"],
            "applied_effective_record_id": kept["effective_record_id"],
            "first_reviewer_id": kept["reviewer"],
            "first_reviewed_at": kept["reviewed_at"],
            "first_reviewer_rationale": kept["decision_reason"],
            "second_review_status": "pending",
            **{f: "" for f in SECOND_REVIEW_FIELDS},
        })
        for m in members:
            member_rows.append({c: m.get(c, "") for c in MEMBER_COLUMNS})

    artifacts = {
        REVIEW_CSV: render_csv(REVIEW_COLUMNS, review_rows),
        MEMBERS_CSV: render_csv(MEMBER_COLUMNS, member_rows),
        CHECKLIST_MD: render_markdown(review_rows, member_rows),
    }
    meta = {"groups": targets, "records": len(member_rows)}
    entries = {
        name: hashlib.sha256(text.encode("utf-8")).hexdigest()
        for name, text in sorted(artifacts.items())
    }
    artifacts[MANIFEST_JSON] = json.dumps({
        "_note": "SHA-256 of every packet artifact. No wall-clock field, so the packet "
                 "is byte-deterministic and can be re-derived and compared.",
        "schema_version": PACKET_SCHEMA,
        "dataset": "PlantDoc",
        "groups_under_review": meta["groups"],
        "records": meta["records"],
        "status": "pending",
        "completed_artifact_expected_at": str(COMPLETED_ARTIFACT),
        "artifacts": entries,
    }, indent=2, sort_keys=True) + "\n"
    return artifacts, meta


def render_markdown(review_rows, member_rows) -> str:
    L = [
        "# PlantDoc canonical relabels — independent second review", "",
        "_Generated by `scripts/build_plantdoc_second_review_packet.py`. **This packet "
        "makes no diagnosis and proposes none.** Every second-review field is blank, and "
        "nothing here changes the decision currently in force._", "",
        "## Why these groups", "",
        "R2B applied twelve human duplicate decisions. Most kept the retained record's own "
        "label. In the groups below the retained record was given a **different** label: "
        "`in_group` means it took the other copy's label, adjudicating between two "
        "contradictory diagnoses on identical pixels; `outside_group` means it took a "
        "label neither copy carried — in one case changing the crop as well. Removing a "
        "duplicate on one reviewer's judgement is proportionate; asserting a diagnosis "
        "that will be trained on and reported is not.", "",
        "The duplicate remediation itself is **not** in question here: the byte identity is "
        "machine-proved and the exclusions stand either way. What is under review is only "
        "the canonical *label* applied to the surviving record.", "",
        "## What is already established", "",
        "For each group the file bytes and decoded pixels of both records are identical "
        "(digests below), and the first reviewer's rationale is quoted verbatim and "
        "unedited. Neither is in dispute.", "",
        "## What a second reviewer is asked for", "",
        "1. **Agreement** with the applied canonical label — `agree`, `disagree`, or "
        "`uncertain`.",
        "2. **An independently citable diagnostic source.** A filename, a dataset "
        "annotation, and a previous reviewer's opinion are none of them evidence. If no "
        "citable source supports a confident call, say so — `uncertain` with "
        "`recommended_action_if_unresolved` is a complete and useful answer.",
        "3. **Confidence** and, on disagreement, a proposed label.",
        "4. **What to do if it stays unresolved** — `exclude_record`, `retain_with_flag`, "
        "or `escalate`.", "",
        "Do not feel obliged to confirm. An excluded record costs the dataset one image; a "
        "wrong label costs every number computed from it.", "",
        "## Groups under review", "",
    ]
    members_by_group: dict[str, list[dict]] = {}
    for m in member_rows:
        members_by_group.setdefault(m["display_group_id"], []).append(m)

    for r in review_rows:
        gid = r["display_group_id"]
        L += [f"### {gid} — `{r['group_id']}`", "",
              f"- byte SHA-256: `{r['byte_sha256']}`",
              f"- decoded RGB SHA-256: `{r['decoded_rgb_sha256']}`",
              f"- labels carried by the two copies: **{r['source_class_labels']}**",
              f"- retained record's own original label: **{r['retained_record_source_label']}**",
              f"- **canonical label currently applied: `{r['applied_canonical_label']}`** "
              f"(split `{r['applied_canonical_split']}`, relabel kind "
              f"`{r['relabel_kind']}`)",
              f"- retained record: `{r['applied_record_relpath']}`",
              f"- effective record id: `{r['applied_effective_record_id']}`",
              f"- first reviewer: `{r['first_reviewer_id']}` at `{r['first_reviewed_at']}`",
              "",
              f"> {r['first_reviewer_rationale']}", "",
              "| member | split | class | size | dimensions | path |",
              "|---|---|---|---:|---:|---|"]
        for m in members_by_group.get(gid, []):
            L.append(f"| {m['member_id']} | {m['source_split']} | {m['source_class_label']} | "
                     f"{int(m['byte_size']):,} B | {m['width']}x{m['height']} | "
                     f"`{m['active_relative_path']}` |")
        L += ["", "- **Agreement** ( agree | disagree | uncertain ): ______",
              "- **Proposed canonical label** (only if disagreeing): ______",
              "- **Confidence** ( low | moderate | high ): ______",
              "- **Diagnostic evidence citation** (author/title/identifier): ______",
              "- **Evidence URL**: ______",
              "- **Recommended action if unresolved** ( exclude_record | retain_with_flag "
              "| escalate ): ______",
              "- **Independent reviewer id** (anonymous): ______",
              "- **Reviewer role / qualification**: ______",
              "- **Reviewed at** (ISO-8601 with timezone offset): ______", ""]

    L += ["## Recording the verdict", "",
          f"Fill `{REVIEW_CSV}`, then record the signed verdict as JSON at:", "",
          f"    {COMPLETED_ARTIFACT}", "",
          "It must satisfy `ica26.governance.approvals.SECOND_REVIEW_SPEC`: generic approval "
          "authorship and reviewed-state fields plus `review_schema_version` and a `groups` "
          "list containing exactly one self-contained object for each of G07, G08, and G10. "
          "Every group object binds this packet manifest's SHA-256 and repeats its exact "
          "member ids and byte SHA-256 values, current effective record id and label, decision "
          "(`agree`, `disagree`, or `uncertain`), strict confidence, independent reviewer id "
          "and qualification, offset timestamp, rationale, structured citations, and a "
          "decision-consistent recommended action. Missing, duplicate, extra, stale, "
          "contradictory, or placeholder content is refused. Only three valid `agree` records "
          "can satisfy readiness; `uncertain` always remains blocked.", "",
          "## What this packet does NOT do", "",
          "- It proposes no diagnosis and offers no recommendation.",
          "- It changes no adjudicated decision, label, split, or record identity.",
          "- It does not satisfy any freeze-readiness condition; the second review reports "
          "as **pending** until a valid human artifact exists.",
          "- It fabricates no citation, and no code in this repository can complete it.", ""]
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build-plantdoc-second-review-packet")
    ap.add_argument("--check", action="store_true",
                    help="verify the packet matches current data; write nothing")
    args = ap.parse_args(argv)

    if not (REPO / RESOLUTION).exists():
        print(f"[second-review] resolution table not found: {RESOLUTION}")
        return 2

    artifacts, meta = build()
    packet = REPO / PACKET_DIR
    print(f"[second-review] relabelled groups requiring independent review: "
          f"{meta['groups']} ({meta['records']} record(s))")

    if args.check:
        stale = [n for n, text in artifacts.items()
                 if not (packet / n).exists()
                 or (packet / n).read_text(encoding="utf-8") != text]
        if stale:
            print("[second-review] CHECK FAILED — out of date: " + ", ".join(stale))
            return 1
        print("[second-review] check OK — packet matches current data")
        return 0

    for name, text in artifacts.items():
        atomic_write_text(packet / name, text)

    print(f"[second-review] wrote {len(artifacts)} artifact(s) to {PACKET_DIR}")
    print("[second-review] every second-review field is blank — this packet proposes "
          "no diagnosis and satisfies no readiness condition")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
