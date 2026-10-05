from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ImportRun, ParentChild, Person, Union


@pytest.fixture
def database_session(client, settings):
    with Session(create_engine(settings.database_url)) as session:
        yield session


def create_person(session, run, name):
    person = Person(import_run_id=run.id, display_name=name, source_uid=str(uuid4()))
    session.add(person)
    session.flush()
    return person


def test_descendant_tree_respects_depth(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    root = create_person(database_session, run, "Анна")
    child = create_person(database_session, run, "Борис")
    grandchild = create_person(database_session, run, "Вера")
    database_session.add_all((ParentChild(parent_id=root.id, child_id=child.id), ParentChild(parent_id=child.id, child_id=grandchild.id)))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=descendants&depth=1")

    assert response.status_code == 200
    assert {person["display_name"] for person in response.json()["people"]} == {"Анна", "Борис"}
    assert response.json()["links"] == [{"parent_id": str(root.id), "child_id": str(child.id)}]


def test_descendant_tree_returns_union_and_typed_parent_link(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="2" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    root = create_person(database_session, run, "Анна")
    partner = create_person(database_session, run, "Пётр")
    child = create_person(database_session, run, "Мария")
    union = Union(import_run_id=run.id, partner_one_id=root.id, partner_two_id=partner.id, union_type="marriage")
    database_session.add_all((union, ParentChild(parent_id=root.id, child_id=child.id, relationship_type="biological")))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=descendants&depth=1")

    assert response.status_code == 200
    assert response.json()["unions"] == [
        {
            "id": str(union.id),
            "partner_one_id": str(root.id),
            "partner_two_id": str(partner.id),
            "union_type": "marriage",
        }
    ]
    assert response.json()["parent_links"] == [
        {"parent_id": str(root.id), "child_id": str(child.id), "relationship_type": "biological"}
    ]


def test_ancestor_and_mixed_tree_include_parents(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="1" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    root = create_person(database_session, run, "Борис")
    child = create_person(database_session, run, "Вера")
    database_session.add_all((ParentChild(parent_id=parent.id, child_id=root.id), ParentChild(parent_id=root.id, child_id=child.id)))
    database_session.commit()

    ancestors = client.get(f"/api/v1/tree/{root.id}?mode=ancestors&depth=1")
    mixed = client.get(f"/api/v1/tree/{root.id}?mode=mixed&depth=1")

    assert {person["display_name"] for person in ancestors.json()["people"]} == {"Анна", "Борис"}
    assert {person["display_name"] for person in mixed.json()["people"]} == {"Анна", "Борис", "Вера"}
    assert {(link["parent_id"], link["child_id"]) for link in mixed.json()["links"]} == {
        (str(parent.id), str(root.id)),
        (str(root.id), str(child.id)),
    }
