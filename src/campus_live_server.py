#!/usr/bin/env python3
"""Live HTTP API and static UI server for the Mininet campus network."""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import shlex
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mininet.log import setLogLevel

from campus_net import AREAS, build_net, configure_security, start_services


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "visualization"
MESSAGE_RECEIVER = PROJECT_ROOT / "src" / "services" / "message_receiver.py"
MESSAGE_SENDER = PROJECT_ROOT / "src" / "services" / "message_sender.py"

POLICIES = [
    {
        "title": "普通区域隔离",
        "body": "学生宿舍、教学楼、图书馆访问人事处或财务处时，核心路由器拒绝转发。",
    },
    {
        "title": "办公业务放行",
        "body": "办公楼到人事处、财务处保持三层连通，满足行政办公访问需求。",
    },
    {
        "title": "服务区共享",
        "body": "校内 10.10.0.0/16 用户可以访问服务器区 Web 与 FTP 服务。",
    },
    {
        "title": "外部访问阻断",
        "body": "外部模拟区 203.0.113.0/24 不能进入校园内网 10.10.0.0/16。",
    },
]

MESSAGE_TEMPLATES = [
    {
        "id": "courseware",
        "label": "课件共享通知",
        "text": "教学楼发送课件共享通知：请同步今日计算机网络实验资料。",
    },
    {
        "id": "library",
        "label": "图书馆借阅提醒",
        "text": "图书馆发送借阅提醒：预约资料已到馆，请及时领取。",
    },
    {
        "id": "office",
        "label": "办公审批消息",
        "text": "办公楼发送行政审批消息：请确认本周会议室使用申请。",
    },
    {
        "id": "finance",
        "label": "财务预算请求",
        "text": "财务处预算请求：请提交本月设备采购费用明细。",
    },
    {
        "id": "hr",
        "label": "人事档案查询",
        "text": "人事处档案查询：请核对教职工基础信息变更记录。",
    },
    {
        "id": "custom",
        "label": "自定义消息",
        "text": "请输入自定义消息。",
    },
]


def host_catalog() -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for area_id, area in AREAS.items():
        for host, ip in area["hosts"]:
            catalog[host] = {
                "id": host,
                "ip": ip.split("/")[0],
                "areaId": area_id,
                "areaLabel": area["label"],
            }
    return catalog


HOSTS = host_catalog()


def topology_payload(running: bool) -> dict[str, Any]:
    areas = []
    for area_id, area in AREAS.items():
        areas.append(
            {
                "id": area_id,
                "label": area["label"],
                "switch": area["switch"],
                "subnet": area["subnet"],
                "gateway": area["gateway"].split("/")[0],
                "hosts": [
                    {
                        "id": host,
                        "label": host,
                        "ip": ip.split("/")[0],
                        "role": "server" if host in {"web", "ftp"} else "host",
                        "service": "HTTP:80" if host == "web" else "FTP:21" if host == "ftp" else "",
                    }
                    for host, ip in area["hosts"]
                ],
            }
        )
    return {
        "running": running,
        "areas": areas,
        "router": {"id": "r_core", "label": "核心路由", "ip": "多接口网关"},
        "policies": POLICIES,
        "messageTemplates": MESSAGE_TEMPLATES,
    }


