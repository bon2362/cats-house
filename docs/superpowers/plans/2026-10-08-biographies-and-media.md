# Biographies and Media Implementation Plan (owner editor, stage 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner writes biographies and uploads photos and PDF documents per person (caption, date, hide/show, delete, one portrait); guests see a biography, a gallery and the portrait on the page and in the tree. Files live in PostgreSQL.

**Architecture:** Migration `0009` adds file bytes, preview bytes, caption, date label, upload time and a deleted flag to `media`, plus `people.portrait_media_id`. A new service `app/media/library.py` holds all rules (sniffing, previews with Pillow, visibility, portrait, logging); `routes/media.py` is rewritten around it; S3 code goes away. The web app gets `cats-biography-section` and `cats-media-section`.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pillow (new), pytest + testcontainers; Lit, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-08-biographies-and-media-design.md` (authority).

## Global Constraints

- Russian user-visible text. Exact refusals: «Разрешены JPEG, PNG и PDF.», «Файл не должен превышать 10 МБ.», «Файл повреждён или это не изображение.», «Подпись не может быть длиннее 500 символов.», «Дата не может быть длиннее 64 символов.», «Портретом может быть только фото.», «Скрытое фото не может быть портретом.», «Этот файл принадлежит другому человеку.», «Биография не может быть длиннее 20000 символов.»; 404 «Человек не найден.», «Файл не найден.»; 401 guests.
- Limits: 10 MB upload (`MAX_MEDIA_BYTES = 10 * 1024 * 1024`), preview max 400×400, JPEG quality 85, caption 500, date label 64, biography 20000.
- Visibility: guest sees a file iff `is_published and not is_deleted` and its person is not archived; owner sees every non-deleted file. Same rule for `/media/{id}/file` and `/preview`.
- Lists never load `content`/`preview` (deferred columns).
- Every change is logged in `change_logs` (`media` / `person`).
- No real people's data in tests. No commits unless the owner asks.

## Review Focus

1. A hidden or deleted file must not be served to a guest by its direct URL — Task 3.
2. Hiding or deleting the portrait clears `portrait_media_id`, so the tree and header never show a hidden photo — Task 2.
3. A PDF must never become a portrait or the tree photo — Tasks 2, 3.
4. File type is decided by content, not by the browser's header (a renamed `.exe` is refused) — Task 1.
5. A failed upload of one file in a multi-file selection does not stop the others and shows its own reason — Task 6.

---

### Task 1: Storage model and media library core

**Files:**
- Create: `apps/api/alembic/versions/0009_media_in_database.py`, `apps/api/app/media/library.py`
- Modify: `apps/api/app/models/genealogy.py`, `apps/api/pyproject.toml` (add `"pillow>=11,<12"`; remove `boto3`)
- Test: `apps/api/tests/test_media_library.py`

**Interfaces (produces):**
- `Media` gains `content: bytes | None` (deferred), `preview: bytes | None` (deferred), `caption: str | None`, `date_label: str | None`, `created_at: datetime`, `is_deleted: bool`; `storage_key` nullable. `Person.portrait_media_id: UUID | None`.
- `library.MediaError(PersonEditError)`; `library.sniff(content: bytes) -> str` (media type or raises); `library.make_preview(content: bytes) -> bytes`; `library.upload(session, person_id, filename, content, owner_email) -> dict`; `library.media_view(session, media, owner: bool) -> dict`.
- Media view: `{id, original_filename, media_type, caption, date_label, file_url, preview_url}` plus for owner `is_published`, `is_portrait`. URLs: `/api/v1/media/{id}/file`, `/api/v1/media/{id}/preview` (`None` for PDF).

- [ ] **Step 1: Install Pillow** — add `"pillow>=11,<12"` to `[project] dependencies`, drop `"boto3…"`, then `cd apps/api && .venv/bin/pip install "pillow>=11,<12"`.

- [ ] **Step 2: Failing tests** `tests/test_media_library.py` (session fixture as in `test_family_editing.py`, with `engine.dispose()`):

```python
import io

import pytest
from PIL import Image

from app.media.library import MediaError, make_preview, sniff, upload
from app.models.genealogy import ChangeLog, Media, MediaLink, Person

OWNER = "owner@example.test"


