# 基于 Mininet 的校园网构建

本项目构建一个可运行、可展示、可写入课程报告的校园网络仿真系统。网络覆盖学生宿舍、教学楼、图书馆、办公楼、人事处、财务处和服务器区，满足部门内部二层互通、部门间三层互通、Web/FTP 资源访问和敏感区域访问控制。

## 目录结构

```text
campus-mininet/
├── install_mininet_wsl.sh          # WSL Ubuntu 环境安装脚本
├── run_campus_net.sh               # Mininet CLI 运行入口
├── run_live_server.sh              # 实时联动 Web 控制台运行入口
├── start_live_server_background.sh # 后台启动实时控制台
├── stop_live_server.sh             # 停止实时控制台并清理 Mininet
├── src/
│   ├── campus_net.py               # Mininet 拓扑、安全策略、测试入口
│   ├── campus_live_server.py       # Web API 后端，实时控制 Mininet
│   └── services/
│       ├── message_receiver.py     # 目标主机一次性 TCP 消息接收器
│       ├── message_sender.py       # 源主机 TCP 消息发送器
│       ├── simple_ftp_server.py    # 无第三方依赖的 FTP 服务
│       ├── web_root/index.html     # Web 服务器首页
│       └── ftp_root/README.txt     # FTP 服务器示例文件
├── visualization/
│   ├── index.html                  # 可视化交互界面
│   ├── styles.css
│   └── app.js
└── docs/
    ├── report.md                   # 课程报告正文
    └── test_plan.md                # 测试方案和预期结果
```

## WSL Ubuntu 安装

在 PowerShell 中进入项目目录，然后进入 WSL：

```powershell
cd E:\A\计算机网络\campus-mininet
wsl -d Ubuntu
```

在 WSL 中执行：

```bash
cd /mnt/e/A/计算机网络/campus-mininet
chmod +x install_mininet_wsl.sh run_campus_net.sh
./install_mininet_wsl.sh
```

安装脚本需要 `sudo` 权限，会安装 Mininet、Open vSwitch、curl、iperf3、dnsmasq、dnsutils、dhclient 等课程项目常用工具。

## 运行方式一：Mininet CLI

```bash
cd /mnt/e/A/计算机网络/campus-mininet
sudo ./run_campus_net.sh
```

进入 Mininet CLI 后可以执行：

```bash
stu1 ping -c 2 stu2
stu1 ping -c 2 teach1
stu1 ping -c 2 hr1
office1 ping -c 2 hr1
stu1 curl -s http://10.10.100.10
stu1 curl -s ftp://10.10.100.20/README.txt
attacker1 ping -c 2 web
```

也可以直接运行自动测试：

```bash
sudo ./run_campus_net.sh --test
```

## 运行方式二：实时联动控制台

推荐用于答辩展示。该模式会启动真实 Mininet 拓扑，同时提供 Web API 和可视化页面：

```bash
cd /mnt/e/A/计算机网络/campus-mininet
sudo ./run_live_server.sh 8088
```

然后在 Windows 浏览器打开：

```text
http://127.0.0.1:8088
```

如果希望后台运行，使用：

```bash
sudo ./start_live_server_background.sh 8088
```

停止实时控制台并清理 Mininet：

```bash
sudo ./stop_live_server.sh
```

实时控制台支持：

- 启动/停止真实 Mininet 拓扑。
- 执行真实 `ping`、Web 访问和 FTP 下载。
- 执行真实 `iperf3` 带宽测试，展示吞吐量和性能瓶颈说明。
- 执行 DHCP 地址获取和 DNS 校园域名解析。
- 制造/恢复接入交换机上联故障和 Web/FTP 服务故障。
- 从一个 Mininet 主机向另一个 Mininet 主机发送可选择的业务消息。
- 展示目标主机实际收到的消息内容、发送方、接收方和 TCP 端口。
- 高亮真实通信路径，成功显示绿色，失败或 ACL 阻断显示红色。
- 展示 VLAN ID、access/trunk 链路角色和核心路由 VLAN 子接口设计。
- 展示安全审计记录，记录普通访问、ACL 阻断、外部访问和性能测试。
- 一键运行包含消息发送场景的自动测试。

