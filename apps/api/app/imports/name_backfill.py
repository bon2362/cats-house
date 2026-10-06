"""Fill surname / given name / patronymic from AT5 for people who have none yet."""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gedcom.at5 import read_at5_name_parts
from app.models.genealogy import ImportRun, Person


@dataclass(frozen=True)
class NameBackfillReport:
    applied: bool
    filled: int
    already_filled: int
    without_at5_names: int
    without_source: int
    display_name_differs: int


def backfill_name_parts(session: Session, path: Path, apply: bool = False) -> NameBackfillReport:
    parts_by_at5 = read_at5_name_parts(path)
    filled = already_filled = without_names = without_source = differs = 0
    for person in session.scalars(select(Person).order_by(Person.id)):
        prefix, _, number = (person.source_uid or "").rpartition("_")
        if not prefix or not number.isdigit():
            without_source += 1
            continue
        if any((person.surname, person.given_name, person.patronymic, person.birth_surname)):
            already_filled += 1
            continue
        parts = parts_by_at5.get(int(number))
        if not parts:
            without_names += 1
            continue
        filled += 1
        composed = " ".join(part for part in (parts.get("given_name"), parts.get("patronymic"), parts.get("surname")) if part)
        if composed != person.display_name:
            differs += 1
        if apply:
            person.surname = parts.get("surname")
            person.given_name = parts.get("given_name")
            person.patronymic = parts.get("patronymic")
    report = NameBackfillReport(apply, filled, already_filled, without_names, without_source, differs)
    if not apply:
        session.rollback()
        return report
    session.add(
        ImportRun(
            original_filename=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            state="applied",
            normalized_payload={"mode": "name-parts-backfill", "report": asdict(report)},
            counts={"people": filled},
        )
    )
    session.commit()
    return report
