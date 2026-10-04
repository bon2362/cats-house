from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.genealogy.write_service import rename_person

router = APIRouter()


class PersonUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=512)


class PersonUpdateResponse(BaseModel):
    id: UUID
    display_name: str


@router.patch("/admin/people/{person_id}", response_model=PersonUpdateResponse)
def update_person(
    person_id: UUID,
    body: PersonUpdateRequest,
    owner: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> PersonUpdateResponse:
    try:
        person = rename_person(session, person_id, body.display_name, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return PersonUpdateResponse(id=person.id, display_name=person.display_name)
