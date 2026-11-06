"""Tests isolate all network mutations; safe to run on the connected device."""
from copy import deepcopy
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch, Mock

from configuration import ConfigStore, DEFAULT_CONFIG, validate_config, validate_network
from controller import BusyError, WifiController
from network import NetworkError, NetworkManager, split_escaped
from wifi import create_app


class FakeNetwork:
    def __init__(self):
        self.calls = []
        self.fail_lan = False
        self.fail_ap = False
        self.state = {'connected': False, 'mode': '', 'ssid': '', 'address': '', 'uuid': ''}

    def snapshot(self):
        return deepcopy(self.state)

    def scan(self):
        return {'networks': [], 'warning': ''}

    def activate(self, mode, config):
        self.calls.append(mode)
        if (mode == 'lan' and self.fail_lan) or (mode == 'ap' and self.fail_ap):
            raise NetworkError('failure')
        self.state = {'connected': True, 'mode': mode, 'ssid': config[mode]['ssid'],
                      'address': config['ap']['address'] if mode == 'ap' else '192.168.1.20', 'uuid': 'owned'}
        return self.state


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ConfigStore(Path(self.temp.name) / 'wifi.yaml')
        self.network = FakeNetwork()
        self.controller = WifiController(self.store, self.network)

    def candidate(self):
        value = deepcopy(DEFAULT_CONFIG)
        value['mode'] = 'lan'
        value['lan'] = {'ssid': '家里:WiFi\\5G', 'password': 'test-secret-123'}
        value['networks'] = [deepcopy(value['lan'])]
        return value


class ConfigurationTests(Base):
    def test_legacy_yaml_keeps_credentials_and_builds_history(self):
        config = self.candidate()
        config.pop('networks')
        config['ap']['password'] = 'legacy-password'
        import yaml
        self.store.path.write_text(yaml.safe_dump(config))
        loaded = self.store.load()
        self.assertEqual(loaded['ap']['password'], 'legacy-password')
        self.assertEqual(loaded['networks'], [config['lan']])
        self.assertEqual(DEFAULT_CONFIG['ap']['password'], '')

    def test_yaml_atomic_private_and_round_trip(self):
        config = self.candidate()
        self.store.save(config)
        self.assertEqual(config, self.store.load())
        self.assertEqual(os.stat(self.store.path).st_mode & 0o777, 0o600)
        self.assertEqual(list(Path(self.temp.name).glob('.wifi-*')), [])

    def test_invalid_write_preserves_valid_config(self):
        original = self.store.path.read_bytes()
        for value in ({'mode': 'bad'}, {'mode': 'ap', 'lan': {}, 'ap': {}}):
            with self.assertRaises(ValueError): self.store.save(value)
        self.assertEqual(self.store.path.read_bytes(), original)

    def test_malformed_yaml_does_not_expose_secret(self):
        self.store.path.write_text('password: secret-sensitive: broken')
        with self.assertRaises(ValueError) as error:
            self.store.load()
        self.assertNotIn('secret-sensitive', str(error.exception))

    def test_validation_boundaries_and_private_ip(self):
        with self.assertRaises(ValueError): validate_network({'ssid': '中' * 11, 'password': '12345678'})
        with self.assertRaises(ValueError): validate_network({'ssid': 'home\nnew', 'password': '12345678'})
        with self.assertRaises(ValueError): validate_network({'ssid': 'home', 'password': 'short'})
        with self.assertRaises(ValueError):
            value = deepcopy(DEFAULT_CONFIG); value['ap']['address'] = '192.169.11.17'; validate_config(value)
        self.assertEqual(validate_network({'ssid': ' home ', 'password': ''})['ssid'], ' home ')


