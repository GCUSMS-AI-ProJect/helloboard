"""Capture README images from a running preview without scanning or writing WiFi.

Requires Playwright and /usr/bin/chromium. Reads one metrics snapshot, replaces
host/network/process identity with examples, and intercepts all browser API calls.
Usage: .venv/bin/python docs/capture_readme.py [http://127.0.0.1:8090]
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect
from theme_check import STATUS, PROCESSES

BASE = (sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8090').rstrip('/')
OUT = Path(__file__).resolve().parent / 'images'


def main():
    with urlopen(BASE+'/api/system',timeout=10) as response:
        metrics=json.load(response)
    metrics['device']['hostname']='helloboard'
    metrics['interfaces']=[dict(name='wlan0',addresses=['192.168.1.20'],wireless=True,
        ssid='StudioWiFi',signal=88,state='up',rx_bytes=126*1024**2,tx_bytes=43*1024**2,
        rx_rate=48*1024,tx_rate=12*1024,rx_errors=0,tx_errors=0)]
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
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport=dict(width=1440,height=1000),
            color_scheme='light',reduced_motion='reduce')
        context.route('**/api/**',fixture)
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(BASE+'/system_status')
        expect(page.locator('#process-list tr')).to_have_count(4)
        for theme in ['light','dark']:
            page.evaluate('(theme)=>HelloBoardTheme.set(theme)',theme)
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(OUT/f'system-{theme}.png'),full_page=True)
        page.goto(BASE+'/wifi_config')
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
    print('Captured four current screenshots with example identities; no device writes or scans.')


if __name__=='__main__': main()
