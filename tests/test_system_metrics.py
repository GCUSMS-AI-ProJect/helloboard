"""Exercise telemetry arithmetic and unavailable hardware using a fake Linux tree."""
from collections import namedtuple
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from system_metrics import SystemMetrics, cpu_counters, cpu_usage, memory_info, process_stat, rate
from wifi import create_app


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc, self.sys = self.root / 'proc', self.root / 'sys'
        self.now = 100.0
        self.commands = []
        self.write('proc/stat', 'cpu 100 20 30 400 10 5 5 0 900 800\ncpu0 50 10 15 200 5 2 3 0\ncpu1 50 10 15 200 5 3 2 0')
        self.write('proc/meminfo', 'MemTotal: 1000 kB\nMemAvailable: 700 kB\nCached: 300 kB\nBuffers: 20 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB')
        self.write('proc/uptime', '120.5 35.0')
        self.write('proc/loadavg', '0.20 0.10 0.05 1/50 2')
        self.write('proc/self/mountinfo', '1 2 179:2 / / rw - ext4 /dev/mmcblk0p2 rw\n2 2 0:1 / /proc rw - proc proc rw')
        self.write('proc/net/dev', 'wlan0: 1000 5 1 0 0 0 0 0 2000 5 2 0 0 0 0 0')
        self.write('sys/class/net/wlan0/operstate', 'up')
        (self.sys / 'class/net/wlan0/wireless').mkdir()
        self.write('sys/class/block/mmcblk0/device/type', 'SD')
        self.write('sys/class/block/mmcblk0p2/partition', '2')
        self.write('proc/diskstats', '179 0 mmcblk0 10 0 20 1 5 0 30 1 0 1 1\n179 2 mmcblk0p2 10 0 20 1 5 0 30 1 0 1 1\n252 0 zram0 0 0 99 0 0 0 99 0 0 0 0')
        self.write('proc/123/stat', self.stat('a (worker) name', 20, 100, 3))
        Usage = namedtuple('Usage', 'total used free')
        self.metrics = SystemMetrics(self.proc, self.sys, monotonic=lambda: self.now,
            wall_time=lambda: self.now + 1000, command=self.command,
            disk_usage=lambda mount: Usage(10000, 2000, 7000))
        self.metrics.page_size = 16384

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def command(self, args):
        self.commands.append(args)
        if args[0] == 'ip':
            return '[{"ifname":"wlan0","addr_info":[{"local":"192.168.1.3","scope":"global"}]}]'
        if args[0] == 'nmcli':
            return '*:My\\:WiFi:75:wlan0\n :Other:10:wlan0'
        if args[0] == 'vcgencmd':
            return 'throttled=0x50005'
        if args[0] == 'systemctl':
            return 'Id=helloboard.service\nActiveState=active\nSubState=running\nUnitFileState=enabled'
        raise AssertionError(args)

    @staticmethod
    def stat(name, ticks, start, pages):
        fields = ['S'] + ['0'] * 21
        fields[11], fields[12], fields[19], fields[21] = str(ticks), '0', str(start), str(pages)
        return '123 (' + name + ') ' + ' '.join(fields)

    def test_cpu_excludes_duplicate_guest_and_counts_iowait_as_idle(self):
        previous = cpu_counters('cpu 100 0 0 100 50 0 0 0 999 999')['cpu']
        current = cpu_counters('cpu 110 0 0 140 100 0 0 0 9999 9999')['cpu']
        self.assertEqual(previous, (250, 150))
        self.assertEqual(cpu_usage(previous, current), 10)
        self.assertIsNone(cpu_usage(None, current))
        self.assertIsNone(cpu_usage(current, previous))

    def test_memory_is_total_minus_available_and_zero_swap_is_valid(self):
        mem = memory_info('MemTotal: 1000 kB\nMemAvailable: 700 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB')
        self.assertEqual(mem['used'], 300 * 1024)
        self.assertEqual(mem['percent'], 30)
        self.assertEqual(mem['swap_used'], 0)
        self.assertIsNone(memory_info('')['percent'])

    def test_first_sample_is_unknown_for_rates_then_computes_true_deltas(self):
        first = self.metrics.snapshot()
        self.assertIsNone(first['cpu']['percent'])
        self.assertIsNone(first['interfaces'][0]['rx_rate'])
        self.assertIsNone(first['disks'][0]['read_rate'])
        self.now += 2
        self.write('proc/stat', 'cpu 130 20 30 470 10 5 5 0\ncpu0 80 10 15 270 5 2 3 0')
        self.write('proc/net/dev', 'wlan0: 1600 5 1 0 0 0 0 0 2200 5 2 0 0 0 0 0')
        self.write('proc/diskstats', '179 0 mmcblk0 10 0 24 1 5 0 32 1 0 1 1')
        second = self.metrics.snapshot()
        self.assertEqual(second['cpu']['percent'], 30)
        self.assertEqual(second['interfaces'][0]['rx_rate'], 300)
        self.assertEqual(second['interfaces'][0]['tx_rate'], 100)
        self.assertEqual(second['disks'][0]['read_rate'], 1024)
        self.assertEqual(second['disks'][0]['write_rate'], 512)
        self.assertEqual(len(second['disks']), 1)  # No partition / zram double count.

    def test_counter_reset_is_unknown_and_does_not_produce_negative_rates(self):
        self.assertIsNone(rate(1, 100, 2))
        self.assertIsNone(rate(5, None, 2))
        self.assertEqual(rate(0, 0, 2), 0)

    def test_processes_handle_parentheses_16k_pages_and_pid_reuse(self):
        first = self.metrics.snapshot()
        proc = first['processes']['memory'][0]
        self.assertEqual(proc['name'], 'a (worker) name')
        self.assertEqual(proc['memory'], 3 * 16384)
        self.now += 6
        self.write('proc/stat', 'cpu 200 20 30 500 10 5 5 0')
        self.write('proc/123/stat', self.stat('a (worker) name', 30, 100, 4))
        second = self.metrics.snapshot()['processes']['cpu'][0]
        self.assertEqual(second['cpu_percent'], 5)
        self.now += 6
        self.write('proc/123/stat', self.stat('replacement', 900, 999, 2))
        third = self.metrics.snapshot()['processes']['cpu'][0]
        self.assertIsNone(third['cpu_percent'])
        self.assertNotIn('ticks', third)
        self.assertNotIn('started', third)

    def test_missing_sensors_and_failed_optional_commands_are_not_fake_zero(self):
        self.metrics.command = lambda args: ''
        data = self.metrics.snapshot()
        self.assertIsNone(data['temperature_c'])
        self.assertEqual(data['fans'], [])
        self.assertIsNone(data['power'])
        self.assertEqual(data['services'], [])
        self.assertEqual(data['interfaces'][0]['addresses'], [])
        self.assertIsNone(data['interfaces'][0]['ssid'])

    def test_real_sensors_and_power_flags(self):
        self.write('sys/class/thermal/thermal_zone0/type', 'cpu-thermal')
        self.write('sys/class/thermal/thermal_zone0/temp', '46321')
        self.write('sys/class/hwmon/hwmon9/name', 'pwmfan')
        self.write('sys/class/hwmon/hwmon9/fan1_input', '4020')
        data = self.metrics.snapshot()
        self.assertEqual(data['temperature_c'], 46.3)
        self.assertEqual(data['fans'][0]['rpm'], 4020)
        self.assertTrue(data['power']['undervoltage'])
        self.assertTrue(data['power']['throttled'])
        self.assertFalse(data['power']['frequency_capped'])
        self.assertTrue(data['power']['historical'])

    def test_cache_is_shared_without_mutation_and_slow_commands_are_not_polled(self):
        first = self.metrics.snapshot()
        first['memory']['used'] = -1
        calls = len(self.commands)
        self.now += 1
        again = self.metrics.snapshot()
        self.assertNotEqual(again['memory']['used'], -1)
        self.assertEqual(first['sampled_at'], again['sampled_at'])
        self.now += 1
        self.metrics.snapshot()
        self.assertEqual(len(self.commands), calls)
        self.now += 16
        self.metrics.snapshot()
        self.assertGreater(len(self.commands), calls)
        wireless = next(c for c in self.commands if c[0] == 'nmcli')
        self.assertEqual(wireless[-2:], ['--rescan', 'no'])
        data = self.metrics.snapshot()
        self.assertEqual(data['interfaces'][0]['ssid'], 'My:WiFi')
        self.assertEqual(data['interfaces'][0]['signal'], 75)
        self.assertEqual(data['volumes'][0]['available'], 7000)  # Reserved bytes retained.

    def test_process_list_reuses_sample_and_exposes_stable_identity_separately(self):
        self.metrics.snapshot()
        with self.metrics.lock:
            self.assertEqual(self.metrics.processes[0]['started'],100)
        with patch.object(self.metrics,'_process_sample',side_effect=AssertionError('Unexpected scan')):
            processes=self.metrics.process_snapshot()
            self.assertEqual(processes[0]['started'],100)
            processes[0]['name']='modified by caller'
            self.assertNotEqual(self.metrics.process_snapshot()[0]['name'],'modified by caller')

    def test_readers_do_not_wait_or_observe_partial_collection(self):
        first = self.metrics.snapshot()
        first_processes = self.metrics.process_snapshot()
        self.now += 8  # Also exercise the stale-sampler fallback path.
        Usage = namedtuple('Usage', 'total used free')
        self.metrics.disk_usage = lambda mount: Usage(10000, 5000, 4000)
        self.write('proc/123/stat', self.stat('new worker', 30, 100, 4))
        entered, release, read_done = threading.Event(), threading.Event(), threading.Event()
        original = self.metrics._process_sample
        results, failures = [], []

        def delayed_process_sample(*args):
            original(*args)  # Working volume/process data has already changed.
            entered.set()
            if not release.wait(3):
                raise TimeoutError('Test did not release the collector')

        def collect():
            try:
                self.metrics._sample()
            except Exception as error:
                failures.append(error)

        def read_snapshot():
            try:
                results.append(self.metrics.snapshot(since=first['sampled_at'],
                    history_id=first['history_id']))
                results.append(self.metrics.process_snapshot())
            except Exception as error:
                failures.append(error)
            finally:
                read_done.set()

        with patch.object(self.metrics, '_process_sample', delayed_process_sample):
            collector = threading.Thread(target=collect)
            collector.start()
            reader = None
            try:
                self.assertTrue(entered.wait(2))
                reader = threading.Thread(target=read_snapshot)
                reader.start()
                self.assertTrue(read_done.wait(1), 'Reader waited for unfinished collection')
                self.assertEqual(results[0]['sampled_at'], first['sampled_at'])
                self.assertEqual(results[0]['volumes'], first['volumes'])
                self.assertEqual(results[0]['history'], [])
                self.assertEqual(results[1], first_processes)
            finally:
                release.set()
                collector.join(3)
                if reader:
                    reader.join(3)
        self.assertEqual(failures, [])
        after = self.metrics.snapshot(since=first['sampled_at'], history_id=first['history_id'])
        self.assertEqual(after['volumes'][0]['percent'], 50)
        self.assertEqual(len(after['history']), 1)
        self.assertEqual(after['history'][0]['time'], after['sampled_at'])
        self.assertEqual(self.metrics.process_snapshot()[0]['name'], 'new worker')

    def test_failed_collection_preserves_published_data_and_releases_collector(self):
        first = self.metrics.snapshot()
        first_processes = self.metrics.process_snapshot()
        self.now += 2

        def failed_collect(now):
            self.metrics.slow['volumes'][0]['used'] = -1
            self.metrics.processes = []
            raise OSError('Optional device disconnected')

        with patch.object(self.metrics, '_collect', failed_collect):
            with self.assertRaises(OSError):
                self.metrics._sample()
        self.assertEqual(self.metrics.cached['volumes'], first['volumes'])
        self.assertEqual(self.metrics.process_snapshot(), first_processes)
        self.assertEqual(list(self.metrics.history), first['history'])
        self.assertEqual(self.metrics.previous_time, self.now - 2)
        self.assertTrue(self.metrics.sample_lock.acquire(blocking=False))
        self.metrics.sample_lock.release()
        self.assertGreater(self.metrics.snapshot()['sampled_at'], first['sampled_at'])

    def test_volume_capacity_updates_on_normal_sampling_without_extra_commands(self):
        self.metrics.snapshot()
        calls=len(self.commands)
        Usage=namedtuple('Usage','total used free')
        self.metrics.disk_usage=lambda mount: Usage(10000,5000,4000)
        self.now+=2
        volume=self.metrics.snapshot()['volumes'][0]
        self.assertEqual((volume['percent'],volume['used'],volume['available']),(50,5000,4000))
        self.assertEqual(len(self.commands),calls)
        def unavailable(mount): raise OSError('Detached volume')
        self.metrics.disk_usage=unavailable
        self.now+=2
        volume=self.metrics.snapshot()['volumes'][0]
        self.assertIsNone(volume['percent'])
        self.assertIsNone(volume['total'])

    def test_history_survives_new_clients_and_returns_only_new_samples(self):
        first = self.metrics.snapshot()
        self.now += 2
        second = self.metrics.snapshot()
        self.assertEqual(len(second['history']), 2)
        self.assertIsNone(second['history'][0]['cpu'])
        # Returning a response must not let clients mutate stored history.
        first['history'][0]['memory'] = -1
        self.assertEqual(second['history'][0]['memory'], 30)
        delta = self.metrics.snapshot(since=first['sampled_at'], history_id=first['history_id'])
        self.assertEqual(delta['history'], second['history'][1:])
        self.assertEqual(self.metrics.snapshot(since=second['sampled_at'], history_id=first['history_id'])['history'], [])
        self.assertEqual(self.metrics.snapshot()['history'], second['history'])
        # An old cursor must not suppress the new service's history.
        reset = self.metrics.snapshot(since=999999, history_id='previous-service')
        self.assertEqual(reset['history'], second['history'])

    def test_history_is_bounded_and_does_not_fill_missing_samples(self):
        for _ in range(305):
            self.metrics.snapshot()
            self.now += 2
        history = self.metrics.snapshot()['history']
        self.assertEqual(len(history), 300)
        self.assertEqual(history[-1]['time'] - history[0]['time'], 598)
        self.now += 700
        after_gap = self.metrics.snapshot()['history']
        self.assertEqual(len(after_gap), 1)
        self.assertEqual(after_gap[0]['time'], self.now + 1000)

    def test_background_sampler_collects_without_requests_and_stops_cleanly(self):
        # A short interval exercises the actual loop without slowing the suite.
        self.metrics.INTERVAL = 0.02
        self.metrics.monotonic = time.monotonic
        ready = threading.Event()
        original = self.metrics._sample
        def sample():
            result = original()
            if len(self.metrics.history) >= 3:
                ready.set()
            return result
        self.metrics._sample = sample
        self.metrics.start()
        worker = self.metrics.sampler_thread
        self.metrics.start()
        self.assertIs(worker, self.metrics.sampler_thread)
        try:
            self.assertTrue(ready.wait(2), 'Sampler did not collect without requests')
        finally:
            self.metrics.stop()
        self.assertFalse(worker.is_alive())
        self.assertGreaterEqual(len(self.metrics.history), 3)

    def test_history_api_new_browser_incremental_and_invalid_cursor(self):
        class Auth:
            username = 'ubuntu'
        app = create_app(object(), authenticator=Auth(), metrics=self.metrics)
        first = app.test_client().get('/api/system').json
        self.now += 4
        other_browser = app.test_client().get('/api/system').json
        self.assertEqual(other_browser['history'][0], first['history'][0])
        self.assertEqual(len(other_browser['history']), 2)
        client = app.test_client()
        delta = client.get('/api/system', query_string=dict(since=first['sampled_at'], history_id=first['history_id'])).json
        self.assertEqual(delta['history'], other_browser['history'][1:])
        for value in ['bad', 'NaN', 'inf', '-1']:
            self.assertEqual(client.get('/api/system', query_string=dict(since=value)).status_code, 400)

    def test_dashboard_api_is_read_only_and_contains_no_wifi_credentials(self):
        class Auth:
            username = 'ubuntu'
        # A controller with no methods: any WiFi access would fail this test.
        client = create_app(object(), authenticator=Auth(), metrics=self.metrics).test_client()
        for route in ['/', '/system_status', '/wifi_config']:
            self.assertEqual(client.get(route).status_code, 200)
        response = client.get('/api/system')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn('password', response.get_data(as_text=True).lower())
        self.assertNotIn('csrf_token', response.json)
        self.assertEqual(client.post('/api/system', json={}).status_code, 403)
        self.assertEqual(client.get('/api/system', headers={'Host':'public.example.com'}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
