#!/usr/bin/env python3
"""Serve only the credential-free MapKit validation assets; never a repo root."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ASSETS = Path(__file__).resolve().parent / 'maps-validation'
FILES = {'/': ('index.html', 'text/html; charset=utf-8'), '/index.html': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        item = FILES.get(urlsplit(self.path).path)
        if item is None:
            self.send_error(404)
            return
        data = (ASSETS / item[0]).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', item[1])
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # URLs and client identifiers are not validation evidence.

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bind', default='127.0.0.1', help='Use the Mac LAN IPv4 address for iPhone validation.')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    with ThreadingHTTPServer((args.bind, args.port), Handler) as server:
        print(f'Map validation: http://{args.bind}:{args.port}/ (Ctrl-C to stop)', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
