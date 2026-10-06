from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.genealogy.kinship import KinshipParentLink, KinshipPerson, KinshipUnion, KinshipResult, resolve_kinship
from app.genealogy.read_service import normalize_public_name
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
    relationship: TreeRelationship | None


@dataclass(frozen=True)
class TreeRelationship:
    label: str
    kind: str
    certainty: str
    reason: str


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
    union_id: UUID | None
    relationship_type: str


@dataclass(frozen=True)
class TreeRelationPath:
    person_ids: list[UUID]
    labels: list[str]
    common_ancestor_id: UUID | None


@dataclass(frozen=True)
class TreeGraph:
    people: list[TreePerson]
    unions: list[TreeUnion]
    parent_links: list[TreeParentLink]
    partner_links: list[TreeUnion]
    relation_path: TreeRelationPath | None


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

    relation_path: TreeRelationPath | None = None
    if mode == "close":
        included_ids = _close_relative_ids(session, root.id)
        people_by_id = {person.id: person for person in session.scalars(select(Person).where(Person.id.in_(included_ids))).all()}
    elif mode == "all":
        included_ids = _all_relative_ids(session, root.id)
        people_by_id = {person.id: person for person in session.scalars(select(Person).where(Person.id.in_(included_ids))).all()}
    elif mode == "mixed":
        included_ids = _mixed_relative_ids(session, root.id, depth)
        people_by_id = {person.id: person for person in session.scalars(select(Person).where(Person.id.in_(included_ids))).all()}
    elif mode == "path":
        if related_to is None:
            raise ValueError("Для режима «Как связаны» выберите второго человека.")
        target = session.scalar(select(Person).where(Person.id == related_to, Person.is_archived.is_(False)))
        if target is None:
            raise ValueError("Второй человек не найден.")
        relation_path = _shortest_relation_path(session, root.id, target.id)
        included_ids = set(relation_path.person_ids) if relation_path else {root.id, target.id}
        people_by_id = {person.id: person for person in session.scalars(select(Person).where(Person.id.in_(included_ids))).all()}
    else:
        people_by_id = {root.id: root}
        queue = deque([(root.id, 0)])
        while queue:
            current_id, level = queue.popleft()
            if level >= depth:
                continue
            related_ids: list[UUID] = []
            if mode == "descendants":
                related_ids.extend(session.scalars(select(ParentChild.child_id).where(ParentChild.parent_id == current_id)).all())
            if mode == "ancestors":
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
    if mode != "path":
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
    resolution_ids = _all_relative_ids(session, root.id)
    resolution_people_by_id = {
        person.id: person for person in session.scalars(select(Person).where(Person.id.in_(resolution_ids))).all()
    }
    resolution_parent_links = list(
        session.scalars(
            select(ParentChild).where(
                ParentChild.parent_id.in_(resolution_ids), ParentChild.child_id.in_(resolution_ids)
            )
        )
    )
    resolution_unions = [
        union
        for union in session.scalars(
            select(Union).where(or_(Union.partner_one_id.in_(resolution_ids), Union.partner_two_id.in_(resolution_ids)))
        )
        if union.partner_one_id in resolution_ids and union.partner_two_id in resolution_ids
    ]
    kinship_people = {
        person.id: KinshipPerson(
            id=person.id,
            sex=person.sex,
            is_archived=person.is_archived,
            display_name=None if person.is_archived else normalize_public_name(person.display_name),
        )
        for person in resolution_people_by_id.values()
    }
    kinship_parent_links = [
        KinshipParentLink(link.parent_id, link.child_id, link.relationship_type) for link in resolution_parent_links
    ]
    kinship_unions = [
        KinshipUnion(union.partner_one_id, union.partner_two_id)
        for union in resolution_unions
        if union.partner_one_id is not None and union.partner_two_id is not None
    ]
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
            display_name=None if person.is_archived else normalize_public_name(person.display_name),
            sex=None if person.is_archived else person.sex,
            birth_label=None if person.is_archived else life_labels.get(person.id, {}).get("birth"),
            death_label=None if person.is_archived else life_labels.get(person.id, {}).get("death"),
            is_hidden=person.is_archived,
            is_root=person.id == root.id,
            relationship=(
                None
                if person.id == root.id
                else _tree_relationship(
                    resolve_kinship(root.id, person.id, kinship_people, kinship_parent_links, kinship_unions)
                )
            ),
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
            union_id=link.union_id,
            relationship_type=link.relationship_type,
        )
        for link in parent_links
    ]
    return TreeGraph(
        people=people,
        unions=graph_unions,
        parent_links=graph_links,
        partner_links=graph_unions,
        relation_path=relation_path,
    )


def _tree_relationship(result: KinshipResult | None) -> TreeRelationship | None:
    if result is None:
        return None
    return TreeRelationship(
        label=result.label,
        kind=result.kind,
        certainty=result.certainty,
        reason=result.reason,
    )


