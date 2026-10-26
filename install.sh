#!/usr/bin/env bash
# Install without changing Wi-Fi. Activation is an explicit, separate command.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo '请使用 sudo bash install.sh 安装。' >&2
  exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir=/opt/helloboard
with_wifi=false
case "${1:-}" in
  --with-wifi) with_wifi=true ;;
  '') ;;
  *) echo '用法：sudo bash install.sh [--with-wifi]' >&2; exit 1 ;;
esac
[[ "$(uname -s)" == Linux ]] || { echo 'Windows 请使用 install.ps1。' >&2; exit 1; }
command -v systemctl >/dev/null && [[ -d /run/systemd/system ]] || {
  echo '未检测到 systemd。请使用虚拟环境直接运行 wifi.py --dashboard-only。' >&2; exit 1;
}
if [[ -e /opt/hellosms-wifi ]]; then
  echo '检测到旧版安装，请使用 sudo bash update.sh 迁移并保留配置。' >&2
  exit 1
fi
if $with_wifi; then
  command -v nmcli >/dev/null || { echo '启用 WiFi 管理需要安装并启动 NetworkManager。' >&2; exit 1; }
fi
if systemctl is-active --quiet helloboard.service; then
  echo '服务正在运行，请先停用或安排维护后再升级。' >&2
  exit 1
fi
install -d -m 755 "$target_dir"
if [[ "$source_dir" != "$target_dir" ]]; then
  for file in wifi.py authentication.py pam_auth.py configuration.py controller.py network.py system_metrics.py portable_metrics.py host_platform.py process_control.py requirements.txt README.md; do
    install -m 644 "$source_dir/$file" "$target_dir/$file"
  done
  cp -R "$source_dir/static" "$source_dir/templates" "$target_dir/"
  cp -R "$source_dir/systemd" "$source_dir/tools" "$target_dir/"
  install -m 755 "$source_dir/install.sh" "$source_dir/update.sh" "$target_dir/"
fi
python3 -m venv "$target_dir/.venv"
"$target_dir/.venv/bin/pip" install -r "$target_dir/requirements.txt"
if [[ ! -f "$target_dir/wifi.yaml" ]]; then
  (cd "$target_dir" && .venv/bin/python -c 'from pathlib import Path; from configuration import ConfigStore; ConfigStore(Path("wifi.yaml"))')
fi
chmod 600 "$target_dir/wifi.yaml"
install -m 644 "$source_dir/systemd/helloboard.service" /etc/systemd/system/helloboard.service
if $with_wifi; then
  sed -i 's/ --dashboard-only$//' /etc/systemd/system/helloboard.service
  sed -i '/^After=/c\Wants=NetworkManager.service\nAfter=network.target NetworkManager.service' /etc/systemd/system/helloboard.service
fi
python3 "$target_dir/tools/install_pam.py"
systemctl daemon-reload
printf '%s\n' '已安装。配置位于 /opt/helloboard/wifi.yaml。' '启用并开机自启：sudo systemctl enable --now helloboard'
if $with_wifi; then
  printf '%s\n' '已启用 WiFi 管理；首次启动按保存的配置切换网络，默认创建热点。'
else
  printf '%s\n' '当前为系统看板，不接管 WiFi；如需启用，安装时添加 --with-wifi。'
fi
