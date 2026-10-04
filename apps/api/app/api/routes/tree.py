from collections import deque
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models.genealogy import ParentChild, Person

router = APIRouter()


class TreePersonResponse(BaseModel):
    id: UUID
    display_name: str


class TreeResponse(BaseModel):
    people: list[TreePersonResponse]


@router.get("/tree/{person_id}", response_model=TreeResponse)
def get_tree(
    person_id: UUID,
    mode: str = Query(pattern="^(descendants)$"),
    depth: int = Query(default=2, ge=0, le=5),
    session: Session = Depends(get_session),
) -> TreeResponse:
    root = session.scalar(select(Person).where(Person.id == person_id, Person.is_archived.is_(False)))
    if root is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    queue = deque([(root.id, 0)])
    seen = {root.id}
    people = [root]
    while queue:
        parent_id, level = queue.popleft()
        if level >= depth:
            continue
        child_ids = session.scalars(select(ParentChild.child_id).where(ParentChild.parent_id == parent_id)).all()
        children = session.scalars(select(Person).where(Person.id.in_(child_ids), Person.is_archived.is_(False))).all()
        for child in children:
            if child.id not in seen:
                seen.add(child.id)
                people.append(child)
                queue.append((child.id, level + 1))
    return TreeResponse(people=[TreePersonResponse(id=person.id, display_name=person.display_name) for person in people])