def image_bytes(kind="JPEG", size=(1200, 800), mode="RGB", exif_rotate=False):
    buffer = io.BytesIO()
    picture = Image.new(mode, size, "red")
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90° on display
        picture.save(buffer, kind, exif=exif)
    else:
        picture.save(buffer, kind)
    return buffer.getvalue()


def test_type_is_decided_by_content():
    assert sniff(image_bytes("JPEG")) == "image/jpeg"
    assert sniff(image_bytes("PNG")) == "image/png"
    assert sniff(b"%PDF-1.7 ...") == "application/pdf"
    with pytest.raises(MediaError, match="Разрешены JPEG, PNG и PDF."):
        sniff(b"MZ\x90\x00 not really a photo")


def test_preview_fits_400_and_follows_exif_rotation():
    preview = Image.open(io.BytesIO(make_preview(image_bytes(size=(1200, 800), exif_rotate=True))))
    assert preview.format == "JPEG" and preview.size == (267, 400)
    transparent = Image.open(io.BytesIO(make_preview(image_bytes("PNG", (100, 50), "RGBA"))))
    assert transparent.size == (100, 50) and transparent.mode == "RGB"


def test_broken_image_is_refused():
    with pytest.raises(MediaError, match="повреждён"):
        make_preview(b"\xff\xd8\xff" + b"garbage")


def test_upload_stores_file_preview_link_and_log(session):
    person = Person(display_name="Анна")
    session.add(person)
    session.commit()

    view = upload(session, person.id, "anna.jpg", image_bytes(), OWNER)

    media = session.get(Media, view["id"])
    assert (media.media_type, media.is_published, media.is_deleted) == ("image/jpeg", True, False)
    assert media.content == image_bytes() and media.preview
    assert session.query(MediaLink).filter_by(media_id=media.id, person_id=person.id).count() == 1
    assert view["file_url"] == f"/api/v1/media/{media.id}/file" and view["preview_url"] == f"/api/v1/media/{media.id}/preview"
    entry = session.query(ChangeLog).filter_by(entity_type="media").one()
    assert entry.after == {"person_id": str(person.id), "original_filename": "anna.jpg", "media_type": "image/jpeg"}


def test_pdf_has_no_preview_and_size_limit_is_enforced(session):
    person = Person(display_name="Анна")
    session.add(person)
    session.commit()

    assert upload(session, person.id, "doc.pdf", b"%PDF-1.4 x", OWNER)["preview_url"] is None
    with pytest.raises(MediaError, match="10 МБ"):
        upload(session, person.id, "big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024), OWNER)
    with pytest.raises(LookupError, match="Человек не найден"):
        upload(session, __import__("uuid").uuid4(), "doc.pdf", b"%PDF-1.4", OWNER)
```

(`Person(display_name=…)` works since `import_run_id` is nullable since stage 2.)

- [ ] **Step 3:** `.venv/bin/pytest tests/test_media_library.py -q` → FAIL (module missing).

- [ ] **Step 4: Implement**

Model (`genealogy.py`), using `from sqlalchemy.orm import deferred` and `LargeBinary, DateTime, func`:

```python
class Media(Base):
    __tablename__ = "media"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    media_type: Mapped[str] = mapped_column(String(32))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    is_published: Mapped[bool] = mapped_column(default=False, server_default="false")
    content: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    preview: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, nullable=True))
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(default=False, server_default="false")
```

`Person.portrait_media_id: Mapped[UUID | None] = mapped_column(ForeignKey("media.id"), nullable=True)`.

Migration `0009_media_in_database` (down_revision `0008_owner_created_records`), idempotent like 0008 (`sa.inspect(...).get_columns`): add the six media columns, make `storage_key` nullable, add `people.portrait_media_id` with FK `fk_people_portrait_media`. Downgrade drops them.

`app/media/library.py`:

```python
"""Owner media library: files stored in the database, previews, visibility, portrait."""

import io
from uuid import UUID

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.genealogy.person_editing import PersonEditError
from app.models.genealogy import ChangeLog, Media, MediaLink, Person

MAX_MEDIA_BYTES = 10 * 1024 * 1024
PREVIEW_SIZE = (400, 400)
IMAGE_TYPES = ("image/jpeg", "image/png")
SIGNATURES = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG", "image/png"), (b"%PDF-", "application/pdf"))


class MediaError(PersonEditError):
    """Owner-facing (Russian) reason why a file action is refused."""


