import io
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.media.library import MediaError, delete_media, make_preview, owner_media, set_biography, set_portrait, sniff, update_media, upload
from app.models.genealogy import Base, ChangeLog, Media, MediaLink, Person

OWNER = "owner@example.test"


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def image_bytes(kind="JPEG", size=(1200, 800), mode="RGB", exif_rotate=False):
    buffer = io.BytesIO()
    picture = Image.new(mode, size, "red")
    if exif_rotate:
        exif = Image.Exif()
        exif[0x0112] = 6  # display rotated by 90°
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
        upload(session, uuid4(), "doc.pdf", b"%PDF-1.4", OWNER)


@pytest.fixture
def anna(session):
    person, other = Person(display_name="Анна"), Person(display_name="Пётр")
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
    assert set_portrait(session, anna["person"].id, None, OWNER) == {"portrait_media_id": None}


def test_deleting_the_portrait_clears_it_and_hides_the_file_from_lists(session, anna):
    set_portrait(session, anna["person"].id, anna["photo"], OWNER)

    delete_media(session, anna["photo"], OWNER)

    assert session.get(Person, anna["person"].id).portrait_media_id is None
    assert session.get(Media, anna["photo"]).is_deleted is True
    assert [item["id"] for item in owner_media(session, anna["person"].id)] == [anna["document"]]
    with pytest.raises(LookupError, match="Файл не найден"):
        delete_media(session, anna["photo"], OWNER)
    with pytest.raises(LookupError, match="Файл не найден"):
        update_media(session, anna["photo"], {"caption": "x"}, OWNER)


def test_owner_list_marks_hidden_and_portrait_in_upload_order(session, anna):
    set_portrait(session, anna["person"].id, anna["photo"], OWNER)
    update_media(session, anna["document"], {"is_published": False}, OWNER)

    items = owner_media(session, anna["person"].id)

    assert [(item["id"], item["is_published"], item["is_portrait"]) for item in items] == [(anna["photo"], True, True), (anna["document"], False, False)]


def test_media_changes_are_logged(session, anna):
    update_media(session, anna["photo"], {"caption": "Свадьба", "is_published": False}, OWNER)
    delete_media(session, anna["document"], OWNER)

    changes = [(entry.before, entry.after) for entry in session.query(ChangeLog).filter_by(entity_type="media").order_by(ChangeLog.created_at) if entry.before]
    assert ({"caption": None, "is_published": True}, {"caption": "Свадьба", "is_published": False}) in changes
    assert ({"is_deleted": False}, {"is_deleted": True}) in changes


def test_biography_is_normalised_limited_and_logged(session, anna):
    assert set_biography(session, anna["person"].id, "  Первый абзац.\r\n\r\nВторой.  ", OWNER) == {"biography": "Первый абзац.\n\nВторой."}
    assert set_biography(session, anna["person"].id, "   ", OWNER) == {"biography": None}
    with pytest.raises(MediaError, match="20000"):
        set_biography(session, anna["person"].id, "я" * 20001, OWNER)
    logged = [entry.after for entry in session.query(ChangeLog).filter_by(entity_type="person").order_by(ChangeLog.created_at)]
    assert logged == [{"biography": "Первый абзац.\n\nВторой."}, {"biography": None}]


def test_the_owner_form_carries_the_biography(session, anna):
    from app.genealogy.person_editing import editable_person

    set_biography(session, anna["person"].id, "Текст", OWNER)

    assert editable_person(session, anna["person"].id)["biography"] == "Текст"


def huge_png():
    buffer = io.BytesIO()
    Image.new("1", (15000, 12000)).save(buffer, "PNG")  # 180 megapixels in a tiny file
    return buffer.getvalue()


def test_a_huge_photo_is_refused_with_a_reason(session):
    person = Person(display_name="Анна")
    session.add(person)
    session.commit()

    with pytest.raises(MediaError, match="мегапикселей"):
        upload(session, person.id, "huge.png", huge_png(), OWNER)


def test_a_preview_read_does_not_load_the_whole_file(session, anna):
    from sqlalchemy import event

    from app.media.library import media_file

    statements = []
    engine = session.get_bind()
    listener = lambda conn, cursor, statement, *args: statements.append(statement)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    session.expunge_all()
    try:
        assert media_file(session, anna["photo"], "preview", owner=True)[1] == "image/jpeg"
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    selected = " ".join(statements)
    assert "media.preview" in selected and "media.content" not in selected
