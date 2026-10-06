"""Owner adds relatives: family overview, duplicate search and relation rules."""

from collections import deque
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.genealogy.person_editing import PersonEdit, PersonEditError, _assign, _snapshot, editable_person
from app.genealogy.read_service import normalize_public_name, public_person_summary
from app.models.genealogy import ChangeLog, ParentChild, Person, Union

RELATIONS = ("child", "parent", "spouse", "sibling")


class RelativeError(PersonEditError):
    """Owner-facing (Russian) reason why a relative cannot be added."""


def _ref(person: Person) -> dict:
    return {"id": str(person.id), "display_name": normalize_public_name(person.display_name)}


def _parent_links(session: Session, child_id: UUID) -> list[ParentChild]:
    return list(session.scalars(select(ParentChild).where(ParentChild.child_id == child_id).order_by(ParentChild.id)))


def _parent_ids(session: Session, child_id: UUID) -> list[UUID]:
    return list(dict.fromkeys(link.parent_id for link in _parent_links(session, child_id)))


def family_overview(session: Session, person_id: UUID) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    parents = [session.get(Person, parent_id) for parent_id in _parent_ids(session, person.id)]
    unions = session.scalars(
        select(Union).where(or_(Union.partner_one_id == person.id, Union.partner_two_id == person.id)).order_by(Union.id)
    ).all()
    overview_unions = []
    for item in unions:
        partner_id = item.partner_two_id if item.partner_one_id == person.id else item.partner_one_id
        partner = session.get(Person, partner_id) if partner_id else None
        overview_unions.append({"union_id": str(item.id), "partner": _ref(partner) if partner else None})
    return {
        "parents": [_ref(parent) for parent in parents],
        "unions": overview_unions,
        "can_add_parent": len(parents) < 2,
        "can_add_sibling": bool(parents),
    }


def _fold(value: str | None) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


def find_similar(session: Session, given_name: str, surname: str, birth_surname: str, limit: int = 5) -> list[dict]:
    given = _fold(given_name)
    surnames = {_fold(surname), _fold(birth_surname)} - {""}
    if not given or not surnames:
        return []

    def folded(column):
        return func.replace(func.lower(func.coalesce(column, "")), "ё", "е")

    statement = (
        select(Person)
        .where(folded(Person.given_name) == given, or_(folded(Person.surname).in_(surnames), folded(Person.birth_surname).in_(surnames)))
        .order_by(Person.display_name, Person.id)
        .limit(limit)
    )
    return [
        {**_ref(candidate), "years": public_person_summary(session, candidate).years, "is_archived": candidate.is_archived}
        for candidate in session.scalars(statement)
    ]


def _log(session: Session, entity_type: str, entity_id: UUID, owner_email: str, before: dict, after: dict) -> None:
    session.add(ChangeLog(entity_type=entity_type, entity_id=entity_id, owner_email=owner_email, before=before, after=after))


def _lineage(session: Session, person_id: UUID, direction: str) -> set[UUID]:
    """All ancestors ("up") or descendants ("down") of a person."""
    edges: dict[UUID, set[UUID]] = {}
    for parent_id, child_id in session.execute(select(ParentChild.parent_id, ParentChild.child_id)):
        source, target = (child_id, parent_id) if direction == "up" else (parent_id, child_id)
        edges.setdefault(source, set()).add(target)
    found: set[UUID] = set()
    queue = deque([person_id])
    while queue:
        for following in edges.get(queue.popleft(), ()):
            if following not in found:
                found.add(following)
                queue.append(following)
    return found


def _union_between(session: Session, first: UUID, second: UUID) -> Union | None:
    return session.scalar(
        select(Union)
        .where(or_((Union.partner_one_id == first) & (Union.partner_two_id == second), (Union.partner_one_id == second) & (Union.partner_two_id == first)))
        .order_by(Union.id)
        .limit(1)
    )


def _new_union(session: Session, first: UUID, second: UUID, owner_email: str) -> Union:
    record = Union(import_run_id=None, partner_one_id=first, partner_two_id=second, union_type="marriage")
    session.add(record)
    session.flush()
    _log(session, "union", record.id, owner_email, {}, {"partner_one_id": str(first), "partner_two_id": str(second), "union_type": "marriage"})
    return record


def _new_link(session: Session, parent_id: UUID, child_id: UUID, union_id: UUID | None, owner_email: str) -> None:
    record = ParentChild(parent_id=parent_id, child_id=child_id, union_id=union_id, relationship_type="biological")
    session.add(record)
    session.flush()
    _log(session, "parent_child", record.id, owner_email, {}, {"parent_id": str(parent_id), "child_id": str(child_id), "union_id": str(union_id) if union_id else None})


def _add_spouse(session: Session, anchor: Person, relative: Person, union_id: UUID | None, owner_email: str) -> None:
    if _union_between(session, anchor.id, relative.id):
        raise RelativeError("Эти люди уже в союзе.")
    _new_union(session, anchor.id, relative.id, owner_email)


