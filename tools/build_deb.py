#!/usr/bin/env python3
"""Build an offline Ubuntu amd64 package on either an ARM64 or x86_64 host.

Only the builder needs pip, curl and dpkg-deb. It never executes target binaries,
copies a developer virtualenv, reads wifi.yaml, or modifies the installed service.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEB = ROOT / 'packaging/deb'
PYTHON_ARCHIVE = 'cpython-3.13.17+20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'
PYTHON_SHA256 = 'f829adc9d888e76c8801b4799ed444188d35239fcae3a9808a99ec5cb0d8d92c'
PYTHON_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20261021/'
              + PYTHON_ARCHIVE.replace('+', '%2B'))
MODULES = ('wifi.py web_assets.py authentication.py pam_auth.py configuration.py '
           'controller.py network.py system_metrics.py portable_metrics.py '
           'host_platform.py process_control.py').split()


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write(path, value, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    path.chmod(mode)


def copy(source, destination, mode=0o644):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='0.1.0-1')
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/helloboard-deb')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--offline', action='store_true', help='Only use verified cached downloads')
    parser.add_argument('--proxy', help='Download proxy; never stored in the package')
    args = parser.parse_args()
    if not args.version or not all(c.isalnum() or c in '.+~-:' for c in args.version):
        parser.error('Invalid Debian version')
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.cache / PYTHON_ARCHIVE
    if not archive.exists():
        if args.offline:
            parser.error(f'Missing runtime archive: {archive}')
        temporary = archive.with_suffix('.download')
        proxy = ['--proxy', args.proxy] if args.proxy else []
        run('curl', '--fail', '--location', '--retry', '4', '--retry-all-errors',
            '--connect-timeout', '15', *proxy, PYTHON_URL, '-o', temporary)
        if digest(temporary) != PYTHON_SHA256:
            raise RuntimeError('Python archive SHA256 mismatch')
        temporary.replace(archive)
    if digest(archive) != PYTHON_SHA256:
        raise RuntimeError('Python archive SHA256 mismatch')
    wheels = args.cache / 'wheels'
    wheels.mkdir(exist_ok=True)
    pip = [sys.executable, '-m', 'pip']
    cross = ['--platform', 'manylinux2014_x86_64', '--python-version', '313',
             '--implementation', 'cp', '--abi', 'cp313', '--only-binary=:all:',
             '--no-deps', '--require-hashes', '-r', str(DEB / 'requirements-amd64.lock')]
    if not args.offline:
        run(*pip, 'download', *cross, '--dest', wheels,
            *(['--proxy', args.proxy] if args.proxy else []))

    with tempfile.TemporaryDirectory(prefix='helloboard-deb-') as temporary:
        stage = Path(temporary) / 'package'
        app = stage / 'opt/helloboard'
        app.mkdir(parents=True)
        unpack = Path(temporary) / 'unpack'
        with tarfile.open(archive) as source:
            source.extractall(unpack, filter='data')
        runtime = app / 'runtime'
        (unpack / 'python').rename(runtime)
        stdlib = runtime / 'lib/python3.13'
        # Keep the interpreter, shared libpython, stdlib and extension modules.
        # GUI tooling, package installation and development headers are unused.
        for path in (runtime / 'include', runtime / 'share/man', runtime / 'lib/pkgconfig',
                     stdlib / 'idlelib', stdlib / 'tkinter', stdlib / 'turtledemo',
                     stdlib / 'ensurepip', stdlib / 'site-packages'):
            shutil.rmtree(path, ignore_errors=True)
        for path in runtime.glob('lib/*'):
            if path.name.startswith(('tcl', 'tk', 'itcl', 'thread', 'libtcl')):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        for path in (stdlib / 'lib-dynload').glob('_tkinter*'):
            path.unlink()
        for path in (runtime / 'bin').iterdir():
            if path.name not in ('python', 'python3', 'python3.13'):
                path.unlink()
        site = stdlib / 'site-packages'
        run(*pip, 'install', *cross, '--no-index', '--find-links', wheels,
            '--no-compile', '--target', site)
        shutil.rmtree(site / 'bin', ignore_errors=True)
        for name in MODULES:
            copy(ROOT / name, app / name)
        for name in ('static', 'templates'):
            shutil.copytree(ROOT / name, app / name)
        copy(ROOT / 'wifi.example.yaml', stage / 'etc/helloboard/wifi.yaml', 0o600)
        (stage / 'etc/helloboard').chmod(0o700)
        copy(DEB / 'default', stage / 'etc/default/helloboard')
        copy(DEB / 'helloboard.service', stage / 'usr/lib/systemd/system/helloboard.service')
        copy(DEB / 'helloboard', stage / 'usr/bin/helloboard', 0o755)
        write(stage / 'etc/pam.d/helloboard',
              '# HelloBoard system account verification\n@include common-auth\n@include common-account\n')
        doc = stage / 'usr/share/doc/helloboard'
        for source in ('README.md', 'docs/deb.md', 'docs/operations.md', 'docs/performance.md'):
            copy(ROOT / source, doc / source)
        shutil.copytree(ROOT / 'docs/images', doc / 'docs/images')
        licenses = DEB / 'runtime-licenses'
        if not licenses.is_dir():
            raise RuntimeError('Missing runtime license notices')
        shutil.copytree(licenses, doc / 'runtime-licenses')
        copy(DEB / 'requirements-amd64.lock', doc / 'requirements-amd64.lock')
        commit = run('git', '-C', ROOT, 'rev-parse', 'HEAD', capture_output=True, text=True).stdout.strip()
        manifest = dict(version=args.version, architecture='amd64', source_commit=commit,
                        source_dirty=bool(run('git', '-C', ROOT, 'status', '--porcelain',
                                              capture_output=True, text=True).stdout),
                        python_url=PYTHON_URL, python_sha256=PYTHON_SHA256,
                        files={str(path.relative_to(app)): digest(path)
                               for path in sorted(app.rglob('*')) if path.is_file()})
        write(doc / 'build-info.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        # Normalize archive permissions and mtimes; config is deliberately private.
        for path in stage.rglob('*'):
            if not path.is_symlink():
                if path.is_dir() and path != stage / 'etc/helloboard':
                    path.chmod(0o755)
                elif path.is_file():
                    path.chmod(0o600 if path == stage / 'etc/helloboard/wifi.yaml'
                               else 0o755 if path.stat().st_mode & 0o111 else 0o644)
        installed = int(run('du', '-sk', stage, capture_output=True, text=True).stdout.split()[0])
        control = stage / 'DEBIAN'
        write(control / 'control', f'''Package: helloboard
Version: {args.version}
Section: admin
Priority: optional
Architecture: amd64
Maintainer: sms <2436210442@qq.com>
Depends: libc6 (>= 2.31), libpam0g, libpam-runtime, systemd (>= 245), init-system-helpers (>= 1.54)
Suggests: network-manager, dnsmasq-base, iproute2
Installed-Size: {installed}
Homepage: https://gitee.com/gcusms/helloboard
Description: Lightweight local system dashboard with bundled Python
 System monitoring, process management and optional NetworkManager WiFi control.
 Includes an isolated x86_64 CPython runtime, runtime dependencies, and local fonts.
 Starts in dashboard-only mode without changing existing network configuration.
''')
        write(control / 'conffiles', '/etc/helloboard/wifi.yaml\n/etc/default/helloboard\n/etc/pam.d/helloboard\n')
        for name in ('preinst', 'postinst', 'prerm', 'postrm'):
            copy(DEB / name, control / name, 0o755)
        epoch = int(os.environ.get('SOURCE_DATE_EPOCH', '1793001600'))
        for path in stage.rglob('*'):
            os.utime(path, (epoch, epoch), follow_symlinks=False)
        package = args.output / f'helloboard_{args.version}_amd64.deb'
        run('dpkg-deb', '--root-owner-group', '-Zxz', '-z6', '--build', stage, package)
        write(package.with_suffix('.deb.sha256'), f'{digest(package)}  {package.name}\n')
        report = dict(package=package.name, package_bytes=package.stat().st_size,
                      installed_kib=installed, python='3.13.17', architecture='amd64',
                      source_commit=commit)
        write(args.output / 'build-report.json', json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
