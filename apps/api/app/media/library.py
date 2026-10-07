"""Owner media library: files stored in the database, previews, visibility, portrait."""

import io
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app.genealogy.person_editing import PersonEditError
from app.models.genealogy import ChangeLog, Media, MediaLink, Person

MAX_MEDIA_BYTES = 10 * 1024 * 1024
PREVIEW_SIZE = (400, 400)
MAX_PIXELS = 80_000_000  # refuse before decoding: a small file can hold a huge picture
TOO_BIG = "Фото слишком большое: не больше 80 мегапикселей. Уменьшите его и загрузите снова."
IMAGE_TYPES = ("image/jpeg", "image/png")
SIGNATURES = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG", "image/png"), (b"%PDF-", "application/pdf"))


class MediaError(PersonEditError):
    """Owner-facing (Russian) reason why a file action is refused."""


def _uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def sniff(content: bytes) -> str:
    """The media type by the file's first bytes; the browser's claim is not trusted."""
    for signature, media_type in SIGNATURES:
        if content.startswith(signature):
            return media_type
    raise MediaError("Разрешены JPEG, PNG и PDF.")


def make_preview(content: bytes) -> bytes:
    """A JPEG at most 400×400, turned upright by EXIF; transparency goes on white."""
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > MAX_PIXELS:
                raise MediaError(TOO_BIG)
            source.draft("RGB", PREVIEW_SIZE)  # JPEG decodes at reduced size, saving memory
            picture = ImageOps.exif_transpose(source)
            picture.thumbnail(PREVIEW_SIZE)
            if picture.mode != "RGB":
                background = Image.new("RGB", picture.size, "white")
                background.paste(picture, mask=picture.convert("RGBA").getchannel("A"))
                picture = background
            buffer = io.BytesIO()
            picture.save(buffer, "JPEG", quality=85)
            return buffer.getvalue()
    except Image.DecompressionBombError as error:  # Pillow refuses gigantic images while opening them
        raise MediaError(TOO_BIG) from error
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise MediaError("Файл повреждён или это не изображение.") from error


def _log(session: Session, entity_type: str, entity_id: UUID, owner_email: str, before: dict, after: dict) -> None:
    session.add(ChangeLog(entity_type=entity_type, entity_id=entity_id, owner_email=owner_email, before=before, after=after))


def _owner_of(session: Session, media: Media) -> Person | None:
    person_id = session.scalar(select(MediaLink.person_id).where(MediaLink.media_id == media.id, MediaLink.person_id.is_not(None)).limit(1))
    return session.get(Person, person_id) if person_id else None


def media_view(session: Session, media: Media, owner: bool) -> dict:
    view = {
        "id": str(media.id),
        "original_filename": media.original_filename,
        "media_type": media.media_type,
        "caption": media.caption,
        "date_label": media.date_label,
        "file_url": f"/api/v1/media/{media.id}/file",
        "preview_url": f"/api/v1/media/{media.id}/preview" if media.media_type in IMAGE_TYPES else None,
    }
    if owner:
        person = _owner_of(session, media)
        view |= {"is_published": media.is_published, "is_portrait": bool(person and person.portrait_media_id == media.id)}
    return view


def upload(session: Session, person_id: UUID | str, filename: str, content: bytes, owner_email: str) -> dict:
    person = session.get(Person, _uuid(person_id))
    if person is None:
        raise LookupError("Человек не найден.")
    if len(content) > MAX_MEDIA_BYTES:
        raise MediaError("Файл не должен превышать 10 МБ.")
    media_type = sniff(content)
    preview = make_preview(content) if media_type in IMAGE_TYPES else None
    name = (filename or "").strip()[:255] or "файл"
    try:
        media = Media(media_type=media_type, original_filename=name, is_published=True, content=content, preview=preview)
        session.add(media)
        session.flush()
        session.add(MediaLink(media_id=media.id, person_id=person.id))
        _log(session, "media", media.id, owner_email, {}, {"person_id": str(person.id), "original_filename": name, "media_type": media_type})
        session.commit()
    except Exception:
        session.rollback()
        raise
    return media_view(session, media, owner=True)


CAPTION_LIMIT, DATE_LIMIT, BIOGRAPHY_LIMIT = 500, 64, 20000


def _clean(value: str | None, limit: int, message: str) -> str | None:
    cleaned = (value or "").strip()
    if len(cleaned) > limit:
        raise MediaError(message)
    return cleaned or None


def _live(session: Session, media_id: UUID | str) -> Media:
    media = session.get(Media, _uuid(media_id))
    if media is None or media.is_deleted:
        raise LookupError("Файл не найден.")
    return media


