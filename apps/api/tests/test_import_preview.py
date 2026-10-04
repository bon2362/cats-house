import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.imports.service import create_preview, get_import_run
from app.models.genealogy import Base, Person


def fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parent / "fixtures" / name).read_bytes()


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


def test_create_preview_persists_counts_sha256_and_issues(session):
    content = fixture_bytes("cyrillic-family.ged")

    run = create_preview(session, "family.ged", content)

    assert run.state == "previewed"
    assert run.counts["people"] == 1
    assert run.sha256 == hashlib.sha256(content).hexdigest()
    assert session.query(Person).count() == 0
    assert get_import_run(session, run.id).id == run.id


def test_preview_with_parse_errors_is_recorded_but_not_applyable(session):
    run = create_preview(session, "broken.ged", fixture_bytes("invalid-reference.ged"))

    assert run.has_errors is True
    assert session.query(Person).count() == 0
