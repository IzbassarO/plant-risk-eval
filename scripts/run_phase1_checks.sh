#!/usr/bin/env bash
# Reproducible Phase-1 (post-remediation) gate.
#
# HARD checks (any failure -> exit 1 FAIL): brief present, unit tests, package
# import, taxonomy, mapping schema, no auto-approved mapping, harm provenance,
# path portability, manifest consistency, pHash parity, duplicate-remediation
# freshness, human-review evidence integrity.
# STATUS checks (feed the verdict, do NOT hard-fail): PlantDoc completeness,
# PlantVillage pixel materialization, leakage-gate state.
#
# Verdict: PASS (0) / PARTIAL|BLOCKED (2) / FAIL (1). It will NOT report PASS
# while datasets are incomplete or a required leakage gate is missing/stale.
#
# Usage:  PYTHON=python ./scripts/run_phase1_checks.sh
set -uo pipefail
PY="${PYTHON:-python}"
cd "$(dirname "$0")/.."

fail() { echo "FAIL: $*"; exit 1; }
echo "================ ica26 Phase-1 remediation gate ($PY) ================"

echo; echo "-- [HARD 1/11] PROJECT_BRIEF.md present --"
test -f PROJECT_BRIEF.md || fail "PROJECT_BRIEF.md (governing spec) is missing"
echo "  ok"

echo; echo "-- [HARD 2/11] unit tests --"
"$PY" -m pytest -q || fail "unit tests failed"

echo; echo "-- [HARD 3/11] package import --"
"$PY" -c "import ica26; from ica26.evaluation import cross_dataset; from ica26.leakage import gate, phash" || fail "package import failed"
echo "  ok"

echo; echo "-- [HARD 4/11] action taxonomy --"
"$PY" -c "import sys; from ica26.config import validate_taxonomy as v; r=v('configs/action_taxonomy.yaml'); print(' ', r.summary()); sys.exit(0 if r.ok else 1)" || fail "taxonomy invalid"

echo; echo "-- [HARD 5/11] mapping schema + no auto-approved unsupported rows --"
"$PY" -m ica26.mapping.validation data/mapping/action_mapping_template.csv || fail "mapping schema invalid"
"$PY" - <<'PYEOF' || fail "an approved mapping row lacks evidence (auto-approval leak)"
import sys
from ica26.mapping.schema import read_mapping
from ica26.mapping.validation import validate_mapping, status_counts
df = read_mapping("data/mapping/action_mapping_template.csv")
c = status_counts(df); print("  statuses:", c)
# every approved row (if any) must pass validation; none may be auto-approved without evidence
appr = df[df["review_status"].astype(str).str.strip() == "approved"]
sys.exit(0 if (validate_mapping(df).ok) else 1)
PYEOF

echo; echo "-- [HARD 6/11] harm-matrix provenance (no approved scientific default) --"
"$PY" - <<'PYEOF' || fail "harm provenance check failed"
import sys
from ica26.evaluation import harm
# example matrix must NOT be production-ready; template must not be approved
assert not harm.EXAMPLE_DEV_REVIEWED_MATRIX.is_production_ready()
t = harm.load_reviewed_matrix("configs/harm_matrix_template.yaml")
assert t.review_status != "approved" and not t.is_production_ready()
print("  ok: no approved scientific harm matrix exists")
PYEOF

echo; echo "-- [HARD 7/11] path portability / anonymity --"
"$PY" -m ica26.portability || fail "machine-specific/personal paths found in artifacts"

echo; echo "-- [HARD 8/11] PlantDoc manifest consistency (fs<->manifest) --"
if [ -f data/manifests/plantdoc_manifest.csv ]; then
  "$PY" - <<'PYEOF' || fail "PlantDoc filesystem/manifest mismatch"
import sys
from ica26.datasets import plantdoc
df = plantdoc.build_manifest("data/raw/plantdoc")
chk = plantdoc.verify_against_filesystem(df, "data/raw/plantdoc")
print("  rows_missing_files:", len(chk["manifest_rows_missing_files"]),
      "| files_missing_from_manifest:", len(chk["files_missing_from_manifest"]))
