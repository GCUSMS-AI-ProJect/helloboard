"""Measure snapshot reads during a delayed background collection (read-only).

The 250ms delay is injected; this is a contention benchmark, not page-load timing.
No WiFi scans, configuration writes or process signals are performed.
"""
import argparse
import json
from pathlib import Path
import statistics
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from system_metrics import SystemMetrics


def measure(delay):
    now = [100.0]
    metrics = SystemMetrics(monotonic=lambda: now[0], command=lambda args: '')
    first = metrics.snapshot()
    entered = threading.Event()
    original = metrics._slow_sample
    failures = []

    def slow(sample_time):
        entered.set()
        time.sleep(delay)
        return original(sample_time)

    def collect():
        try:
            metrics._sample()
        except Exception as error:
            failures.append(error)

    metrics._slow_sample = slow
    now[0] += 16
    worker = threading.Thread(target=collect)
    metrics.sampler_thread = worker
    worker.start()
    try:
        assert entered.wait(5), 'Collector did not reach the delayed stage'
        started = time.perf_counter()
        snapshot = metrics.snapshot()
        elapsed = (time.perf_counter() - started) * 1000
    finally:
        worker.join(5)
    assert not worker.is_alive() and not failures, failures
    current = metrics.snapshot()
    assert current['sampled_at'] > first['sampled_at']
    return elapsed, snapshot['sampled_at'] == first['sampled_at']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--delay', type=float, default=.25)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('refresh-report.json'))
    args = parser.parse_args()
    if args.runs < 1 or not 0 < args.delay <= 5:
        parser.error('runs must be positive; delay must be within (0, 5] seconds')
    results = [measure(args.delay) for _ in range(args.runs)]
    median = statistics.median(result[0] for result in results)
    if not args.baseline:
        assert all(previous for _, previous in results), 'Reader waited for collection'
        assert median < args.delay * 500, 'Snapshot read still waits for the delayed stage'
    report = dict(condition='Read-only Linux collector; one optional stage deliberately delayed',
                  injected_delay_ms=args.delay * 1000, runs=args.runs,
                  refresh_wait_ms=[round(value, 3) for value, _ in results],
                  median_ms=round(median, 3),
                  read_previous_complete_snapshot=all(previous for _, previous in results))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
