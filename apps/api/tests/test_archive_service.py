from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.exports.service import build_archive, restore_archive
from app.models.genealogy import Base, Event, ImportRun, Media, Person


def test_archive_restores_people_events_and_media_manifest(postgres_url):
    source_engine = create_engine(postgres_url)
    Base.metadata.create_all(source_engine)
    with Session(source_engine) as source:
        run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
        source.add(run)
        source.flush()
        person = Person(import_run_id=run.id, display_name="Анна Иванова", source_uid=str(uuid4()))
        source.add(person)
        source.flush()
        source.add(Event(person_id=person.id, event_type="BIRT", date_text="1900"))
        source.add(Media(storage_key="media/photo.jpg", media_type="image/jpeg", original_filename="photo.jpg", is_published=True))
        source.commit()
        archive = build_archive(source)

    target_engine = create_engine(postgres_url)
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)
    with Session(target_engine) as target:
        restore_archive(target, archive)
        assert target.query(Person).count() == 1
        assert target.query(Event).count() == 1
        assert target.query(Media).count() == 1
        assert archive["counts"] == {"people": 1, "events": 1, "media": 1}