def sniff(content: bytes) -> str:
    for signature, media_type in SIGNATURES:
        if content.startswith(signature):
            return media_type
    raise MediaError("Разрешены JPEG, PNG и PDF.")


def make_preview(content: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(content)) as source:
            picture = ImageOps.exif_transpose(source)
            picture.thumbnail(PREVIEW_SIZE)
            if picture.mode != "RGB":
                background = Image.new("RGB", picture.size, "white")
                background.paste(picture, mask=picture.convert("RGBA").getchannel("A"))
                picture = background
            buffer = io.BytesIO()
            picture.save(buffer, "JPEG", quality=85)
            return buffer.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise MediaError("Файл повреждён или это не изображение.") from error


def _log(session: Session, entity_type: str, entity_id: UUID, owner_email: str, before: dict, after: dict) -> None:
    session.add(ChangeLog(entity_type=entity_type, entity_id=entity_id, owner_email=owner_email, before=before, after=after))


def media_view(session: Session, media: Media, owner: bool) -> dict:
    view = {
        "id": str(media.id), "original_filename": media.original_filename, "media_type": media.media_type,
        "caption": media.caption, "date_label": media.date_label,
        "file_url": f"/api/v1/media/{media.id}/file",
        "preview_url": f"/api/v1/media/{media.id}/preview" if media.media_type in IMAGE_TYPES else None,
    }
    if owner:
        person = _owner_of(session, media)
        view |= {"is_published": media.is_published, "is_portrait": bool(person and person.portrait_media_id == media.id)}
    return view


def _owner_of(session: Session, media: Media) -> Person | None:
    link = session.query(MediaLink).filter(MediaLink.media_id == media.id, MediaLink.person_id.is_not(None)).first()
    return session.get(Person, link.person_id) if link else None


def upload(session: Session, person_id: UUID, filename: str, content: bytes, owner_email: str) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    if len(content) > MAX_MEDIA_BYTES:
        raise MediaError("Файл не должен превышать 10 МБ.")
    media_type = sniff(content)
    preview = make_preview(content) if media_type in IMAGE_TYPES else None
    name = (filename or "файл").strip()[:255]
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
```

- [ ] **Step 5:** `.venv/bin/pytest tests/test_media_library.py -q`, then full `pytest -q` → PASS (old S3 media tests still pass at this point: they set their own fake storage).

---

### Task 2: Owner actions — caption, visibility, delete, portrait, biography

**Files:**
- Modify: `apps/api/app/media/library.py`, `apps/api/app/genealogy/person_editing.py` (`editable_person` gains `biography`)
- Test: `apps/api/tests/test_media_library.py`, `apps/api/tests/test_person_editing.py` (if it compares the full editable dict, add `"biography": None`)

**Interfaces (produces):** `owner_media(session, person_id) -> list[dict]`; `update_media(session, media_id, changes: dict, owner_email) -> dict` (keys `caption`, `date_label`, `is_published`, any subset); `delete_media(session, media_id, owner_email) -> None`; `set_portrait(session, person_id, media_id: UUID | None, owner_email) -> dict` (`{"portrait_media_id"}`); `set_biography(session, person_id, text: str | None, owner_email) -> dict` (`{"biography"}`).

- [ ] **Step 1: Failing tests** (append):

```python
@pytest.fixture
def anna(session):
    person = Person(display_name="Анна")
    other = Person(display_name="Пётр")
    session.add_all([person, other])
    session.commit()
    photo = upload(session, person.id, "anna.jpg", image_bytes(), OWNER)["id"]
    document = upload(session, person.id, "doc.pdf", b"%PDF-1.4", OWNER)["id"]
    foreign = upload(session, other.id, "petr.jpg", image_bytes(), OWNER)["id"]
    return {"person": person, "photo": photo, "document": document, "foreign": foreign}


def test_caption_and_date_are_trimmed_and_limited(session, anna):
    view = update_media(session, anna["photo"], {"caption": "  Свадьба  ", "date_label": " около 1950 "}, OWNER)
    assert (view["caption"], view["date_label"]) == ("Свадьба", "около 1950")
    assert update_media(session, anna["photo"], {"caption": "   "}, OWNER)["caption"] is None
    with pytest.raises(MediaError, match="500"):
        update_media(session, anna["photo"], {"caption": "я" * 501}, OWNER)
    with pytest.raises(MediaError, match="64"):
        update_media(session, anna["photo"], {"date_label": "1" * 65}, OWNER)


