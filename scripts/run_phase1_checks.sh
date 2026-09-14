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
# Verdict: ACCEPTED (0) / scientifically BLOCKED (2) / status-control failure
# (3); an earlier HARD check exits 1. It will never report acceptance while a
# required scientific decision, technical record, or control is absent/stale.
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
import pandas as pd
from ica26.datasets import plantdoc
# The committed manifest is the reference side. Building it from the same tree
# it is then compared against made this check compare the filesystem to itself,
# so it passed vacuously -- including against an empty data/raw/plantdoc.
df = pd.read_csv("data/manifests/plantdoc_manifest.csv")
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

# The second-review packet is derived from the resolution table. If it has
# drifted, a reviewer would be looking at a decision that is no longer in force.
if [ -f reports/plantdoc_label_second_review/packet_manifest.json ]; then
  "$PY" scripts/build_plantdoc_second_review_packet.py --check \
    || fail "the relabel second-review packet does not match the current decisions"
fi

echo; echo "-- [HARD 11/11] preserved human-review evidence is unaltered --"
if [ -d human_review ]; then
  "$PY" scripts/build_human_review_evidence_manifest.py --check \
    || fail "preserved human-review evidence does not match its recorded digests"
else echo "  (no preserved evidence yet)"; fi

# ------------------ STATUS checks (feed the verdict) ------------------
# The strict readiness assessment is the ONLY authority for the technical
# control plane. Every displayed dimension and the final Phase-1 verdict below
# is derived from its fresh, validated condition set.
echo; echo "-- [STATUS] strict Dataset V1 freeze-readiness assessment --"
READINESS_CHECK_RC=0
"$PY" scripts/build_dataset_v1_freeze_readiness.py --check || READINESS_CHECK_RC=$?

echo; echo "-- [STATUS] validated Dataset V1 technical freeze record --"
FREEZE_CHECK_RC=0
"$PY" scripts/materialize_dataset_v1_freeze.py --check || FREEZE_CHECK_RC=$?

echo; echo "-- [STATUS] per-dimension Phase-1 status --"
READINESS_CHECK_RC="$READINESS_CHECK_RC" FREEZE_CHECK_RC="$FREEZE_CHECK_RC" "$PY" - <<'PYEOF'
import json, os

check_rc = int(os.environ.get("READINESS_CHECK_RC", "99"))
freeze_check_rc = int(os.environ.get("FREEZE_CHECK_RC", "99"))

