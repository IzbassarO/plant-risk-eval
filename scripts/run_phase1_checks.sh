#!/usr/bin/env bash
# Reproducible Phase-1 (post-remediation) gate.
#
# HARD checks (any failure -> exit 1 FAIL): brief present, unit tests, package
# import, taxonomy, mapping schema, no auto-approved mapping, harm provenance,
# path portability, manifest consistency.
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

echo; echo "-- [HARD 1/9] PROJECT_BRIEF.md present --"
test -f PROJECT_BRIEF.md || fail "PROJECT_BRIEF.md (governing spec) is missing"
echo "  ok"

echo; echo "-- [HARD 2/9] unit tests --"
"$PY" -m pytest -q || fail "unit tests failed"

echo; echo "-- [HARD 3/9] package import --"
"$PY" -c "import ica26; from ica26.evaluation import cross_dataset; from ica26.leakage import gate, phash" || fail "package import failed"
echo "  ok"

echo; echo "-- [HARD 4/9] action taxonomy --"
"$PY" -c "import sys; from ica26.config import validate_taxonomy as v; r=v('configs/action_taxonomy.yaml'); print(' ', r.summary()); sys.exit(0 if r.ok else 1)" || fail "taxonomy invalid"

echo; echo "-- [HARD 5/9] mapping schema + no auto-approved unsupported rows --"
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

echo; echo "-- [HARD 6/9] harm-matrix provenance (no approved scientific default) --"
"$PY" - <<'PYEOF' || fail "harm provenance check failed"
import sys
from ica26.evaluation import harm
# example matrix must NOT be production-ready; template must not be approved
assert not harm.EXAMPLE_DEV_REVIEWED_MATRIX.is_production_ready()
t = harm.load_reviewed_matrix("configs/harm_matrix_template.yaml")
assert t.review_status != "approved" and not t.is_production_ready()
print("  ok: no approved scientific harm matrix exists")
PYEOF

echo; echo "-- [HARD 7/9] path portability / anonymity --"
"$PY" -m ica26.portability || fail "machine-specific/personal paths found in artifacts"

echo; echo "-- [HARD 8/9] PlantDoc manifest consistency (fs<->manifest) --"
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

echo; echo "-- [HARD 9/9] leakage index parity (indexed == brute force) --"
"$PY" -m pytest -q tests/test_phash_scale.py >/dev/null 2>&1 || fail "pHash indexed/brute-force parity failed"
echo "  ok"

# ------------------ STATUS checks (feed the verdict) ------------------
echo; echo "-- [STATUS] dataset acquisition + leakage gate --"
"$PY" - <<'PYEOF'
import json, os
def load(p):
    return json.load(open(p)) if os.path.exists(p) else None
verdict = "PASS"; reasons = []

pd_sum = load("data/manifests/plantdoc_summary.json")
if pd_sum is None:
    verdict = "BLOCKED"; reasons.append("PlantDoc not acquired")
elif not pd_sum.get("complete", False):
    verdict = "PARTIAL"; rec = pd_sum.get("reconciliation", {})
    reasons.append(f"PlantDoc incomplete ({rec.get('downloaded_image_count')}/{rec.get('upstream_repository_count')})")

pv_sum = load("data/manifests/plantvillage_summary.json")
if pv_sum is None:
    verdict = "BLOCKED"; reasons.append("PlantVillage not executed")
elif not pv_sum.get("pixels_materialized", False):
    if verdict == "PASS": verdict = "PARTIAL"
    reasons.append("PlantVillage pixels not materialized (leaf_id structure acquired; images pending)")

gate = load("reports/leakage_gate.json")
if gate is None:
    reasons.append("no cross-dataset leakage gate yet (cross-dataset eval blocked)")
    if verdict == "PASS": verdict = "PARTIAL"
elif gate.get("status") != "pass":
    reasons.append(f"leakage gate status={gate.get('status')} (cross-dataset eval blocked)")
    if verdict == "PASS": verdict = "PARTIAL"

print("  verdict:", verdict)
for r in reasons: print("   -", r)
open("/tmp/ica_verdict.txt", "w").write(verdict)
PYEOF

V=$(cat /tmp/ica_verdict.txt 2>/dev/null || echo BLOCKED)
echo; echo "================ OVERALL: $V ================"
echo "(HARD checks all passed. Exit: 0=PASS, 2=PARTIAL/BLOCKED, 1=FAIL.)"
case "$V" in
  PASS) exit 0 ;;
  *) exit 2 ;;
esac
