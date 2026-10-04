from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.read_service import get_public_person, public_events, public_family, public_person_media, search_people

router = APIRouter()


class PersonSearchResponse(BaseModel):
    id: UUID
    display_name: str


class EventResponse(BaseModel):
    event_type: str
    date_text: str | None


class PublicMediaResponse(BaseModel):
    id: UUID
    original_filename: str
    url: str


class PersonResponse(PersonSearchResponse):
    biography: str | None
    events: list[EventResponse]
    parents: list[PersonSearchResponse]
    children: list[PersonSearchResponse]
    partners: list[PersonSearchResponse]
    media: list[PublicMediaResponse]


@router.get("/people", response_model=list[PersonSearchResponse])
def search(query: str = Query(min_length=1), session: Session = Depends(get_session)) -> list[PersonSearchResponse]:
    return [PersonSearchResponse(id=person.id, display_name=person.display_name) for person in search_people(session, query)]


@router.get("/people/{person_id}", response_model=PersonResponse)
def get_person(person_id: UUID, request: Request, session: Session = Depends(get_session)) -> PersonResponse:
    person = get_public_person(session, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    parents, children, partners = public_family(session, person.id)
    return PersonResponse(
        id=person.id,
        display_name=person.display_name,
        biography=person.biography,
        events=[EventResponse(event_type=event.event_type, date_text=event.date_text) for event in public_events(session, person.id)],
        parents=[PersonSearchResponse(id=related.id, display_name=related.display_name) for related in parents],
        children=[PersonSearchResponse(id=related.id, display_name=related.display_name) for related in children],
        partners=[PersonSearchResponse(id=related.id, display_name=related.display_name) for related in partners],
        media=[
            PublicMediaResponse(
                id=item.id,
                original_filename=item.original_filename,
                url=request.app.state.media_storage.public_url(item.storage_key),
            )
            for item in public_person_media(session, person.id)
        ],
    )