sys.exit(0 if not chk["manifest_rows_missing_files"] and not chk["files_missing_from_manifest"] else 1)
PYEOF
else echo "  (no PlantDoc manifest yet)"; fi

echo; echo "-- [HARD 9/11] leakage index parity (indexed == brute force) --"
"$PY" -m pytest -q tests/test_phash_scale.py >/dev/null 2>&1 || fail "pHash indexed/brute-force parity failed"
echo "  ok"

# R2B: the effective dataset is DERIVED from the recorded human decisions. If it
# has drifted from what a fresh rebuild produces, the decisions on file no longer
# describe the data in front of us -- which is exactly the state the duplicate
# gate exists to refuse.
echo; echo "-- [HARD 10/11] PlantDoc duplicate remediation is current --"
if [ -f data/manifests/plantdoc_effective_manifest.csv ]; then
  "$PY" scripts/apply_plantdoc_duplicate_adjudication.py --check \
    || fail "the effective PlantDoc dataset does not match a fresh rebuild from the recorded decisions"
else echo "  (no effective manifest yet)"; fi

echo; echo "-- [HARD 11/11] preserved human-review evidence is unaltered --"
if [ -d human_review ]; then
  "$PY" scripts/build_human_review_evidence_manifest.py --check \
    || fail "preserved human-review evidence does not match its recorded digests"
else echo "  (no preserved evidence yet)"; fi

# ------------------ STATUS checks (feed the verdict) ------------------
# R1-MED-001: a single OVERALL verdict conflated "the mechanics work" with
# "the science is accepted", and printed PASS while 12 duplicate groups and 17
# mappings were unreviewed. The status is now reported per dimension, and
# SCIENTIFIC PHASE-1 STATUS is BLOCKED unless every one of them is settled.
echo; echo "-- [STATUS] per-dimension Phase-1 status --"
"$PY" - <<'PYEOF'
import csv, json, os

def load(p):
    return json.load(open(p)) if os.path.exists(p) else None

def rows(p):
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

notes = []      # why a dimension is not settled
facts = []      # settled results worth stating; never a reason to block

# 1) mechanical/data acquisition ------------------------------------------- #
data_status, pd_sum = "PASS", load("data/manifests/plantdoc_summary.json")
pv_sum = load("data/manifests/plantvillage_summary.json")
if pd_sum is None:
    data_status = "BLOCKED"; notes.append("PlantDoc not acquired")
elif not pd_sum.get("complete", False):
    rec = pd_sum.get("reconciliation", {})
    data_status = "PARTIAL"
    notes.append(f"PlantDoc incomplete ({rec.get('manifest_count')}/"
                 f"{rec.get('upstream_repository_count')})")
if pv_sum is None:
    data_status = "BLOCKED"; notes.append("PlantVillage not executed")
elif not pv_sum.get("pixels_materialized", False):
    data_status = "PARTIAL" if data_status == "PASS" else data_status
    notes.append("PlantVillage pixels not materialized")

# 2) cross-dataset leakage gate -------------------------------------------- #
gate = load("reports/leakage_gate.json")
if gate is None:
    cross_status = "FAIL"; notes.append("no cross-dataset leakage gate")
else:
    cross_status = "PASS" if gate.get("status") == "pass" else "FAIL"
    if cross_status != "PASS":
        notes.append(f"cross-dataset gate status={gate.get('status')}")

# 3) internal PlantDoc duplicate review ------------------------------------ #
idg = load("reports/plantdoc_internal_duplicate_gate.json")
if idg is None:
    dup_status = "INCOMPLETE"
    notes.append("no internal duplicate gate; run "
                 "scripts/build_plantdoc_internal_duplicate_gate.py")
