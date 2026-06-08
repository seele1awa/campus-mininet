#!/usr/bin/env python3
"""Live HTTP API and static UI server for the Mininet campus network."""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
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

from campus_net import (
    AREAS,
    DNS_RECORDS,
    access_trunk_port_name,
    build_net,
    configure_dynamic_hosts,
    configure_security,
    configure_vlans,
    dhcp_pool,
    host_display_ip,
    is_dhcp_host,
    start_ftp_service,
    start_dns_dhcp_services,
    start_services,
    start_web_service,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = PROJECT_ROOT / "visualization"
MESSAGE_RECEIVER = PROJECT_ROOT / "src" / "services" / "message_receiver.py"
MESSAGE_SENDER = PROJECT_ROOT / "src" / "services" / "message_sender.py"
AUDIT_LOG = Path("/tmp/campus_audit.log")
DNS_TARGET_HOSTS = {
    "web.campus.local": "web",
    "ftp.campus.local": "ftp",
    "hr.campus.local": "hr1",
    "finance.campus.local": "fin1",
}

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
    {
        "title": "VLAN 分区",
        "body": "各区域使用 access VLAN 接入，接入交换机、核心交换机和路由器之间通过 trunk 承载多 VLAN。",
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
                "ip": host_display_ip(ip),
                "areaId": area_id,
                "areaLabel": area["label"],
                "vlan": str(area["vlan"]),
                "dhcp": is_dhcp_host(ip),
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
                "vlan": area["vlan"],
                "uplink": "trunk",
                "dhcp": bool(area.get("dhcp")),
                "hosts": [
                    {
                        "id": host,
                        "label": host,
                        "ip": host_display_ip(ip),
                        "role": "server" if host in {"web", "ftp"} else "host",
                        "service": "HTTP:80" if host == "web" else "FTP:21" if host == "ftp" else "",
                        "vlan": area["vlan"],
                        "portMode": "access",
                        "dhcp": is_dhcp_host(ip),
                    }
                    for host, ip in area["hosts"]
                ],
            }
        )
    return {
        "running": running,
        "areas": areas,
        "router": {"id": "r_core", "label": "核心路由", "ip": "多接口网关"},
        "coreSwitch": {"id": "s_core", "label": "核心交换", "mode": "trunk"},
        "policies": POLICIES,
        "messageTemplates": MESSAGE_TEMPLATES,
        "dnsRecords": DNS_RECORDS,
    }


