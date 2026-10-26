"""Read-only browser check against the preview service; never switches Wi-Fi."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parent
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    # Bypass CSP only in this automation context so axe can be injected.
    context = browser.new_context(reduced_motion='reduce', bypass_csp=True)
    context.add_init_script("""for (const [name,value] of [['layout','compact'],['sidebar','expanded']]) {
        if (localStorage.getItem('helloboard.'+name) === null && localStorage.getItem('hellowifi.'+name) === null)
            localStorage.setItem('hellowifi.'+name,value);
    }""")
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:8090/wifi_config', wait_until='networkidle')
    expect(page).to_have_url('http://127.0.0.1:8090/wifi_config')
    expect(page.locator('.sidebar-nav .nav-item.active')).to_have_attribute('href','/wifi_config')
    page.evaluate('document.fonts.ready')
    assert page.evaluate("localStorage.getItem('helloboard.layout')") == 'compact'
    assert page.evaluate("localStorage.getItem('helloboard.sidebar')") == 'expanded'
    assert page.evaluate("localStorage.getItem('hellowifi.layout')") is None
    assert page.evaluate("localStorage.getItem('hellowifi.sidebar')") is None
    expect(page.locator('#notice')).to_contain_text('预览模式')
    page.wait_for_function("!document.querySelector('#scan-button').classList.contains('spinning')", timeout=25000)
    expect(page.locator('#connect-button')).to_be_disabled()
    for selector in ['#ssid','#password']:
        style = page.locator(selector).evaluate("e=>{const s=getComputedStyle(e);return {top:s.borderTopWidth,right:s.borderRightWidth,bottom:s.borderBottomWidth,left:s.borderLeftWidth,radius:s.borderRadius}}")
        assert style == {'top':'0px','right':'0px','bottom':'1px','left':'0px','radius':'0px'}, style
        page.locator(selector).focus()
        assert page.locator(selector).evaluate('e=>getComputedStyle(e).boxShadow') != 'none'
    expect(page).to_have_title('HelloBoard · WiFi 管理')
    expect(page.locator('.sidebar .brand')).to_have_text('HelloBoard')
    expect(page.locator('.desktop-heading .page-title')).to_have_text('WiFi 管理')
    expect(page.locator('.topbar-actions button')).to_have_count(3)
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('#sidebar-toggle')).to_have_text('')
    expect(page.locator('#sidebar-toggle svg')).to_have_count(1)
    page.locator('.desktop-heading .page-title').click()
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded', 'true')
    expect(page.locator('.card')).to_have_count(1)
    expect(page.locator('.sidebar [data-panel="ap"]')).to_have_count(0)
    expect(page.locator('[data-panel="ap"]')).to_have_count(1)
    expect(page.locator('#connect-button svg')).to_have_count(0)
    session = context.new_cdp_session(page)
    session.send('DOM.enable')
    session.send('CSS.enable')
    # Inspect actual rendered Latin and Chinese glyphs, not just CSS declarations.
    page.evaluate("""() => {const e=document.createElement('div');e.id='font-probe';e.textContent='WiFi 管理 HelloBoard 192.168';document.body.append(e)}""")
    page.evaluate('document.fonts.ready')
    doc = session.send('DOM.getDocument')
    node = session.send('DOM.querySelector', {'nodeId': doc['root']['nodeId'], 'selector':'#font-probe'})
    fonts = session.send('CSS.getPlatformFontsForNode', {'nodeId': node['nodeId']})['fonts']
    assert any(f['isCustomFont'] and 'Inter' in f['familyName'] for f in fonts), fonts
    assert any(f['isCustomFont'] and 'Noto' in f['familyName'] for f in fonts), fonts
    page.locator('#font-probe').evaluate('(e)=>e.remove()')
    resources = page.evaluate("() => performance.getEntriesByType('resource').filter(r=>r.name.endsWith('.woff2')).map(r=>({name:r.name.split('/').pop(),bytes:r.encodedBodySize}))")
    assert not any('fallback' in r['name'] for r in resources), resources
    reports = {'rendered_fonts': fonts, 'initial_fonts': resources}
    page.set_viewport_size({'width':1280,'height':900})
    page.locator('#ssid').fill('Keep my unsaved Wi-Fi')
    page.locator('#password').fill('unsaved-test-secret')
    network_requests = []
    page.on('request', lambda request: network_requests.append(request.url)
            if any(endpoint in request.url for endpoint in ['/api/connect','/api/scan']) else None)
    page.locator('#sidebar-toggle').click()
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded','false')
    assert page.locator('.sidebar').bounding_box()['width'] == 76
    assert page.locator('.app-frame').bounding_box()['x'] == 76
    page.locator('.sidebar-nav .nav-item.active').hover()
    expect(page.locator('.sidebar-nav .nav-item.active .nav-tooltip')).to_be_visible()
    expect(page.locator('.sidebar-nav .nav-item.active .nav-tooltip')).to_have_text('WiFi 管理')
    page.locator('.sidebar-nav .nav-item.active').focus()
    page.keyboard.press('Escape')
    expect(page.locator('.sidebar-nav .nav-item.active .nav-tooltip')).not_to_be_visible()
    page.locator('#sidebar-toggle').focus()
    page.keyboard.press('Shift+Tab')
    expect(page.locator('.sidebar-nav .nav-item.active .nav-tooltip')).to_be_visible()
    page.locator('#language-toggle').click()
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-label','Expand sidebar')
    expect(page.locator('.sidebar-nav .nav-item.active .nav-tooltip')).to_have_text('WiFi manager')
    page.locator('#language-toggle').click()
    expect(page.locator('#ssid')).to_have_value('Keep my unsaved Wi-Fi')
    expect(page.locator('#password')).to_have_value('unsaved-test-secret')
    page.screenshot(path=str(OUT/'sidebar-collapsed.png'))
    page.reload(wait_until='networkidle')
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded','false')
    assert page.locator('.sidebar').bounding_box()['width'] == 76
    page.wait_for_function("!document.querySelector('#scan-button').classList.contains('spinning')", timeout=25000)
    network_requests.clear()
    page.locator('#sidebar-toggle').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#sidebar-toggle')).to_have_attribute('aria-expanded','true')
    assert page.locator('.sidebar').bounding_box()['width'] == 216
    assert not network_requests, network_requests
    reports['sidebar'] = {'collapsed_width':76,'tooltip_hover_and_keyboard':True,
                          'escape_dismisses':True,'state_persisted':True,'form_preserved':True,
                          'no_network_operations':True}
    expect(page.locator('.sidebar [data-panel="help"]')).to_have_count(0)
    expect(page.locator('[data-panel="help"]')).to_have_count(1)
    desktop_layouts = []
    for width, height in [(1024,768),(1280,720),(1366,768),(1440,900),(1920,1080)]:
        page.set_viewport_size({'width':width,'height':height})
        brand = page.locator('.sidebar .brand').bounding_box()
        sidebar = page.locator('.sidebar').bounding_box()
        assert brand['x']+brand['width'] <= sidebar['x']+sidebar['width']-12, (width,brand,sidebar)
        for density in ['compact','relaxed']:
            page.evaluate('(layout) => setLayout(layout,false)',density)
            for mode in ['lan','ap']:
                page.locator('#mode-'+mode).click()
                metrics = page.evaluate("""() => {
                    const config=document.querySelector('.settings'),nearby=document.querySelector('.nearby');
                    const button=document.querySelector('#connect-button').getBoundingClientRect();
                    const scan=document.querySelector('#scan-button').getBoundingClientRect();
                    const count=document.querySelector('#scan-message').getBoundingClientRect();
                    return {pageOverflow:document.documentElement.scrollHeight>innerHeight+1,configOverflow:config.scrollHeight>config.clientHeight+1,buttonBottom:button.bottom,configY:config.getBoundingClientRect().y,nearbyY:nearby.getBoundingClientRect().y,scanRightOfCount:scan.left>=count.right && Math.abs(scan.y+scan.height/2-count.y-count.height/2)<1,windowHeight:innerHeight};
                }""")
                assert not metrics['configOverflow'],(width,height,density,mode,metrics)
                if density=='compact':
                    assert not metrics['pageOverflow'],(width,height,density,mode,metrics)
                    assert metrics['buttonBottom'] <= height,metrics
                assert metrics['configY']==metrics['nearbyY'] and metrics['scanRightOfCount'],metrics
                desktop_layouts.append({'width':width,'height':height,'density':density,'mode':mode,**metrics})
        if width in [1280,1366]:
            page.evaluate('() => setLayout("compact",false)')
            page.screenshot(path=str(OUT/f'one-screen-{width}.png'))
    page.set_viewport_size({'width':1280,'height':900})
    page.evaluate('setLayout("compact",false);setMode("lan")')
    if page.locator('.network-row').count()>10:
        page.locator('#network-list').focus()
        page.keyboard.press('PageDown')
        page.wait_for_function("document.querySelector('#network-list').scrollTop > 0",timeout=5000)
        assert page.evaluate('document.scrollingElement.scrollTop') == 0
        # Native PageDown scrolls over several frames, even in reduced motion.
        page.evaluate("""() => new Promise(resolve => {
            let previous=-1, stable=0;
            function settled(){const top=document.querySelector('#network-list').scrollTop;stable=top===previous?stable+1:0;previous=top;if(stable>=3)resolve();else requestAnimationFrame(settled);}
            requestAnimationFrame(settled);
        })""")
        page.locator('#mode-lan').click()
        page.locator('#network-list').evaluate("e=>e.scrollTo({top:0,behavior:'instant'})")
        page.wait_for_function("document.querySelector('#network-list').scrollTop === 0")
    reports['desktop_one_screen'] = desktop_layouts
    for label, width, height in [('desktop', 1280, 900), ('wide', 1920, 1080), ('tablet', 768, 900), ('mobile', 375, 900), ('landscape', 812, 375), ('narrow', 320, 900)]:
        page.set_viewport_size({'width': width, 'height': height})
        if page.locator('.mobile-brand').is_visible():
            expect(page.locator('.mobile-brand .brand')).to_have_text('HelloBoard')
            brand = page.locator('.mobile-brand .brand').bounding_box()
            actions = page.locator('.topbar-actions').bounding_box()
            assert brand['x']+brand['width'] <= actions['x']-4, (label,brand,actions)
        page.screenshot(path=str(OUT / f'{label}.png'), full_page=True)
        page.locator('#language-toggle').scroll_into_view_if_needed()
        language_bounds = page.locator('#language-toggle').bounding_box()
        settings_bounds = page.locator('#style-settings').bounding_box()
        page.locator('#language-toggle').click()
        assert page.locator('#language-toggle').bounding_box() == language_bounds, label
        assert page.locator('#style-settings').bounding_box() == settings_bounds, label
        page.locator('#language-toggle').click()
        assert page.locator('#language-toggle').bounding_box() == language_bounds, label
        if page.locator('#connection-password-area').is_visible():
            name = page.locator('#connection-name').bounding_box()
            secret = page.locator('#connection-password-area').bounding_box()
            address = page.locator('.address').bounding_box()
            assert secret['y'] >= name['y'] + name['height'], label
            assert address['y'] >= secret['y'] + secret['height'], label
            assert abs(address['x']-name['x']) < 1, label
        expect(page.locator('.address [data-i18n="设备地址"]')).to_have_count(0)
        overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not overflow, label
        text_sizes = page.evaluate('''() => [...document.querySelectorAll('p,a,button,input,label,dt,dd,span,h1,h2,strong')].filter(e=>e.getClientRects().length && e.textContent.trim() && parseFloat(getComputedStyle(e).fontSize)<16).map(e=>({tag:e.tagName,text:e.textContent,size:getComputedStyle(e).fontSize}))''')
        assert not text_sizes, text_sizes
        if Path('/tmp/helloboard-axe.min.js').exists():
            page.add_script_tag(path='/tmp/helloboard-axe.min.js')
            violations = page.evaluate("async()=> (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.target)}))")
        else: violations = ['axe unavailable']
        reports[label] = {'overflow': overflow, 'small_text': text_sizes, 'axe': violations}
        page.locator('#help-button').click()
        expect(page.locator('#side-panel')).to_be_visible()
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), label
        if label == 'desktop': page.screenshot(path=str(OUT / 'help-drawer.png'))
        page.keyboard.press('Escape')
        expect(page.locator('#side-panel')).not_to_be_visible()
    # The selected background moves; neither touch target changes its bounds.
    page.set_viewport_size({'width':1280,'height':900})
    for selected in ['ap','lan','ap','lan']:
        button = page.locator('#mode-'+selected)
        button.scroll_into_view_if_needed()
        before = button.bounding_box()
        button.hover(); page.mouse.down()
        assert button.bounding_box() == before
        page.mouse.up()
        expect(page.locator('.mode-switch')).to_have_attribute('data-mode',selected)
        expect(button).to_have_attribute('aria-pressed','true')
        assert button.bounding_box() == before
        assert button.evaluate('e=>getComputedStyle(e).color') == 'rgb(255, 255, 255)'
    reports['pill_targets_do_not_move'] = True
    page.locator('#mode-ap').click()
    expect(page.locator('#ap-fields')).to_be_visible()
    expect(page.locator('#connect-button')).to_have_text('开启设备热点')
    bounds = page.locator('#mode-ap svg').evaluate('e=>{const b=e.getBBox();return {x:b.x,y:b.y,right:b.x+b.width,bottom:b.y+b.height}}')
    assert bounds['x'] >= 1 and bounds['y'] >= 1 and bounds['right'] <= 23 and bounds['bottom'] <= 23, bounds
    page.locator('#mode-lan').click()
    page.locator('#password').fill('browser-test-password')
    page.locator('#show-password').click()
    expect(page.locator('#password')).to_have_attribute('type', 'text')
    page.locator('#show-password').click()
    expect(page.locator('#password')).to_have_attribute('type', 'password')
    # Language changes preserve the form and require no navigation/API round trip.
    page.locator('#ssid').fill('Language test network')
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    page.locator('#language-toggle').click()
    expect(page.locator('html')).to_have_attribute('lang', 'en')
    expect(page.locator('h1')).to_have_count(0)
    expect(page.locator('.sidebar-nav [aria-current="page"] .nav-label')).to_have_text('WiFi manager')
    expect(page.locator('#mode-ap')).to_have_text('Hotspot')
    expect(page.locator('#password')).to_have_value('browser-test-password')
    expect(page.locator('#ssid')).to_have_value('Language test network')
    expect(page.locator('#notice')).to_contain_text('Preview:')
    untranslated = page.locator('[data-i18n]').evaluate_all("els=>els.filter(e=>e.getClientRects().length && /[\\u4e00-\\u9fff]/.test(e.textContent)).map(e=>e.textContent)")
    assert not untranslated, untranslated
    page.set_viewport_size({'width':1280,'height':900})
    page.screenshot(path=str(OUT/'english.png'), full_page=True)
    page.locator('#help-button').click()
    expect(page.locator('#panel-title')).to_have_text('Help')
    expect(page.locator('#help-content h3').first).to_have_text('How do I access the device after switching networks?')
    page.keyboard.press('Escape')
    expect(page.locator('#side-panel')).not_to_be_visible()
    page.locator('#mode-ap').click()
    page.locator('.ap-settings-link').click()
    expect(page.locator('#ap-auth-state')).to_have_text('Verify your system account when saving')
    page.screenshot(path=str(OUT/'ap-password-drawer.png'), full_page=True)
    page.keyboard.press('Escape')
    expect(page.locator('#side-panel')).not_to_be_visible()
    page.locator('#language-toggle').click()
    expect(page.locator('h1')).to_have_count(0)
    expect(page.locator('.sidebar-nav [aria-current="page"] .nav-label')).to_have_text('WiFi 管理')
    reports['language_toggle_preserves_form'] = True
    reports['hotspot_icon_bounds'] = bounds
    for layout, title in [('relaxed','宽松'),('compact','紧凑')]:
        page.locator('#style-settings').click()
        expect(page.locator('#panel-title')).to_have_text('样式设置')
        page.locator('#layout-'+layout).click()
        expect(page.locator('html')).to_have_attribute('data-layout',layout)
        expect(page.locator('#layout-'+layout)).to_have_attribute('aria-pressed','true')
        page.screenshot(path=str(OUT / ('style-'+layout+'.png')))
        page.keyboard.press('Escape')
        expect(page.locator('#side-panel')).not_to_be_visible()
        for width in [320,375,768,1280,1920]:
            page.set_viewport_size({'width':width,'height':900})
            assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), (layout,width)
        page.set_viewport_size({'width':1280,'height':900})
        page.screenshot(path=str(OUT / ('layout-'+layout+'.png')),full_page=True)
        page.reload()
        expect(page.locator('html')).to_have_attribute('data-layout',layout)
        expect(page.locator('#status-title')).not_to_have_text('正在读取网络')
    # The real preview only opens/cancels verification; no credentials are submitted.
    if page.locator('#connection-password-area').is_visible():
        page.locator('#reveal-password').click()
        expect(page.locator('#authorize-dialog')).to_be_visible()
        expect(page.locator('#authorize-title')).to_have_text('验证登录')
        expect(page.locator('#authorize-form .helper')).to_have_count(0)
        page.screenshot(path=str(OUT / 'authorization-dialog.png'))
        page.locator('#authorize-cancel').click()
        expect(page.locator('#authorize-dialog')).not_to_be_visible()
        expect(page.locator('#connection-secret')).to_have_text('••••••••')
    reports['two_layouts_responsive_and_persisted'] = True
    # Inspect real animation as well as the reduced-motion layout checks.
    page.emulate_media(reduced_motion='no-preference')
    sidebar_motion = page.locator('.sidebar').evaluate('e=>({duration:getComputedStyle(e).transitionDuration,easing:getComputedStyle(e).transitionTimingFunction})')
    assert sidebar_motion['duration'] == '0.36s', sidebar_motion
    page.locator('#sidebar-toggle').click()
    page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().width === 76")
    page.locator('#sidebar-toggle').click()
    page.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().width === 216")
    reports['sidebar']['motion'] = sidebar_motion
    page.locator('#mode-lan').click()
    page.locator('#mode-ap').click()
    page.wait_for_function("() => {const s=getComputedStyle(document.querySelector('.mode-switch'),'::before');return Math.abs(new DOMMatrixReadOnly(s.transform).m41 - parseFloat(s.width))<.1}")
    pill = page.locator('.mode-switch').evaluate("e=>{const s=getComputedStyle(e,'::before');return {duration:s.transitionDuration,radius:s.borderRadius,background:s.backgroundColor}}")
    assert pill['duration'] == '0.34s' and pill['background'] == 'rgb(29, 29, 31)', pill
    page.screenshot(path=str(OUT/'mode-capsule.png'),full_page=True)
    page.locator('#mode-lan').click()
    reports['mode_pill_motion'] = pill
    page.locator('#help-button').click()
    animation = page.locator('#side-panel').evaluate('e=>({duration:getComputedStyle(e).animationDuration,easing:getComputedStyle(e).animationTimingFunction})')
    assert animation['duration'] == '0.42s', animation
    page.keyboard.press('Escape')
    expect(page.locator('#side-panel')).not_to_be_visible()
    if page.locator('#connection-password-area').is_visible():
        page.locator('#reveal-password').click()
        expect(page.locator('#authorize-dialog')).to_be_visible()
        enter = page.locator('#authorize-dialog').evaluate('e=>getComputedStyle(e).animationName')
        assert enter == 'modal-in', enter
        page.locator('#authorize-cancel').click()
        exit = page.locator('#authorize-dialog').evaluate('e=>({open:e.open,name:getComputedStyle(e).animationName})')
        assert exit['open'] and exit['name'] == 'modal-out', exit
        expect(page.locator('#authorize-dialog')).not_to_be_visible()
        reports['modal_motion'] = {'enter':enter,'exit':exit['name']}
    reports['language_button_fixed_bounds'] = True
    context.grant_permissions(['clipboard-read','clipboard-write'])
    page.locator('#copy-address').click()
    expect(page.locator('#toast')).to_have_text('设备地址已复制。')
    page.wait_for_function("getComputedStyle(document.querySelector('#toast')).opacity === '1'")
    # The reserved scrollbar gutter is outside the fixed positioning area.
    feedback = page.locator('#toast').evaluate("e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {centerX:r.x+r.width/2,centerY:r.y+r.height/2,width:document.documentElement.getBoundingClientRect().width,height:innerHeight,pointerEvents:s.pointerEvents,duration:s.transitionDuration}}")
    assert abs(feedback['centerX']-feedback['width']/2)<1 and abs(feedback['centerY']-feedback['height']/2)<1, feedback
    assert feedback['duration']=='0.12s' and feedback['pointerEvents']=='none',feedback
    page.screenshot(path=str(OUT/'centered-feedback.png'))
    page.wait_for_function("!document.querySelector('#toast').classList.contains('visible') && !document.querySelector('#toast').hidden")
    # A second copy during fade-out must cancel the earlier hide timer.
    page.locator('#copy-address').click()
    page.wait_for_function("getComputedStyle(document.querySelector('#toast')).opacity === '1'")
    expect(page.locator('#toast')).not_to_be_visible(timeout=2500)
    assert page.evaluate('document.activeElement.id') == 'copy-address'
    reports['centered_copy_feedback'] = feedback
    reports['network_password_ip_stacked'] = True
    reports['drawer_animation'] = animation
    assert not errors, errors
    reports['javascript_errors'] = errors
    (OUT / 'browser-report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    browser.close()
