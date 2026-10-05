from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.tree_service import TreeRelationPath, build_tree_graph

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
    union_id: UUID | None
    relationship_type: str


class TreeUnionResponse(BaseModel):
    id: UUID
    partner_one_id: UUID | None
    partner_two_id: UUID | None
    union_type: str | None


class TreeRelationPathResponse(BaseModel):
    person_ids: list[UUID]
    labels: list[str]
    common_ancestor_id: UUID | None


class TreeResponse(BaseModel):
    people: list[TreePersonResponse]
    unions: list[TreeUnionResponse]
    parent_links: list[TreeParentLinkResponse]
    partner_links: list[TreeUnionResponse]
    links: list[TreeLinkResponse]
    relation_path: TreeRelationPathResponse | None


@router.get("/tree/{person_id}", response_model=TreeResponse)
def get_tree(
    person_id: UUID,
    mode: str = Query(pattern="^(close|ancestors|descendants|mixed|path)$"),
    depth: int = Query(default=2, ge=1, le=5),
    related_to: UUID | None = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
) -> TreeResponse:
    try:
        graph = build_tree_graph(session, person_id, mode, depth, related_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if graph is None:
        raise HTTPException(status_code=404, detail="Человек не найден.")
    return TreeResponse(
        people=[TreePersonResponse(**person.__dict__) for person in graph.people],
        unions=[TreeUnionResponse(**union.__dict__) for union in graph.unions],
        parent_links=[TreeParentLinkResponse(**link.__dict__) for link in graph.parent_links],
        partner_links=[TreeUnionResponse(**union.__dict__) for union in graph.partner_links],
        links=[TreeLinkResponse(parent_id=link.parent_id, child_id=link.child_id) for link in graph.parent_links],
        relation_path=TreeRelationPathResponse(**graph.relation_path.__dict__) if graph.relation_path else None,
    )
