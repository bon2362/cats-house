"""Убрать из текста ошибок адреса баз и значения секретов."""

from __future__ import annotations

import re
from typing import Iterable, Optional

URL_RE = re.compile(r"postgres(?:ql)?(?:\+\w+)?://\S+")


def redact(text: str, secrets: Iterable[Optional[str]], limit: int = 500) -> str:
    out = URL_RE.sub("<адрес базы>", text)
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        out = out.replace(secret, "***")
    return out[:limit]
