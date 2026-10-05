from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import Event, ImportRun, Media, MediaLink, ParentChild, Person, Union


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


def test_public_people_returns_the_catalog_when_query_is_empty(client, database_session):
    later = add_person(database_session, "Яна Архипова")
    first = add_person(database_session, "Анна Архипова")
    add_person(database_session, "Скрытая Архипова", archived=True)

    response = client.get("/api/v1/people")

    assert response.status_code == 200
    assert response.json() == [
        {"id": str(first.id), "display_name": "Анна Архипова"},
        {"id": str(later.id), "display_name": "Яна Архипова"},
    ]


def test_public_search_treats_yo_and_e_as_equivalent(client, database_session):
    person = add_person(database_session, "Фёдор Архипов")

    response = client.get("/api/v1/people?query=Федор")

    assert response.status_code == 200
    assert response.json() == [{"id": str(person.id), "display_name": "Фёдор Архипов"}]


def test_public_catalogue_exposes_normalized_person_context(client, database_session):
    person = add_person(database_session, "Евдокия ??? ???")
    parent = Person(import_run_id=person.import_run_id, display_name="Пётр ???", source_uid=str(uuid4()))
    database_session.add(parent)
    database_session.flush()
    database_session.add_all(
        [
            ParentChild(parent_id=parent.id, child_id=person.id, relationship_type="biological"),
            Event(person_id=person.id, event_type="BIRT", date_text="ABT 1901"),
            Event(person_id=person.id, event_type="DEAT", date_text="19 FEB 1951"),
        ]
    )
    database_session.commit()

    response = client.get("/api/v1/people?query=Евдокия")

    assert response.status_code == 200
    assert response.json() == [{
        "id": str(person.id),
        "display_name": "Евдокия",
        "birth_label": "ок. 1901",
        "death_label": "19 февраля 1951",
        "years": "1901 – 1951",
        "is_living": False,
        "parents_label": "Пётр",
    }]


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


def test_featured_person_returns_the_first_active_person_without_login(client, database_session):
    hidden = add_person(database_session, "Алексей Скрытый", archived=True)
    visible = add_person(database_session, "Борис Видимый")
    add_person(database_session, "Владимир Поздний")
    add_person(database_session, "")
    add_person(database_session, "??? ??? ???")

    response = client.get("/api/v1/people/featured")

    assert response.status_code == 200
    assert response.json() == {"id": str(visible.id), "display_name": "Борис Видимый"}
    assert response.json()["id"] != str(hidden.id)


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


def test_public_card_includes_only_published_attached_media(client, database_session):
    person = add_person(database_session, "Анна")
    published = Media(storage_key="media/published.jpg", media_type="image/jpeg", original_filename="published.jpg", is_published=True)
    private = Media(storage_key="media/private.jpg", media_type="image/jpeg", original_filename="private.jpg", is_published=False)
    database_session.add_all([published, private])
    database_session.flush()
    database_session.add_all([MediaLink(media_id=published.id, person_id=person.id), MediaLink(media_id=private.id, person_id=person.id)])
    database_session.commit()

    class FakeStorage:
        def public_url(self, key: str) -> str:
            return f"https://media.example.test/{key}"

    client.app.state.media_storage = FakeStorage()
    response = client.get(f"/api/v1/people/{person.id}")

    assert response.status_code == 200
    assert response.json()["media"] == [
        {"id": str(published.id), "original_filename": "published.jpg", "url": "https://media.example.test/media/published.jpg"}
    ]
