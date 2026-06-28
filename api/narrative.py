"""POST|GET /api/narrative — Claude briefing for the current state.

Returns an SSE-formatted body (event: token / data) so the frontend's existing
parser handles it identically to the local Flask SSE endpoint. The body is sent
in one shot (serverless), not incrementally streamed.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(__file__))
import _lib  # noqa: E402


def _briefing_sse() -> bytes:
    state = _lib.build_state()
    text = _lib.briefing_text(state)
    out = (
        f"event: token\ndata: {json.dumps({'text': text})}\n\n"
        f"event: done\ndata: {json.dumps({'version': state.get('version')})}\n\n"
    )
    return out.encode()


class handler(BaseHTTPRequestHandler):
    def _send(self):
        body = _briefing_sse()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._send()

    def do_GET(self):
        self._send()
