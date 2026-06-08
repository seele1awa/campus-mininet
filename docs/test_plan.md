# 测试方案与操作记录

## 1. 环境准备

在 WSL Ubuntu 中进入项目目录：

```bash
cd /mnt/e/A/计算机网络/campus-mininet
chmod +x install_mininet_wsl.sh run_campus_net.sh
chmod +x run_live_server.sh
./install_mininet_wsl.sh
```

如果系统已安装 Mininet，可以跳过安装脚本。

## 2. 启动拓扑

```bash
sudo ./run_campus_net.sh
```

启动后会进入 Mininet CLI。核心脚本会自动完成：

- 创建核心路由器 `r_core`。
- 创建各区域接入交换机。
- 创建核心交换机 `s_core`，配置 access/trunk VLAN。
- 创建各区域主机。
- 配置主机默认网关。
- 在核心路由器创建 `r_core-eth0.<vlan_id>` 子接口作为各 VLAN 网关。
- 开启核心路由器 IPv4 转发。
- 配置 `iptables` ACL。
- 启动 Web/FTP 服务。

## 3. 手工测试命令

### 3.0 VLAN 配置验证

```bash
s_stu ovs-vsctl get port s_stu-eth1 tag
s_stu ovs-vsctl get port s_stu-eth9 trunks
s_core ovs-vsctl get port s_core-eth1 trunks
r_core ip link show r_core-eth0.10
```

预期：`s_stu-eth1` 为 access VLAN 10，`s_stu-eth9` 和 `s_core-eth1` 承载 VLAN 10，`r_core-eth0.10` 子接口存在。

### 3.1 部门内部二层互通

```bash
stu1 ping -c 2 stu2
```

预期：成功。

### 3.2 部门间三层互通

```bash
stu1 ping -c 2 teach1
lib1 ping -c 2 office1
```

预期：成功。

### 3.3 Web 服务访问

```bash
stu1 curl -s http://10.10.100.10
teach1 curl -s http://10.10.100.10
office1 curl -s http://10.10.100.10
```

预期：均成功返回“校园网 Web 服务器”页面内容。

### 3.4 FTP 服务访问

```bash
stu1 curl -s ftp://10.10.100.20/README.txt
lib1 curl -s ftp://10.10.100.20/README.txt
office1 curl -s ftp://10.10.100.20/README.txt
```

预期：均成功返回 FTP 测试文件内容。

### 3.5 敏感区域访问控制

```bash
stu1 ping -c 2 hr1
teach1 ping -c 2 fin1
lib1 ping -c 2 hr1
```

预期：失败，说明普通区域不能访问人事处和财务处。

### 3.6 办公区域访问敏感部门

```bash
office1 ping -c 2 hr1
office1 ping -c 2 fin1
```

预期：成功，说明办公楼被策略允许。

### 3.7 外部攻击模拟

```bash
attacker1 ping -c 2 web
attacker1 ping -c 2 hr1
```

预期：失败，说明外部模拟区无法进入校园内网。

## 4. 自动测试

```bash
sudo ./run_campus_net.sh --test
```

预期输出包含：

```text
[PASS] 宿舍区内部二层互通
[PASS] 宿舍区到教学楼三层互通
[PASS] 宿舍区访问 Web 服务
[PASS] 宿舍区访问 FTP 服务
[PASS] 宿舍区访问人事处被限制
[PASS] 教学楼访问财务处被限制
[PASS] 办公楼访问人事处允许
[PASS] 办公楼访问财务处允许
[PASS] 外部主机访问 Web 被阻断
```

## 5. 性能扩展测试

可以使用 `iperf3` 观察链路吞吐，也可以在实时控制台中选择“带宽测试 iperf3”直接运行。

```bash
web iperf3 -s -D
stu1 iperf3 -c 10.10.100.10 -t 5
```

由于拓扑脚本中服务器区上联带宽设置为 1000 Mbps，普通区域链路设置为 100 Mbps，测试结果应体现接入链路带宽约束。

建议对比：

```bash
web iperf3 -s -D
stu1 iperf3 -c 10.10.100.10 -t 5
pkill -f iperf3

ftp iperf3 -s -D
web iperf3 -c 10.10.100.20 -t 5
pkill -f iperf3
```

预期：`stu1 -> web` 受普通接入链路限制，约为 100 Mbps 级别；`web -> ftp` 位于服务器区内部，预期高于普通区域并体现 1000 Mbps 链路设计。虚拟机性能会造成波动，因此以“能解析吞吐量并体现对比趋势”为验收标准。

## 6. 可视化展示

实时联动控制台启动方式：

```bash
sudo ./run_live_server.sh 8088
```

浏览器打开：

```text
http://127.0.0.1:8088
```

控制台会自动启动真实 Mininet 拓扑。展示时建议依次点击以下快速场景：

1. 宿舍内部二层互通。
2. 宿舍访问教学楼。
3. 学生访问 Web。
4. 学生访问 FTP。
5. 学生访问人事处。
6. 办公楼向财务处发送业务消息。

## 7. 实时消息发送测试

实时控制台的“主机间消息发送”不是前端模拟。后端会在目标 Mininet 主机中启动一次性 TCP 接收器，然后由源 Mininet 主机连接目标 IP 和端口发送 JSON 消息。

### 7.1 办公楼向财务处发送消息

操作：

```text
发送方：office1
接收方：fin1
消息模板：办公审批消息
```

预期：成功。页面输出中应出现 `fin1` 实际收到的 payload，例如发送方 `office1`、接收方 `fin1`、消息内容和接收端口。

### 7.2 学生宿舍向人事处发送消息

操作：

```text
发送方：stu1
接收方：hr1
消息模板：人事档案查询
```

预期：失败。因为学生宿舍到人事处命中核心路由器 ACL，页面应显示发送失败或连接被拒绝，目标主机没有收到消息。

## 8. 实时控制台自动测试

在页面点击“运行自动测试”，预期 `11/11` 通过：

```text
PASS 宿舍区内部二层互通
PASS 宿舍区到教学楼三层互通
PASS 宿舍区访问 Web 服务
PASS 宿舍区访问 FTP 服务
PASS 宿舍区访问人事处被限制
PASS 教学楼访问财务处被限制
PASS 办公楼访问人事处允许
PASS 办公楼访问财务处允许
PASS 外部主机访问 Web 被阻断
PASS 办公楼向财务处发送业务消息
PASS 学生向人事处发送消息被拦截
```

## 9. 安全审计测试

实时控制台会在“安全审计”面板展示访问记录，并同步追加到 `/tmp/campus_audit.log`。

建议测试：

1. 执行 `stu1 -> hr1` ping，预期失败，审计级别为高风险，原因为普通区域访问敏感区域。
2. 执行 `attacker1 -> web` ping，预期失败，审计级别为高风险，原因为外部模拟区访问校园内网。
3. 执行 `office1 -> fin1` ping 或消息发送，预期成功，审计级别为正常。
4. 执行 `stu1 -> web` 与 `web -> ftp` 性能测试，预期审计面板记录 `perf` 动作和吞吐量结果。
