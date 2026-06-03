#!/usr/bin/env bash
set -euo pipefail

pkill -TERM -f "[c]ampus_live_server.py" 2>/dev/null || true
sleep 1
pkill -KILL -f "[c]ampus_live_server.py" 2>/dev/null || true
mn -c >/tmp/campus_mn_cleanup.log 2>&1 || true
rm -f /tmp/campus_live_server.pid
echo "live server stopped and Mininet cleanup completed"
