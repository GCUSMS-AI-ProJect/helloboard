"""Check process interactions in Chromium. All process writes are intercepted.

The live service is only read. Fixtures exercise confirmations without signalling
any device process; real pidfd execution is covered with disposable test children.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    page = browser.new_page(viewport={'width':1440,'height':1000}, reduced_motion='reduce')
    errors, writes = [], []
    page.on('pageerror',lambda error: errors.append(str(error)))
    fixture = dict(items=[dict(pid=40000+i,started=1000+i,name=f'demo-{i:02d}',cpu_percent=24-i,memory=(24-i)*1024**2,selectable=i!=0,reason='受保护的系统进程' if i==0 else '') for i in range(24)], preview=False,supported=True,max_batch=32)
    replies = []
    def write(route):
        payload=route.request.post_data_json
        assert route.request.headers.get('x-csrf-token')
        writes.append(payload)
        status,body=replies.pop(0)
        route.fulfill(status=status,json=body)
    page.route('**/api/processes/terminate',write)
    page.goto('http://127.0.0.1:8090/system_status')
    page.wait_for_selector('#process-list tr[data-key]')
    # The actual preview must never offer a destructive submission.
    page.locator('#process-list .process-more:not(:disabled)').first.click()
    expect(page.locator('#process-submit')).to_be_disabled()
    expect(page.locator('#process-dialog-error')).to_have_text('预览模式不允许终止进程。')
    page.locator('#process-cancel').click()
    expect(page.locator('#process-dialog')).not_to_be_visible()
    assert not writes
    page.route('**/api/processes',lambda route:route.fulfill(json=fixture))
    page.locator('#refresh-status').click()
    expect(page.locator('#process-count')).to_have_text('共 24 个')
    expect(page.locator('#process-list tr[data-key]')).to_have_count(6)
    expect(page.locator('#process-list tr').first.locator('input')).to_be_disabled()
    more=page.locator('#process-list tr').nth(1).locator('.process-more')
    page.mouse.move(0,0)
    expect(more).to_have_css('opacity','0')
    more.locator('..').hover()
    expect(more).to_have_css('opacity','1')
    more.focus()
    expect(more).to_have_css('opacity','1')
    page.emulate_media(reduced_motion='no-preference')
    assert '0.16s' in more.evaluate('e=>getComputedStyle(e).transitionDuration')
    page.emulate_media(reduced_motion='reduce')
    page.locator('#process-search').fill('demo-02')
    expect(page.locator('#process-list tr[data-key]')).to_have_count(1)
    page.locator('#process-list input').check()
    page.locator('#sort-memory').click()
    expect(page.locator('#process-list input')).to_be_checked()
    page.locator('#process-list .process-more').click()
    expect(page.locator('#process-dialog')).to_be_visible()
    expect(page.locator('#process-username')).to_have_value('ubuntu')
    expect(page.locator('#process-method button[data-action=terminate]')).to_have_attribute('aria-pressed','true')
    replies.append((403,dict(error='系统用户名或密码不正确。')))
    page.locator('#process-password').fill('wrong-test-only')
    page.locator('#process-submit').click()
    expect(page.locator('#process-dialog-error')).to_have_text('系统用户名或密码不正确。')
    expect(page.locator('#process-password')).to_have_value('')
    expect(page.locator('#process-submit')).to_be_enabled()
    replies.append((200,dict(results=[dict(pid=40002,started=1002,status='sent',message='已发送退出请求')])))
    page.locator('#process-password').fill('correct-test-only')
    page.locator('#process-submit').click()
    expect(page.locator('#process-dialog')).not_to_be_visible()
    expect(page.locator('#toast')).to_have_text('已向 1 个进程发送退出请求')
    assert len(writes)==2 and writes[1]['targets']==[dict(pid=40002,started=1002)]
    assert writes[1]['action']=='terminate'
    expect(page.locator('#process-list input')).not_to_be_checked()
    # Cross-page selections survive polling and filtering.
    page.locator('#process-search').fill('')
    page.locator('#sort-cpu').click()
    page.locator('#process-list tr').nth(1).locator('input').check()
    page.locator('#process-next').click()
    page.locator('#process-list tr').first.locator('input').check()
    expect(page.locator('#process-count')).to_have_text('已选 2 · 共 24 个')
    page.locator('#refresh-status').click()
    expect(page.locator('#process-count')).to_have_text('已选 2 · 共 24 个')
    page.locator('#terminate-selected').click()
    expect(page.locator('#process-targets li')).to_have_count(2)
    page.locator('#process-method button[data-action=kill]').click()
    expect(page.locator('#process-method-note')).to_contain_text('未保存的数据')
    replies.append((200,dict(results=[dict(pid=40001,started=1001,status='sent',message='已发送强制终止信号'),dict(pid=40006,started=1006,status='changed',message='进程已变化，请重新选择。')])))
    page.locator('#process-password').fill('fresh-test-only')
    page.locator('#process-submit').click()
    expect(page.locator('#process-results')).to_be_visible()
    expect(page.locator('#process-results p')).to_have_count(2)
    expect(page.locator('#process-password')).to_have_value('')
    assert writes[-1]['action']=='kill' and len(writes[-1]['targets'])==2
    expect(page.locator('#process-submit')).to_have_text('关闭')
    page.evaluate('() => HelloBoardI18n.toggle()')
    expect(page.locator('#process-submit')).to_have_text('Close')
    expect(page.locator('#process-results p').last).to_contain_text('The process has changed')
    page.locator('#process-submit').click()
    expect(page.locator('#process-dialog')).not_to_be_visible()
    page.locator('#process-clear').click()
    page.locator('#process-prev').click()
    page.locator('#process-select-all').check()
    expect(page.locator('#process-count')).to_have_text('5 selected · 24 total')
    page.locator('#process-search').fill('missing-name')
    expect(page.locator('#process-list')).to_contain_text('No matching processes')
    page.locator('#process-clear').click()
    page.locator('#process-search').fill('40023')
    expect(page.locator('#process-list tr[data-key]')).to_have_count(1)
    page.locator('#process-search').fill('')
    page.locator('#language-toggle').click()
    expect(page.locator('#toast')).not_to_be_visible(timeout=4000)
    for width in [320,375,768,1024,1440,1920]:
        page.set_viewport_size({'width':width,'height':1000})
        page.locator('.process-card').scroll_into_view_if_needed()
        assert page.evaluate('() => document.documentElement.scrollWidth <= innerWidth'),width
        assert page.locator('.process-table-wrap').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),width
        assert page.locator('.process-tools').evaluate('e=>e.scrollWidth<=e.clientWidth+1'),width
        page.screenshot(path=str(OUT/f'process-{width}.png'))
    touch_context=browser.new_context(viewport={'width':375,'height':850},is_mobile=True,has_touch=True,reduced_motion='reduce')
    touch=touch_context.new_page()
    touch.route('**/api/processes',lambda route:route.fulfill(json=fixture))
    touch.route('**/api/processes/terminate',lambda route:route.abort())
    touch.goto('http://127.0.0.1:8090/system_status')
    touch.wait_for_selector('#process-list tr[data-key]')
    touch_button=touch.locator('#process-list .process-more:not(:disabled)').first
    expect(touch_button).to_have_css('opacity','1')
    touch_button.tap()
    expect(touch.locator('#process-dialog')).to_be_visible()
    touch.locator('#process-cancel').tap()
    expect(touch.locator('#process-dialog')).not_to_be_visible()
    touch_context.close()
    assert not errors,errors
    assert len(writes)==3
    report=dict(search_by_name_and_pid=True,protected_rows=True,hover_motion=True,touch_and_keyboard=True,cross_page_selection=True,
        password_rechecked_and_cleared=True,normal_and_force_actions=True,partial_results=True,
        preview_read_only=True,responsive_widths=[320,375,768,1024,1440,1920],no_real_process_writes=True,js_errors=errors)
    (OUT/'process-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    browser.close()
