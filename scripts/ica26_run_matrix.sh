#!/usr/bin/env bash
# Run a named set of ICA 2026 experiments sequentially, retrying each once.
#
#   bash scripts/ica26_run_matrix.sh                      # all six
#   bash scripts/ica26_run_matrix.sh pv_resnet50_s42 ...  # a named subset
#
# Why the retry: Spotlight (`mds`, `mds_stores`, `spotlightknowledged`) indexing
# the dataset tree while six DataLoader workers read it can return a transient
# EACCES for a file that is present, owned by the user, and readable moments
# later. `ManifestImageDataset._read` absorbs that per-image, but a retry at the
# run level keeps a whole matrix from being lost to one unlucky epoch.
#
# The retry never masks a data problem: a genuinely missing, corrupt, or
# mismatched file fails identically on both attempts, and the dataset lock is
# revalidated at the start of every attempt.

set -u
cd "$(dirname "$0")/.."
REPO="$(pwd)"
PY="${PY:-$REPO/.venv/bin/python}"
LOGDIR="$REPO/experiments/ica26/logs"
mkdir -p "$LOGDIR"

MASTER="$LOGDIR/run_matrix.log"
PIDFILE="$LOGDIR/run_matrix.pid"
echo $$ > "$PIDFILE"

if [ "$#" -gt 0 ]; then
  RUNS=("$@")
else
  RUNS=(
    pdc_mobilenet_v3_small_s42
    pv_mobilenet_v3_small_s42
    pdc_efficientnet_b0_s42
    pv_efficientnet_b0_s42
    pdc_resnet50_s42
    pv_resnet50_s42
  )
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$MASTER"; }

log "=== ICA 2026 matrix starting (pid $$): ${RUNS[*]} ==="

if ! "$PY" scripts/ica26_validate_experiment_lock.py >>"$MASTER" 2>&1; then
  log "ABORT: dataset lock did not validate"
  rm -f "$PIDFILE"
  exit 2
fi

FAILED=()
for eid in "${RUNS[@]}"; do
  CFG="experiments/ica26/configs/${eid}.yaml"
  if [ ! -f "$CFG" ]; then
    log "SKIP $eid: no config at $CFG"
    FAILED+=("$eid")
    continue
  fi
  OK=0
  for attempt in 1 2; do
    LOG="$LOGDIR/${eid}.log"
    [ "$attempt" -gt 1 ] && LOG="$LOGDIR/${eid}.attempt${attempt}.log"
    log "--- starting $eid (attempt $attempt, log: $LOG) ---"
    START=$(date +%s)
    if "$PY" scripts/ica26_train.py --config "$CFG" > "$LOG" 2>&1; then
      log "--- finished $eid in $(( $(date +%s) - START ))s ---"
      OK=1
      break
    fi
    rc=$?
    log "--- attempt $attempt of $eid FAILED rc=$rc after $(( $(date +%s) - START ))s ---"
    [ "$attempt" -eq 1 ] && sleep 30
  done
  [ "$OK" -eq 1 ] || FAILED+=("$eid")
done

log "building paper tables and figures from whatever completed"
"$PY" scripts/ica26_build_tables.py >>"$MASTER" 2>&1 \
  && log "tables and figures written" \
  || log "WARNING: table/figure build failed; result JSON is still intact"

rm -f "$PIDFILE"
if [ ${#FAILED[@]} -eq 0 ]; then
  log "=== all ${#RUNS[@]} run(s) completed ==="
  exit 0
fi
log "=== ${#FAILED[@]} run(s) FAILED after retry: ${FAILED[*]} ==="
exit 1
