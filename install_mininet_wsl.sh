#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "请在 WSL Ubuntu 或 Linux 环境中运行本脚本。"
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "当前系统缺少 sudo，无法自动安装依赖。"
  exit 1
fi

echo "[1/4] 更新软件源"
sudo apt-get -o Acquire::ForceIPv4=true update

echo "[2/4] 安装 Mininet、Open vSwitch 和测试工具"
sudo DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::ForceIPv4=true install -y \
  mininet \
  openvswitch-switch \
  openvswitch-testcontroller \
  iproute2 \
  iptables \
  curl \
  iperf3 \
  net-tools \
  python3

echo "[3/4] 启动 Open vSwitch"
if command -v service >/dev/null 2>&1; then
  sudo service openvswitch-switch start || true
fi

echo "[4/4] 清理旧 Mininet 状态"
sudo mn -c || true

echo "安装完成。运行：sudo ./run_campus_net.sh"
