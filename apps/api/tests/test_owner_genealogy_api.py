from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ChangeLog, Event, ImportRun, Person


@pytest.fixture
def database_session(client, settings):
    with Session(create_engine(settings.database_url)) as session:
        yield session


def create_person(session) -> Person:
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    person = Person(import_run_id=run.id, display_name="Анна", source_uid=str(uuid4()))
    session.add(person)
    session.commit()
    return person


def test_anonymous_client_cannot_edit_person(client, database_session):
    person = create_person(database_session)

    response = client.patch(f"/api/v1/admin/people/{person.id}", json={"display_name": "Анна Иванова"})

    assert response.status_code == 401


def test_owner_can_edit_person_and_change_is_logged(client, database_session):
    person = create_person(database_session)
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    response = client.patch(f"/api/v1/admin/people/{person.id}", json={"display_name": "Анна Иванова"})

    assert response.status_code == 200
    assert response.json()["display_name"] == "Анна Иванова"
    entry = database_session.query(ChangeLog).one()
    assert entry.before == {"display_name": "Анна"}
    assert entry.after == {"display_name": "Анна Иванова"}


def test_owner_archives_person_without_deleting_it(client, database_session):
    person = create_person(database_session)
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    response = client.post(f"/api/v1/admin/people/{person.id}/archive")

    assert response.status_code == 204
    database_session.expire_all()
    assert database_session.get(Person, person.id).is_archived is True
    assert client.get("/api/v1/people?query=Анна").json() == []


def test_owner_creates_person_event_and_change_is_logged(client, database_session):
    person = create_person(database_session)
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    response = client.post(f"/api/v1/admin/people/{person.id}/events", json={"event_type": "BIRT", "date_text": "1900"})

    assert response.status_code == 201
    assert database_session.query(Event).filter_by(person_id=person.id, event_type="BIRT").count() == 1
    assert database_session.query(ChangeLog).filter_by(entity_type="event").count() == 1
