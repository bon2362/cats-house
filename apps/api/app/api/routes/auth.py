from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies import OwnerSession, is_owner, require_owner
from app.auth.service import verify_owner_password, verify_totp

router = APIRouter()


class LoginRequest(BaseModel):
    password: str
    totp_code: str | None = None


@router.get("/auth/status")
def owner_status(request: Request) -> dict[str, bool]:
    return {
        "authenticated": is_owner(request),
        "totp_required": request.app.state.settings.owner_totp_secret is not None,
    }


@router.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login_owner(payload: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings
    throttle = request.app.state.login_throttle
    address = request.client.host if request.client else "unknown"

    # The attempt is counted before the password check; success removes it.
    wait = throttle.reserve(address)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_owner_password(payload.password, settings.owner_password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный пароль.")
    if settings.owner_totp_secret and not verify_totp(payload.totp_code, settings.owner_totp_secret.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный одноразовый код.")

    throttle.reset(address)
    request.session["owner_email"] = settings.owner_email
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_owner(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/session")
def get_owner_session(owner: OwnerSession = Depends(require_owner)) -> dict[str, str]:
    return {"email": owner.email}
