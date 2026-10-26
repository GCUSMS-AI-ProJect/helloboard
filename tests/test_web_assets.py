"""Asset transfer/caching checks. No radio access or credential verification."""
import gzip
import re
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest

from flask import Flask
from host_platform import DashboardController
from wifi import create_app
from web_assets import install_assets


def app():
    return create_app(DashboardController(dict(available=False, manage=False, ap=False, reason='fixture')),
        authenticator=SimpleNamespace(username='fixture', available=False),
        metrics=SimpleNamespace(snapshot=lambda **kw: {'history': [], 'device': {}}),
        processes=SimpleNamespace(supported=lambda: False, allow_control=False, snapshot=lambda: {'items':[]}))


class WebAssetsTests(unittest.TestCase):
    def setUp(self):
        self.app = app()
        self.client = self.app.test_client()

    def test_gzip_negotiation_integrity_and_head(self):
        plain = self.client.get('/static/style.css')
        zipped = self.client.get('/static/style.css', headers={'Accept-Encoding':'gzip'})
        self.assertEqual(gzip.decompress(zipped.data), plain.data)
        self.assertLess(len(zipped.data),len(plain.data)*.4)
        self.assertIn('Accept-Encoding',zipped.headers['Vary'])
        self.assertNotEqual(plain.headers['ETag'],zipped.headers['ETag'])
        for encoding in ['identity','gzip;q=0','br']:
            response = self.client.get('/static/style.css',headers={'Accept-Encoding':encoding})
            self.assertNotIn('Content-Encoding',response.headers)
            self.assertEqual(response.data,plain.data)
        head = self.client.head('/static/style.css',headers={'Accept-Encoding':'gzip'})
        self.assertEqual(head.data,b'')
        self.assertEqual(int(head.headers['Content-Length']),len(zipped.data))

    def test_versioned_urls_cache_and_conditional_response(self):
        html = self.client.get('/system_status').text
        url = re.search(r'href="(/static/style.css\?v=[a-f0-9]+)"',html)[1]
        response = self.client.get(url,headers={'Accept-Encoding':'gzip'})
        self.assertIn('immutable',response.headers['Cache-Control'])
        cached = self.client.get(url,headers={'Accept-Encoding':'gzip','If-None-Match':response.headers['ETag']})
        self.assertEqual(cached.status_code,304)
        self.assertEqual(cached.data,b'')
        self.assertIn('Accept-Encoding',cached.headers['Vary'])
        for path in ['/static/style.css','/static/style.css?v=old-version']:
            self.assertNotIn('immutable',self.client.get(path).headers['Cache-Control'])
        self.assertEqual(len(re.findall('rel="preload"',html)),2)
        self.assertNotRegex(html,r'rel="preload"[^>]+(?:fallback|inter-variable)')

    def test_private_responses_are_neither_compressed_nor_cached(self):
        for path in ['/system_status','/api/status','/api/system','/api/processes','/api/capabilities']:
            with self.subTest(path=path):
                response=self.client.get(path,headers={'Accept-Encoding':'gzip'})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['Cache-Control'],'no-store')
                self.assertNotIn('Content-Encoding',response.headers)
        self.assertEqual(self.client.get('/static/../wifi.yaml').status_code,404)
        self.assertEqual(self.client.get('/static/style.css',headers={'Host':'example.com','Accept-Encoding':'gzip'}).status_code,403)

    def test_version_changes_only_when_asset_content_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'style.css'
            path.write_text('body { color: black; }')
            def version():
                return install_assets(Flask(__name__,static_folder=temp))['style.css'].version
            original=version()
            self.assertEqual(version(),original)
            path.write_text('body { color: white; }')
            self.assertNotEqual(version(),original)

    def test_font_preload_uses_active_css_not_old_files_left_by_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            fonts=Path(temp)/'fonts'
            fonts.mkdir()
            (fonts/'noto-sans-sc-core.111111111111.woff2').write_bytes(b'old')
            (fonts/'fonts.css').write_text("src: url('/static/fonts/noto-sans-sc-core.222222222222.woff2');")
            application=Flask(__name__,static_folder=temp)
            install_assets(application)
            self.assertEqual(application.jinja_env.globals['ui_fonts'],['fonts/noto-sans-sc-core.222222222222.woff2'])


if __name__=='__main__': unittest.main()
