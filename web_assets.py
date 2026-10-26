"""Small public assets: precompress once and cache by content version.

HTML, API responses, session data and passwords never enter this cache.
"""
from dataclasses import dataclass
import gzip
from hashlib import sha256
from pathlib import Path
import re

from flask import Response, request, url_for


@dataclass(frozen=True)
class Asset:
    body: bytes
    compressed: bytes
    version: str
    content_type: str


def install_assets(app):
    types = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
             '.svg': 'image/svg+xml; charset=utf-8'}
    root = Path(app.static_folder)
    assets = {}
    for path in root.rglob('*'):
        if path.suffix not in types or not path.is_file():
            continue
        body = path.read_bytes()
        assets[path.relative_to(root).as_posix()] = Asset(body,
            gzip.compress(body, compresslevel=6, mtime=0), sha256(body).hexdigest()[:12], types[path.suffix])

    def asset_url(filename):
        asset = assets.get(filename)
        return url_for('static', filename=filename, **({'v': asset.version} if asset else {}))

    # Font binaries already have content hashes; advertise just the two UI faces.
    # Read active CSS references: upgrades may leave older hashed files on disk.
    font_css = assets.get('fonts/fonts.css')
    fonts = list(dict.fromkeys(re.findall(
        r'/static/(fonts/(?:inter-core|noto-sans-sc-core)\.[a-f0-9]+\.woff2)',
        font_css.body.decode('utf-8') if font_css else '')))
    app.jinja_env.globals.update(asset_url=asset_url, ui_fonts=fonts)

    @app.before_request
    def serve_asset():
        if request.endpoint != 'static' or request.method not in ('GET', 'HEAD'):
            return
        asset = assets.get(request.view_args.get('filename'))
        if asset is None:
            return
        compressed = request.accept_encodings['gzip'] > 0
        response = Response(asset.compressed if compressed else asset.body,
                            content_type=asset.content_type)
        if compressed:
            response.headers['Content-Encoding'] = 'gzip'
        response.vary.add('Accept-Encoding')
        response.set_etag(asset.version + ('-gzip' if compressed else '-identity'))
        response.make_conditional(request)
        return response

    return assets
