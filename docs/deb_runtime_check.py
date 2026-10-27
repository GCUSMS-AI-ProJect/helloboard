#!/usr/bin/env python3
"""Start an extracted package in read-only mode and inspect its actual HTTP server.

Native amd64: --app /path/to/extracted/opt/helloboard
ARM64 emulation: additionally --qemu /path/to/qemu-x86_64 --sysroot /path/to/x86_64-linux-gnu
The supplied sysroot must include lib/ld-linux-x86-64.so.2 and glibc libraries.
"""
import argparse
import gzip
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--qemu', type=Path)
    parser.add_argument('--sysroot', type=Path)
    args = parser.parse_args()
    app = args.app.resolve()
    python = app / 'runtime/bin/python3'
    command = [str(python), '-E', '-s', '-B']
    if args.qemu:
        if not args.sysroot:
            parser.error('--qemu requires --sysroot')
        sysroot = args.sysroot.resolve()
        # Starting the target loader also works on ARM64 hosts with 16KB pages.
        command = [str(args.qemu.resolve()), '-L', str(sysroot),
                   str(sysroot / 'lib/ld-linux-x86-64.so.2'), '--library-path',
                   f'{sysroot / "lib"}:{app / "runtime/lib"}', *command]
    imports = subprocess.check_output([*command, '-c',
        'import sys, ssl, flask, waitress, yaml, markupsafe; '
        'assert yaml.__with_libyaml__; '
        'assert markupsafe.escape("<x>") == "&lt;x&gt;"; '
        'print(sys.version.split()[0])'], cwd=app, text=True).strip()
    with socket.socket() as port_probe:
        port_probe.bind(('127.0.0.1', 0))
        port = port_probe.getsockname()[1]
    with tempfile.TemporaryFile(mode='w+t') as log:
        child = subprocess.Popen([*command, str(app / 'wifi.py'), '--dashboard-only',
                                  '--preview', '--host', '127.0.0.1', '--port', str(port)],
                                 cwd=app, stdout=log, stderr=log)
        try:
            base = f'http://127.0.0.1:{port}'

            def fetch(path, headers=None):
                with urlopen(Request(base + path, headers=headers or {}), timeout=10) as response:
                    assert response.status == 200
                    return response.read(), dict(response.headers)

            deadline = time.monotonic() + 45
            while True:
                if child.poll() is not None:
                    log.seek(0)
                    raise RuntimeError(log.read())
                try:
                    html, _ = fetch('/system_status')
                    break
                except URLError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.25)
            assert b'HelloBoard' in html
            capabilities = json.loads(fetch('/api/capabilities')[0])
            assert capabilities['wifi']['manage'] is False
            system = json.loads(fetch('/api/system')[0])
            assert 'cpu' in system and 'memory' in system
            fetch('/api/processes')
            css = next((app / 'static').glob('*.css'))
            compressed, headers = fetch('/static/' + css.name, {'Accept-Encoding': 'gzip'})
            assert headers['Content-Encoding'] == 'gzip'
            assert gzip.decompress(compressed) == css.read_bytes()
            for font in (app / 'static/fonts').glob('*.woff2'):
                data, _ = fetch('/static/fonts/' + font.name)
                assert data == font.read_bytes(), font.name
            print(json.dumps(dict(result='passed', python=imports,
                                  mode='qemu-x86_64' if args.qemu else 'native-amd64',
                                  checks=['C extensions', 'actual Waitress HTTP server', 'system page',
                                          'system/process APIs', 'gzip integrity', 'all font files']), indent=2))
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    main()
