from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class OwnerSession:
    email: str


def is_owner(request: Request) -> bool:
    session_email = request.session.get("owner_email")
    return isinstance(session_email, str) and compare_digest(session_email, request.app.state.settings.owner_email)


def require_owner(request: Request) -> OwnerSession:
    if not is_owner(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход владельца.",
        )
    return OwnerSession(email=request.app.state.settings.owner_email)
