"""Read event ownership from a local, read-only Древо Жизни AT5 database."""

import sqlite3
from dataclasses import replace
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
