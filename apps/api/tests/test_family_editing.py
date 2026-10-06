from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.genealogy.dates import DatePoint, DateValue
from app.genealogy.family_editing import move_child, remove_parent, remove_union, replace_parent, update_union
from app.genealogy.person_editing import LifeEventInput, PersonEdit
from app.genealogy.relatives import RelativeError, family_overview
from app.models.genealogy import Base, ChangeLog, Event, ParentChild, Person, Union

OWNER = "owner@example.test"


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def person(session, given, sex=None):
    record = Person(import_run_id=None, source_uid=None, display_name=given, given_name=given, sex=sex)
    session.add(record)
    session.flush()
    return record


def union(session, first, second):
    record = Union(import_run_id=None, partner_one_id=first.id, partner_two_id=second.id if second else None, union_type="marriage")
    session.add(record)
    session.flush()
    return record


def link(session, parent, child, family=None):
    session.add(ParentChild(parent_id=parent.id, child_id=child.id, union_id=family.id if family else None, relationship_type="biological"))
    session.flush()


def parents_of(session, child):
    return {(record.parent_id, record.union_id) for record in session.query(ParentChild).filter_by(child_id=child.id)}


def new_person(given, sex=None):
    return PersonEdit(surname=None, given_name=given, patronymic=None, birth_surname=None, sex=sex, birth=None, death_status="unknown", death=None)


@pytest.fixture
def vakhrameev(session):
    """Катя recorded as a child of Наталья + Александр; her real father Виктор is missing."""
    katya, natalia, alexander = person(session, "Катя", "F"), person(session, "Наталья", "F"), person(session, "Александр", "M")
    marriage = union(session, natalia, alexander)
    link(session, natalia, katya, marriage)
    link(session, alexander, katya, marriage)
    session.commit()
    return {"katya": katya, "natalia": natalia, "alexander": alexander, "marriage": marriage}


def test_replacing_the_father_puts_the_child_into_the_mothers_union_with_the_new_father(session, vakhrameev):
    family = vakhrameev

    result = replace_parent(session, family["katya"].id, family["alexander"].id, new_person("Виктор", "M"), None, OWNER)

    viktor = session.get(Person, result["person"]["id"])
    first = session.query(Union).filter(Union.id != family["marriage"].id).one()
    assert {first.partner_one_id, first.partner_two_id} == {family["natalia"].id, viktor.id}
    assert parents_of(session, family["katya"]) == {(family["natalia"].id, first.id), (viktor.id, first.id)}
    assert session.get(Union, family["marriage"].id) is not None
    deleted = [entry for entry in session.query(ChangeLog).filter_by(entity_type="parent_child") if entry.after == {}]
    assert [entry.before["parent_id"] for entry in deleted] == [str(family["alexander"].id)]


def test_replacing_the_only_parent_links_the_new_one_without_a_union(session):
    child, mother = person(session, "Иван"), person(session, "Анна")
    link(session, mother, child)
    session.commit()

    result = replace_parent(session, child.id, mother.id, new_person("Ольга"), None, OWNER)

    assert parents_of(session, child) == {(session.get(Person, result["person"]["id"]).id, None)}


@pytest.mark.parametrize(("setup", "message"), [("not_parent", "не записан родителем"), ("already", "уже записан как родитель"), ("descendant", "потомка человека его родителем"), ("self", "самим собой")])
def test_replace_refusals_change_nothing(session, vakhrameev, setup, message):
    family = vakhrameev
    old, candidate = family["alexander"].id, person(session, "Пётр").id
    if setup == "not_parent":
        old = candidate
    if setup == "already":
        candidate = family["natalia"].id
    if setup == "descendant":
        grandchild = person(session, "Внук")
        link(session, family["katya"], grandchild)
        candidate = grandchild.id
    if setup == "self":
        candidate = family["katya"].id
    session.commit()
    before = parents_of(session, family["katya"])

    with pytest.raises(RelativeError, match=message):
        replace_parent(session, family["katya"].id, old, None, candidate, OWNER)
    assert parents_of(session, family["katya"]) == before


def test_removing_a_parent_detaches_the_child_from_that_union(session, vakhrameev):
    family = vakhrameev

    remove_parent(session, family["katya"].id, family["alexander"].id, OWNER)

    assert parents_of(session, family["katya"]) == {(family["natalia"].id, None)}
    assert session.get(Person, family["alexander"].id) is not None


def test_removing_someone_who_is_not_a_parent_is_refused(session, vakhrameev):
    with pytest.raises(RelativeError, match="не записан родителем"):
        remove_parent(session, vakhrameev["katya"].id, person(session, "Пётр").id, OWNER)


def test_moving_a_child_into_another_union_changes_the_other_parent(session, vakhrameev):
    family = vakhrameev
    viktor = person(session, "Виктор", "M")
    first = union(session, family["natalia"], viktor)
    session.commit()

    move_child(session, family["natalia"].id, family["katya"].id, first.id, OWNER)

    assert parents_of(session, family["katya"]) == {(family["natalia"].id, first.id), (viktor.id, first.id)}


def test_moving_a_child_to_an_unknown_other_parent_leaves_one_parent(session, vakhrameev):
    family = vakhrameev

    move_child(session, family["natalia"].id, family["katya"].id, None, OWNER)

    assert parents_of(session, family["katya"]) == {(family["natalia"].id, None)}


