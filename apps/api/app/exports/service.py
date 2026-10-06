from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, ImportRun, Media, MediaLink, ParentChild, Person, Union


def export_gedcom(session: Session) -> bytes:
    lines = ["0 HEAD", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]
    people = session.scalars(select(Person).where(Person.is_archived.is_(False)).order_by(Person.display_name)).all()
    for index, person in enumerate(people, 1):
        names = person.display_name.split(maxsplit=1)
        given = names[0] if names else ""
        surname = names[1] if len(names) > 1 else ""
        lines.extend((f"0 @I{index}@ INDI", f"1 NAME {given} /{surname}/"))
        if person.sex:
            lines.append(f"1 SEX {person.sex}")
        if person.source_uid:
            lines.append(f"1 _UID {person.source_uid}")
    lines.append("0 TRLR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value else None


def build_archive(session: Session) -> dict:
    people = session.scalars(select(Person)).all()
    unions = session.scalars(select(Union)).all()
    parent_children = session.scalars(select(ParentChild)).all()
    events = session.scalars(select(Event)).all()
    media = session.scalars(select(Media)).all()
    media_links = session.scalars(select(MediaLink)).all()
    people_by_id = {person.id: person for person in people}
    return {
        "format": "cats-house-archive-v1",
        "people": [
            {"archive_id": str(person.id), "display_name": person.display_name, "surname": person.surname, "given_name": person.given_name, "patronymic": person.patronymic, "birth_surname": person.birth_surname, "source_uid": person.source_uid, "sex": person.sex, "biography": person.biography, "is_archived": person.is_archived}
            for person in people
        ],
        "unions": [
            {"archive_id": str(union.id), "partner_one_archive_id": str(union.partner_one_id) if union.partner_one_id else None, "partner_two_archive_id": str(union.partner_two_id) if union.partner_two_id else None, "union_type": union.union_type}
            for union in unions
        ],
        "parent_children": [
            {
                "parent_archive_id": str(link.parent_id),
                "child_archive_id": str(link.child_id),
                "union_archive_id": str(link.union_id) if link.union_id else None,
                "relationship_type": link.relationship_type,
            }
            for link in parent_children
        ],
        "events": [
            {
                "archive_id": str(event.id),
                "person_archive_id": str(event.person_id) if event.person_id else None,
                "union_archive_id": str(event.union_id) if event.union_id else None,
                "person_source_uid": people_by_id[event.person_id].source_uid if event.person_id in people_by_id else None,
                "event_type": event.event_type,
                "date_text": event.date_text,
                "date_qualifier": event.date_qualifier,
                "date_lower": _date_text(event.date_lower),
                "date_upper": _date_text(event.date_upper),
                "place": event.place,
                "description": event.description,
            }
            for event in events
        ],
        "media_manifest": [
            {"archive_id": str(item.id), "storage_key": item.storage_key, "media_type": item.media_type, "original_filename": item.original_filename, "is_published": item.is_published}
            for item in media
        ],
        "media_links": [
            {"media_archive_id": str(link.media_id), "person_archive_id": str(link.person_id) if link.person_id else None, "event_archive_id": str(link.event_id) if link.event_id else None}
            for link in media_links
        ],
        "counts": {"people": len(people), "events": len(events), "unions": len(unions), "parent_children": len(parent_children), "media": len(media), "media_links": len(media_links)},
    }


def restore_archive(session: Session, archive: dict) -> None:
    if archive.get("format") != "cats-house-archive-v1":
        raise ValueError("Неподдерживаемый формат архива.")
    run = ImportRun(original_filename="cats-house-archive.json", sha256="archive", state="applied", normalized_payload={}, counts=archive["counts"])
    session.add(run)
    session.flush()

    restored_people: dict[str, Person] = {}
    people_by_source_uid: dict[str, Person] = {}
    for data in archive["people"]:
        person = Person(import_run_id=run.id, display_name=data["display_name"], surname=data.get("surname"), given_name=data.get("given_name"), patronymic=data.get("patronymic"), birth_surname=data.get("birth_surname"), source_uid=data.get("source_uid"), sex=data.get("sex"), biography=data.get("biography"), is_archived=data.get("is_archived", False))
        session.add(person)
        if data.get("archive_id"):
            restored_people[data["archive_id"]] = person
        if person.source_uid:
            people_by_source_uid[person.source_uid] = person
    session.flush()

    restored_unions: dict[str, Union] = {}
    for data in archive.get("unions", []):
        first = restored_people.get(data.get("partner_one_archive_id"))
        second = restored_people.get(data.get("partner_two_archive_id"))
        union = Union(import_run_id=run.id, partner_one_id=first.id if first else None, partner_two_id=second.id if second else None, union_type=data.get("union_type"))
        session.add(union)
        if data.get("archive_id"):
            restored_unions[data["archive_id"]] = union
    session.flush()

    for data in archive.get("parent_children", []):
        parent = restored_people.get(data.get("parent_archive_id"))
        child = restored_people.get(data.get("child_archive_id"))
        if parent and child:
            union = restored_unions.get(data.get("union_archive_id"))
            session.add(
                ParentChild(
                    parent_id=parent.id,
                    child_id=child.id,
                    union_id=union.id if union else None,
                    relationship_type=data["relationship_type"],
                )
            )

    restored_events: dict[str, Event] = {}
    for data in archive["events"]:
        person = restored_people.get(data.get("person_archive_id")) or people_by_source_uid.get(data.get("person_source_uid"))
        union = restored_unions.get(data.get("union_archive_id"))
        event = Event(
            person_id=person.id if person else None,
            union_id=union.id if union else None,
            event_type=data["event_type"],
            date_text=data.get("date_text"),
            date_qualifier=data.get("date_qualifier"),
            date_lower=date.fromisoformat(data["date_lower"]) if data.get("date_lower") else None,
            date_upper=date.fromisoformat(data["date_upper"]) if data.get("date_upper") else None,
            place=data.get("place"),
            description=data.get("description"),
        )
        session.add(event)
        if data.get("archive_id"):
            restored_events[data["archive_id"]] = event
    session.flush()

    restored_media: dict[str, Media] = {}
    for data in archive["media_manifest"]:
        media = Media(storage_key=data["storage_key"], media_type=data["media_type"], original_filename=data.get("original_filename", ""), is_published=data.get("is_published", False))
        session.add(media)
        if data.get("archive_id"):
            restored_media[data["archive_id"]] = media
    session.flush()

    for data in archive.get("media_links", []):
        media = restored_media.get(data.get("media_archive_id"))
        person = restored_people.get(data.get("person_archive_id"))
        event = restored_events.get(data.get("event_archive_id"))
        if media and (person or event):
            session.add(MediaLink(media_id=media.id, person_id=person.id if person else None, event_id=event.id if event else None))
    session.commit()
