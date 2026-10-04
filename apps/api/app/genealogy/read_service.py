from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, Person


def search_people(session: Session, query: str) -> list[Person]:
    statement = (
        select(Person)
        .where(Person.is_archived.is_(False), Person.display_name.ilike(f"%{query.strip()}%"))
        .order_by(Person.display_name)
        .limit(20)
    )
    return list(session.scalars(statement))


def get_public_person(session: Session, person_id: UUID) -> Person | None:
    return session.scalar(select(Person).where(Person.id == person_id, Person.is_archived.is_(False)))


def public_events(session: Session, person_id: UUID) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.person_id == person_id).order_by(Event.date_lower, Event.event_type)))
