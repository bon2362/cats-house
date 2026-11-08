"""Google Drive v3 через urllib: своя папка, загрузка, список, корзина."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FOLDER_MIME = "application/vnd.google-apps.folder"
FOLDER_NAME = "Cat's House — копии базы"
MARK_KEY = "cats_house_backups"
JSON_TYPE = "application/json; charset=UTF-8"


class DriveError(Exception):
    """Google Drive не выполнил запрос."""


class DriveClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, *,
                 token_url: str = "https://oauth2.googleapis.com/token",
                 api_url: str = "https://www.googleapis.com/drive/v3",
                 upload_url: str = "https://www.googleapis.com/upload/drive/v3",
                 timeout: float = 60) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.token_url = token_url
        self.api_url = api_url
        self.upload_url = upload_url
        self.timeout = timeout
        self._access_token: str | None = None

    def _send(self, method: str, url: str, *, data: bytes | None = None,
              headers: dict[str, str] | None = None, auth: bool = True):
        headers = dict(headers or {})
        if auth:
            headers["Authorization"] = f"Bearer {self._token()}"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
                return response.headers, (json.loads(body) if body else {})
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            raise DriveError(f"Google Drive ответил {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise DriveError(f"Google Drive недоступен: {reason}") from None

    def _token(self) -> str:
        if self._access_token is None:
            form = urllib.parse.urlencode({
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            }).encode()
            try:
                _, result = self._send("POST", self.token_url, data=form, auth=False,
                                       headers={"Content-Type": "application/x-www-form-urlencoded"})
            except DriveError as error:
                if "invalid_grant" in str(error) or "invalid_client" in str(error):
                    raise DriveError("ключ доступа Google не действует — нужно заново выдать разрешение "
                                     "(apps/backup/scripts/google-authorize.py)") from None
                raise
            token = result.get("access_token")
            if not token:
                raise DriveError("Google не выдал ключ доступа.")
            self._access_token = token
        return self._access_token

    def _files_url(self, suffix: str = "", **params) -> str:
        query = ("?" + urllib.parse.urlencode(params)) if params else ""
        return f"{self.api_url}/files{suffix}{query}"

    def find_or_create_folder(self) -> str:
        q = (f"mimeType='{FOLDER_MIME}' and appProperties has {{ key='{MARK_KEY}' and value='1' }} "
             "and trashed=false")
        _, found = self._send("GET", self._files_url(q=q, orderBy="createdTime", fields="files(id,name)",
                                                     pageSize=10, spaces="drive"))
        if found.get("files"):
            return found["files"][0]["id"]
        meta = {"name": FOLDER_NAME, "mimeType": FOLDER_MIME, "appProperties": {MARK_KEY: "1"}}
        _, created = self._send("POST", self._files_url(fields="id"), data=json.dumps(meta).encode(),
                                headers={"Content-Type": JSON_TYPE})
        return created["id"]

    def upload(self, folder_id: str, path: Path, name: str) -> str:
        content = Path(path).read_bytes()
        meta = {"name": name, "parents": [folder_id], "mimeType": "application/octet-stream"}
        headers, _ = self._send(
            "POST", f"{self.upload_url}/files?uploadType=resumable", data=json.dumps(meta).encode(),
            headers={"Content-Type": JSON_TYPE, "X-Upload-Content-Type": "application/octet-stream",
                     "X-Upload-Content-Length": str(len(content))},
        )
        session = headers.get("Location")
        if not session:
            raise DriveError("Google Drive не начал загрузку.")
        _, uploaded = self._send("PUT", session, data=content,
                                 headers={"Content-Type": "application/octet-stream"})
        if "id" not in uploaded:
            raise DriveError("Google Drive не подтвердил загрузку.")
        return uploaded["id"]

    def file_info(self, file_id: str) -> dict:
        _, info = self._send("GET", self._files_url(f"/{file_id}", fields="id,name,size,md5Checksum"))
        return info

    def list_files(self, folder_id: str) -> list[dict]:
        files: list[dict] = []
        page_token = None
        while True:
            params = {"q": f"'{folder_id}' in parents and trashed=false",
                      "fields": "nextPageToken,files(id,name)", "pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            _, page = self._send("GET", self._files_url(**params))
            files.extend(page.get("files", []))
            page_token = page.get("nextPageToken")
            if not page_token:
                return files

    def trash(self, file_id: str) -> None:
        self._send("PATCH", self._files_url(f"/{file_id}", fields="id"),
                   data=json.dumps({"trashed": True}).encode(), headers={"Content-Type": JSON_TYPE})
