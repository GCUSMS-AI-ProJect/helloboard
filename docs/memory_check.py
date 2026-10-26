"""Measure a fresh read-only service's memory and six-client HTTP performance.

Linux only. No WiFi scans, settings writes or process signals are performed by
the tested service. A temporary preview child is stopped after each run.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import re
import socket
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def measure(arenas, requests_per_route):
    environment = dict(os.environ)
    environment.pop('MALLOC_ARENA_MAX', None)
    if arenas != 'default':
        environment['MALLOC_ARENA_MAX'] = arenas
    with socket.socket() as available:
        available.bind(('127.0.0.1', 0))
        port = available.getsockname()[1]
    process = subprocess.Popen([sys.executable, str(ROOT / 'wifi.py'), '--preview',
        '--host', '127.0.0.1', '--port', str(port), '--config', str(ROOT / 'wifi.example.yaml')], cwd=ROOT, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def memory():
        fields = {}
        for line in Path(f'/proc/{process.pid}/smaps_rollup').read_text().splitlines():
            key, _, value = line.partition(':')
            if key in ('Rss', 'Pss', 'Private_Dirty', 'Anonymous'):
                fields[key] = int(value.split()[0])
        return fields

    def get(path):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            started = time.perf_counter()
            connection.request('GET', path, headers={'Accept-Encoding': 'gzip'})
            response = connection.getresponse()
            response.read()
            assert response.status == 200, (path, response.status)
            return (time.perf_counter() - started) * 1000
        finally:
            connection.close()

    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Preview child exited before becoming ready')
            try:
                get('/api/system')
                break
            except OSError:
                time.sleep(.05)
        else:
            raise TimeoutError('Preview did not become ready')
        startup = memory()
        for name in ('system_status', 'wifi_config'):
            get('/' + name)
        for suffix in ('.css', '.js'):
            for asset in (ROOT / 'static').glob('*' + suffix):
                get('/static/' + asset.name)
        # Read active font references, ignoring old files left by upgrades.
        font_css = (ROOT / 'static/fonts/fonts.css').read_text()
        for filename in dict.fromkeys(re.findall(r'/static/(fonts/(?:inter-core|noto-sans-sc-core)\.[a-f0-9]+\.woff2)', font_css)):
            get('/static/' + filename)
        paths = ['/api/system', '/api/processes', '/system_status', '/wifi_config'] * requests_per_route
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=6) as clients:
            timings = list(clients.map(get, paths))
        elapsed = time.perf_counter() - started
        normal = memory()
        fallback = next((ROOT / 'static/fonts').glob('noto-sans-sc-fallback*.woff2'))
        get('/static/fonts/' + fallback.name)
        return dict(startup_kib=startup, normal_kib=normal, after_fallback_kib=memory(),
            request_p50_ms=statistics.median(timings),
            request_p95_ms=sorted(timings)[int(len(timings) * .95)],
            requests_per_second=len(paths) / elapsed)
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arenas', choices=('default', '2'), default='2')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--requests-per-route', type=int, default=600)
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('memory-report.json'))
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Memory measurements require Linux /proc')
    if args.runs < 1 or args.requests_per_route < 1:
        parser.error('runs and requests-per-route must be positive')
    results = [measure(args.arenas, args.requests_per_route) for _ in range(args.runs)]
    summary = {key: round(statistics.median(result[key] for result in results), 3)
               for key in ('request_p50_ms', 'request_p95_ms', 'requests_per_second')}
    for stage in ('startup_kib', 'normal_kib', 'after_fallback_kib'):
        summary[stage] = {key: statistics.median(result[stage][key] for result in results)
                          for key in results[0][stage]}
    report = dict(arenas=args.arenas, runs=args.runs, clients=6,
                  requests_per_run=args.requests_per_route * 4, summary=summary, measurements=results)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
