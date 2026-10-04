from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.media.service import media_key
from app.models.genealogy import Media

router = APIRouter()

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_MEDIA_BYTES = 10 * 1024 * 1024


class MediaResponse(BaseModel):
    id: UUID
    original_filename: str
    is_published: bool


class PublicMediaResponse(BaseModel):
    id: UUID
    original_filename: str
    url: str


@router.post("/admin/media", status_code=status.HTTP_201_CREATED, response_model=MediaResponse)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    _: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> MediaResponse:
    if not file.filename or file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(status_code=422, detail="Разрешены JPEG, PNG и PDF.")
    content = await file.read(MAX_MEDIA_BYTES + 1)
    if len(content) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=422, detail="Файл не должен превышать 10 МБ.")
    key = media_key(file.filename)
    request.app.state.media_storage.put(key, content, file.content_type)
    media = Media(storage_key=key, media_type=file.content_type, original_filename=file.filename)
    session.add(media)
    session.commit()
    session.refresh(media)
    return MediaResponse(id=media.id, original_filename=media.original_filename, is_published=media.is_published)


@router.patch("/admin/media/{media_id}/publish", status_code=204)
def publish_media(media_id: UUID, _: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    media = session.get(Media, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Материал не найден.")
    media.is_published = True
    session.commit()


@router.get("/media/{media_id}", response_model=PublicMediaResponse)
def get_media(media_id: UUID, request: Request, session: Session = Depends(get_session)) -> PublicMediaResponse:
    media = session.get(Media, media_id)
    if media is None or not media.is_published:
        raise HTTPException(status_code=404, detail="Материал не найден.")
    return PublicMediaResponse(id=media.id, original_filename=media.original_filename, url=request.app.state.media_storage.public_url(media.storage_key))