class CampusLiveRuntime:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.net = None
        self.started_at: float | None = None
        self.events: list[dict[str, Any]] = []

    def log_event(self, kind: str, message: str, ok: bool = True) -> None:
        event = {
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "message": message,
            "ok": ok,
        }
        self.events.append(event)
        self.events = self.events[-80:]

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                **topology_payload(self.net is not None),
                "startedAt": self.started_at,
                "events": self.events[-12:],
            }

    def start(self) -> dict[str, Any]:
        with self.lock:
            if self.net is not None:
                return {"ok": True, "running": True, "message": "拓扑已经在运行。"}

            subprocess.run(["service", "openvswitch-switch", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            setLogLevel("info")
            net = build_net()
            net.start()
            configure_security(net.get("r_core"))
            start_services(net)
            self.net = net
            self.started_at = time.time()
            self.log_event("start", "真实 Mininet 校园网拓扑已启动。")
            return {"ok": True, "running": True, "message": "真实 Mininet 校园网拓扑已启动。"}

    def stop(self) -> dict[str, Any]:
        with self.lock:
            if self.net is None:
                return {"ok": True, "running": False, "message": "拓扑未运行。"}
            try:
                self.net.stop()
            finally:
                self.net = None
                self.started_at = None
                subprocess.run(["mn", "-c"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            self.log_event("stop", "Mininet 拓扑已停止。")
            return {"ok": True, "running": False, "message": "Mininet 拓扑已停止。"}

    def require_net(self):
        if self.net is None:
            raise RuntimeError("拓扑未启动，请先点击“启动拓扑”。")
        return self.net

    def host_ip(self, host_id: str) -> str:
        if host_id not in HOSTS:
            raise ValueError(f"未知主机：{host_id}")
        return HOSTS[host_id]["ip"]

    def host(self, host_id: str):
        net = self.require_net()
        if host_id not in HOSTS:
            raise ValueError(f"未知主机：{host_id}")
        return net.get(host_id)

    def run_host_command(self, host_id: str, command: str, timeout_hint: int = 4) -> dict[str, Any]:
        host = self.host(host_id)
        wrapped = f"timeout {timeout_hint} bash -lc {shlex.quote(command + '; rc=$?; printf \"\\n__RC__%s\\n\" \"$rc\"')}"
        output = host.cmd(wrapped)
        rc = 124
        cleaned = []
        for line in output.splitlines():
            if line.startswith("__RC__"):
                try:
                    rc = int(line.replace("__RC__", "").strip())
                except ValueError:
                    rc = 1
            else:
                cleaned.append(line)
        return {"ok": rc == 0, "rc": rc, "output": "\n".join(cleaned).strip(), "command": command}

    def ping(self, source: str, target: str) -> dict[str, Any]:
        target_ip = self.host_ip(target)
        result = self.run_host_command(source, f"ping -c 2 -W 1 {target_ip}", timeout_hint=5)
        self.log_event("ping", f"{source} ping {target} {'成功' if result['ok'] else '失败'}", result["ok"])
        return {"action": "ping", "source": source, "target": target, "targetIp": target_ip, **result}

    def web(self, source: str, target: str) -> dict[str, Any]:
        target_ip = self.host_ip(target)
        fetch_code = (
            "import base64, urllib.request; "
            f"data=urllib.request.urlopen('http://{target_ip}', timeout=4).read(); "
            "print(base64.b64encode(data).decode('ascii'))"
        )
        result = self.run_host_command(source, f"python3 -c {shlex.quote(fetch_code)}", timeout_hint=6)
        if result["ok"]:
            result["rawOutputBase64"] = result["output"]
            result["output"] = base64.b64decode(result["output"].encode("ascii")).decode("utf-8", errors="replace")
        self.log_event("web", f"{source} HTTP 访问 {target} {'成功' if result['ok'] else '失败'}", result["ok"])
        return {"action": "web", "source": source, "target": target, "targetIp": target_ip, **result}

    def ftp(self, source: str, target: str) -> dict[str, Any]:
        target_ip = self.host_ip(target)
        fetch_cmd = f"set -o pipefail; curl -fsS --max-time 5 ftp://{target_ip}/README.txt | base64 -w0"
        result = self.run_host_command(source, fetch_cmd, timeout_hint=7)
        if result["ok"]:
            result["rawOutputBase64"] = result["output"]
            result["output"] = base64.b64decode(result["output"].encode("ascii")).decode("utf-8", errors="replace")
        self.log_event("ftp", f"{source} FTP 访问 {target} {'成功' if result['ok'] else '失败'}", result["ok"])
        return {"action": "ftp", "source": source, "target": target, "targetIp": target_ip, **result}

    def send_message(self, source: str, target: str, message: str) -> dict[str, Any]:
        self.require_net()
        if not message.strip():
            raise ValueError("消息内容不能为空。")
        if source == target:
            raise ValueError("源主机和目标主机不能相同。")

        target_ip = self.host_ip(target)
        target_host = self.host(target)
        source_host = self.host(source)
        port = random.randint(12000, 18000)
        token = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        out_path = f"/tmp/campus_message_{token}.json"
        receiver_cmd = (
            f"rm -f {shlex.quote(out_path)}; "
            f"nohup python3 {shlex.quote(str(MESSAGE_RECEIVER))} "
            f"--port {port} --out {shlex.quote(out_path)} --timeout 7 "
            f"> /tmp/campus_message_{token}.log 2>&1 &"
        )
        target_host.cmd(receiver_cmd)
        time.sleep(0.25)

        encoded = base64.b64encode(message.encode("utf-8")).decode("ascii")
        send_cmd = (
            f"python3 {shlex.quote(str(MESSAGE_SENDER))} "
            f"--host {target_ip} --port {port} "
            f"--sender {shlex.quote(source)} --receiver {shlex.quote(target)} "
            f"--message-b64 {encoded} --timeout 4"
        )
        wrapped = f"timeout 6 bash -lc {shlex.quote(send_cmd + '; rc=$?; printf \"\\n__RC__%s\\n\" \"$rc\"')}"
        output = source_host.cmd(wrapped)
        rc = 124
        lines = []
        for line in output.splitlines():
            if line.startswith("__RC__"):
                try:
                    rc = int(line.replace("__RC__", "").strip())
                except ValueError:
                    rc = 1
            else:
                lines.append(line)

        time.sleep(0.2)
        received_raw = target_host.cmd(f"cat {shlex.quote(out_path)} 2>/dev/null || true")
        target_host.cmd(f"pkill -f 'message_receiver.py --port {port}' 2>/dev/null || true")
        target_host.cmd(f"rm -f {shlex.quote(out_path)} /tmp/campus_message_{token}.log 2>/dev/null || true")

        received = None
        if received_raw.strip():
            try:
                received = json.loads(received_raw)
            except json.JSONDecodeError:
                received = {"raw": received_raw}

        ok = rc == 0 and bool(received and received.get("ok"))
        self.log_event("message", f"{source} 向 {target} 发送消息 {'成功' if ok else '失败'}", ok)
        return {
            "ok": ok,
            "rc": rc,
            "action": "message",
            "source": source,
            "target": target,
            "targetIp": target_ip,
            "port": port,
            "message": message,
            "command": send_cmd,
            "output": "\n".join(lines).strip(),
            "received": received,
        }

    def run_action(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            action = body.get("action")
            source = str(body.get("source", ""))
            target = str(body.get("target", ""))
            if action == "ping":
                return self.ping(source, target)
            if action == "web":
                return self.web(source, target)
            if action == "ftp":
                return self.ftp(source, target)
            if action == "message":
                return self.send_message(source, target, str(body.get("message", "")))
            raise ValueError(f"未知操作：{action}")

    def run_tests(self) -> dict[str, Any]:
        with self.lock:
            cases = [
                ("宿舍区内部二层互通", "ping", "stu1", "stu2", True),
                ("宿舍区到教学楼三层互通", "ping", "stu1", "teach1", True),
                ("宿舍区访问 Web 服务", "web", "stu1", "web", True),
                ("宿舍区访问 FTP 服务", "ftp", "stu1", "ftp", True),
                ("宿舍区访问人事处被限制", "ping", "stu1", "hr1", False),
                ("教学楼访问财务处被限制", "ping", "teach1", "fin1", False),
                ("办公楼访问人事处允许", "ping", "office1", "hr1", True),
                ("办公楼访问财务处允许", "ping", "office1", "fin1", True),
                ("外部主机访问 Web 被阻断", "ping", "attacker1", "web", False),
                ("办公楼向财务处发送业务消息", "message", "office1", "fin1", True),
                ("学生向人事处发送消息被拦截", "message", "stu1", "hr1", False),
            ]
            results = []
            for title, action, source, target, expect_ok in cases:
                if action == "message":
                    result = self.send_message(source, target, f"自动测试消息：{title}")
                elif action == "ping":
                    result = self.ping(source, target)
                elif action == "web":
                    result = self.web(source, target)
                elif action == "ftp":
                    result = self.ftp(source, target)
                else:
                    raise ValueError(f"未知测试操作：{action}")
                passed = bool(result["ok"]) == expect_ok
                results.append({"title": title, "expectOk": expect_ok, "passed": passed, **result})
            ok = all(item["passed"] for item in results)
            self.log_event("test", f"自动测试完成：{sum(1 for item in results if item['passed'])}/{len(results)} 通过", ok)
            return {"ok": ok, "results": results}


RUNTIME = CampusLiveRuntime()


class LiveRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[live-ui] " + fmt % args + "\n")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/api/status":
            self.write_json(HTTPStatus.OK, RUNTIME.status())
            return
        if self.path == "/api/topology":
            self.write_json(HTTPStatus.OK, topology_payload(RUNTIME.net is not None))
            return
        super().do_GET()

    def do_POST(self) -> None:
        try:
            if self.path == "/api/start":
                self.write_json(HTTPStatus.OK, RUNTIME.start())
                return
            if self.path == "/api/stop":
                self.write_json(HTTPStatus.OK, RUNTIME.stop())
                return
            if self.path == "/api/run":
                self.write_json(HTTPStatus.OK, RUNTIME.run_action(self.read_json()))
                return
            if self.path == "/api/tests":
                self.write_json(HTTPStatus.OK, RUNTIME.run_tests())
                return
            self.write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "API 不存在。"})
        except Exception as exc:
            self.write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live campus Mininet UI server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--auto-start", action="store_true")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("实时联动服务器需要 root 权限，请使用 sudo 运行。", file=sys.stderr)
        return 1

    if args.auto_start:
        RUNTIME.start()

    server = ThreadingHTTPServer((args.host, args.port), LiveRequestHandler)

    def shutdown(_signum, _frame) -> None:
        threading.Thread(target=lambda: (RUNTIME.stop(), server.shutdown()), daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"Live campus UI: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        RUNTIME.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
