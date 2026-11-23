"""User-level HelloBoard socket worker. Only edit this user's Bash startup files."""
import fcntl
from ipaddress import ip_network
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SOURCE = '[ -r "$HOME/.proxy.sh" ] && source "$HOME/.proxy.sh"'
LEGACY = {"source ~/.proxy.sh", "source ~/.proxyt.sh", SOURCE}
MARK = "# Managed by HelloBoard"
PROTOCOLS = {"http", "https", "socks5", "socks5h"}
DOMAIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")

def valid_host(value):
    return 0 < len(value) <= 253 and all(DOMAIN.fullmatch(part) for part in value.split("."))

def valid_bypass(value):
    try:
        ip_network(value, strict=False)
    except ValueError:
        return value == "*" or valid_host(value.removeprefix("."))
    return re.fullmatch(r"[0-9a-fA-F:./]+", value) is not None

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
                    protocol=field("PROXY_PROTOCOL", "http"), bypass=field("PROXY_BYPASS", ""),
                    timeout=field("PROXY_TIMEOUT", "5"),
                    enabled=any(line.strip() in LEGACY for line in startup.splitlines()) and
                    bool(old) and "# disabled" not in old)
    host, port, enabled = data.get("host"), data.get("port"), data.get("enabled")
    action = data.get("action")
    if (action not in ("save", "test") or type(enabled) is not bool or not isinstance(host, str)
        or (not valid_host(host) and (host or enabled or action == "test"))
        or type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("请输入有效的主机名、IPv4 地址和端口。")
    protocol = data.get("protocol", "http")
    bypass = data.get("bypass", "")
    timeout = data.get("timeout", 5)
    if not isinstance(protocol, str) or protocol not in PROTOCOLS:
        raise ValueError("请选择 HTTP、HTTPS 或 SOCKS5 代理。")
    if type(timeout) is not int or not 3 <= timeout <= 10:
        raise ValueError("测试超时需为 3–10 秒。")
    if not isinstance(bypass, str) or len(bypass) > 512:
        raise ValueError("直连列表最多 512 个字符。")
    entries = [entry.strip() for entry in bypass.split(",") if entry.strip()]
    if not all(valid_bypass(entry) for entry in entries):
        raise ValueError("直连列表需填写主机名、IP 或网段，并用逗号分隔。")
    bypass = ",".join(entries)

    proxy_url = f"{protocol}://{host}:{port}"
    if action == "test":
        result = subprocess.run(["curl", "--disable", "--noproxy", "", "--silent", "--fail",
                                 "--location", "--connect-timeout", "3", "--max-time", str(timeout),
                                 "--proxy", proxy_url, "http://ipinfo.io"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise ValueError("Error · 代理联网测试失败，请检查地址和端口。")
        return {"ok": True}
    script_text = (f'#!/bin/bash\n{MARK}\nPROXY_HOST="{host}"\nPROXY_PORT="{port}"\n'
                   f'PROXY_PROTOCOL="{protocol}"\nPROXY_BYPASS="{bypass}"\nPROXY_TIMEOUT="{timeout}"\n')
    clear = "unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
    script_text += (
        'if [[ -n "${_helloboard_bypass-}" ]]; then\n'
        '    [[ "${no_proxy-}" != "$_helloboard_bypass" ]] || unset no_proxy\n'
        '    [[ "${NO_PROXY-}" != "$_helloboard_bypass" ]] || unset NO_PROXY\n'
        '    unset _helloboard_bypass\n'
        'fi\n'
    )
    if enabled:
        script_text += ('if curl --disable --noproxy "" --silent --fail --proxy "${PROXY_PROTOCOL}://${PROXY_HOST}:${PROXY_PORT}" '
                        '--connect-timeout 3 --max-time "$PROXY_TIMEOUT" --location http://ipinfo.io >/dev/null 2>&1; then\n'
                        '    export http_proxy="${PROXY_PROTOCOL}://${PROXY_HOST}:${PROXY_PORT}"\n'
                        '    export https_proxy="$http_proxy" HTTPS_PROXY="$http_proxy"\n'
                        '    if [[ -n "$PROXY_BYPASS" ]]; then\n'
                        '        export no_proxy="$PROXY_BYPASS" NO_PROXY="$PROXY_BYPASS"\n'
                        '        _helloboard_bypass="$PROXY_BYPASS"\n'
                        '    fi\n'
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
    return dict(host=host, port=port, enabled=enabled, protocol=protocol, bypass=bypass, timeout=timeout)

if __name__ == "__main__":
    try:
        home = Path.home()
        data = json.loads(sys.stdin.buffer.readline(4097))
        if data.get("action") == "test":
            reply = handle(home, data)
        else:
            with (home / ".helloboard-proxy.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                reply = handle(home, data)
    except (ValueError, OSError) as error:
        reply = dict(error=str(error))
    print(json.dumps(reply))
