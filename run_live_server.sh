#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8088}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "实时联动服务器需要 root 权限，请使用：sudo ./run_live_server.sh"
  exit 1
fi

python3 "$SCRIPT_DIR/src/campus_live_server.py" --host 0.0.0.0 --port "$PORT" --auto-start

