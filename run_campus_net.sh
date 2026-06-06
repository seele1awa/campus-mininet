#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Mininet requires root. Run: sudo ./run_campus_net.sh"
  exit 1
fi

python3 "$SCRIPT_DIR/src/campus_net.py" "$@"
