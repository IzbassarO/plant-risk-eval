#!/usr/bin/env python
"""Fail-closed gate for byte-exact duplicate groups INSIDE PlantDoc (R1-CRIT-002).

    python scripts/build_plantdoc_internal_duplicate_gate.py
    python scripts/build_plantdoc_internal_duplicate_gate.py --check

Deliberately SEPARATE from the cross-dataset leakage gate. The two answer
different scientific questions, and overloading one artifact with both is how a
"pass" comes to mean less than a reader assumes:

    reports/leakage_gate.json                    PlantVillage -> PlantDoc overlap
    reports/plantdoc_internal_duplicate_gate.json  duplicates within PlantDoc

This gate reports `incomplete` until a human records a terminal decision for
EVERY enumerated group, and `fail` on any authorization violation. There is no
count parameter and no override. It decides nothing itself.

Schema 2.0 (R2B) added the second half of the question. "A human decided" is not
the same claim as "the decision was applied", so the gate now also proves the
effective dataset is exactly what those decisions authorise: one canonical record
per `keep_one_record` group and none per `exclude_all_records`, the adjudicated
label and split on every retained record, no exact duplicate surviving anywhere,
no record outside the reviewed set changed, and the persisted effective manifest
equal to a fresh rebuild by identity SET rather than by row count.

Bound inputs (digested, and re-digested on validation): the PlantDoc manifest,
the duplicate group table, the member table, the resolution table, the effective
manifest, and the schema/policy version.

Deterministic: no wall-clock field, so repeated builds are byte-identical.
Exit codes: 0 pass, 1 fail/incomplete, 2 missing input, 3 stale (--check).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ica26.datasets.duplicates import (  # noqa: E402
    DUPLICATE_GROUP_SCHEMA,
    aggregate,
    build_internal_duplicate_gate,
    find_duplicate_groups,
)

MANIFEST = Path("data/manifests/plantdoc_manifest.csv")
COLLISION_MAP = Path("data/manifests/plantdoc_case_collision_mapping.csv")
ACTIVE_ROOT = Path("data/raw/plantdoc")
PACKET_DIR = Path("reports/plantdoc_exact_duplicate_review")
GROUPS_CSV = PACKET_DIR / "plantdoc_exact_duplicate_groups.csv"
MEMBERS_CSV = PACKET_DIR / "plantdoc_exact_duplicate_members.csv"
RESOLUTION_CSV = Path("data/exclusions/plantdoc_internal_duplicate_resolution.csv")
EFFECTIVE_CSV = Path("data/manifests/plantdoc_effective_manifest.csv")
OUT = Path("reports/plantdoc_internal_duplicate_gate.json")
SOURCE_REVISION = "5467f6012d78d1c446145d5f582da6096f852ae8"


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plantdoc-internal-duplicate-gate")
    ap.add_argument("--check", action="store_true",
                    help="verify the persisted gate matches current inputs; write nothing")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    if not (REPO / MANIFEST).exists():
        print(f"[internal-dup-gate] manifest not found: {MANIFEST}")
        return 2

    original_of = {}
    if (REPO / COLLISION_MAP).exists():
        for r in read_csv(REPO / COLLISION_MAP):
            original_of[r["collision_safe_relative_path"]] = r["original_archive_path"]

    manifest_rows = read_csv(REPO / MANIFEST)
    groups = find_duplicate_groups(
        manifest_rows, dataset="PlantDoc",
        source_revision=SOURCE_REVISION, active_root=REPO / ACTIVE_ROOT,
        original_path_of=original_of)

    decisions = read_csv(REPO / GROUPS_CSV) if (REPO / GROUPS_CSV).exists() else []
    if not decisions:
        print(f"[internal-dup-gate] no review packet at {GROUPS_CSV}; every group is "
              "unresolved. Run scripts/build_plantdoc_duplicate_packet.py.")

    # The persisted effective dataset is compared against a fresh rebuild by
    # IDENTITY SET. A missing file is not "nothing to compare" -- it means the
    # decisions have not been applied, so the gate must not pass.
    persisted_effective = (read_csv(REPO / EFFECTIVE_CSV)
                           if (REPO / EFFECTIVE_CSV).exists() else None)
    if persisted_effective is None and decisions:
        print(f"[internal-dup-gate] no effective manifest at {EFFECTIVE_CSV}; run "
              "scripts/apply_plantdoc_duplicate_adjudication.py.")

    digests = {}
    for name, p in (("plantdoc_manifest", MANIFEST),
                    ("duplicate_groups", GROUPS_CSV),
                    ("duplicate_members", MEMBERS_CSV),
                    ("duplicate_resolution", RESOLUTION_CSV),
                    ("effective_manifest", EFFECTIVE_CSV)):
        digests[name] = sha256_of(REPO / p) if (REPO / p).exists() else "<absent>"
    digests["group_schema"] = hashlib.sha256(
        DUPLICATE_GROUP_SCHEMA.encode("utf-8")).hexdigest()

    gate = build_internal_duplicate_gate(
        groups, decisions, dataset="PlantDoc", input_digests=digests,
        manifest_rows=manifest_rows, persisted_effective=persisted_effective,
        provenance={"command": "build_plantdoc_internal_duplicate_gate.py",
                    "source_revision": SOURCE_REVISION,
                    "review_packet": str(PACKET_DIR),
                    "resolution_table": str(RESOLUTION_CSV),
                    "effective_manifest": str(EFFECTIVE_CSV)})

    agg = aggregate(groups)
    print(f"[internal-dup-gate] groups={gate.total_groups} records={gate.total_records} "
          f"cross_split={gate.cross_split_groups} cross_class={gate.cross_class_groups}")
    print(f"[internal-dup-gate] resolved={gate.resolved_groups} "
          f"unresolved={gate.unresolved_groups} violations={len(gate.violations)} "
          f"-> status={gate.status}")
    rem = gate.remediation or {}
    if rem.get("evaluated"):
        print(f"[internal-dup-gate] remediation: retained={rem.get('retained_records')} "
              f"excluded={rem.get('excluded_records')} "
              f"effective={rem.get('effective_records')}/{rem.get('source_records')} "
              f"surviving_exact_duplicate_groups={rem.get('surviving_exact_duplicate_groups')} "
              f"ok={rem.get('ok')}")
        rec = gate.identity_reconciliation or {}
        print(f"[internal-dup-gate] fresh-vs-persisted: fresh={rec.get('fresh_count')} "
              f"persisted={rec.get('persisted_count')} equal={rec.get('equal')}")
    for v in gate.violations[:10]:
        print(f"  VIOLATION {v}")

    text = json.dumps(gate.to_dict(), indent=2, sort_keys=True) + "\n"
    target = REPO / args.out
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            print(f"[internal-dup-gate] CHECK FAILED — {args.out} is stale")
            return 3
        print("[internal-dup-gate] check OK — persisted gate matches current inputs")
        return 0 if gate.status == "pass" else 1

    gate.write(target)
    print(f"[internal-dup-gate] wrote {args.out}")
    if gate.status != "pass":
        print(f"[internal-dup-gate] Phase-1 scientific status is BLOCKED by "
              f"{gate.unresolved_groups} unresolved duplicate group(s); "
              f"aggregate={agg}")
    return 0 if gate.status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
