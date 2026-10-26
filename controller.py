"""Serialized mode changes, recovery hotspot, and periodic link monitoring."""
from copy import deepcopy
import logging
import threading

from configuration import validate_network
from network import NetworkError

LOG = logging.getLogger(__name__)


class BusyError(RuntimeError):
    pass


class WifiController:
    def __init__(self, store, network, *, preview=False, capabilities=None):
        self.store, self.network, self.preview = store, network, preview
        self.capabilities = capabilities or dict(available=True, manage=not preview, ap=True,
                                               interface=network.interface if hasattr(network, 'interface') else '', reason='')
        self.config = store.load()
        self.operation = threading.Lock()
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.phase = 'preview' if preview else 'starting'
        self.message = '预览模式：可查看状态和扫描，网络切换尚未启用。' if preview else '正在准备网络。'
        if preview and self.capabilities.get('reason'):
            self.message = self.capabilities['reason']
        self.fallback = False
        self.monitor_thread = None

    def update(self, phase, message, *, fallback=None):
        with self.state_lock:
            self.phase, self.message = phase, message
            if fallback is not None:
                self.fallback = fallback

    def public_status(self):
        try:
            actual = self.network.snapshot()
            actual.pop('uuid', None)
        except NetworkError as error:
            actual = {'connected': False, 'mode': '', 'ssid': '', 'address': '', 'error': str(error)}
        with self.state_lock:
            return {**actual, 'configured_mode': self.config['mode'],
                    'saved_ssid': self.config['lan']['ssid'], 'has_password': bool(self.config['lan']['password']),
                    'saved_networks': [{'ssid': n['ssid'], 'has_password': bool(n['password'])}
                                       for n in self.config['networks']],
                    'ap_ssid': self.config['ap']['ssid'], 'ap_address': self.config['ap']['address'],
                    'ap_has_password': bool(self.config['ap']['password']),
                    'phase': self.phase, 'message': self.message, 'fallback': self.fallback,
                    'busy': self.operation.locked(), 'preview': self.preview,
                    'capabilities': self.capabilities}

    def scan(self):
        if not self.operation.acquire(blocking=False):
            raise BusyError('正在处理网络操作，请稍后再试。')
        try:
            return self.network.scan()
        finally:
            self.operation.release()

    def connection_password(self):
        """Only called by the protected endpoint; status never includes secrets."""
        if not self.operation.acquire(blocking=False):
            raise BusyError('正在处理网络操作，请稍后再试。')
        try:
            actual = self.network.snapshot()
            if not actual['connected'] or actual['mode'] != 'lan':
                raise ValueError('当前没有连接 Wi-Fi。')
            with self.state_lock:
                saved = next((n for n in self.config['networks'] if n['ssid'] == actual['ssid']), None)
                password = saved['password'] if saved is not None else None
            if password is None:
                password = self.network.read_connection_password(actual['uuid'])
            return {'ssid': actual['ssid'], 'password': password}
        finally:
            self.operation.release()

    def ap_password(self):
        """Read the saved hotspot secret only through the protected endpoint."""
        with self.state_lock:
            return {'password': self.config['ap']['password']}

    def recover(self, reason):
        if not self.capabilities['ap']:
            self.update('error', '当前无线网卡不支持 AP 热点，连接失败后请通过原有网络访问。')
            return
        self.update('recovering', reason + ' 正在恢复热点。', fallback=True)
        self.network.activate('ap', self.config)
        self.update('ready', reason + ' 已开启配置热点，原有配置已保留。', fallback=True)

    def apply(self, candidate, *, persist):
        """Called only under operation lock. Failed credentials never replace YAML."""
        try:
            mode = candidate['mode']
            if mode == 'lan' and not candidate['lan']['ssid']:
                self.recover('尚未设置 Wi-Fi。')
                return
            self.update('connecting', '正在连接 Wi-Fi。' if mode == 'lan' else '正在开启热点。')
            self.network.activate(mode, candidate)
            if persist:
                if mode == 'lan':
                    candidate['networks'] = [deepcopy(candidate['lan']), *[
                        n for n in candidate.get('networks', [])
                        if n['ssid'] != candidate['lan']['ssid']]][:100]
                self.store.save(candidate)
                with self.state_lock:
                    self.config = candidate
            self.update('ready', 'Wi-Fi 已连接。' if mode == 'lan' else '热点已开启。', fallback=False)
        except (NetworkError, OSError):
            LOG.warning('Mode change failed; recovering the configured hotspot.')
            try:
                self.recover('连接或保存失败。')
            except (NetworkError, OSError):
                self.update('error', '热点恢复失败，稍后会重试。请检查无线网卡和 NetworkManager。', fallback=True)

    def request(self, payload):
        if self.preview:
            raise PermissionError('当前是预览模式，尚未启用网络切换服务。')
        mode = payload.get('mode')
        if mode == 'ap' and not self.capabilities['ap']:
            raise NetworkError('这块无线网卡不支持 AP 热点模式。')
        if mode not in ('ap', 'lan'):
            raise ValueError('请选择热点或局域网模式。')
        if not self.operation.acquire(blocking=False):
            raise BusyError('正在处理网络操作，请稍后再试。')
        try:
            candidate = deepcopy(self.config)
            candidate['mode'] = mode
            if mode == 'lan':
                ssid = payload.get('ssid')
                password = payload.get('password')
                if password is None:
                    saved = next((n for n in self.config['networks'] if n['ssid'] == ssid), None)
                    if saved is not None:
                        password = saved['password']
                candidate['lan'] = validate_network({'ssid': ssid, 'password': password})
            self.update('queued', '即将切换网络。当前网页可能暂时断开，请连接新网络后重新打开。')
            threading.Thread(target=self._change, args=(candidate,), daemon=True).start()
        except Exception:
            self.operation.release()
            raise

    def save_ap_password(self, payload):
        """Persist for the next AP activation; do not interrupt the current link."""
        if self.preview:
            raise PermissionError('预览模式不允许修改配置。')
        if not self.capabilities['ap']:
            raise NetworkError('这块无线网卡不支持 AP 热点模式。')
        password = payload.get('password')
        if not isinstance(password, str) or not password:
            raise ValueError('AP 密码至少需要 8 个字符。')
        if not self.operation.acquire(blocking=False):
            raise BusyError('正在处理网络操作，请稍后再试。')
        try:
            candidate = deepcopy(self.config)
            candidate['ap'].update(validate_network({'ssid': candidate['ap']['ssid'], 'password': password}))
            self.store.save(candidate)
            with self.state_lock:
                self.config = candidate
        finally:
            self.operation.release()

    def _change(self, candidate):
        try:
            # Allow the HTTP acknowledgement to reach the browser before AP stops.
            if not self.stop_event.wait(2):
                self.apply(candidate, persist=True)
        finally:
            self.operation.release()

    def start(self):
        if self.preview:
            return
        self.monitor_thread = threading.Thread(target=self._monitor, daemon=True)
        self.monitor_thread.start()

    def _monitor(self):
        with self.operation:
            if self.config['mode'] == 'ap' and not self.capabilities['ap']:
                self.update('error', '这块无线网卡不支持 AP 热点模式。')
            else:
                self.apply(deepcopy(self.config), persist=False)
        failures = 0
        while not self.stop_event.wait(10):
            if not self.operation.acquire(blocking=False):
                continue
            try:
                try:
                    status = self.network.snapshot()
                    expected_mode = 'ap' if self.fallback else self.config['mode']
                    if expected_mode == 'ap' and not self.capabilities['ap']:
                        continue
                    expected = self.config[expected_mode]
                    healthy = status['connected'] and status['mode'] == expected_mode and status['ssid'] == expected['ssid']
                    if expected_mode == 'ap':
                        healthy = healthy and status['address'] == expected['address']
                except NetworkError:
                    healthy = False
                failures = 0 if healthy else failures + 1
                if failures >= 3:
                    try:
                        self.recover('无线连接已中断。')
                    except NetworkError:
                        self.update('error', '热点启动失败，稍后会重试。', fallback=True)
                    failures = 0
            finally:
                self.operation.release()
