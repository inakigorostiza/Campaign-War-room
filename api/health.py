"""GET /api/health — liveness + config info."""

import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "ok": True,
            "source": "seed",
            "model": os.getenv("CLAUDE_MODEL", "claude-opus-4-8"),
            "has_anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "runtime": "vercel-serverless",
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
