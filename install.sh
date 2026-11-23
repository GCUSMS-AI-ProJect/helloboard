#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir=/opt/helloboard
mode=auto
with_wifi=false
start=false

for option in "$@"; do
  case "$option" in
    --system) mode=system ;;
    --local) mode=local ;;
    --with-wifi) with_wifi=true ;;
    --start) start=true ;;
    -h|--help)
      printf '%s\n' '用法：bash install.sh [--system|--local] [--start] [--with-wifi]' \
        '默认自动识别环境。--start 启用并启动系统服务，或在当前终端运行。' \
        '--with-wifi 适用于宿主机的系统服务，需要 NetworkManager。'
      exit 0 ;;
    *) echo "未知选项：$option。请运行 bash install.sh --help。" >&2; exit 1 ;;
  esac
done

[[ "$(uname -s)" == Linux ]] || { echo 'Windows 请使用 install.ps1。' >&2; exit 1; }
running_systemd() {
  command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] &&
    [[ "$(cat /proc/1/comm)" == systemd ]] &&
    [[ ! -e /.dockerenv && ! -e /run/.containerenv ]] &&
    { ! command -v systemd-detect-virt >/dev/null || ! systemd-detect-virt --quiet --container; }
}
if [[ "$mode" == auto ]]; then
  if running_systemd; then
    mode=system
  else
    mode=local
  fi
fi

install_dependencies() {
  local directory="$1"
  if ! command -v python3 >/dev/null ||
      ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo '需要 Python 3.10 或更新版本。' >&2
    exit 1
  fi
  if ! python3 -m venv "$directory/.venv"; then
    echo '创建虚拟环境失败。Debian、Ubuntu 和 Raspberry Pi OS 可安装 python3-venv。' >&2
    exit 1
  fi
  "$directory/.venv/bin/python" -m pip install -r "$source_dir/requirements.txt"
}

if [[ "$mode" == local ]]; then
  if $with_wifi; then
    echo '宿主机 Wi-Fi 管理请使用 --system --with-wifi。Docker 请使用宿主机 Wi-Fi 控制套接字。' >&2
    exit 1
  fi
  install_dependencies "$source_dir"
  if $start; then
    exec bash "$source_dir/start.sh"
  fi
  echo '依赖已安装。运行 bash start.sh 启动 HelloBoard。'
  exit 0
fi

if ! running_systemd; then
  echo '系统服务需要在宿主机上运行 systemd。请使用 bash install.sh --local。' >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo '请使用 sudo bash install.sh 安装系统服务。' >&2
  exit 1
fi
if [[ -e /opt/hellosms-wifi ]]; then
  echo '检测到旧版安装，请使用 sudo bash update.sh 迁移并保留配置。' >&2
  exit 1
fi
if [[ -e "$target_dir/runtime" ]]; then
  echo '检测到离线 DEB 安装，请使用 DEB 包更新。' >&2
  exit 1
fi
if $with_wifi; then
  command -v nmcli >/dev/null || { echo '启用 Wi-Fi 管理需要安装 NetworkManager。' >&2; exit 1; }
  if systemctl is-active --quiet helloboard-control.socket; then
    echo '宿主机 Wi-Fi 已由 Docker 的 HelloBoard 控制服务管理。请使用桥接部署，或停用该服务后再切换。' >&2
    exit 1
  fi
fi
if systemctl is-active --quiet helloboard.service; then
  echo '服务正在运行，请使用 sudo bash update.sh 更新。' >&2
  exit 1
fi

install -d -m 755 "$target_dir"
install_dependencies "$target_dir"
if [[ "$source_dir" != "$target_dir" ]]; then
  for file in wifi.py web_assets.py authentication.py pam_auth.py configuration.py controller.py network.py network_bridge.py system_metrics.py portable_metrics.py host_platform.py pi_dashboard.py process_control.py requirements.txt README.md; do
    install -m 644 "$source_dir/$file" "$target_dir/$file"
  done
  cp -R "$source_dir/static" "$source_dir/templates" "$source_dir/systemd" "$source_dir/tools" "$target_dir/"
  install -m 755 "$source_dir/install.sh" "$source_dir/start.sh" "$source_dir/update.sh" "$target_dir/"
fi
if [[ ! -f "$target_dir/wifi.yaml" ]]; then
  (cd "$target_dir" && .venv/bin/python -c 'from pathlib import Path; from configuration import ConfigStore; ConfigStore(Path("wifi.yaml"))')
fi
chmod 600 "$target_dir/wifi.yaml"
install -d -m 755 /etc/helloboard
if [[ ! -e /etc/helloboard/helloboard.env ]]; then
  install -m 600 "$target_dir/systemd/helloboard.env" /etc/helloboard/helloboard.env
fi
install -m 644 "$target_dir/systemd/helloboard.service" /etc/systemd/system/helloboard.service
if $with_wifi; then
  sed -i 's/ --dashboard-only$/ --native-wifi/' /etc/systemd/system/helloboard.service
  sed -i '/^After=/c\Wants=NetworkManager.service\nAfter=network.target NetworkManager.service' /etc/systemd/system/helloboard.service
fi
python3 "$target_dir/tools/install_pam.py"
systemctl daemon-reload
echo '已安装。环境变量位于 /etc/helloboard/helloboard.env，Wi-Fi 配置位于 /opt/helloboard/wifi.yaml。'
if $with_wifi; then
  echo '服务启动时将应用已保存的 Wi-Fi 模式。'
fi
if $start; then
  systemctl enable --now helloboard.service
  echo 'HelloBoard 已启动并启用开机自启。'
else
  echo '启动并设为开机自启：sudo systemctl enable --now helloboard'
fi
