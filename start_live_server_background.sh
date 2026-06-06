#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8088}"
LOG_FILE="/tmp/campus_live_server.log"
PID_FILE="/tmp/campus_live_server.pid"

rm -f "$LOG_FILE" "$PID_FILE"
cd "$SCRIPT_DIR"
nohup ./run_live_server.sh "$PORT" > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
echo "pid=$(cat "$PID_FILE")"
echo "log=$LOG_FILE"
