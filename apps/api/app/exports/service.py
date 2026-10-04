from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, ImportRun, Media, Person


def export_gedcom(session: Session) -> bytes:
    lines = ["0 HEAD", "1 GEDC", "2 VERS 5.5.1", "1 CHAR UTF-8"]
    people = session.scalars(select(Person).where(Person.is_archived.is_(False)).order_by(Person.display_name)).all()
    for index, person in enumerate(people, 1):
        names = person.display_name.split(maxsplit=1)
        given = names[0]
        surname = names[1] if len(names) > 1 else ""
        lines.extend((f"0 @I{index}@ INDI", f"1 NAME {given} /{surname}/"))
        if person.sex:
            lines.append(f"1 SEX {person.sex}")
        if person.source_uid:
            lines.append(f"1 _UID {person.source_uid}")
    lines.append("0 TRLR")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def build_archive(session: Session) -> dict:
    people = session.scalars(select(Person).where(Person.is_archived.is_(False))).all()
    events = session.scalars(select(Event)).all()
    media = session.scalars(select(Media)).all()
    people_by_id = {person.id: person for person in people}
    return {
        "format": "cats-house-archive-v1",
        "people": [{"display_name": person.display_name, "source_uid": person.source_uid, "sex": person.sex, "biography": person.biography} for person in people],
        "events": [{"person_source_uid": people_by_id[event.person_id].source_uid if event.person_id in people_by_id else None, "event_type": event.event_type, "date_text": event.date_text} for event in events],
        "media_manifest": [{"storage_key": item.storage_key, "media_type": item.media_type, "original_filename": item.original_filename, "is_published": item.is_published} for item in media],
        "counts": {"people": len(people), "events": len(events), "media": len(media)},
    }


def restore_archive(session: Session, archive: dict) -> None:
    if archive.get("format") != "cats-house-archive-v1":
        raise ValueError("Неподдерживаемый формат архива.")
    run = ImportRun(original_filename="cats-house-archive.json", sha256="archive", state="applied", normalized_payload={}, counts=archive["counts"])
    session.add(run)
    session.flush()
    restored_people: dict[str, Person] = {}
    for data in archive["people"]:
        person = Person(import_run_id=run.id, display_name=data["display_name"], source_uid=data.get("source_uid"), sex=data.get("sex"), biography=data.get("biography"))
        session.add(person)
        if person.source_uid:
            restored_people[person.source_uid] = person
    session.flush()
    for data in archive["events"]:
        person = restored_people.get(data.get("person_source_uid"))
        session.add(Event(person_id=person.id if person else None, event_type=data["event_type"], date_text=data.get("date_text")))
    for data in archive["media_manifest"]:
        session.add(Media(**data))
    session.commit()
