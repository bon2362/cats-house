from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.genealogy.person_editing import LifeEventInput, PersonEdit, PersonEditError
from app.genealogy.relatives import RelativeError, add_relative, family_overview, find_similar
from app.models.genealogy import Base, ChangeLog, ParentChild, Person, Union

OWNER = "owner@example.test"


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


def person(session, given, surname=None, birth_surname=None, archived=False):
    record = Person(import_run_id=None, source_uid=None, display_name=" ".join(part for part in (given, surname) if part), given_name=given, surname=surname, birth_surname=birth_surname, is_archived=archived)
    session.add(record)
    session.flush()
    return record


def link(session, parent, child, union=None):
    session.add(ParentChild(parent_id=parent.id, child_id=child.id, union_id=union.id if union else None, relationship_type="biological"))
    session.flush()


def union(session, first, second):
    record = Union(import_run_id=None, partner_one_id=first.id, partner_two_id=second.id if second else None, union_type="marriage")
    session.add(record)
    session.flush()
    return record


def new_person(given, surname=None, sex=None) -> PersonEdit:
    return PersonEdit(surname=surname, given_name=given, patronymic=None, birth_surname=None, sex=sex, birth=None, death_status="unknown", death=None)


def test_family_overview_lists_parents_unions_and_what_can_be_added(session):
    mother, father, child, wife = person(session, "Анна"), person(session, "Пётр"), person(session, "Иван"), person(session, "Мария")
    parents = union(session, mother, father)
    link(session, mother, child, parents)
    link(session, father, child, parents)
    marriage = union(session, child, wife)
    lonely = union(session, child, None)
    session.commit()

    overview = family_overview(session, child.id)

    assert sorted(item["display_name"] for item in overview["parents"]) == ["Анна", "Пётр"]
    assert overview["unions"] == [
        {"union_id": str(item.id), "partner": {"id": str(wife.id), "display_name": "Мария"} if item is marriage else None}
        for item in sorted([marriage, lonely], key=lambda record: record.id)
    ]
    assert (overview["can_add_parent"], overview["can_add_sibling"]) == (False, True)
    assert family_overview(session, wife.id)["can_add_sibling"] is False


def test_family_overview_of_a_missing_person_is_a_lookup_error(session):
    with pytest.raises(LookupError):
        family_overview(session, uuid4())


def test_similar_people_match_given_name_and_any_surname_including_hidden(session):
    by_surname = person(session, "Анна", "Иванова")
    by_birth = person(session, "Анна", "Петрова", birth_surname="Иванова")
    person(session, "Анна", "Ёлкина", archived=True)
    person(session, "Мария", "Иванова")
    person(session, "Анна", "Смирнова")
    session.commit()

    found = find_similar(session, given_name=" анна ", surname="ИВАНОВА", birth_surname="")
    assert sorted(item["id"] for item in found) == sorted([str(by_surname.id), str(by_birth.id)])
    assert [item["is_archived"] for item in find_similar(session, given_name="Анна", surname="Елкина", birth_surname="")] == [True]
    assert find_similar(session, given_name="Анна", surname="", birth_surname="") == []
    assert find_similar(session, given_name="", surname="Иванова", birth_surname="") == []


def test_similar_people_are_limited_to_five(session):
    for _ in range(7):
        person(session, "Анна", "Иванова")
    session.commit()

    assert len(find_similar(session, given_name="Анна", surname="Иванова", birth_surname="")) == 5


def parents_of(session, child):
    return {(record.parent_id, record.union_id) for record in session.query(ParentChild).filter_by(child_id=child.id)}


def test_adds_a_new_spouse_with_a_logged_union(session):
    anchor = person(session, "Пётр")
    session.commit()

    result = add_relative(session, anchor.id, "spouse", new_person("Мария", "Иванова", "F"), None, None, OWNER)

    assert result["created"] is True and result["person"]["display_name"] == "Мария Иванова"
    spouse = session.get(Person, result["person"]["id"])
    assert spouse.import_run_id is None and spouse.source_uid is None
    marriage = session.query(Union).one()
    assert {marriage.partner_one_id, marriage.partner_two_id} == {anchor.id, spouse.id} and marriage.union_type == "marriage"
    assert sorted(entry.entity_type for entry in session.query(ChangeLog)) == ["person", "union"]


def test_a_second_union_with_the_same_person_is_refused(session):
    anchor, wife = person(session, "Пётр"), person(session, "Мария")
    union(session, wife, anchor)
    session.commit()

    with pytest.raises(RelativeError, match="уже в союзе"):
        add_relative(session, anchor.id, "spouse", None, wife.id, None, OWNER)


