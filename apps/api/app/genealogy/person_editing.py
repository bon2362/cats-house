"""Owner corrections of an existing person: name parts, sex, birth and death, in one logged save."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.genealogy.dates import DateValue, build_stored_date, date_value_to_dict, parse_stored_date
from app.genealogy.read_service import normalize_public_name, public_person_summary
from app.models.genealogy import ChangeLog, Event, MediaLink, Person

MAX_NAME_LENGTH = 255
MAX_PLACE_LENGTH = 512
NAME_FIELDS = ("surname", "given_name", "patronymic", "birth_surname")
EVENT_WORDS = {"BIRT": "рождения", "DEAT": "смерти"}


class PersonEditError(ValueError):
    """Owner-facing (Russian) reason why a save is refused."""


@dataclass(frozen=True)
class LifeEventInput:
    date: DateValue | None
    place: str | None
    keep_date_text: bool = False


@dataclass(frozen=True)
class PersonEdit:
    surname: str | None
    given_name: str | None
    patronymic: str | None
    birth_surname: str | None
    sex: str | None
    birth: LifeEventInput | None
    death_status: str
    death: LifeEventInput | None


def _clean(value: str | None, limit: int, label: str) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if len(cleaned) > limit:
        raise PersonEditError(f"{label} не может быть длиннее {limit} символов.")
    return cleaned or None


def compose_display_name(given_name: str | None, patronymic: str | None, surname: str | None) -> str:
    return " ".join(part for part in (given_name, patronymic, surname) if part)


def _life_events(session: Session, person_id: UUID, kind: str) -> list[Event]:
    return list(session.scalars(
        select(Event).where(Event.person_id == person_id, Event.event_type == kind).order_by(Event.date_lower.asc().nulls_last(), Event.id)
    ))


def _single(session: Session, person_id: UUID, kind: str) -> Event | None:
    events = _life_events(session, person_id, kind)
    if len(events) > 1:
        raise PersonEditError(f"У человека несколько событий {EVENT_WORDS[kind]} — исправьте их отдельно.")
    return events[0] if events else None


def _event_view(event: Event | None) -> dict | None:
    if event is None:
        return None
    return {"date": date_value_to_dict(parse_stored_date(event.date_text)), "date_text": event.date_text, "place": event.place}


def _snapshot(session: Session, person: Person) -> dict:
    def summary(kind: str) -> dict | None:
        events = _life_events(session, person.id, kind)
        return {"date_text": events[0].date_text, "place": events[0].place} if events else None

    return {
        **{name: getattr(person, name) for name in NAME_FIELDS},
        "sex": person.sex,
        "display_name": person.display_name,
        "birth": summary("BIRT"),
        "death": summary("DEAT"),
    }


def editable_person(session: Session, person_id: UUID) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    births, deaths = _life_events(session, person.id, "BIRT"), _life_events(session, person.id, "DEAT")
    death = _event_view(deaths[0] if deaths else None)
    return {
        "id": str(person.id),
        "display_name": person.display_name,
        "is_archived": person.is_archived,
        **{name: getattr(person, name) for name in NAME_FIELDS},
        "sex": person.sex,
        "birth": _event_view(births[0] if births else None),
        "death": {"status": "deceased" if deaths else "unknown", **(death or {"date": None, "date_text": None, "place": None})},
    }


def _apply(session: Session, person: Person, kind: str, value: LifeEventInput | None) -> None:
    event = _single(session, person.id, kind)
    if value is None:
        if event is not None:
            linked = session.scalar(select(func.count()).select_from(MediaLink).where(MediaLink.event_id == event.id))
            if linked:
                raise PersonEditError("К событию привязаны материалы — сначала отвяжите их.")
            session.delete(event)
        return
    if event is None:
        event = Event(person_id=person.id, event_type=kind)
        session.add(event)
    keep_unparsed = value.keep_date_text and event.date_text and parse_stored_date(event.date_text) is None
    if not keep_unparsed:
        stored = build_stored_date(value.date) if value.date else None
        event.date_text = stored.text if stored else None
        event.date_qualifier = stored.qualifier if stored else None
        event.date_lower = stored.lower if stored else None
        event.date_upper = stored.upper if stored else None
    event.place = _clean(value.place, MAX_PLACE_LENGTH, "Место")


def update_person(session: Session, person_id: UUID, edit: PersonEdit, owner_email: str) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    try:
        names = {name: _clean(getattr(edit, name), MAX_NAME_LENGTH, "Часть имени") for name in NAME_FIELDS}
        if not names["given_name"] and not names["surname"]:
            raise PersonEditError("Укажите имя или фамилию.")
        if edit.sex not in (None, "M", "F"):
            raise PersonEditError("Неизвестное значение пола.")
        if edit.death_status not in ("unknown", "deceased"):
            raise PersonEditError("Неизвестное состояние смерти.")
        before = _snapshot(session, person)
        for name, value in names.items():
            setattr(person, name, value)
        person.sex = edit.sex
        person.display_name = compose_display_name(names["given_name"], names["patronymic"], names["surname"])
        _apply(session, person, "BIRT", edit.birth)
        _apply(session, person, "DEAT", (edit.death or LifeEventInput(None, None)) if edit.death_status == "deceased" else None)
        session.flush()
        after = _snapshot(session, person)
        changed = [key for key in after if after[key] != before[key]]
        if changed:
            session.add(ChangeLog(
                entity_type="person", entity_id=person.id, owner_email=owner_email,
                before={key: before[key] for key in changed}, after={key: after[key] for key in changed},
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return editable_person(session, person_id)


def owner_search(session: Session, query: str) -> list[dict]:
    normalized = query.strip().lower().replace("ё", "е")
    statement = select(Person)
    if normalized:
        def folded(column):
            return func.replace(func.lower(func.coalesce(column, "")), "ё", "е")
        statement = statement.where(or_(folded(Person.display_name).contains(normalized), folded(Person.birth_surname).contains(normalized)))
    people = session.scalars(statement.order_by(Person.display_name).limit(20))
    return [
        {"id": str(person.id), "display_name": normalize_public_name(person.display_name), "years": public_person_summary(session, person).years, "is_archived": person.is_archived}
        for person in people
    ]
