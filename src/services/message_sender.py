#!/usr/bin/env python3
"""TCP message sender used by the live Mininet UI."""

from __future__ import annotations

import argparse
import base64
import json
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--sender", required=True)
    parser.add_argument("--receiver", required=True)
    parser.add_argument("--message-b64", required=True)
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()

    message = base64.b64decode(args.message_b64.encode("ascii")).decode("utf-8")
    payload = {
        "sender": args.sender,
        "receiver": args.receiver,
        "message": message,
        "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
            sock.settimeout(args.timeout)
            sock.sendall(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            ack = sock.recv(8192).decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"send failed: {exc}")
        return 1

    print(json.dumps({"ok": True, "target": f"{args.host}:{args.port}", "ack": ack}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

