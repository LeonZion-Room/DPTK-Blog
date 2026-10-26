#!/usr/bin/env python3
"""本地预览 dist-static/ 的简易 HTTP 服务器。
用法: python3 preview_server.py [port]
默认端口 8001。
"""
import http.server
import os
import sys
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist-static')

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip('/')
        # /p/xxx/ → /p/xxx/index.html
        if path.startswith('/p/') and not os.path.exists(os.path.join(DIST, path.lstrip('/'))):
            candidate = os.path.join(DIST, path.lstrip('/'), 'index.html')
            if os.path.isfile(candidate):
                self.path = path + '/index.html'
        # / → /index.html
        if path == '':
            self.path = '/index.html'
        return super().do_GET()

    def log_message(self, format, *args):
        pass  # 静默日志

if __name__ == '__main__':
    with http.server.HTTPServer(('0.0.0.0', PORT), Handler) as httpd:
        print(f'Preview server: http://192.168.11.70:{PORT}/')
        print(f'Dist static: {DIST}')
        httpd.serve_forever()
