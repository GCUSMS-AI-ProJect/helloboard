"""Exercise full browser connect/failure flows using an isolated fake radio."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configuration import ConfigStore, DEFAULT_CONFIG
from controller import WifiController
from network import NetworkError
from wifi import create_app
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect


class TestRadio:
    def __init__(self):
        self.fail = False
        self.scan_started = threading.Event()
        self.scan_release = threading.Event(); self.scan_release.set()
        self.activations = []
        self.state = {'connected': True, 'mode': 'ap', 'ssid': 'hellosms', 'address': '192.168.11.17', 'uuid': 'fake'}
    def snapshot(self): return deepcopy(self.state)
    def scan(self):
        self.scan_started.set()
        if not self.scan_release.wait(timeout=10): raise NetworkError("Test scan timeout")
        return {'networks': [{'ssid': '<script>alert(1)</script>', 'signal': 90, 'security': 'WPA2', 'active': False, 'supported': True},
                             {'ssid': 'Guest', 'signal': 50, 'security': '--', 'active': False, 'supported': True}], 'warning': ''}
    def activate(self, mode, config):
        self.activations.append(mode)
        if mode == 'lan' and self.fail: raise NetworkError('Test connection failure')
        self.state = {'connected': True, 'mode': mode, 'ssid': config[mode]['ssid'],
                      'address': config['ap']['address'] if mode == 'ap' else '192.168.1.20', 'uuid': 'fake'}
        return self.state


class TestAuthenticator:
    username = 'ubuntu'
    def __init__(self): self.calls = []
    def verify(self, password):
        self.calls.append(password)
        if password != 'system-secret': raise PermissionError('系统登录密码不正确或账户不可用。')


with tempfile.TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp) / 'wifi.yaml')
    radio = TestRadio()
    controller = WifiController(store, radio)
    controller.phase = 'ready'
    authenticator = TestAuthenticator()
    server = make_server('127.0.0.1', 8091, create_app(controller, authenticator=authenticator), threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
            page = browser.new_page(viewport={'width':375,'height':900},reduced_motion='reduce')
            errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8091/wifi_config')
            expect(page.locator('#login-dialog')).to_have_count(0)
            expect(page.locator('#lock-button')).to_have_count(0)
            expect(page.locator('.network-row')).to_have_count(2)
            expect(page.locator('.network-row strong').first).to_have_text('<script>alert(1)</script>')
            expect(page.locator('.signal-icon').first).to_have_attribute('data-level', '3')
            expect(page.locator('.signal-icon').nth(1)).to_have_attribute('data-level', '2')
            expect(page.locator('#help-content')).not_to_be_visible()
            page.locator('#help-button').click()
            expect(page.locator('#side-panel')).to_be_visible()
            expect(page.locator('#help-content')).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.locator('#side-panel')).not_to_be_visible()
            page.locator('#mode-ap').click()
            page.locator('#reveal-ap-password').click()
            expect(page.locator('#authorize-dialog')).to_be_visible()
            page.locator('#authorize-cancel').click()
            expect(page.locator('#authorize-dialog')).not_to_be_visible()
            expect(page.locator('#reveal-ap-password')).to_have_attribute('aria-pressed', 'false')
            page.locator('.ap-settings-link').click()
            expect(page.locator('#ap-password')).to_have_value('')
            page.locator('#ap-password').fill('saved-ap-secret')
            page.locator('#save-ap-password').click()
            expect(page.locator('#authorize-dialog')).to_be_visible()
            page.locator('#auth-username').fill('other')
            page.locator('#auth-password').fill('system-secret')
            page.locator('#authorize-submit').click()
            expect(page.locator('#auth-error')).to_be_visible()
            page.locator('#auth-username').fill('ubuntu')
            page.locator('#auth-password').fill('incorrect')
            page.locator('#authorize-submit').click()
            expect(page.locator('#auth-error')).to_contain_text('系统登录密码不正确')
            expect(page.locator('#auth-password')).to_have_value('')
            assert store.load()['ap']['password'] == ''
            page.locator('#auth-password').fill('system-secret')
            page.locator('#authorize-submit').click()
            expect(page.locator('#authorize-dialog')).not_to_be_visible()
            expect(page.locator('#side-panel')).not_to_be_visible()
            assert store.load()['ap']['password'] == 'saved-ap-secret'
            restarted = WifiController(store, radio)
            assert restarted.config['ap']['password'] == 'saved-ap-secret'
            assert 'system-secret' not in store.path.read_text()
            page.locator('#reveal-ap-password').click()
            expect(page.locator('#ap-security')).to_have_text('saved-ap-secret')
            expect(page.locator('#authorize-dialog')).not_to_be_visible()
            page.evaluate('refreshStatus()')
            expect(page.locator('#ap-security')).to_have_text('saved-ap-secret')
            page.locator('#reveal-ap-password').click()
            expect(page.locator('#ap-security')).to_have_text('已设置')
            page.locator('#reveal-ap-password').click()
            expect(page.locator('#ap-security')).to_have_text('saved-ap-secret')
            page.locator('.ap-settings-link').click()
            page.locator('#ap-password').fill('second-ap-secret')
            page.locator('#save-ap-password').click()
            expect(page.locator('#side-panel')).not_to_be_visible()
            assert store.load()['ap']['password'] == 'second-ap-secret'
            expect(page.locator('#ap-security')).to_have_text('已设置')
            page.locator('#reveal-ap-password').click()
            expect(page.locator('#ap-security')).to_have_text('second-ap-secret')
            page.locator('#mode-lan').click()
            expect(page.locator('#reveal-ap-password')).to_have_attribute('aria-pressed', 'false')
            assert authenticator.calls == ['incorrect','system-secret']
            page.locator('.network-row').first.click()
            expect(page.locator('#ssid')).to_have_value('<script>alert(1)</script>')
            page.locator('#password').fill('new-password123')
            page.locator('#language-toggle').click()
            expect(page.locator('#connect-button')).to_have_text('Save & connect')
            page.locator('#connect-button').click()
            expect(page.locator('#confirm-dialog')).to_be_visible()
            page.locator('#confirm-switch').click()
            expect(page.locator('#status-title')).to_have_text('Connected to Wi-Fi',timeout=15000)
            page.locator('#reveal-password').click()
            expect(page.locator('#connection-secret')).to_have_text('new-password123')
            expect(page.locator('#authorize-dialog')).not_to_be_visible()
            page.locator('#reveal-password').click()
            expect(page.locator('#connection-secret')).to_have_text('••••••••')
            # Rotate the Flask signing key as a service restart would. Even an
            # already open tab must reauthorize and recover its stale CSRF token.
            server.app = create_app(controller, authenticator=authenticator)
            page.locator('#reveal-password').click()
            expect(page.locator('#authorize-dialog')).to_be_visible()
            page.locator('#auth-password').fill('system-secret')
            page.locator('#authorize-submit').click()
            expect(page.locator('#connection-secret')).to_have_text('new-password123')
            page.locator('#reveal-password').click()
            page.locator('#language-toggle').click()
            assert store.load()['mode']=='lan'
            assert store.load()['lan']['ssid']=='<script>alert(1)</script>'
            page.reload()
            expect(page.locator('#connection-secret')).to_have_text('••••••••')
            page.locator('#reveal-password').click()
            expect(page.locator('#connection-secret')).to_have_text('new-password123')
            assert authenticator.calls == ['incorrect','system-secret','system-secret']
            page.locator('#reveal-password').click()
            expect(page.locator('#ssid')).to_have_value('<script>alert(1)</script>')
            expect(page.locator('#password')).to_have_value('')
            expect(page.locator('#password')).to_have_attribute('placeholder', '留空使用已保存密码')
            page.locator('#saved-network-toggle').click()
            expect(page.locator('#saved-network-menu [role="option"]')).to_have_text('<script>alert(1)</script>')
            page.keyboard.press('ArrowDown')
            page.keyboard.press('Enter')
            expect(page.locator('#saved-network-menu')).not_to_be_visible()
            # The saved password is reused even though no credential returns to the browser.
            page.locator('#connect-button').click()
            page.locator('#confirm-switch').click()
            expect(page.locator('#confirm-dialog')).not_to_be_visible()
            page.wait_for_function("async () => {const s=await (await fetch('/api/status')).json();return !s.busy && s.phase==='ready' && s.mode==='lan'}", timeout=15000)
            expect(page.locator('#connect-button')).to_be_enabled(timeout=15000)
            # Scanning must not disable the form. A confirmed connection waits
            # for the radio scan, and cancelling that wait must not switch modes.
            before = len(radio.activations)
            for cancel in [True, False]:
                radio.scan_started.clear(); radio.scan_release.clear()
                page.locator('#scan-button').click()
                assert radio.scan_started.wait(timeout=2)
                page.evaluate('refreshStatus()')
                expect(page.locator('#connect-button')).to_be_enabled()
                page.locator('#connect-button').click()
                page.locator('#confirm-switch').click()
                expect(page.locator('#confirm-switch')).to_have_text('等待扫描…')
                assert len(radio.activations) == before
                if cancel:
                    page.locator('#cancel-switch').click()
                    expect(page.locator('#confirm-dialog')).not_to_be_visible()
                radio.scan_release.set()
                expect(page.locator('#scan-button')).not_to_have_class('icon-button spinning',timeout=15000)
                expect(page.locator('#confirm-dialog')).not_to_be_visible()
                if cancel:
                    assert len(radio.activations) == before
                else:
                    page.wait_for_function("async () => {const s=await (await fetch('/api/status')).json();return !s.busy && s.phase==='ready' && s.mode==='lan'}",timeout=15000)
                    expect(page.locator('#connect-button')).to_be_enabled(timeout=15000)
                    assert len(radio.activations) == before + 1, (before, radio.activations, controller.public_status())
                expect(page.locator('#connect-button')).to_be_enabled(timeout=15000)
            # A failed new connection must restore AP without replacing good YAML.
            old=store.path.read_bytes(); radio.fail=True
            page.locator('#ssid').fill('Failing network')
            page.locator('#password').fill('wrong-password123')
            page.locator('#connect-button').click()
            page.locator('#confirm-switch').click()
            expect(page.locator('#status-badge')).to_have_text('备用热点',timeout=15000)
            assert store.path.read_bytes()==old
            # Explicit AP selection is persisted and stops next-boot LAN retry.
            page.locator('#mode-ap').click()
            page.locator('#connect-button').click()
            page.locator('#confirm-switch').click()
            expect(page.locator('#status-badge')).to_have_text('热点模式',timeout=15000)
            assert store.load()['mode']=='ap'
            assert not errors,errors
            report={'login_not_required':True,'successful_connect_saved':True,'english_connection_flow':True,'refresh_restores_saved_network':True,'saved_password_reused':True,'ap_password_survives_restart':True,'browser_grant_reused_for_ap_and_wifi_password':True,'password_hidden_on_reload':True,'service_restart_revokes_grant_in_open_tab':True,'help_drawer_dismissible':True,'signal_levels_rendered':True,'failed_connect_preserves_yaml':True,'ap_mode_persisted':True,'ssid_html_rendered_as_text':True,'connect_while_scanning_waits_and_can_cancel':True,'console_errors':errors}
            (Path(__file__).parent/'flow-report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
            browser.close()
    finally:
        server.shutdown();server.server_close()
