"""Owner corrections of existing links and unions: replace/remove parents, move children, edit/remove unions."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.genealogy.dates import DateValue, build_stored_date, date_value_to_dict, parse_stored_date
from app.genealogy.person_editing import MAX_PLACE_LENGTH, LifeEventInput, PersonEdit, _clean, editable_person
from app.genealogy.relatives import RelativeError, _lineage, _log, _new_link, _new_union, _parent_ids, _parent_links, _ref, _relative_person, _union_between
from app.models.genealogy import Event, MediaLink, ParentChild, Person, Union

EVENT_WORDS = {"MARR": "брака", "DIV": "развода"}


def _link_view(link: ParentChild) -> dict:
    return {"parent_id": str(link.parent_id), "child_id": str(link.child_id), "union_id": str(link.union_id) if link.union_id else None}


def _delete_link(session: Session, link: ParentChild, owner_email: str) -> None:
    _log(session, "parent_child", link.id, owner_email, _link_view(link), {})
    session.delete(link)


def _set_union(session: Session, link: ParentChild, union_id: UUID | None, owner_email: str) -> None:
    if link.union_id == union_id:
        return
    before = str(link.union_id) if link.union_id else None
    link.union_id = union_id
    _log(session, "parent_child", link.id, owner_email, {"union_id": before}, {"union_id": str(union_id) if union_id else None})


def _union_events(session: Session, union_id: UUID, kind: str) -> list[Event]:
    return list(session.scalars(select(Event).where(Event.union_id == union_id, Event.event_type == kind).order_by(Event.id)))


def _event_view(event: Event | None, with_place: bool) -> dict | None:
    if event is None:
        return None
    view = {"date": date_value_to_dict(parse_stored_date(event.date_text)), "date_text": event.date_text}
    if with_place:
        view["place"] = event.place
    return view


def child_entry(session: Session, child: Person, anchor_id: UUID | None) -> dict:
    """A child with its other recorded parents, so the owner sees whose link a move would remove."""
    others = [parent_id for parent_id in _parent_ids(session, child.id) if parent_id != anchor_id]
    return {**_ref(child), "other_parents": [_ref(session.get(Person, parent_id)) for parent_id in others]}


def union_details(session: Session, union: Union, anchor_id: UUID | None) -> dict:
    partner_id = union.partner_two_id if union.partner_one_id == anchor_id else union.partner_one_id
    partner = session.get(Person, partner_id) if partner_id else None
    marriages, divorces = _union_events(session, union.id, "MARR"), _union_events(session, union.id, "DIV")
    children = session.scalars(
        select(Person).where(Person.id.in_(select(ParentChild.child_id).where(ParentChild.union_id == union.id))).order_by(Person.display_name)
    )
    return {
        "union_id": str(union.id),
        "partner": _ref(partner) if partner else None,
        "marriage": _event_view(marriages[0] if marriages else None, True),
        "divorce": _event_view(divorces[0] if divorces else None, False),
        "children": [child_entry(session, child, anchor_id) for child in children],
    }


def _no_media(session: Session, events: list[Event]) -> None:
    if events and session.scalar(select(func.count()).select_from(MediaLink).where(MediaLink.event_id.in_([event.id for event in events]))):
        raise RelativeError("К событиям союза привязаны материалы.")


def _write_union_event(session: Session, union: Union, kind: str, value: LifeEventInput | None, owner_email: str) -> None:
    events = _union_events(session, union.id, kind)
    if len(events) > 1:
        raise RelativeError(f"У союза несколько событий {EVENT_WORDS[kind]} — исправьте их отдельно.")
    event = events[0] if events else None
    if value is None:
        if event is not None:
            _no_media(session, [event])
            session.delete(event)
        return
    if event is None:
        event = Event(union_id=union.id, event_type=kind)
        session.add(event)
    keep_unparsed = value.keep_date_text and event.date_text and parse_stored_date(event.date_text) is None
    if not keep_unparsed:
        stored = build_stored_date(value.date) if value.date else None
        event.date_text = stored.text if stored else None
        event.date_qualifier = stored.qualifier if stored else None
        event.date_lower = stored.lower if stored else None
        event.date_upper = stored.upper if stored else None
    event.place = _clean(value.place, MAX_PLACE_LENGTH, "Место")


def _union_summary(session: Session, union: Union) -> dict:
    def summary(kind: str) -> dict | None:
        events = _union_events(session, union.id, kind)
        return {"date_text": events[0].date_text, "place": events[0].place} if events else None

    return {"marriage": summary("MARR"), "divorce": summary("DIV")}


def update_union(session: Session, union_id: UUID, marriage: LifeEventInput | None, divorced: bool, divorce_date: DateValue | None, owner_email: str, divorce_date_text_keep: bool = False) -> dict:
    union = session.get(Union, union_id)
    if union is None:
        raise LookupError("Союз не найден.")
    try:
        before = _union_summary(session, union)
        marriages = _union_events(session, union.id, "MARR")
        legacy = len(marriages) == 1 and bool(marriages[0].date_text) and parse_stored_date(marriages[0].date_text) is None
        has_marriage = marriage is not None and (
            marriage.date is not None or bool((marriage.place or "").strip()) or (marriage.keep_date_text and legacy)
        )
        _write_union_event(session, union, "MARR", marriage if has_marriage else None, owner_email)
        _write_union_event(session, union, "DIV", LifeEventInput(divorce_date, None, divorce_date_text_keep) if divorced else None, owner_email)
        session.flush()
        after = _union_summary(session, union)
        if after != before:
            _log(session, "union", union.id, owner_email, before, after)
        session.commit()
    except Exception:
        session.rollback()
        raise
    details = union_details(session, union, None)
    return {"union_id": details["union_id"], "marriage": details["marriage"], "divorce": details["divorce"]}


def remove_union(session: Session, union_id: UUID, owner_email: str) -> None:
    union = session.get(Union, union_id)
    if union is None:
        raise LookupError("Союз не найден.")
    try:
        if session.scalar(select(func.count()).select_from(ParentChild).where(ParentChild.union_id == union.id)):
            raise RelativeError("В союзе есть дети — сначала перенесите или уберите их.")
        events = list(session.scalars(select(Event).where(Event.union_id == union.id)))
        _no_media(session, events)
        for event in events:
            _log(session, "event", event.id, owner_email, {"union_id": str(union.id), "event_type": event.event_type, "date_text": event.date_text, "place": event.place}, {})
            session.delete(event)
        _log(session, "union", union.id, owner_email, {"partner_one_id": str(union.partner_one_id) if union.partner_one_id else None, "partner_two_id": str(union.partner_two_id) if union.partner_two_id else None, "union_type": union.union_type}, {})
        session.flush()
        session.delete(union)
        session.commit()
    except Exception:
        session.rollback()
        raise


def replace_parent(session: Session, child_id: UUID, parent_id: UUID, new: PersonEdit | None, existing_id: UUID | None, owner_email: str) -> dict:
    if (new is None) == (existing_id is None):
        raise RelativeError("Выберите нового или существующего человека.")
    child = session.get(Person, child_id)
    if child is None:
        raise LookupError("Человек не найден.")
    try:
        old_links = [item for item in _parent_links(session, child.id) if item.parent_id == parent_id]
        if not old_links:
            raise RelativeError("Этот человек не записан родителем.")
        relative, _created = _relative_person(session, child, new, existing_id, owner_email)
        current = _parent_ids(session, child.id)
        if relative.id in current:
            raise RelativeError("Этот человек уже записан как родитель.")
        if relative.id in _lineage(session, child.id, "down"):
            raise RelativeError("Нельзя сделать потомка человека его родителем.")
        others = [item for item in current if item != parent_id]
        for item in old_links:
            _delete_link(session, item, owner_email)
        session.flush()
        if others:
            marriage = _union_between(session, others[0], relative.id) or _new_union(session, others[0], relative.id, owner_email)
            for item in _parent_links(session, child.id):
                if item.parent_id == others[0]:
                    _set_union(session, item, marriage.id, owner_email)
            _new_link(session, relative.id, child.id, marriage.id, owner_email)
        else:
            _new_link(session, relative.id, child.id, None, owner_email)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"person": editable_person(session, relative.id)}


def remove_parent(session: Session, child_id: UUID, parent_id: UUID, owner_email: str) -> None:
    child = session.get(Person, child_id)
    if child is None:
        raise LookupError("Человек не найден.")
    try:
        links = [item for item in _parent_links(session, child.id) if item.parent_id == parent_id]
        if not links:
            raise RelativeError("Этот человек не записан родителем.")
        with_parent = set(session.scalars(select(Union.id).where(or_(Union.partner_one_id == parent_id, Union.partner_two_id == parent_id))))
        for item in links:
            _delete_link(session, item, owner_email)
        session.flush()
        for item in _parent_links(session, child.id):
            if item.union_id in with_parent:
                _set_union(session, item, None, owner_email)
        session.commit()
    except Exception:
        session.rollback()
        raise


def move_child(session: Session, parent_id: UUID, child_id: UUID, union_id: UUID | None, owner_email: str) -> None:
    anchor = session.get(Person, parent_id)
    if anchor is None:
        raise LookupError("Человек не найден.")
    child = session.get(Person, child_id)
    if child is None:
        raise LookupError("Выбранный человек не найден.")
    try:
        links = _parent_links(session, child.id)
        if not any(item.parent_id == anchor.id for item in links):
            raise RelativeError("Этот человек не записан ребёнком.")
        other = None
        if union_id is not None:
            chosen = session.get(Union, union_id)
            if chosen is None or anchor.id not in (chosen.partner_one_id, chosen.partner_two_id):
                raise RelativeError("Выбранный союз не принадлежит этому человеку.")
            other = chosen.partner_two_id if chosen.partner_one_id == anchor.id else chosen.partner_one_id
        if other is not None and other == child.id:
            raise RelativeError("Супруг из выбранного союза не может быть ребёнком этой пары.")
        if other is not None and other in _lineage(session, child.id, "down"):
            raise RelativeError("Нельзя сделать потомка человека его родителем.")
        keep = {anchor.id} | ({other} if other else set())
        for item in links:
            if item.parent_id in keep:
                _set_union(session, item, union_id, owner_email)
            else:
                _delete_link(session, item, owner_email)
        if other is not None and other not in {item.parent_id for item in links}:
            _new_link(session, other, child.id, union_id, owner_email)
        session.commit()
    except Exception:
        session.rollback()
        raise
