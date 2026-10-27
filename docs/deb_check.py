#!/usr/bin/env python3
"""Inspect a built deb without installing it or touching system services."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([str(arg) for arg in args], check=True,
                          capture_output=True, text=True).stdout


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    assert run('dpkg-deb', '-f', args.package, 'Architecture').strip() == 'amd64'
    with tempfile.TemporaryDirectory(prefix='helloboard-deb-check-') as temporary:
        root = Path(temporary)
        run('dpkg-deb', '-x', args.package, root)
        run('dpkg-deb', '-e', args.package, root / 'DEBIAN')
        app = root / 'opt/helloboard'
        manifest = json.loads((root / 'usr/share/doc/helloboard/build-info.json').read_text())
        for name, expected in manifest['files'].items():
            assert sha(app / name) == expected, name
        for name in ('static', 'templates'):
            for source in (ROOT / name).rglob('*'):
                if source.is_file():
                    assert sha(source) == sha(app / source.relative_to(ROOT)), str(source)
        assert not (app / 'wifi.yaml').exists()
        assert not (app / '.venv').exists()
        assert not (app / '.git').exists()
        assert (root / 'etc/helloboard/wifi.yaml').read_bytes() == (ROOT / 'wifi.example.yaml').read_bytes()
        assert (root / 'etc/helloboard').stat().st_mode & 0o777 == 0o700
        assert (root / 'etc/helloboard/wifi.yaml').stat().st_mode & 0o777 == 0o600
        site = app / 'runtime/lib/python3.13/site-packages'
        assert len(list(site.glob('*.dist-info'))) == 9
        assert not (site / 'pip').exists()
        assert not (site / 'playwright').exists()
        assert not (site / 'fontTools').exists()
        assert not list(site.glob('*.pth'))
        for name in ('preinst', 'postinst', 'prerm', 'postrm'):
            run('sh', '-n', root / 'DEBIAN' / name)
        run('sh', '-n', root / 'usr/bin/helloboard')
        unit = (root / 'usr/lib/systemd/system/helloboard.service').read_text()
        assert '--config /etc/helloboard/wifi.yaml' in unit
        assert 'MALLOC_ARENA_MAX=2' in unit
        assert 'ReadWritePaths=/etc/helloboard' in unit
        assert '--dashboard-only' in (root / 'etc/default/helloboard').read_text()
        assert set((root / 'DEBIAN/conffiles').read_text().splitlines()) == {
            '/etc/default/helloboard', '/etc/helloboard/wifi.yaml', '/etc/pam.d/helloboard'}
        elves = []
        versions = set()
        needed = set()
        for path in app.rglob('*'):
            if not path.is_file() or path.is_symlink():
                continue
            with path.open('rb') as source:
                if source.read(4) != b'\x7fELF':
                    continue
            header = run('readelf', '-h', path)
            assert 'Advanced Micro Devices X86-64' in header, str(path)
            versions.update(re.findall(r'GLIBC_([0-9.]+)', run('readelf', '-V', path)))
            for library in re.findall(r'\(NEEDED\).*\[(.*?)\]', run('readelf', '-d', path)):
                if library.startswith('$ORIGIN/'):
                    bundled = (path.parent / library.removeprefix('$ORIGIN/')).resolve()
                    assert bundled.is_relative_to(app) and bundled.is_file(), library
                else:
                    needed.add(library)
            elves.append(str(path.relative_to(app)))
        maximum = max(versions, key=lambda v: tuple(map(int, v.split('.'))))
        assert tuple(map(int, maximum.split('.'))) <= (2, 31), maximum
        supplied = {p.name for p in (app / 'runtime/lib').glob('*')}
        base = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2',
                'librt.so.1', 'libutil.so.1', 'ld-linux-x86-64.so.2'}
        assert not needed - supplied - base, needed - supplied - base
        print(json.dumps(dict(result='passed', elf_files=len(elves),
                              maximum_glibc=maximum, system_shared_libraries=sorted(needed - supplied),
                              static_assets='byte-identical to source', python_packages=9), indent=2))


if __name__ == '__main__':
    main()
