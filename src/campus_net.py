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
import ipaddress
import os
import shlex
import subprocess
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
ROUTER_TRUNK_INTF = "r_core-eth0"
CORE_ROUTER_PORT = "s_core-eth15"


DNS_RECORDS = {
    "web.campus.local": "10.10.100.10",
    "ftp.campus.local": "10.10.100.20",
    "hr.campus.local": "10.10.50.11",
    "finance.campus.local": "10.10.60.11",
}

DHCP_SERVICE_AREAS = {"student", "teaching", "library", "office", "guest"}


AREAS = {
    "student": {
        "label": "学生宿舍",
        "switch": "s_stu",
        "vlan": 10,
        "subnet": "10.10.10.0/24",
        "gateway": "10.10.10.1/24",
        "dhcp": True,
        "hosts": [
            ("stu1", "10.10.10.11/24"),
            ("stu2", "10.10.10.12/24"),
            ("stu3", "10.10.10.13/24"),
            ("dhcp_stu1", "dhcp"),
        ],
    },
    "teaching": {
        "label": "教学楼",
        "switch": "s_teach",
        "vlan": 20,
        "subnet": "10.10.20.0/24",
        "gateway": "10.10.20.1/24",
        "dhcp": True,
        "hosts": [
            ("teach1", "10.10.20.11/24"),
            ("teach2", "10.10.20.12/24"),
        ],
    },
    "library": {
        "label": "图书馆",
        "switch": "s_lib",
        "vlan": 30,
        "subnet": "10.10.30.0/24",
        "gateway": "10.10.30.1/24",
        "dhcp": True,
        "hosts": [
            ("lib1", "10.10.30.11/24"),
            ("lib2", "10.10.30.12/24"),
        ],
    },
    "office": {
        "label": "办公楼",
        "switch": "s_office",
        "vlan": 40,
        "subnet": "10.10.40.0/24",
        "gateway": "10.10.40.1/24",
        "dhcp": True,
        "hosts": [
            ("office1", "10.10.40.11/24"),
            ("office2", "10.10.40.12/24"),
        ],
    },
    "hr": {
        "label": "人事处",
        "switch": "s_hr",
        "vlan": 50,
        "subnet": "10.10.50.0/24",
        "gateway": "10.10.50.1/24",
        "hosts": [
            ("hr1", "10.10.50.11/24"),
        ],
    },
    "finance": {
        "label": "财务处",
        "switch": "s_fin",
        "vlan": 60,
        "subnet": "10.10.60.0/24",
        "gateway": "10.10.60.1/24",
        "hosts": [
            ("fin1", "10.10.60.11/24"),
        ],
    },
    "guest": {
        "label": "访客网络",
        "switch": "s_guest",
        "vlan": 70,
        "subnet": "10.10.70.0/24",
        "gateway": "10.10.70.1/24",
        "dhcp": True,
        "hosts": [
            ("guest1", "dhcp"),
        ],
    },
    "server": {
        "label": "服务器区",
        "switch": "s_srv",
        "vlan": 100,
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
        "vlan": 200,
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


def is_dhcp_host(host_ip: str) -> bool:
    """Return True when a host should obtain its address dynamically."""

    return host_ip == "dhcp"


def host_display_ip(host_ip: str) -> str:
    """Return the visible host address for static and DHCP hosts."""

    return "DHCP" if is_dhcp_host(host_ip) else host_ip.split("/")[0]


def dhcp_pool(area: dict) -> tuple[str, str, str]:
    """Return DHCP start IP, end IP and netmask for an area."""

    network = ipaddress.ip_network(str(area["subnet"]))
    prefix = str(network.network_address).rsplit(".", 1)[0]
    return f"{prefix}.100", f"{prefix}.199", str(network.netmask)


def access_port_name(switch_name: str, host_index: int) -> str:
    """Return a Linux-safe OVS port name for a host-facing access port."""

    return f"{switch_name}-eth{host_index}"


def access_trunk_port_name(switch_name: str) -> str:
    """Return a Linux-safe OVS port name for an access switch trunk uplink."""

    return f"{switch_name}-eth9"


def core_area_port_name(area_index: int) -> str:
    """Return a Linux-safe OVS port name for a core switch area trunk."""

    return f"s_core-eth{area_index}"


def router_vlan_intf(vlan: int | str) -> str:
    """Return a Linux-safe router VLAN subinterface name."""

    return f"{ROUTER_TRUNK_INTF}.{vlan}"


def cleanup_legacy_interfaces() -> None:
    """Remove legacy custom veth names left by interrupted older runs."""

    names = ["s_core-r_core", "r_core-t"]
    for area_key, area in AREAS.items():
        switch_name = area["switch"]
        names.extend([f"{switch_name}-trunk", f"s_core-{area_key}"])
        for host_name, _host_ip in area["hosts"]:
            names.append(f"{switch_name}-{host_name}")
        for host_index, _host in enumerate(area["hosts"], start=1):
            names.append(f"{switch_name}-h{host_index}")
    for name in names:
        subprocess.run(["ip", "link", "delete", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


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
        self.cmd("for intf in $(ip -o link show | awk -F': ' '/r_core-eth0\\./ {print $2}'); do ip link delete \"$intf\" 2>/dev/null || true; done")
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


class CampusTopo(Topo):
    """Campus topology with VLAN access switches, a core trunk switch, and one router."""

    def build(self):  # type: ignore[override]
        router = self.addNode("r_core", cls=LinuxRouter, ip=None)
        core_switch = self.addSwitch(
            "s_core",
            cls=OVSKernelSwitch,
            failMode="standalone",
            dpid="00000000000000ff",
        )
        self.addLink(
            core_switch,
            router,
            intfName1=CORE_ROUTER_PORT,
            intfName2=ROUTER_TRUNK_INTF,
            cls=TCLink,
            bw=1000,
            delay="1ms",
            use_tbf=True,
        )

        for dpid_index, (area_key, area) in enumerate(AREAS.items(), start=1):
            switch = self.addSwitch(
                area["switch"],
                cls=OVSKernelSwitch,
                failMode="standalone",
                dpid=f"{dpid_index:016x}",
            )
            self.addLink(
                switch,
                core_switch,
                intfName1=access_trunk_port_name(area["switch"]),
                intfName2=core_area_port_name(dpid_index),
                cls=TCLink,
                bw=100 if area_key != "server" else 1000,
                delay="2ms" if area_key != "external" else "20ms",
                use_tbf=True,
            )
            gateway_ip = area["gateway"].split("/")[0]
            for host_index, (host_name, host_ip) in enumerate(area["hosts"], start=1):
                host_params = {"ip": None} if is_dhcp_host(host_ip) else {"ip": host_ip, "defaultRoute": f"via {gateway_ip}"}
                host = self.addHost(host_name, **host_params)
                self.addLink(
                    host,
                    switch,
                    intfName2=access_port_name(area["switch"], host_index),
                    cls=TCLink,
                    bw=1000 if area_key == "server" else 100,
                    delay="1ms",
                    use_tbf=True,
                )


def configure_vlans(net: Mininet) -> None:
    """Configure OVS access/trunk ports and router VLAN subinterfaces."""

    vlan_ids = [str(area["vlan"]) for area in AREAS.values()]
    trunk_list = ",".join(vlan_ids)

    core = net.get("s_core")
    core.cmd(f"ovs-vsctl set port {CORE_ROUTER_PORT} trunks={trunk_list}")

    router = net.get("r_core")
    router.cmd(f"ip link set {ROUTER_TRUNK_INTF} up")
    router.cmd("for intf in $(ip -o link show | awk -F': ' '/r_core-eth0\\./ {print $2}'); do ip link delete \"$intf\" 2>/dev/null || true; done")

    for area_index, (_area_key, area) in enumerate(AREAS.items(), start=1):
        switch_name = area["switch"]
        vlan = area["vlan"]

        access_switch = net.get(switch_name)
        access_switch.cmd(f"ovs-vsctl set port {access_trunk_port_name(switch_name)} trunks={vlan}")
        core.cmd(f"ovs-vsctl set port {core_area_port_name(area_index)} trunks={vlan}")

        for host_index, (_host_name, _host_ip) in enumerate(area["hosts"], start=1):
            access_switch.cmd(f"ovs-vsctl set port {access_port_name(switch_name, host_index)} tag={vlan}")

        vlan_intf = router_vlan_intf(vlan)
        router.cmd(f"ip link add link {ROUTER_TRUNK_INTF} name {vlan_intf} type vlan id {vlan}")
        router.cmd(f"ip addr add {area['gateway']} dev {vlan_intf}")
        router.cmd(f"ip link set {vlan_intf} up")


def verify_vlan_config(net: Mininet) -> bool:
    """Return True when core/access VLAN settings and router subinterfaces exist."""

    core = net.get("s_core")
    checks = []
    for area_index, (_area_key, area) in enumerate(AREAS.items(), start=1):
        switch_name = area["switch"]
        vlan = str(area["vlan"])
        access_switch = net.get(switch_name)
        checks.append(access_switch.cmd(f"ovs-vsctl get port {access_trunk_port_name(switch_name)} trunks").strip() in {f"[{vlan}]", vlan})
        checks.append(core.cmd(f"ovs-vsctl get port {core_area_port_name(area_index)} trunks").strip() in {f"[{vlan}]", vlan})
        for host_index, (_host_name, _host_ip) in enumerate(area["hosts"], start=1):
            checks.append(access_switch.cmd(f"ovs-vsctl get port {access_port_name(switch_name, host_index)} tag").strip() == vlan)
        checks.append(net.get("r_core").cmd(f"ip link show {router_vlan_intf(vlan)} >/dev/null 2>&1; echo $?").strip() == "0")
    return all(checks)


def configure_security(router: Node) -> None:
    """Apply ACL policies on the core router."""

    router.cmd("iptables -F FORWARD")
    router.cmd("iptables -P FORWARD ACCEPT")

    # Existing flows should continue once they were allowed.
    router.cmd("iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT")

    # External simulation subnet cannot enter the campus intranet.
    router.cmd("iptables -A FORWARD -s 203.0.113.0/24 -d 10.10.0.0/16 -j DROP")

    # Guest network can use shared services but cannot enter campus user/admin VLANs.
    router.cmd("iptables -A FORWARD -s 10.10.70.0/24 -d 10.10.100.0/24 -p tcp -m multiport --dports 80,21 -j ACCEPT")
    router.cmd("iptables -A FORWARD -s 10.10.70.0/24 -d 10.10.0.0/16 -j REJECT")

    normal_user_subnets = ["10.10.10.0/24", "10.10.20.0/24", "10.10.30.0/24"]
    sensitive_subnets = ["10.10.50.0/24", "10.10.60.0/24"]
    for source in normal_user_subnets:
        for dest in sensitive_subnets:
            router.cmd(f"iptables -A FORWARD -s {source} -d {dest} -j REJECT")

    # Explicit service access rules are kept for readability and report evidence.
    router.cmd("iptables -A FORWARD -s 10.10.0.0/16 -d 10.10.100.0/24 -p tcp -m multiport --dports 80,21 -j ACCEPT")
    router.cmd("iptables -A FORWARD -s 10.10.40.0/24 -d 10.10.50.0/24 -j ACCEPT")
    router.cmd("iptables -A FORWARD -s 10.10.40.0/24 -d 10.10.60.0/24 -j ACCEPT")


def configure_dynamic_hosts(net: Mininet) -> None:
    """Clear any auto-assigned address from DHCP demonstration hosts."""

    for area in AREAS.values():
        for host_name, host_ip in area["hosts"]:
            if not is_dhcp_host(host_ip):
                continue
            host = net.get(host_name)
            intf = host.defaultIntf().name
            host.cmd(f"ip addr flush dev {intf}")
            host.cmd(f"ip link set {intf} up")
            host.cmd("ip route flush table main")


def start_dns_dhcp_services(net: Mininet) -> None:
    """Start dnsmasq on the router for campus DNS and DHCP service."""

    router = net.get("r_core")
    router.cmd("if [ -s /tmp/campus_dnsmasq.pid ]; then kill $(cat /tmp/campus_dnsmasq.pid) 2>/dev/null || true; fi; rm -f /tmp/campus_dnsmasq.pid")

    config_lines = [
        "port=53",
        "bind-interfaces",
        "dhcp-authoritative",
        "dhcp-broadcast",
        "domain=campus.local",
        "local=/campus.local/",
        "log-queries",
        "log-dhcp",
    ]
    for domain, ip in DNS_RECORDS.items():
        config_lines.append(f"address=/{domain}/{ip}")
    for area_id, area in AREAS.items():
        if area_id not in DHCP_SERVICE_AREAS:
            continue
        start_ip, end_ip, netmask = dhcp_pool(area)
        tag = f"vlan{area['vlan']}"
        gateway = area["gateway"].split("/")[0]
        intf = router_vlan_intf(area["vlan"])
        config_lines.extend(
            [
                f"interface={intf}",
                f"dhcp-range=set:{tag},{start_ip},{end_ip},{netmask},12h",
                f"dhcp-option=tag:{tag},option:router,{gateway}",
                f"dhcp-option=tag:{tag},option:dns-server,{gateway}",
                f"dhcp-option=tag:{tag},option:domain-name,campus.local",
            ]
        )

    conf = "\n".join(config_lines) + "\n"
    router.cmd(f"printf %s {shlex.quote(conf)} > /tmp/campus_dnsmasq.conf")
    router.cmd(
        "dnsmasq --conf-file=/tmp/campus_dnsmasq.conf "
        "--pid-file=/tmp/campus_dnsmasq.pid "
        "--dhcp-leasefile=/tmp/campus_dnsmasq.leases "
        "--log-facility=/tmp/campus_dnsmasq.log"
    )


def start_web_service(web: Node) -> None:
    """Start the HTTP service on the given Mininet host."""

    web.cmd("if [ -s /tmp/campus_web.pid ]; then kill $(cat /tmp/campus_web.pid) 2>/dev/null || true; fi; rm -f /tmp/campus_web.pid")
    web.cmd(f"cd {shlex.quote(str(WEB_ROOT))} && nohup python3 -m http.server 80 > /tmp/campus_web.log 2>&1 & echo $! > /tmp/campus_web.pid")


def start_ftp_service(ftp: Node) -> None:
    """Start the FTP service on the given Mininet host."""

    ftp.cmd("if [ -s /tmp/campus_ftp.pid ]; then kill $(cat /tmp/campus_ftp.pid) 2>/dev/null || true; fi; rm -f /tmp/campus_ftp.pid")
    ftp.cmd(
        f"nohup python3 {shlex.quote(str(FTP_SERVER))} "
        f"--root {shlex.quote(str(FTP_ROOT))} --port 21 "
        "> /tmp/campus_ftp.log 2>&1 & echo $! > /tmp/campus_ftp.pid"
    )


def start_services(net: Mininet) -> None:
    """Start Web, FTP, DNS and DHCP services."""

    web = net.get("web")
    ftp = net.get("ftp")

    start_web_service(web)
    start_ftp_service(ftp)
    start_dns_dhcp_services(net)


def print_summary(net: Mininet) -> None:
    info("\n*** 校园网地址规划与 VLAN\n")
    for area in AREAS.values():
        info(f"{area['label']}: VLAN {area['vlan']}, {area['subnet']}, 网关 {area['gateway'].split('/')[0]}\n")
        for host_name, host_ip in area["hosts"]:
            info(f"  - {host_name}: {host_display_ip(host_ip)}\n")
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
    vlan_ok = verify_vlan_config(net)
    info(f"[{'PASS' if vlan_ok else 'FAIL'}] VLAN access/trunk 与路由子接口配置检查\n")
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
        ("访客主机 DHCP 获取地址", "guest1", "dhclient -4 -v -1 guest1-eth0 >/dev/null 2>&1; ip -4 addr show guest1-eth0 | grep -q 10.10.70.", True),
        ("学生主机解析 Web 校园域名", "stu1", "dig +short @10.10.10.1 web.campus.local | grep -q 10.10.100.10", True),
        ("访客访问 Web 服务允许", "guest1", "curl -fsS http://10.10.100.10", True),
        ("访客访问办公楼被隔离", "guest1", "ping -c 1 -W 1 10.10.40.11", False),
    ]
    results = [run_case(net, *case) for case in cases]
    passed = sum(1 for item in results if item) + (1 if vlan_ok else 0)
    total = len(results) + 1
    info(f"*** 自动测试完成: {passed}/{total} 通过\n")
    return 0 if vlan_ok and all(results) else 1


def build_net() -> Mininet:
    cleanup_legacy_interfaces()
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
        configure_vlans(net)
        configure_dynamic_hosts(net)
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