def test_child_of_a_chosen_union_gets_both_parents(session):
    anchor, wife = person(session, "Пётр"), person(session, "Мария")
    marriage = union(session, anchor, wife)
    session.commit()

    result = add_relative(session, anchor.id, "child", new_person("Иван"), None, marriage.id, OWNER)

    child = session.get(Person, result["person"]["id"])
    assert parents_of(session, child) == {(anchor.id, marriage.id), (wife.id, marriage.id)}


def test_child_with_an_unknown_other_parent_is_linked_to_the_person_only(session):
    anchor = person(session, "Пётр")
    session.commit()

    child = session.get(Person, add_relative(session, anchor.id, "child", new_person("Иван"), None, None, OWNER)["person"]["id"])

    assert parents_of(session, child) == {(anchor.id, None)}


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("ancestor", "предка человека его ребёнком"),
        ("already", "уже записан как ребёнок"),
        ("two_parents", "уже есть родители"),
        ("foreign_union", "не принадлежит этому человеку"),
    ],
)
def test_child_refusals(session, setup, message):
    anchor, wife, other = person(session, "Пётр"), person(session, "Мария"), person(session, "Олег")
    marriage = union(session, anchor, wife)
    candidate = person(session, "Иван")
    chosen_union = marriage.id
    if setup == "ancestor":
        link(session, candidate, anchor)
    if setup == "already":
        link(session, anchor, candidate)
    if setup == "two_parents":
        link(session, other, candidate)
        link(session, person(session, "Ольга"), candidate)
    if setup == "foreign_union":
        chosen_union = union(session, wife, other).id
    session.commit()

    with pytest.raises(RelativeError, match=message):
        add_relative(session, anchor.id, "child", None, candidate.id, chosen_union, OWNER)


def test_first_parent_is_linked_without_a_union(session):
    anchor = person(session, "Иван")
    session.commit()

    mother = session.get(Person, add_relative(session, anchor.id, "parent", new_person("Анна"), None, None, OWNER)["person"]["id"])

    assert parents_of(session, anchor) == {(mother.id, None)}


def test_second_parent_joins_the_first_in_a_union_and_only_this_child_moves(session):
    anchor, sibling, mother = person(session, "Иван"), person(session, "Ольга"), person(session, "Анна")
    link(session, mother, anchor)
    link(session, mother, sibling)
    session.commit()

    father = session.get(Person, add_relative(session, anchor.id, "parent", new_person("Пётр"), None, None, OWNER)["person"]["id"])

    marriage = session.query(Union).one()
    assert {marriage.partner_one_id, marriage.partner_two_id} == {mother.id, father.id}
    assert parents_of(session, anchor) == {(mother.id, marriage.id), (father.id, marriage.id)}
    assert parents_of(session, sibling) == {(mother.id, None)}
    moved = [entry for entry in session.query(ChangeLog).filter_by(entity_type="parent_child") if entry.before]
    assert [(entry.before, entry.after) for entry in moved] == [({"union_id": None}, {"union_id": str(marriage.id)})]


def test_second_parent_reuses_an_existing_union(session):
    anchor, mother, father = person(session, "Иван"), person(session, "Анна"), person(session, "Пётр")
    existing = union(session, father, mother)
    link(session, mother, anchor)
    session.commit()

    add_relative(session, anchor.id, "parent", None, father.id, None, OWNER)

    assert session.query(Union).count() == 1
    assert parents_of(session, anchor) == {(mother.id, existing.id), (father.id, existing.id)}


@pytest.mark.parametrize(("setup", "message"), [("two", "уже два родителя"), ("already", "уже записан как родитель"), ("descendant", "потомка человека его родителем")])
def test_parent_refusals(session, setup, message):
    anchor, candidate = person(session, "Иван"), person(session, "Пётр")
    if setup == "two":
        link(session, person(session, "Анна"), anchor)
        link(session, person(session, "Олег"), anchor)
    if setup == "already":
        link(session, candidate, anchor)
    if setup == "descendant":
        grandchild = person(session, "Внук")
        link(session, anchor, grandchild)
        link(session, grandchild, candidate)
    session.commit()

    with pytest.raises(RelativeError, match=message):
        add_relative(session, anchor.id, "parent", None, candidate.id, None, OWNER)


