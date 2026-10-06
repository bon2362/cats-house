from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.genealogy.read_service import public_person_media
from app.genealogy.tree_service import TreeRelationPath, build_tree_graph

router = APIRouter()


class TreeRelationshipResponse(BaseModel):
    label: str
    kind: str
    certainty: str
    reason: str


class TreePersonResponse(BaseModel):
    id: UUID
    display_name: str | None
    sex: str | None
    birth_label: str | None
    death_label: str | None
    is_hidden: bool
    is_root: bool
    relationship: TreeRelationshipResponse | None = Field(default=None, exclude_if=lambda value: value is None)
    photo_url: str | None = None


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
    request: Request,
    mode: str = Query(pattern="^(close|ancestors|descendants|mixed|path|all)$"),
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
        people=[
            TreePersonResponse(
                **{key: value for key, value in person.__dict__.items() if key != "relationship"},
                relationship=(TreeRelationshipResponse(**person.relationship.__dict__) if person.relationship else None),
                photo_url=(
                    request.app.state.media_storage.public_url(media[0].storage_key)
                    if not person.is_hidden and (media := public_person_media(session, person.id))
                    else None
                ),
            )
            for person in graph.people
        ],
        unions=[TreeUnionResponse(**union.__dict__) for union in graph.unions],
        parent_links=[TreeParentLinkResponse(**link.__dict__) for link in graph.parent_links],
        partner_links=[TreeUnionResponse(**union.__dict__) for union in graph.partner_links],
        links=[TreeLinkResponse(parent_id=link.parent_id, child_id=link.child_id) for link in graph.parent_links],
        relation_path=TreeRelationPathResponse(**graph.relation_path.__dict__) if graph.relation_path else None,
    )
