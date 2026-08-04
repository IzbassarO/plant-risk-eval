#!/usr/bin/env bash
# Run the six ICA 2026 experiments sequentially.
#
# Sequential by design: this machine has 16 GB of unified memory shared between
# CPU and GPU, so two ResNet-50 trainings at once risk an out-of-memory kill
# mid-run. `caffeinate` keeps macOS awake for the duration; without it the run
# stalls when the display sleeps.
#
#   bash scripts/ica26_run_all.sh
#
# Order puts the cheap MobileNet runs first so a complete one-model matrix
# (PlantVillage in-domain, PlantDoc in-domain, cross-domain) exists early, then
# escalates. If the session is cut short, what finished is still coherent.

set -u
cd "$(dirname "$0")/.."
REPO="$(pwd)"
PY="${PY:-$REPO/.venv/bin/python}"
LOGDIR="$REPO/experiments/ica26/logs"
mkdir -p "$LOGDIR"

MASTER="$LOGDIR/run_all.log"
PIDFILE="$LOGDIR/run_all.pid"
echo $$ > "$PIDFILE"

RUNS=(
  pdc_mobilenet_v3_small_s42
  pv_mobilenet_v3_small_s42
  pdc_efficientnet_b0_s42
  pv_efficientnet_b0_s42
  pdc_resnet50_s42
  pv_resnet50_s42
)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$MASTER"; }

log "=== ICA 2026 full run matrix starting (pid $$) ==="
log "python: $PY"

log "validating the experiment dataset lock once before the matrix"
if ! "$PY" scripts/ica26_validate_experiment_lock.py >>"$MASTER" 2>&1; then
  log "ABORT: dataset lock did not validate"
  rm -f "$PIDFILE"
  exit 2
fi

FAILED=()
for eid in "${RUNS[@]}"; do
  LOG="$LOGDIR/${eid}.log"
  log "--- starting $eid  (log: $LOG) ---"
  START=$(date +%s)
  # Each run re-validates the lock itself, so a corpus change mid-matrix is
  # caught at the boundary rather than silently accepted.
  if "$PY" scripts/ica26_train.py \
        --config "experiments/ica26/configs/${eid}.yaml" > "$LOG" 2>&1; then
    log "--- finished $eid in $(( $(date +%s) - START ))s ---"
  else
    rc=$?
    log "--- FAILED $eid rc=$rc after $(( $(date +%s) - START ))s (see $LOG) ---"
    FAILED+=("$eid")
  fi
done

if [ ${#FAILED[@]} -eq 0 ]; then
  log "=== all ${#RUNS[@]} runs completed ==="
  log "building paper tables and figures"
  "$PY" scripts/ica26_build_tables.py >>"$MASTER" 2>&1 \
    && log "tables and figures written" \
    || log "WARNING: table/figure build failed; result JSON is still intact"
  rm -f "$PIDFILE"
  exit 0
fi

log "=== ${#FAILED[@]} run(s) FAILED: ${FAILED[*]} ==="
rm -f "$PIDFILE"
exit 1