def test_portrait_rules(session, anna):
    assert set_portrait(session, anna["person"].id, anna["photo"], OWNER) == {"portrait_media_id": anna["photo"]}
    for media_id, message in ((anna["document"], "только фото"), (anna["foreign"], "другому человеку")):
        with pytest.raises(MediaError, match=message):
            set_portrait(session, anna["person"].id, media_id, OWNER)
    update_media(session, anna["photo"], {"is_published": False}, OWNER)
    assert session.get(Person, anna["person"].id).portrait_media_id is None
    with pytest.raises(MediaError, match="Скрытое фото"):
        set_portrait(session, anna["person"].id, anna["photo"], OWNER)


def test_deleting_the_portrait_clears_it_and_hides_the_file_from_lists(session, anna):
    set_portrait(session, anna["person"].id, anna["photo"], OWNER)

    delete_media(session, anna["photo"], OWNER)

    assert session.get(Person, anna["person"].id).portrait_media_id is None
    assert session.get(Media, anna["photo"]).is_deleted is True
    assert [item["id"] for item in owner_media(session, anna["person"].id)] == [anna["document"]]
    with pytest.raises(LookupError, match="Файл не найден"):
        delete_media(session, anna["photo"], OWNER)


def test_owner_list_marks_hidden_and_portrait_in_upload_order(session, anna):
    set_portrait(session, anna["person"].id, anna["photo"], OWNER)
    update_media(session, anna["document"], {"is_published": False}, OWNER)

    items = owner_media(session, anna["person"].id)

    assert [(item["id"], item["is_published"], item["is_portrait"]) for item in items] == [(anna["photo"], True, True), (anna["document"], False, False)]


def test_biography_is_normalised_limited_and_logged(session, anna):
    assert set_biography(session, anna["person"].id, "  Первый абзац.\r\n\r\nВторой.  ", OWNER) == {"biography": "Первый абзац.\n\nВторой."}
    assert set_biography(session, anna["person"].id, "   ", OWNER) == {"biography": None}
    with pytest.raises(MediaError, match="20000"):
        set_biography(session, anna["person"].id, "я" * 20001, OWNER)
    logged = [entry.after for entry in session.query(ChangeLog).filter_by(entity_type="person")]
    assert logged == [{"biography": "Первый абзац.\n\nВторой."}, {"biography": None}]
```

Order rule: `owner_media` orders by `Media.created_at, Media.id`; upload order is preserved because each upload commits separately (server `now()` per transaction).

- [ ] **Step 2:** run → FAIL (names missing).

- [ ] **Step 3: Implement** in `library.py`:

```python
CAPTION_LIMIT, DATE_LIMIT, BIOGRAPHY_LIMIT = 500, 64, 20000


def _clean(value: str | None, limit: int, message: str) -> str | None:
    cleaned = (value or "").strip()
    if len(cleaned) > limit:
        raise MediaError(message)
    return cleaned or None


def _live(session: Session, media_id: UUID) -> Media:
    media = session.get(Media, media_id)
    if media is None or media.is_deleted:
        raise LookupError("Файл не найден.")
    return media


def _person_media(session: Session, person_id: UUID):
    return (
        select(Media)
        .join(MediaLink, MediaLink.media_id == Media.id)
        .where(MediaLink.person_id == person_id, Media.is_deleted.is_(False))
        .order_by(Media.created_at, Media.id)
    )


def owner_media(session: Session, person_id: UUID) -> list[dict]:
    if session.get(Person, person_id) is None:
        raise LookupError("Человек не найден.")
    return [media_view(session, item, owner=True) for item in session.scalars(_person_media(session, person_id))]


def _drop_portrait(session: Session, media: Media, owner_email: str) -> None:
    person = _owner_of(session, media)
    if person is not None and person.portrait_media_id == media.id:
        person.portrait_media_id = None
        _log(session, "person", person.id, owner_email, {"portrait_media_id": str(media.id)}, {"portrait_media_id": None})


