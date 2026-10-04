from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.genealogy import Person


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
