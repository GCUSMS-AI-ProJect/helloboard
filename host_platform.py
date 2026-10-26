"""Detect host capabilities once at startup, without changing system settings.

Linux keeps the native /proc collector. Other desktop systems use psutil and
remain read-only until they have a native, authenticated control adapter.
"""
import ctypes.util
import getpass
import os
from pathlib import Path
import platform
import shutil
import subprocess
import threading

from network import NetworkError, split_escaped


def identity():
    family = platform.system()
    release = {}
    if family == 'Linux':
        try:
            release = platform.freedesktop_os_release()
        except OSError:
            pass
    return dict(family=family, name=release.get('PRETTY_NAME') or platform.platform(),
                distribution=release.get('ID', ''), architecture=platform.machine(),
                wsl=family == 'Linux' and 'microsoft' in platform.release().lower())


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'LC_ALL': 'C'})
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect_wifi(host, requested=None, *, dashboard_only=False, run=command):
    caps = dict(available=False, manage=False, ap=False, interface='', reason='')
    if dashboard_only:
        caps['reason'] = '当前仅运行系统看板。'
    elif host['family'] != 'Linux':
        caps['reason'] = '当前系统暂不支持 WiFi 配置与热点管理。'
    elif not shutil.which('nmcli'):
        caps['reason'] = '未安装 NetworkManager，仅显示系统状态。'
    else:
        output = run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE', 'device', 'status'])
        if output is None:
            caps['reason'] = 'NetworkManager 未运行，仅显示系统状态。'
        else:
            devices = [split_escaped(line) for line in output.splitlines()]
            # "unavailable" can mean a soft-blocked radio. Keep a managed
            # adapter discoverable so the existing activation can turn it on.
            devices = [d for d in devices if len(d) == 3 and d[1] == 'wifi' and d[2] != 'unmanaged']
            devices.sort(key=lambda d: (d[2] != 'connected', d[2] == 'unavailable', d[0] != 'wlan0', d[0]))
            selected = next((d for d in devices if d[0] == requested), None) if requested else next(iter(devices), None)
            if not selected:
                caps['reason'] = '没有可用的无线网卡，仅显示系统状态。'
            else:
                interface = selected[0]
                caps.update(available=True, interface=interface,
                            manage=hasattr(os, 'geteuid') and os.geteuid() == 0,
                            ap=run(['nmcli', '-g', 'WIFI-PROPERTIES.AP', 'device', 'show', interface]) == 'yes')
                if not caps['manage']:
                    caps['reason'] = '当前权限仅支持查看和扫描 WiFi。'
    return caps


class ReadOnlyAuthenticator:
    """No synthetic account or password fallback on unsupported hosts."""
    available = False

    def __init__(self, username=None):
        self.username = username or getpass.getuser()

    def verify(self, password):
        raise PermissionError('当前系统未启用账号验证，仅支持查看。')


def make_authenticator(host, username=None):
    if host['family'] == 'Linux' and ctypes.util.find_library('pam') and Path('/etc/pam.d/helloboard').is_file():
        from authentication import SystemAuthenticator
        return SystemAuthenticator(username)
    return ReadOnlyAuthenticator(username)


class DashboardController:
    """Keep system routes usable when no network-management adapter is available."""
    preview = True

    def __init__(self, capabilities):
        self.capabilities = capabilities
        self.stop_event = threading.Event()

    def start(self):
        pass

    def public_status(self):
        return dict(connected=False, mode='', ssid='', address='', configured_mode='lan',
                    saved_ssid='', has_password=False, saved_networks=[],
                    ap_ssid='', ap_address='', ap_has_password=False, busy=False,
                    phase='unavailable', preview=True, fallback=False,
                    message=self.capabilities['reason'], capabilities=self.capabilities)

    def unavailable(self, *args, **kwargs):
        raise NetworkError(self.capabilities['reason'])

    scan = request = connection_password = ap_password = save_ap_password = unavailable


def make_metrics(host):
    if host['family'] == 'Linux':
        from system_metrics import SystemMetrics
        return SystemMetrics()
    from portable_metrics import PortableSystemMetrics
    return PortableSystemMetrics(host=host)
