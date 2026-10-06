"""Read event ownership from a local, read-only Древо Жизни AT5 database."""

import sqlite3
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from app.gedcom.types import ImportPreview, PreviewEvent


class At5ImportError(ValueError):
    """AT5 and GEDCOM cannot be safely used together for this import."""


def restore_events_from_at5(preview: ImportPreview, path: Path) -> ImportPreview:
    """Replace GEDCOM events with the complete AT5 event list.

    The exporter's GEDCOM pointers are the numeric primary keys of the AT5
    ``Persons`` table. The function validates that invariant before importing
    an event, so a different database cannot silently attach facts to a wrong
    person.
    """
    if not path.is_absolute() or not path.is_file():
        raise At5ImportError("Укажите существующий абсолютный путь к файлу AT5.")

    people = {person.pointer: person for person in preview.people}
    existing_dates = {
        (event.person_pointer, event.event_type): event.date
        for event in preview.events
        if event.person_pointer is not None
    }
    unions_by_partners = {
        frozenset(pointer for pointer in (family.husband, family.wife) if pointer): family.pointer
        for family in preview.unions
    }

    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = connection.execute(
            """
            SELECT e.id, e.db_id, et.gedname, ed.p_id, er.ismain
            FROM Events e
            JOIN EventTypes et ON et.id = e.et_id AND et.db_id = e.et_db_id
            LEFT JOIN EventDetails ed ON ed.e_id = e.id AND ed.e_db_id = e.db_id
            LEFT JOIN EventRoles er ON er.id = ed.er_id AND er.db_id = ed.er_db_id
            ORDER BY e.id, e.db_id, ed.e_ord, ed.p_ord
            """
        ).fetchall()
    except sqlite3.Error as error:
        raise At5ImportError("Не удалось прочитать события из файла AT5.") from error
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass

    by_event: dict[tuple[int, int, str], list[tuple[int, bool]]] = {}
    for event_id, database_id, event_type, person_id, is_main in rows:
        key = (event_id, database_id, event_type)
        by_event.setdefault(key, [])
        if person_id is not None:
            pointer = f"@I{person_id}@"
            if pointer not in people:
                raise At5ImportError(f"Ссылка {pointer} из AT5 не найдена в GEDCOM.")
            if is_main:
                by_event[key].append((person_id, True))

    events: list[PreviewEvent] = []
    for event_key, main_participants in by_event.items():
        _, _, event_type = event_key
        main_people = tuple(f"@I{person_id}@" for person_id, _is_main in main_participants)
        if event_type == "MARR" and len(main_people) == 2:
            union_pointer = unions_by_partners.get(frozenset(main_people))
            if union_pointer is not None:
                events.append(PreviewEvent(event_type="MARR", union_pointer=union_pointer))
                continue
        for person_pointer in main_people:
            events.append(
                PreviewEvent(
                    event_type=event_type,
                    person_pointer=person_pointer,
                    date=existing_dates.get((person_pointer, event_type)),
                )
            )

    counts = {**preview.counts, "events": len(events)}
    return replace(preview, events=tuple(events), counts=counts)


MONTH_NAMES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
# ValuesDates.f_id of the main event date in Древо Жизни (field 29, table code 7 = Events).
EVENT_DATE_FIELD = 29
EVENTS_TABLE = 7


@dataclass(frozen=True)
class At5Event:
    """One AT5 event with the AT5 person ids of its main participants."""

    source_id: int
    event_type: str
    main_person_ids: tuple[int, ...]
    date: tuple[str, str, date | None, date | None] | None


def at5_date(day, month, year, day2, month2, year2, kind, is_julian) -> tuple[str, str, date | None, date | None] | None:
    """Convert an AT5 date to (GEDCOM text, qualifier, lower, upper) at the recorded precision.

    Only plain Gregorian single dates exist in the source today. Anything else is
    rejected rather than guessed, so a future file cannot be silently misread.
    """
    if year is None:
        return None
    if is_julian:
        raise At5ImportError("Даты по юлианскому календарю пока не поддерживаются.")
    if kind not in (0, None):
        raise At5ImportError(f"Неизвестный тип даты AT5: {kind}.")
    if year2 is not None or month2 is not None or day2 is not None:
        raise At5ImportError("Даты-периоды AT5 пока не поддерживаются.")
    if month is None:
        return (str(year), "exact", date(year, 1, 1), date(year, 12, 31))
    month_name = MONTH_NAMES[month - 1]
    if day is None:
        return (f"{month_name} {year}", "exact", date(year, month, 1), date(year, month, monthrange(year, month)[1]))
    exact = date(year, month, day)
    return (f"{day} {month_name} {year}", "exact", exact, exact)


def read_at5_events(path: Path) -> list[At5Event]:
    """Read every event, its main participants and its date from an AT5 file, read-only."""
    if not path.is_absolute() or not path.is_file():
        raise At5ImportError("Укажите существующий абсолютный путь к файлу AT5.")
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        events = connection.execute(
            """
            SELECT e.id, et.gedname
            FROM Events e
            JOIN EventTypes et ON et.id = e.et_id AND et.db_id = e.et_db_id
            ORDER BY e.id
            """
        ).fetchall()
        participants = connection.execute(
            """
            SELECT ed.e_id, ed.p_id
            FROM EventDetails ed
            JOIN EventRoles er ON er.id = ed.er_id AND er.db_id = ed.er_db_id
            WHERE er.ismain = 1 AND ed.p_id IS NOT NULL
            ORDER BY ed.e_id, ed.e_ord, ed.p_ord
            """
        ).fetchall()
        dates = connection.execute(
            "SELECT rec_id, d, m, y, d2, m2, y2, type, isjulian FROM ValuesDates WHERE rec_table = ? AND f_id = ?",
            (EVENTS_TABLE, EVENT_DATE_FIELD),
        ).fetchall()
    except sqlite3.Error as error:
        raise At5ImportError("Не удалось прочитать события из файла AT5.") from error
    finally:
        if connection is not None:
            connection.close()

    main_by_event: dict[int, list[int]] = {}
    for event_id, person_id in participants:
        main_by_event.setdefault(event_id, []).append(person_id)
    date_by_event = {row[0]: at5_date(*row[1:]) for row in dates}
    return [
        At5Event(event_id, event_type, tuple(main_by_event.get(event_id, ())), date_by_event.get(event_id))
        for event_id, event_type in events
    ]


def read_at5_people(path: Path) -> dict[int, str | None]:
    """AT5 person ids with their sex as stored on the site (M/F), read-only."""
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = connection.execute("SELECT id, sex FROM Persons").fetchall()
    except sqlite3.Error as error:
        raise At5ImportError("Не удалось прочитать людей из файла AT5.") from error
    finally:
        if connection is not None:
            connection.close()
    return {person_id: {1: "M", 2: "F"}.get(sex) for person_id, sex in rows}
