from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.imports.service import apply_preview, create_preview, get_import_run
from app.models.genealogy import ImportRun

router = APIRouter()


class IssueResponse(BaseModel):
    severity: str
    message: str
    line_number: int | None
    tag: str | None


class ImportResponse(BaseModel):
    id: UUID
    state: str
    counts: dict[str, int]
    issues: list[IssueResponse]


def response_for(run: ImportRun) -> ImportResponse:
    return ImportResponse(
        id=run.id,
        state=run.state,
        counts=run.counts,
        issues=[IssueResponse(severity=issue.severity, message=issue.message, line_number=issue.line_number, tag=issue.tag) for issue in run.issues],
    )


@router.post("/admin/imports/preview", status_code=status.HTTP_201_CREATED, response_model=ImportResponse)
async def preview_import(
    file: UploadFile = File(...),
    _: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> ImportResponse:
    if not file.filename or not file.filename.lower().endswith(".ged"):
        raise HTTPException(status_code=422, detail="Нужен файл GEDCOM с расширением .ged.")
    return response_for(create_preview(session, file.filename, await file.read()))


@router.get("/admin/imports/{import_id}", response_model=ImportResponse)
def get_import(import_id: UUID, _: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> ImportResponse:
    try:
        return response_for(get_import_run(session, import_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/admin/imports/{import_id}/apply", response_model=ImportResponse)
def apply_import(import_id: UUID, _: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> ImportResponse:
    try:
        return response_for(apply_preview(session, import_id))
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        code = 422 if "ошибк" in str(error) else 409
        raise HTTPException(status_code=code, detail=str(error)) from error
