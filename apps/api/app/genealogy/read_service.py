from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, Media, MediaLink, ParentChild, Person, Union


def search_people(session: Session, query: str) -> list[Person]:
    statement = (
        select(Person)
        .where(Person.is_archived.is_(False), Person.display_name.ilike(f"%{query.strip()}%"))
        .order_by(Person.display_name)
        .limit(20)
    )
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
