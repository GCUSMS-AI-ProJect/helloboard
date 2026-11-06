# Benchmark summary

These historical results were documented in commit `1b44031` on October 26, 2026. They were not rerun for the latest documentation update. Exact hardware, OS release, Python version, and original measurement timestamps were not recorded in the benchmark document, so these figures should not be treated as a reproducible hardware specification or a performance guarantee.

## Page loading

The baseline was commit `a3b2c25`. Measurements used the same device, Chromium, a 1440 × 900 viewport, and the median of three runs. Simulated slow WiFi used 70 ms latency and 200 KiB/s download speed.

| Metric | Before | After |
| --- | --- | --- |
| Initial static-asset transfer | 614 KiB | 298 KiB |
| Slow-WiFi page load | 2.90 s | 2.02 s |
| Static-asset requests on a cached revisit | 12 | 0 |

Static assets include scripts, styles, fonts, and icons. HTML and live API requests remain uncached. Page-load timings are not API response times.

## Server memory

The same source was tested with default allocator settings and `MALLOC_ARENA_MAX=2` on Linux/glibc. Each configuration used three fresh read-only processes, six concurrent clients, and 2,400 GET requests per run; results are medians.

| RSS | Default | Tuned |
| --- | --- | --- |
| Startup | 36.6 MiB | 36.5 MiB |
| After routine load | 40.8 MiB | 39.6 MiB |
| After full Chinese fallback-font transfer | 42.6 MiB | 41.1 MiB |

RSS includes resident shared-library pages; it is not exclusive memory usage or virtual address space. Usage varies with system process count, clients, and requested content. HTTP median response times were 7.7 / 7.9 ms and P95 times were 24.3 / 22.2 ms for default / tuned settings.

## Recheck on your device

Install the project dependencies first. Browser checks additionally require Playwright and a compatible Chromium installation; inspect the script requirements before running them. Run memory measurements sequentially, without other benchmarks in parallel:

```bash
.venv/bin/python docs/memory_check.py --arenas default --output /tmp/helloboard-memory-default.json
.venv/bin/python docs/memory_check.py --arenas 2 --output /tmp/helloboard-memory-tuned.json
```

For browser measurements, start a read-only preview as described in the [original methodology](performance.md) (Chinese), then run:

```bash
.venv/bin/python docs/performance_check.py --runs 3
```

Record your commit, hardware model, OS, architecture, Python/browser versions, test date, and workload alongside new results. The scripts use read-only preview services; they are not intended to switch WiFi or terminate processes.
