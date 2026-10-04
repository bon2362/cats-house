from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import Base, ChangeLog, ImportRun, Person


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


def test_person_can_be_archived_without_being_deleted(session):
    run = ImportRun(
        original_filename="family.ged",
        sha256="0" * 64,
        state="applied",
        normalized_payload={},
        counts={},
    )
    session.add(run)
    session.flush()
    person = Person(import_run_id=run.id, display_name="Анна Иванова", is_archived=True)
    session.add(person)
    session.flush()

    assert session.get(Person, person.id).is_archived is True


def test_change_log_records_before_and_after_values(session):
    entry = ChangeLog(
        entity_type="person",
        entity_id=uuid4(),
        owner_email="owner@example.test",
        before={"display_name": "Анна"},
        after={"display_name": "Анна Иванова"},
    )

    session.add(entry)
    session.flush()

    assert session.get(ChangeLog, entry.id).before == {"display_name": "Анна"}
    assert session.get(ChangeLog, entry.id).after == {"display_name": "Анна Иванова"}
