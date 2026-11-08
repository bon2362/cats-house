"""Поддельный Google OAuth + Drive v3 для тестов (только то, что использует клиент)."""

import hashlib
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from drive_backup.drive import DriveClient

ACCESS = "fake-access"


class FakeDrive:
    def __init__(self):
        self.files = {}
        self.sessions = {}
        self.corrupt_md5 = False
        self.fail_upload = False
        self.fail_info = False
        self.puts = []
        self.partial = {}
        drive = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, body=None, headers=None):
                data = json.dumps(body or {}).encode()
                self.send_response(code)
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def body(self):
                return self.rfile.read(int(self.headers.get("Content-Length", 0)))

            def authorized(self):
                if self.headers.get("Authorization") != f"Bearer {ACCESS}":
                    self.reply(401, {"error": {"message": "Invalid Credentials"}})
                    return False
                return True

            def do_POST(self):
                url = urlparse(self.path)
                if url.path == "/token":
                    form = parse_qs(self.body().decode())
                    if form.get("grant_type") == ["refresh_token"] and form.get("refresh_token") == ["good-refresh"]:
                        return self.reply(200, {"access_token": ACCESS, "expires_in": 3599})
                    return self.reply(400, {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})
                if not self.authorized():
                    return
                if url.path == "/drive/v3/files":
                    meta = json.loads(self.body())
                    file_id = uuid.uuid4().hex
                    drive.files[file_id] = {**meta, "id": file_id, "trashed": False, "parents": meta.get("parents", ["root"])}
                    return self.reply(200, {"id": file_id})
                if url.path == "/upload/drive/v3/files" and parse_qs(url.query).get("uploadType") == ["resumable"]:
                    session = uuid.uuid4().hex
                    drive.sessions[session] = json.loads(self.body())
                    host = f"http://127.0.0.1:{drive.port}"
                    return self.reply(200, {}, {"Location": f"{host}/upload-session?upload_id={session}"})
                self.reply(404)

            def do_PUT(self):
                url = urlparse(self.path)
                session = parse_qs(url.query).get("upload_id", [""])[0]
                content = self.body()
                if url.path != "/upload-session" or session not in drive.sessions:
                    return self.reply(404)
                if drive.fail_upload:
                    return self.reply(503, {"error": {"message": "Backend Error"}})
                drive.puts.append(len(content))
                total = None
                data = drive.partial.get(session, b"") + content
                rng = self.headers.get("Content-Range")
                if rng:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", rng)
                    if not match or int(match.group(1)) != len(drive.partial.get(session, b"")):
                        return self.reply(400, {"error": {"message": "bad range"}})
                    total = int(match.group(3))
                if total is not None and len(data) < total:
                    drive.partial[session] = data
                    self.send_response(308)
                    self.send_header("Range", f"bytes=0-{len(data) - 1}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                drive.partial.pop(session, None)
                meta = drive.sessions.pop(session)
                file_id = uuid.uuid4().hex
                drive.files[file_id] = {**meta, "id": file_id, "trashed": False, "content": data}
                self.reply(200, {"id": file_id, "name": meta["name"]})

            def do_GET(self):
                if not self.authorized():
                    return
                url = urlparse(self.path)
                match = re.fullmatch(r"/drive/v3/files/([^/]+)", url.path)
                if match:
                    item = drive.files.get(match.group(1))
                    if not item:
                        return self.reply(404)
                    if drive.fail_info:
                        return self.reply(500, {"error": {"message": "Internal Error"}})
                    md5 = hashlib.md5(item.get("content", b"")).hexdigest()
                    if drive.corrupt_md5:
                        md5 = "0" * 32
                    return self.reply(200, {"id": item["id"], "name": item["name"],
                                            "size": str(len(item.get("content", b""))), "md5Checksum": md5})
                if url.path == "/drive/v3/files":
                    q = parse_qs(url.query)["q"][0]
                    live = [f for f in drive.files.values() if not f["trashed"]]
                    if "appProperties has" in q:
                        found = [f for f in live if f.get("appProperties", {}).get("cats_house_backups") == "1"]
                    else:
                        parent = re.search(r"'(\w+)' in parents", q).group(1)
                        found = [f for f in live if parent in f.get("parents", [])]
                    return self.reply(200, {"files": [{"id": f["id"], "name": f["name"]} for f in found]})
                self.reply(404)

            def do_PATCH(self):
                if not self.authorized():
                    return
                match = re.fullmatch(r"/drive/v3/files/([^/]+)", urlparse(self.path).path)
                if not match or match.group(1) not in drive.files:
                    return self.reply(404)
                drive.files[match.group(1)].update(json.loads(self.body()))
                self.reply(200, {"id": match.group(1)})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    def client(self, refresh_token="good-refresh"):
        base = f"http://127.0.0.1:{self.port}"
        return DriveClient("client-id", "client-secret", refresh_token, token_url=f"{base}/token",
                           api_url=f"{base}/drive/v3", upload_url=f"{base}/upload/drive/v3")

    def live_names(self, folder_id):
        return sorted(f["name"] for f in self.files.values() if not f["trashed"] and folder_id in f.get("parents", []))
