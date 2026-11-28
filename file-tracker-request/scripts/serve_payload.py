"""Serve a request payload JSON on loopback for the browser fill step.

Usage: uv run serve_payload.py <payload.json> [port]
Default port 8765. Binds 127.0.0.1 only, sends Access-Control-Allow-Origin: *.
Start detached (Start-Process -WindowStyle Hidden) and verify with a local GET.
"""

import http.server
import sys
from pathlib import Path

payload_path = Path(sys.argv[1])
port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
PAYLOAD = payload_path.read_bytes()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        self.wfile.write(PAYLOAD)

    def log_message(self, *args):
        pass


http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()

