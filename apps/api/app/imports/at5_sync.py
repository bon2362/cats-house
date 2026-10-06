"""Rebuild site events from the Древо Жизни AT5 file, which is the source of truth.

People, unions and parent links are left untouched: they already match AT5 and
their ids are used in public URLs. Only events (births, deaths, marriages) are
rebuilt, with their owners and dates taken directly from AT5.
"""

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.gedcom.at5 import At5ImportError, read_at5_events, read_at5_people
from app.models.genealogy import ChangeLog, Event, ImportRun, MediaLink, Person, Union


@dataclass(frozen=True)
class At5SyncReport:
    applied: bool
    before: dict[str, int]
    after: dict[str, int]
    dated_before: int
    dated_after: int
    skipped_absent_people: int
    skipped_without_owner: int
    marriages_without_union: int


def sync_events_from_at5(session: Session, path: Path, apply: bool = False) -> At5SyncReport:
    """Compute (and with ``apply`` write in one transaction) the AT5 event set."""
    at5_people = read_at5_people(path)
    at5_events = read_at5_events(path)
    person_by_at5 = _match_people(session, at5_people)
    _refuse_manual_edits(session)

    union_by_pair: dict[frozenset[UUID], UUID] = {}
    for union_id, first, second in session.execute(select(Union.id, Union.partner_one_id, Union.partner_two_id).order_by(Union.id)):
        if first and second:
            union_by_pair.setdefault(frozenset((first, second)), union_id)

    targets: list[Event] = []
    skipped_absent = skipped_without_owner = marriages_without_union = 0
    for at5_event in at5_events:
        if not at5_event.main_person_ids:
            skipped_without_owner += 1
            continue
        owners = [person_by_at5.get(person_id) for person_id in at5_event.main_person_ids]
        if any(owner is None for owner in owners):
            # Someone deliberately removed from the site (or never imported): do not bring them back.
            skipped_absent += 1
            owners = [owner for owner in owners if owner is not None]
            if not owners:
                continue
        text, qualifier, lower, upper = at5_event.date or (None, None, None, None)
        dated = {"date_text": text, "date_qualifier": qualifier, "date_lower": lower, "date_upper": upper}
        if at5_event.event_type == "MARR" and len(owners) == 2:
            union_id = union_by_pair.get(frozenset(owners))
            if union_id is not None:
                targets.append(Event(union_id=union_id, event_type="MARR", **dated))
                continue
            marriages_without_union += 1
        targets.extend(Event(person_id=owner, event_type=at5_event.event_type, **dated) for owner in owners)

    before = Counter(session.scalars(select(Event.event_type)).all())
    dated_before = session.scalar(select(func.count()).select_from(Event).where(Event.date_text.is_not(None))) or 0
    report = At5SyncReport(
        applied=apply,
        before=dict(sorted(before.items())),
        after=dict(sorted(Counter(event.event_type for event in targets).items())),
        dated_before=dated_before,
        dated_after=sum(1 for event in targets if event.date_text),
        skipped_absent_people=skipped_absent,
        skipped_without_owner=skipped_without_owner,
        marriages_without_union=marriages_without_union,
    )
    if not apply:
        return report

    try:
        session.execute(delete(Event))
        session.add_all(targets)
        session.add(
            ImportRun(
                original_filename=path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                state="applied",
                normalized_payload={"mode": "at5-event-sync", "report": asdict(report)},
                counts={"events": len(targets), **report.after},
            )
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return report


def _match_people(session: Session, at5_people: dict[int, str | None]) -> dict[int, UUID]:
    """Map AT5 person ids to site people through ``source_uid`` = ``<tree id>_<AT5 id>``."""
    rows = session.execute(select(Person.id, Person.source_uid, Person.sex)).all()
    matched: dict[int, UUID] = {}
    prefixes: set[str] = set()
    for person_id, source_uid, sex in rows:
        prefix, _, number = (source_uid or "").rpartition("_")
        if not prefix or not number.isdigit():
            continue
        at5_id = int(number)
        if at5_id not in at5_people or (sex and at5_people[at5_id] and sex != at5_people[at5_id]):
            raise At5ImportError("Не удалось сопоставить людей сайта с этим файлом AT5: похоже, это другое дерево.")
        prefixes.add(prefix)
        matched[at5_id] = person_id
    if not matched or len(prefixes) != 1 or len(matched) != len(rows):
        raise At5ImportError("Не удалось сопоставить людей сайта с этим файлом AT5: у части людей нет ссылки на запись AT5.")
    return matched


def _refuse_manual_edits(session: Session) -> None:
    """Events are replaced wholesale, so anything entered on the site must not exist yet."""
    if session.scalar(select(func.count()).select_from(ChangeLog)):
        raise At5ImportError("На сайте уже есть ручные правки: пересборка событий из AT5 их перезапишет.")
    if session.scalar(select(func.count()).select_from(Event).where(or_(Event.place.is_not(None), Event.description.is_not(None)))):
        raise At5ImportError("У событий на сайте есть места или описания, которых нет в AT5.")
    if session.scalar(select(func.count()).select_from(MediaLink).where(MediaLink.event_id.is_not(None))):
        raise At5ImportError("К событиям на сайте привязаны медиа-файлы.")
