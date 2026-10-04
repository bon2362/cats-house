from uuid import UUID

from sqlalchemy.orm import Session

from app.models.genealogy import ChangeLog, Event, ParentChild, Person, Union


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


def create_union(
    session: Session,
    partner_one_id: UUID,
    partner_two_id: UUID,
    union_type: str | None,
    owner_email: str,
) -> Union:
    first = session.get(Person, partner_one_id)
    second = session.get(Person, partner_two_id)
    if first is None or second is None or first.is_archived or second.is_archived:
        raise LookupError("Один из людей не найден.")
    if first.id == second.id:
        raise ValueError("Нельзя создать союз человека с самим собой.")
    if first.import_run_id != second.import_run_id:
        raise ValueError("Люди должны относиться к одному импорту.")
    union = Union(
        import_run_id=first.import_run_id,
        partner_one_id=partner_one_id,
        partner_two_id=partner_two_id,
        union_type=union_type,
    )
    session.add(union)
    session.flush()
    session.add(
        ChangeLog(
            entity_type="union",
            entity_id=union.id,
            owner_email=owner_email,
            before={},
            after={
                "partner_one_id": str(partner_one_id),
                "partner_two_id": str(partner_two_id),
                "union_type": union_type,
            },
        )
    )
    session.commit()
    session.refresh(union)
    return union


def create_parent_child_link(
    session: Session,
    parent_id: UUID,
    child_id: UUID,
    relationship_type: str,
    owner_email: str,
) -> ParentChild:
    parent = session.get(Person, parent_id)
    child = session.get(Person, child_id)
    if parent is None or child is None or parent.is_archived or child.is_archived:
        raise LookupError("Один из людей не найден.")
    if parent.id == child.id:
        raise ValueError("Человек не может быть собственным родителем.")
    link = ParentChild(parent_id=parent_id, child_id=child_id, relationship_type=relationship_type)
    session.add(link)
    session.flush()
    session.add(
        ChangeLog(
            entity_type="parent_child",
            entity_id=link.id,
            owner_email=owner_email,
            before={},
            after={
                "parent_id": str(parent_id),
                "child_id": str(child_id),
                "relationship_type": relationship_type,
            },
        )
    )
    session.commit()
    session.refresh(link)
    return link
