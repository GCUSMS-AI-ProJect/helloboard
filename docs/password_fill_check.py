"""Saved-password UI regression with fake radio and isolated config only."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from test_wifi import FakeNetwork, TestAuthenticator
from configuration import ConfigStore, DEFAULT_CONFIG
from controller import WifiController
from wifi import create_app
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp) / 'wifi.yaml')
    config = deepcopy(DEFAULT_CONFIG)
    config.update(mode='lan', lan={'ssid': 'First', 'password': 'first-example-secret'},
        networks=[{'ssid': 'First', 'password': 'first-example-secret'},
                  {'ssid': 'Other', 'password': 'other-example-secret'},
                  {'ssid': 'Guest', 'password': ''}])
    store.save(config)
    radio = FakeNetwork()
    radio.state = dict(connected=True, mode='lan', ssid='First', address='192.168.1.20', uuid='fake')
    controller = WifiController(store, radio)
    controller.phase = 'ready'
    submissions = []
    controller.request = lambda payload: submissions.append(payload)
    auth = TestAuthenticator()
    app = create_app(controller, authenticator=auth)
    server = make_server('127.0.0.1', 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':1280, 'height':900}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def reload():
                page.goto(f'http://127.0.0.1:{server.server_port}/wifi_config')
                expect(page.locator('#password')).to_have_value('••••••••')
                expect(page.locator('#password')).to_have_attribute('type', 'password')
                expect(page.locator('#scan-button')).to_be_enabled()
            def select(name):
                page.locator('#saved-network-toggle').click()
                page.locator('#saved-network-menu [role="option"]').filter(has_text=name).click()
            def submit():
                page.locator('#connect-button').click()
                page.locator('#confirm-switch').click()
                expect(page.locator('#confirm-dialog')).not_to_be_visible()
            reload()
            assert not auth.calls
            submit()
            assert submissions[-1] == dict(mode='lan', ssid='First', password=None)
            reload()
            select('Other')
            expect(page.locator('#password')).to_have_value('••••••••')
            page.locator('#show-password').click()
            expect(page.locator('#authorize-dialog')).to_be_visible()
            page.locator('#auth-password').fill('system-secret')
            page.locator('#authorize-submit').click()
            expect(page.locator('#password')).to_have_value('other-example-secret')
            expect(page.locator('#password')).to_have_attribute('type', 'text')
            page.locator('#show-password').click()
            expect(page.locator('#password')).to_have_attribute('type', 'password')
            # Revoking the browser grant clears an already loaded secret even while hidden.
            app.config['SECRET_KEY'] = 'different-service-key'
            page.evaluate('refreshStatus()')
            expect(page.locator('#password')).to_have_value('••••••••')
            reload()
            page.locator('#password').focus()
            page.keyboard.press('End')
            page.keyboard.type('replacement-example')
            page.evaluate('refreshStatus()')
            expect(page.locator('#password')).to_have_value('replacement-example')
            submit()
            assert submissions[-1]['password'] == 'replacement-example'
            reload()
            page.locator('#ssid').fill('NewNetwork')
            expect(page.locator('#password')).to_have_value('')
            page.locator('#ssid').fill('Other')
            expect(page.locator('#password')).to_have_value('••••••••')
            page.locator('#open-network').check()
            expect(page.locator('#password')).to_have_value('')
            expect(page.locator('#password')).to_be_disabled()
            page.locator('#open-network').uncheck()
            expect(page.locator('#password')).to_have_value('••••••••')
            select('Guest')
            expect(page.locator('#password')).to_have_value('')
            expect(page.locator('#open-network')).to_be_checked()
            submit()
            assert submissions[-1]['password'] == ''
            assert radio.calls == [], 'Browser test must never activate a radio'
            assert store.load() == config
            assert errors == [], errors
            browser.close()
    finally:
        server.shutdown()
print('PASS: initial/history/manual SSID fill; reveal requires auth; revoked grant remasks; typed input survives polling; open network and saved/null submit; no config/radio mutation')
