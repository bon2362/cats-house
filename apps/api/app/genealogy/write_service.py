from uuid import UUID

from sqlalchemy.orm import Session

from app.models.genealogy import ChangeLog, Event, Person


def rename_person(session: Session, person_id: UUID, display_name: str, owner_email: str) -> Person:
    person = session.get(Person, person_id)
    if person is None or person.is_archived:
        raise LookupError("Человек не найден.")
    before = {"display_name": person.display_name}
    person.display_name = display_name
    session.add(ChangeLog(entity_type="person", entity_id=person.id, owner_email=owner_email, before=before, after={"display_name": display_name}))
    session.commit()
    session.refresh(person)
    return person


def archive_person(session: Session, person_id: UUID, owner_email: str) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    person.is_archived = True
    session.add(ChangeLog(entity_type="person", entity_id=person.id, owner_email=owner_email, before={"is_archived": False}, after={"is_archived": True}))
    session.commit()
    session.refresh(person)
    return person


def create_person_event(
    session: Session,
    person_id: UUID,
    event_type: str,
    date_text: str | None,
    owner_email: str,
) -> Event:
    person = session.get(Person, person_id)
    if person is None or person.is_archived:
        raise LookupError("Человек не найден.")
    event = Event(person_id=person_id, event_type=event_type, date_text=date_text)
    session.add(event)
    session.flush()
    session.add(
        ChangeLog(
            entity_type="event",
            entity_id=event.id,
            owner_email=owner_email,
            before={},
            after={"person_id": str(person_id), "event_type": event_type, "date_text": date_text},
        )
    )
    session.commit()
    session.refresh(event)
    return event
