"""Measure real assets and verify update reuse using isolated API fixtures.

Loading measurements use only read-only monitoring APIs. Interaction checks
use isolated fixtures seeded from one read-only metrics snapshot. --baseline records node reuse without requiring the optimization.
Requires Playwright and system Chromium. No radio scan or system writes occur.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import statistics
import time
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect
from theme_check import fixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8090')
    parser.add_argument('--runs',type=int,default=3)
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--output',type=Path,default=Path(__file__).with_name('performance-report.json'))
    args=parser.parse_args()
    # A freshly started collector needs a second sample for a genuine CPU rate.
    for _ in range(24):
        with urlopen(args.base+'/api/system',timeout=10) as response: sample=json.load(response)
        if sample['cpu']['percent'] is not None: break
        time.sleep(.25)
    errors=[]
    results=[]
    current=deepcopy(sample)
    def api(route):
        if route.request.url.split('?')[0].endswith('/api/system'): route.fulfill(json=current)
        else: fixture(route)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        for profile in ['lan','slow-wifi']:
            for run in range(args.runs):
                context=browser.new_context(viewport=dict(width=1440,height=900),reduced_motion='reduce')
                page=context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                cdp=context.new_cdp_session(page)
                cdp.send('Network.enable')
                if profile=='slow-wifi':
                    cdp.send('Network.emulateNetworkConditions',dict(offline=False,latency=70,
                        downloadThroughput=200*1024,uploadThroughput=100*1024))
                for visit in ['cold','revisit']:
                    page.goto(args.base+'/system_status')
                    expect(page.locator('#metric-cpu')).not_to_have_text('—')
                    page.evaluate('document.fonts.ready')
                    page.wait_for_timeout(100)
                    timing=page.evaluate('''() => {
                        const nav=performance.getEntriesByType('navigation')[0];
                        const resources=performance.getEntriesByType('resource').filter(r=>new URL(r.name).pathname.startsWith('/static/'));
                        return {load_ms:nav.loadEventEnd, fcp_ms:performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null,
                            static_transfer_bytes:resources.reduce((sum,r)=>sum+r.transferSize,0),
                            static_network_requests:resources.filter(r=>r.transferSize>0).length,
                            fonts:resources.filter(r=>r.name.includes('.woff2')).map(r=>({name:new URL(r.name).pathname.split('/').pop(),bytes:r.transferSize}))};
                    }''')
                    if not args.baseline:
                        assert not any('fallback' in f['name'] or 'inter-variable' in f['name'] for f in timing['fonts'])
                    results.append(dict(profile=profile,run=run,visit=visit,**timing))
                # Hold references across a real manual refresh and across language changes.
                if profile=='lan' and run==0:
                    context.route('**/api/**',api)
                    page.reload()
                    expect(page.locator('#metric-cpu')).not_to_have_text('—')
                    page.evaluate('''() => {window.reusedNodes=['#device-list > div','#resources-list > div','#interface-list > div',
                        '#interface-list dd','#service-list > div'].map(selector=>[selector,document.querySelector(selector)]);}''')
                    current['sampled_at']+=2
                    current['cpu']['percent']=43.7
                    if current['interfaces']: current['interfaces'][0]['rx_rate']=16384
                    page.locator('#refresh-status').click()
                    expect(page.locator('#metric-cpu')).to_have_text('43.7%')
                    reuse=page.evaluate('''() => Object.fromEntries(reusedNodes.map(([selector,node])=>[selector,node===document.querySelector(selector)]))''')
                    if not args.baseline: assert all(reuse.values()),reuse
                    # Existing service nodes stay while data is unchanged; changed states still repaint.
                    if current['services']:
                        current['sampled_at']+=2
                        current['services'][0]['state']='failed'
                        page.locator('#refresh-status').click()
                        expect(page.locator('#service-list .status-badge').first).to_have_text('故障')
                        expect(page.locator('#service-list .status-badge').first).to_have_attribute('data-tone','warning')
                    page.locator('#language-toggle').click()
                    expect(page.locator('#device-list')).to_contain_text('Hostname')
                    if current['services']:expect(page.locator('#service-list .status-badge').first).to_have_text('Failed')
                    # Probe a rare glyph in each face to verify on-demand coverage is retained.
                    page.evaluate('''() => {const probe=document.createElement('p');probe.id='font-coverage-probe';probe.textContent='Ω龘';document.body.append(probe);}''')
                    page.evaluate('document.fonts.ready')
                    loaded=page.evaluate('''() => performance.getEntriesByType('resource').filter(r=>r.name.includes('.woff2')).map(r=>r.name)''')
                    assert any('noto-sans-sc-fallback' in url for url in loaded)
                    assert any('inter-variable' in url for url in loaded)
                    page.locator('#font-coverage-probe').evaluate('e=>e.remove()')
                    current=deepcopy(sample)
                context.close()
        browser.close()
    assert not errors,errors
    summaries=[]
    for profile in ['lan','slow-wifi']:
        for visit in ['cold','revisit']:
            group=[r for r in results if r['profile']==profile and r['visit']==visit]
            summaries.append(dict(profile=profile,visit=visit,**{
                key:round(statistics.median(r[key] for r in group),1)
                for key in ['load_ms','fcp_ms','static_transfer_bytes','static_network_requests']}))
    report=dict(conditions='Chromium, 1440x900, reduced motion; slow WiFi: 70ms latency / 200KiB/s down; isolated API fixtures',
                runs=args.runs,summary=summaries,node_reuse=reuse,errors=errors,measurements=results)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(summary=summaries,node_reuse=reuse,errors=errors),indent=2))


if __name__=='__main__':main()
