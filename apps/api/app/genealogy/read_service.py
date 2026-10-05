import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, Media, MediaLink, ParentChild, Person, Union


_MONTHS_RU = {
    "JAN": "января", "FEB": "февраля", "MAR": "марта", "APR": "апреля",
    "MAY": "мая", "JUN": "июня", "JUL": "июля", "AUG": "августа",
    "SEP": "сентября", "OCT": "октября", "NOV": "ноября", "DEC": "декабря",
}
_QUALIFIERS_RU = {"ABT": "ок.", "EST": "ок.", "CAL": "ок.", "BEF": "до", "AFT": "после"}


@dataclass(frozen=True)
class PublicPersonSummary:
    id: UUID
    display_name: str
    birth_label: str | None
    death_label: str | None
    years: str | None
    is_living: bool | None
    parents_label: str | None


def normalize_public_name(value: str) -> str:
    cleaned = re.sub(r"\?+", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    return cleaned or "Неизвестный человек"


def format_public_date(value: str | None) -> str | None:
    if not value:
        return None
    words = value.strip().split()
    if not words:
        return None
    qualifier = _QUALIFIERS_RU.get(words[0].upper())
    if qualifier:
        words = words[1:]
    if len(words) == 3 and words[1].upper() in _MONTHS_RU and words[0].isdigit() and words[2].isdigit():
        rendered = f"{int(words[0])} {_MONTHS_RU[words[1].upper()]} {words[2]}"
    else:
        rendered = " ".join(words)
    return f"{qualifier} {rendered}" if qualifier else rendered


def _year(value: str | None) -> str | None:
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", value or "")
    return match.group(1) if match else None


def public_person_summary(session: Session, person: Person) -> PublicPersonSummary:
    events = public_events(session, person.id)
    birth = next((event for event in events if event.event_type == "BIRT"), None)
    death = next((event for event in events if event.event_type == "DEAT"), None)
    birth_label = format_public_date(birth.date_text if birth else None)
    death_label = format_public_date(death.date_text if death else None)
    birth_year, death_year = _year(birth_label), _year(death_label)
    years = f"{birth_year or '?'} – {death_year or '?'}" if birth_year or death_year else None
    parents, _, _ = public_family(session, person.id)
    parents_label = " и ".join(normalize_public_name(parent.display_name) for parent in parents) or None
    return PublicPersonSummary(
        id=person.id,
        display_name=normalize_public_name(person.display_name),
        birth_label=birth_label,
        death_label=death_label,
        years=years,
        is_living=False if death else None,
        parents_label=parents_label,
    )


def search_people(session: Session, query: str) -> list[Person]:
    normalized_query = query.strip().lower().replace("ё", "е")
    statement = select(Person).where(Person.is_archived.is_(False))
    if normalized_query:
        normalized_name = func.replace(func.lower(Person.display_name), "ё", "е")
        statement = statement.where(normalized_name.contains(normalized_query))
    statement = statement.order_by(Person.display_name).limit(500 if not normalized_query else 20)
    return list(session.scalars(statement))


def featured_person(session: Session) -> Person | None:
    return session.scalar(
        select(Person)
        .where(
            Person.is_archived.is_(False),
            func.trim(Person.display_name) != "",
            Person.display_name.not_like("%?%"),
        )
        .order_by(Person.display_name)
        .limit(1)
    )


def get_public_person(session: Session, person_id: UUID) -> Person | None:
    return session.scalar(select(Person).where(Person.id == person_id, Person.is_archived.is_(False)))


def public_events(session: Session, person_id: UUID) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.person_id == person_id).order_by(Event.date_lower, Event.event_type)))


def public_family(session: Session, person_id: UUID) -> tuple[list[Person], list[Person], list[Person]]:
    active = Person.is_archived.is_(False)
    parents = list(
        session.scalars(
            select(Person)
            .join(ParentChild, ParentChild.parent_id == Person.id)
            .where(ParentChild.child_id == person_id, active)
            .order_by(Person.display_name)
        )
    )
    children = list(
        session.scalars(
            select(Person)
            .join(ParentChild, ParentChild.child_id == Person.id)
            .where(ParentChild.parent_id == person_id, active)
            .order_by(Person.display_name)
        )
    )
    partners = list(
        session.scalars(
            select(Person)
            .join(Union, or_(Union.partner_one_id == Person.id, Union.partner_two_id == Person.id))
            .where(
                or_(Union.partner_one_id == person_id, Union.partner_two_id == person_id),
                Person.id != person_id,
                active,
            )
            .order_by(Person.display_name)
        )
    )
    return parents, children, partners


def public_person_media(session: Session, person_id: UUID) -> list[Media]:
    return list(
        session.scalars(
            select(Media)
            .join(MediaLink, MediaLink.media_id == Media.id)
            .where(MediaLink.person_id == person_id, Media.is_published.is_(True))
            .order_by(Media.original_filename)
        )
    )
