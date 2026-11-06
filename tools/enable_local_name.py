#!/usr/bin/env python3
"""Persist HelloBoard's mDNS name without changing WiFi or the OS hostname."""
import os
from pathlib import Path
import re
import shutil
import subprocess


def configure(text):
    """Preserve unrelated Avahi settings and comments; repeated runs are safe."""
    required = {'server': {'host-name': 'helloboard', 'domain-name': 'local'},
                'publish': {'disable-publishing': 'no', 'publish-addresses': 'yes'}}
    section = None
    output = []
    for line in text.splitlines():
        match = re.match(r'^\s*\[([^]]+)\]\s*$', line)
        if match:
            if section in required:
                output.extend(f'{key}={value}' for key, value in required.pop(section).items())
            section = match.group(1)
        # Remove active duplicates; insert authoritative settings at section end.
        key = re.match(r'^\s*([^#;\s=]+)\s*=', line)
        if key and key.group(1) in required.get(section, {}):
            continue
        output.append(line)
    if section in required:
        output.extend(f'{key}={value}' for key, value in required.pop(section).items())
    for section, values in required.items():
        output.extend(['', f'[{section}]'])
        output.extend(f'{key}={value}' for key, value in values.items())
    return '\n'.join(output) + '\n'


def main():
    if os.geteuid() != 0:
        raise SystemExit('请使用 sudo python3 tools/enable_local_name.py 执行。')
    if not shutil.which('avahi-daemon'):
        raise SystemExit('请先安装：sudo apt install avahi-daemon')
    path = Path('/etc/avahi/avahi-daemon.conf')
    original = path.read_text()
    updated = configure(original)
    changed = original != updated
    if changed:
        path.write_text(updated)
    subprocess.run(['systemctl', 'enable', '--now', 'avahi-daemon.service'], check=True)
    if changed:
        subprocess.run(['systemctl', 'restart', 'avahi-daemon.service'], check=True)
    print('本地名称发现已启用：http://helloboard.local')
    print('不修改系统 hostname，也不重启 WiFi。设备需与客户端处于同一本地网络。')
    print('如名称冲突，请检查 Avahi 日志；实际广播名称可能自动添加数字后缀。')


if __name__ == '__main__':
    main()
