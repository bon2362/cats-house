import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.imports.name_backfill import backfill_name_parts
from app.models.genealogy import Base, ImportRun, Person


def create_at5(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE ValuesStr (f_id INTEGER, f_db_id INTEGER, rec_id INTEGER, rec_db_id INTEGER, rec_table INTEGER, lang_id INTEGER, vstr TEXT);
        INSERT INTO ValuesStr VALUES
          (64, -1, 1, 0, 13, 0, 'Кошкин'), (66, -1, 1, 0, 13, 0, 'Петр'), (67, -1, 1, 0, 13, 0, 'Николаевич'),
          (66, -1, 2, 0, 13, 0, 'Вера'),
          (64, -1, 3, 0, 13, 0, 'Другой'),
          (50, -1, 1, 0, 9, 0, 'КОШКИН');
        """
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def people(session):
    run = ImportRun(original_filename="archive.json", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    rows = {
        "petr": Person(import_run_id=run.id, display_name="Петр Николаевич Кошкин", source_uid="ABCD_1"),
        "vera": Person(import_run_id=run.id, display_name="Вера Иванова", source_uid="ABCD_2"),
        "edited": Person(import_run_id=run.id, display_name="Уже Исправлен", source_uid="ABCD_3", surname="Исправлен"),
        "absent": Person(import_run_id=run.id, display_name="Без Записи", source_uid="ABCD_9"),
        "new": Person(import_run_id=run.id, display_name="Добавлен На Сайте", source_uid=None),
    }
    session.add_all(rows.values())
    session.commit()
    return rows


def test_fills_only_people_without_name_parts_and_keeps_display_names(session, people, tmp_path):
    report = backfill_name_parts(session, create_at5(tmp_path / "tree.at5"), apply=True)

    session.expire_all()
    petr, vera, edited = people["petr"], people["vera"], people["edited"]
    assert (petr.surname, petr.given_name, petr.patronymic, petr.display_name) == ("Кошкин", "Петр", "Николаевич", "Петр Николаевич Кошкин")
    assert (vera.surname, vera.given_name, vera.patronymic, vera.display_name) == (None, "Вера", None, "Вера Иванова")
    assert (edited.surname, edited.given_name) == ("Исправлен", None)
    assert (report.filled, report.already_filled, report.without_at5_names, report.without_source, report.display_name_differs) == (2, 1, 1, 1, 1)
    assert session.query(ImportRun).filter_by(original_filename="tree.at5").one().state == "applied"


def test_dry_run_writes_nothing(session, people, tmp_path):
    report = backfill_name_parts(session, create_at5(tmp_path / "tree.at5"), apply=False)

    session.expire_all()
    assert report.applied is False and report.filled == 2
    assert people["petr"].surname is None
    assert session.query(ImportRun).filter_by(original_filename="tree.at5").count() == 0
