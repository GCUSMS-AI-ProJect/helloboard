"""NetworkManager adapter. Commands never use a shell or expose PSKs in argv."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import time
import uuid


class NetworkError(RuntimeError):
    pass


def split_escaped(line):
    """Decode nmcli terse fields, including SSIDs containing ':' and '\\'."""
    fields, current, escaped = [], [], False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            fields.append(''.join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        current.append('\\')
    fields.append(''.join(current))
    return fields


class NetworkManager:
    PREFIX = 'helloboard-managed-'
    LEGACY_PREFIX = 'hellosms-managed-'

    def __init__(self, interface='wlan0'):
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', interface):
            raise ValueError('无线网卡名称不正确。')
        self.interface = interface

    def run(self, *args, timeout=15):
        try:
            result = subprocess.run(
                ['nmcli', '--colors', 'no', *args], capture_output=True,
                text=True, timeout=timeout, env={**os.environ, 'LC_ALL': 'C'},
            )
        except (OSError, subprocess.TimeoutExpired):
            raise NetworkError('网络命令不可用或执行超时，请检查 NetworkManager。') from None
        if result.returncode:
            # nmcli error text can include configuration values. Do not log it.
            raise NetworkError('NetworkManager 操作失败，请检查网卡、权限或 Wi-Fi 密码。')
        return result.stdout.rstrip('\n')

    def snapshot(self):
        values = self.run('-g', 'GENERAL.STATE,GENERAL.CON-UUID,IP4.ADDRESS',
                          'device', 'show', self.interface).splitlines()
        connected = bool(values and values[0].startswith('100 '))
        connection_uuid = values[1] if len(values) > 1 and values[1] != '--' else ''
        address = next((line.split('/')[0] for line in values[2:] if '/' in line), '')
        mode, ssid = '', ''
        if connected and connection_uuid:
            details = self.run('-g', '802-11-wireless.mode,802-11-wireless.ssid',
                               '--escape', 'no', 'connection', 'show', 'uuid', connection_uuid).splitlines()
            mode = 'ap' if details and details[0] == 'ap' else 'lan'
            ssid = details[1] if len(details) > 1 else ''
        return {'connected': connected and bool(address), 'mode': mode,
                'ssid': ssid, 'address': address, 'uuid': connection_uuid}

    def read_connection_password(self, connection_uuid):
        """Read an existing NM profile only after browser authorization."""
        security = self.run('-g', '802-11-wireless-security.key-mgmt',
                            'connection', 'show', 'uuid', connection_uuid)
        if security in ('', '--'):
            return ''
        if security not in ('wpa-psk', 'sae'):
            raise NetworkError('此网络的认证方式不支持显示密码。')
        password = self.run('--show-secrets', '-g', '802-11-wireless-security.psk',
                            '--escape', 'no', 'connection', 'show', 'uuid', connection_uuid)
        if not password or password == '--':
            raise NetworkError('当前连接没有可读取的已保存密码。')
        return password

    def scan(self):
        warning = ''
        try:
            self.run('--wait', '12', 'device', 'wifi', 'rescan', 'ifname', self.interface, timeout=16)
        except NetworkError:
            warning = '网卡当前无法主动扫描，显示最近的扫描结果。也可以手动输入名称。'
        output = self.run('-t', '--escape', 'yes', '-f', 'IN-USE,SSID,SIGNAL,SECURITY',
                          'device', 'wifi', 'list', 'ifname', self.interface, '--rescan', 'no')
        networks = {}
        for line in output.splitlines():
            fields = split_escaped(line)
            if len(fields) != 4 or not fields[1]:
                continue
            active, ssid, signal, security = fields
            item = {'ssid': ssid, 'signal': int(signal) if signal.isdigit() else 0,
                    'security': security or '开放网络', 'active': active == '*',
                    'supported': security in ('', '--') or ('WPA' in security and '802.1X' not in security)}
            key = (ssid, security)
            if key in networks:
                item['active'] = item['active'] or networks[key]['active']
                if item['signal'] <= networks[key]['signal']:
                    networks[key]['active'] = item['active']
                    continue
            networks[key] = item
        return {'networks': sorted(networks.values(), key=lambda n: (not n['active'], -n['signal'])),
                'warning': warning}

    def activate(self, mode, config):
        settings = config[mode]
        self.run('radio', 'wifi', 'on')
        if mode == 'ap' and self.run('-g', 'WIFI-PROPERTIES.AP', 'device', 'show', self.interface) != 'yes':
            raise NetworkError('这块无线网卡不支持 AP 热点模式。')
        connection_uuid = str(uuid.uuid4())
        # Volatile profiles: YAML is the source of truth. Existing user profiles
        # are never modified or deleted; old profiles owned by us are cleaned up.
        self.run('connection', 'add', 'save', 'no', 'type', 'wifi',
                 'ifname', self.interface, 'con-name', self.PREFIX + connection_uuid,
                 'connection.uuid', connection_uuid, 'autoconnect', 'no',
                 'ssid', settings['ssid'])
        secret_file = None
        try:
            properties = ['802-11-wireless.mode', 'ap' if mode == 'ap' else 'infrastructure',
                          'ipv6.method', 'disabled']
            if mode == 'ap':
                properties += ['802-11-wireless.band', 'bg', '802-11-wireless.channel', '6',
                               'ipv4.method', 'shared', 'ipv4.addresses', settings['address'] + '/24',
                               'ipv4.never-default', 'yes']
            else:
                properties += ['ipv4.method', 'auto', '802-11-wireless.hidden', 'yes']
            if settings['password']:
                properties += ['802-11-wireless-security.key-mgmt', 'wpa-psk',
                               '802-11-wireless-security.psk-flags', '2']
            self.run('connection', 'modify', '--temporary', 'uuid', connection_uuid, *properties)
            args = ['--wait', '35', 'connection', 'up', 'uuid', connection_uuid, 'ifname', self.interface]
            if settings['password']:
                fd, secret_file = tempfile.mkstemp(prefix='helloboard-psk-')
                with os.fdopen(fd, 'w') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write('802-11-wireless-security.psk:' + settings['password'] + '\n')
                args += ['passwd-file', secret_file]
            self.run(*args, timeout=40)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                status = self.snapshot()
                if status['connected'] and status['uuid'] == connection_uuid:
                    if mode != 'ap' or status['address'] == settings['address']:
                        self.cleanup(keep=connection_uuid)
                        return status
                time.sleep(1)
            raise NetworkError('连接未能取得预期的 IP 地址。')
        except Exception:
            self.delete(connection_uuid)
            raise
        finally:
            if secret_file:
                Path(secret_file).unlink(missing_ok=True)

    def delete(self, connection_uuid):
        try:
            self.run('connection', 'delete', 'uuid', connection_uuid)
        except NetworkError:
            pass

    def cleanup(self, keep):
        try:
            lines = self.run('-t', '--escape', 'yes', '-f', 'UUID,NAME', 'connection', 'show').splitlines()
        except NetworkError:
            # Cleanup is best effort; a working connection must stay active.
            return
        for line in lines:
            fields = split_escaped(line)
            if (len(fields) == 2 and fields[0] != keep
                    and fields[1] in (self.PREFIX + fields[0], self.LEGACY_PREFIX + fields[0])):
                self.delete(fields[0])
