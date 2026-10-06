import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.gedcom.at5 import At5ImportError, at5_date
from app.imports.at5_sync import sync_events_from_at5
from app.models.genealogy import Base, ChangeLog, Event, ImportRun, Person, Union


# Synthetic family. AT5 person ids: 1 father, 2 mother, 3 child, 4 second wife,
# 5 child of the second marriage, 9 a person removed from the site.
AT5_SCHEMA = """
CREATE TABLE Persons (id INTEGER, db_id INTEGER, sex INTEGER);
CREATE TABLE EventTypes (id INTEGER, db_id INTEGER, gedname TEXT);
CREATE TABLE EventRoles (id INTEGER, db_id INTEGER, et_id INTEGER, et_db_id INTEGER, ismain BOOLEAN);
CREATE TABLE Events (id INTEGER, db_id INTEGER, et_id INTEGER, et_db_id INTEGER, isfav BOOLEAN, alive BOOLEAN);
CREATE TABLE EventDetails (id INTEGER, db_id INTEGER, p_id INTEGER, p_db_id INTEGER, e_id INTEGER, e_db_id INTEGER, er_id INTEGER, er_db_id INTEGER, e_ord INTEGER, p_ord INTEGER);
CREATE TABLE ValuesDates (f_id INTEGER, f_db_id INTEGER, rec_id INTEGER, rec_db_id INTEGER, rec_table INTEGER, d INTEGER, m INTEGER, y INTEGER, d2 INTEGER, m2 INTEGER, y2 INTEGER, isjulian BOOLEAN, isdateBC BOOLEAN, isdate2BC BOOLEAN, type INTEGER);
INSERT INTO Persons VALUES (1, 0, 1), (2, 0, 2), (3, 0, 1), (4, 0, 2), (5, 0, 2), (9, 0, 1);
INSERT INTO EventTypes VALUES (1, -1, 'BIRT'), (2, -1, 'DEAT'), (3, -1, 'MARR');
INSERT INTO EventRoles VALUES (1, -1, 1, -1, 1), (2, -1, 1, -1, 0), (4, -1, 2, -1, 1), (5, -1, 3, -1, 1);
INSERT INTO Events VALUES
  (10, 0, 1, -1, 0, 0),  -- birth of the child, parents as witnesses
  (11, 0, 2, -1, 0, 0),  -- death of the father, year only
  (12, 0, 3, -1, 0, 0),  -- first marriage
  (13, 0, 3, -1, 0, 0),  -- second marriage, no union on the site
  (14, 0, 1, -1, 0, 0),  -- birth of the removed person
  (15, 0, 1, -1, 0, 0),  -- birth with parents only, child unknown
  (16, 0, 2, -1, 0, 0);  -- death of the mother, month and year
INSERT INTO EventDetails VALUES
  (1, 0, 3, 0, 10, 0, 1, -1, 0, 0), (2, 0, 1, 0, 10, 0, 2, -1, 0, 1), (3, 0, 2, 0, 10, 0, 2, -1, 0, 2),
  (4, 0, 1, 0, 11, 0, 4, -1, 0, 0),
  (5, 0, 1, 0, 12, 0, 5, -1, 0, 0), (6, 0, 2, 0, 12, 0, 5, -1, 0, 1),
  (7, 0, 1, 0, 13, 0, 5, -1, 0, 0), (8, 0, 4, 0, 13, 0, 5, -1, 0, 1),
  (9, 0, 9, 0, 14, 0, 1, -1, 0, 0),
  (10, 0, 1, 0, 15, 0, 2, -1, 0, 0),
  (11, 0, 2, 0, 16, 0, 4, -1, 0, 0);
INSERT INTO ValuesDates VALUES
  (29, -1, 10, 0, 7, 6, 4, 1926, NULL, NULL, NULL, 0, NULL, NULL, 0),
  (29, -1, 11, 0, 7, NULL, NULL, 1944, NULL, NULL, NULL, 0, NULL, NULL, 0),
  (29, -1, 16, 0, 7, NULL, 3, 2004, NULL, NULL, NULL, 0, NULL, NULL, 0);
"""


