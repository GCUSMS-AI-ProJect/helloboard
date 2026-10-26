"""Read-only Linux telemetry with shared sampling and bounded in-memory history.

No configuration, process arguments, environment variables or credentials are read.
Counters need two samples; absent hardware is represented by None, never fake zero.
"""
from collections import deque
import copy
import logging
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import threading
import time
import uuid

from network import split_escaped


def read(path):
    try:
        return Path(path).read_text(errors='replace').strip().strip('\x00')
    except (OSError, ValueError):
        return ''


def number(path):
    try:
        return int(read(path))
    except ValueError:
        return None


def cpu_counters(text):
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if parts and re.fullmatch(r'cpu\d*', parts[0]):
            values = [int(v) for v in parts[1:9]]  # Guest time is already in user/nice.
            if len(values) >= 4:
                result[parts[0]] = (sum(values), values[3] + (values[4] if len(values) > 4 else 0))
    return result


def cpu_usage(previous, current):
    if not previous:
        return None
    total, idle = current[0] - previous[0], current[1] - previous[1]
    if total <= 0 or idle < 0:
        return None
    return round(max(0, min(100, 100 * (total - idle) / total)), 1)


def memory_info(text):
    values = {}
    for line in text.splitlines():
        key, _, value = line.partition(':')
        try:
            values[key] = int(value.split()[0]) * 1024
        except (ValueError, IndexError):
            continue
    total, available = values.get('MemTotal'), values.get('MemAvailable')
    used = max(0, total - available) if total is not None and available is not None else None
    swap_total, swap_free = values.get('SwapTotal'), values.get('SwapFree')
    return dict(total=total, available=available, used=used,
                percent=round(used / total * 100, 1) if total and used is not None else None,
                cached=values.get('Cached'), buffers=values.get('Buffers'),
                swap_total=swap_total,
                swap_used=max(0, swap_total - swap_free) if swap_total is not None and swap_free is not None else None)


def process_stat(text, page_size):
    # comm can contain whitespace and parentheses; the final ')' terminates it.
    start, end = text.find('('), text.rfind(')')
    fields = text[end + 2:].split()
    if start < 0 or end < start or len(fields) < 22:
        raise ValueError('Incomplete process stat')
    return {'name': text[start + 1:end], 'state': fields[0], 'parent': int(fields[1]),
            'flags': int(fields[6]), 'ticks': int(fields[11]) + int(fields[12]),
            'started': int(fields[19]), 'memory': max(0, int(fields[21])) * page_size}


def rate(current, previous, elapsed):
    if previous is None or elapsed <= 0 or current < previous:
        return None
    return round((current - previous) / elapsed, 1)


