#!/usr/bin/env bash
# Update HelloBoard, migrating the old install without backing up or replacing YAML.
set -euo pipefail
umask 077
if [[ $EUID -ne 0 ]]; then
  echo '请使用 sudo bash update.sh 更新。' >&2
  exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir=/opt/helloboard
legacy_dir=/opt/hellosms-wifi
service=helloboard.service
legacy_service=hellosms-wifi.service
unit_dir=/etc/systemd/system
migrating=false

# Resolve conflicts and check dependencies before stopping the running service.
if [[ -e "$legacy_dir" && -e "$target_dir" ]]; then
  echo '新旧安装目录同时存在，请先核对配置；尚未停止任何服务。' >&2
  exit 1
fi
installed_dir="$target_dir"
installed_service="$service"
if [[ -d "$legacy_dir" ]]; then
  migrating=true
  installed_dir="$legacy_dir"
  installed_service="$legacy_service"
  if [[ -e "$unit_dir/$service" || -e "$unit_dir/$service.d" ]]; then
    echo '新服务文件已存在，请先核对；尚未停止旧服务。' >&2
    exit 1
  fi
fi
if [[ ! -x "$installed_dir/.venv/bin/python" || ! -f "$installed_dir/wifi.yaml" ]]; then
  echo '未找到已安装的程序，请先运行 install.sh。' >&2
  exit 1
fi
"$installed_dir/.venv/bin/python" -c 'import flask, yaml, waitress'
for item in wifi.py authentication.py pam_auth.py configuration.py controller.py network.py system_metrics.py portable_metrics.py host_platform.py process_control.py requirements.txt README.md install.sh update.sh static templates systemd/helloboard.service systemd/helloboard.pam tools/relocate_venv.py tools/install_pam.py; do
  [[ -e "$source_dir/$item" ]] || { echo "更新文件缺失：$item" >&2; exit 1; }
done
# Install new dependencies before stopping the running service. A download failure
# leaves the existing service running; use -m pip so relocated venvs work too.
if [[ ! -f "$installed_dir/requirements.txt" ]] || ! cmp -s "$source_dir/requirements.txt" "$installed_dir/requirements.txt"; then
  "$installed_dir/.venv/bin/python" -m pip install -r "$source_dir/requirements.txt"
fi
enabled_state="$(systemctl is-enabled "$installed_service" 2>/dev/null || true)"
case "$enabled_state" in
  masked|masked-runtime)
    echo '服务已被屏蔽，请先解除屏蔽后更新。' >&2
    exit 1
    ;;
esac

systemctl stop "$installed_service"
if $migrating; then
  if [[ "$enabled_state" == enabled-runtime ]]; then
    systemctl disable --runtime "$legacy_service"
  else
    systemctl disable "$legacy_service"
  fi
  mv -- "$legacy_dir" "$target_dir"
  if [[ "$source_dir" == "$legacy_dir" ]]; then
    source_dir="$target_dir"
  fi
  python3 "$source_dir/tools/relocate_venv.py" "$legacy_dir" "$target_dir"
  if [[ -f "$unit_dir/$legacy_service" ]]; then
    mv -- "$unit_dir/$legacy_service" "$unit_dir/$service"
  fi
  if [[ -d "$unit_dir/$legacy_service.d" ]]; then
    mv -- "$unit_dir/$legacy_service.d" "$unit_dir/$service.d"
  fi
fi

if [[ "$source_dir" != "$target_dir" ]]; then
  for file in wifi.py authentication.py pam_auth.py configuration.py controller.py network.py system_metrics.py portable_metrics.py host_platform.py process_control.py requirements.txt README.md; do
    install -m 644 "$source_dir/$file" "$target_dir/$file"
  done
  for file in install.sh update.sh; do
    install -m 755 "$source_dir/$file" "$target_dir/$file"
  done
  for directory in static templates systemd tools; do
    cp -R "$source_dir/$directory" "$target_dir/"
  done
fi
# Remove the retired web-terminal module from older installations.
for retired in terminal.py static/terminal.js static/terminal.css templates/terminal.html; do
  rm -f -- "$target_dir/$retired"
done
rm -rf -- "$target_dir/static/vendor/xterm"
chmod 600 "$target_dir/wifi.yaml"
if [[ ! -f "$unit_dir/$service" ]]; then
  install -m 644 "$source_dir/systemd/$service" "$unit_dir/$service"
fi
# Keep existing interface/auth-user arguments and service overrides during migration.
for unit in "$unit_dir/$service" "$unit_dir/$service.d/"*.conf; do
  if [[ -f "$unit" ]]; then
    sed -i 's/hellosms-wifi/helloboard/g' "$unit"
  fi
done
sed -i 's/^Description=.*/Description=HelloBoard system dashboard/' "$unit_dir/$service"
sed -i 's/^Requires=NetworkManager.service$/Wants=NetworkManager.service/' "$unit_dir/$service"
python3 "$target_dir/tools/install_pam.py"
systemctl daemon-reload
case "$enabled_state" in
  enabled) systemctl enable "$service" ;;
  enabled-runtime) systemctl enable --runtime "$service" ;;
esac
systemctl restart "$service"
systemctl is-active --quiet "$service"
rm -f -- /etc/pam.d/hellowifi
printf '%s\n' '更新完成，helloboard 服务已重启。' '程序与配置：/opt/helloboard' '原有开机自启状态已保留。'