class CampusLiveRuntime:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.net = None
        self.started_at: float | None = None
        self.events: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.faults: dict[str, dict[str, Any]] = {}

    def log_event(self, kind: str, message: str, ok: bool = True) -> None:
        event = {
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "message": message,
            "ok": ok,
        }
        self.events.append(event)
        self.events = self.events[-80:]

    def audit_summary(self) -> dict[str, int]:
        recent = self.audit[-80:]
        return {
            "total": len(recent),
            "high": sum(1 for item in recent if item["level"] == "high"),
            "blocked": sum(1 for item in recent if not item["ok"]),
            "normal": sum(1 for item in recent if item["level"] == "normal"),
        }

    def dhcp_summary(self) -> list[dict[str, str]]:
        summary = []
        for area_id, area in AREAS.items():
            if not area.get("dhcp"):
                continue
            start_ip, end_ip, netmask = dhcp_pool(area)
            summary.append(
                {
                    "areaId": area_id,
                    "areaLabel": area["label"],
                    "vlan": str(area["vlan"]),
                    "range": f"{start_ip}-{end_ip}",
                    "netmask": netmask,
                    "gateway": area["gateway"].split("/")[0],
                    "dns": area["gateway"].split("/")[0],
                }
            )
        return summary

    def classify_audit(self, source: str, target: str, action: str, ok: bool) -> tuple[str, str]:
        target = DNS_TARGET_HOSTS.get(target, target)
        source_area = HOSTS.get(source, {}).get("areaId", "")
        target_area = HOSTS.get(target, {}).get("areaId", "")
        sensitive_areas = {"hr", "finance"}
        normal_user_areas = {"student", "teaching", "library"}

        if source_area == "external" and target_area != "external":
            return "high", "外部模拟区访问校园内网，命中边界防护审计规则。"
        if source_area == "guest" and target_area not in {"server", "guest"}:
            return "high", "访客网络访问校园内部区域，命中访客隔离审计规则。"
        if source_area in normal_user_areas and target_area in sensitive_areas:
            return "high", "普通区域访问人事处/财务处，命中敏感区域隔离规则。"
        if not ok and target_area in sensitive_areas:
            return "blocked", "访问敏感区域失败，记录为阻断事件。"
        if not ok:
            return "blocked", "访问失败或服务不可达，记录为异常事件。"
        if action == "perf":
            return "normal", "性能测试完成，记录吞吐量审计数据。"
        if action in {"dhcp", "dns", "fault_down", "fault_up"}:
            return "normal", "网络管理操作已记录到审计日志。"
        return "normal", "业务访问符合当前网络策略。"

    def log_audit(self, action: str, source: str, target: str, ok: bool, detail: str = "") -> dict[str, Any]:
        level, reason = self.classify_audit(source, target, action, ok)
        record = {
            "time": time.strftime("%H:%M:%S"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "source": source,
            "target": target,
            "sourceArea": HOSTS.get(source, {}).get("areaLabel", "-"),
            "targetArea": HOSTS.get(target, {}).get("areaLabel", "-"),
            "ok": ok,
            "level": level,
            "reason": reason,
            "detail": detail,
        }
        self.audit.append(record)
        self.audit = self.audit[-160:]
        try:
            AUDIT_LOG.write_text("", encoding="utf-8") if not AUDIT_LOG.exists() else None
            with AUDIT_LOG.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return record

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                **topology_payload(self.net is not None),
                "startedAt": self.started_at,
                "events": self.events[-12:],
                "audit": self.audit[-16:],
                "auditSummary": self.audit_summary(),
                "faults": list(self.faults.values()),
                "dhcpSummary": self.dhcp_summary(),
                "dnsRecords": DNS_RECORDS,
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
            configure_vlans(net)
            configure_dynamic_hosts(net)
            configure_security(net.get("r_core"))
            start_services(net)
            self.net = net
            self.started_at = time.time()
            self.faults.clear()
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
                self.faults.clear()
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

    def gateway_for_host(self, host_id: str) -> str:
        if host_id not in HOSTS:
            raise ValueError(f"未知主机：{host_id}")
        area_id = HOSTS[host_id]["areaId"]
        return AREAS[area_id]["gateway"].split("/")[0]

    def host(self, host_id: str):
        net = self.require_net()
        if host_id not in HOSTS:
            raise ValueError(f"未知主机：{host_id}")
        return net.get(host_id)

    def run_host_command(self, host_id: str, command: str, timeout_hint: int = 4) -> dict[str, Any]:
        host = self.host(host_id)
        shell_command = command + '; rc=$?; printf "\n__RC__%s\n" "$rc"'
        wrapped = f"timeout {timeout_hint} bash -lc {shlex.quote(shell_command)}"
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

    def ensure_dns_dhcp_service(self) -> None:
        """Restart dnsmasq on r_core if the DHCP/DNS service is not active."""

        net = self.require_net()
        router = net.get("r_core")
        running = router.cmd("test -s /tmp/campus_dnsmasq.pid && kill -0 $(cat /tmp/campus_dnsmasq.pid) 2>/dev/null; echo $?").strip().endswith("0")
        if not running:
            start_dns_dhcp_services(net)
            time.sleep(0.35)

    def resolve_domain(self, source: str, domain: str, audit: bool = True) -> dict[str, Any]:
        if domain not in DNS_RECORDS:
            raise ValueError(f"未知校园域名：{domain}")
        self.ensure_dns_dhcp_service()
        gateway = self.gateway_for_host(source)
        command = f"dig +short @{gateway} {shlex.quote(domain)} A | tail -n 1"
        result = self.run_host_command(source, command, timeout_hint=5)
        resolved_ip = ""
        if result["output"]:
            match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", result["output"])
            if match:
                resolved_ip = match.group(0)
        ok = result["ok"] and resolved_ip == DNS_RECORDS[domain]
        self.log_event("dns", f"{source} 解析 {domain} {'成功' if ok else '失败'}", ok)
        audit_record = self.log_audit("dns", source, domain, ok, resolved_ip or result["output"][:160]) if audit else None
        return {
            "action": "dns",
            "source": source,
            "target": domain,
            "targetIp": DNS_RECORDS[domain],
            "resolvedIp": resolved_ip,
            "dnsServer": gateway,
            "ok": ok,
            "rc": result["rc"],
            "command": command,
            "output": result["output"],
            "auditLevel": audit_record["level"] if audit_record else None,
            "auditReason": audit_record["reason"] if audit_record else None,
        }

    def service_target_ip(self, source: str, target: str) -> tuple[str, dict[str, Any] | None]:
        if target in DNS_RECORDS:
            resolution = self.resolve_domain(source, target, audit=False)
            return resolution["resolvedIp"] or DNS_RECORDS[target], resolution
        return self.host_ip(target), None

    def ensure_application_service(self, target: str) -> None:
        """Restart Web/FTP service when it is unexpectedly down, unless a fault is active."""

        target = DNS_TARGET_HOSTS.get(target, target)
        if target in self.faults:
            return
        if target == "web":
            host = self.host("web")
            listening = host.cmd("ss -ltn | grep -q ':80 ' ; echo $?").strip().endswith("0")
            if not listening:
                start_web_service(host)
                time.sleep(0.25)
        elif target == "ftp":
            host = self.host("ftp")
            listening = host.cmd("ss -ltn | grep -q ':21 ' ; echo $?").strip().endswith("0")
            if not listening:
                start_ftp_service(host)
                time.sleep(0.25)

    def dhcp(self, source: str) -> dict[str, Any]:
        host_info = HOSTS.get(source)
        if not host_info:
            raise ValueError(f"未知主机：{source}")
        if not host_info.get("dhcp"):
            raise ValueError(f"{source} 不是 DHCP 演示主机")

        self.ensure_dns_dhcp_service()
        host = self.host(source)
        intf = host.defaultIntf().name
        lease_file = f"/tmp/campus_dhclient_{source}.leases"
        pid_file = f"/tmp/campus_dhclient_{source}.pid"
        command = (
            f"if [ -s {shlex.quote(pid_file)} ]; then kill $(cat {shlex.quote(pid_file)}) 2>/dev/null || true; fi; "
            f"rm -f {shlex.quote(lease_file)} {shlex.quote(pid_file)}; "
            f"ip addr flush dev {shlex.quote(intf)}; "
            f"ip link set {shlex.quote(intf)} up; "
            f"timeout 12 dhclient -4 -v -1 -pf {shlex.quote(pid_file)} -lf {shlex.quote(lease_file)} {shlex.quote(intf)} 2>&1 || true; "
            f"ip -4 -o addr show dev {shlex.quote(intf)}; "
            "ip route show default"
        )
        result = self.run_host_command(source, command, timeout_hint=18)
        ip_match = re.search(r"inet\s+((?:\d{1,3}\.){3}\d{1,3})/", result["output"])
        route_match = re.search(r"default via ((?:\d{1,3}\.){3}\d{1,3})", result["output"])
        assigned_ip = ip_match.group(1) if ip_match else ""
        gateway = route_match.group(1) if route_match else self.gateway_for_host(source)
        ok = result["ok"] and bool(assigned_ip)
        router = self.require_net().get("r_core")
        dnsmasq_status = router.cmd("test -s /tmp/campus_dnsmasq.pid && kill -0 $(cat /tmp/campus_dnsmasq.pid) 2>/dev/null; echo $?").strip()
        dnsmasq_log = router.cmd("tail -n 20 /tmp/campus_dnsmasq.log 2>/dev/null || true").strip()
        output = result["output"]
        if not ok:
            output = "\n".join(
                item
                for item in [
                    result["output"],
                    f"dnsmasq_status={dnsmasq_status}",
                    "dnsmasq_log:",
                    dnsmasq_log or "(empty)",
                ]
                if item
            )
        self.log_event("dhcp", f"{source} DHCP {'获得 ' + assigned_ip if ok else '失败'}", ok)
        audit = self.log_audit("dhcp", source, source, ok, assigned_ip or output[:160])
        return {
            "action": "dhcp",
            "source": source,
            "target": source,
            "targetIp": assigned_ip,
            "assignedIp": assigned_ip,
            "gateway": gateway,
            "dns": gateway,
            "ok": ok,
            "rc": result["rc"],
            "command": command,
            "output": output,
            "dnsmasqStatus": dnsmasq_status,
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
        }

    def set_fault(self, action: str, target: str) -> dict[str, Any]:
        self.require_net()
        make_down = action == "fault_down"
        if target in {area["switch"] for area in AREAS.values()}:
            node = self.net.get(target)
            port = access_trunk_port_name(target)
            node.cmd(f"ip link set {port} {'down' if make_down else 'up'}")
            fault_type = "link"
            detail = f"{target} uplink {port}"
        elif target in {"web", "ftp"}:
            host = self.net.get(target)
            if target == "web":
                if make_down:
                    host.cmd("if [ -s /tmp/campus_web.pid ]; then kill $(cat /tmp/campus_web.pid) 2>/dev/null || true; fi; rm -f /tmp/campus_web.pid")
                else:
                    start_web_service(host)
            else:
                if make_down:
                    host.cmd("if [ -s /tmp/campus_ftp.pid ]; then kill $(cat /tmp/campus_ftp.pid) 2>/dev/null || true; fi; rm -f /tmp/campus_ftp.pid")
                else:
                    start_ftp_service(host)
            fault_type = "service"
            detail = f"{target} service"
        else:
            raise ValueError(f"不支持的故障目标：{target}")

        if make_down:
            self.faults[target] = {
                "target": target,
                "type": fault_type,
                "detail": detail,
                "state": "down",
                "time": time.strftime("%H:%M:%S"),
            }
        else:
            self.faults.pop(target, None)

        ok = True
        self.log_event("fault", f"{'制造' if make_down else '恢复'}故障：{detail}", ok)
        audit = self.log_audit(action, "operator", target, ok, detail)
        return {
            "action": action,
            "source": "operator",
            "target": target,
            "targetIp": "",
            "ok": ok,
            "rc": 0,
            "command": f"{'down' if make_down else 'up'} {detail}",
            "output": f"{'已制造' if make_down else '已恢复'}故障：{detail}",
            "faults": list(self.faults.values()),
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
        }

    def ping(self, source: str, target: str) -> dict[str, Any]:
        target_ip = self.host_ip(target)
        result = self.run_host_command(source, f"ping -c 2 -W 1 {target_ip}", timeout_hint=5)
        self.log_event("ping", f"{source} ping {target} {'成功' if result['ok'] else '失败'}", result["ok"])
        audit = self.log_audit("ping", source, target, result["ok"], result["output"][:160])
        return {"action": "ping", "source": source, "target": target, "targetIp": target_ip, "auditLevel": audit["level"], "auditReason": audit["reason"], **result}

    def web(self, source: str, target: str) -> dict[str, Any]:
        target_ip, resolution = self.service_target_ip(source, target)
        self.ensure_application_service(target)
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
        audit = self.log_audit("web", source, target, result["ok"], result["output"][:160])
        return {
            "action": "web",
            "source": source,
            "target": target,
            "targetIp": target_ip,
            "resolvedIp": resolution["resolvedIp"] if resolution else None,
            "dnsServer": resolution["dnsServer"] if resolution else None,
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
            **result,
        }

    def ftp(self, source: str, target: str) -> dict[str, Any]:
        target_ip, resolution = self.service_target_ip(source, target)
        self.ensure_application_service(target)
        fetch_cmd = f"set -o pipefail; curl -fsS --max-time 5 ftp://{target_ip}/README.txt | base64 -w0"
        result = self.run_host_command(source, fetch_cmd, timeout_hint=7)
        if result["ok"]:
            result["rawOutputBase64"] = result["output"]
            result["output"] = base64.b64decode(result["output"].encode("ascii")).decode("utf-8", errors="replace")
        self.log_event("ftp", f"{source} FTP 访问 {target} {'成功' if result['ok'] else '失败'}", result["ok"])
        audit = self.log_audit("ftp", source, target, result["ok"], result["output"][:160])
        return {
            "action": "ftp",
            "source": source,
            "target": target,
            "targetIp": target_ip,
            "resolvedIp": resolution["resolvedIp"] if resolution else None,
            "dnsServer": resolution["dnsServer"] if resolution else None,
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
            **result,
        }

    def performance(self, source: str, target: str) -> dict[str, Any]:
        target_ip = self.host_ip(target)
        target_host = self.host(target)
        port = random.randint(19000, 22000)
        token = f"{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        iperf_pid = f"/tmp/campus_iperf_{token}.pid"
        target_host.cmd(f"nohup iperf3 -s -1 -p {port} > /tmp/campus_iperf_{token}.log 2>&1 & echo $! > {shlex.quote(iperf_pid)}")
        time.sleep(0.35)

        command = f"iperf3 -c {target_ip} -p {port} -t 4 -J"
        result = self.run_host_command(source, command, timeout_hint=9)
        target_host.cmd(f"if [ -s {shlex.quote(iperf_pid)} ]; then kill $(cat {shlex.quote(iperf_pid)}) 2>/dev/null || true; fi; rm -f {shlex.quote(iperf_pid)} /tmp/campus_iperf_{token}.log 2>/dev/null || true")

        mbps = None
        raw_output = result["output"]
        if result["ok"] and result["output"]:
            try:
                json_start = result["output"].find("{")
                json_end = result["output"].rfind("}")
                json_text = result["output"][json_start : json_end + 1] if json_start >= 0 and json_end >= json_start else result["output"]
                parsed = json.loads(json_text)
                bits = (
                    parsed.get("end", {}).get("sum_received", {}).get("bits_per_second")
                    or parsed.get("end", {}).get("sum_sent", {}).get("bits_per_second")
                )
                if bits:
                    mbps = round(float(bits) / 1_000_000, 2)
            except (TypeError, ValueError, json.JSONDecodeError):
                mbps = None

        source_area = HOSTS.get(source, {}).get("areaId")
        target_area = HOSTS.get(target, {}).get("areaId")
        if source_area == "server" and target_area == "server":
            expected_profile = "服务器区内部高速链路，目标约 1000 Mbps。"
        else:
            expected_profile = "普通接入链路瓶颈，目标约 100 Mbps。"

        ok = result["ok"] and mbps is not None
        detail = f"{mbps} Mbps" if mbps is not None else result["output"][:160]
        self.log_event("perf", f"{source} 到 {target} iperf3 {'成功' if ok else '失败'}", ok)
        audit = self.log_audit("perf", source, target, ok, detail)
        output = f"吞吐量: {mbps} Mbps\n{expected_profile}" if mbps is not None else result["output"]
        return {
            "action": "perf",
            "source": source,
            "target": target,
            "targetIp": target_ip,
            "ok": ok,
            "rc": result["rc"],
            "command": command,
            "output": output,
            "rawOutput": raw_output,
            "mbps": mbps,
            "expectedProfile": expected_profile,
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
        }

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
        receiver_pid = f"/tmp/campus_message_{token}.pid"
        receiver_cmd = (
            f"rm -f {shlex.quote(out_path)}; "
            f"nohup python3 {shlex.quote(str(MESSAGE_RECEIVER))} "
            f"--port {port} --out {shlex.quote(out_path)} --timeout 7 "
            f"> /tmp/campus_message_{token}.log 2>&1 & echo $! > {shlex.quote(receiver_pid)}"
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
        shell_command = send_cmd + '; rc=$?; printf "\n__RC__%s\n" "$rc"'
        wrapped = f"timeout 6 bash -lc {shlex.quote(shell_command)}"
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
        target_host.cmd(f"if [ -s {shlex.quote(receiver_pid)} ]; then kill $(cat {shlex.quote(receiver_pid)}) 2>/dev/null || true; fi; rm -f {shlex.quote(receiver_pid)} {shlex.quote(out_path)} /tmp/campus_message_{token}.log 2>/dev/null || true")

        received = None
        if received_raw.strip():
            try:
                received = json.loads(received_raw)
            except json.JSONDecodeError:
                received = {"raw": received_raw}

        ok = rc == 0 and bool(received and received.get("ok"))
        self.log_event("message", f"{source} 向 {target} 发送消息 {'成功' if ok else '失败'}", ok)
        audit = self.log_audit("message", source, target, ok, message[:160])
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
            "auditLevel": audit["level"],
            "auditReason": audit["reason"],
        }

    def run_action(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            action = body.get("action")
            source = str(body.get("source", ""))
            target = str(body.get("target", ""))
            if action == "dhcp":
                return self.dhcp(source)
            if action == "dns":
                return self.resolve_domain(source, target)
            if action in {"fault_down", "fault_up"}:
                return self.set_fault(action, target)
            if action == "ping":
                return self.ping(source, target)
            if action == "web":
                return self.web(source, target)
            if action == "ftp":
                return self.ftp(source, target)
            if action == "perf":
                return self.performance(source, target)
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
                ("访客主机 DHCP 获取地址", "dhcp", "guest1", "guest1", True),
                ("学生主机解析 Web 校园域名", "dns", "stu1", "web.campus.local", True),
                ("访客通过域名访问 Web", "web", "guest1", "web.campus.local", True),
                ("访客访问办公楼被隔离", "ping", "guest1", "office1", False),
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
                elif action == "dhcp":
                    result = self.dhcp(source)
                elif action == "dns":
                    result = self.resolve_domain(source, target)
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
        if self.path == "/api/audit":
            self.write_json(HTTPStatus.OK, {"ok": True, "audit": RUNTIME.audit[-80:], "auditSummary": RUNTIME.audit_summary()})
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
