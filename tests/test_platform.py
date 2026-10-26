"""Host capability and desktop telemetry tests; never change real networking."""
from collections import namedtuple
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from configuration import ConfigStore
from controller import WifiController
from host_platform import DashboardController, ReadOnlyAuthenticator, detect_wifi, identity, make_authenticator, make_metrics
from network import NetworkError
from portable_metrics import PortableSystemMetrics
from process_control import ProcessManager
from tools.install_pam import install as install_pam
from wifi import create_app

WINDOWS = dict(family='Windows', name='Windows 11', distribution='', architecture='AMD64', wsl=False)
LINUX = dict(family='Linux', name='Ubuntu', distribution='ubuntu', architecture='aarch64', wsl=False)


class CapabilityTests(unittest.TestCase):
    def test_windows_does_not_probe_linux_commands_or_authenticate(self):
        run = Mock(side_effect=AssertionError('No Linux commands on Windows'))
        caps = detect_wifi(WINDOWS, run=run)
        self.assertFalse(caps['available'])
        with patch('host_platform.ctypes.util.find_library', side_effect=AssertionError('No PAM probe')):
            auth = make_authenticator(WINDOWS, 'desktop')
        with self.assertRaises(PermissionError): auth.verify('password')
        run.assert_not_called()

    def test_missing_stopped_unmanaged_and_explicit_missing_adapter(self):
        with patch('host_platform.shutil.which', return_value=None):
            caps = detect_wifi(LINUX, run=Mock(side_effect=AssertionError('No binary')))
            self.assertFalse(caps['available'])
        for output in [None, 'eth0:ethernet:connected', 'wlan0:wifi:unmanaged']:
            with self.subTest(output=output), patch('host_platform.shutil.which', return_value='/bin/nmcli'):
                self.assertFalse(detect_wifi(LINUX, run=lambda args: output)['available'])
        with patch('host_platform.shutil.which', return_value='/bin/nmcli'):
            self.assertFalse(detect_wifi(LINUX, 'wlan9', run=lambda args: 'wlan0:wifi:connected')['available'])
            self.assertTrue(detect_wifi(LINUX, run=lambda args: 'yes' if 'WIFI-PROPERTIES.AP' in args else 'wlan0:wifi:unavailable')['available'])

    def test_adapter_selection_permissions_and_ap_capability(self):
        def run(args):
            return 'yes' if 'WIFI-PROPERTIES.AP' in args else 'wlan0:wifi:disconnected\nwlp2s0:wifi:connected\neth0:ethernet:connected'
        with patch('host_platform.shutil.which', return_value='/bin/nmcli'), patch('host_platform.os.geteuid', return_value=0):
            caps = detect_wifi(LINUX, run=run)
            self.assertEqual(caps['interface'], 'wlp2s0')
            self.assertTrue(caps['manage'] and caps['ap'])
            self.assertEqual(detect_wifi(LINUX, 'wlan0', run=run)['interface'], 'wlan0')
        with patch('host_platform.shutil.which', return_value='/bin/nmcli'), patch('host_platform.os.geteuid', return_value=1000):
            caps = detect_wifi(LINUX, run=lambda args: 'no' if 'WIFI-PROPERTIES.AP' in args else 'wlp1s0:wifi:connected')
            self.assertTrue(caps['available'])
            self.assertFalse(caps['manage'] or caps['ap'])

    def test_dashboard_only_never_probes_network_manager(self):
        run = Mock(side_effect=AssertionError('Explicit read-only mode'))
        self.assertFalse(detect_wifi(LINUX, dashboard_only=True, run=run)['available'])
        run.assert_not_called()

    def test_linux_keeps_native_collector_and_missing_pam_is_readonly(self):
        self.assertEqual(type(make_metrics(LINUX)).__name__, 'SystemMetrics')
        with patch('host_platform.ctypes.util.find_library', return_value=None):
            self.assertIsInstance(make_authenticator(LINUX), ReadOnlyAuthenticator)
        with patch('host_platform.platform.system', return_value='Linux'), patch('host_platform.platform.release', return_value='6.1-microsoft-standard-WSL2'):
            self.assertTrue(identity()['wsl'])

    def test_imports_do_not_require_unix_only_python_apis(self):
        code = '''import os, sys
sys.modules['pwd'] = None
for name in ('geteuid', 'sysconf', 'fchmod'):
    if hasattr(os, name): delattr(os, name)
import wifi
from host_platform import ReadOnlyAuthenticator
assert not ReadOnlyAuthenticator('desktop').available
'''
        result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_pam_policy_uses_existing_distribution_policy_only(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.assertFalse(install_pam(directory))
            self.assertFalse((directory / 'helloboard').exists())
            (directory / 'system-auth').touch()
            self.assertTrue(install_pam(directory))
            self.assertIn('account include system-auth', (directory / 'helloboard').read_text())
            (directory / 'common-auth').touch()
            (directory / 'common-account').touch()
            self.assertTrue(install_pam(directory))
            self.assertIn('@include common-auth', (directory / 'helloboard').read_text())

    def test_adapter_without_ap_never_attempts_fallback_hotspot(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ConfigStore(Path(temp) / 'wifi.yaml')
            network = Mock()
            network.activate.side_effect = NetworkError('bad credentials')
            controller = WifiController(store, network, capabilities=dict(available=True, manage=True, ap=False))
            candidate = store.load()
            candidate.update(mode='lan', lan=dict(ssid='test', password='12345678'))
            controller.apply(candidate, persist=True)
            self.assertEqual(network.activate.call_count, 1)
            self.assertEqual(network.activate.call_args.args[0], 'lan')
            self.assertEqual(store.load()['mode'], 'ap')
            with self.assertRaises(NetworkError): controller.request(dict(mode='ap'))


Times = namedtuple('Times', 'user system idle')
Memory = namedtuple('Memory', 'total available')
Usage = namedtuple('Usage', 'total used free')
Part = namedtuple('Part', 'device mountpoint fstype opts')
Net = namedtuple('Net', 'bytes_recv bytes_sent errin errout')
Disk = namedtuple('Disk', 'read_bytes write_bytes')


class DesktopBackend:
    class Error(Exception):
        pass

    def __init__(self):
        self.step, self.started, self.denied = 0, 100.0, False
        self.process_calls = 0

    def cpu_times(self, *, percpu): return [Times(1 + self.step, 1, 8 + self.step)] * 2
    def cpu_count(self): return 2
    def virtual_memory(self): return Memory(1000, 600)
    def disk_partitions(self, **kwargs): return [Part('C:', 'C:\\', 'NTFS', 'rw'), Part('D:', 'D:\\', 'NTFS', 'rw')]
    def disk_usage(self, mount):
        if mount == 'D:\\': raise self.Error('locked')
        return Usage(10000, 2000 + self.step * 100, 8000 - self.step * 100)
    def boot_time(self): return 100.0
    def net_if_addrs(self): return {'Ethernet': [SimpleNamespace(family=2, address='192.168.1.20')]}
    def net_if_stats(self): return {'Ethernet': SimpleNamespace(isup=True)}
    def net_io_counters(self, **kwargs): return {'Ethernet': Net(1000 + self.step * 100, 2000 + self.step * 50, 0, 0)}
    def disk_io_counters(self, **kwargs): return {'PhysicalDrive0': Disk(4000 + self.step * 512, 5000)}
    def cpu_freq(self): raise NotImplementedError
    def win_service_get(self, name): raise self.Error('service missing')
    def process_iter(self, **kwargs):
        self.process_calls += 1
        if self.denied:
            return [SimpleNamespace(info=dict(pid=50, name='protected', create_time=None, cpu_times=None, memory_info=None))]
        return [SimpleNamespace(info=dict(pid=50, name='worker', create_time=self.started,
                cpu_times=Times(self.step, 0, 0), memory_info=SimpleNamespace(rss=256), status='running'))]
    def pids(self): return [0, 4, 50]


class DesktopMetricsTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.backend = DesktopBackend()
        self.metrics = PortableSystemMetrics(host=WINDOWS, backend=self.backend,
            monotonic=lambda: self.now, wall_time=lambda: self.now)

    def advance(self, seconds=2):
        self.now += seconds
        self.backend.step += 1
        return self.metrics.snapshot()

    def test_desktop_rates_history_system_drive_and_missing_hardware(self):
        first = self.metrics.snapshot()
        self.assertIsNone(first['cpu']['percent'])
        self.assertIsNone(first['interfaces'][0]['rx_rate'])
        self.assertEqual(first['primary_mount'], 'C:\\')
        self.assertEqual(first['cpu']['count'], 2)
        self.assertEqual(first['memory']['percent'], 40)
        self.assertEqual(first['process_count'], 3)
        self.assertEqual(len(first['volumes']), 1)
        self.assertIsNone(first['temperature_c'])
        self.assertIsNone(first['power'])
        self.assertEqual(first['services'], [])
        second = self.advance()
        self.assertEqual(second['cpu']['percent'], 50)
        self.assertEqual(second['interfaces'][0]['rx_rate'], 50)
        self.assertEqual(second['disks'][0]['read_rate'], 256)
        self.assertEqual(second['volumes'][0]['used'], 2100)
        self.assertEqual(len(second['history']), 2)
        delta = self.metrics.snapshot(since=first['sampled_at'], history_id=first['history_id'])
        self.assertEqual(delta['history'], second['history'][1:])
        self.assertNotIn('cpu_times', str(second))

    def test_process_sampling_cpu_normalization_reuse_and_denied_access(self):
        self.metrics.snapshot()
        self.advance()
        self.assertEqual(self.backend.process_calls, 1)
        self.advance(4)
        self.assertEqual(self.backend.process_calls, 2)
        self.assertEqual(self.metrics.process_snapshot()[0]['cpu_percent'], 16.7)
        self.backend.started = 999.0
        self.advance(6)
        self.assertIsNone(self.metrics.process_snapshot()[0]['cpu_percent'])
        self.backend.denied = True
        self.advance(6)
        self.assertEqual(self.metrics.process_snapshot(), [])

    def test_counter_reset_stays_unknown(self):
        self.metrics.snapshot()
        self.advance()
        self.backend.step = -2
        self.now += 2
        self.assertIsNone(self.metrics.snapshot()['interfaces'][0]['rx_rate'])

    def test_windows_routes_navigation_and_mutations_are_readonly(self):
        caps = detect_wifi(WINDOWS)
        controller = DashboardController(caps)
        with patch('process_control.platform.system', return_value='Windows'):
            manager = ProcessManager(self.metrics, allow_control=False)
            with patch.object(manager, '_ancestors', side_effect=AssertionError('No /proc access')):
                self.assertFalse(manager.snapshot()['items'][0]['selectable'])
            app = create_app(controller, host=WINDOWS, metrics=self.metrics, processes=manager,
                             authenticator=ReadOnlyAuthenticator('desktop'))
            client = app.test_client()
            page = client.get('/system_status')
            self.assertEqual(page.status_code, 200)
            self.assertNotIn('href="/wifi_config"', page.text)
            self.assertEqual(client.get('/wifi_config').status_code, 302)
            data = client.get('/api/capabilities').json
            self.assertEqual(data['host']['family'], 'Windows')
            self.assertFalse(data['wifi']['available'] or data['processes']['available'])
            self.assertEqual(client.get('/api/system').status_code, 200)
            self.assertEqual(client.get('/api/processes').status_code, 200)
            with client.session_transaction() as session: headers = {'X-CSRF-Token': session['csrf']}
            self.assertEqual(client.post('/api/connect', json={'mode':'ap'}, headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/scan', json={}, headers=headers).status_code, 503)
            self.assertEqual(client.post('/api/authorize', json={'username':'desktop','password':'x'}, headers=headers).status_code, 403)
            with self.assertRaises(PermissionError): manager.terminate(dict(action='kill', targets=[dict(pid=50,started=100)]))


if __name__ == '__main__':
    unittest.main()
