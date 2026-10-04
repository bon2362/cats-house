import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.genealogy import Base, ImportRun, Person


def test_person_source_uid_is_unique_within_an_import(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        run = ImportRun(
            original_filename="family.ged",
            sha256="a" * 64,
            normalized_payload={},
            counts={},
            state="previewed",
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                Person(import_run_id=run.id, display_name="Анна", source_uid="UID-1"),
                Person(import_run_id=run.id, display_name="Анна", source_uid="UID-1"),
            ]
        )

        with pytest.raises(IntegrityError):
            session.flush()
