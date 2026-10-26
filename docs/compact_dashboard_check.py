"""Check four desktop columns, live ring values and narrow-screen layout.

Only read-only APIs are used. Controlled telemetry verifies updates while the
existing process interaction check covers search, selection and confirmations.
"""
import copy
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright, expect

OUT=Path(__file__).resolve().parent
with urllib.request.urlopen('http://127.0.0.1:8090/api/system') as response:
    sample=json.load(response)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    current=copy.deepcopy(sample)
    page.route('**/api/system*',lambda route:route.fulfill(json=current))
    page.goto('http://127.0.0.1:8090/system_status')
    expect(page.locator('#core-list .resource-ring')).to_have_count(len(current['cpu']['cores']))
    expect(page.locator('#memory-gauge .resource-ring')).to_have_count(1)
    expect(page.locator('#volume-list .resource-ring')).to_have_count(len(current['volumes']))
    assert page.locator('#core-list progress,#volume-list progress').count()==0
    page.wait_for_selector('#process-list tr[data-key]')
    page.locator('#process-list input:not(:disabled)').first.check()
    page.evaluate('() => window.savedCoreRing=document.querySelector("#core-list .resource-ring")')
    current['cpu']['cores'][0]['percent']=73.2
    current['memory']['percent']=84.6
    current['volumes'][0]['percent']=91.2
    page.locator('#refresh-status').click()
    expect(page.locator('#core-list .donut-value').first).to_have_attribute('stroke-dasharray','73.2 100')
    expect(page.locator('#memory-gauge .donut-value')).to_have_attribute('stroke-dasharray','84.6 100')
    expect(page.locator('#volume-list .donut-value').first).to_have_attribute('stroke-dasharray','91.2 100')
    assert page.evaluate('() => savedCoreRing===document.querySelector("#core-list .resource-ring")')
    expect(page.locator('#core-list .resource-ring').first).to_have_attribute('aria-label','CPU0 · 73.2%')
    expect(page.locator('#process-count')).to_contain_text('已选 1')
    page.locator('#process-clear').click()
    layouts=[]
    for layout in ['compact','relaxed']:
        page.locator('#style-settings').click()
        page.locator('#layout-'+layout).click()
        page.locator('#panel-close').click()
        for language in ['zh','en']:
            if page.locator('html').get_attribute('lang') != ('zh-CN' if language=='zh' else 'en'):
                page.locator('#language-toggle').click()
            for width in [320,375,600,768,1024,1280,1440,1920]:
                page.set_viewport_size({'width':width,'height':1000})
                expected=(2 if width>1000 else 1) if layout=='relaxed' else (4 if width>=1200 else 2 if width>=700 else 1)
                count=page.locator('.details-grid').evaluate('e=>getComputedStyle(e).gridTemplateColumns.split(" ").length')
                assert count==expected,(width,count,expected)
                assert page.locator('.detail-column').count()==4
                assert page.locator('.process-card').locator('..').get_attribute('class')=='detail-column'
                assert page.locator('.process-card').bounding_box()['width']<=page.locator('.details-grid').bounding_box()['width']/expected+1
                assert page.evaluate('() => document.documentElement.scrollWidth<=innerWidth'),(layout,language,width)
                assert page.locator('.process-table-wrap').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(layout,language,width)
                assert page.locator('.process-tools').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(layout,language,width)
                for ring in page.locator('.resource-ring').all():
                    assert ring.locator('.resource-percent').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),(layout,language,width)
                layouts.append([layout,language,width,count])
    # Missing samples are unknown; zero and full utilization remain distinct.
    for value in [None,0,100]:
        current['cpu']['cores'][0]['percent']=value
        current['memory']['percent']=value
        current['volumes'][0]['percent']=value
        page.locator('#refresh-status').click()
        for selector in ['#core-list .donut-value','#memory-gauge .donut-value','#volume-list .donut-value']:
            expect(page.locator(selector).first).to_have_attribute('data-available',str(value is not None).lower())
            expect(page.locator(selector).first).to_have_attribute('stroke-dasharray',f'{value or 0} 100')
    current=copy.deepcopy(sample)
    page.locator('#refresh-status').click()
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#language-toggle').click()
    page.locator('#style-settings').click();page.locator('#layout-compact').click();page.locator('#panel-close').click()
    page.evaluate('() => window.scrollTo(0,0)')
    page.screenshot(path=str(OUT/'four-column-desktop.png'),full_page=True)
    page.set_viewport_size({'width':375,'height':900})
    page.screenshot(path=str(OUT/'four-column-mobile.png'),full_page=True)
    assert not errors,errors
    report=dict(layouts=layouts,live_core_memory_volume_rings=True,preserved_svg_nodes=True,
        unknown_zero_and_full_distinct=True,compact_process_column=True,selection_preserved=True,js_errors=errors)
    (OUT/'compact-dashboard-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    browser.close()
