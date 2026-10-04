from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.exports.service import export_gedcom

router = APIRouter()


@router.get("/admin/exports/gedcom")
def download_gedcom(_: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> Response:
    return Response(
        content=export_gedcom(session),
        media_type="application/x-gedcom; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cats-house.ged"'},
    )