class ControllerTests(Base):
    def test_current_wifi_password_from_history_and_external_profile(self):
        self.controller.apply(self.candidate(), persist=True)
        self.assertEqual(self.controller.connection_password()['password'], 'test-secret-123')
        self.network.state['ssid'] = 'External network'
        with patch.object(self.network, 'read_connection_password', return_value='external-secret', create=True) as read:
            self.assertEqual(self.controller.connection_password(), {'ssid':'External network', 'password':'external-secret'})
            read.assert_called_once_with('owned')
        self.assertNotIn('external-secret', json.dumps(self.controller.public_status()))

    def test_secret_read_respects_operation_lock_and_connection_mode(self):
        with self.controller.operation:
            with self.assertRaises(BusyError): self.controller.connection_password()
        with self.assertRaises(ValueError): self.controller.connection_password()
        self.network.activate('ap', DEFAULT_CONFIG)
        with self.assertRaises(ValueError): self.controller.connection_password()
        self.assertFalse(self.controller.operation.locked())

    def test_history_survives_restarts_and_reuses_older_password(self):
        first = self.candidate()
        self.controller.apply(first, persist=True)
        second = deepcopy(self.controller.config)
        second['lan'] = {'ssid': 'Second network', 'password': 'second-secret'}
        self.controller.apply(second, persist=True)
        rebooted = WifiController(self.store, self.network)
        self.assertEqual([n['ssid'] for n in rebooted.config['networks']], ['Second network', first['lan']['ssid']])
        with patch('controller.threading.Thread') as worker:
            rebooted.request({'mode': 'lan', 'ssid': first['lan']['ssid'], 'password': None})
            candidate = worker.call_args.kwargs['args'][0]
            self.assertEqual(candidate['lan']['password'], 'test-secret-123')
            rebooted.operation.release()
        public = json.dumps(rebooted.public_status())
        self.assertNotIn('test-secret-123', public)
        self.assertNotIn('second-secret', public)

    def test_ap_password_persists_without_interrupting_network(self):
        self.controller.save_ap_password({'password': 'new-ap-password'})
        self.assertEqual(self.network.calls, [])
        rebooted = WifiController(self.store, self.network)
        with patch.object(self.network, 'activate', wraps=self.network.activate) as activate:
            rebooted.apply(deepcopy(rebooted.config), persist=False)
            self.assertEqual(activate.call_args.args[1]['ap']['password'], 'new-ap-password')
        self.assertNotIn('new-ap-password', json.dumps(rebooted.public_status()))

    def test_invalid_ap_password_and_failed_save_preserve_config(self):
        old = self.store.path.read_bytes()
        for password in ['', 'short', None, '中文密码至少八个字']:
            with self.assertRaises(ValueError): self.controller.save_ap_password({'password': password})
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.controller.save_ap_password({'password': 'valid-password'})
        self.assertEqual(self.store.path.read_bytes(), old)
        self.assertEqual(self.controller.config['ap']['password'], '')
        self.assertFalse(self.controller.operation.locked())

    def test_ap_password_respects_operation_lock_and_preview(self):
        with self.controller.operation:
            with self.assertRaises(BusyError): self.controller.save_ap_password({'password': 'valid-password'})
        with self.assertRaises(PermissionError):
            WifiController(self.store, self.network, preview=True).save_ap_password({'password': 'valid-password'})

    def test_success_persists_only_after_connected(self):
        self.controller.apply(self.candidate(), persist=True)
        self.assertEqual(self.network.calls, ['lan'])
        self.assertEqual(self.store.load()['mode'], 'lan')
        self.assertEqual(self.controller.phase, 'ready')

    def test_bad_credentials_recover_without_overwriting_yaml(self):
        original = self.store.path.read_bytes()
        self.network.fail_lan = True
        self.controller.apply(self.candidate(), persist=True)
        self.assertEqual(self.network.calls, ['lan', 'ap'])
        self.assertEqual(self.store.path.read_bytes(), original)
        self.assertTrue(self.controller.fallback)

    def test_startup_failed_lan_preserves_saved_mode(self):
        value = self.candidate(); self.store.save(value)
        self.controller = WifiController(self.store, self.network)
        self.network.fail_lan = True
        self.controller.apply(value, persist=False)
        self.assertEqual(self.store.load(), value)
        self.assertEqual(self.controller.public_status()['configured_mode'], 'lan')
        self.assertEqual(self.controller.public_status()['mode'], 'ap')

    def test_empty_lan_starts_ap(self):
        value = deepcopy(DEFAULT_CONFIG); value['mode'] = 'lan'
        self.controller.apply(value, persist=False)
        self.assertEqual(self.network.calls, ['ap'])

    def test_config_io_failure_recovers_old_hotspot(self):
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            self.controller.apply(self.candidate(), persist=True)
        self.assertEqual(self.network.calls, ['lan', 'ap'])
        self.assertEqual(self.store.load()['mode'], 'ap')

    def test_both_modes_fail_returns_error(self):
        self.network.fail_lan = self.network.fail_ap = True
        self.controller.apply(self.candidate(), persist=True)
        self.assertEqual(self.controller.phase, 'error')

    def test_operation_lock_prevents_racing_switch_and_scan(self):
        with self.controller.operation:
            with self.assertRaises(BusyError): self.controller.request({'mode': 'ap'})
            with self.assertRaises(BusyError): self.controller.scan()

    def test_preview_never_changes_network(self):
        preview = WifiController(self.store, self.network, preview=True)
        preview.start(); preview.scan(); preview.public_status()
        with self.assertRaises(PermissionError): preview.request({'mode': 'ap'})
        self.assertEqual(self.network.calls, [])

    def test_persistent_disconnect_recovers_ap(self):
        value = self.candidate(); self.store.save(value)
        controller = WifiController(self.store, self.network)
        with patch.object(controller.stop_event, 'wait', side_effect=[False, False, False, True]), patch.object(self.network, 'snapshot', return_value={'connected': False}):
            controller._monitor()
        self.assertEqual(self.network.calls, ['lan', 'ap'])
        self.assertEqual(self.store.load()['mode'], 'lan')

    def test_status_contains_no_passwords_or_uuid(self):
        self.controller.config = self.candidate()
        status = json.dumps(self.controller.public_status())
        self.assertNotIn('test-secret-123', status)
        self.assertNotIn('fixture-ap-secret-2026', status)
        self.assertNotIn('uuid', status)


