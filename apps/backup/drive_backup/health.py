"""Сигналы сторожу healthchecks.io. Ошибки сигналов не ломают запуск."""

from __future__ import annotations

import urllib.request


def _send(request: urllib.request.Request, opener) -> bool:
    try:
        with opener(request, timeout=10) as response:
            response.read()
        return True
    except Exception:  # noqa: BLE001 — сторож недоступен: копия от этого не хуже
        return False


def ping_success(url: str, *, opener=urllib.request.urlopen) -> bool:
    return _send(urllib.request.Request(url, method="GET"), opener)


def ping_fail(url: str, message: str, *, opener=urllib.request.urlopen) -> bool:
    request = urllib.request.Request(url.rstrip("/") + "/fail", data=message.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
    return _send(request, opener)