def update_media(session: Session, media_id: UUID, changes: dict, owner_email: str) -> dict:
    media = _live(session, media_id)
    try:
        before, after = {}, {}
        values = {}
        if "caption" in changes:
            values["caption"] = _clean(changes["caption"], CAPTION_LIMIT, "Подпись не может быть длиннее 500 символов.")
        if "date_label" in changes:
            values["date_label"] = _clean(changes["date_label"], DATE_LIMIT, "Дата не может быть длиннее 64 символов.")
        if "is_published" in changes:
            values["is_published"] = bool(changes["is_published"])
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


def delete_media(session: Session, media_id: UUID, owner_email: str) -> None:
    media = _live(session, media_id)
    try:
        _drop_portrait(session, media, owner_email)
        media.is_deleted = True
        _log(session, "media", media.id, owner_email, {"is_deleted": False}, {"is_deleted": True})
        session.commit()
    except Exception:
        session.rollback()
        raise


def set_portrait(session: Session, person_id: UUID, media_id: UUID | None, owner_email: str) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    if media_id is not None:
        media = _live(session, media_id)
        owner = _owner_of(session, media)
        if owner is None or owner.id != person.id:
            raise MediaError("Этот файл принадлежит другому человеку.")
        if media.media_type not in IMAGE_TYPES:
            raise MediaError("Портретом может быть только фото.")
        if not media.is_published:
            raise MediaError("Скрытое фото не может быть портретом.")
    before = str(person.portrait_media_id) if person.portrait_media_id else None
    after = str(media_id) if media_id else None
    if before != after:
        person.portrait_media_id = media_id
        _log(session, "person", person.id, owner_email, {"portrait_media_id": before}, {"portrait_media_id": after})
    session.commit()
    return {"portrait_media_id": after}


def set_biography(session: Session, person_id: UUID, text: str | None, owner_email: str) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    value = _clean((text or "").replace("\r\n", "\n").replace("\r", "\n"), BIOGRAPHY_LIMIT, "Биография не может быть длиннее 20000 символов.")
    if person.biography != value:
        _log(session, "person", person.id, owner_email, {"biography": person.biography}, {"biography": value})
        person.biography = value
    session.commit()
    return {"biography": value}
```

Note `media_id` arrives as `UUID` from routes but tests pass the string id from views; `session.get` accepts both for `PostgreSQLUUID(as_uuid=True)` only with `UUID` — convert at the top of each public function with `UUID(str(media_id))`. Same for `set_portrait`’s returned value (string).

`person_editing.editable_person` adds `"biography": person.biography`.

- [ ] **Step 4:** run file and full suite → PASS.

---

### Task 3: Routes — owner API, file delivery, public person page, tree

**Files:**
- Rewrite: `apps/api/app/api/routes/media.py`
- Modify: `apps/api/app/api/routes/people.py`, `apps/api/app/api/routes/tree.py`, `apps/api/app/genealogy/read_service.py` (`public_person_media` uses the visibility rule and upload order; add `public_portrait(session, person) -> Media | None`), `apps/api/app/main.py` (no `media_storage`), `apps/api/app/core/config.py` (`s3_endpoint: AnyHttpUrl | None = None`, `s3_bucket: str | None = None`), delete `apps/api/app/media/service.py`
- Test: rewrite `apps/api/tests/test_media_api.py`; update media tests in `test_public_people_api.py`, `test_public_tree_api.py`; config test if one asserts S3 required

**Interfaces (produces):** routes from the spec's API tables. Owner reads (`GET /media/{id}/file`) detect the owner with the existing session check used by `require_owner` (read the owner from the request session without raising; check `app/api/dependencies.py` for the helper — if only `require_owner` exists, add `optional_owner(request) -> OwnerSession | None` next to it).

- [ ] **Step 1: Failing tests** `tests/test_media_api.py` (replace file; reuse `client`, login with `test-owner-password`; create people via `client.app.state.session_factory()`; image bytes via Pillow helper copied from Task 1):

```python
def test_guests_cannot_upload_or_change_media(client): ...
    # POST /admin/people/{id}/media, PATCH /admin/media/{id}, DELETE, PUT portrait, PATCH biography → 401

def test_owner_uploads_a_photo_and_guests_see_it_and_its_files(client):
    # upload → 201 with file_url/preview_url; GET /people/{id} media == [view without owner fields]
    # GET file → 200, bytes equal, content-type image/jpeg, nosniff, inline filename*
    # GET preview → 200 image/jpeg

