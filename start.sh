#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python="$source_dir/.venv/bin/python"
if [[ ! -x "$python" ]]; then
  echo '请先执行 bash install.sh --local 安装 Python 依赖。' >&2
  exit 1
fi
export HELLOBOARD_WIFI_MODE=dashboard
exec "$python" "$source_dir/wifi.py" "$@"
