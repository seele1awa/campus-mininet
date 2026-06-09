#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Please run this script in WSL Ubuntu or Linux."
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required to install dependencies."
  exit 1
fi

echo "[1/4] Updating apt repositories"
sudo apt-get -o Acquire::ForceIPv4=true update

echo "[2/4] Installing Mininet, Open vSwitch and test tools"
sudo DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::ForceIPv4=true install -y \
  mininet \
  openvswitch-switch \
  openvswitch-testcontroller \
  iproute2 \
  iptables \
  curl \
  dnsmasq \
  dnsutils \
  isc-dhcp-client \
  iperf3 \
  net-tools \
  python3

echo "[3/4] Starting Open vSwitch"
if command -v service >/dev/null 2>&1; then
  sudo service openvswitch-switch start || true
fi

echo "[4/4] Cleaning old Mininet state"
sudo mn -c || true

echo "Install complete. Run: sudo ./run_campus_net.sh"
