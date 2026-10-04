from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ImportRun, Person


@pytest.fixture
def database_session(client, settings):
    with Session(create_engine(settings.database_url)) as session:
        yield session


def test_owner_downloads_gedcom_without_archived_people(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    database_session.add_all((
        Person(import_run_id=run.id, display_name="Анна Иванова", source_uid=str(uuid4())),
        Person(import_run_id=run.id, display_name="", source_uid=str(uuid4())),
        Person(import_run_id=run.id, display_name="Скрытая Иванова", source_uid=str(uuid4()), is_archived=True),
    ))
    database_session.commit()
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    response = client.get("/api/v1/admin/exports/gedcom")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-gedcom")
    assert "Анна /Иванова/" in response.text
    assert "Скрытая" not in response.text
    assert "0 @I1@ INDI" in response.text
