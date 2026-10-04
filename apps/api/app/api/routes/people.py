from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.read_service import get_public_person, public_events, search_people

router = APIRouter()


class PersonSearchResponse(BaseModel):
    id: UUID
    display_name: str


class EventResponse(BaseModel):
    event_type: str
    date_text: str | None


class PersonResponse(PersonSearchResponse):
    biography: str | None
    events: list[EventResponse]


@router.get("/people", response_model=list[PersonSearchResponse])
def search(query: str = Query(min_length=1), session: Session = Depends(get_session)) -> list[PersonSearchResponse]:
    return [PersonSearchResponse(id=person.id, display_name=person.display_name) for person in search_people(session, query)]


@router.get("/people/{person_id}", response_model=PersonResponse)
def get_person(person_id: UUID, session: Session = Depends(get_session)) -> PersonResponse:
    person = get_public_person(session, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    return PersonResponse(
        id=person.id,
        display_name=person.display_name,
        biography=person.biography,
        events=[EventResponse(event_type=event.event_type, date_text=event.date_text) for event in public_events(session, person.id)],
    )
