"""Exercise deployment scripts in a private filesystem with a fake systemd.

Only the root guard and absolute OS directories are adapted in the test copy;
no real system service, NetworkManager profile, or installed configuration is used.
"""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.relocate_venv import relocate

ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        for name in ['wifi.py', 'web_assets.py','authentication.py','pam_auth.py','configuration.py','controller.py',
                     'network.py','system_metrics.py','portable_metrics.py','host_platform.py','process_control.py','requirements.txt','README.md','install.sh','update.sh']:
            shutil.copy2(ROOT / name, self.source / name)
        for name in ['static','templates','systemd','tools']:
            shutil.copytree(ROOT / name, self.source / name, ignore=shutil.ignore_patterns('__pycache__'))
        self.units = self.root / 'etc/systemd/system'
        self.units.mkdir(parents=True)
        self.pam = self.root / 'etc/pam.d'
        self.pam.mkdir(parents=True)
        (self.pam / 'common-auth').write_text('test policy')
        (self.pam / 'common-account').write_text('test policy')
        self.legacy = self.root / 'opt/hellosms-wifi'
        self.target = self.root / 'opt/helloboard'
        self.legacy.mkdir(parents=True)
        (self.legacy / '.venv/bin').mkdir(parents=True)
        (self.legacy / '.venv/bin/python').symlink_to(sys.executable)
        self.launcher = '#!' + str(self.legacy) + '/.venv/bin/python\n'
        (self.legacy / '.venv/bin/pip').write_text(self.launcher)
        (self.legacy / '.venv/bin/pip').chmod(0o755)
        self.config = b'mode: lan\nlan:\n  ssid: keep-network\n  password: keep-secret\n'
        (self.legacy / 'wifi.yaml').write_bytes(self.config)
        (self.pam / 'hellowifi').write_text('legacy policy')
        unit = (ROOT / 'systemd/helloboard.service').read_text().replace('/opt/helloboard', str(self.legacy))
        unit = unit.replace('Environment=MALLOC_ARENA_MAX=2\n', '')
        unit = unit.replace('--port 80', '--port 80 --interface wlan9 --auth-user piuser')
        unit = unit.replace('After=network.target', 'Requires=NetworkManager.service\nAfter=NetworkManager.service')
        (self.units / 'hellosms-wifi.service').write_text(unit)
        override = self.units / 'hellosms-wifi.service.d'
        override.mkdir()
        (override / 'custom.conf').write_text('[Service]\nReadWritePaths=' + str(self.legacy) + '\n')
        # Simulate a previous release that included the now-retired terminal.
        for retired in ['terminal.py','static/terminal.js','static/terminal.css','templates/terminal.html','static/vendor/xterm/xterm.js']:
            path = self.legacy / retired
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('retired terminal fixture')
        self.state_path = self.root / 'state.json'
        self.state_path.write_text(json.dumps({'enabled': {'hellosms-wifi.service':'enabled'}, 'calls':[]}))
        mock_bin = self.root / 'bin'
        mock_bin.mkdir()
        systemctl = mock_bin / 'systemctl'
        systemctl.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
p = Path(os.environ['HELLOBOARD_TEST_STATE'])
s = json.loads(p.read_text())
args = sys.argv[1:]
s['calls'].append(args)
code = 0
if args[0] == 'is-enabled':
    value = s['enabled'].get(args[1], 'disabled')
    print(value)
    code = 0 if value in ('enabled','enabled-runtime') else 1
elif args[0] == 'is-active':
    code = 0 if s.get('active', {}).get(args[-1], False) else 3
elif args[0] in ('restart', 'stop'):
    s.setdefault('active', {})[args[-1]] = args[0] == 'restart'
elif args[0] == 'disable':
    s['enabled'][args[-1]] = 'disabled'
elif args[0] == 'enable':
    s['enabled'][args[-1]] = 'enabled-runtime' if '--runtime' in args else 'enabled'