def test_hidden_deleted_and_hidden_person_files_are_404_for_guests_but_hidden_is_served_to_owner(client):
    # hide → guest 404 on file & preview, owner 200; delete → owner 404 too; archived person → guest 404

def test_pdf_has_no_preview_and_upload_refusals_are_russian(client):
    # pdf preview 404; b"MZ.." → 422 «Разрешены JPEG, PNG и PDF.»; >10MB → 422; unknown person → 404

def test_portrait_appears_on_the_person_page_and_in_the_tree(client):
    # PUT portrait → 200; /people/{id} portrait == {id, preview_url, file_url}; /tree/{id}?mode=close photo_url == preview_url
    # PUT portrait with a pdf → 422 «Портретом может быть только фото.»

def test_owner_edits_caption_and_biography_and_reads_hidden_files(client):
    # PATCH caption/date → 200; PATCH biography → 200 {biography}; GET /people/{id}.biography; GET /admin/people/{id}.biography
    # GET /admin/people/{id}/media lists hidden with is_published False
```

Write each test fully when implementing (exact asserts as in the comments; refusals compared with the exact Russian texts from Global Constraints).

In `test_public_people_api.py` replace `test_public_card_includes_only_published_attached_media` with a DB-level test: two `Media` rows (published/hidden, `content=b"%PDF-1.4"`, `media_type="application/pdf"`) linked to the person → response `media` has only the published one with `file_url`, `preview_url: None`, `caption: None`, `date_label: None`, `media_type`. In `test_public_tree_api.py` replace `test_tree_exposes_only_a_published_person_photo`: a published JPEG that is not the portrait gives `photo_url None`; making it the portrait gives `/api/v1/media/{id}/preview`; hiding it gives `None`.

- [ ] **Step 2:** run → FAIL.

- [ ] **Step 3: Implement**

`routes/media.py` (new):

```python
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from urllib.parse import quote

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
```

`library.media_file(session, media_id, kind, owner) -> tuple[bytes, str, str] | None`: load media; `None` if missing or deleted; for guests also `None` unless published and the linked person is not archived; for `preview` `None` when `preview` is empty, returning `(preview, "image/jpeg", name + ".jpg")`; for `file` `(content, media_type, original_filename)`. Use `undefer` loading only here.

`read_service.public_person_media`: published, not deleted, order by `created_at, id`. `public_portrait(session, person)`: the `Media` at `person.portrait_media_id` if published and not deleted, else `None`.

`routes/people.py`: `PublicMediaResponse` becomes the guest view (`id, original_filename, media_type, caption, date_label, file_url, preview_url`) built with `media_view(session, item, owner=False)`; `PersonResponse.portrait: PortraitResponse | None` (`id, preview_url, file_url`). Remove `request.app.state.media_storage` use.

`routes/tree.py`: `photo_url` = `f"/api/v1/media/{portrait.id}/preview"` when the person is not hidden and `public_portrait` returns a photo.

`main.py`: drop the `S3MediaStorage` import and `app.state.media_storage`. `config.py`: S3 fields optional. Delete `app/media/service.py`.

- [ ] **Step 4:** full suite → PASS (the backup scripts are fixed in Task 4; `grep -rn "media.service" ../../scripts` must be addressed there).

---

### Task 4: Archive and backup scripts

**Files:**
- Modify: `apps/api/app/exports/service.py`, `scripts/create-local-backup.py`, `scripts/restore-local-backup.py`
- Test: `apps/api/tests/test_archive_service.py`

**Interfaces (produces):** `build_archive` media manifest items gain `caption, date_label, created_at (ISO), is_deleted`; people gain `portrait_archive_id`. New `media_contents(session) -> Iterator[tuple[str, bytes]]` (archive id, file bytes, skipping rows without content). `restore_archive(session, archive, contents: dict[str, bytes] | None = None)` puts bytes into `content`, rebuilds `preview` for images with `make_preview`, restores portrait.

- [ ] **Step 1: Failing test** (append):

```python
def test_archive_round_trip_keeps_files_captions_and_portrait(postgres_url):
    # source: person + JPEG (Pillow) uploaded via library.upload, caption/date set, made portrait; hidden PDF
    # archive = build_archive(source); contents = dict(media_contents(source))
    # restore_archive(target, archive, contents)
    # target: two media with same bytes, caption/date kept, PDF still hidden, image has preview, person.portrait_media_id points to the restored photo
