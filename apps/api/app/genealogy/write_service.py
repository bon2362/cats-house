from uuid import UUID

from sqlalchemy.orm import Session

from app.models.genealogy import ChangeLog, Person


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
