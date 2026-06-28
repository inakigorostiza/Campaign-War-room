"""GET /api/state — current dashboard state (stateless serverless recompute)."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))
import _lib  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(_lib.build_state()).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