后端只接受白名单主机和操作类型，浏览器不会直接执行 shell 命令。

## 地址规划

| 区域 | 网段 | 网关 | 示例主机 |
|---|---|---|---|
| 学生宿舍 / VLAN 10 | `10.10.10.0/24` | `10.10.10.1` | `stu1`, `stu2`, `stu3` |
| 教学楼 / VLAN 20 | `10.10.20.0/24` | `10.10.20.1` | `teach1`, `teach2` |
| 图书馆 / VLAN 30 | `10.10.30.0/24` | `10.10.30.1` | `lib1`, `lib2` |
| 办公楼 / VLAN 40 | `10.10.40.0/24` | `10.10.40.1` | `office1`, `office2` |
| 人事处 / VLAN 50 | `10.10.50.0/24` | `10.10.50.1` | `hr1` |
| 财务处 / VLAN 60 | `10.10.60.0/24` | `10.10.60.1` | `fin1` |
| 访客网络 / VLAN 70 | `10.10.70.0/24` | `10.10.70.1` | `guest1` DHCP |
| 服务器区 / VLAN 100 | `10.10.100.0/24` | `10.10.100.1` | `web`, `ftp` |
| 外部模拟区 / VLAN 200 | `203.0.113.0/24` | `203.0.113.1` | `attacker1` |

## VLAN、审计与性能测试

拓扑使用真实 OVS VLAN：

- 主机到接入交换机端口为 access VLAN。
- 接入交换机到核心交换机 `s_core` 为 trunk。
- `s_core` 到核心路由器 `r_core` 为 trunk。
- `r_core` 使用 `r_core-eth0.<vlan>` 子接口作为各 VLAN 网关。

实时控制台会把每次访问写入安全审计记录，并同步追加到 `/tmp/campus_audit.log`。高风险审计包括外部模拟区访问校园内网，以及学生宿舍、教学楼、图书馆访问人事处或财务处。

带宽测试使用 `iperf3`，页面中选择“带宽测试 iperf3”或点击快速场景即可运行。普通区域访问服务器区预期约 100 Mbps，服务器区内部 `web -> ftp` 预期体现 1000 Mbps 高速链路。

## DHCP、DNS、访客网络与故障模拟

`r_core` 通过 `dnsmasq` 提供 DHCP/DNS 服务。学生、教学、图书馆、办公和访客 VLAN 各自拥有 `100-199` 地址池；`guest1` 和 `dhcp_stu1` 用于演示动态地址获取。

校园 DNS 记录：

| 域名 | 地址 |
|---|---|
| `web.campus.local` | `10.10.100.10` |
| `ftp.campus.local` | `10.10.100.20` |
| `hr.campus.local` | `10.10.50.11` |
| `finance.campus.local` | `10.10.60.11` |

访客网络 VLAN 70 只允许访问服务器区 Web/FTP，不允许访问学生、教学、图书馆、办公、人事和财务区域。实时控制台支持一键制造/恢复接入交换机上联故障，以及停止/恢复 Web/FTP 服务，用于展示故障发生后业务失败、恢复后业务恢复的过程。

## 安全策略

核心路由节点 `r_core` 使用 `iptables` 实现 ACL：

- 学生宿舍、教学楼、图书馆禁止访问人事处和财务处。
- 办公楼允许访问人事处和财务处。
- 内网各区域允许访问 Web/FTP 服务器。
- 外部模拟主机禁止访问校园内网。
- 访客网络只允许访问 Web/FTP 服务区，禁止进入校园内部办公和敏感区域。
- 其他普通校园区域之间保持三层互通。