def _add_child(session: Session, anchor: Person, relative: Person, union_id: UUID | None, owner_email: str) -> None:
    other = None
    if union_id is not None:
        chosen = session.get(Union, union_id)
        if chosen is None or anchor.id not in (chosen.partner_one_id, chosen.partner_two_id):
            raise RelativeError("Выбранный союз не принадлежит этому человеку.")
        other = chosen.partner_two_id if chosen.partner_one_id == anchor.id else chosen.partner_one_id
    if other is not None and relative.id == other:
        raise RelativeError("Супруг из выбранного союза не может быть ребёнком этой пары.")
    # Both future parents' ancestors are off limits, otherwise the link closes a cycle.
    ancestors = _lineage(session, anchor.id, "up")
    if other is not None:
        ancestors |= _lineage(session, other, "up")
    if relative.id in ancestors:
        raise RelativeError("Нельзя сделать предка человека его ребёнком.")
    current = set(_parent_ids(session, relative.id))
    if anchor.id in current:
        raise RelativeError("Этот человек уже записан как ребёнок.")
    new_parents = [parent for parent in (anchor.id, other) if parent is not None]
    if len(current | set(new_parents)) > 2:
        raise RelativeError("У этого человека уже есть родители.")
    for parent in new_parents:
        if parent not in current:
            _new_link(session, parent, relative.id, union_id, owner_email)
            continue
        # The other parent was already recorded: the child now belongs to the chosen union.
        for item in _parent_links(session, relative.id):
            if item.parent_id == parent and item.union_id != union_id:
                before = str(item.union_id) if item.union_id else None
                item.union_id = union_id
                _log(session, "parent_child", item.id, owner_email, {"union_id": before}, {"union_id": str(union_id)})


def _add_parent(session: Session, anchor: Person, relative: Person, union_id: UUID | None, owner_email: str) -> None:
    links = _parent_links(session, anchor.id)
    parents = list(dict.fromkeys(item.parent_id for item in links))
    if relative.id in parents:
        raise RelativeError("Этот человек уже записан как родитель.")
    if len(parents) >= 2:
        raise RelativeError("У человека уже два родителя.")
    if relative.id in _lineage(session, anchor.id, "down"):
        raise RelativeError("Нельзя сделать потомка человека его родителем.")
    if not parents:
        _new_link(session, relative.id, anchor.id, None, owner_email)
        return
    marriage = _union_between(session, parents[0], relative.id) or _new_union(session, parents[0], relative.id, owner_email)
    for item in links:
        if item.union_id != marriage.id:
            before = str(item.union_id) if item.union_id else None
            item.union_id = marriage.id
            _log(session, "parent_child", item.id, owner_email, {"union_id": before}, {"union_id": str(marriage.id)})
    _new_link(session, relative.id, anchor.id, marriage.id, owner_email)


def _add_sibling(session: Session, anchor: Person, relative: Person, union_id: UUID | None, owner_email: str) -> None:
    links = _parent_links(session, anchor.id)
    if not links:
        raise RelativeError("У человека не указаны родители — сначала добавьте родителя.")
    if relative.id in _lineage(session, anchor.id, "up") | _lineage(session, anchor.id, "down"):
        raise RelativeError("Нельзя сделать предка или потомка человека его братом или сестрой.")
    if _parent_links(session, relative.id):
        raise RelativeError("У этого человека уже есть родители.")
    seen: set[UUID] = set()
    for item in links:
        if item.parent_id not in seen:
            seen.add(item.parent_id)
            _new_link(session, item.parent_id, relative.id, item.union_id, owner_email)


_RULES = {"spouse": _add_spouse, "child": _add_child, "parent": _add_parent, "sibling": _add_sibling}


def add_relative(session: Session, person_id: UUID, relation: str, new: PersonEdit | None, existing_id: UUID | None, union_id: UUID | None, owner_email: str) -> dict:
    if relation not in _RULES:
        raise RelativeError("Неизвестный вид родства.")
    if (new is None) == (existing_id is None):
        raise RelativeError("Выберите нового или существующего человека.")
    anchor = session.get(Person, person_id)
    if anchor is None:
        raise LookupError("Человек не найден.")
    try:
        if existing_id is not None:
            relative = session.get(Person, existing_id)
            if relative is None:
                raise LookupError("Выбранный человек не найден.")
            if relative.id == anchor.id:
                raise RelativeError("Нельзя связать человека с самим собой.")
            created = False
        else:
            relative = Person(import_run_id=None, source_uid=None, display_name="")
            session.add(relative)
            session.flush()
            _assign(session, relative, new)
            session.flush()
            _log(session, "person", relative.id, owner_email, {}, _snapshot(session, relative))
            created = True
        _RULES[relation](session, anchor, relative, union_id, owner_email)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"relation": relation, "created": created, "person": editable_person(session, relative.id)}