def create_at5(path: Path, extra: str = "") -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(AT5_SCHEMA + extra)
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    # The container is shared by all test modules; start from empty tables.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def family(session):
    run = ImportRun(original_filename="archive.json", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    people = {at5_id: Person(import_run_id=run.id, display_name=f"Person {at5_id}", source_uid=f"ABCD1234_{at5_id}") for at5_id in (1, 2, 3, 4, 5)}
    session.add_all(people.values())
    session.flush()
    union = Union(import_run_id=run.id, partner_one_id=people[1].id, partner_two_id=people[2].id)
    session.add(union)
    session.flush()
    # The state left by the old import: a birth hanging on a parent, an undated death, a per-person marriage.
    session.add_all([
        Event(person_id=people[1].id, event_type="BIRT"),
        Event(person_id=people[1].id, event_type="DEAT"),
        Event(person_id=people[1].id, event_type="MARR"),
    ])
    session.commit()
    return {"people": people, "union": union, "ids": {at5_id: person.id for at5_id, person in people.items()}}


def events_by_owner(session, family):
    """Events as (type, AT5 owner id, union marker, date), sorted for comparison."""
    by_id = {person_id: at5_id for at5_id, person_id in family["ids"].items()}
    rows = [
        (event.event_type, by_id.get(event.person_id), "union" if event.union_id == family["union"].id else None, event.date_text)
        for event in session.query(Event).all()
    ]
    return ordered(rows)


def ordered(rows):
    return sorted(rows, key=str)


def test_at5_dates_keep_the_recorded_precision():
    assert at5_date(6, 4, 1926, None, None, None, 0, False) == ("6 APR 1926", "exact", date(1926, 4, 6), date(1926, 4, 6))
    assert at5_date(None, 3, 2004, None, None, None, 0, False) == ("MAR 2004", "exact", date(2004, 3, 1), date(2004, 3, 31))
    assert at5_date(None, None, 1944, None, None, None, 0, False) == ("1944", "exact", date(1944, 1, 1), date(1944, 12, 31))
    assert at5_date(None, None, None, None, None, None, 0, False) is None


def test_at5_dates_that_cannot_be_read_safely_are_rejected():
    with pytest.raises(At5ImportError, match="юлиан"):
        at5_date(1, 1, 1850, None, None, None, 0, True)
    with pytest.raises(At5ImportError, match="тип"):
        at5_date(1, 1, 1850, None, None, None, 3, False)
    with pytest.raises(At5ImportError, match="период"):
        at5_date(1, 1, 1850, 1, 1, 1860, 0, False)


def test_sync_rebuilds_events_from_at5_owners_and_dates(session, family, tmp_path):
    report = sync_events_from_at5(session, create_at5(tmp_path / "tree.at5"), apply=True)

    assert events_by_owner(session, family) == ordered([
        ("BIRT", 3, None, "6 APR 1926"),
        ("DEAT", 1, None, "1944"),
        ("DEAT", 2, None, "MAR 2004"),
        ("MARR", None, "union", None),
        ("MARR", 1, None, None),
        ("MARR", 4, None, None),
    ])
    assert report.before == {"BIRT": 1, "DEAT": 1, "MARR": 1}
    assert report.after == {"BIRT": 1, "DEAT": 2, "MARR": 3}
    assert report.dated_after == 3
    assert report.skipped_absent_people == 1
    assert report.skipped_without_owner == 1
    assert report.marriages_without_union == 1
    assert {person.id for person in session.query(Person).all()} == set(family["ids"].values())
    audit = session.query(ImportRun).filter_by(original_filename="tree.at5").one()
    assert audit.state == "applied"
    assert audit.counts["events"] == 6


def test_dry_run_reports_without_touching_the_database(session, family, tmp_path):
    report = sync_events_from_at5(session, create_at5(tmp_path / "tree.at5"), apply=False)

    assert report.after == {"BIRT": 1, "DEAT": 2, "MARR": 3}
    assert events_by_owner(session, family) == ordered([("BIRT", 1, None, None), ("DEAT", 1, None, None), ("MARR", 1, None, None)])
    assert session.query(ImportRun).filter_by(original_filename="tree.at5").count() == 0


def test_sync_refuses_to_overwrite_manual_edits(session, family, tmp_path):
    session.add(ChangeLog(entity_type="person", entity_id=family["ids"][1], owner_email="owner@example.test", before={}, after={}))
    session.commit()

    with pytest.raises(At5ImportError, match="правк"):
        sync_events_from_at5(session, create_at5(tmp_path / "tree.at5"), apply=True)
    assert len(events_by_owner(session, family)) == 3


def test_sync_refuses_to_drop_event_places_or_descriptions(session, family, tmp_path):
    session.query(Event).filter_by(event_type="DEAT").update({"place": "Москва"})
    session.commit()

    with pytest.raises(At5ImportError, match="мест"):
        sync_events_from_at5(session, create_at5(tmp_path / "tree.at5"), apply=True)


def test_sync_rejects_an_at5_file_from_another_tree(session, family, tmp_path):
    session.query(Person).update({"source_uid": None})
    session.commit()

    with pytest.raises(At5ImportError, match="сопостав"):
        sync_events_from_at5(session, create_at5(tmp_path / "tree.at5"), apply=True)
