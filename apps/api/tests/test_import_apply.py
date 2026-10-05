from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.imports.service import apply_preview, create_preview, get_import_run
from app.models.genealogy import Base, Event, ImportIssue, ParentChild, Person, Union


def fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parent / "fixtures" / name).read_bytes()


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


def test_apply_preview_creates_people_unions_links_and_events(session):
    run = create_preview(session, "complex.ged", fixture_bytes("complex-family.ged"))

    applied = apply_preview(session, run.id)

    assert applied.state == "applied"
    assert session.query(Person).count() == 5
    assert session.query(Union).count() == 2
    assert session.query(ParentChild).count() == 4
    assert session.query(ParentChild).filter(ParentChild.union_id.is_not(None)).count() == 4
    assert session.query(Event).count() == 0


def test_apply_preview_with_errors_creates_no_genealogy_rows(session):
    run = create_preview(session, "broken.ged", fixture_bytes("invalid-reference.ged"))

    with pytest.raises(ValueError, match="ошибк"):
        apply_preview(session, run.id)

    assert session.query(Person).count() == 0
    assert get_import_run(session, run.id).state == "failed"
    assert session.query(ImportIssue).filter_by(import_run_id=run.id, severity="error").count() >= 1


def test_applied_preview_cannot_be_applied_twice(session):
    run = create_preview(session, "complex.ged", fixture_bytes("complex-family.ged"))
    apply_preview(session, run.id)

    with pytest.raises(ValueError, match="уже"):
        apply_preview(session, run.id)
