import hashlib
from dataclasses import asdict
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.gedcom.parser import build_preview, parse_gedcom
from app.gedcom.at5 import restore_events_from_at5
from app.models.genealogy import ImportIssue, ImportRun
from app.models.genealogy import Event, ParentChild, Person, Union


def create_preview(session: Session, filename: str, content: bytes, at5_path=None) -> ImportRun:
    preview = build_preview(parse_gedcom(content))
    if at5_path is not None:
        preview = restore_events_from_at5(preview, at5_path)
    run = ImportRun(
        original_filename=filename,
        sha256=hashlib.sha256(content).hexdigest(),
        state="previewed",
        normalized_payload=_jsonable(asdict(preview)),
        counts=preview.counts,
    )
    run.issues = [
        ImportIssue(
            severity=issue.severity,
            message=issue.message,
            line_number=issue.line_number,
            tag=issue.tag,
        )
        for issue in preview.issues
    ]
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def get_import_run(session: Session, import_id: UUID) -> ImportRun:
    run = session.get(ImportRun, import_id)
    if run is None:
        raise LookupError("Предпросмотр импорта не найден.")
    return run


def apply_preview(session: Session, import_id: UUID) -> ImportRun:
    run = get_import_run(session, import_id)
    if run.state != "previewed":
        raise ValueError("Этот предпросмотр уже был применён или отклонён.")
    if run.has_errors:
        run.state = "failed"
        session.commit()
        raise ValueError("Импорт нельзя применить: в предпросмотре есть ошибки.")
    if session.query(Person).count() > 0:
        raise ValueError("Начальный импорт уже был выполнен.")

    try:
        payload = run.normalized_payload
        people_by_pointer = {}
        for raw_person in payload["people"]:
            person = Person(
                import_run_id=run.id,
                display_name=raw_person["name"],
                source_uid=raw_person["source_uid"],
                sex=raw_person["sex"],
            )
            session.add(person)
            people_by_pointer[raw_person["pointer"]] = person
        session.flush()

        unions_by_pointer = {}
        for raw_family in payload["unions"]:
            union = Union(
                import_run_id=run.id,
                partner_one_id=_person_id(people_by_pointer, raw_family["husband"]),
                partner_two_id=_person_id(people_by_pointer, raw_family["wife"]),
            )
            session.add(union)
            unions_by_pointer[raw_family["pointer"]] = union
            for parent_pointer in (raw_family["husband"], raw_family["wife"]):
                if parent_pointer:
                    for child_pointer in raw_family["children"]:
                        session.add(ParentChild(parent_id=_person_id(people_by_pointer, parent_pointer), child_id=_person_id(people_by_pointer, child_pointer)))
        session.flush()

        for raw_event in payload["events"]:
            raw_date = raw_event["date"]
            union = unions_by_pointer.get(raw_event["union_pointer"])
            if raw_event["union_pointer"] and union is None:
                raise ValueError(f"Союз {raw_event['union_pointer']} не найден в предпросмотре.")
            session.add(
                Event(
                    person_id=_person_id(people_by_pointer, raw_event["person_pointer"]),
                    union_id=union.id if union else None,
                    event_type=raw_event["event_type"],
                    date_text=raw_date["text"] if raw_date else None,
                    date_qualifier=raw_date["qualifier"] if raw_date else None,
                    date_lower=date.fromisoformat(raw_date["lower"]) if raw_date and raw_date["lower"] else None,
                    date_upper=date.fromisoformat(raw_date["upper"]) if raw_date and raw_date["upper"] else None,
                )
            )
        run.state = "applied"
        session.commit()
    except Exception:
        session.rollback()
        run = get_import_run(session, import_id)
        run.state = "failed"
        session.add(ImportIssue(import_run_id=run.id, severity="error", message="Не удалось применить импорт."))
        session.commit()
        raise
    return get_import_run(session, import_id)


def _person_id(people_by_pointer: dict, pointer: str | None):
    if pointer is None:
        return None
    try:
        return people_by_pointer[pointer].id
    except KeyError as error:
        raise ValueError(f"Ссылка {pointer} не найдена в предпросмотре.") from error


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
