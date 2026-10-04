from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ImportRun, ParentChild, Person, Union


@pytest.fixture
def database_session(client, settings):
    with Session(create_engine(settings.database_url)) as session:
        yield session


def add_person(session, name: str, archived: bool = False) -> Person:
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    person = Person(import_run_id=run.id, display_name=name, source_uid=str(uuid4()), is_archived=archived)
    session.add(person)
    session.commit()
    return person


def test_public_search_finds_cyrillic_name_without_login(client, database_session):
    person = add_person(database_session, "Анна Иванова")

    response = client.get("/api/v1/people?query=Иван")

    assert response.status_code == 200
    assert response.json() == [{"id": str(person.id), "display_name": "Анна Иванова"}]


def test_public_card_returns_person_without_login(client, database_session):
    person = add_person(database_session, "Анна Иванова")

    response = client.get(f"/api/v1/people/{person.id}")

    assert response.status_code == 200
    assert response.json()["display_name"] == "Анна Иванова"
    assert response.json()["events"] == []


def test_public_search_excludes_archived_person(client, database_session):
    add_person(database_session, "Скрытая Иванова", archived=True)

    response = client.get("/api/v1/people?query=Иван")

    assert response.status_code == 200
    assert response.json() == []


def test_public_card_includes_active_family_relationships(client, database_session):
    person = add_person(database_session, "Анна")
    parent = Person(import_run_id=person.import_run_id, display_name="Иван", source_uid=str(uuid4()))
    partner = Person(import_run_id=person.import_run_id, display_name="Пётр", source_uid=str(uuid4()))
    child = Person(import_run_id=person.import_run_id, display_name="Мария", source_uid=str(uuid4()))
    hidden = Person(import_run_id=person.import_run_id, display_name="Скрытый", source_uid=str(uuid4()), is_archived=True)
    database_session.add_all([parent, partner, child, hidden])
    database_session.flush()
    database_session.add_all(
        [
            ParentChild(parent_id=parent.id, child_id=person.id, relationship_type="biological"),
            ParentChild(parent_id=person.id, child_id=child.id, relationship_type="biological"),
            ParentChild(parent_id=hidden.id, child_id=person.id, relationship_type="biological"),
            Union(import_run_id=person.import_run_id, partner_one_id=person.id, partner_two_id=partner.id, union_type="marriage"),
        ]
    )
    database_session.commit()

    response = client.get(f"/api/v1/people/{person.id}")

    assert response.status_code == 200
    assert response.json()["parents"] == [{"id": str(parent.id), "display_name": "Иван"}]
    assert response.json()["children"] == [{"id": str(child.id), "display_name": "Мария"}]
    assert response.json()["partners"] == [{"id": str(partner.id), "display_name": "Пётр"}]