else:
    dup_status = {"pass": "PASS", "fail": "FAIL"}.get(idg.get("status"), "INCOMPLETE")
    if dup_status != "PASS":
        notes.append(f"{idg.get('unresolved_groups')} of {idg.get('total_groups')} "
                     f"PlantDoc exact-duplicate group(s) unresolved "
                     f"({idg.get('cross_split_groups')} cross train/test, "
                     f"{idg.get('cross_class_groups')} contradictory labels)")
    # R2B: `status == pass` on a schema-1.0 gate meant only that a human had
    # decided. Reading it alone would now credit a decision that was never
    # applied, so the remediation half is checked explicitly.
    rem = idg.get("remediation") or {}
    if idg.get("schema_version") != "2.0":
        dup_status = "INCOMPLETE"
        notes.append(f"internal duplicate gate is schema "
                     f"{idg.get('schema_version')}; it does not verify that the "
                     f"decisions were applied")
    elif not (rem.get("evaluated") and rem.get("ok")
              and (idg.get("identity_reconciliation") or {}).get("equal")):
        dup_status = "FAIL"
        notes.append("PlantDoc duplicate decisions are recorded but not verifiably "
                     "applied to the effective dataset")
    elif dup_status == "PASS":
        facts.append(f"PlantDoc effective dataset: {rem.get('effective_records')} "
                     f"record(s) from {rem.get('source_records')}; "
                     f"{rem.get('retained_records')} canonical retained, "
                     f"{rem.get('excluded_records')} removed by explicit decision")

# 4) disease->action mapping review ---------------------------------------- #
mapping = rows("data/mapping/action_mapping_review.csv")
pv_classes = {r["class_label"] for r in rows("data/manifests/plantvillage_manifest.csv")}
pv_mapped = {r["dataset_class"] for r in mapping if r.get("dataset") == "PlantVillage"}
needs = sum(1 for r in mapping if r.get("review_status") == "needs_review")
map_status = "PASS"
if needs:
    map_status = "INCOMPLETE"
    notes.append(f"{needs} PlantDoc disease mapping row(s) still needs_review")
if pv_classes and not pv_mapped:
    map_status = "INCOMPLETE"
    notes.append(f"PlantVillage action-mapping coverage 0/{len(pv_classes)}")

# 5) Dataset V1 freeze ------------------------------------------------------ #
# The freeze readiness assessment is the single reproducible answer to "may we
# freeze?". It decides nothing and freezes nothing; it enumerates every
# precondition and names the ones a human still has to settle.
v1_status = "PASS" if os.path.exists("data/manifests/dataset_v1_freeze.json") else "NOT STARTED"
if v1_status != "PASS":
    notes.append("Dataset V1 is not frozen")
ready = load("reports/dataset_v1_freeze_readiness.json")
if ready is None:
    notes.append("no freeze-readiness assessment; run "
                 "scripts/build_dataset_v1_freeze_readiness.py")
else:
    facts.append(f"freeze readiness: {ready['satisfied']} of "
                 f"{ready['satisfied'] + ready['blocked']} precondition(s) satisfied "
                 f"-> {ready['status']}")
    for cid in ready["blockers"]:
        c = next(x for x in ready["conditions"] if x["id"] == cid)
        notes.append(f"freeze blocker [{c['kind']}] {cid}: {c['detail']}")

scientific = "ACCEPTED" if (
    data_status == "PASS" and cross_status == "PASS" and dup_status == "PASS"
    and map_status == "PASS" and v1_status == "PASS") else "BLOCKED"

print(f"  MECHANICAL / DATA CHECKS ....... {data_status}")
print(f"  CROSS-DATASET GATE ............. {cross_status}")
print(f"  INTERNAL DUPLICATE REVIEW ...... {dup_status}")
print(f"  MAPPING REVIEW ................. {map_status}")
print(f"  DATASET V1 FREEZE .............. {v1_status}")
print(f"  SCIENTIFIC PHASE-1 STATUS ...... {scientific}")
if facts:
    print("  applied:")
    for f in facts:
        print("   -", f)
if notes:
    print("  reasons:")
    for n in notes:
        print("   -", n)
open("/tmp/ica_verdict.txt", "w").write(scientific)
PYEOF

V=$(cat /tmp/ica_verdict.txt 2>/dev/null || echo BLOCKED)
echo
echo "================ SCIENTIFIC PHASE-1 STATUS: $V ================"
echo "(The HARD checks above are mechanical only. They do NOT constitute"
echo " scientific acceptance; see the per-dimension status. Exit: 0=ACCEPTED,"
echo " 2=BLOCKED, 1=a hard check failed.)"
case "$V" in
  ACCEPTED) exit 0 ;;
  *) exit 2 ;;
esac
