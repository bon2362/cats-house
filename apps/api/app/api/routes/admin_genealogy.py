from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.genealogy.write_service import (
    archive_person,
    create_parent_child_link,
    create_person_event,
    create_union,
    rename_person,
)

router = APIRouter()


class PersonUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=512)


class PersonUpdateResponse(BaseModel):
    id: UUID
    display_name: str


class PersonEventCreateRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    date_text: str | None = Field(default=None, max_length=255)


class PersonEventCreateResponse(BaseModel):
    id: UUID
    event_type: str
    date_text: str | None


class UnionCreateRequest(BaseModel):
    partner_one_id: UUID
    partner_two_id: UUID
    union_type: str | None = Field(default=None, max_length=64)


class UnionCreateResponse(BaseModel):
    id: UUID


class ParentChildCreateRequest(BaseModel):
    parent_id: UUID
    child_id: UUID
    relationship_type: str = Field(default="biological", min_length=1, max_length=32)


class ParentChildCreateResponse(BaseModel):
    id: UUID


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


@router.post("/admin/people/{person_id}/archive", status_code=204)
def archive(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    try:
        archive_person(session, person_id, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/admin/people/{person_id}/events", response_model=PersonEventCreateResponse, status_code=201)
def create_event(
    person_id: UUID,
    body: PersonEventCreateRequest,
    owner: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> PersonEventCreateResponse:
    try:
        event = create_person_event(session, person_id, body.event_type, body.date_text, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return PersonEventCreateResponse(id=event.id, event_type=event.event_type, date_text=event.date_text)


@router.post("/admin/unions", response_model=UnionCreateResponse, status_code=201)
def create_family_union(
    body: UnionCreateRequest,
    owner: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> UnionCreateResponse:
    try:
        union = create_union(session, body.partner_one_id, body.partner_two_id, body.union_type, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return UnionCreateResponse(id=union.id)


@router.post("/admin/parent-links", response_model=ParentChildCreateResponse, status_code=201)
def create_parent_link(
    body: ParentChildCreateRequest,
    owner: OwnerSession = Depends(require_owner),
    session: Session = Depends(get_session),
) -> ParentChildCreateResponse:
    try:
        link = create_parent_child_link(session, body.parent_id, body.child_id, body.relationship_type, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ParentChildCreateResponse(id=link.id)