class AdapterTests(unittest.TestCase):
    def test_read_profile_password_open_personal_and_unsupported(self):
        backend = NetworkManager()
        for security in ('', '--'):
            with patch.object(backend, 'run', return_value=security) as run:
                self.assertEqual(backend.read_connection_password('profile'), '')
                self.assertEqual(run.call_count, 1)
        for security in ('wpa-psk','sae'):
            with patch.object(backend, 'run', side_effect=[security, 'secret:with\\colon']) as run:
                self.assertEqual(backend.read_connection_password('profile'), 'secret:with\\colon')
                self.assertNotIn('secret:with', repr(run.call_args_list))
        for results in [('none',), ('wpa-eap',), ('wpa-psk','--'), ('wpa-psk','')]:
            with patch.object(backend, 'run', side_effect=results):
                with self.assertRaises(NetworkError): backend.read_connection_password('profile')

    def test_default_open_ap_does_not_set_security_or_pass_password(self):
        backend = NetworkManager()
        commands = []
        def run(*args, **kwargs):
            commands.append(args)
            return 'yes' if args[:2] == ('-g', 'WIFI-PROPERTIES.AP') else ''
        with patch.object(backend, 'run', side_effect=run), patch('network.uuid.uuid4', return_value='new-profile'), patch.object(backend, 'snapshot', return_value={'connected': True, 'uuid': 'new-profile', 'address': '192.168.11.17'}):
            backend.activate('ap', DEFAULT_CONFIG)
        self.assertNotIn('passwd-file', repr(commands))
        self.assertNotIn('wpa-psk', repr(commands))

    def test_escaped_fields(self):
        self.assertEqual(split_escaped(r'*:room\:A\\B:80:WPA2'), ['*', 'room:A\\B', '80', 'WPA2'])

    def test_scan_groups_duplicates_and_handles_unsupported_security(self):
        backend = NetworkManager()
        output = '*:house:50:WPA2\n:house:90:WPA2\n:guest:40:--\n:office:60:WPA2 802.1X\n:lab\\:one:30:WPA2'
        with patch.object(backend, 'run', side_effect=['', output]):
            networks = backend.scan()['networks']
        self.assertEqual(len(networks), 4)
        self.assertTrue(next(n for n in networks if n['ssid'] == 'house')['active'])
        self.assertTrue(any(n['ssid'] == 'lab:one' for n in networks))
        self.assertFalse(next(n for n in networks if n['ssid'] == 'office')['supported'])

    def test_psk_only_in_private_temporary_file_and_cleanup(self):
        backend = NetworkManager()
        commands, passwords = [], []
        def run(*args, **kwargs):
            commands.append(args)
            if 'passwd-file' in args:
                path = Path(args[args.index('passwd-file') + 1]); passwords.append(path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertIn('fixture-ap-secret-2026', path.read_text())
            if args[:2] == ('-g', 'WIFI-PROPERTIES.AP'): return 'yes'
            return ''
        with patch.object(backend, 'run', side_effect=run), patch('network.uuid.uuid4', return_value='new-profile'), patch.object(backend, 'snapshot', return_value={'connected': True, 'uuid': 'new-profile', 'address': '192.168.11.17'}):
            config = deepcopy(DEFAULT_CONFIG)
            config['ap']['password'] = 'fixture-ap-secret-2026'
            backend.activate('ap', config)
        self.assertNotIn('fixture-ap-secret-2026', repr(commands))
        self.assertTrue(passwords and all(not p.exists() for p in passwords))
        self.assertTrue(any('192.168.11.17/24' in args for args in commands))
        self.assertTrue(any('--temporary' in args for args in commands))

    def test_cleanup_error_does_not_break_working_connection(self):
        backend = NetworkManager()
        with patch.object(backend, 'run', side_effect=NetworkError('temporary failure')):
            backend.cleanup('working')

    def test_owned_cleanup_does_not_touch_foreign_profiles(self):
        backend = NetworkManager()
        output = 'keep:helloboard-managed-keep\nold:hellosms-managed-old\nnew:helloboard-managed-new\nforeign:Home\nother:helloboard-managed-something\nlegacy-other:hellosms-managed-something'
        with patch.object(backend, 'run', return_value=output), patch.object(backend, 'delete') as delete:
            backend.cleanup('keep')
        self.assertEqual([call.args[0] for call in delete.call_args_list], ['old', 'new'])


class TestAuthenticator:
    username = 'ubuntu'
    def __init__(self): self.calls = []
    def verify(self, password):
        self.calls.append(password)
        if password != 'system-secret':
            raise PermissionError('系统登录密码不正确或账户不可用。')


class ApiTests(Base):
    def test_system_home_and_wifi_subpage_support_direct_access(self):
        root = self.client.get('/')
        self.assertEqual(root.status_code, 200)
        self.assertIn('系统状态'.encode(), root.data)
        self.assertEqual(self.client.get('/system_status').status_code, 200)
        for path in ('/wifi_config', '/wifi_config/'):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'HelloBoard', page.data)
            self.assertIn(b'href="/wifi_config"', page.data)
            self.assertIn(self.csrf.encode(), page.data)
            self.assertEqual(page.headers['Cache-Control'], 'no-store')
        self.authorize()
        self.client.get('/', follow_redirects=True)
        self.assertTrue(self.client.get('/api/status').json['authorized'])
        self.assertEqual(self.client.get('/unknown-panel').status_code, 404)

    def test_saved_network_secret_is_authorized_scoped_and_not_cached(self):
        self.controller.config = self.candidate()
        self.controller.config['networks'].append({'ssid': 'Other', 'password': 'other-example-secret'})
        endpoint = '/api/saved-network-password'
        denied = self.client.post(endpoint, json={'ssid': 'Other'}, headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(denied.json['authorization_required'])
        self.authorize()
        reply = self.client.post(endpoint, json={'ssid': 'Other'}, headers=self.headers)
        self.assertEqual(reply.json, {'ssid': 'Other', 'password': 'other-example-secret'})
        self.assertEqual(reply.headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'other-example-secret', self.client.get('/api/status').data)
        self.assertEqual(self.network.calls, [])
        self.assertEqual(self.client.post(endpoint, json={'ssid': 'Other'}).status_code, 403)
        self.app.config['SECRET_KEY'] = 'new-service-signing-key'
        self.assertEqual(self.client.post(endpoint, json={'ssid': 'Other'}, headers=self.headers).status_code, 403)

    def test_saved_network_secret_rejects_unknown_and_invalid_selection(self):
        self.authorize()
        for payload in [None, [], {}, {'ssid': []}, {'ssid': 'x' * 33}, {'ssid': 'not saved'}]:
            reply = self.client.post('/api/saved-network-password', data=json.dumps(payload),
                content_type='application/json', headers=self.headers)
            self.assertEqual(reply.status_code, 400)
        self.assertEqual(self.network.calls, [])

    def test_hotspot_secret_requires_authorization_and_is_never_cached(self):
        endpoint = '/api/ap-password/reveal'
        denied = self.client.post(endpoint, json={}, headers=self.headers)
        self.assertEqual(denied.status_code, 403)
        self.assertTrue(denied.json['authorization_required'])
        self.authorize()
        self.assertEqual(self.client.post(endpoint, json={}, headers=self.headers).json, {'password': ''})
        self.controller.save_ap_password({'password': 'saved-hotspot-secret'})
        self.controller.preview = True
        response = self.client.post(endpoint, json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'password': 'saved-hotspot-secret'})
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertNotIn(b'saved-hotspot-secret', self.client.get('/api/status').data)
        self.assertEqual(self.network.calls, [])

    def authorize(self, client=None):
        client = client or self.client
        token = client.get('/api/status').json['csrf_token']
        response = client.post('/api/authorize', json={'username': 'ubuntu', 'password': 'system-secret'}, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 200)
        return {'X-CSRF-Token': token}

    def test_ap_password_endpoint_is_validated_and_csrf_protected(self):
        expired = self.client.post('/api/ap-password', json={'password': 'valid-password'})
        self.assertEqual(expired.status_code, 403)
        self.assertTrue(expired.json['csrf_expired'])
        self.authorize()
        for payload in [[], {}, {'password': 'short'}]:
            self.assertEqual(self.client.post('/api/ap-password', json=payload, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post('/api/ap-password', json={'password': 'valid-password'}, headers=self.headers).status_code, 200)
        self.assertTrue(self.client.get('/api/status').json['ap_has_password'])
        self.assertNotIn(b'valid-password', self.client.get('/api/status').data)

    def test_grant_reused_for_protected_actions_without_storing_login_password(self):
        self.controller.apply(self.candidate(), persist=True)
        for endpoint in ('ap-password', 'connection-password', 'ap-password/reveal'):
            response = self.client.post('/api/' + endpoint, json={'password':'first-ap-password'}, headers=self.headers)
            self.assertEqual(response.status_code, 403)
            self.assertTrue(response.json['authorization_required'])
        for username, password in [('other', 'system-secret'), ('ubuntu', 'incorrect')]:
            self.assertEqual(self.client.post('/api/authorize', json={'username': username, 'password': password}, headers=self.headers).status_code, 403)
        self.authorize()
        self.assertTrue(self.client.get('/api/status').json['authorized'])
        self.assertEqual(self.client.post('/api/connection-password', json={}, headers=self.headers).json,
                         {'ssid': self.candidate()['lan']['ssid'], 'password': 'test-secret-123'})
        for password in ['first-ap-password', 'second-ap-password']:
            self.assertEqual(self.client.post('/api/ap-password', json={'password':password}, headers=self.headers).status_code, 200)
        self.assertEqual(self.authenticator.calls, ['incorrect', 'system-secret'])
        self.assertNotIn(b'system-secret', self.store.path.read_bytes())
        self.assertNotIn(b'system-secret', self.client.get('/api/status').data)
        self.assertNotIn(b'test-secret-123', self.client.get('/api/status').data)
        self.client.get('/')
        self.assertTrue(self.client.get('/api/status').json['authorized'])

    def test_grants_are_browser_scoped_and_invalidated_on_service_restart(self):
        self.authorize()
        other = self.app.test_client()
        token = other.get('/api/status').json['csrf_token']
        self.assertFalse(other.get('/api/status').json['authorized'])
        self.assertEqual(other.post('/api/connection-password', json={}, headers={'X-CSRF-Token':token}).status_code, 403)
        restarted = create_app(self.controller, authenticator=self.authenticator).test_client()
        restarted.set_cookie('session', self.client.get_cookie('session').value)
        state = restarted.get('/api/status').json
        self.assertFalse(state['authorized'])
        self.assertNotEqual(state['csrf_token'], self.csrf)
        response = restarted.post('/api/connection-password', json={}, headers={'X-CSRF-Token':state['csrf_token']})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json['authorization_required'])

    def test_authorization_and_secret_endpoints_reject_csrf_and_foreign_origin(self):
        for endpoint in ('authorize', 'connection-password', 'ap-password/reveal'):
            self.assertEqual(self.client.post('/api/'+endpoint,json={}).status_code,403)
            self.assertEqual(self.client.post('/api/'+endpoint,json={},headers={**self.headers,'Origin':'http://evil.test'}).status_code,403)
        for payload in [[], {'username':None}, {'username':['ubuntu']}]:
            self.assertIn(self.client.post('/api/authorize',json=payload,headers=self.headers).status_code,(400,403))

    def test_cache_policy_keeps_configuration_private(self):
        self.assertEqual(self.client.get('/api/status').headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.get('/').headers['Cache-Control'], 'no-store')
        font = self.client.get('/static/fonts/inter-variable.693b77d4f32e.woff2')
        self.assertIn('immutable', font.headers['Cache-Control'])
        font.close()

    def setUp(self):
        super().setUp()
        self.authenticator = TestAuthenticator()
        self.app = create_app(self.controller, authenticator=self.authenticator)
        self.client = self.app.test_client()
        self.client.get('/wifi_config')
        with self.client.session_transaction() as session:
            self.csrf = session['csrf']
        self.headers = {'X-CSRF-Token': self.csrf}

    def test_no_login_required_and_csrf_origin_preserved(self):
        self.assertEqual(self.client.get('/api/status').status_code, 200)
        self.assertEqual(self.client.post('/api/scan', json={}, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post('/api/scan', json={}).status_code, 403)
        self.assertEqual(self.client.post('/api/scan', json={}, headers={**self.headers, 'Origin': 'http://evil.test'}).status_code, 403)
        self.assertEqual(self.client.get('/', headers={'Host': 'evil.test'}).status_code, 403)
        payload = {'mode': 'lan', 'ssid': 'home', 'password': 'example-password'}
        with patch.object(self.controller, 'request') as change:
            self.assertEqual(self.client.post('/api/connect', json=payload, headers=self.headers).status_code, 202)
            change.assert_called_once_with(payload)

    def test_local_discovery_host_and_origin(self):
        for hostname in ('helloboard.local', 'HelloBoard.local:80', 'helloboard.local.', '[::1]:80'):
            with self.subTest(hostname=hostname):
                self.assertEqual(self.client.get('/api/status', headers={'Host': hostname}).status_code, 200)
        for hostname in ('other.local', 'helloboard.local.evil.test', '8.8.8.8'):
            self.assertEqual(self.client.get('/api/status', headers={'Host': hostname}).status_code, 403)
        client = self.app.test_client()
        client.get('/wifi_config', base_url='http://helloboard.local')
        with client.session_transaction(base_url='http://helloboard.local') as session:
            token = session['csrf']
        headers = {'X-CSRF-Token': token, 'Origin': 'http://helloboard.local'}
        self.assertEqual(client.post('/api/scan', json={}, base_url='http://helloboard.local', headers=headers).status_code, 200)
        headers['Origin'] = 'http://other.local'
        self.assertEqual(client.post('/api/scan', json={}, base_url='http://helloboard.local', headers=headers).status_code, 403)

    def test_sensitive_data_absent_and_invalid_payload_rejected(self):
        self.assertNotIn(b'fixture-ap-secret-2026', self.client.get('/api/status').data)
        for value in (None, [], {'mode': 'bad'}, {'mode': 'lan', 'ssid': 'home', 'password': 'short'}):
            response = self.client.post('/api/connect', json=value, headers=self.headers)
            self.assertIn(response.status_code, (400, 415))
        self.assertFalse(self.controller.operation.locked())

    def test_login_ui_and_endpoints_removed(self):
        page = self.client.get('/wifi_config').data
        self.assertNotIn(b'login-dialog', page)
        self.assertNotIn(b'lock-button', page)
        self.assertNotIn(b'data-authenticated', page)
        for endpoint in ('login', 'logout'):
            self.assertEqual(self.client.post('/api/' + endpoint, json={}, headers=self.headers).status_code, 404)


if __name__ == '__main__':
    unittest.main()
