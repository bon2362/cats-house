from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.dates import format_date_ru
from app.genealogy.read_service import featured_person, get_public_person, normalize_public_name, public_events, public_family, public_person_media, public_person_summary, public_siblings, search_people

router = APIRouter()


class PersonSearchResponse(BaseModel):
    id: UUID
    display_name: str
    birth_label: str | None = None
    death_label: str | None = None
    years: str | None = None
    is_living: bool | None = None
    parents_label: str | None = None


class EventResponse(BaseModel):
    event_type: str
    date_text: str | None
    date_label_ru: str | None = None
    place: str | None = None


class PublicMediaResponse(BaseModel):
    id: UUID
    original_filename: str
    url: str


class PersonResponse(PersonSearchResponse):
    birth_surname: str | None = None
    sex: str | None = None
    biography: str | None
    events: list[EventResponse]
    parents: list[PersonSearchResponse]
    children: list[PersonSearchResponse]
    partners: list[PersonSearchResponse]
    siblings: list[PersonSearchResponse] = []
    media: list[PublicMediaResponse]


@router.get("/people", response_model=list[PersonSearchResponse], response_model_exclude_none=True)
def search(query: str = Query(default=""), session: Session = Depends(get_session)) -> list[PersonSearchResponse]:
    return [PersonSearchResponse(**public_person_summary(session, person).__dict__) for person in search_people(session, query)]


@router.get("/people/featured", response_model=PersonSearchResponse, response_model_exclude_none=True)
def get_featured_person(session: Session = Depends(get_session)) -> PersonSearchResponse:
    person = featured_person(session)
    if person is None:
        raise HTTPException(status_code=404, detail="В семейном архиве пока нет людей.")
    return PersonSearchResponse(**public_person_summary(session, person).__dict__)


@router.get("/people/{person_id}", response_model=PersonResponse, response_model_exclude_none=True)
def get_person(person_id: UUID, request: Request, session: Session = Depends(get_session)) -> PersonResponse:
    person = get_public_person(session, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    parents, children, partners = public_family(session, person.id)
    return PersonResponse(
        **public_person_summary(session, person).__dict__,
        birth_surname=person.birth_surname,
        sex=person.sex,
        biography=person.biography,
        events=[EventResponse(event_type=event.event_type, date_text=event.date_text, date_label_ru=format_date_ru(event.date_text), place=event.place) for event in public_events(session, person.id)],
        parents=[PersonSearchResponse(id=related.id, display_name=normalize_public_name(related.display_name)) for related in parents],
        children=[PersonSearchResponse(id=related.id, display_name=normalize_public_name(related.display_name)) for related in children],
        partners=[PersonSearchResponse(id=related.id, display_name=normalize_public_name(related.display_name)) for related in partners],
        siblings=[PersonSearchResponse(id=related.id, display_name=normalize_public_name(related.display_name)) for related in public_siblings(session, person.id)],
        media=[
            PublicMediaResponse(
                id=item.id,
                original_filename=item.original_filename,
                url=request.app.state.media_storage.public_url(item.storage_key),
            )
            for item in public_person_media(session, person.id)
        ],
    )
