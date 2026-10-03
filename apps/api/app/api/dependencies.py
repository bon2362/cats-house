from dataclasses import dataclass
from secrets import compare_digest

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class OwnerSession:
    email: str


def require_owner(request: Request) -> OwnerSession:
    owner_email = request.app.state.settings.owner_email
    session_email = request.session.get("owner_email")

    if not isinstance(session_email, str) or not compare_digest(session_email, owner_email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется вход владельца.",
        )

    return OwnerSession(email=owner_email)
