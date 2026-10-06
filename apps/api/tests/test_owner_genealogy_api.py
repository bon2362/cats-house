from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ChangeLog, Event, ImportRun, ParentChild, Person, Union


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


def create_related_person(session, import_run_id, name: str) -> Person:
    person = Person(import_run_id=import_run_id, display_name=name, source_uid=str(uuid4()))
    session.add(person)
    session.commit()
    return person


FORM = {
    "surname": "Иванова", "given_name": "Анна", "patronymic": None, "birth_surname": "Петрова", "sex": "F",
    "birth": {"date": {"qualifier": "about", "year": 1900, "month": None, "day": None, "end": None}, "place": "Тула", "date_text_keep": False},
    "death": {"status": "unknown", "date": None, "place": None, "date_text_keep": False},
}


def login(client):
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})


def test_guests_cannot_read_or_edit_people_for_the_owner(client, database_session):
    person = create_person(database_session)

    assert client.get("/api/v1/admin/people").status_code == 401
    assert client.get(f"/api/v1/admin/people/{person.id}").status_code == 401
    assert client.patch(f"/api/v1/admin/people/{person.id}", json=FORM).status_code == 401
    assert client.post(f"/api/v1/admin/people/{person.id}/restore").status_code == 401


def test_owner_saves_the_form_and_the_change_is_logged(client, database_session):
    person = create_person(database_session)
    login(client)

    response = client.patch(f"/api/v1/admin/people/{person.id}", json=FORM)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Анна Иванова"
    assert body["birth"] == {"date": {"qualifier": "about", "year": 1900, "month": None, "day": None, "end": None}, "date_text": "ABT 1900", "place": "Тула"}
    assert body["death"]["status"] == "unknown"
    assert client.get(f"/api/v1/admin/people/{person.id}").json() == body
    entry = database_session.query(ChangeLog).filter_by(entity_id=person.id).one()
    assert entry.after["display_name"] == "Анна Иванова"


def test_owner_gets_russian_validation_errors(client, database_session):
    person = create_person(database_session)
    login(client)

    no_name = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "surname": None, "given_name": " "})
    bad_day = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "birth": {"date": {"qualifier": "exact", "year": 1901, "month": 2, "day": 30, "end": None}, "place": None, "date_text_keep": False}})
    bad_type = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "sex": "X"})

    assert (no_name.status_code, no_name.json()) == (422, {"detail": "Укажите имя или фамилию."})
    assert (bad_day.status_code, bad_day.json()) == (422, {"detail": "В этом месяце нет такого дня."})
    assert bad_type.status_code == 422


def test_owner_saves_three_maximum_length_name_parts(client, database_session):
    person = create_person(database_session)
    login(client)
    surname, given_name, patronymic = "К" * 255, "П" * 255, "Н" * 255

    response = client.patch(
        f"/api/v1/admin/people/{person.id}",
        json={**FORM, "surname": surname, "given_name": given_name, "patronymic": patronymic},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == f"{given_name} {patronymic} {surname}"
    database_session.expire_all()
    assert database_session.get(Person, person.id).display_name == f"{given_name} {patronymic} {surname}"
    assert database_session.query(ChangeLog).filter_by(entity_id=person.id).count() == 1


def test_owner_finds_hidden_people_and_restores_them(client, database_session):
    person = create_person(database_session)
    login(client)
    client.post(f"/api/v1/admin/people/{person.id}/archive")

    assert client.get("/api/v1/people?query=Анна").json() == []
    assert client.get("/api/v1/admin/people?query=анна").json() == [{"id": str(person.id), "display_name": "Анна", "years": None, "is_archived": True}]

    assert client.post(f"/api/v1/admin/people/{person.id}/restore").status_code == 204
    assert client.get(f"/api/v1/admin/people/{person.id}").json()["is_archived"] is False


def test_unknown_person_is_404_for_the_owner(client, database_session):
    from uuid import uuid4

    login(client)
    assert client.get(f"/api/v1/admin/people/{uuid4()}").status_code == 404
    assert client.patch(f"/api/v1/admin/people/{uuid4()}", json=FORM).status_code == 404


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


def test_owner_creates_family_links_and_changes_are_logged(client, database_session):
    parent = create_person(database_session)
    partner = create_related_person(database_session, parent.import_run_id, "Пётр")
    child = create_related_person(database_session, parent.import_run_id, "Мария")
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    union_response = client.post(
        "/api/v1/admin/unions",
        json={"partner_one_id": str(parent.id), "partner_two_id": str(partner.id), "union_type": "marriage"},
    )
    parent_response = client.post(
        "/api/v1/admin/parent-links",
        json={"parent_id": str(parent.id), "child_id": str(child.id), "relationship_type": "biological"},
    )

    assert union_response.status_code == 201
    assert parent_response.status_code == 201
    assert database_session.query(Union).count() == 1
    assert database_session.query(ParentChild).count() == 1
    assert database_session.query(ChangeLog).filter(ChangeLog.entity_type.in_(["union", "parent_child"])).count() == 2
