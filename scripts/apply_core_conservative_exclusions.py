#!/usr/bin/env python
"""Apply the OPERATOR's conservative exclusions for Core Dataset V1 (R2B.2).

    python scripts/apply_core_conservative_exclusions.py --record ...   # once
    python scripts/apply_core_conservative_exclusions.py                # apply
    python scripts/apply_core_conservative_exclusions.py --check        # verify

Three PlantDoc duplicate groups (G07, G08, G10) had a canonical label applied
that no copy in the group carried, or that adjudicated between two contradictory
diagnoses on identical pixels. Those relabels were referred for an independent
scientific second review. That review has NOT been performed, and this script
does not perform it, simulate it, or stand in for it.

What the dataset owner may decide without a diagnosis is whether an uncertain
record belongs in the corpus at all. This script applies exactly that decision
and nothing else: it removes the named records and changes no label, no split,
no other record, and no image byte.

    data/exclusions/core_dataset_v1_conservative_exclusions.csv
        the immutable operator decision, one row per excluded record, each bound
        to the R2B outcome it overturns by identity, digest, label and split

    data/manifests/plantdoc_core_effective_manifest.csv
        Core Dataset V1's PlantDoc component: the R2B effective manifest with
        the conservatively excluded records removed

The R2B adjudication, its resolution table, its effective manifest, and every
historical review packet are read-only here and are left byte-for-byte intact.
The layering is deliberate and stays visible in the artifacts::

    plantdoc_manifest.csv            2,578  acquired source
      -> plantdoc_effective_manifest.csv    2,564  after R2B duplicate remediation
        -> plantdoc_core_effective_manifest.csv  2,561  after conservative exclusion

Idempotent and deterministic: the outputs are a pure function of the manifests
and the decision file, canonically ordered, with no wall-clock field, so a
second run reproduces them byte for byte.

Exit codes: 0 ok, 1 refused (unauthenticated decision) or stale (--check),
2 missing input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.conservative_exclusions import (  # noqa: E402
    CONSERVATIVE_EXCLUSION_DECISION,
    CONSERVATIVE_EXCLUSION_SCHEMA,
    EXCLUSION_BASES,
    EXCLUSION_COLUMNS,
    apply_conservative_exclusions,
    parse_conservative_exclusions,
    verify_core_records,
)
from ica26.datasets.duplicate_remediation import apply_adjudication  # noqa: E402
from ica26.datasets.duplicates import find_duplicate_groups  # noqa: E402
from ica26.schemas import IMAGE_MANIFEST_COLUMNS  # noqa: E402

MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
COLLISION_MAP = Path("data/manifests/plantdoc_case_collision_mapping.csv")
ACTIVE_ROOT = Path("data/raw/plantdoc")
GROUPS_CSV = Path("reports/plantdoc_exact_duplicate_review/plantdoc_exact_duplicate_groups.csv")
RESOLUTION = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
EFFECTIVE = Path("data/manifests/plantdoc_effective_manifest.csv")
SECOND_REVIEW_PACKET = Path("reports/plantdoc_label_second_review/packet_manifest.json")

DECISION = Path("data/exclusions/core_dataset_v1_conservative_exclusions.csv")
CORE_EFFECTIVE = Path("data/manifests/plantdoc_core_effective_manifest.csv")

SOURCE_REVISION = "5467f6012d78d1c446145d5f582da6096f852ae8"

#: Groups the operator decided to exclude. Named explicitly so a silent change
#: to the decision file cannot quietly widen or narrow the scope.
EXPECTED_EXCLUDED_GROUPS = ("G07", "G08", "G10")


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


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_digests(repo: Path) -> dict:
    """The current digests a decision row must be bound to."""
    return {
        "bound_resolution_sha256": sha256_of(repo / RESOLUTION),
        "bound_effective_manifest_sha256": sha256_of(repo / EFFECTIVE),
        "bound_second_review_packet_sha256": sha256_of(repo / SECOND_REVIEW_PACKET),
    }


def load_adjudication(repo: Path):
    """Re-derive the R2B outcomes from the manifest and the recorded decisions."""
    manifest = read_csv(repo / MANIFEST)
    original_of = {}
    if (repo / COLLISION_MAP).exists():
        for r in read_csv(repo / COLLISION_MAP):
            original_of[r["collision_safe_relative_path"]] = r["original_archive_path"]
    groups = find_duplicate_groups(
        manifest, dataset="PlantDoc", source_revision=SOURCE_REVISION,
        active_root=repo / ACTIVE_ROOT, original_path_of=original_of)
    decisions = read_csv(repo / GROUPS_CSV)
    return manifest, apply_adjudication(groups, decisions)


def build(repo: Path = REPO) -> tuple[str, dict]:
    """Render the Core manifest and the verification report. Writes nothing."""
    manifest, adj = load_adjudication(repo)
    effective = read_csv(repo / EFFECTIVE)

    rows = read_csv(repo / DECISION) if (repo / DECISION).exists() else []
    exclusions, parse_violations = parse_conservative_exclusions(
        rows, adj, artifact_digests=artifact_digests(repo))

    core, apply_violations = apply_conservative_exclusions(effective, exclusions)
    verify_violations, report = verify_core_records(
        manifest, effective, core, exclusions, adj)

    scope = sorted({e.display_group_id for e in exclusions})
    if exclusions and scope != sorted(EXPECTED_EXCLUDED_GROUPS):
        verify_violations.append(
            f"conservative exclusion scope is {scope}, this remediation records "
            f"{sorted(EXPECTED_EXCLUDED_GROUPS)}")

    report["violations"] = sorted(
        adj.violations + parse_violations + apply_violations + verify_violations)
    report["ok"] = not report["violations"]
    return render_csv(IMAGE_MANIFEST_COLUMNS, core), report


# --------------------------------------------------------------------------- #
# Recording the operator decision
# --------------------------------------------------------------------------- #
def record(repo: Path, args) -> int:
    """Mint the immutable decision file from authoritative bindings.

    The operator supplies the judgement -- who, when, why, and which groups. The
    identity, digest, label and split bindings are read from the R2B outcomes
    rather than retyped, because a decision that names the wrong record is worse
    than no decision, and a human cannot check thirty digests by eye.
    """
    target = repo / DECISION
    if target.exists():
        print(f"[core-exclusions] REFUSED — {DECISION} already exists; a recorded "
              "decision is immutable. Delete it deliberately if it was wrong.")
        return 1

    _, adj = load_adjudication(repo)
    if adj.violations:
        print("[core-exclusions] REFUSED — the R2B adjudication does not currently "
              "apply cleanly; nothing may be layered on top of it")
        for v in adj.violations[:10]:
            print(f"  VIOLATION {v}")
        return 1

    retained = {m.display_group_id: m for m in adj.members if m.retained}
    missing = [g for g in args.groups if g not in retained]
    if missing:
        print(f"[core-exclusions] REFUSED — no retained record for group(s) {missing}")
        return 1

    digests = artifact_digests(repo)
    rows = []
    for group in args.groups:
        outcome = retained[group]
        member = outcome.member
        rows.append({
            "decision_schema": CONSERVATIVE_EXCLUSION_SCHEMA,
            "group_id": outcome.group_id,
            "display_group_id": outcome.display_group_id,
            "member_id": outcome.member_id,
            "dataset": member.dataset,
            "active_relative_path": member.active_relative_path,
            "source_split": member.split,
            "source_class_label": member.class_label,
            "byte_sha256": member.byte_sha256,
            "decoded_rgb_sha256": member.decoded_rgb_sha256,
            "byte_size": member.byte_size,
            "width": member.width,
            "height": member.height,
            "mode": member.mode,
            "source_revision": member.source_revision,
            "prior_remediation_action": outcome.action,
            "prior_effective_split": outcome.effective_split,
            "prior_effective_class_label": outcome.effective_class_label,
            "prior_effective_record_id": outcome.as_row()["effective_record_id"],
            "exclusion_decision": CONSERVATIVE_EXCLUSION_DECISION,
            "exclusion_basis": args.basis,
            "exclusion_rationale": args.rationale,
            "reviewer_id": args.reviewer_id,
            "reviewer_role": args.reviewer_role,
            "decided_at": args.decided_at,
            "reviewed_repository_commit": args.reviewed_commit,
            **digests,
        })
    rows.sort(key=lambda r: (r["display_group_id"], r["member_id"]))
    atomic_write_text(target, render_csv(EXCLUSION_COLUMNS, rows))
    print(f"[core-exclusions] recorded {len(rows)} conservative exclusion(s) in {DECISION}")
    for r in rows:
        print(f"  {r['display_group_id']}/{r['member_id']} "
              f"{r['prior_effective_record_id']} "
              f"[{r['prior_effective_split']}] {r['prior_effective_class_label']}")
    return 0


def _head_commit(repo: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo),
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="apply-core-conservative-exclusions")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted Core manifest matches a fresh rebuild")
    ap.add_argument("--record", action="store_true",
                    help="mint the immutable operator decision file (once)")
    ap.add_argument("--groups", nargs="+", default=list(EXPECTED_EXCLUDED_GROUPS))
    ap.add_argument("--basis", default=EXCLUSION_BASES[0], choices=list(EXCLUSION_BASES))
    ap.add_argument("--rationale", default="")
    ap.add_argument("--reviewer-id", dest="reviewer_id", default="")
    ap.add_argument("--reviewer-role", dest="reviewer_role", default="")
    ap.add_argument("--decided-at", dest="decided_at", default="")
    ap.add_argument("--reviewed-commit", dest="reviewed_commit", default="")
    args = ap.parse_args(argv)

    for required in (MANIFEST, EFFECTIVE, RESOLUTION, GROUPS_CSV):
        if not (REPO / required).exists():
            print(f"[core-exclusions] required input not found: {required}")
            return 2

    if args.record:
        for name in ("rationale", "reviewer_id", "reviewer_role", "decided_at"):
            if not getattr(args, name):
                ap.error(f"--{name.replace('_', '-')} is required with --record")
        if not args.reviewed_commit:
            args.reviewed_commit = _head_commit(REPO)
        return record(REPO, args)

    if not (REPO / DECISION).exists():
        print(f"[core-exclusions] no operator decision at {DECISION}; nothing to "
              "apply. Core Dataset V1 is not defined without it.")
        return 2

    core_text, report = build()

    print(f"[core-exclusions] source={report['source_records']} "
          f"effective={report['effective_records']} -> core={report['core_records']} "
          f"(excluded {report['conservatively_excluded_records']} record(s) from "
          f"{report['conservatively_excluded_groups']})")
    print(f"[core-exclusions] retained_reviewed={report['retained_reviewed_records']} "
          f"excluded_reviewed={report['excluded_reviewed_records']} "
          f"non_reviewed={report['non_reviewed_records']} "
          f"unchanged={report['non_reviewed_records_unchanged']}")
    print(f"[core-exclusions] splits={report['core_split_counts']} "
          f"classes={report['core_class_count']} "
          f"surviving_exact_duplicate_groups={report['surviving_exact_duplicate_groups']}")

    if not report["ok"]:
        print(f"[core-exclusions] REFUSED — {len(report['violations'])} violation(s); "
              "nothing was written")
        for v in report["violations"][:10]:
            print(f"  VIOLATION {v}")
        return 1

    if args.check:
        target = REPO / CORE_EFFECTIVE
        if not target.exists() or target.read_text(encoding="utf-8") != core_text:
            print(f"[core-exclusions] CHECK FAILED — out of date: {CORE_EFFECTIVE}")
            return 1
        print("[core-exclusions] check OK — Core manifest matches a fresh rebuild")
        return 0

    atomic_write_text(REPO / CORE_EFFECTIVE, core_text)
    print(f"[core-exclusions] wrote {CORE_EFFECTIVE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
