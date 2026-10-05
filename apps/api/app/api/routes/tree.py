from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.tree_service import build_tree_graph

router = APIRouter()


class TreePersonResponse(BaseModel):
    id: UUID
    display_name: str | None
    sex: str | None
    birth_label: str | None
    death_label: str | None
    is_hidden: bool
    is_root: bool


class TreeLinkResponse(BaseModel):
    parent_id: UUID
    child_id: UUID


class TreeParentLinkResponse(TreeLinkResponse):
    relationship_type: str


class TreeUnionResponse(BaseModel):
    id: UUID
    partner_one_id: UUID | None
    partner_two_id: UUID | None
    union_type: str | None


class TreeResponse(BaseModel):
    people: list[TreePersonResponse]
    unions: list[TreeUnionResponse]
    parent_links: list[TreeParentLinkResponse]
    partner_links: list[TreeUnionResponse]
    links: list[TreeLinkResponse]


@router.get("/tree/{person_id}", response_model=TreeResponse)
def get_tree(
    person_id: UUID,
    mode: str = Query(pattern="^(ancestors|descendants|mixed)$"),
    depth: int = Query(default=2, ge=0, le=5),
    session: Session = Depends(get_session),
) -> TreeResponse:
    graph = build_tree_graph(session, person_id, mode, depth)
    if graph is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    return TreeResponse(
        people=[TreePersonResponse(**person.__dict__) for person in graph.people],
        unions=[TreeUnionResponse(**union.__dict__) for union in graph.unions],
        parent_links=[TreeParentLinkResponse(**link.__dict__) for link in graph.parent_links],
        partner_links=[TreeUnionResponse(**union.__dict__) for union in graph.partner_links],
        links=[TreeLinkResponse(parent_id=link.parent_id, child_id=link.child_id) for link in graph.parent_links],
    )