def _person_media(person_id: UUID):
    return (
        select(Media)
        .join(MediaLink, MediaLink.media_id == Media.id)
        .where(MediaLink.person_id == person_id, Media.is_deleted.is_(False))
        .order_by(Media.created_at, Media.id)
    )


def owner_media(session: Session, person_id: UUID | str) -> list[dict]:
    person = session.get(Person, _uuid(person_id))
    if person is None:
        raise LookupError("Человек не найден.")
    return [media_view(session, item, owner=True) for item in session.scalars(_person_media(person.id))]


def _drop_portrait(session: Session, media: Media, owner_email: str) -> None:
    person = _owner_of(session, media)
    if person is not None and person.portrait_media_id == media.id:
        person.portrait_media_id = None
        _log(session, "person", person.id, owner_email, {"portrait_media_id": str(media.id)}, {"portrait_media_id": None})


def update_media(session: Session, media_id: UUID | str, changes: dict, owner_email: str) -> dict:
    """Change any of caption, date_label, is_published; hiding the portrait clears it."""
    media = _live(session, media_id)
    try:
        values = {}
        if "caption" in changes:
            values["caption"] = _clean(changes["caption"], CAPTION_LIMIT, "Подпись не может быть длиннее 500 символов.")
        if "date_label" in changes:
            values["date_label"] = _clean(changes["date_label"], DATE_LIMIT, "Дата не может быть длиннее 64 символов.")
        if changes.get("is_published") is not None:
            values["is_published"] = bool(changes["is_published"])
        before, after = {}, {}
        for field, value in values.items():
            if getattr(media, field) != value:
                before[field], after[field] = getattr(media, field), value
                setattr(media, field, value)
        if after.get("is_published") is False:
            _drop_portrait(session, media, owner_email)
        if after:
            _log(session, "media", media.id, owner_email, before, after)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return media_view(session, media, owner=True)


def delete_media(session: Session, media_id: UUID | str, owner_email: str) -> None:
    """The file leaves the site; the row stays in the database so it can be recovered by hand."""
    media = _live(session, media_id)
    try:
        _drop_portrait(session, media, owner_email)
        media.is_deleted = True
        _log(session, "media", media.id, owner_email, {"is_deleted": False}, {"is_deleted": True})
        session.commit()
    except Exception:
        session.rollback()
        raise


def set_portrait(session: Session, person_id: UUID | str, media_id: UUID | str | None, owner_email: str) -> dict:
    person = session.get(Person, _uuid(person_id))
    if person is None:
        raise LookupError("Человек не найден.")
    chosen = None
    if media_id is not None:
        chosen = _live(session, media_id)
        holder = _owner_of(session, chosen)
        if holder is None or holder.id != person.id:
            raise MediaError("Этот файл принадлежит другому человеку.")
        if chosen.media_type not in IMAGE_TYPES:
            raise MediaError("Портретом может быть только фото.")
        if not chosen.is_published:
            raise MediaError("Скрытое фото не может быть портретом.")
    before = str(person.portrait_media_id) if person.portrait_media_id else None
    after = str(chosen.id) if chosen else None
    if before != after:
        person.portrait_media_id = chosen.id if chosen else None
        _log(session, "person", person.id, owner_email, {"portrait_media_id": before}, {"portrait_media_id": after})
    session.commit()
    return {"portrait_media_id": after}


def set_biography(session: Session, person_id: UUID | str, text: str | None, owner_email: str) -> dict:
    person = session.get(Person, _uuid(person_id))
    if person is None:
        raise LookupError("Человек не найден.")
    normalised = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    value = _clean(normalised, BIOGRAPHY_LIMIT, "Биография не может быть длиннее 20000 символов.")
    if person.biography != value:
        _log(session, "person", person.id, owner_email, {"biography": person.biography}, {"biography": value})
        person.biography = value
    session.commit()
    return {"biography": value}


def media_file(session: Session, media_id: UUID | str, kind: str, owner: bool) -> tuple[bytes, str, str] | None:
    """File or preview bytes with type and name, or ``None`` when this viewer may not see it."""
    column = Media.preview if kind == "preview" else Media.content  # load only the bytes being sent
    media = session.scalar(select(Media).where(Media.id == _uuid(media_id)).options(undefer(column)))
    if media is None or media.is_deleted:
        return None
    if not owner:
        person = _owner_of(session, media)
        if not media.is_published or person is None or person.is_archived:
            return None
    if kind == "preview":
        if not media.preview:
            return None
        stem = media.original_filename.rsplit(".", 1)[0] or "preview"
        return media.preview, "image/jpeg", f"{stem}.jpg"
    if media.content is None:
        return None
    return media.content, media.media_type, media.original_filename
