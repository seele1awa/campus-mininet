#!/usr/bin/env python3
"""One-shot TCP message receiver used by the live Mininet UI."""

from __future__ import annotations

import argparse
import json
import socket
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=6.0)
    args = parser.parse_args()

    result = {
        "ok": False,
        "port": args.port,
        "received_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "peer": None,
        "payload": None,
        "error": None,
    }

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("0.0.0.0", args.port))
            server.listen(1)
            server.settimeout(args.timeout)

            conn, addr = server.accept()
            with conn:
                conn.settimeout(args.timeout)
                chunks = []
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if sum(len(item) for item in chunks) > 65536:
                        break
                raw = b"".join(chunks).decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"raw": raw}
                result.update({"ok": True, "peer": f"{addr[0]}:{addr[1]}", "payload": payload})
                conn.sendall(("ACK " + json.dumps(payload, ensure_ascii=False)).encode("utf-8"))
    except Exception as exc:
        result["error"] = str(exc)

    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

