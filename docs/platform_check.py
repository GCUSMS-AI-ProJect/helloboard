"""Verify the live Linux preview and an isolated Windows capability profile.

The desktop backend is a fixture, not a Windows hardware certification. All
network writes and scans are intercepted; no system configuration is changed.
"""
import json
import logging
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from host_platform import DashboardController, ReadOnlyAuthenticator, detect_wifi
from portable_metrics import PortableSystemMetrics
from process_control import ProcessManager
from tests.test_platform import DesktopBackend, WINDOWS
from wifi import create_app


def main():
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    clock = [1000.0]
    backend = DesktopBackend()
    metrics = PortableSystemMetrics(host=WINDOWS, backend=backend,
        monotonic=lambda: clock[0], wall_time=lambda: clock[0])
    app = create_app(DashboardController(detect_wifi(WINDOWS)), host=WINDOWS,
        metrics=metrics, authenticator=ReadOnlyAuthenticator('desktop'),
        processes=ProcessManager(metrics, allow_control=False))
    server = make_server('127.0.0.1', 0, app, threaded=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    results, errors = [], []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            for profile, base in [('Linux', 'http://127.0.0.1:8090'), ('Windows', f'http://127.0.0.1:{server.server_port}')]:
                context = browser.new_context(reduced_motion='reduce')
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.route('**/api/scan', lambda route: route.fulfill(json={'networks':[], 'warning':''}))
                for width, height in [(1440,900), (375,812), (320,640)]:
                    page.set_viewport_size(dict(width=width,height=height))
                    page.goto(base + '/system_status')
                    expect(page.locator('#update-state')).to_have_text('实时更新')
                    expect(page.locator('.sidebar-nav a')).to_have_count(1 if profile == 'Windows' else 2)
                    expect(page.locator('.mobile-pages a')).to_have_count(1 if profile == 'Windows' else 2)
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (profile,width)
                    if profile == 'Windows':
                        expect(page.locator('#metric-storage')).to_have_text('20%')
                        expect(page.locator('#health-list').locator('..')).to_be_hidden()
                        expect(page.locator('#process-list input:enabled')).to_have_count(0)
                        page.locator('#language-toggle').click()
                        expect(page.locator('#update-state')).to_have_text('Live')
                        page.locator('#help-button').click()
                        expect(page.locator('#help-content')).to_contain_text('Runtime environment')
                        expect(page.locator('#help-content')).to_contain_text('Windows 11')
                        expect(page.locator('#help-content')).to_contain_text('not supported on this system yet')
                        page.locator('#panel-close').click()
                        page.locator('#language-toggle').click()
                    results.append(dict(profile=profile,width=width,horizontal_overflow=False))
                if profile == 'Windows':
                    clock[0] += 2
                    backend.step += 1
                    page.locator('#refresh-status').click()
                    expect(page.locator('#metric-cpu')).to_have_text('50%')
                    expect(page.locator('#metric-storage')).to_have_text('21%')
                    page.goto(base + '/wifi_config')
                    expect(page).to_have_url(base + '/system_status')
                    expect(page.locator('#update-state')).to_have_text('实时更新')
                    page.set_viewport_size(dict(width=1440,height=900))
                    page.screenshot(path=str(ROOT / 'docs/platform-windows.png'), full_page=True)
                else:
                    page.goto(base + '/wifi_config')
                    expect(page.locator('#connection-name')).not_to_have_text('—')
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                context.close()
            browser.close()
        assert not errors, errors
        (ROOT / 'docs/platform-check.json').write_text(json.dumps(dict(checks=results, errors=errors,
            windows='Simulated profile; native Windows validation still required.'), ensure_ascii=False, indent=2))
        print(json.dumps(dict(checks=results, errors=errors)))
    finally:
        server.shutdown()
        worker.join(timeout=3)


if __name__ == '__main__':
    main()
