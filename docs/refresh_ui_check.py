"""Verify independent loading and refresh/recovery using isolated browser APIs."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from urllib.request import urlopen

from playwright.async_api import async_playwright, expect
from theme_check import PROCESSES


async def main():
    base = 'http://127.0.0.1:8090'
    with urlopen(base + '/api/system', timeout=10) as response:
        sample = json.load(response)
    data = deepcopy(sample)
    data['cpu']['percent'] = 43.7
    errors, requests = [], {'system': 0, 'processes': 0}
    state = {'failed': False}

    async def api(route):
        path = route.request.url.split('/api/')[-1].split('?')[0]
        assert route.request.method == 'GET', 'Unexpected device write'
        if path == 'system':
            requests['system'] += 1
            # Sleep asynchronously: the process response can arrive independently.
            await asyncio.sleep(.6)
            if state['failed']:
                await route.fulfill(status=503, json={'error': 'fixture unavailable'})
            else:
                await route.fulfill(json=data)
        elif path == 'processes':
            requests['processes'] += 1
            await route.fulfill(json=PROCESSES)
        else:
            raise AssertionError('Unexpected API: ' + path)

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.route('**/api/**', api)
        await page.goto(base + '/system_status', wait_until='domcontentloaded')
        await expect(page.locator('#process-list')).to_contain_text('worker')
        await expect(page.locator('#metric-cpu')).to_have_text('—')
        await expect(page.locator('#metric-cpu')).to_have_text('43.7%')
        assert requests['processes'] == 1, requests
        await page.locator('#process-list input:enabled').check()
        await page.evaluate('window.originalDeviceRow=document.querySelector("#device-list > div")')

        data['cpu']['percent'] = 44.2
        data['sampled_at'] += 2
        await page.locator('#refresh-status').click()
        await expect(page.locator('#refresh-status')).to_have_attribute('aria-busy', 'true')
        await expect(page.locator('#metric-cpu')).to_have_text('44.2%')
        await expect(page.locator('#refresh-status')).to_have_attribute('aria-busy', 'false')
        await expect(page.locator('#process-list input:enabled')).to_be_checked()
        assert await page.evaluate('originalDeviceRow === document.querySelector("#device-list > div")')
        await expect(page.locator('#process-error')).to_be_hidden()

        state['failed'] = True
        await page.locator('#refresh-status').click()
        await expect(page.locator('#update-state')).to_have_attribute('data-state', 'error')
        await expect(page.locator('#metric-cpu')).to_have_text('44.2%')
        await expect(page.locator('#process-list')).to_contain_text('worker')
        state['failed'] = False
        data['cpu']['percent'] = 45.1
        data['sampled_at'] += 2
        await page.locator('#refresh-status').click()
        await expect(page.locator('#metric-cpu')).to_have_text('45.1%')
        await expect(page.locator('#update-state')).to_have_attribute('data-state', 'live')

        await page.locator('#language-toggle').click()
        await expect(page.locator('#refresh-status')).to_have_attribute('aria-label', 'Refresh status')
        for width in (1440, 375, 320):
            await page.set_viewport_size({'width': width, 'height': 900})
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
            assert await page.locator('.system-panel #refresh-status').count() == 1
        assert not errors, errors
        await browser.close()
    report = dict(process_list_loads_before_delayed_system=True,
                  initial_process_request_not_duplicated=True,
                  manual_refresh_and_failure_recovery=True,
                  process_selection_and_node_reuse=True,
                  language_and_mobile_layout=True, errors=errors)
    Path(__file__).with_name('refresh-ui-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
