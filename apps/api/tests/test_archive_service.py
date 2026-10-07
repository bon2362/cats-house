from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.exports.service import build_archive, restore_archive
from app.models.genealogy import Base, Event, ImportRun, Media, MediaLink, ParentChild, Person, Union


def test_archive_restores_complete_genealogy_and_media_manifest(postgres_url):
    source_engine = create_engine(postgres_url)
    Base.metadata.create_all(source_engine)
    with Session(source_engine) as source:
        run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
        source.add(run)
        source.flush()
        person = Person(import_run_id=run.id, display_name="Анна Иванова", source_uid=str(uuid4()), biography="Заметка")
        partner = Person(import_run_id=run.id, display_name="Пётр Иванов", source_uid=str(uuid4()))
        child = Person(import_run_id=run.id, display_name="Мария Иванова", source_uid=str(uuid4()))
        source.add_all([person, partner, child])
        source.flush()
        event = Event(person_id=person.id, event_type="BIRT", date_text="1900", place="Москва", description="Запись")
        media = Media(storage_key="media/photo.jpg", media_type="image/jpeg", original_filename="photo.jpg", is_published=True)
        source.add_all([
            event,
            media,
            Union(import_run_id=run.id, partner_one_id=person.id, partner_two_id=partner.id, union_type="marriage"),
            ParentChild(parent_id=person.id, child_id=child.id, relationship_type="biological"),
        ])
        source.flush()
        source.add(MediaLink(media_id=media.id, event_id=event.id))
        source.commit()
        archive = build_archive(source)

    target_engine = create_engine(postgres_url)
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)
    with Session(target_engine) as target:
        restore_archive(target, archive)
        assert target.query(Person).count() == 3
        assert target.query(Event).count() == 1
        assert target.query(Media).count() == 1
        assert target.query(Union).count() == 1
        assert target.query(ParentChild).count() == 1
        assert target.query(MediaLink).count() == 1
        restored_event = target.query(Event).one()
        assert (restored_event.place, restored_event.description) == ("Москва", "Запись")
        assert archive["counts"] == {"people": 3, "events": 1, "unions": 1, "parent_children": 1, "media": 1, "media_links": 1}


def test_archive_keeps_name_parts_and_people_created_on_the_site(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as source:
        person = Person(import_run_id=None, source_uid=None, display_name="Анна Петровна Иванова", surname="Иванова", given_name="Анна", patronymic="Петровна", birth_surname="Сидорова")
        partner = Person(import_run_id=None, source_uid=None, display_name="Пётр Иванов", given_name="Пётр", surname="Иванов")
        source.add_all([person, partner])
        source.flush()
        source.add(Union(import_run_id=None, partner_one_id=person.id, partner_two_id=partner.id, union_type="marriage"))
        source.commit()
        archive = build_archive(source)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        restore_archive(target, archive)
        restored = target.query(Person).filter_by(display_name="Анна Петровна Иванова").one()
        assert (restored.surname, restored.given_name, restored.patronymic, restored.birth_surname) == ("Иванова", "Анна", "Петровна", "Сидорова")
        assert target.query(Union).count() == 1


def test_archive_round_trip_keeps_files_captions_and_portrait(postgres_url):
    import io

    from PIL import Image

    from app.exports.service import media_contents
    from app.media.library import set_portrait, update_media, upload

    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), "green").save(buffer, "JPEG")
    photo_bytes = buffer.getvalue()
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as source:
        person = Person(display_name="Анна")
        source.add(person)
        source.commit()
        photo = upload(source, person.id, "anna.jpg", photo_bytes, "owner@example.test")["id"]
        document = upload(source, person.id, "doc.pdf", b"%PDF-1.4 doc", "owner@example.test")["id"]
        update_media(source, photo, {"caption": "Свадьба", "date_label": "1950"}, "owner@example.test")
        update_media(source, document, {"is_published": False}, "owner@example.test")
        set_portrait(source, person.id, photo, "owner@example.test")
        archive = build_archive(source)
        contents = dict(media_contents(source))
    engine.dispose()

    target_engine = create_engine(postgres_url)
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)
    with Session(target_engine) as target:
        restore_archive(target, archive, contents)
        restored = {item.original_filename: item for item in target.query(Media)}
        assert restored["anna.jpg"].content == photo_bytes and restored["anna.jpg"].preview
        assert (restored["anna.jpg"].caption, restored["anna.jpg"].date_label) == ("Свадьба", "1950")
        assert restored["doc.pdf"].content == b"%PDF-1.4 doc" and restored["doc.pdf"].is_published is False
        assert target.query(Person).one().portrait_media_id == restored["anna.jpg"].id
    target_engine.dispose()


def test_restore_keeps_a_file_whose_preview_cannot_be_made(postgres_url):
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("1", (15000, 12000)).save(buffer, "PNG")
    archive = {
        "format": "cats-house-archive-v1", "people": [], "events": [], "counts": {},
        "media_manifest": [{"archive_id": "m1", "storage_key": None, "media_type": "image/png", "original_filename": "huge.png", "is_published": True}],
    }
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        restore_archive(target, archive, {"m1": buffer.getvalue()})
        restored = target.query(Media).one()
        assert restored.content == buffer.getvalue() and restored.preview is None
    engine.dispose()
