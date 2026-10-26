"""Browser checks for theme persistence, legibility and intact form state.

All WiFi status/scan and process data are fixtures. No device writes occur.
Run against the local preview: .venv/bin/python docs/theme_check.py
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8090'
STATUS = dict(address='192.168.1.20', ap_address='192.168.11.17', ap_ssid='hellosms',
    ap_has_password=True, authorized=False, busy=False, configured_mode='lan', connected=True,
    csrf_token='fixture', fallback=False, message='', mode='lan', phase='ready', preview=False,
    saved_ssid='StudioWiFi', ssid='StudioWiFi', saved_networks=[{'ssid':'StudioWiFi','has_password':True}],
    capabilities=dict(ap=True,available=True,manage=True,interface='wlan0',reason=''))
PROCESSES = dict(preview=False, supported=True, max_batch=32, username='ubuntu', items=[
    dict(pid=50,started=100,name='worker',memory=10485760,cpu_percent=12,selectable=True,reason=''),
    dict(pid=1,started=1,name='systemd',memory=1048576,cpu_percent=0,selectable=False,reason='受保护的系统进程')])


def fixture(route):
    path = route.request.url.split('/api/')[-1].split('?')[0]
    if path == 'status': route.fulfill(json=STATUS)
    elif path == 'scan': route.fulfill(json=dict(networks=[dict(ssid='StudioWiFi',signal=90,security='WPA2',active=True,supported=True)],warning=''))
    elif path == 'processes': route.fulfill(json=PROCESSES)
    elif route.request.method != 'GET':
        raise AssertionError('Unexpected write: ' + route.request.url)
    else: route.continue_()


def contrast(a, b):
    def luminance(color):
        values = [int(color[i:i+2],16)/255 for i in (1,3,5)]
        return sum(w*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)
                   for v,w in zip(values,(.2126,.7152,.0722)))
    x,y=sorted((luminance(a),luminance(b)))
    return (y+.05)/(x+.05)


def main():
    errors, checks, ratios = [], [], {}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(color_scheme='light',reduced_motion='reduce')
        context.route('**/api/**',fixture)
        page=context.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(BASE+'/wifi_config')
        expect(page.locator('#connection-name')).to_have_text('StudioWiFi')
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        page.locator('#ssid').fill('Unsaved network')
        page.locator('#password').fill('unsaved-password')
        page.evaluate('window.originalInput=document.querySelector("#ssid")')
        before=page.locator('#theme-toggle').bounding_box()
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        expect(page.locator('#theme-toggle')).to_have_attribute('aria-checked','true')
        expect(page.locator('#ssid')).to_have_value('Unsaved network')
        expect(page.locator('#password')).to_have_value('unsaved-password')
        assert page.evaluate('originalInput === document.querySelector("#ssid")')
        after=page.locator('#theme-toggle').bounding_box()
        assert before['width']==after['width'] and before['x']==after['x']
        page.locator('#language-toggle').click()
        expect(page.locator('#theme-toggle')).to_have_attribute('title','Switch to light mode')
        page.locator('#language-toggle').click()
        page.locator('#connect-button').click()
        expect(page.locator('#confirm-dialog')).to_be_visible()
        page.locator('#cancel-switch').click()
        page.locator('#reveal-password').click()
        expect(page.locator('#authorize-dialog')).to_be_visible()
        page.locator('#authorize-cancel').click()
        page.locator('#mode-ap').click()
        page.locator('.ap-settings-link').click()
        expect(page.locator('#ap-password')).to_be_visible()
        page.locator('#panel-close').click()
        page.locator('#mode-lan').click()
        page.locator('#saved-network-toggle').click()
        expect(page.locator('#saved-network-menu')).to_be_visible()
        page.keyboard.press('Escape')
        checks.append('Theme preserves form nodes/values; labels, confirmation, authorization, AP drawer and saved list work')
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        # Sample at DOM ready: saved theme was applied before deferred UI setup.
        page.goto(BASE+'/system_status',wait_until='domcontentloaded')
        assert page.evaluate('document.documentElement.dataset.theme')=='dark'
        expect(page.locator('#process-list input:enabled')).to_have_count(1)
        page.locator('#process-list input:enabled').check()
        page.locator('#terminate-selected').click()
        expect(page.locator('#process-dialog')).to_be_visible()
        page.locator('#process-cancel').click()
        checks.append('Dark preference survives reload and page navigation; process selection/dialog work')
        for theme in ['light','dark']:
            page.evaluate('(theme)=>HelloBoardTheme.set(theme)',theme)
            colors=page.evaluate('''() => {const s=getComputedStyle(document.documentElement);return Object.fromEntries(
                ['text','muted','placeholder','primary-bg','on-primary','surface','surface-raised','surface-hover',
                'surface-track','segment-selected','positive','positive-bg','warning','warning-bg','danger','danger-bg',
                'neutral','neutral-bg','control-border','donut-cpu','donut-memory','donut-storage','donut-track',
                'chart-primary','chart-secondary','tooltip-bg','on-tooltip'].map(k=>[k,s.getPropertyValue('--'+k).trim()]));}''')
            pairs=[('text',bg,4.5) for bg in ['surface','surface-raised','surface-hover','segment-selected']]
            pairs += [('muted',bg,4.5) for bg in ['surface','surface-raised','surface-track','segment-selected']]
            pairs += [(a,b,4.5) for a,b in [('placeholder','surface'),('placeholder','surface-raised'),
                ('on-primary','primary-bg'),('positive','positive-bg'),('warning','warning-bg'),
                ('danger','danger-bg'),('neutral','neutral-bg'),('on-tooltip','tooltip-bg')]]
            pairs += [('control-border',bg,3) for bg in ['surface','surface-raised']]
            pairs += [(key,'donut-track',3) for key in ['donut-cpu','donut-memory','donut-storage']]
            pairs += [(key,'surface',3) for key in ['chart-primary','chart-secondary']]
            for a,b,minimum in pairs:
                value=contrast(colors[a],colors[b])
                assert value>=minimum,(theme,a,b,value,minimum)
                ratios[f'{theme}:{a}/{b}']=round(value,2)
            for path in ['system_status','wifi_config']:
                page.goto(BASE+'/'+path)
                for density in ['compact','relaxed']:
                    page.locator('#style-settings').click()
                    page.locator('#layout-'+density).click()
                    page.locator('#panel-close').click()
                    for width,height in [(1440,900),(375,812),(320,640)]:
                        page.set_viewport_size(dict(width=width,height=height))
                        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),(theme,path,density,width)
                        expect(page.locator('#theme-toggle')).to_be_in_viewport()
                        box=page.locator('#theme-toggle').bounding_box()
                        assert box['width']>=44 and box['height']>=44
                        if theme=='dark' and density=='compact' and width in [1440,375]:
                            page.screenshot(path=str(ROOT/f'docs/dark-{path}-{width}.png'),full_page=True)
                    checks.append(f'{theme}/{path}/{density}: desktop, 375px and 320px fit; toggle touch area >=44px')
        # Theme follows OS only until the user chooses explicitly; changes sync across tabs.
        page.evaluate('localStorage.removeItem("helloboard.theme")')
        page.emulate_media(color_scheme='dark')
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        page.emulate_media(color_scheme='light')
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        page.locator('#theme-toggle').click()
        page.emulate_media(color_scheme='dark')
        page.emulate_media(color_scheme='light')
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        other=context.new_page()
        other.goto(BASE+'/system_status')
        other.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','light')
        checks.append('OS preference, explicit override and cross-tab synchronization')
        context.close()
        isolated=browser.new_context(color_scheme='light',reduced_motion='reduce')
        isolated.route('**/api/**',fixture)
        isolated.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('storage blocked')}})")
        page=isolated.new_page()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(BASE+'/system_status')
        page.locator('#theme-toggle').click()
        expect(page.locator('html')).to_have_attribute('data-theme','dark')
        checks.append('Theme toggle works when browser storage is blocked')
        isolated.close()
        browser.close()
    assert not errors,errors
    report=dict(checks=checks,contrast_ratios=ratios,errors=errors)
    (ROOT/'docs/theme-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