def load(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

notes = []      # why a dimension is not settled
facts = []      # settled results worth stating; never a reason to block

# 5) Dataset V1 freeze readiness -------------------------------------------- #
# The readiness script checks freshness before we inspect this file.  A raw
# `dataset_v1_freeze.json` has no authority here: it can be created by anyone
# and is not an approval or a validated freeze decision.
ready = load("reports/dataset_v1_freeze_readiness.json")
if not isinstance(ready, dict):
    ready = None
conditions = {c.get("id"): c for c in (ready or {}).get("conditions", [])
              if isinstance(c, dict) and c.get("id")}
blockers = list((ready or {}).get("blockers") or [])
assessment_current = check_rc in (0, 1) and ready is not None
hard_status_failure = check_rc not in (0, 1) or freeze_check_rc not in (0, 1)
strict_ready = (
    check_rc == 0
    and assessment_current
    and ready.get("status") == "ready"
    and not blockers
    and bool(conditions)
    and all(c.get("status") == "satisfied" for c in conditions.values())
)

def readiness_group(ids, blocked):
    """Render a dimension from the fresh strict assessment, never raw counts."""
    if not assessment_current:
        return "UNVERIFIABLE"
    states = [conditions.get(cid, {}).get("status") for cid in ids]
    return "PASS" if states and all(state == "satisfied" for state in states) else blocked

# Derive every displayed dimension from the strict condition set rather than
# duplicating its predicates in this shell script.
data_status = readiness_group(("plantdoc_acquired", "plantvillage_materialized"), "PARTIAL")
cross_status = readiness_group(("cross_dataset_leakage_gate",), "FAIL")
dup_status = readiness_group(("internal_duplicate_gate",), "INCOMPLETE")
map_status = readiness_group(
    ("disease_action_mapping_reviewed", "plantvillage_action_mapping_coverage",
     "harm_matrix_approved", "relabel_second_scientific_review"),
    "INCOMPLETE")

technical_freeze_valid = strict_ready and freeze_check_rc == 0
if technical_freeze_valid:
    v1_status = "FROZEN"
elif freeze_check_rc not in (0, 1):
    v1_status = "UNVERIFIABLE"
elif strict_ready:
    v1_status = "READY_FOR_FREEZE"
elif assessment_current:
    v1_status = "BLOCKED"
else:
    v1_status = "UNVERIFIABLE"

if ready is None:
    notes.append("no readable freeze-readiness assessment")
elif check_rc == 3:
    notes.append("persisted freeze-readiness assessment is stale")
elif check_rc == 2:
    notes.append("freeze-readiness assessment is missing required input(s)")
elif check_rc not in (0, 1):
    notes.append(f"freeze-readiness checker returned unexpected exit {check_rc}")
elif not strict_ready:
    notes.append("current strict freeze-readiness assessment is not_ready")
elif freeze_check_rc == 1:
    notes.append("no current validated technical freeze record; readiness alone does not freeze Dataset V1")
elif freeze_check_rc != 0:
    notes.append(f"technical freeze validator returned hard-failure exit {freeze_check_rc}")

if ready is not None:
    facts.append(f"freeze readiness: {ready.get('satisfied', 0)} of "
                 f"{ready.get('satisfied', 0) + ready.get('blocked', 0)} "
                 f"precondition(s) satisfied -> {ready.get('status', 'unknown')}")
    for cid in blockers:
        c = conditions.get(cid, {})
        notes.append(f"freeze blocker [{c.get('kind', 'unknown')}] {cid}: "
                     f"{c.get('detail', 'no detail recorded')}")

# One source of truth: a renamed mapping status, a blank PlantVillage row, a
# hand-created freeze JSON, or even a ready pre-decision report cannot turn this
# into ACCEPTED.  The deterministic technical record must validate too.
scientific = "ACCEPTED" if technical_freeze_valid else "BLOCKED"

print(f"  MECHANICAL / DATA CHECKS ....... {data_status}")
print(f"  CROSS-DATASET GATE ............. {cross_status}")
print(f"  INTERNAL DUPLICATE REVIEW ...... {dup_status}")
print(f"  SCIENTIFIC REVIEW .............. {map_status}")
print(f"  DATASET V1 FREEZE READINESS .... {v1_status}")
print(f"  SCIENTIFIC PHASE-1 STATUS ...... {scientific}")
if facts:
    print("  applied:")
    for f in facts:
        print("   -", f)
if notes:
    print("  reasons:")
    for n in notes:
        print("   -", n)
raise SystemExit(0 if scientific == "ACCEPTED" else (3 if hard_status_failure else 2))
PYEOF

STATUS_RC=$?
if [ "$STATUS_RC" -eq 0 ]; then
  V=ACCEPTED
elif [ "$STATUS_RC" -eq 2 ]; then
  V=BLOCKED
else
  V=HARD_FAILURE
fi
echo
echo "================ SCIENTIFIC PHASE-1 STATUS: $V ================"
echo "(The HARD checks above are mechanical only. They do NOT constitute"
echo " scientific acceptance; see the per-dimension status. Exit: 0=ACCEPTED,"
echo " 2=BLOCKED, 1=a mechanical hard check failed, 3=status control failure.)"
case "$V" in
  ACCEPTED) exit 0 ;;
  BLOCKED) exit 2 ;;
  *) exit 3 ;;
esac
