#!/usr/bin/env python3
"""Small anonymous FTP server for Mininet demos.

The implementation intentionally uses only Python's standard library so the
campus topology can provide an FTP service without installing pyftpdlib.
It supports the command subset needed by curl, wget and common FTP clients:
USER, PASS, SYST, FEAT, PWD, TYPE, PASV, LIST, RETR, CWD, QUIT and NOOP.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import socket
import socketserver
import threading
from pathlib import Path


class FTPState:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.cwd = "/"
        self.data_socket: socket.socket | None = None

    def resolve(self, raw_path: str | None) -> Path:
        if not raw_path:
            raw_path = self.cwd
        if raw_path.startswith("/"):
            virtual = posixpath.normpath(raw_path)
        else:
            virtual = posixpath.normpath(posixpath.join(self.cwd, raw_path))
        if not virtual.startswith("/"):
            virtual = "/" + virtual
        candidate = (self.root / virtual.lstrip("/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("path escapes root")
        return candidate


class FTPHandler(socketserver.StreamRequestHandler):
    timeout = 10

    def setup(self) -> None:
        super().setup()
        self.state = FTPState(self.server.root)  # type: ignore[attr-defined]

    def send_line(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode("utf-8"))
        self.wfile.flush()

    def handle(self) -> None:
        self.send_line("220 Campus Mininet FTP ready")
        while True:
            raw = self.rfile.readline(8192)
            if not raw:
                break
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            command, _, argument = line.partition(" ")
            command = command.upper()
            argument = argument.strip()
            try:
                should_continue = self.dispatch(command, argument)
            except Exception as exc:  # Keep demo server resilient.
                self.send_line(f"550 {exc}")
                should_continue = True
            if not should_continue:
                break

    def dispatch(self, command: str, argument: str) -> bool:
        handlers = {
            "USER": self.cmd_user,
            "PASS": self.cmd_pass,
            "SYST": self.cmd_syst,
            "FEAT": self.cmd_feat,
            "PWD": self.cmd_pwd,
            "TYPE": self.cmd_type,
            "PASV": self.cmd_pasv,
            "LIST": self.cmd_list,
            "NLST": self.cmd_list,
            "RETR": self.cmd_retr,
            "CWD": self.cmd_cwd,
            "QUIT": self.cmd_quit,
            "NOOP": self.cmd_noop,
        }
        handler = handlers.get(command)
        if handler is None:
            self.send_line("502 Command not implemented")
            return True
        return handler(argument)

    def cmd_user(self, _argument: str) -> bool:
        self.send_line("331 Anonymous login ok, send password")
        return True

    def cmd_pass(self, _argument: str) -> bool:
        self.send_line("230 Login successful")
        return True

    def cmd_syst(self, _argument: str) -> bool:
        self.send_line("215 UNIX Type: L8")
        return True

    def cmd_feat(self, _argument: str) -> bool:
        self.send_line("211-Features")
        self.send_line(" PASV")
        self.send_line(" UTF8")
        self.send_line("211 End")
        return True

    def cmd_pwd(self, _argument: str) -> bool:
        self.send_line(f'257 "{self.state.cwd}"')
        return True

    def cmd_type(self, _argument: str) -> bool:
        self.send_line("200 Type set")
        return True

    def cmd_pasv(self, _argument: str) -> bool:
        self.close_data_socket()
        data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        data_socket.bind(("0.0.0.0", 0))
        data_socket.listen(1)
        data_socket.settimeout(10)
        self.state.data_socket = data_socket
        host_ip = self.request.getsockname()[0]
        if host_ip == "0.0.0.0":
            host_ip = "127.0.0.1"
        port = data_socket.getsockname()[1]
        p1, p2 = divmod(port, 256)
        self.send_line(f"227 Entering Passive Mode ({host_ip.replace('.', ',')},{p1},{p2})")
        return True

    def accept_data(self) -> socket.socket:
        if self.state.data_socket is None:
            raise RuntimeError("Use PASV first")
        conn, _addr = self.state.data_socket.accept()
        self.close_data_socket()
        return conn

    def cmd_list(self, argument: str) -> bool:
        path = self.state.resolve(argument or self.state.cwd)
        if not path.exists():
            self.send_line("550 Path not found")
            return True
        self.send_line("150 Opening data connection")
        with self.accept_data() as conn:
            rows = []
            items = sorted(path.iterdir()) if path.is_dir() else [path]
            for item in items:
                size = item.stat().st_size
                prefix = "drwxr-xr-x" if item.is_dir() else "-rw-r--r--"
                rows.append(f"{prefix} 1 owner group {size:>8} Jan 01 00:00 {item.name}")
            conn.sendall(("\r\n".join(rows) + "\r\n").encode("utf-8"))
        self.send_line("226 Transfer complete")
        return True

    def cmd_retr(self, argument: str) -> bool:
        path = self.state.resolve(argument)
        if not path.is_file():
            self.send_line("550 File not found")
            return True
        self.send_line("150 Opening data connection")
        with self.accept_data() as conn, path.open("rb") as handle:
            while True:
                chunk = handle.read(64 * 1024)
                if not chunk:
                    break
                conn.sendall(chunk)
        self.send_line("226 Transfer complete")
        return True

    def cmd_cwd(self, argument: str) -> bool:
        path = self.state.resolve(argument)
        if not path.is_dir():
            self.send_line("550 Directory not found")
            return True
        relative = path.relative_to(self.state.root)
        self.state.cwd = "/" + relative.as_posix() if relative.as_posix() != "." else "/"
        self.send_line("250 Directory changed")
        return True

    def cmd_quit(self, _argument: str) -> bool:
        self.send_line("221 Goodbye")
        return False

    def cmd_noop(self, _argument: str) -> bool:
        self.send_line("200 NOOP ok")
        return True

    def close_data_socket(self) -> None:
        if self.state.data_socket is not None:
            try:
                self.state.data_socket.close()
            finally:
                self.state.data_socket = None


class ThreadedFTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler, root: Path) -> None:
        self.root = root
        super().__init__(server_address, handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=21)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    args.root.mkdir(parents=True, exist_ok=True)
    server = ThreadedFTPServer((args.host, args.port), FTPHandler, args.root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"FTP server listening on {args.host}:{args.port}, root={args.root}", flush=True)
    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

