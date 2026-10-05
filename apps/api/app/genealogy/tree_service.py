from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.genealogy import Event, ParentChild, Person, Union


TreeMode = str


@dataclass(frozen=True)
class TreePerson:
    id: UUID
    display_name: str | None
    sex: str | None
    birth_label: str | None
    death_label: str | None
    is_hidden: bool
    is_root: bool


@dataclass(frozen=True)
class TreeUnion:
    id: UUID
    partner_one_id: UUID | None
    partner_two_id: UUID | None
    union_type: str | None


@dataclass(frozen=True)
class TreeParentLink:
    parent_id: UUID
    child_id: UUID
    relationship_type: str


@dataclass(frozen=True)
class TreeGraph:
    people: list[TreePerson]
    unions: list[TreeUnion]
    parent_links: list[TreeParentLink]
    partner_links: list[TreeUnion]


def build_tree_graph(
    session: Session,
    person_id: UUID,
    mode: TreeMode,
    depth: int,
    related_to: UUID | None = None,
) -> TreeGraph | None:
    root = session.scalar(select(Person).where(Person.id == person_id, Person.is_archived.is_(False)))
    if root is None:
        return None

    people_by_id = {root.id: root}
    queue = deque([(root.id, 0)])
    while queue:
        current_id, level = queue.popleft()
        if level >= depth:
            continue
        related_ids: list[UUID] = []
        if mode in {"descendants", "mixed"}:
            related_ids.extend(session.scalars(select(ParentChild.child_id).where(ParentChild.parent_id == current_id)).all())
        if mode in {"ancestors", "mixed"}:
            related_ids.extend(session.scalars(select(ParentChild.parent_id).where(ParentChild.child_id == current_id)).all())
        related_people = session.scalars(select(Person).where(Person.id.in_(related_ids))).all()
        for person in related_people:
            if person.id not in people_by_id:
                people_by_id[person.id] = person
                queue.append((person.id, level + 1))

    included_ids = set(people_by_id)
    unions = list(
        session.scalars(
            select(Union)
            .where(or_(Union.partner_one_id.in_(included_ids), Union.partner_two_id.in_(included_ids)))
            .order_by(Union.id)
        )
    )
    partner_ids = {
        partner_id
        for union in unions
        for partner_id in (union.partner_one_id, union.partner_two_id)
        if partner_id is not None
    }
    for partner in session.scalars(select(Person).where(Person.id.in_(partner_ids))).all():
        people_by_id.setdefault(partner.id, partner)
    included_ids = set(people_by_id)

    parent_links = list(
        session.scalars(
            select(ParentChild)
            .where(ParentChild.parent_id.in_(included_ids), ParentChild.child_id.in_(included_ids))
            .order_by(ParentChild.parent_id, ParentChild.child_id, ParentChild.relationship_type)
        )
    )
    included_unions = [
        union
        for union in unions
        if (union.partner_one_id is None or union.partner_one_id in included_ids)
        and (union.partner_two_id is None or union.partner_two_id in included_ids)
    ]
    life_labels = _life_labels(session, included_ids)
    people = [
        TreePerson(
            id=person.id,
            display_name=None if person.is_archived else person.display_name,
            sex=None if person.is_archived else person.sex,
            birth_label=None if person.is_archived else life_labels.get(person.id, {}).get("birth"),
            death_label=None if person.is_archived else life_labels.get(person.id, {}).get("death"),
            is_hidden=person.is_archived,
            is_root=person.id == root.id,
        )
        for person in sorted(people_by_id.values(), key=lambda item: str(item.id))
    ]
    graph_unions = [
        TreeUnion(
            id=union.id,
            partner_one_id=union.partner_one_id,
            partner_two_id=union.partner_two_id,
            union_type=union.union_type,
        )
        for union in included_unions
    ]
    graph_links = [
        TreeParentLink(
            parent_id=link.parent_id,
            child_id=link.child_id,
            relationship_type=link.relationship_type,
        )
        for link in parent_links
    ]
    return TreeGraph(people=people, unions=graph_unions, parent_links=graph_links, partner_links=graph_unions)


def _life_labels(session: Session, person_ids: set[UUID]) -> dict[UUID, dict[str, str]]:
    if not person_ids:
        return {}
    labels: dict[UUID, dict[str, str]] = {}
    events = session.scalars(
        select(Event).where(Event.person_id.in_(person_ids)).order_by(Event.person_id, Event.date_lower, Event.id)
    ).all()
    for event in events:
        if event.person_id is None or not event.date_text:
            continue
        if event.event_type in {"BIRT", "BIRTH"}:
            labels.setdefault(event.person_id, {}).setdefault("birth", event.date_text)
        if event.event_type in {"DEAT", "DEATH"}:
            labels.setdefault(event.person_id, {}).setdefault("death", event.date_text)
    return labels
