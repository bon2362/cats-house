from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, optional_owner, require_owner
from app.db.session import get_session
from app.genealogy.person_editing import PersonEditError
from app.media.library import MAX_MEDIA_BYTES, delete_media, media_file, owner_media, set_biography, set_portrait, update_media, upload

router = APIRouter()


class MediaChangeBody(BaseModel):
    caption: str | None = None
    date_label: str | None = None
    is_published: bool | None = None


class PortraitBody(BaseModel):
    media_id: UUID | None = None


class BiographyBody(BaseModel):
    biography: str | None = None


def _errors(call):
    try:
        return call()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PersonEditError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/admin/people/{person_id}/media")
def list_owner_media(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> list[dict]:
    return _errors(lambda: owner_media(session, person_id))


@router.post("/admin/people/{person_id}/media", status_code=201)
async def upload_person_media(person_id: UUID, file: UploadFile = File(...), owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    content = await file.read(MAX_MEDIA_BYTES + 1)
    return _errors(lambda: upload(session, person_id, file.filename or "", content, owner.email))


@router.patch("/admin/media/{media_id}")
def change_media(media_id: UUID, body: MediaChangeBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    return _errors(lambda: update_media(session, media_id, body.model_dump(exclude_unset=True), owner.email))


@router.delete("/admin/media/{media_id}", status_code=204)
def remove_media(media_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    _errors(lambda: delete_media(session, media_id, owner.email))


@router.put("/admin/people/{person_id}/portrait")
def choose_portrait(person_id: UUID, body: PortraitBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    return _errors(lambda: set_portrait(session, person_id, body.media_id, owner.email))


@router.patch("/admin/people/{person_id}/biography")
def save_biography(person_id: UUID, body: BiographyBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    return _errors(lambda: set_biography(session, person_id, body.biography, owner.email))


def _deliver(session: Session, media_id: UUID, kind: str, owner: OwnerSession | None) -> Response:
    found = media_file(session, media_id, kind, owner is not None)
    if found is None:
        raise HTTPException(status_code=404, detail="Файл не найден.")
    content, media_type, filename = found
    return Response(content, media_type=media_type, headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=300",
    })


@router.get("/media/{media_id}/file")
def media_file_route(media_id: UUID, owner: OwnerSession | None = Depends(optional_owner), session: Session = Depends(get_session)) -> Response:
    return _deliver(session, media_id, "file", owner)


@router.get("/media/{media_id}/preview")
def media_preview_route(media_id: UUID, owner: OwnerSession | None = Depends(optional_owner), session: Session = Depends(get_session)) -> Response:
    return _deliver(session, media_id, "preview", owner)