```

Also keep the old test working: an archive whose media have no `caption`/`content` restores with empty fields (`contents=None`).

- [ ] **Step 2:** run → FAIL. **Step 3:** implement; scripts: create — for each `(archive_id, content)` in `media_contents(session)` write `{archive_id}.bin` and set `item["backup_file"]` on the matching manifest entry (entries without content get no file); restore — read `backup_file` when present into `contents[archive_id]`, error «Файл медиа из архива не найден.» if a listed file is missing; pass `contents` to `restore_archive`. Drop S3 imports. **Step 4:** full suite → PASS; `python -c "import ast,sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]" scripts/create-local-backup.py scripts/restore-local-backup.py`.

---

### Task 5: Web — client and biography section

**Files:**
- Modify: `apps/web/src/owner-api.ts`
- Create: `apps/web/src/pages/biography-section.ts`
- Test: `apps/web/test/biography-section.test.ts`

**Interfaces (produces):**

```ts
export type MediaItem = { id: string; original_filename: string; media_type: string; caption: string | null; date_label: string | null; file_url: string; preview_url: string | null }
export type OwnerMediaItem = MediaItem & { is_published: boolean; is_portrait: boolean }
export const fetchOwnerMedia = (personId: string) => request<OwnerMediaItem[]>(`/api/v1/admin/people/${personId}/media`)
export const uploadMedia = (personId: string, file: File) => { const body = new FormData(); body.append('file', file); return request<OwnerMediaItem>(`/api/v1/admin/people/${personId}/media`, { method: 'POST', body }) }
export const updateMedia = (mediaId: string, changes: Partial<Pick<OwnerMediaItem, 'caption' | 'date_label' | 'is_published'>>) => request<OwnerMediaItem>(`/api/v1/admin/media/${mediaId}`, json('PATCH', changes))
export const deleteMedia = (mediaId: string) => request<null>(`/api/v1/admin/media/${mediaId}`, { method: 'DELETE' })
export const setPortrait = (personId: string, mediaId: string | null) => request<{ portrait_media_id: string | null }>(`/api/v1/admin/people/${personId}/portrait`, json('PUT', { media_id: mediaId }))
export const saveBiography = (personId: string, biography: string) => request<{ biography: string | null }>(`/api/v1/admin/people/${personId}/biography`, json('PATCH', { biography }))
```

`EditablePerson` gains `biography: string | null`. `request()`: on 404 use the server `detail` when it is a string (so «Файл не найден.» reaches the owner), else «Человек не найден.».

`<cats-biography-section>`: properties `personId`, `biography: string | null | undefined` (undefined → loads via `fetchEditablePerson`), `isOwner: boolean`. Renders heading-less content (the page section keeps its h2): paragraphs split on `/\n\s*\n/` (`<p class="bio">`), or `<p class="empty">Биография пока не написана</p>`. Owner: button «Изменить» → `<textarea name="biography">`, counter `.counter` «N из 20000», «Сохранить», «Отмена», `[role="alert"]`. Save → `saveBiography`; success shows the new text and dispatches `person-changed` (bubbles, composed); failure shows the message and keeps the draft.

- [ ] **Step 1: Failing tests**: guest paragraphs (two `p.bio` for «А\n\nБ»); empty state; owner edit → PATCH body `{ biography: 'Новый' }`, `person-changed` fired, text shown; 422 keeps draft and shows «Биография не может быть длиннее 20000 символов.»; «Отмена» restores view without request; counter shows «5 из 20000» after typing «Новый»; undefined biography loads `/api/v1/admin/people/p1`.
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 6: Web — media section

**Files:**
- Create: `apps/web/src/pages/media-section.ts`
- Test: `apps/web/test/media-section.test.ts`

**Interfaces (produces):** `<cats-media-section>`: `personId`, `media: MediaItem[]` (guest list from the page), `isOwner`, `confirm: (text: string) => boolean` (default `window.confirm`). Owner mode loads `fetchOwnerMedia` and ignores `media`. DOM: `.tiles .tile` (`.tile.hidden` when unpublished, `.badge` «Портрет» / «скрыт»); image tile `a[href=file_url][target=_blank] img[src=preview_url]`; PDF tile `a` with `.doc-icon` and file name; `.caption`, `.date`. Owner controls: `input[type=file][multiple][accept="image/jpeg,image/png,application/pdf"]` behind button «Загрузить файлы»; `.uploads li` per file: «{name}: загружается…» → «{name}: готово» or «{name}: {reason}»; per tile buttons «Изменить подпись» (form with `input[name=caption]`, `input[name=date_label]`, «Сохранить», «Отмена»), «Сделать портретом» (images, not portrait, published) / «Убрать портрет» (portrait), «Скрыть»/«Показать», «Удалить» (confirm «Удалить файл «{name}»? Он исчезнет с сайта.»). Every successful change reloads the owner list and dispatches `person-changed`. Empty guest state «Фото и документы пока не добавлены».

- [ ] **Step 1: Failing tests:** guest tiles (image with preview link, PDF with icon, captions); owner upload of two files where the second answers 422 «Разрешены JPEG, PNG и PDF.» → both statuses shown, first «готово», list reloaded, `person-changed` once; «Сделать портретом» → PUT body `{ media_id: 'm1' }`; «Скрыть» → PATCH `{ is_published: false }`; «Удалить» cancelled → no request, confirmed → DELETE; caption form → PATCH `{ caption: 'Свадьба', date_label: '1950' }`; no «Сделать портретом» on a PDF or hidden photo.
- [ ] **Step 2:** FAIL. **Step 3:** implement (Lit, `static styles = css\`…\``; tiles grid `repeat(auto-fill,minmax(160px,1fr))`, two columns under 480px). **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 7: Web — person page, hidden person page, tree

