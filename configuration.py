"""Validated YAML configuration, kept next to wifi.py and written atomically."""
from copy import deepcopy
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path
import os
import tempfile

import yaml

DEFAULT_CONFIG = {
    'mode': 'ap',
    'lan': {'ssid': '', 'password': ''},
    'ap': {'ssid': 'hellosms', 'password': '', 'address': '192.168.11.17'},
    'networks': [],
}


def validate_network(value, *, allow_empty=False):
    if not isinstance(value, dict):
        raise ValueError('Wi-Fi 配置格式不正确。')
    ssid, password = value.get('ssid'), value.get('password')
    if not isinstance(ssid, str) or not isinstance(password, str):
        raise ValueError('Wi-Fi 名称和密码必须是文字。')
    if not (0 if allow_empty else 1) <= len(ssid.encode('utf-8')) <= 32:
        raise ValueError('Wi-Fi 名称需为 1–32 字节，中文通常每字占 3 字节。')
    if any(ord(c) < 32 or ord(c) == 127 for c in ssid + password):
        raise ValueError('名称和密码不能包含换行或控制字符。')
    if password and not (8 <= len(password) <= 63 and password.isascii()):
        if not (len(password) == 64 and all(c in '0123456789abcdefABCDEF' for c in password)):
            raise ValueError('密码需为 8–63 位 ASCII 字符，或 64 位十六进制密钥。')
    return {'ssid': ssid, 'password': password}


def validate_config(value):
    if not isinstance(value, dict) or value.get('mode') not in ('ap', 'lan'):
        raise ValueError('模式必须为 ap 或 lan。')
    lan = validate_network(value.get('lan'), allow_empty=True)
    ap = validate_network(value.get('ap'))
    address = value['ap'].get('address')
    try:
        ip = IPv4Address(address)
    except (ValueError, TypeError):
        raise ValueError('热点地址必须是有效的 IPv4 地址。') from None
    if not any(ip in network for network in PRIVATE_NETWORKS) or int(ip) % 256 in (0, 255):
        raise ValueError('热点地址需使用私有地址，且不能是 /24 网段的网络或广播地址。')
    ap['address'] = str(ip)
    saved = value.get('networks', [])
    if not isinstance(saved, list) or len(saved) > 100:
        raise ValueError('已保存的网络列表格式不正确，最多保存 100 个网络。')
    networks = []
    for item in [lan, *saved]:
        network = validate_network(item, allow_empty=True)
        if network['ssid'] and not any(n['ssid'] == network['ssid'] for n in networks):
            networks.append(network)
    return {'mode': value['mode'], 'lan': lan, 'ap': ap, 'networks': networks[:100]}


PRIVATE_NETWORKS = tuple(map(IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))


class ConfigStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if not self.path.exists():
            self.save(deepcopy(DEFAULT_CONFIG))

    def load(self):
        try:
            with self.path.open(encoding='utf-8') as stream:
                value = yaml.safe_load(stream)
        except yaml.YAMLError:
            raise ValueError('wifi.yaml 格式有误，请检查缩进和引号。') from None
        return validate_config(value)

    def save(self, config):
        config = validate_config(config)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.wifi-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                if hasattr(os, 'fchmod'):
                    os.fchmod(stream.fileno(), 0o600)
                yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
