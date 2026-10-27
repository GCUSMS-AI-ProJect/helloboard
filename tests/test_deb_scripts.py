"""Exercise maintainer scripts in a private tree with fake systemd commands."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DebScriptsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.log = self.root / 'calls'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f'{self.bin}:/usr/bin:/bin', DEB_TEST_LOG=str(self.log))
        fake = '''#!/bin/sh
printf '%s %s\\n' "${0##*/}" "$*" >> "$DEB_TEST_LOG"
if [ "${1:-}" = --quiet ]; then shift; fi
case "$1" in
  debian-installed) exit "${DEB_TEST_EXISTING:-1}" ;;
  was-enabled) exit "${DEB_TEST_WAS_ENABLED:-0}" ;;
esac
exit 0
'''
        for name in ('systemctl', 'deb-systemd-helper', 'deb-systemd-invoke'):
            path = self.bin / name
            path.write_text(fake)
            path.chmod(0o755)
        (self.root / 'run/systemd/system').mkdir(parents=True)
        self.config = self.root / 'etc/helloboard/wifi.yaml'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('mode: lan\nlan: {ssid: SavedNetwork, password: saved-example}\n')
        self.defaults = self.root / 'etc/default/helloboard'
        self.defaults.parent.mkdir()
        self.defaults.write_text('HELLOBOARD_ARGS="--port 8123 --dashboard-only"\n')

    def script(self, name, *args):
        text = (ROOT / 'packaging/deb' / name).read_text()
        for prefix in ('/opt/', '/etc/', '/run/'):
            text = text.replace(prefix, f'{self.root}{prefix}')
        path = self.root / name
        path.write_text(text)
        return subprocess.run(['sh', str(path), *args], env=self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_first_install_starts_and_preserves_configuration(self):
        before = self.config.read_bytes(), self.defaults.read_bytes()
        self.assertEqual(self.script('postinst', 'configure').returncode, 0)
        self.assertEqual(before, (self.config.read_bytes(), self.defaults.read_bytes()))
        self.assertIn('deb-systemd-invoke start helloboard.service', self.calls())
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.config.parent.stat().st_mode & 0o777, 0o700)

    def test_upgrade_only_restarts_running_service_and_is_idempotent(self):
        self.env['DEB_TEST_EXISTING'] = '0'
        before = self.config.read_bytes(), self.defaults.read_bytes()
        for _ in range(2):
            self.assertEqual(self.script('postinst', 'configure', '0.1.0-1').returncode, 0)
        self.assertEqual(before, (self.config.read_bytes(), self.defaults.read_bytes()))
        self.assertEqual(self.calls().count('deb-systemd-invoke try-restart helloboard.service'), 2)
        self.assertNotIn('deb-systemd-invoke start ', self.calls())
        self.assertNotIn(' stop ', self.calls())

    def test_upgrade_does_not_stop_service_before_try_restart(self):
        self.assertEqual(self.script('prerm', 'upgrade', '0.1.1-1').returncode, 0)
        self.assertEqual(self.calls(), '')

    def test_upgrade_preserves_disabled_autostart(self):
        self.env.update(DEB_TEST_EXISTING='0', DEB_TEST_WAS_ENABLED='1')
        self.assertEqual(self.script('postinst', 'configure', '0.1.0-1').returncode, 0)
        self.assertNotIn('deb-systemd-helper enable ', self.calls())

    def test_remove_masks_only_through_package_helper(self):
        self.assertEqual(self.script('postrm', 'remove').returncode, 0)
        self.assertIn('deb-systemd-helper mask helloboard.service', self.calls())

    def test_removal_stops_service(self):
        self.assertEqual(self.script('prerm', 'remove').returncode, 0)
        self.assertIn('deb-systemd-invoke stop helloboard.service', self.calls())

    def test_install_refuses_source_installation(self):
        app = self.root / 'opt/helloboard/wifi.py'
        app.parent.mkdir(parents=True)
        app.write_text('existing source')
        self.assertNotEqual(self.script('preinst', 'install').returncode, 0)
        self.assertEqual(app.read_text(), 'existing source')
        self.assertEqual(self.script('preinst', 'upgrade').returncode, 0)

    def test_purge_does_not_delete_unknown_user_files(self):
        self.assertEqual(self.script('postrm', 'purge').returncode, 0)
        self.assertTrue(self.config.exists())  # dpkg, not this script, removes conffiles.
        self.assertIn('deb-systemd-helper purge helloboard.service', self.calls())

    def test_no_systemd_directory_does_not_start_service(self):
        (self.root / 'run/systemd/system').rmdir()
        self.assertEqual(self.script('postinst', 'configure').returncode, 0)
        self.assertNotIn('deb-systemd-invoke', self.calls())


if __name__ == '__main__':
    unittest.main()
