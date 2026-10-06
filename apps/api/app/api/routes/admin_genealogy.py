from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import OwnerSession, require_owner
from app.db.session import get_session
from app.genealogy.dates import DateError, DatePoint, DateValue
from app.genealogy.person_editing import LifeEventInput, PersonEdit, PersonEditError, editable_person, owner_search, update_person
from app.genealogy.relatives import add_relative, family_overview, find_similar
from app.genealogy.write_service import archive_person, create_parent_child_link, create_person_event, create_union, restore_person

router = APIRouter()


class DatePointBody(BaseModel):
    year: int
    month: int | None = None
    day: int | None = None


class DateBody(DatePointBody):
    qualifier: Literal["exact", "about", "before", "after", "between"]
    end: DatePointBody | None = None


class LifeEventBody(BaseModel):
    date: DateBody | None = None
    place: str | None = None
    date_text_keep: bool = False


class DeathBody(LifeEventBody):
    status: Literal["unknown", "deceased"]


class PersonEditBody(BaseModel):
    surname: str | None = None
    given_name: str | None = None
    patronymic: str | None = None
    birth_surname: str | None = None
    sex: Literal["M", "F"] | None = None
    birth: LifeEventBody | None = None
    death: DeathBody


def _date(body: DateBody | None) -> DateValue | None:
    if body is None:
        return None
    end = DatePoint(body.end.year, body.end.month, body.end.day) if body.end else None
    return DateValue(body.qualifier, DatePoint(body.year, body.month, body.day), end)


def _life(body: LifeEventBody | None) -> LifeEventInput | None:
    return None if body is None else LifeEventInput(_date(body.date), body.place, body.date_text_keep)


def _edit(body: "PersonEditBody") -> PersonEdit:
    return PersonEdit(
        surname=body.surname, given_name=body.given_name, patronymic=body.patronymic, birth_surname=body.birth_surname,
        sex=body.sex, birth=_life(body.birth), death_status=body.death.status, death=_life(body.death),
    )


class RelativeBody(BaseModel):
    relation: Literal["child", "parent", "spouse", "sibling"]
    person: PersonEditBody | None = None
    existing_id: UUID | None = None
    union_id: UUID | None = None


@router.get("/admin/people/similar")
def similar_people(given_name: str = Query(default=""), surname: str = Query(default=""), birth_surname: str = Query(default=""), owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> list[dict]:
    return find_similar(session, given_name, surname, birth_surname)


@router.get("/admin/people/{person_id}/family")
def person_family(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return family_overview(session, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/admin/people/{person_id}/relatives", status_code=201)
def add_person_relative(person_id: UUID, body: RelativeBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return add_relative(session, person_id, body.relation, _edit(body.person) if body.person else None, body.existing_id, body.union_id, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (PersonEditError, DateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/admin/people")
def search_people_for_owner(query: str = Query(default=""), owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> list[dict]:
    return owner_search(session, query)


@router.get("/admin/people/{person_id}")
def read_person_for_owner(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return editable_person(session, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/admin/people/{person_id}")
def save_person(person_id: UUID, body: PersonEditBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return update_person(session, person_id, _edit(body), owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (PersonEditError, DateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/admin/people/{person_id}/restore", status_code=204)
def restore(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    try:
        restore_person(session, person_id, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
