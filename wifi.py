#!/usr/bin/env python3
"""HelloBoard system dashboard and WiFi panel. Run --preview for read-only inspection."""
import argparse
from ipaddress import ip_address
import logging
import math
from pathlib import Path
import secrets

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from process_control import ProcessManager
from configuration import ConfigStore
from controller import BusyError, WifiController
from network import NetworkError, NetworkManager
from host_platform import identity, detect_wifi, make_metrics, make_authenticator, DashboardController

ROOT = Path(__file__).resolve().parent


class AuthorizationRequired(PermissionError):
    pass


def create_app(controller, *, authenticator=None, metrics=None, processes=None, host=None):
    host = host or identity()
    metrics = metrics if metrics is not None else make_metrics(host)
    authenticator = authenticator if authenticator is not None else make_authenticator(host)
    processes = processes if processes is not None else ProcessManager(metrics,
        allow_control=getattr(authenticator, 'available', True), preview=getattr(controller, 'preview', True))
    capabilities = dict(host=host,
        wifi=getattr(controller, 'capabilities', dict(available=True, manage=True, ap=True, reason='')),
        processes=dict(available=bool(processes.supported() and getattr(processes, 'allow_control', True)),
                       reason='当前系统仅支持查看进程。'))
    if capabilities['processes']['available']:
        capabilities['processes']['reason'] = ''
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=4096,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict')

    @app.context_processor
    def platform_context():
        return dict(capabilities=capabilities)

    @app.get('/api/capabilities')
    def runtime_capabilities():
        return jsonify(capabilities)

    def authorized():
        # The signing key is generated on each service start, invalidating grants.
        return session.get('authorized_user') == authenticator.username

    def require_authorized():
        if not authorized():
            raise AuthorizationRequired('请先验证系统用户名和密码。')

    @app.before_request
    def protect():
        # Only local/IP-host access: this interface is not intended for a public tunnel.
        host = request.host.split(':')[0]
        try:
            address = ip_address(host)
            valid_host = address.is_private or address.is_loopback
        except ValueError:
            valid_host = host == 'localhost'
        if not valid_host:
            return jsonify(error='请通过设备的局域网或热点 IP 地址访问。'), 403
        if request.path.startswith('/api/'):
            if request.method == 'POST':
                if not request.is_json:
                    return jsonify(error='请求格式必须是 JSON。'), 415
                origin = request.headers.get('Origin')
                if origin and origin != request.host_url.rstrip('/'):
                    return jsonify(error='请求来源不匹配，请刷新页面。'), 403
                if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', '-') ):
                    return jsonify(error='页面已过期，请刷新后重试。', csrf_expired=True), 403

    @app.after_request
    def headers(response):
        # Versioned font binaries are immutable; API/configuration remains private.
        if request.path.startswith('/static/fonts/') and request.path.endswith('.woff2'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, no-cache'
        else:
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/')
    @app.get('/system_status', strict_slashes=False)
    def index():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return render_template('system_status.html', csrf=session['csrf'], login_user=authenticator.username)

    @app.get('/api/processes')
    def process_list():
        return jsonify(processes.snapshot())

    @app.post('/api/processes/terminate')
    def terminate_processes():
        payload = request.get_json()
        processes.validate(payload)
        if processes.preview:
            raise PermissionError('预览模式不允许终止进程。')
        username = payload.get('username')
        if not isinstance(username, str) or not secrets.compare_digest(username.encode(), authenticator.username.encode()):
            raise PermissionError('系统用户名或密码不正确。')
        # Destructive process actions always need fresh credentials, including
        # browsers that already have a WiFi/password-display session grant.
        authenticator.verify(payload.get('password'))
        return jsonify(processes.terminate(payload))

    @app.get('/api/system')
    def system_status():
        since = request.args.get('since')
        if since is not None:
            try:
                since = float(since)
            except ValueError:
                raise ValueError('采样时间不正确。') from None
            if not math.isfinite(since) or since < 0:
                raise ValueError('采样时间不正确。')
        return jsonify(metrics.snapshot(since=since, history_id=request.args.get('history_id')))

    @app.get('/wifi_config', strict_slashes=False)
    def wifi_config():
        if not capabilities['wifi']['available']:
            return redirect(url_for('index'))
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return render_template('wifi_config.html', csrf=session['csrf'], login_user=authenticator.username)

    @app.get('/api/status')
    def status():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return jsonify(**controller.public_status(), authorized=authorized(), csrf_token=session['csrf'])

    @app.post('/api/authorize')
    def authorize():
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError('配置格式不正确。')
        username = payload.get('username')
        if not isinstance(username, str) or not secrets.compare_digest(username.encode(), authenticator.username.encode()):
            raise PermissionError('系统用户名或密码不正确。')
        authenticator.verify(payload.get('password'))
        session['authorized_user'] = authenticator.username
        return jsonify(ok=True, authorized=True)

    @app.post('/api/connection-password')
    def connection_password():
        require_authorized()
        return jsonify(controller.connection_password())

    @app.post('/api/scan')
    def scan():
        if not capabilities['wifi']['available']:
            raise NetworkError(capabilities['wifi']['reason'])
        return jsonify(controller.scan())

    @app.post('/api/ap-password/reveal')
    def reveal_ap_password():
        require_authorized()
        return jsonify(controller.ap_password())

    @app.post('/api/connect')
    def connect():
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError('配置格式不正确。')
        controller.request(payload)
        return jsonify(ok=True, message='已开始切换，请稍候。'), 202

    @app.post('/api/ap-password')
    def ap_password():
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError('配置格式不正确。')
        if controller.preview:
            raise PermissionError('预览模式不允许修改配置。')
        require_authorized()
        controller.save_ap_password(payload)
        return jsonify(ok=True, message='已保存，下次开启热点或重启服务时生效。')

    @app.errorhandler(Exception)
    def error_response(error):
        if isinstance(error, HTTPException):
            return jsonify(error='请求无效。'), error.code
        if isinstance(error, (ValueError, BusyError, PermissionError, NetworkError)):
            code = 400 if isinstance(error, ValueError) else 409 if isinstance(error, BusyError) else 403 if isinstance(error, PermissionError) else 503
            return jsonify(error=str(error), authorization_required=isinstance(error, AuthorizationRequired)), code
        logging.error('Unhandled request error (%s).', type(error).__name__)
        return jsonify(error='操作未完成，请稍后重试。'), 500

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'wifi.yaml')
    parser.add_argument('--interface', help='Wireless adapter; detected automatically when omitted')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--preview', action='store_true', help='Read-only preview: never changes network settings')
    parser.add_argument('--auth-user', help='System login account used to authorize protected actions')
    parser.add_argument('--dashboard-only', action='store_true', help='Only run the system dashboard; never manage WiFi')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    host = identity()
    wifi_caps = detect_wifi(host, args.interface, dashboard_only=args.dashboard_only)
    if wifi_caps['available']:
        store = ConfigStore(args.config)
        controller = WifiController(store, NetworkManager(wifi_caps['interface']),
            preview=args.preview or not wifi_caps['manage'], capabilities=wifi_caps)
    else:
        controller = DashboardController(wifi_caps)
    metrics = make_metrics(host)
    auth = make_authenticator(host, args.auth_user)
    processes = ProcessManager(metrics, preview=args.preview,
        allow_control=host['family'] == 'Linux' and auth.available)
    app = create_app(controller, authenticator=auth, metrics=metrics, processes=processes, host=host)
    # Waitress must bind successfully before any network mutation starts.
    from waitress.server import create_server
    server = create_server(app, host=args.host, port=args.port, threads=6)
    controller.start()
    metrics.start()
    logging.info('HelloBoard: %s; port=%s; WiFi=%s; preview=%s', host['name'], args.port,
                 wifi_caps['interface'] or 'unavailable', args.preview)
    try:
        server.run()
    finally:
        controller.stop_event.set()
        metrics.stop()
        server.close()


if __name__ == '__main__':
    main()
