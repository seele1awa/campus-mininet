#!/usr/bin/env python3
"""Campus network simulation built with Mininet.

Topology goals:
- L2 connectivity inside every campus area through one access switch.
- L3 connectivity across areas through a Linux core router.
- Shared Web/FTP services in a server subnet.
- ACL isolation for HR and Finance, plus an external attack simulation subnet.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    from mininet.cli import CLI
    from mininet.link import TCLink
    from mininet.log import info, setLogLevel
    from mininet.net import Mininet
    from mininet.node import Node, OVSKernelSwitch
    from mininet.topo import Topo
except ImportError as exc:
    print("Mininet 未安装。请先在 WSL Ubuntu 中运行 ./install_mininet_wsl.sh", file=sys.stderr)
    raise


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = PROJECT_ROOT / "src" / "services"
WEB_ROOT = SERVICES_DIR / "web_root"
FTP_ROOT = SERVICES_DIR / "ftp_root"
FTP_SERVER = SERVICES_DIR / "simple_ftp_server.py"


AREAS = {
    "student": {
        "label": "学生宿舍",
        "switch": "s_stu",
        "subnet": "10.10.10.0/24",
        "gateway": "10.10.10.1/24",
        "hosts": [
            ("stu1", "10.10.10.11/24"),
            ("stu2", "10.10.10.12/24"),
            ("stu3", "10.10.10.13/24"),
        ],
    },
    "teaching": {
        "label": "教学楼",
        "switch": "s_teach",
        "subnet": "10.10.20.0/24",
        "gateway": "10.10.20.1/24",
        "hosts": [
            ("teach1", "10.10.20.11/24"),
            ("teach2", "10.10.20.12/24"),
        ],
    },
    "library": {
        "label": "图书馆",
        "switch": "s_lib",
        "subnet": "10.10.30.0/24",
        "gateway": "10.10.30.1/24",
        "hosts": [
            ("lib1", "10.10.30.11/24"),
            ("lib2", "10.10.30.12/24"),
        ],
    },
    "office": {
        "label": "办公楼",
        "switch": "s_office",
        "subnet": "10.10.40.0/24",
        "gateway": "10.10.40.1/24",
        "hosts": [
            ("office1", "10.10.40.11/24"),
            ("office2", "10.10.40.12/24"),
        ],
    },
    "hr": {
        "label": "人事处",
        "switch": "s_hr",
        "subnet": "10.10.50.0/24",
        "gateway": "10.10.50.1/24",
        "hosts": [
            ("hr1", "10.10.50.11/24"),
        ],
    },
    "finance": {
        "label": "财务处",
        "switch": "s_fin",
        "subnet": "10.10.60.0/24",
        "gateway": "10.10.60.1/24",
        "hosts": [
            ("fin1", "10.10.60.11/24"),
        ],
    },
    "server": {
        "label": "服务器区",
        "switch": "s_srv",
        "subnet": "10.10.100.0/24",
        "gateway": "10.10.100.1/24",
        "hosts": [
            ("web", "10.10.100.10/24"),
            ("ftp", "10.10.100.20/24"),
        ],
    },
    "external": {
        "label": "外部模拟区",
        "switch": "s_ext",
        "subnet": "203.0.113.0/24",
        "gateway": "203.0.113.1/24",
        "hosts": [
            ("attacker1", "203.0.113.100/24"),
        ],
    },
}


HOST_GATEWAYS = {
    host: area["gateway"].split("/")[0]
    for area in AREAS.values()
    for host, _ip in area["hosts"]
}


class LinuxRouter(Node):
    """A Mininet node configured as a Linux router."""

    def config(self, **params):  # type: ignore[override]
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")
        self.cmd("sysctl -w net.ipv4.conf.all.rp_filter=0")
        self.cmd("sysctl -w net.ipv4.conf.default.rp_filter=0")

    def terminate(self):  # type: ignore[override]
        self.cmd("iptables -F FORWARD")
        self.cmd("iptables -P FORWARD ACCEPT")
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class CampusTopo(Topo):
    """Campus topology with per-area access switches and one core router."""

    def build(self):  # type: ignore[override]
        router = self.addNode("r_core", cls=LinuxRouter, ip=None)

        for dpid_index, (area_key, area) in enumerate(AREAS.items(), start=1):
            switch = self.addSwitch(
                area["switch"],
                cls=OVSKernelSwitch,
                failMode="standalone",
                dpid=f"{dpid_index:016x}",
            )
            self.addLink(
                switch,
                router,
                intfName2=f"r_core-{area_key}",
                params2={"ip": area["gateway"]},
                cls=TCLink,
                bw=100 if area_key != "server" else 1000,
                delay="2ms" if area_key != "external" else "20ms",
                use_tbf=True,
            )
            gateway_ip = area["gateway"].split("/")[0]
            for host_name, host_ip in area["hosts"]:
                host = self.addHost(
                    host_name,
                    ip=host_ip,
                    defaultRoute=f"via {gateway_ip}",
                )
                self.addLink(host, switch, cls=TCLink, bw=100, delay="1ms", use_tbf=True)


def configure_security(router: Node) -> None:
    """Apply ACL policies on the core router."""

    router.cmd("iptables -F FORWARD")
    router.cmd("iptables -P FORWARD ACCEPT")

    # Existing flows should continue once they were allowed.
    router.cmd("iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")

    # External simulation subnet cannot enter the campus intranet.
    router.cmd("iptables -A FORWARD -s 203.0.113.0/24 -d 10.10.0.0/16 -j DROP")

    normal_user_subnets = ["10.10.10.0/24", "10.10.20.0/24", "10.10.30.0/24"]
    sensitive_subnets = ["10.10.50.0/24", "10.10.60.0/24"]
    for source in normal_user_subnets:
        for dest in sensitive_subnets:
            router.cmd(f"iptables -A FORWARD -s {source} -d {dest} -j REJECT")

    # Explicit service access rules are kept for readability and report evidence.
    router.cmd("iptables -A FORWARD -s 10.10.0.0/16 -d 10.10.100.0/24 -p tcp -m multiport --dports 80,21 -j ACCEPT")
    router.cmd("iptables -A FORWARD -s 10.10.40.0/24 -d 10.10.50.0/24 -j ACCEPT")
    router.cmd("iptables -A FORWARD -s 10.10.40.0/24 -d 10.10.60.0/24 -j ACCEPT")


def start_services(net: Mininet) -> None:
    """Start Web and FTP services on the server-area hosts."""

    web = net.get("web")
    ftp = net.get("ftp")

    web.cmd("pkill -f 'http.server 80' || true")
    ftp.cmd("pkill -f 'simple_ftp_server.py' || true")

    web.cmd(f"cd {WEB_ROOT} && nohup python3 -m http.server 80 > /tmp/campus_web.log 2>&1 &")
    ftp.cmd(f"nohup python3 {FTP_SERVER} --root {FTP_ROOT} --port 21 > /tmp/campus_ftp.log 2>&1 &")


def print_summary(net: Mininet) -> None:
    info("\n*** 校园网地址规划\n")
    for area in AREAS.values():
        info(f"{area['label']}: {area['subnet']}, 网关 {area['gateway'].split('/')[0]}\n")
        for host_name, host_ip in area["hosts"]:
            info(f"  - {host_name}: {host_ip.split('/')[0]}\n")
    info("\n*** 服务地址: Web=http://10.10.100.10, FTP=ftp://10.10.100.20/README.txt\n")
    info("*** 敏感区域 ACL: 学生宿舍/教学楼/图书馆 -> 人事处/财务处 被拒绝，办公楼允许访问\n\n")


def run_case(net: Mininet, title: str, host_name: str, command: str, expect_ok: bool) -> bool:
    host = net.get(host_name)
    wrapped = f"bash -lc '{command} >/tmp/campus_case.out 2>&1; rc=$?; cat /tmp/campus_case.out; echo __RC__$rc'"
    output = host.cmd(wrapped)
    rc_line = [line for line in output.splitlines() if line.startswith("__RC__")]
    rc = int(rc_line[-1].replace("__RC__", "")) if rc_line else 1
    ok = rc == 0
    passed = ok == expect_ok
    state = "PASS" if passed else "FAIL"
    expected = "允许" if expect_ok else "拒绝"
    actual = "允许" if ok else "拒绝"
    info(f"[{state}] {title}: 预期{expected}, 实际{actual}\n")
    if not passed and output.strip():
        info(output.replace("__RC__", "exit=") + "\n")
    return passed


def run_tests(net: Mininet) -> int:
    info("\n*** 自动测试开始\n")
    cases = [
        ("宿舍区内部二层互通", "stu1", "ping -c 1 -W 1 10.10.10.12", True),
        ("宿舍区到教学楼三层互通", "stu1", "ping -c 1 -W 1 10.10.20.11", True),
        ("宿舍区访问 Web 服务", "stu1", "curl -fsS http://10.10.100.10", True),
        ("宿舍区访问 FTP 服务", "stu1", "curl -fsS ftp://10.10.100.20/README.txt", True),
        ("宿舍区访问人事处被限制", "stu1", "ping -c 1 -W 1 10.10.50.11", False),
        ("教学楼访问财务处被限制", "teach1", "ping -c 1 -W 1 10.10.60.11", False),
        ("办公楼访问人事处允许", "office1", "ping -c 1 -W 1 10.10.50.11", True),
        ("办公楼访问财务处允许", "office1", "ping -c 1 -W 1 10.10.60.11", True),
        ("外部主机访问 Web 被阻断", "attacker1", "ping -c 1 -W 1 10.10.100.10", False),
    ]
    results = [run_case(net, *case) for case in cases]
    passed = sum(1 for item in results if item)
    info(f"*** 自动测试完成: {passed}/{len(results)} 通过\n")
    return 0 if all(results) else 1


def build_net() -> Mininet:
    topo = CampusTopo()
    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=True,
        waitConnected=False,
    )
    return net


def main() -> int:
    parser = argparse.ArgumentParser(description="Campus Mininet topology")
    parser.add_argument("--test", action="store_true", help="run automated connectivity and ACL tests")
    parser.add_argument("--no-cli", action="store_true", help="start topology and exit after tests")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("Mininet 需要 root 权限，请使用 sudo 运行。", file=sys.stderr)
        return 1

    setLogLevel("info")
    net = build_net()
    exit_code = 0
    try:
        info("*** 启动校园网拓扑\n")
        net.start()
        configure_security(net.get("r_core"))
        start_services(net)
        print_summary(net)

        if args.test:
            exit_code = run_tests(net)

        if not args.no_cli and not args.test:
            CLI(net)
    finally:
        info("*** 停止校园网拓扑\n")
        net.stop()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
