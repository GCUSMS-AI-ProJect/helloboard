"""Check layout composition, motion and preserved state without network writes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:8090'
fixture = dict(items=[dict(pid=40000+i, started=1000+i, name=f'worker-{i:02d}',
    cpu_percent=24-i, memory=(24-i)*1024**2, selectable=i != 0,
    reason='受保护的系统进程' if i == 0 else '') for i in range(8)],
    preview=False, supported=True, max_batch=32)
errors, writes, layouts = [], [], []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width':1440, 'height':1000})
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda req: writes.append(req.url) if '/api/' in req.url and req.method != 'GET' else None)
    page.route('**/api/processes', lambda route: route.fulfill(json=fixture))
    page.route('**/api/processes/terminate', lambda route: route.abort())
    page.goto(BASE+'/system_status')
    page.wait_for_selector('#process-list tr[data-key]')
    page.wait_for_selector('#core-list .resource-ring')
    page.locator('#process-list input:not(:disabled)').first.check()
    page.locator('#process-search').fill('worker-01')
    page.evaluate("() => {window.savedRow=document.querySelector('#process-list tr');window.savedRing=document.querySelector('#core-list .resource-ring');window.transitions=[];const start=document.startViewTransition.bind(document);document.startViewTransition=(update)=>{const result=start(update);transitions.push(result);return result;};}")
    page.locator('#style-settings').click()
    page.locator('#side-panel').evaluate('async e => await Promise.allSettled(e.getAnimations().map(a=>a.finished))')
    before = page.locator('#side-panel').bounding_box()
    page.locator('#layout-relaxed').click()
    motion = page.evaluate("async () => {await transitions.at(-1).ready;return document.getAnimations().filter(a=>a.animationName?.startsWith('layout-fade')).map(a=>({name:a.animationName,duration:a.effect.getTiming().duration}));}")
    assert len(motion) == 2 and all(a['duration'] == 420 for a in motion), motion
    page.evaluate('async () => await transitions.at(-1).finished')
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    assert page.locator('#side-panel').bounding_box() == before
    expect(page.locator('#process-search')).to_have_value('worker-01')
    expect(page.locator('#process-list input')).to_be_checked()
    assert page.evaluate("() => savedRow===document.querySelector('#process-list tr') && savedRing===document.querySelector('#core-list .resource-ring')")
    # Cancel pending snapshots and keep the last semantic/persisted selection.
    page.evaluate("() => {setLayout('compact');setLayout('relaxed');setLayout('compact');setLayout('relaxed');}")
    page.evaluate('async () => await Promise.allSettled(transitions.map(t=>t.finished))')
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    expect(page.locator('#layout-relaxed')).to_have_attribute('aria-pressed','true')
    assert page.evaluate("localStorage.getItem('helloboard.layout')") == 'relaxed'
    # Exercise the fallback and interrupted Web Animations too.
    page.evaluate("() => {Object.defineProperty(document,'startViewTransition',{configurable:true,value:undefined});setLayout('compact');setLayout('relaxed');}")
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    page.evaluate("async () => await Promise.allSettled(document.querySelector('#main').getAnimations().map(a=>a.finished))")
    page.emulate_media(reduced_motion='reduce')
    page.evaluate("() => setLayout('compact')")
    assert not page.locator('#main').evaluate('e=>e.getAnimations().length')
    page.locator('#panel-close').click()
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-layout','compact')
    # Both compositions are usable across screen sizes and languages.
    for path in ['system_status','wifi_config']:
        page.goto(BASE+'/'+path)
        if path == 'wifi_config':
            page.wait_for_function("() => document.querySelector('#connection-name').textContent !== '—'")
            page.locator('#ssid').fill('Unsaved layout test')
            page.locator('#password').fill('unsaved-test-only')
        for layout in ['compact','relaxed']:
            page.evaluate('(layout) => setLayout(layout)', layout)
            for language in ['zh','en']:
                if page.locator('html').get_attribute('lang') != ('en' if language=='en' else 'zh-CN'):
                    page.locator('#language-toggle').click()
                for width in [320,375,600,768,1000,1024,1280,1440,1920]:
                    page.set_viewport_size({'width':width,'height':1000})
                    assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth'),(path,layout,language,width)
                    if path == 'system_status':
                        columns=page.locator('.details-grid').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length')
                        expected=(2 if width>1000 else 1) if layout=='relaxed' else (4 if width>=1200 else 2 if width>=700 else 1)
                        assert columns==expected,(layout,width,columns)
                        assert page.locator('.process-table-wrap').evaluate('e=>e.scrollWidth<=e.clientWidth+1')
                    else:
                        expect(page.locator('#ssid')).to_have_value('Unsaved layout test')
                        expect(page.locator('#password')).to_have_value('unsaved-test-only')
                        if layout=='relaxed' and width>=1400:
                            status=page.locator('.status-card').bounding_box()
                            settings=page.locator('.settings').bounding_box()
                            nearby=page.locator('.nearby').bounding_box()
                            assert status['x']<settings['x']<nearby['x']
                        if layout=='compact' and width>=900:
                            assert page.evaluate('() => document.documentElement.scrollHeight<=innerHeight+1')
                    layouts.append([path,layout,language,width])
                page.set_viewport_size({'width':1440,'height':1000})
            if page.locator('html').get_attribute('lang')!='zh-CN':
                page.locator('#language-toggle').click()
            page.evaluate('() => window.scrollTo(0,0)')
            page.screenshot(path=str(OUT/f'{layout}-{path}-desktop.png'), full_page=True)
            page.set_viewport_size({'width':375,'height':900})
            page.screenshot(path=str(OUT/f'{layout}-{path}-mobile.png'), full_page=True)
            page.set_viewport_size({'width':1440,'height':1000})
    # The same preference is restored when navigating between pages.
    page.locator('.sidebar-nav a[href="/system_status"]').click()
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    assert not errors, errors
    # WiFi scanning is a read-only POST; configuration writes remain forbidden.
    assert all(url.endswith('/api/scan') for url in writes), writes
    report=dict(layouts=layouts,snapshot_motion=motion,rapid_switch_last_choice=True,
        fallback_and_reduced_motion=True,drawer_position_stable=True,
        form_and_process_selection_preserved=True,existing_data_nodes_preserved=True,
        cross_page_preference=True,no_network_writes=True,js_errors=errors)
    (OUT/'layout-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({**report,'layouts_checked':len(layouts),'layouts':'See docs/layout-report.json'},indent=2))
    browser.close()
