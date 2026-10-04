import sqlite3
from pathlib import Path

import pytest

from app.gedcom.at5 import At5ImportError, restore_events_from_at5
from app.gedcom.parser import build_preview, parse_gedcom


GEDCOM = b"""0 @I1@ INDI
1 NAME Parent /One/
0 @I2@ INDI
1 NAME Parent /Two/
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
"""


def create_at5(path: Path, participant_id: int = 1) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE Events (id INTEGER, db_id INTEGER, et_id INTEGER, et_db_id INTEGER);
        CREATE TABLE EventTypes (id INTEGER, db_id INTEGER, gedname TEXT);
        CREATE TABLE EventDetails (p_id INTEGER, p_db_id INTEGER, e_id INTEGER, e_db_id INTEGER, er_id INTEGER, er_db_id INTEGER, e_ord INTEGER, p_ord INTEGER);
        CREATE TABLE EventRoles (id INTEGER, db_id INTEGER, ismain BOOLEAN);
        INSERT INTO EventTypes VALUES (1, -1, 'BIRT'), (2, -1, 'MARR'), (3, -1, 'OCCU');
        INSERT INTO EventRoles VALUES (1, -1, 1);
        INSERT INTO Events VALUES (1, 0, 1, -1), (2, 0, 2, -1), (3, 0, 3, -1);
        INSERT INTO EventDetails VALUES (1, 0, 1, 0, 1, -1, 0, 0), (1, 0, 2, 0, 1, -1, 0, 0), (2, 0, 2, 0, 1, -1, 0, 1), (2, 0, 3, 0, 1, -1, 0, 0);
        """
    )
    connection.execute("UPDATE EventDetails SET p_id = ? WHERE e_id = 1", (participant_id,))
    connection.commit()
    connection.close()


def test_at5_events_replace_gedcom_events_and_match_marriage_to_union(tmp_path):
    at5_path = tmp_path / "tree.at5"
    create_at5(at5_path)
    preview = build_preview(parse_gedcom(GEDCOM))

    restored = restore_events_from_at5(preview, at5_path)

    assert restored.counts["events"] == 3
    assert {(event.event_type, event.person_pointer, event.union_pointer) for event in restored.events} == {
        ("BIRT", "@I1@", None),
        ("MARR", None, "@F1@"),
        ("OCCU", "@I2@", None),
    }


def test_at5_event_with_unknown_person_is_rejected(tmp_path):
    at5_path = tmp_path / "tree.at5"
    create_at5(at5_path, participant_id=99)
    preview = build_preview(parse_gedcom(GEDCOM))

    with pytest.raises(At5ImportError, match="не найдена"):
        restore_events_from_at5(preview, at5_path)