@pytest.mark.parametrize(("setup", "message"), [("not_child", "не записан ребёнком"), ("foreign", "не принадлежит этому человеку"), ("partner_is_child", "не может быть ребёнком этой пары")])
def test_move_refusals(session, vakhrameev, setup, message):
    family = vakhrameev
    child, target = family["katya"], family["marriage"].id
    if setup == "not_child":
        child = person(session, "Пётр")
    if setup == "foreign":
        target = union(session, family["alexander"], person(session, "Ольга")).id
    if setup == "partner_is_child":
        target = union(session, family["natalia"], family["katya"]).id
    session.commit()

    with pytest.raises(RelativeError, match=message):
        move_child(session, family["natalia"].id, child.id, target, OWNER)


def test_union_marriage_and_divorce_are_events_on_the_union(session, vakhrameev):
    family = vakhrameev

    view = update_union(session, family["marriage"].id, LifeEventInput(DateValue("exact", DatePoint(1975, 6)), "Москва"), True, DateValue("about", DatePoint(1990)), OWNER)

    assert view["marriage"] == {"date": {"qualifier": "exact", "year": 1975, "month": 6, "day": None, "end": None}, "date_text": "JUN 1975", "place": "Москва"}
    assert view["divorce"]["date_text"] == "ABT 1990"
    assert sorted(event.event_type for event in session.query(Event).filter_by(union_id=family["marriage"].id)) == ["DIV", "MARR"]

    view = update_union(session, family["marriage"].id, LifeEventInput(None, "  "), False, None, OWNER)

    assert view["marriage"] is None and view["divorce"] is None
    assert session.query(Event).filter_by(union_id=family["marriage"].id).count() == 0
    assert session.query(ChangeLog).filter_by(entity_type="union").count() == 2


def test_duplicate_union_events_block_the_save(session, vakhrameev):
    session.add_all([Event(union_id=vakhrameev["marriage"].id, event_type="MARR"), Event(union_id=vakhrameev["marriage"].id, event_type="MARR")])
    session.commit()

    with pytest.raises(RelativeError, match="несколько событий брака"):
        update_union(session, vakhrameev["marriage"].id, None, False, None, OWNER)


def test_a_union_with_children_cannot_be_removed_but_an_empty_one_can(session, vakhrameev):
    family = vakhrameev
    with pytest.raises(RelativeError, match="В союзе есть дети"):
        remove_union(session, family["marriage"].id, OWNER)

    empty = union(session, family["natalia"], person(session, "Олег"))
    session.add(Event(union_id=empty.id, event_type="MARR", date_text="1990"))
    session.commit()
    remove_union(session, empty.id, OWNER)

    assert session.get(Union, empty.id) is None
    assert session.query(Event).filter_by(union_id=empty.id).count() == 0


def test_missing_union_is_a_lookup_error(session):
    with pytest.raises(LookupError, match="Союз не найден"):
        remove_union(session, uuid4(), OWNER)


def test_family_overview_shows_union_details_and_children(session, vakhrameev):
    family = vakhrameev
    single = person(session, "Сын")
    link(session, family["natalia"], single)
    session.add(Event(union_id=family["marriage"].id, event_type="DIV", date_text="1990", date_qualifier="exact", date_lower=date(1990, 1, 1), date_upper=date(1990, 12, 31)))
    session.commit()

    overview = family_overview(session, family["natalia"].id)

    [details] = overview["unions"]
    assert details["partner"]["display_name"] == "Александр" and details["marriage"] is None
    assert details["divorce"] == {"date": {"qualifier": "exact", "year": 1990, "month": None, "day": None, "end": None}, "date_text": "1990"}
    assert details["children"] == [{"id": str(family["katya"].id), "display_name": "Катя", "other_parents": [{"id": str(family["alexander"].id), "display_name": "Александр"}]}]
    assert overview["children_without_union"] == [{"id": str(single.id), "display_name": "Сын", "other_parents": []}]


def test_an_unparsed_marriage_date_survives_marking_a_divorce(session, vakhrameev):
    session.add(Event(union_id=vakhrameev["marriage"].id, event_type="MARR", date_text="весной 1975"))
    session.commit()

    view = update_union(session, vakhrameev["marriage"].id, LifeEventInput(None, None, keep_date_text=True), True, None, OWNER)

    assert view["marriage"]["date_text"] == "весной 1975"
    assert view["divorce"] == {"date": None, "date_text": None}


def test_a_child_without_a_union_lists_the_other_recorded_parent(session, vakhrameev):
    family = vakhrameev
    other_child, father = person(session, "Олег"), person(session, "Пётр")
    link(session, family["natalia"], other_child)
    link(session, father, other_child)
    session.commit()

    [entry] = family_overview(session, family["natalia"].id)["children_without_union"]

    assert entry["other_parents"] == [{"id": str(father.id), "display_name": "Пётр"}]


def test_an_unparsed_divorce_date_survives_editing_the_marriage(session, vakhrameev):
    session.add(Event(union_id=vakhrameev["marriage"].id, event_type="DIV", date_text="после войны"))
    session.commit()

    view = update_union(session, vakhrameev["marriage"].id, LifeEventInput(None, "Москва"), True, None, OWNER, divorce_date_text_keep=True)

    assert view["divorce"]["date_text"] == "после войны"
