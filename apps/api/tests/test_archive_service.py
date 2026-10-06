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
