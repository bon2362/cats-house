from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.api.dependencies import OwnerSession, require_owner
from app.auth.service import verify_owner_password

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login", status_code=status.HTTP_204_NO_CONTENT)
def login_owner(payload: LoginRequest, request: Request) -> Response:
    settings = request.app.state.settings

    if not verify_owner_password(payload.password, settings.owner_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный пароль.",
        )

    request.session["owner_email"] = settings.owner_email
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/session")
def get_owner_session(owner: OwnerSession = Depends(require_owner)) -> dict[str, str]:
    return {"email": owner.email}
