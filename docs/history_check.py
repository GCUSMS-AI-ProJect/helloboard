"""Verify real history survives reloads, closed browsers, manual refresh and service restart."""
import json
from pathlib import Path
import subprocess
import time
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    context=browser.new_context(reduced_motion='reduce')
    page=context.new_page(); errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def open_history(action):
        with page.expect_response(lambda response:'/api/system' in response.url and '?' not in response.url) as info:
            action()
        response=info.value
        assert response.status==200
        return response.json()
    first=open_history(lambda:page.goto('http://127.0.0.1:8090/'))
    page.wait_for_timeout(6400)
    before=context.request.get('http://127.0.0.1:8090/api/system').json()
    assert len(before['history'])>=3
    refreshed=open_history(lambda:page.reload())
    assert refreshed['history_id']==before['history_id']
    shared={point['time']:point for point in refreshed['history']}
    assert all(shared[point['time']]==point for point in before['history'])
    expect(page.locator('#usage-empty')).not_to_be_visible()
    expect(page.locator('#traffic-empty')).not_to_be_visible()
    page.close()
    # No requests occur during this period: the service must still collect.
    time.sleep(4.4)
    another=browser.new_context(reduced_motion='reduce')
    page=another.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
    reopened=open_history(lambda:page.goto('http://127.0.0.1:8090/system_status'))
    assert reopened['history_id']==refreshed['history_id']
    assert len(reopened['history'])>=len(refreshed['history'])+2
    assert reopened['history'][0]==refreshed['history'][0]
    page.wait_for_timeout(2300)
    with page.expect_response(lambda response:'/api/system?' in response.url) as info:
        page.locator('#refresh-status').click()
    delta=info.value.json()
    assert delta['history_id']==reopened['history_id']
    assert delta['sampled_at']>=reopened['sampled_at']
    expect(page.locator('#refresh-status')).to_be_enabled()
    expect(page.locator('#usage-empty')).not_to_be_visible()
    # Restart only the read-only preview; an already open browser must resync
    # with its old cursor, instead of mixing histories or losing future samples.
    old_generation=reopened['history_id']
    subprocess.run(['systemctl','--user','restart','helloboard-preview.service'],check=True)
    with page.expect_response(lambda response:'/api/system' in response.url and response.status==200,timeout=15000) as info:
        pass
    reset=info.value.json()
    assert reset['history_id']!=old_generation
    assert reset['history']
    assert reset['history'][0]['time']>reopened['history'][-1]['time']
    expect(page.locator('#update-state')).to_have_text('实时更新',timeout=10000)
    page.wait_for_timeout(4300)
    expect(page.locator('#usage-empty')).not_to_be_visible()
    assert not errors,errors
    report=dict(refresh_preserves_history=True,closed_browsers_keep_sampling=True,
        manual_refresh_preserves_history=True,service_restart_resyncs=True,
        restored_samples=len(reopened['history']),incremental_samples=len(delta['history']),js_errors=errors)
    (OUT/'history-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    browser.close()