class SystemMetrics:
    INTERVAL = 2
    HISTORY_SECONDS = 600
    HISTORY_LIMIT = 300

    def __init__(self, proc='/proc', sys='/sys', *, monotonic=time.monotonic,
                 wall_time=time.time, command=None, disk_usage=shutil.disk_usage):
        self.proc, self.sys = Path(proc), Path(sys)
        self.monotonic, self.wall_time = monotonic, wall_time
        self.command = command or self._command
        self.disk_usage = disk_usage
        # Collection may wait on hardware/commands; readers only share the short
        # publication lock and always see a complete, independent snapshot.
        self.lock = threading.Lock()
        self.sample_lock = threading.Lock()
        self.published_processes = []
        self.previous_cpu, self.previous_net, self.previous_disk = {}, {}, {}
        self.previous_process = {}
        self.previous_time = None
        self.cached = None
        self.slow = {}
        self.slow_time = None
        self.processes = []
        self.process_count = None
        self.process_time = None
        self.process_cpu_total = None
        self.page_size = os.sysconf('SC_PAGE_SIZE') if hasattr(os, 'sysconf') else 4096
        self.history = deque(maxlen=self.HISTORY_LIMIT)
        self.history_id = uuid.uuid4().hex
        self.stop_event = threading.Event()
        self.sampler_thread = None

    @staticmethod
    def _command(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=0.8,
                                  check=False).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return ''

    def _sensors(self):
        temperatures = []
        for zone in (self.sys / 'class/thermal').glob('thermal_zone*'):
            value = number(zone / 'temp')
            if value is not None and -20000 <= value <= 150000:
                temperatures.append({'name': read(zone / 'type'), 'celsius': round(value / 1000, 1)})
        fans = []
        for hwmon in (self.sys / 'class/hwmon').glob('hwmon*'):
            for sensor in hwmon.glob('temp*_input'):
                value = number(sensor)
                if value is not None and -20000 <= value <= 150000:
                    temperatures.append(dict(name=read(hwmon / 'name') + ' ' + read(sensor.with_name(sensor.name.replace('_input', '_label'))),
                                             celsius=round(value / 1000, 1)))
            for sensor in hwmon.glob('fan*_input'):
                value = number(sensor)
                if value is not None:
                    fans.append({'name': read(hwmon / 'name'), 'rpm': value})
        cpu_temp = next((t['celsius'] for t in temperatures
                         if any(name in t['name'].lower() for name in ('cpu', 'coretemp', 'k10temp', 'package'))), None)
        return cpu_temp, fans, temperatures

    def _slow_sample(self, now):
        if self.slow_time is not None and now - self.slow_time < 15:
            return
        os_release = {}
        for line in read('/etc/os-release').splitlines():
            key, sep, value = line.partition('=')
            if sep:
                os_release[key] = value.strip('"')
        device = read(self.proc / 'device-tree/model') or read(self.sys / 'class/dmi/id/product_name')
        self.slow['device'] = dict(model=device or platform.machine(), hostname=platform.node(),
                                  os=os_release.get('PRETTY_NAME', platform.system()),
                                  kernel=platform.release(), architecture=platform.machine())
        mounts = []
        seen = set()
        for line in read(self.proc / 'self/mountinfo').splitlines():
            left, sep, right = line.partition(' - ')
            fields, filesystem = left.split(), right.split()
            if not sep or len(fields) < 5 or len(filesystem) < 2:
                continue
            if filesystem[0] not in {'ext4', 'ext3', 'ext2', 'vfat', 'exfat', 'btrfs', 'xfs', 'f2fs', 'ntfs3', 'ntfs', 'zfs', 'fuseblk'} and fields[4] != '/':
                continue
            mount = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
            if fields[2] in seen:
                continue
            try:
                usage = self.disk_usage(mount)
            except OSError:
                continue
            seen.add(fields[2])
            mounts.append(dict(mount=mount, filesystem=filesystem[0], source=filesystem[1],
                               total=usage.total, used=usage.used, available=usage.free,
                               percent=round(100 * usage.used / usage.total, 1) if usage.total else None))
        self.slow['volumes'] = sorted(mounts, key=lambda v: (v['mount'] != '/', v['mount']))
        try:
            addresses = json.loads(self.command(['ip', '-j', 'address', 'show']) or '[]')
            self.slow['addresses'] = {item['ifname']: [a['local'] for a in item.get('addr_info', [])
                                      if a.get('scope') == 'global'] for item in addresses}
        except (ValueError, KeyError, TypeError):
            self.slow['addresses'] = {}
        # Cached access-point information only: never ask NetworkManager to rescan.
        wireless = {}
        output = self.command(['nmcli', '-t', '-f', 'IN-USE,SSID,SIGNAL,DEVICE',
                               'device', 'wifi', 'list', '--rescan', 'no'])
        for line in output.splitlines():
            fields = split_escaped(line)
            if len(fields) == 4 and fields[0] == '*':
                try:
                    signal = max(0, min(100, int(fields[2])))
                except ValueError:
                    signal = None
                wireless[fields[3]] = dict(ssid=fields[1], signal=signal)
        self.slow['wireless'] = wireless
        services = []
        output = self.command(['systemctl', 'show', 'helloboard.service', 'NetworkManager.service',
                               '--property=Id,ActiveState,SubState,UnitFileState', '--no-pager'])
        for block in output.split('\n\n'):
            props = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
            if props.get('Id'):
                services.append(dict(name=props['Id'], state=props.get('ActiveState') or None,
                                     substate=props.get('SubState') or None,
                                     enabled=props.get('UnitFileState') or None))
        self.slow['services'] = services
        throttled = self.command(['vcgencmd', 'get_throttled'])
        match = re.fullmatch(r'throttled=(0x[\da-fA-F]+)', throttled)
        value = int(match[1], 16) if match else None
        self.slow['power'] = None if value is None else dict(
            undervoltage=bool(value & 1), frequency_capped=bool(value & 2),
            throttled=bool(value & 4), temperature_limited=bool(value & 8),
            historical=bool(value & 0xf0000))
        self.slow_time = now

    def _process_sample(self, now, cpu_total):
        if self.process_time is not None and now - self.process_time < 5:
            return
        processes, current = [], {}
        try:
            paths = list(self.proc.iterdir())
        except OSError:
            paths = None
        self.process_count = sum(p.name.isdigit() for p in paths) if paths is not None else None
        paths = paths or []
        total_delta = cpu_total - self.process_cpu_total if self.process_cpu_total is not None else 0
        for path in paths:
            if not path.name.isdigit():
                continue
            try:
                item = process_stat(read(path / 'stat'), self.page_size)
            except (ValueError, IndexError):
                continue
            key = (int(path.name), item['started'])
            previous = self.previous_process.get(key)
            item['cpu_percent'] = (round(max(0, min(100, (item['ticks'] - previous) / total_delta * 100)), 1)
                                   if previous is not None and total_delta > 0 else None)
            current[key] = item['ticks']
            processes.append(dict(pid=key[0], started=item['started'], name=item['name'],
                                  state=item['state'], flags=item['flags'],
                                  cpu_percent=item['cpu_percent'], memory=item['memory']))
        self.previous_process = current
        self.processes, self.process_time, self.process_cpu_total = processes, now, cpu_total

    def _volume_sample(self, now):
        # Mount discovery stays on the slow cadence. Capacity uses lightweight
        # statvfs on each normal sample so the usage rings reflect current data.
        if self.slow_time == now:
            return
        for volume in self.slow['volumes']:
            try:
                usage = self.disk_usage(volume['mount'])
                volume.update(total=usage.total, used=usage.used, available=usage.free,
                              percent=round(100 * usage.used / usage.total, 1) if usage.total else None)
            except OSError:
                volume.update(total=None, used=None, available=None, percent=None)

    def _sample(self, *, blocking=True):
        """Publish a sample; callers read through snapshot(), never a second copy."""
        if not self.sample_lock.acquire(blocking=blocking):
            return None
        try:
            now = self.monotonic()
            if self.cached is not None and now - self.previous_time < self.INTERVAL:
                return None
            sample = self._collect(now)
            # Detach slow metadata (especially volumes) before publishing: the
            # next collection may update its working data while readers run.
            published = copy.deepcopy(sample)
            with self.lock:
                self.cached = published
                # Process collection builds a new list with new records. Keep
                # that completed list alive until the next one is published;
                # process_snapshot() still gives each reader its own copy.
                self.published_processes = self.processes
                self.previous_time = now
                self._record_history()
        finally:
            self.sample_lock.release()

    def _collect(self, now):
        elapsed = now - self.previous_time if self.previous_time is not None else 0
        cpu = cpu_counters(read(self.proc / 'stat'))
        cores = [dict(name=name, percent=cpu_usage(self.previous_cpu.get(name), values))
                 for name, values in cpu.items() if name != 'cpu']
        memory = memory_info(read(self.proc / 'meminfo'))
        try:
            uptime = float(read(self.proc / 'uptime').split()[0])
        except (ValueError, IndexError):
            uptime = None
        try:
            load = [float(v) for v in read(self.proc / 'loadavg').split()[:3]]
        except ValueError:
            load = []
        policies = self.sys / 'devices/system/cpu/cpufreq'
        frequencies = [number(p / 'scaling_cur_freq') for p in policies.glob('policy*')]
        frequencies = [v for v in frequencies if v is not None]
        temperature, fans, temperatures = self._sensors()
        self._slow_sample(now)
        self._volume_sample(now)
        interfaces, net_now = [], {}
        for line in read(self.proc / 'net/dev').splitlines():
            name, sep, values = line.partition(':')
            name = name.strip()
            if not sep or name == 'lo':
                continue
            fields = values.split()
            if len(fields) < 16:
                continue
            rx, tx = int(fields[0]), int(fields[8])
            previous = self.previous_net.get(name)
            net_now[name] = (rx, tx)
            base = self.sys / 'class/net' / name
            interfaces.append(dict(name=name, state=read(base / 'operstate') or None,
                wireless=(base / 'wireless').exists(), addresses=self.slow['addresses'].get(name, []),
                **self.slow['wireless'].get(name, dict(ssid=None, signal=None)),
                rx_bytes=rx, tx_bytes=tx, rx_errors=int(fields[2]), tx_errors=int(fields[10]),
                rx_rate=rate(rx, previous[0] if previous else None, elapsed),
                tx_rate=rate(tx, previous[1] if previous else None, elapsed)))
        disks, disk_now = [], {}
        for line in read(self.proc / 'diskstats').splitlines():
            fields = line.split()
            if len(fields) < 14:
                continue
            name = fields[2]
            base = self.sys / 'class/block' / name
            if name.startswith(('loop', 'ram', 'zram')) or (base / 'partition').exists() or not (base / 'device').exists():
                continue
            rx, tx = int(fields[5]) * 512, int(fields[9]) * 512
            previous = self.previous_disk.get(name)
            disk_now[name] = (rx, tx)
            disks.append(dict(name=name, type=read(base / 'device/type') or None,
                read_bytes=rx, write_bytes=tx,
                read_rate=rate(rx, previous[0] if previous else None, elapsed),
                write_rate=rate(tx, previous[1] if previous else None, elapsed)))
        cpu_total = cpu.get('cpu', (0, 0))[0]
        self._process_sample(now, cpu_total)
        sample = dict(sampled_at=self.wall_time(), interval_seconds=self.INTERVAL, primary_mount='/',
            device=self.slow['device'], uptime_seconds=uptime,
            cpu=dict(percent=cpu_usage(self.previous_cpu.get('cpu'), cpu['cpu']) if 'cpu' in cpu else None,
                     cores=cores, count=len(cores) or os.cpu_count(), load=load,
                     frequency_mhz=round(sum(frequencies) / len(frequencies) / 1000) if frequencies else None),
            memory=memory, temperature_c=temperature, temperatures=temperatures, fans=fans,
            volumes=self.slow['volumes'], disks=disks, interfaces=interfaces,
            services=self.slow['services'], power=self.slow['power'], process_count=self.process_count,
            processes={key: [{k: item[k] for k in ('pid', 'name', 'cpu_percent', 'memory')}
                             for item in sorted(self.processes, key=sort, reverse=True)[:8]]
                       for key, sort in [('cpu', lambda p: p['cpu_percent'] or 0),
                                         ('memory', lambda p: p['memory'])]})
        self.previous_cpu, self.previous_net, self.previous_disk = cpu, net_now, disk_now
        return sample

    def _record_history(self):
        """Publish history under the same lock as its matching snapshot."""
        def total_rate(key):
            values = [item[key] for item in self.cached['interfaces'] if item[key] is not None]
            return round(sum(values), 1) if values else None
        self.history.append(dict(time=self.cached['sampled_at'],
            cpu=self.cached['cpu']['percent'], memory=self.cached['memory']['percent'],
            rx=total_rate('rx_rate'), tx=total_rate('tx_rate')))
        cutoff = self.cached['sampled_at'] - self.HISTORY_SECONDS
        while self.history and self.history[0]['time'] < cutoff:
            self.history.popleft()

    def snapshot(self, *, since=None, history_id=None):
        # A running collector owns the cadence; requests normally only read.
        with self.lock:
            needs_sample = (self.cached is None or not self.sampler_thread
                            or not self.sampler_thread.is_alive()
                            or self.monotonic() - self.previous_time > self.INTERVAL * 3)
            cold = self.cached is None
        if needs_sample:
            # Only the first ever sample must wait. During a slow refresh serve
            # the last completed sample rather than queue browser requests.
            self._sample(blocking=cold)
        with self.lock:
            # The generation changes after a service restart. Old cursors then
            # receive a full history, even if the wall clock moved backwards.
            incremental = history_id == self.history_id and since is not None
            history = [point.copy() for point in self.history
                       if not incremental or point['time'] > since]
            return dict(copy.deepcopy(self.cached), history=history,
                        history_id=self.history_id)

    def start(self):
        """Collect independently of browsers. Called only after the server binds."""
        with self.lock:
            if self.sampler_thread and self.sampler_thread.is_alive():
                return
            self.stop_event.clear()
            self.sampler_thread = threading.Thread(target=self._run, name='system-metrics', daemon=True)
            self.sampler_thread.start()

    def process_snapshot(self):
        """Reuse the six-second process sample; browser searches never walk /proc."""
        if self.cached is None:
            self.snapshot()
        with self.lock:
            return copy.deepcopy(self.published_processes)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self._sample()
                # Anchor the next deadline to the actual counter sample. Basing
                # it on loop entry can wake before the cache TTL and skip a tick.
                with self.lock:
                    delay = max(0.05, self.previous_time + self.INTERVAL - self.monotonic())
            except Exception as error:
                logging.error('System sampling unavailable (%s).', type(error).__name__)
                delay = self.INTERVAL
            if self.stop_event.wait(delay):
                break

    def stop(self):
        self.stop_event.set()
        if self.sampler_thread:
            self.sampler_thread.join(timeout=5)
