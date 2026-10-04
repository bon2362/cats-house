from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ImportRun, ParentChild, Person


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
