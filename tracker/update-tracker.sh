#!/usr/bin/env bash
# update-tracker.sh — wrapper around build_tracker.py for cron/systemd use.
#
# Idempotent and safe to run repeatedly: build_tracker.py always reads the
# existing outreach-tracker.xlsx (if any) and preserves every hand-maintained
# column before overwriting it, so re-running this on a schedule never loses
# manual edits. It only ever touches tracker/outreach-tracker.xlsx.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG="$HERE/update.log"
PYTHON="python3"

{
    echo "===== $(date -Iseconds) ====="
    if "$PYTHON" "$HERE/build_tracker.py"; then
        echo "update-tracker: OK"
    else
        rc=$?
        echo "update-tracker: FAILED (exit $rc)"
        exit "$rc"
    fi
} >>"$LOG" 2>&1
