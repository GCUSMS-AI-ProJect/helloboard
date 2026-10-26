"""Read-only dashboard and shared-shell checks; no WiFi operations or logins."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    context = browser.new_context(viewport={'width':1440,'height':1080}, reduced_motion='reduce')
    page = context.new_page()
    errors, console_errors, operations, samples = [], [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)
    page.on('request', lambda request: operations.append(request.url) if '/api/' in request.url and not (request.method == 'GET' and request.url.split('?')[0].endswith(('/api/system','/api/processes'))) else None)
    page.on('response', lambda response: samples.append(response.url) if response.url.split('?')[0].endswith('/api/system') else None)
    page.goto('http://127.0.0.1:8090/')
    expect(page).to_have_title('HelloBoard · 系统状态')
    expect(page.locator('.sidebar-nav .active')).to_have_text('系统状态系统状态')
    expect(page.locator('#update-state')).to_have_text('实时更新')
    page.wait_for_function("() => document.querySelector('#metric-cpu').textContent !== '—'", timeout=10000)
    page.evaluate('document.fonts.ready')
    expect(page.locator('#usage-empty')).not_to_be_visible(timeout=8000)
    assert page.locator('.card').count() == 1
    data = context.request.get('http://127.0.0.1:8090/api/system').json()
    assert data['cpu']['count'] == 4
    assert data['memory']['total'] > 0 and data['memory']['used'] >= 0
    assert data['volumes'] and data['interfaces'] and data['services']
    assert data['fans'][0]['rpm'] >= 0
    expect(page.locator('#device-list')).to_contain_text(data['device']['model'])
    expect(page.locator('#interface-list')).to_contain_text('192.168.36.36')
    expect(page.locator('#service-list')).to_contain_text('helloboard')
    assert page.locator('#usage-chart .series-primary').get_attribute('d')
    assert not operations, operations
    resources = page.evaluate("performance.getEntriesByType('resource').filter(r=>r.name.endsWith('.woff2')).map(r=>r.name)")
    assert not any('fallback' in resource for resource in resources), resources
    page.screenshot(path=str(OUT/'system-desktop.png'),full_page=True)
    layouts=[]
    for layout in ['compact','relaxed']:
        page.locator('#style-settings').click()
        page.locator('#layout-'+layout).click()
        expect(page.locator('html')).to_have_attribute('data-layout',layout)
        page.locator('#panel-close').click()
        for width in [320,375,600,768,900,1024,1280,1920]:
            page.set_viewport_size({'width':width,'height':900})
            page.evaluate('document.fonts.ready')
            overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow, (layout,width,page.evaluate('document.documentElement.scrollWidth'))
            layouts.append([layout,width])
    page.set_viewport_size({'width':375,'height':900})
    expect(page.locator('.mobile-pages')).to_be_visible()
    page.screenshot(path=str(OUT/'system-mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1080})
    before=page.locator('#language-toggle').bounding_box()
    page.locator('#language-toggle').click()
    expect(page).to_have_title('HelloBoard · System status')
    after=page.locator('#language-toggle').bounding_box()
    assert before == after, (before,after)
    expect(page.locator('#resources-list')).to_contain_text('Available memory')
    expect(page.locator('#service-list')).to_contain_text('Running')
    page.locator('#help-button').click()
    expect(page.locator('#panel-title')).to_have_text('Help')
    page.keyboard.press('Escape')
    expect(page.locator('#side-panel')).not_to_be_visible()
    page.locator('#language-toggle').click()
    page.locator('#sort-memory').click()
    expect(page.locator('#sort-memory')).to_have_attribute('aria-pressed','true')
    values=page.locator('#process-list .process-memory-cell > span:first-child').all_text_contents()
    assert values and all(value != '—' for value in values)
    expect(page.locator('#pause-updates')).to_have_count(0)
    count=len(samples)
    with page.expect_response(lambda response:'/api/system' in response.url):
        page.locator('#refresh-status').click()
    expect(page.locator('#refresh-status')).to_be_enabled()
    expect(page.locator('#update-state')).to_have_text('实时更新')
    assert len(samples)>count
    count=len(samples)
    page.wait_for_timeout(2400)
    assert len(samples)>count, 'Manual refresh stopped automatic updates'
    page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>window.testHidden});window.testHidden=true;document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(200)
    count=len(samples)
    page.wait_for_timeout(2200)
    assert len(samples)==count
    page.evaluate("window.testHidden=false;document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(300)
    assert len(samples)>count
    # Fail a real poll, retain the last values, then recover without a reload.
    last=page.locator('#metric-memory').inner_text()
    page.route('**/api/system*',lambda route:route.fulfill(status=503,content_type='application/json',body='{}'))
    expect(page.locator('#update-state')).to_have_text('更新中断',timeout=10000)
    expect(page.locator('#metric-memory')).to_have_text(last)
    page.unroute('**/api/system*')
    expect(page.locator('#update-state')).to_have_text('实时更新',timeout=12000)
    page.locator('#sidebar-toggle').click()
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded','false')
    page.locator('.sidebar-nav .active').hover()
    expect(page.locator('.sidebar-nav .active .nav-tooltip')).to_be_visible()
    page.locator('.sidebar-nav a[href="/wifi_config"]').click()
    expect(page).to_have_url('http://127.0.0.1:8090/wifi_config')
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded','false')
    expect(page.locator('html')).to_have_attribute('data-layout','relaxed')
    page.locator('.sidebar-nav a').first.click()
    expect(page).to_have_title('HelloBoard · 系统状态')
    page.emulate_media(reduced_motion='no-preference')
    page.locator('#style-settings').click()
    assert page.locator('#side-panel').evaluate('e=>getComputedStyle(e).animationDuration') == '0.42s'
    page.locator('#panel-close').click()
    expect(page.locator('#side-panel')).not_to_be_visible()
    assert not errors, errors
    assert not [e for e in console_errors if 'Content Security Policy' in e], console_errors
    report=dict(layouts=layouts,actual_device=data['device'],js_errors=errors,single_surface=True,
                fonts=resources,manual_refresh_and_background_resume=True,failure_recovery=True,
                shared_navigation_preferences=True,read_only=True)
    (OUT/'dashboard-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    browser.close()