p.write_text(json.dumps(s))
sys.exit(code)
''')
        systemctl.chmod(0o755)
        self.env = {**os.environ, 'PATH':str(mock_bin) + os.pathsep + os.environ['PATH'],
                    'PYTHONPATH':os.pathsep.join(p for p in sys.path if 'site-packages' in p),
                    'HELLOBOARD_TEST_STATE':str(self.state_path)}
        script = (self.source / 'update.sh').read_text()
        script = script.replace('if [[ $EUID -ne 0 ]]; then', 'if false; then', 1)
        script = script.replace('/opt/helloboard', str(self.target)).replace('/opt/hellosms-wifi', str(self.legacy))
        script = script.replace('/etc/systemd/system', str(self.units)).replace('/etc/pam.d', str(self.pam))
        # The helper receives the private test PAM directory rather than /etc.
        helper = self.source / 'tools/install_pam.py'
        helper.write_text(helper.read_text().replace("Path('/etc/pam.d')", 'Path(' + repr(str(self.pam)) + ')'))
        # Dependency installation is tested with a fake pip, not real network access.
        script = script.replace('"$installed_dir/.venv/bin/python" -m pip install -r "$source_dir/requirements.txt"', '"$installed_dir/.venv/bin/python" -c "import flask, yaml, waitress"')
        (self.source / 'update.sh').write_text(script)

    def run_update(self):
        return subprocess.run(['bash', str(self.source / 'update.sh')], env=self.env,
                              text=True, capture_output=True, timeout=15)

    def state(self):
        return json.loads(self.state_path.read_text())

    def test_migration_preserves_credentials_custom_options_and_autostart(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.legacy.exists())
        self.assertEqual((self.target / 'wifi.yaml').read_bytes(), self.config)
        self.assertEqual((self.target / 'wifi.yaml').stat().st_mode & 0o777, 0o600)
        launcher = self.target / '.venv/bin/pip'
        self.assertEqual(launcher.read_text(), self.launcher.replace(str(self.legacy), str(self.target)))
        self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
        self.assertFalse((self.units / 'hellosms-wifi.service').exists())
        unit = (self.units / 'helloboard.service').read_text()
        self.assertIn('--interface wlan9 --auth-user piuser', unit)
        self.assertNotIn('hellosms-wifi', unit)
        self.assertNotIn('Requires=NetworkManager.service', unit)
        self.assertIn('Wants=NetworkManager.service', unit)
        self.assertEqual(unit.count('Environment=MALLOC_ARENA_MAX=2'), 1)
        self.assertIn(str(self.target), (self.units / 'helloboard.service.d/custom.conf').read_text())
        self.assertTrue((self.pam / 'helloboard').exists())
        for retired in ['terminal.py','static/terminal.js','static/terminal.css','templates/terminal.html','static/vendor/xterm']:
            self.assertFalse((self.target / retired).exists(), retired)
        self.assertFalse((self.pam / 'hellowifi').exists())
        self.assertEqual(self.state()['enabled']['helloboard.service'], 'enabled')
        self.assertIn(['restart','helloboard.service'], self.state()['calls'])
        # A normal subsequent update is idempotent and still preserves the YAML.
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / 'wifi.yaml').read_bytes(), self.config)
        self.assertEqual((self.units / 'helloboard.service').read_text().count('Environment=MALLOC_ARENA_MAX=2'), 1)
        self.assertFalse(any('backup' in p.name for p in self.root.rglob('*')))
        result = subprocess.run(['bash', str(self.target / 'update.sh')], env=self.env,
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / 'wifi.yaml').read_bytes(), self.config)

    def test_legacy_runtime_autostart_moves_to_new_service(self):
        state = self.state()
        state['enabled']['hellosms-wifi.service'] = 'enabled-runtime'
        self.state_path.write_text(json.dumps(state))
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(['disable','--runtime','hellosms-wifi.service'], self.state()['calls'])
        self.assertEqual(self.state()['enabled']['helloboard.service'], 'enabled-runtime')

    def test_memory_setting_preserves_existing_unit_and_custom_override(self):
        unit = self.units / 'hellosms-wifi.service'
        unit.write_text(unit.read_text().replace('[Service]\n', '[Service]\nEnvironment=MALLOC_ARENA_MAX=4\n'))
        custom = self.units / 'hellosms-wifi.service.d/custom.conf'
        custom.write_text(custom.read_text() + 'Environment=MALLOC_ARENA_MAX=8\n')
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        updated = (self.units / 'helloboard.service').read_text()
        self.assertIn('Environment=MALLOC_ARENA_MAX=4', updated)
        self.assertNotIn('Environment=MALLOC_ARENA_MAX=2', updated)
        self.assertIn('Environment=MALLOC_ARENA_MAX=8',
            (self.units / 'helloboard.service.d/custom.conf').read_text())

    def test_disabled_and_runtime_autostart_are_preserved(self):
        for value in ['disabled','enabled-runtime']:
            with self.subTest(value=value):
                state = self.state()
                service = 'hellosms-wifi.service' if self.legacy.exists() else 'helloboard.service'
                state['enabled'][service] = value
                state['calls'] = []
                self.state_path.write_text(json.dumps(state))
                result = self.run_update()
                self.assertEqual(result.returncode, 0, result.stderr)
                enables = [c for c in self.state()['calls'] if c[0]=='enable']
                if value == 'disabled': self.assertEqual(enables, [])
                else: self.assertEqual(enables, [['enable','--runtime','helloboard.service']])

    def test_dependency_failure_keeps_existing_service_and_configuration(self):
        script = self.source / 'update.sh'
        script.write_text(script.read_text().replace('"$installed_dir/.venv/bin/python" -c "import flask, yaml, waitress"', 'false'))
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['calls'], [])
        self.assertEqual((self.legacy / 'wifi.yaml').read_bytes(), self.config)

    def test_conflicting_directories_abort_before_service_stop(self):
        self.target.mkdir()
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['calls'], [])
        self.assertEqual((self.legacy / 'wifi.yaml').read_bytes(), self.config)

    def test_missing_source_aborts_before_service_stop(self):
        (self.source / 'tools/relocate_venv.py').unlink()
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()['calls'], [])
        self.assertTrue(self.legacy.exists())

    def test_relocator_leaves_binary_and_symlinks_untouched(self):
        launcher = self.legacy / '.venv/bin/binary'
        launcher.write_bytes(b'\xff\xfe\x00')
        relocate('/previous/project', self.legacy)
        self.assertEqual(launcher.read_bytes(), b'\xff\xfe\x00')
        self.assertTrue((self.legacy / '.venv/bin/python').is_symlink())

    def test_fresh_install_selects_dashboard_or_wifi_without_starting_service(self):
        shutil.rmtree(self.legacy)
        mock_nmcli = self.root / 'bin/nmcli'
        mock_nmcli.write_text('#!/bin/sh\nexit 0\n')
        mock_nmcli.chmod(0o755)
        script = (ROOT / 'install.sh').read_text()
        script = script.replace('if [[ $EUID -ne 0 ]]; then', 'if false; then', 1)
        script = script.replace('/opt/helloboard', str(self.target)).replace('/opt/hellosms-wifi', str(self.legacy))
        script = script.replace('/etc/systemd/system', str(self.units)).replace('/run/systemd/system', str(self.units))
        script = script.replace('python3 -m venv "$target_dir/.venv"',
            'mkdir -p "$target_dir/.venv/bin"\nln -sf ' + repr(sys.executable) + ' "$target_dir/.venv/bin/python"')
        script = script.replace('"$target_dir/.venv/bin/pip" install -r "$target_dir/requirements.txt"',
            '"$target_dir/.venv/bin/python" -c "import flask, yaml, waitress"')
        installer = self.source / 'install.sh'
        installer.write_text(script)
        for args in [[], ['--with-wifi']]:
            result = subprocess.run(['bash', str(installer), *args], env=self.env,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            unit = (self.units / 'helloboard.service').read_text()
            self.assertEqual('--dashboard-only' in unit, not bool(args))
            self.assertNotIn('Requires=NetworkManager.service', unit)
            self.assertIn('Environment=MALLOC_ARENA_MAX=2', unit)
            self.assertTrue((self.target / 'host_platform.py').exists())
            self.assertTrue((self.target / 'portable_metrics.py').exists())
            self.assertFalse(any(c[0] in ('start', 'restart', 'stop') for c in self.state()['calls']))
