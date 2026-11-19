"""User-level HelloBoard socket worker. Only edit this user's Bash startup files."""
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import tempfile

SOURCE = '[ -r "$HOME/.proxy.sh" ] && source "$HOME/.proxy.sh"'
LEGACY = {"source ~/.proxy.sh", "source ~/.proxyt.sh", SOURCE}
MARK = "# Managed by HelloBoard"

def read(path):
    return path.read_text() if path.exists() else ""

def replace(path, text, mode):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        os.fchmod(tmp.fileno(), mode)
    os.replace(tmp.name, path)

def handle(home, data):
    script, rc = home / ".proxy.sh", home / ".bashrc"
    old, startup = read(script), read(rc)
    if data.get("action") == "status":
        def field(name, fallback):
            match = re.search(r'^' + name + r'="([^"\n]*)"$', old, re.M)
            return match.group(1) if match else fallback
        return dict(host=field("PROXY_HOST", ""), port=field("PROXY_PORT", "7891"),
                    enabled=any(line.strip() in LEGACY for line in startup.splitlines()) and
                    bool(old) and "# disabled" not in old)
    host, port, enabled = data.get("host"), data.get("port"), data.get("enabled")
    if (data.get("action") != "save" or type(enabled) is not bool or
        not isinstance(host, str) or len(host) > 253 or
        not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part) for part in host.split(".")) or
        type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("请输入有效的主机名、IPv4 地址和端口。")
    script_text = f'#!/bin/bash\n{MARK}\nPROXY_HOST="{host}"\nPROXY_PORT="{port}"\n'
    clear = "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
    if enabled:
        script_text += ('if curl --disable --noproxy "" --silent --fail --proxy "http://${PROXY_HOST}:${PROXY_PORT}" '
                        '--connect-timeout 3 --max-time 5 https://ipinfo.io/ip >/dev/null 2>&1; then\n'
                        '    export http_proxy="http://${PROXY_HOST}:${PROXY_PORT}"\n'
                        '    export https_proxy="$http_proxy" HTTPS_PROXY="$http_proxy"\n'
                        '    unset HTTP_PROXY\nelse\n    ' + clear + '\nfi\n')
    else:
        script_text += "# disabled\n" + clear + "\n"
    for path, content in ((script, old), (rc, startup)):
        backup = path.with_name(path.name + ".before-helloboard")
        if content and not backup.exists():
            replace(backup, content, 0o600)
    clean = "".join(line for line in startup.splitlines(keepends=True) if line.strip() not in LEGACY)
    clean += ("" if not clean or clean.endswith("\n") else "\n") + SOURCE + "\n"
    replace(script, script_text, 0o700)
    if clean != startup:
        replace(rc, clean, (rc.stat().st_mode & 0o777) if rc.exists() else 0o600)
    return dict(host=host, port=port, enabled=enabled)

if __name__ == "__main__":
    try:
        home = Path.home()
        with (home / ".helloboard-proxy.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            reply = handle(home, json.loads(sys.stdin.buffer.readline(4097)))
    except (ValueError, OSError) as error:
        reply = dict(error=str(error))
    print(json.dumps(reply))
