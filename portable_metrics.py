"""Read-only desktop telemetry; identical API/history contract to Linux.

psutil is imported only when this collector is selected. Optional sensors,
services and access-denied processes never block the remaining measurements.
"""
import copy
import ipaddress
import os
import platform
import socket

from system_metrics import SystemMetrics, cpu_usage, rate


class PortableSystemMetrics(SystemMetrics):
    def __init__(self, *, host, backend=None, **kwargs):
        super().__init__(**kwargs)
        if backend is None:
            try:
                import psutil as backend
            except ImportError:
                raise RuntimeError('请先执行 python -m pip install -r requirements.txt 安装系统采集依赖。') from None
        self.backend, self.host = backend, host
        self.primary_mount = os.environ.get('SystemDrive', 'C:') + '\\' if host['family'] == 'Windows' else '/'

    def optional(self, name, default=None, *args, **kwargs):
        fn = getattr(self.backend, name, None)
        if fn is None:
            return default
        try:
            return fn(*args, **kwargs)
        except (OSError, self.backend.Error, NotImplementedError):
            return default

    @staticmethod
    def cpu_counter(value):
        values = value._asdict()
        total = sum(v for key, v in values.items() if key not in ('guest', 'guest_nice'))
        return total, values.get('idle', 0) + values.get('iowait', 0)

    def _slow_sample(self, now):
        if self.slow_time is not None and now - self.slow_time < 15:
            return
        self.slow['device'] = dict(model=platform.processor() or self.host['architecture'],
            hostname=platform.node(), os=self.host['name'], kernel=platform.release(),
            architecture=self.host['architecture'])
        volumes, seen = [], set()
        for part in self.optional('disk_partitions', [], all=False):
            if part.mountpoint in seen or not part.fstype or 'cdrom' in part.opts:
                continue
            usage = self.optional('disk_usage', None, part.mountpoint)
            if usage is None or not usage.total:
                continue
            seen.add(part.mountpoint)
            volumes.append(dict(mount=part.mountpoint, source=part.device, filesystem=part.fstype,
                total=usage.total, used=usage.used, available=usage.free,
                percent=round(100 * usage.used / usage.total, 1)))
        self.slow['volumes'] = sorted(volumes, key=lambda v: (v['mount'] != self.primary_mount, v['mount']))
        self.slow['addresses'] = {}
        for name, entries in self.optional('net_if_addrs', {}).items():
            self.slow['addresses'][name] = [a.address for a in entries if a.family in (socket.AF_INET, socket.AF_INET6)]
        self.slow['services'] = []
        if self.host['family'] == 'Windows':
            for name in ('HelloBoard', 'WlanSvc'):
                try:
                    service = self.backend.win_service_get(name).as_dict()
                except (AttributeError, OSError, self.backend.Error):
                    continue
                state = {'running': 'active', 'stopped': 'inactive', 'start_pending': 'activating',
                         'stop_pending': 'deactivating'}.get(service.get('status'), 'unknown')
                enabled = {'automatic': 'enabled', 'disabled': 'disabled', 'manual': 'manual'}.get(service.get('start_type'))
                self.slow['services'].append(dict(name=service.get('display_name') or name,
                                                  state=state, substate=None, enabled=enabled))
        self.slow_time = now

    def _process_sample(self, now, cpu_total=None):
        if self.process_time is not None and now - self.process_time < 5:
            return
        elapsed = now - self.process_time if self.process_time is not None else 0
        count = self.backend.cpu_count() or 1
        items, current = [], {}
        attrs = ['pid', 'name', 'create_time', 'cpu_times', 'memory_info', 'status']
        for proc in self.backend.process_iter(attrs=attrs, ad_value=None):
            try:
                item = proc.info
                if any(item.get(key) is None for key in ('create_time', 'cpu_times', 'memory_info')):
                    continue
                started = int(item['create_time'] * 1_000_000)
                key = (item['pid'], started)
                seconds = item['cpu_times'].user + item['cpu_times'].system
                # CPU needs sub-second precision before conversion to percent.
                previous = self.previous_process.get(key)
                value = (round(max(0, min(100, (seconds - previous) / elapsed / count * 100)), 1)
                         if previous is not None and elapsed > 0 and seconds >= previous else None)
                current[key] = seconds
                items.append(dict(pid=key[0], started=started, name=item['name'] or str(key[0]),
                    state=item['status'], flags=0, memory=item['memory_info'].rss, cpu_percent=value))
            except (OSError, self.backend.Error):
                continue
        pids = self.optional('pids')
        self.process_count = len(pids) if pids is not None else len(items)
        self.processes, self.previous_process, self.process_time = items, current, now

    def _sample(self):
        with self.lock:
            now = self.monotonic()
            if self.cached is not None and now - self.previous_time < self.INTERVAL:
                return copy.deepcopy(self.cached)
            elapsed = now - self.previous_time if self.previous_time is not None else 0
            counters = self.backend.cpu_times(percpu=True)
            cpu = {f'cpu{i}': self.cpu_counter(c) for i, c in enumerate(counters)}
            cpu['cpu'] = tuple(sum(v[j] for v in cpu.values()) for j in (0, 1))
            cores = [dict(name=k, percent=cpu_usage(self.previous_cpu.get(k), v)) for k, v in cpu.items() if k != 'cpu']
            memory = self.backend.virtual_memory()
            swap = self.optional('swap_memory')
            used = max(0, memory.total - memory.available)
            self._slow_sample(now)
            self.disk_usage = self.backend.disk_usage
            self._volume_sample(now)
            boot = self.optional('boot_time')
            net_now, interfaces = {}, []
            states = self.optional('net_if_stats', {})
            for name, stats in (self.optional('net_io_counters', {}, pernic=True) or {}).items():
                addresses = self.slow['addresses'].get(name, [])
                if addresses and all(ipaddress.ip_address(a.split('%')[0]).is_loopback for a in addresses):
                    continue
                if name.lower() in ('lo', 'lo0', 'loopback pseudo-interface 1'):
                    continue
                rx, tx = stats.bytes_recv, stats.bytes_sent
                previous = self.previous_net.get(name)
                net_now[name] = (rx, tx)
                state = states.get(name)
                interfaces.append(dict(name=name, state=('up' if state.isup else 'down') if state else None,
                    wireless=None, addresses=addresses, ssid=None, signal=None,
                    rx_bytes=rx, tx_bytes=tx, rx_errors=stats.errin, tx_errors=stats.errout,
                    rx_rate=rate(rx, previous[0] if previous else None, elapsed),
                    tx_rate=rate(tx, previous[1] if previous else None, elapsed)))
            disks, disk_now = [], {}
            for name, stats in (self.optional('disk_io_counters', {}, perdisk=True) or {}).items():
                rx, tx = stats.read_bytes, stats.write_bytes
                previous = self.previous_disk.get(name)
                disk_now[name] = (rx, tx)
                disks.append(dict(name=name, type=None, read_bytes=rx, write_bytes=tx,
                    read_rate=rate(rx, previous[0] if previous else None, elapsed),
                    write_rate=rate(tx, previous[1] if previous else None, elapsed)))
            temperatures = [dict(name=sensor.label or name, celsius=sensor.current)
                for name, entries in self.optional('sensors_temperatures', {}).items() for sensor in entries
                if sensor.current is not None]
            temperature = next((t['celsius'] for t in temperatures
                                if any(k in t['name'].lower() for k in ('cpu', 'core', 'package'))), None)
            fans = [dict(name=fan.label or name, rpm=fan.current)
                for name, entries in self.optional('sensors_fans', {}).items() for fan in entries if fan.current is not None]
            self._process_sample(now)
            self.cached = dict(sampled_at=self.wall_time(), interval_seconds=self.INTERVAL,
                primary_mount=self.primary_mount, device=self.slow['device'],
                uptime_seconds=max(0, self.wall_time() - boot) if boot is not None else None,
                cpu=dict(percent=cpu_usage(self.previous_cpu.get('cpu'), cpu['cpu']), cores=cores,
                    count=len(cores), load=[], frequency_mhz=None),
                memory=dict(total=memory.total, available=memory.available, used=used,
                    percent=round(100 * used / memory.total, 1) if memory.total else None,
                    cached=getattr(memory, 'cached', None), buffers=getattr(memory, 'buffers', None),
                    swap_total=swap.total if swap else None, swap_used=swap.used if swap else None),
                temperature_c=temperature, temperatures=temperatures, fans=fans, power=None,
                volumes=self.slow['volumes'], disks=disks, interfaces=interfaces,
                services=self.slow['services'], process_count=self.process_count,
                processes={key: [{k: item[k] for k in ('pid', 'name', 'cpu_percent', 'memory')}
                    for item in sorted(self.processes, key=sort, reverse=True)[:8]]
                    for key, sort in [('cpu', lambda p: p['cpu_percent'] or 0), ('memory', lambda p: p['memory'])]})
            frequency = self.optional('cpu_freq')
            self.cached['cpu']['frequency_mhz'] = frequency.current if frequency and frequency.current else None
            self.previous_cpu, self.previous_net, self.previous_disk = cpu, net_now, disk_now
            self.previous_time = now
            self._record_history()
            return copy.deepcopy(self.cached)