def _all_relative_ids(session: Session, root_id: UUID) -> set[UUID]:
    adjacency: dict[UUID, set[UUID]] = {}
    for link in session.scalars(select(ParentChild)).all():
        adjacency.setdefault(link.parent_id, set()).add(link.child_id)
        adjacency.setdefault(link.child_id, set()).add(link.parent_id)
    for union in session.scalars(select(Union)).all():
        if union.partner_one_id is not None and union.partner_two_id is not None:
            adjacency.setdefault(union.partner_one_id, set()).add(union.partner_two_id)
            adjacency.setdefault(union.partner_two_id, set()).add(union.partner_one_id)

    visited = {root_id}
    queue = deque([root_id])
    while queue:
        for related_id in adjacency.get(queue.popleft(), ()):
            if related_id not in visited:
                visited.add(related_id)
                queue.append(related_id)
    return visited


def _mixed_relative_ids(session: Session, root_id: UUID, depth: int) -> set[UUID]:
    included_ids = {root_id}
    for relation_column, person_column in (
        (ParentChild.parent_id, ParentChild.child_id),
        (ParentChild.child_id, ParentChild.parent_id),
    ):
        queue = deque([(root_id, 0)])
        while queue:
            current_id, level = queue.popleft()
            if level >= depth:
                continue
            related_ids = session.scalars(select(relation_column).where(person_column == current_id)).all()
            for related_id in related_ids:
                if related_id not in included_ids:
                    included_ids.add(related_id)
                    queue.append((related_id, level + 1))
    return included_ids


def _close_relative_ids(session: Session, root_id: UUID) -> set[UUID]:
    parent_ids = set(session.scalars(select(ParentChild.parent_id).where(ParentChild.child_id == root_id)).all())
    child_ids = set(session.scalars(select(ParentChild.child_id).where(ParentChild.parent_id == root_id)).all())
    sibling_ids = set()
    if parent_ids:
        sibling_ids = set(session.scalars(select(ParentChild.child_id).where(ParentChild.parent_id.in_(parent_ids))).all())
    unions = session.scalars(
        select(Union).where(or_(Union.partner_one_id == root_id, Union.partner_two_id == root_id))
    ).all()
    partner_ids = {
        partner_id
        for union in unions
        for partner_id in (union.partner_one_id, union.partner_two_id)
        if partner_id is not None and partner_id != root_id
    }
    partner_parent_ids = set()
    if partner_ids:
        partner_parent_ids = set(session.scalars(select(ParentChild.parent_id).where(ParentChild.child_id.in_(partner_ids))).all())
    return {root_id, *parent_ids, *child_ids, *sibling_ids, *partner_ids, *partner_parent_ids}


def _shortest_relation_path(session: Session, first_id: UUID, second_id: UUID) -> TreeRelationPath | None:
    adjacency: dict[UUID, list[tuple[UUID, str]]] = {}
    parent_links = session.scalars(select(ParentChild)).all()
    for link in parent_links:
        adjacency.setdefault(link.parent_id, []).append((link.child_id, "ребёнок"))
        adjacency.setdefault(link.child_id, []).append((link.parent_id, "родитель"))
    for union in session.scalars(select(Union)).all():
        if union.partner_one_id is not None and union.partner_two_id is not None:
            adjacency.setdefault(union.partner_one_id, []).append((union.partner_two_id, "партнёр"))
            adjacency.setdefault(union.partner_two_id, []).append((union.partner_one_id, "партнёр"))

    queue = deque([first_id])
    previous: dict[UUID, tuple[UUID, str] | None] = {first_id: None}
    while queue:
        current_id = queue.popleft()
        if current_id == second_id:
            break
        for next_id, label in sorted(adjacency.get(current_id, []), key=lambda item: str(item[0])):
            if next_id not in previous:
                previous[next_id] = (current_id, label)
                queue.append(next_id)
    if second_id not in previous:
        return None

    person_ids = [second_id]
    labels: list[str] = []
    current_id = second_id
    while previous[current_id] is not None:
        prior_id, label = previous[current_id]
        person_ids.append(prior_id)
        labels.append(label)
        current_id = prior_id
    person_ids.reverse()
    labels.reverse()
    return TreeRelationPath(
        person_ids=person_ids,
        labels=labels,
        common_ancestor_id=_common_ancestor(session, first_id, second_id),
    )


def _common_ancestor(session: Session, first_id: UUID, second_id: UUID) -> UUID | None:
    parents_by_child: dict[UUID, list[UUID]] = {}
    for link in session.scalars(select(ParentChild)).all():
        parents_by_child.setdefault(link.child_id, []).append(link.parent_id)

    def ancestor_distances(person_id: UUID) -> dict[UUID, int]:
        distances: dict[UUID, int] = {}
        queue = deque([(person_id, 0)])
        seen = {person_id}
        while queue:
            current_id, distance = queue.popleft()
            for parent_id in parents_by_child.get(current_id, []):
                if parent_id not in seen:
                    seen.add(parent_id)
                    distances[parent_id] = distance + 1
                    queue.append((parent_id, distance + 1))
        return distances

    first_ancestors = ancestor_distances(first_id)
    second_ancestors = ancestor_distances(second_id)
    common = set(first_ancestors) & set(second_ancestors)
    if not common:
        return None
    return min(common, key=lambda item: (max(first_ancestors[item], second_ancestors[item]), str(item)))


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
