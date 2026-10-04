from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies import OwnerSession, require_owner
from app.auth.service import verify_owner_password, verify_totp

router = APIRouter()


class LoginRequest(BaseModel):
    password: str
    totp_code: str | None = None


@router.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login_owner(payload: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings

    if not verify_owner_password(payload.password, settings.owner_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль.",
        )
    if settings.owner_totp_secret and not verify_totp(payload.totp_code, settings.owner_totp_secret.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный одноразовый код.",
        )

    request.session["owner_email"] = settings.owner_email
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/session")
def get_owner_session(owner: OwnerSession = Depends(require_owner)) -> dict[str, str]:
    return {"email": owner.email}
