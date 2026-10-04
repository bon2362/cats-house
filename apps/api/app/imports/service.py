import hashlib
from dataclasses import asdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.gedcom.parser import build_preview, parse_gedcom
from app.models.genealogy import ImportIssue, ImportRun


def create_preview(session: Session, filename: str, content: bytes) -> ImportRun:
    preview = build_preview(parse_gedcom(content))
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


def _jsonable(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value