**Files:**
- Modify: `apps/web/src/pages/person-card.ts`, `apps/web/src/app-shell.ts`
- Test: `apps/web/test/person-card.test.ts`, `apps/web/test/app-shell.test.ts`

- [ ] **Step 1: Failing tests:** person card hero shows `img.portrait[src="/api/v1/media/m1/preview"]` and no `.monogram` when `portrait` is set; the hero no longer contains the biography text; `#biography cats-biography-section` and `#media cats-media-section` get `personId`, `biography`/`media`, `isOwner`; hidden person page (app-shell) renders both sections with `personId` 'h1' and `isOwner` true. Update the existing test that expects a media link at `https://media.example.test/family-photo.jpg` to the new `MediaItem` shape (`file_url`).
- [ ] **Step 2:** FAIL. **Step 3:** implement: `PublicPerson.media: MediaItem[]`, `portrait?: { id: string; preview_url: string; file_url: string } | null`; hero `${person.portrait ? html`<img class="portrait" src=${person.portrait.preview_url} alt="Портрет: ${person.display_name}">` : monogram}`; remove `${person.biography ? … .bio …}` from the hero; sections render the two components; `person-changed` from them bubbles to the shell as today. app-shell hidden branch adds `<cats-biography-section .personId=${id} .isOwner=${true}>` (biography undefined → self-loads) and `<cats-media-section .personId=${id} .isOwner=${true}>`. **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 8: E2E, docs, final verification

- [ ] **Step 1: E2E** (append to `apps/web/e2e/owner-login.spec.ts`, skipped without the password, never saves): sign in to `/people/ca7750a8-ecfe-4cf4-a58c-9e9806656913`, click «Изменить» inside `cats-biography-section`, see the textarea, click «Отмена», textarea gone.
- [ ] **Step 2: README** — section «Биографии, фото и документы» after «Исправление связей»: what the owner can do, formats/limit, files stored in the database, backups put files next to the JSON; remove the claim that S3 stores media (line 9, line 132 and any S3 mention in the dev section that is no longer true).
- [ ] **Step 3: Migrate the dev DB and restart:** stop tab «Cat's House dev», `cd apps/api && CATS_HOUSE_… alembic upgrade head` the way earlier stages did (the dev script loads `.env`; run `scripts/dev-native.sh` which applies migrations if it does, otherwise run alembic with the env loaded from `.env` without printing secrets), restart with `CATS_HOUSE_WEB_PORT=5176 bash scripts/dev-native.sh`.
- [ ] **Step 4: Final verification:** `cd apps/api && .venv/bin/pytest -q`; `cd apps/web && npm test && npm run typecheck && npm run build && CATS_HOUSE_E2E_URL=http://127.0.0.1:5176 npm run test:e2e`.
- [ ] **Step 5:** independent whole-branch review; RED→GREEN fixes; report; ask before commit/merge/push.