def test_sibling_shares_the_parents_through_the_same_union(session):
    anchor, mother, father = person(session, "Иван"), person(session, "Анна"), person(session, "Пётр")
    marriage = union(session, mother, father)
    link(session, mother, anchor, marriage)
    link(session, father, anchor, marriage)
    session.commit()

    sister = session.get(Person, add_relative(session, anchor.id, "sibling", new_person("Ольга"), None, None, OWNER)["person"]["id"])

    assert parents_of(session, sister) == {(mother.id, marriage.id), (father.id, marriage.id)}


@pytest.mark.parametrize(("setup", "message"), [("orphan", "не указаны родители"), ("has_parents", "уже есть родители"), ("descendant", "предка или потомка")])
def test_sibling_refusals(session, setup, message):
    anchor, candidate = person(session, "Иван"), person(session, "Ольга")
    if setup != "orphan":
        link(session, person(session, "Анна"), anchor)
    if setup == "has_parents":
        link(session, person(session, "Олег"), candidate)
    if setup == "descendant":
        link(session, anchor, candidate)
    session.commit()

    with pytest.raises(RelativeError, match=message):
        add_relative(session, anchor.id, "sibling", None, candidate.id, None, OWNER)


def test_general_refusals(session):
    anchor = person(session, "Иван")
    session.commit()

    with pytest.raises(RelativeError, match="самим собой"):
        add_relative(session, anchor.id, "spouse", None, anchor.id, None, OWNER)
    with pytest.raises(RelativeError, match="нового или существующего"):
        add_relative(session, anchor.id, "spouse", None, None, None, OWNER)
    with pytest.raises(RelativeError, match="нового или существующего"):
        add_relative(session, anchor.id, "spouse", new_person("Мария"), anchor.id, None, OWNER)
    with pytest.raises(LookupError, match="Выбранный человек не найден"):
        add_relative(session, anchor.id, "spouse", None, uuid4(), None, OWNER)
    with pytest.raises(LookupError):
        add_relative(session, uuid4(), "spouse", new_person("Мария"), None, None, OWNER)


def test_a_refused_add_leaves_nothing_behind(session):
    anchor = person(session, "Иван")
    link(session, person(session, "Анна"), anchor)
    link(session, person(session, "Олег"), anchor)
    session.commit()
    people_before = session.query(Person).count()

    with pytest.raises(RelativeError):
        add_relative(session, anchor.id, "parent", new_person("Пётр"), None, None, OWNER)

    assert session.query(Person).count() == people_before
    assert session.query(ChangeLog).count() == 0


def test_a_new_relative_with_an_invalid_form_is_refused(session):
    anchor = person(session, "Иван")
    session.commit()

    with pytest.raises(PersonEditError, match="Укажите имя или фамилию"):
        add_relative(session, anchor.id, "spouse", new_person(" "), None, None, OWNER)
    assert session.query(Person).count() == 1


def test_hidden_people_can_be_linked(session):
    anchor, hidden = person(session, "Иван"), person(session, "Мария", archived=True)
    session.commit()

    result = add_relative(session, anchor.id, "spouse", None, hidden.id, None, OWNER)

    assert result["created"] is False and result["person"]["is_archived"] is True


def test_the_partner_of_the_chosen_union_cannot_become_the_child(session):
    anchor, wife = person(session, "Пётр"), person(session, "Мария")
    marriage = union(session, anchor, wife)
    session.commit()

    with pytest.raises(RelativeError, match="не может быть ребёнком этой пары"):
        add_relative(session, anchor.id, "child", None, wife.id, marriage.id, OWNER)
    assert session.query(ParentChild).count() == 0


def test_an_ancestor_of_the_other_parent_cannot_become_the_child(session):
    anchor, wife, mother_in_law = person(session, "Пётр"), person(session, "Мария"), person(session, "Анна")
    marriage = union(session, anchor, wife)
    link(session, mother_in_law, wife)
    session.commit()

    with pytest.raises(RelativeError, match="предка человека его ребёнком"):
        add_relative(session, anchor.id, "child", None, mother_in_law.id, marriage.id, OWNER)


def test_an_existing_child_of_the_other_parent_is_moved_into_the_chosen_union(session):
    anchor, wife, child = person(session, "Пётр"), person(session, "Мария"), person(session, "Иван")
    marriage = union(session, anchor, wife)
    link(session, wife, child)
    session.commit()

    add_relative(session, anchor.id, "child", None, child.id, marriage.id, OWNER)

    assert parents_of(session, child) == {(anchor.id, marriage.id), (wife.id, marriage.id)}
    moved = [entry for entry in session.query(ChangeLog).filter_by(entity_type="parent_child") if entry.before]
    assert [(entry.before, entry.after) for entry in moved] == [({"union_id": None}, {"union_id": str(marriage.id)})]
