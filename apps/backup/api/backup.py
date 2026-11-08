"""Вход функции Vercel: GET /api/backup, вызывается расписанием Vercel Cron."""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drive_backup.endpoint import handle  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = handle(self.headers.get("Authorization"), os.environ)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass
