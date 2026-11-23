"""Capture README images from a running preview without scanning or writing WiFi.

Requires Playwright and /usr/bin/chromium. Reads one metrics snapshot, replaces
host/network/process identity with examples, and intercepts all browser API calls.
Usage: .venv/bin/python docs/capture_readme.py [http://127.0.0.1:8090] [--dashboard-only]
"""
import argparse
from copy import deepcopy
import json
from math import sin
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from playwright.sync_api import sync_playwright, expect
from theme_check import STATUS, PROCESSES

OUT = Path(__file__).resolve().parent / 'images'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', nargs='?', default='http://127.0.0.1:8090')
    parser.add_argument('--dashboard-only', action='store_true')
    args = parser.parse_args()
    base = args.base.rstrip('/')
    with build_opener(ProxyHandler({})).open(base + '/api/system', timeout=10) as response:
        metrics=json.load(response)
    metrics['device'] = dict(hostname='helloboard', model='Raspberry Pi 5 Model B Rev 1.0',
        os='Debian GNU/Linux 13 (trixie)', kernel='6.18.50+rpt-rpi-2712', architecture='aarch64')
    metrics['sampled_at'] = 1770000000
    metrics['history_id'] = 'readme-preview'
    metrics['history'] = [
        dict(time=metrics['sampled_at'] - (60 - i) * 8, cpu=33 + 10 * sin(i / 3) + 9 * sin(i * 1.23),
             memory=27 + 2.5 * sin(i / 12), rx=45000 + 14000 * sin(i / 4) + 17000 * sin(i * 1.95),
             tx=14000 + 4000 * sin(i / 5) + 5500 * sin(i * 1.31))
        for i in range(61)
    ]
    latest = metrics['history'][-1]
    metrics['cpu'].update(count=4, frequency_mhz=2400, load=[0.92, .65, .39],
                          cores=[dict(name=f'cpu{i}', percent=load) for i, load in enumerate((32, 39, 45, 35))],
                          percent=latest['cpu'])
    metrics['memory']['percent'] = latest['memory']
    metrics['memory']['total'] = 8 * 1024 ** 3
    metrics['memory']['used'] = round(metrics['memory']['total'] * latest['memory'] / 100)
    metrics['memory']['available'] = metrics['memory']['total'] - metrics['memory']['used']
    metrics['memory'].update(cached=2 * 1024**3, buffers=105 * 1024**2, swap_total=2 * 1024**3, swap_used=0)
    metrics['uptime_seconds'] = 16 * 3600 + 42 * 60
    metrics['temperature_c'] = 48.7
    metrics['fans'] = [dict(name='fan1', rpm=3200)]
    metrics['power'] = dict(undervoltage=False, frequency_capped=False, throttled=False,
                            temperature_limited=False, historical=False)
    metrics['primary_mount'] = '/'
    metrics['volumes'] = [
        dict(mount='/', total=117 * 1024**3, used=9 * 1024**3, available=108 * 1024**3,
             percent=7.7, filesystem='ext4', source='/dev/mmcblk0p2'),
        dict(mount='/boot/firmware', total=512 * 1024**2, used=88 * 1024**2, available=424 * 1024**2,
             percent=17.2, filesystem='vfat', source='/dev/mmcblk0p1'),
    ]
    metrics['disks'] = [dict(name='mmcblk0', type='SD', read_bytes=135 * 1024**2, write_bytes=2 * 1024**3,
                             read_rate=48000, write_rate=42000)]
    metrics['services'] = [
        dict(name=name, state='active', enabled='enabled')
        for name in ('helloboard.service', 'NetworkManager.service')
    ]
    metrics['interfaces']=[dict(name='wlan0',addresses=['192.168.1.20'],wireless=True,
        ssid='StudioWiFi',signal=88,state='up',rx_bytes=126*1024**2,tx_bytes=43*1024**2,
        rx_rate=latest['rx'],tx_rate=latest['tx'],rx_errors=0,tx_errors=0)]
    metrics['processes']={'cpu':[],'memory':[]}
    processes=deepcopy(PROCESSES)
    processes['items']=[dict(pid=pid,started=pid,name=name,memory=memory*1024**2,
        cpu_percent=cpu,selectable=allowed,reason='' if allowed else '受保护的系统进程')
        for pid,name,memory,cpu,allowed in [
            (820,'python',48,3.2,True),(544,'NetworkManager',16,.4,False),
            (960,'worker',24,1.1,True),(1,'systemd',12,.1,False)]]
    metrics['process_count']=len(processes['items'])
    OUT.mkdir(exist_ok=True)
    errors=[]
    def fixture(route):
        path=route.request.url.split('/api/')[-1].split('?')[0]
        if path=='system': route.fulfill(json=metrics)
        elif path=='processes': route.fulfill(json=processes)
        elif path=='status': route.fulfill(json=STATUS)
        elif path=='scan': route.fulfill(json={'networks':[
            dict(ssid=name,signal=signal,security=security,active=active,supported=True)
            for name,signal,security,active in [
                ('StudioWiFi',88,'WPA2',True),('Workshop',72,'WPA2',False),
                ('Guest',50,'--',False),('HomeOffice',38,'WPA2',False)]], 'warning':''})
        else: raise AssertionError('Unexpected API call: '+route.request.url)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox', '--no-proxy-server'])
        context=browser.new_context(viewport=dict(width=1440,height=1120), device_scale_factor=1,
            color_scheme='light',reduced_motion='reduce', timezone_id='Asia/Shanghai')
        context.route('**/api/**',fixture)
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(base+'/system_status', timeout=12000)
        expect(page.locator('#process-list tr')).to_have_count(4)
        for chart in ('usage', 'traffic'):
            expect(page.locator(f'#{chart}-empty')).to_be_hidden()
            for series in ('primary', 'secondary'):
                assert 'C' in page.locator(f'#{chart}-chart .series-{series}').get_attribute('d')
        for theme in ['light','dark']:
            page.evaluate('(theme)=>HelloBoardTheme.set(theme)',theme)
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(OUT/f'system-{theme}.png'),full_page=True)
        if not args.dashboard_only:
            page.goto(base+'/wifi_config')
            expect(page.locator('.network-row')).to_have_count(4)
            page.evaluate("HelloBoardTheme.set('light')")
            page.set_viewport_size(dict(width=1440,height=900))
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(OUT/'wifi-desktop.png'),full_page=True)
            page.set_viewport_size(dict(width=390,height=844))
            page.evaluate("HelloBoardTheme.set('dark')")
            page.screenshot(path=str(OUT/'wifi-mobile.png'),full_page=True)
        context.close()
        browser.close()
    assert not errors,errors
    print('Captured README screenshots with example system history and device identities.')


if __name__=='__main__': main()
