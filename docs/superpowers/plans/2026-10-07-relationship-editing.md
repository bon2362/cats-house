# Relationship Editing Implementation Plan (owner editor, stage 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The owner replaces and removes parents, edits unions (marriage date/place, divorce), removes empty unions, moves and removes children; kinship knows step-relations and former spouses; the tree dashes divorced unions; the person page lists siblings.

**Architecture:** No schema change: marriage and divorce are `MARR`/`DIV` events on the union. A new `family_editing.py` service holds the five operations on top of the stage-2 helpers in `relatives.py` (person resolution is extracted there and shared). `kinship.py` learns step-relations and a `divorced` flag on unions. The web app gets a replace mode in `cats-relative-adder`, a `cats-union-editor` form and a `cats-family-editor` block on the person page.

**Tech Stack:** FastAPI, SQLAlchemy 2, pytest + testcontainers; Lit, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-relationship-editing-design.md` (authority). Stage 2: `docs/superpowers/specs/2026-10-07-adding-relatives-design.md`.

## Global Constraints

- Russian user-visible text; `422` + Russian `detail` for refusals; `404` for missing people («Человек не найден.», «Выбранный человек не найден.») and unions («Союз не найден.»); `401` guests.
- Refusal texts (exact): «Этот человек не записан родителем.», «Этот человек не записан ребёнком.», «Этот человек уже записан как родитель.», «Нельзя сделать потомка человека его родителем.», «Нельзя связать человека с самим собой.», «Выберите нового или существующего человека.», «Выбранный союз не принадлежит этому человеку.», «Супруг из выбранного союза не может быть ребёнком этой пары.», «В союзе есть дети — сначала перенесите или уберите их.», «К событиям союза привязаны материалы.», «У союза несколько событий брака — исправьте их отдельно.», «У союза несколько событий развода — исправьте их отдельно.»
- Kinship labels: «отчим»/«мачеха» (reason «супруг родителя»), «пасынок»/«падчерица» («ребёнок супруга»), unknown sex → the reason itself as the label («супруг родителя», «ребёнок супруга»; descriptive); divorced union → «бывший …»/«бывшая …» for spouse, step-parent and step-child labels. Blood relationship keeps priority.
- One operation = one transaction; every created/changed/deleted link, union and event is logged (`parent_child`, `union`, `event`; deletions: `before` = values, `after` = `{}`).
- The e2e test never saves. No new dependencies. Lit `static styles = css\`…\``.
- Branch `feature/relationship-editing`; no commit/push/merge unless the owner asks.

## Review Focus

1. Removing a parent must also detach the remaining parent's link from the union with the removed parent, so the tree does not keep the child under that union — Task 3.
2. Replacing a parent keeps the old parent's union with anyone else intact (Наталья + Александр stays) — Task 3.
3. Moving a child to «второй родитель неизвестен» removes the other parent's link and leaves exactly one parent — Task 3.
4. Saving a union with an empty marriage (no date, no place) removes the `MARR` event instead of storing an empty one — Task 3.
5. After any change in the «Связи» block, the «Добавить родственника» block and the block itself show fresh data (shared revision) — Task 7.

---

### Task 1: Step-relations and former spouses in kinship

**Files:**
- Modify: `apps/api/app/genealogy/kinship.py`
- Test: `apps/api/tests/test_kinship.py`

**Interfaces:**
- Produces: `KinshipUnion(partner_one_id, partner_two_id, divorced: bool = False)`; `resolve_kinship` unchanged signature.

- [ ] **Step 1: Failing tests** — append to `tests/test_kinship.py` (read the file first; it builds `KinshipPerson`, `KinshipParentLink`, `KinshipUnion` directly — reuse its helpers if present, otherwise use these):

```python
from uuid import uuid4

from app.genealogy.kinship import KinshipParentLink, KinshipPerson, KinshipUnion, resolve_kinship


def _family():
    ids = {name: uuid4() for name in ("katya", "natalia", "viktor", "alexander", "son")}
    people = {
        ids["katya"]: KinshipPerson(ids["katya"], "F", False),
        ids["natalia"]: KinshipPerson(ids["natalia"], "F", False),
        ids["viktor"]: KinshipPerson(ids["viktor"], "M", False),
        ids["alexander"]: KinshipPerson(ids["alexander"], "M", False),
        ids["son"]: KinshipPerson(ids["son"], "M", False),
    }
    links = [
        KinshipParentLink(ids["natalia"], ids["katya"], "biological"),
        KinshipParentLink(ids["viktor"], ids["katya"], "biological"),
        KinshipParentLink(ids["alexander"], ids["son"], "biological"),
    ]
    return ids, people, links


def test_mothers_husband_is_a_stepfather_and_her_former_husband_stays_father():
    ids, people, links = _family()
    unions = [KinshipUnion(ids["natalia"], ids["viktor"], divorced=True), KinshipUnion(ids["natalia"], ids["alexander"])]

    stepfather = resolve_kinship(ids["katya"], ids["alexander"], people, links, unions)
    father = resolve_kinship(ids["katya"], ids["viktor"], people, links, unions)

    assert (stepfather.label, stepfather.kind, stepfather.reason) == ("отчим", "affinity", "супруг родителя")
    assert father.label == "отец"


def test_spouses_child_is_a_stepchild_and_divorce_makes_everything_former():
    ids, people, links = _family()
    unions = [KinshipUnion(ids["natalia"], ids["viktor"], divorced=True), KinshipUnion(ids["natalia"], ids["alexander"], divorced=True)]

    assert resolve_kinship(ids["alexander"], ids["katya"], people, links, unions).label == "бывшая падчерица"
    assert resolve_kinship(ids["natalia"], ids["son"], people, links, unions).label == "бывший пасынок"
    assert resolve_kinship(ids["natalia"], ids["viktor"], people, links, unions).label == "бывший муж"
    assert resolve_kinship(ids["viktor"], ids["natalia"], people, links, unions).label == "бывшая жена"
    assert resolve_kinship(ids["katya"], ids["alexander"], people, links, unions).label == "бывший отчим"


def test_stepmother_and_unknown_sex():
    ids, people, links = _family()
    stepmother = uuid4()
    people[stepmother] = KinshipPerson(stepmother, "F", False)
    unknown = uuid4()
    people[unknown] = KinshipPerson(unknown, None, False)
    unions = [KinshipUnion(ids["viktor"], stepmother), KinshipUnion(ids["natalia"], unknown)]

    assert resolve_kinship(ids["katya"], stepmother, people, links, unions).label == "мачеха"
    unclear = resolve_kinship(ids["katya"], unknown, people, links, unions)
    assert (unclear.label, unclear.certainty) == ("супруг родителя", "descriptive")


def test_blood_relationship_wins_over_a_step_relationship():
    ids, people, links = _family()
    links.append(KinshipParentLink(ids["alexander"], ids["katya"], "biological"))
    unions = [KinshipUnion(ids["natalia"], ids["alexander"])]

    assert resolve_kinship(ids["katya"], ids["alexander"], people, links, unions).label == "отец"
```

- [ ] **Step 2:** `cd apps/api && .venv/bin/pytest tests/test_kinship.py -q` → new tests FAIL.

- [ ] **Step 3: Implement** in `kinship.py`:
  - `KinshipUnion` gets `divorced: bool = False`.
  - At the top of `_resolve_affinity`, after building `partners`:

```python
    former = {frozenset((union.partner_one_id, union.partner_two_id)) for union in unions if union.divorced}

    def ended(first: UUID, second: UUID) -> bool:
        return frozenset((first, second)) in former
```

  - Replace the spouse check and insert the step rules right after it:

```python
    if target_id in partners.get(centre_id, set()):
        return _former(_spouse_result(target.sex), ended(centre_id, target_id), target.sex)

    centre_parents = parents.get(centre_id, set())
    for parent_id in sorted(centre_parents, key=str):
        if target_id in partners.get(parent_id, set()) and target_id not in centre_parents:
            return _former(_step(target.sex, "отчим", "мачеха", "супруг родителя"), ended(parent_id, target_id), target.sex)

    for spouse_id in sorted(partners.get(centre_id, set()), key=str):
        target_parents = parents.get(target_id, set())
        if spouse_id in target_parents and centre_id not in target_parents:
            return _former(_step(target.sex, "пасынок", "падчерица", "ребёнок супруга"), ended(centre_id, spouse_id), target.sex)
```

  - Helpers (next to `_gendered_affinity`; check `KinshipResult`'s field order and `_is_male` in the file first):

```python
def _step(sex: str | None, male: str, female: str, reason: str) -> KinshipResult:
    """Step-relation label; with unknown sex the reason itself is the descriptive label."""
    if sex not in ("M", "F"):
        return KinshipResult(reason, "affinity", "descriptive", reason)
    return _gendered_affinity(sex, male, female, reason)
```

```python
def _former(result: KinshipResult, divorced: bool, sex: str | None) -> KinshipResult:
    """«бывший»/«бывшая» for relations that exist only through a dissolved union."""
    if not divorced or result.kind != "affinity":
        return result
    prefix = "бывший" if _is_male(sex) else "бывшая"
    return KinshipResult(f"{prefix} {result.label}", result.kind, result.certainty, f"{result.reason}, союз расторгнут")
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_kinship.py -q && .venv/bin/pytest -q` → PASS.

---

### Task 2: Divorce in the tree API and siblings on the person page

**Files:**
- Modify: `apps/api/app/genealogy/tree_service.py`, `apps/api/app/api/routes/tree.py`
- Modify: `apps/api/app/genealogy/read_service.py` (add `public_siblings`), `apps/api/app/api/routes/people.py`
- Test: `apps/api/tests/test_public_tree_api.py`, `apps/api/tests/test_public_people_api.py`

**Interfaces:**
- Produces: tree unions `divorced: bool`; kinship in the tree uses it; public person `siblings: [{id, display_name}]`; `public_siblings(session, person_id) -> list[Person]`.

- [ ] **Step 1: Failing tests**

`test_public_tree_api.py` (it has `create_person(session, run, name, sex=None)`):

```python
def test_tree_marks_divorced_unions_and_names_the_former_and_step_relatives(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    katya, natalia = create_person(database_session, run, "Катя", "F"), create_person(database_session, run, "Наталья", "F")
    viktor, alexander = create_person(database_session, run, "Виктор", "M"), create_person(database_session, run, "Александр", "M")
    first = Union(import_run_id=run.id, partner_one_id=natalia.id, partner_two_id=viktor.id, union_type="marriage")
    second = Union(import_run_id=run.id, partner_one_id=natalia.id, partner_two_id=alexander.id, union_type="marriage")
    database_session.add_all([first, second])
    database_session.flush()
    database_session.add_all([
        ParentChild(parent_id=natalia.id, child_id=katya.id, union_id=first.id, relationship_type="biological"),
        ParentChild(parent_id=viktor.id, child_id=katya.id, union_id=first.id, relationship_type="biological"),
        Event(union_id=first.id, event_type="DIV"),
    ])
    database_session.commit()

    body = client.get(f"/api/v1/tree/{katya.id}?mode=close").json()

    divorced = {item["id"]: item["divorced"] for item in body["unions"]}
    assert divorced == {str(first.id): True, str(second.id): False}
    labels = {item["display_name"]: (item.get("relationship") or {}).get("label") for item in body["people"]}
    assert labels["Александр"] == "отчим" and labels["Виктор"] == "отец"
```

(Import `Event`, `ParentChild`, `Union`, `ImportRun` in the test file if missing.)

`test_public_people_api.py` (has `add_person`):

```python
def test_person_page_lists_siblings_without_hidden_ones(client, database_session):
    mother = add_person(database_session, "Анна")
    child, brother, hidden = add_person(database_session, "Иван"), add_person(database_session, "Пётр"), add_person(database_session, "Скрытый", archived=True)
    for person in (child, brother, hidden):
        database_session.add(ParentChild(parent_id=mother.id, child_id=person.id, relationship_type="biological"))
    database_session.commit()

    body = client.get(f"/api/v1/people/{child.id}").json()

    assert body["siblings"] == [{"id": str(brother.id), "display_name": "Пётр"}]
```

- [ ] **Step 2:** run both files → new tests FAIL.

- [ ] **Step 3: Implement**
  - `tree_service.py`: after loading the unions used for the graph and for kinship, compute `divorced_ids = set(session.scalars(select(Event.union_id).where(Event.event_type == "DIV", Event.union_id.is_not(None))))`. `TreeUnion` gets `divorced: bool = False`; build it with `divorced=union.id in divorced_ids`. `KinshipUnion(union.partner_one_id, union.partner_two_id, divorced=union.id in divorced_ids)`.
  - `routes/tree.py`: `TreeUnionResponse.divorced: bool = False` and pass it through where unions are mapped.
  - `read_service.py`:

```python
def public_siblings(session: Session, person_id: UUID) -> list[Person]:
    parent_ids = select(ParentChild.parent_id).where(ParentChild.child_id == person_id)
    return list(session.scalars(
        select(Person)
        .join(ParentChild, ParentChild.child_id == Person.id)
        .where(ParentChild.parent_id.in_(parent_ids), Person.id != person_id, Person.is_archived.is_(False))
        .distinct()
        .order_by(Person.display_name)
    ))
```

  (If `.distinct()` with `order_by` on a non-selected expression errors in Postgres, select `Person` only — it is selected — so this is fine.)
  - `routes/people.py`: `PersonResponse.siblings: list[PersonSearchResponse]`, filled like `parents` from `public_siblings`.

- [ ] **Step 4:** `.venv/bin/pytest -q` → PASS.

---

### Task 3: Family editing service

**Files:**
- Modify: `apps/api/app/genealogy/relatives.py` (extract `_relative_person`; extend `family_overview`)
- Create: `apps/api/app/genealogy/family_editing.py`
- Test: `apps/api/tests/test_family_editing.py`; update `apps/api/tests/test_relatives.py` (overview shape)

**Interfaces:**
- Produces in `relatives.py`: `_relative_person(session, anchor: Person, new: PersonEdit | None, existing_id: UUID | None, owner_email: str) -> tuple[Person, bool]` (validates, creates and logs a new person or loads the existing one; raises the stage-2 refusals); `family_overview` unions gain `marriage`, `divorce`, `children`; overview gains `children_without_union`.
- Produces in `family_editing.py`: `replace_parent(session, child_id, parent_id, new, existing_id, owner_email) -> dict` (`{"person": EditablePerson}`), `remove_parent(session, child_id, parent_id, owner_email) -> None`, `move_child(session, parent_id, child_id, union_id, owner_email) -> None`, `update_union(session, union_id, marriage: LifeEventInput | None, divorced: bool, divorce_date: DateValue | None, owner_email) -> dict` (`{"union_id", "marriage", "divorce"}`), `remove_union(session, union_id, owner_email) -> None`, `union_details(session, union: Union, anchor_id: UUID | None) -> dict`.

- [ ] **Step 1: Failing tests** `apps/api/tests/test_family_editing.py`

```python
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
    assert details["children"] == [{"id": str(family["katya"].id), "display_name": "Катя"}]
    assert overview["children_without_union"] == [{"id": str(single.id), "display_name": "Сын"}]
```

In `tests/test_relatives.py`, `test_family_overview_lists_parents_unions_and_what_can_be_added` compares the whole union dict; change the expectation to compare only `{"union_id", "partner"}` of each item:

```python
    assert [{"union_id": item["union_id"], "partner": item["partner"]} for item in overview["unions"]] == [ ...same expected list as before... ]
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_family_editing.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

In `relatives.py`, extract from `add_relative` the existing/new person block into:

```python
def _relative_person(session: Session, anchor: Person, new: PersonEdit | None, existing_id: UUID | None, owner_email: str) -> tuple[Person, bool]:
    if existing_id is not None:
        relative = session.get(Person, existing_id)
        if relative is None:
            raise LookupError("Выбранный человек не найден.")
        if relative.id == anchor.id:
            raise RelativeError("Нельзя связать человека с самим собой.")
        return relative, False
    relative = Person(import_run_id=None, source_uid=None, display_name="")
    session.add(relative)
    session.flush()
    _assign(session, relative, new)
    session.flush()
    _log(session, "person", relative.id, owner_email, {}, _snapshot(session, relative))
    return relative, True
```

and use it in `add_relative` (`relative, created = _relative_person(session, anchor, new, existing_id, owner_email)` inside the `try`). Move `_log` above `family_overview` if needed for ordering (Python resolves at call time, so order only matters for readability).

Extend `family_overview`: each union item becomes `union_details(session, item, person.id)` (import from `family_editing` lazily inside the function to avoid a cycle: `from app.genealogy.family_editing import union_details`), and add

```python
        "children_without_union": [
            _ref(child) for child in session.scalars(
                select(Person).join(ParentChild, ParentChild.child_id == Person.id)
                .where(ParentChild.parent_id == person.id, ParentChild.union_id.is_(None)).distinct().order_by(Person.display_name)
            )
        ],
```

`apps/api/app/genealogy/family_editing.py`:

```python
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


def union_details(session: Session, union: Union, anchor_id: UUID | None) -> dict:
    partner_id = union.partner_two_id if union.partner_one_id == anchor_id else union.partner_one_id
    partner = session.get(Person, partner_id) if partner_id else None
    marriages, divorces = _union_events(session, union.id, "MARR"), _union_events(session, union.id, "DIV")
    children = session.scalars(
        select(Person).join(ParentChild, ParentChild.child_id == Person.id).where(ParentChild.union_id == union.id).distinct().order_by(Person.display_name)
    )
    return {
        "union_id": str(union.id),
        "partner": _ref(partner) if partner else None,
        "marriage": _event_view(marriages[0] if marriages else None, True),
        "divorce": _event_view(divorces[0] if divorces else None, False),
        "children": [_ref(child) for child in children],
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


def update_union(session: Session, union_id: UUID, marriage: LifeEventInput | None, divorced: bool, divorce_date: DateValue | None, owner_email: str) -> dict:
    union = session.get(Union, union_id)
    if union is None:
        raise LookupError("Союз не найден.")
    try:
        before = _union_summary(session, union)
        has_marriage = marriage is not None and (marriage.date is not None or bool((marriage.place or "").strip()))
        _write_union_event(session, union, "MARR", marriage if has_marriage else None, owner_email)
        _write_union_event(session, union, "DIV", LifeEventInput(divorce_date, None) if divorced else None, owner_email)
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
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_family_editing.py tests/test_relatives.py -q && .venv/bin/pytest -q` → PASS.

---

### Task 4: Owner API routes

**Files:**
- Modify: `apps/api/app/api/routes/admin_genealogy.py`
- Test: `apps/api/tests/test_owner_genealogy_api.py`

**Interfaces:**
- Produces: `POST /admin/people/{child_id}/parents/{parent_id}/replace` (200), `DELETE /admin/people/{child_id}/parents/{parent_id}` (204), `POST /admin/people/{parent_id}/children/{child_id}/move` (204), `PATCH /admin/unions/{union_id}` (200), `DELETE /admin/unions/{union_id}` (204).

- [ ] **Step 1: Failing tests** (append; `FORM`, `login`, `create_person`, `create_related_person` exist):

```python
def _family(database_session):
    mother = create_person(database_session)
    father = create_related_person(database_session, mother.import_run_id, "Пётр")
    child = create_related_person(database_session, mother.import_run_id, "Мария")
    marriage = Union(import_run_id=mother.import_run_id, partner_one_id=mother.id, partner_two_id=father.id, union_type="marriage")
    database_session.add(marriage)
    database_session.flush()
    database_session.add_all([
        ParentChild(parent_id=mother.id, child_id=child.id, union_id=marriage.id, relationship_type="biological"),
        ParentChild(parent_id=father.id, child_id=child.id, union_id=marriage.id, relationship_type="biological"),
    ])
    database_session.commit()
    return mother, father, child, marriage


def test_guests_cannot_edit_links_or_unions(client, database_session):
    mother, father, child, marriage = _family(database_session)

    assert client.post(f"/api/v1/admin/people/{child.id}/parents/{father.id}/replace", json={"person": FORM}).status_code == 401
    assert client.request("DELETE", f"/api/v1/admin/people/{child.id}/parents/{father.id}").status_code == 401
    assert client.post(f"/api/v1/admin/people/{mother.id}/children/{child.id}/move", json={"union_id": None}).status_code == 401
    assert client.patch(f"/api/v1/admin/unions/{marriage.id}", json={"marriage": None, "divorced": True, "divorce_date": None}).status_code == 401
    assert client.request("DELETE", f"/api/v1/admin/unions/{marriage.id}").status_code == 401


def test_owner_replaces_a_parent_marks_a_divorce_and_sees_it_in_the_family(client, database_session):
    mother, father, child, marriage = _family(database_session)
    login(client)

    replaced = client.post(f"/api/v1/admin/people/{child.id}/parents/{father.id}/replace", json={"person": FORM, "existing_id": None})
    divorce = client.patch(f"/api/v1/admin/unions/{marriage.id}", json={"marriage": None, "divorced": True, "divorce_date": {"qualifier": "exact", "year": 1990, "month": None, "day": None, "end": None}})

    assert replaced.status_code == 200 and replaced.json()["person"]["display_name"] == "Анна Иванова"
    assert divorce.status_code == 200 and divorce.json()["divorce"]["date_text"] == "1990"
    family = client.get(f"/api/v1/admin/people/{mother.id}/family").json()
    by_partner = {item["partner"]["display_name"]: item for item in family["unions"]}
    assert by_partner["Пётр"]["divorce"]["date_text"] == "1990" and by_partner["Пётр"]["children"] == []
    assert [item["display_name"] for item in by_partner["Анна Иванова"]["children"]] == ["Мария"]


def test_owner_removes_and_moves_links_and_removes_an_empty_union(client, database_session):
    mother, father, child, marriage = _family(database_session)
    login(client)

    assert client.post(f"/api/v1/admin/people/{mother.id}/children/{child.id}/move", json={"union_id": None}).status_code == 204
    assert client.request("DELETE", f"/api/v1/admin/unions/{marriage.id}").status_code == 204
    assert client.request("DELETE", f"/api/v1/admin/people/{child.id}/parents/{mother.id}").status_code == 204
    assert database_session.query(ParentChild).filter_by(child_id=child.id).count() == 0


def test_link_refusals_are_russian_and_missing_unions_404(client, database_session):
    from uuid import uuid4

    mother, father, child, marriage = _family(database_session)
    login(client)

    full = client.request("DELETE", f"/api/v1/admin/unions/{marriage.id}")
    not_parent = client.request("DELETE", f"/api/v1/admin/people/{child.id}/parents/{child.id}")

    assert (full.status_code, full.json()) == (422, {"detail": "В союзе есть дети — сначала перенесите или уберите их."})
    assert (not_parent.status_code, not_parent.json()) == (422, {"detail": "Этот человек не записан родителем."})
    assert client.patch(f"/api/v1/admin/unions/{uuid4()}", json={"marriage": None, "divorced": False, "divorce_date": None}).status_code == 404
```

The stage-0 test client exposes `request(method, path, json=None)`; use it for `DELETE` as above.

- [ ] **Step 2:** run the file → new tests FAIL (405/404).

- [ ] **Step 3: Implement** (append to `admin_genealogy.py`; import from `app.genealogy.family_editing`):

```python
class ReplaceBody(BaseModel):
    person: PersonEditBody | None = None
    existing_id: UUID | None = None


class MoveBody(BaseModel):
    union_id: UUID | None = None


class MarriageBody(BaseModel):
    date: DateBody | None = None
    place: str | None = None


class UnionEditBody(BaseModel):
    marriage: MarriageBody | None = None
    divorced: bool = False
    divorce_date: DateBody | None = None


def _owner_errors(call):
    try:
        return call()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (PersonEditError, DateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/admin/people/{child_id}/parents/{parent_id}/replace")
def replace_person_parent(child_id: UUID, parent_id: UUID, body: ReplaceBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    return _owner_errors(lambda: replace_parent(session, child_id, parent_id, _edit(body.person) if body.person else None, body.existing_id, owner.email))


@router.delete("/admin/people/{child_id}/parents/{parent_id}", status_code=204)
def remove_person_parent(child_id: UUID, parent_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    _owner_errors(lambda: remove_parent(session, child_id, parent_id, owner.email))


@router.post("/admin/people/{parent_id}/children/{child_id}/move", status_code=204)
def move_person_child(parent_id: UUID, child_id: UUID, body: MoveBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    _owner_errors(lambda: move_child(session, parent_id, child_id, body.union_id, owner.email))


@router.patch("/admin/unions/{union_id}")
def edit_union(union_id: UUID, body: UnionEditBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    marriage = LifeEventInput(_date(body.marriage.date), body.marriage.place) if body.marriage else None
    return _owner_errors(lambda: update_union(session, union_id, marriage, body.divorced, _date(body.divorce_date), owner.email))


@router.delete("/admin/unions/{union_id}", status_code=204)
def delete_union(union_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    _owner_errors(lambda: remove_union(session, union_id, owner.email))
```

- [ ] **Step 4:** `.venv/bin/pytest -q` → PASS.

---

### Task 5: Web — client, siblings column, dashed divorced unions

**Files:**
- Modify: `apps/web/src/owner-api.ts`, `apps/web/src/pages/person-card.ts`, `apps/web/src/pages/tree-graph.ts`
- Test: `apps/web/test/person-card.test.ts`, `apps/web/test/tree-graph.test.ts`

**Interfaces:**
- Produces (`owner-api.ts`):

```ts
export type UnionDetails = { union_id: string; partner: PersonRef | null; marriage: LifeEventView | null; divorce: { date: DateValue | null; date_text: string | null } | null; children: PersonRef[] }
// FamilyOverview.unions becomes UnionDetails[]; FamilyOverview gains children_without_union: PersonRef[]
export type UnionEditPayload = { marriage: { date: DateValue | null; place: string | null } | null; divorced: boolean; divorce_date: DateValue | null }
export const replaceParent = (childId: string, parentId: string, payload: { person: PersonEditPayload | null; existing_id: string | null }) => request<{ person: EditablePerson }>(`/api/v1/admin/people/${childId}/parents/${parentId}/replace`, json('POST', payload))
export const removeParent = (childId: string, parentId: string) => request<null>(`/api/v1/admin/people/${childId}/parents/${parentId}`, { method: 'DELETE' })
export const moveChild = (parentId: string, childId: string, unionId: string | null) => request<null>(`/api/v1/admin/people/${parentId}/children/${childId}/move`, json('POST', { union_id: unionId }))
export const updateUnion = (unionId: string, payload: UnionEditPayload) => request<{ union_id: string; marriage: LifeEventView | null; divorce: UnionDetails['divorce'] }>(`/api/v1/admin/unions/${unionId}`, json('PATCH', payload))
export const removeUnion = (unionId: string) => request<null>(`/api/v1/admin/unions/${unionId}`, { method: 'DELETE' })
```

- Produces: `TreeUnionData.divorced?: boolean`; partner paths of divorced unions get class `divorced` (`.line.partner.divorced { stroke-dasharray:6 4 }`); person card shows `person.siblings` in «Братья и сёстры».

- [ ] **Step 1: Failing tests**

`person-card.test.ts`:

```ts
it('lists siblings instead of the placeholder', async () => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, siblings: [{ id: 's1', display_name: 'Ольга' }] }
  document.body.append(card)
  await card.updateComplete

  const column = [...card.shadowRoot!.querySelectorAll('.family-columns > div')].find((item) => item.querySelector('h3')?.textContent === 'Братья и сёстры')!
  expect(column.querySelector('a')?.getAttribute('href')).toBe('/people/s1')
  expect(column.textContent).not.toContain('пока не указаны')
})
```

`tree-graph.test.ts`:

```ts
it('draws a divorced union with a dashed partner line', async () => {
  await import('../src/pages/tree-graph')
  const graph = document.createElement('cats-tree-graph') as HTMLElement & { graph: TreeGraphData }
  graph.graph = {
    ...familyGraph,
    people: familyGraph.people.slice(0, 2),
    unions: [{ id: 'pair', partner_one_id: 'parent', partner_two_id: 'child', union_type: 'marriage', divorced: true }],
    parent_links: [],
  }
  document.body.append(graph)
  await (graph as unknown as { updateComplete: Promise<void> }).updateComplete

  expect(graph.shadowRoot?.querySelector('path.partner')?.classList.contains('divorced')).toBe(true)
})
```

- [ ] **Step 2:** `cd apps/web && npx vitest run test/person-card.test.ts test/tree-graph.test.ts` → new tests FAIL.

- [ ] **Step 3: Implement**
  - `owner-api.ts`: the types and functions above; update `FamilyOverview`.
  - `person-card.ts`: `PublicPerson` gets `siblings?: PublicRelation[]`; replace the siblings placeholder with `${this.renderRelationList(person.siblings ?? [], 'Братья и сёстры в архиве пока не указаны')}`.
  - `tree-graph.ts`: `TreeUnionData` add `divorced?:boolean`; in `render()` compute `const divorced=new Set((this.graph.unions??[]).filter(u=>u.divorced).map(u=>u.id))` and render paths with `class="line ${p.kind} ${p.kind==='partner'&&p.blockId&&divorced.has(p.blockId)?'divorced':''}"`; add CSS `.line.partner.divorced{stroke-dasharray:6 4}`.

- [ ] **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 6: Web — replace mode of the adder and the union editor

**Files:**
- Modify: `apps/web/src/pages/relative-adder.ts`
- Create: `apps/web/src/pages/union-editor.ts`
- Test: `apps/web/test/relative-adder.test.ts`, `apps/web/test/union-editor.test.ts`

**Interfaces:**
- Produces on `<cats-relative-adder>`: property `replaceParent: PersonRef | null` (default `null`). When set: heading «Заменить родителя: {name}», no second-parent radios, never blocked, search/suggestions exclude both `personId` and the replaced parent, and submit calls `replaceParent(personId, replaceParent.id, { person, existing_id })`; on success dispatches the same `relative-added` event (`detail: { relation: 'parent', created: <bool from payload: person !== null>, person }`).
- Produces `<cats-union-editor>`: property `union: UnionDetails`; form with a `cats-date-input` (`data-kind="marriage"`), `input[name="marriage-place"]`, checkbox `input[name="divorced"]` («В разводе»), a second `cats-date-input` (`data-kind="divorce"`) shown only when divorced; buttons «Сохранить», «Отмена»; `[role="alert"]`. Events: `union-saved` (`detail` = API response), `union-cancel`. Payload: `marriage` is `null` when neither date nor place is filled, otherwise `{ date, place }`; `divorce_date` is `null` unless divorced.

- [ ] **Step 1: Failing tests**

Append to `relative-adder.test.ts` (reuse `render`-like setup; the replace mode does not need `/family` to answer meaningfully, but `api()` handles it):

```ts
describe('cats-relative-adder replacing a parent', () => {
  it('replaces the chosen parent with a new person', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith('/family')) return Promise.resolve(new Response(JSON.stringify({ ...FAMILY, can_add_parent: false })))
      if (url.endsWith('/parents/alex/replace')) return Promise.resolve(new Response(JSON.stringify({ person: { id: 'viktor', display_name: 'Виктор' } })))
      return Promise.resolve(new Response('[]'))
    })
    vi.stubGlobal('fetch', fetchMock)
    const adder = document.createElement('cats-relative-adder') as Adder & { replaceParent: { id: string; display_name: string } | null }
    adder.personId = 'katya'
    adder.relation = 'parent'
    adder.replaceParent = { id: 'alex', display_name: 'Александр' }
    adder.similarDelay = 0
    document.body.append(adder)
    await settle(adder)
    const added = vi.fn()
    adder.addEventListener('relative-added', added)

    expect(root(adder).querySelector('h3')?.textContent).toBe('Заменить родителя: Александр')
    expect(root(adder).querySelector('.blocked')).toBeNull()
    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/replace'))!
    expect(JSON.parse(String(init!.body))).toEqual({ person: DRAFT, existing_id: null })
    expect(added).toHaveBeenCalledWith(expect.objectContaining({ detail: { relation: 'parent', created: true, person: { id: 'viktor', display_name: 'Виктор' } } }))
  })
})
```

`apps/web/test/union-editor.test.ts`:

```ts
import { afterEach, expect, it, vi } from 'vitest'

import '../src/pages/union-editor'
import type { UnionDetails } from '../src/owner-api'

type Editor = HTMLElement & { union: UnionDetails; updateComplete: Promise<boolean> }
const settle = async (element: Editor) => { for (let index = 0; index < 3; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const UNION: UnionDetails = { union_id: 'u1', partner: { id: 'v', display_name: 'Виктор' }, marriage: { date: { qualifier: 'exact', year: 1975, month: null, day: null, end: null }, date_text: '1975', place: null }, divorce: null, children: [] }

async function render(union = UNION, response: Response = new Response(JSON.stringify({ union_id: 'u1', marriage: null, divorce: { date: null, date_text: null } }))) {
  const fetchMock = vi.fn().mockResolvedValue(response)
  vi.stubGlobal('fetch', fetchMock)
  const editor = document.createElement('cats-union-editor') as Editor
  editor.union = union
  document.body.append(editor)
  await settle(editor)
  return { editor, fetchMock }
}
const button = (editor: Editor, text: string) => [...editor.shadowRoot!.querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement
const body = (fetchMock: ReturnType<typeof vi.fn>) => JSON.parse(String(fetchMock.mock.calls[0][1].body))

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('marks a divorce without a date and keeps the marriage date', async () => {
  const { editor, fetchMock } = await render()
  const saved = vi.fn()
  editor.addEventListener('union-saved', saved)
  expect(editor.shadowRoot!.querySelector('cats-date-input[data-kind="divorce"]')).toBeNull()

  const divorced = editor.shadowRoot!.querySelector('input[name="divorced"]') as HTMLInputElement
  divorced.checked = true
  divorced.dispatchEvent(new Event('change'))
  await settle(editor)
  expect(editor.shadowRoot!.querySelector('cats-date-input[data-kind="divorce"]')).not.toBeNull()
  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/unions/u1', expect.objectContaining({ method: 'PATCH' }))
  expect(body(fetchMock)).toEqual({ marriage: { date: UNION.marriage!.date, place: null }, divorced: true, divorce_date: null })
  expect(saved).toHaveBeenCalledTimes(1)
})

it('sends no marriage when neither date nor place is filled', async () => {
  const { editor, fetchMock } = await render({ ...UNION, marriage: null })

  button(editor, 'Сохранить').click()
  await settle(editor)

  expect(body(fetchMock)).toEqual({ marriage: null, divorced: false, divorce_date: null })
})

it('shows the server reason and cancels without saving', async () => {
  const { editor } = await render(UNION, new Response(JSON.stringify({ detail: 'У союза несколько событий брака — исправьте их отдельно.' }), { status: 422 }))
  const cancelled = vi.fn()
  editor.addEventListener('union-cancel', cancelled)

  button(editor, 'Сохранить').click()
  await settle(editor)
  expect(editor.shadowRoot!.querySelector('[role="alert"]')?.textContent).toContain('несколько событий брака')

  button(editor, 'Отмена').click()
  expect(cancelled).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2:** run both files → FAIL.

- [ ] **Step 3: Implement**

`relative-adder.ts`:
- `static properties` add `replaceParent: { attribute: false }`; `declare replaceParent: PersonRef | null`; constructor `this.replaceParent = null`; import `replaceParent as replaceParentRequest` and `PersonRef`.
- `willUpdate`: also `reset()` when `changed.has('replaceParent') && changed.get('replaceParent') !== undefined`.
- `blocked()`: `if (this.replaceParent) return ''` first.
- `otherParent()`: return `''` when `this.replaceParent`.
- Exclusion helper `private excluded(item: OwnerSearchResult) { return item.id === this.personId || item.id === this.replaceParent?.id }` used in both filters.
- `submit(person)`:

```ts
    const result = this.replaceParent
      ? await replaceParentRequest(this.personId, this.replaceParent.id, { person, existing_id: person ? null : this.chosen?.id ?? null })
      : await addRelative(this.personId, { relation: this.relation, person, existing_id: person ? null : this.chosen?.id ?? null, union_id: this.relation === 'child' ? this.unionId : null })
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    const detail = this.replaceParent ? { relation: 'parent', created: person !== null, person: result.value.person } : result.value
    this.dispatchEvent(new CustomEvent('relative-added', { detail, bubbles: true, composed: true }))
```

- `render()`: title `this.replaceParent ? \`Заменить родителя: ${this.replaceParent.display_name}\` : TITLES[this.relation]`.

`union-editor.ts`:

```ts
import { LitElement, css, html } from 'lit'

import '../components/date-input'
import type { CatsDateInput } from '../components/date-input'
import { updateUnion, type DateValue, type UnionDetails } from '../owner-api'

/** Owner form for one union: marriage date and place, divorce flag and date. */
export class CatsUnionEditor extends LitElement {
  static properties = { union: { attribute: false }, marriageDate: { state: true }, marriagePlace: { state: true }, divorced: { state: true }, divorceDate: { state: true }, error: { state: true }, busy: { state: true } }
  declare union: UnionDetails
  private declare marriageDate: DateValue | null
  private declare marriagePlace: string
  private declare divorced: boolean
  private declare divorceDate: DateValue | null
  private declare error: string
  private declare busy: boolean

  constructor() { super(); this.marriageDate = null; this.marriagePlace = ''; this.divorced = false; this.divorceDate = null; this.error = ''; this.busy = false }

  static styles = css`
    :host { display:block; margin:.75rem 0; padding:1rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    form { display:grid; gap:.75rem; }
    label { display:grid; gap:.25rem; font-size:.8rem; font-weight:600; color:var(--text-2,#4a4c49); }
    label.check { display:flex; align-items:center; gap:.5rem; }
    input[name="marriage-place"] { height:2.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; }
    .actions { display:flex; gap:.5rem; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:#fff; font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    [role="alert"] { color:#7d2b20; margin:0; }
  `

  willUpdate(changed: Map<string, unknown>) {
    if (!changed.has('union') || !this.union) return
    this.marriageDate = this.union.marriage?.date ?? null
    this.marriagePlace = this.union.marriage?.place ?? ''
    this.divorced = this.union.divorce !== null
    this.divorceDate = this.union.divorce?.date ?? null
  }

  private async save(event: Event) {
    event.preventDefault()
    if (this.busy) return
    for (const kind of ['marriage', 'divorce']) {
      const input = this.shadowRoot?.querySelector<CatsDateInput>(`cats-date-input[data-kind="${kind}"]`)
      const value = kind === 'marriage' ? this.marriageDate : this.divorceDate
      const message = value ? input?.validationMessage() : ''
      if (message) { this.error = message; return }
    }
    const place = this.marriagePlace.trim() || null
    this.busy = true; this.error = ''
    const result = await updateUnion(this.union.union_id, {
      marriage: this.marriageDate || place ? { date: this.marriageDate, place } : null,
      divorced: this.divorced,
      divorce_date: this.divorced ? this.divorceDate : null,
    })
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.dispatchEvent(new CustomEvent('union-saved', { detail: result.value, bubbles: true, composed: true }))
  }

  render() {
    return html`<form @submit=${this.save} novalidate>
      <cats-date-input data-kind="marriage" label="Дата брака" .value=${this.marriageDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.marriageDate = event.detail }}></cats-date-input>
      <label>Место брака<input name="marriage-place" .value=${this.marriagePlace} @input=${(event: Event) => { this.marriagePlace = (event.target as HTMLInputElement).value }} /></label>
      <label class="check"><input type="checkbox" name="divorced" .checked=${this.divorced} @change=${(event: Event) => { this.divorced = (event.target as HTMLInputElement).checked }} /> В разводе</label>
      ${this.divorced ? html`<cats-date-input data-kind="divorce" label="Дата развода (если известна)" .value=${this.divorceDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.divorceDate = event.detail }}></cats-date-input>` : ''}
      ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
      <div class="actions"><button class="primary" type="submit" ?disabled=${this.busy}>Сохранить</button><button type="button" @click=${() => this.dispatchEvent(new CustomEvent('union-cancel', { bubbles: true, composed: true }))}>Отмена</button></div>
    </form>`
  }
}

customElements.define('cats-union-editor', CatsUnionEditor)
```

(Check `CatsDateInput.validationMessage`'s signature in `components/date-input.ts` before calling it; it takes an optional `keepLegacy` flag.)

- [ ] **Step 4:** `npx vitest run test/relative-adder.test.ts test/union-editor.test.ts && npm run typecheck` → PASS.

---

### Task 7: Web — family editor block on the person page

**Files:**
- Create: `apps/web/src/pages/family-editor.ts`
- Modify: `apps/web/src/pages/person-card.ts`, `apps/web/src/pages/relative-section.ts`
- Test: `apps/web/test/family-editor.test.ts`, `apps/web/test/person-card.test.ts`

**Interfaces:**
- Produces `<cats-family-editor>`: properties `personId: string`, `revision: number` (reload on change), `confirm: (text: string) => boolean` (default `window.confirm`). Emits `person-changed` (bubbles, composed) after every successful change and reloads itself.
- DOM contract: heading «Связи»; `.parents li` with «Заменить», «Убрать»; `.unions .union` with partner name, `.status` text, «Изменить», «Убрать союз» (disabled with `title` «Сначала перенесите или уберите детей» when the union has children), `.children li` with «Перенести», «Убрать»; `.single li` («Дети без второго родителя») same; move form: `select[name="move-target"]` with options «Второй родитель неизвестен» (`value=""`) and «С {partner}» for each other union, `.move-note` text, «Перенести», «Отмена»; `[role="alert"]` for errors.
- Status text: «брак: {label}» (label = `formatDateValueRu(date)` or `date_text`; with place «, {place}»); divorced: «в разводе» plus «, развод: {label}» when dated; nothing known → «сведений о браке нет».
- Move note: `Ребёнок будет записан ${target ? \`в союз с ${partner}\` : 'без второго родителя'}` + `; связь с ${currentPartner} будет убрана` when the current union's partner differs from the target's partner, then «.».
- `cats-relative-section` gains `revision` too and re-renders nothing special (its adder reloads family on open), but the person card passes the same counter to both so a stale panel is closed: when `revision` changes the section closes its adder.

- [ ] **Step 1: Failing tests** `apps/web/test/family-editor.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/family-editor'
import type { FamilyOverview } from '../src/owner-api'

type Block = HTMLElement & { personId: string; revision: number; confirm: (text: string) => boolean; updateComplete: Promise<boolean> }
const settle = async (element: Block) => { for (let index = 0; index < 4; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const FAMILY: FamilyOverview = {
  parents: [{ id: 'mom', display_name: 'Анна' }],
  unions: [
    { union_id: 'u1', partner: { id: 'alex', display_name: 'Александр' }, marriage: null, divorce: null, children: [{ id: 'katya', display_name: 'Катя' }] },
    { union_id: 'u2', partner: { id: 'viktor', display_name: 'Виктор' }, marriage: { date: { qualifier: 'exact', year: 1975, month: null, day: null, end: null }, date_text: '1975', place: 'Москва' }, divorce: { date: null, date_text: null }, children: [] },
  ],
  children_without_union: [{ id: 'son', display_name: 'Сын' }],
  can_add_parent: true, can_add_sibling: true,
}

function api() {
  return vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/family')) return Promise.resolve(new Response(JSON.stringify(FAMILY)))
    if (init?.method === 'DELETE' || url.endsWith('/move')) return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response('[]'))
  })
}
async function render() {
  const fetchMock = api()
  vi.stubGlobal('fetch', fetchMock)
  const block = document.createElement('cats-family-editor') as Block
  block.personId = 'natalia'
  block.confirm = vi.fn(() => true)
  document.body.append(block)
  await settle(block)
  return { block, fetchMock }
}
const root = (block: Block) => block.shadowRoot!
const buttonIn = (element: Element, text: string) => [...element.querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-family-editor', () => {
  it('lists parents, unions with status and children, and children without a second parent', async () => {
    const { block } = await render()

    expect(root(block).querySelector('h3')?.textContent).toBe('Связи')
    expect(root(block).querySelector('.parents li')?.textContent).toContain('Анна')
    const [alex, viktor] = [...root(block).querySelectorAll('.unions .union')]
    expect(alex.querySelector('.status')?.textContent?.trim()).toBe('сведений о браке нет')
    expect(viktor.querySelector('.status')?.textContent?.trim()).toBe('брак: 1975, Москва; в разводе')
    expect(buttonIn(alex, 'Убрать союз').disabled).toBe(true)
    expect(buttonIn(viktor, 'Убрать союз').disabled).toBe(false)
    expect(root(block).querySelector('.single li')?.textContent).toContain('Сын')
  })

  it('removes a parent after confirmation and reports the change', async () => {
    const { block, fetchMock } = await render()
    const changed = vi.fn()
    block.addEventListener('person-changed', changed)

    buttonIn(root(block).querySelector('.parents li')!, 'Убрать').click()
    await settle(block)

    expect(block.confirm).toHaveBeenCalledWith('Убрать связь «Анна — родитель»? Сам человек останется в архиве.')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/natalia/parents/mom', { method: 'DELETE' })
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('moves a child into another union and explains whose link goes away', async () => {
    const { block, fetchMock } = await render()
    const katya = root(block).querySelector('.unions .union .children li')!

    buttonIn(katya, 'Перенести').click()
    await settle(block)
    const select = root(block).querySelector('select[name="move-target"]') as HTMLSelectElement
    select.value = 'u2'
    select.dispatchEvent(new Event('change'))
    await settle(block)
    expect(root(block).querySelector('.move-note')?.textContent).toBe('Ребёнок будет записан в союз с Виктор; связь с Александр будет убрана.')
    buttonIn(root(block).querySelector('.move')!, 'Перенести').click()
    await settle(block)

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/children/katya/move'))!
    expect(JSON.parse(String(init!.body))).toEqual({ union_id: 'u2' })
  })

  it('opens the replace panel for a parent and the union editor for a union', async () => {
    const { block } = await render()

    buttonIn(root(block).querySelector('.parents li')!, 'Заменить').click()
    await settle(block)
    const adder = root(block).querySelector('cats-relative-adder') as HTMLElement & { replaceParent: { id: string } }
    expect(adder.replaceParent.id).toBe('mom')

    buttonIn(root(block).querySelectorAll('.unions .union')[1], 'Изменить').click()
    await settle(block)
    expect((root(block).querySelector('cats-union-editor') as HTMLElement & { union: { union_id: string } }).union.union_id).toBe('u2')
  })

  it('does nothing when the owner cancels a removal', async () => {
    const { block, fetchMock } = await render()
    ;(block.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false)

    buttonIn(root(block).querySelectorAll('.unions .union')[1], 'Убрать союз').click()
    await settle(block)

    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })
})
```

`person-card.test.ts` — extend the stage-2 owner test or add:

```ts
it('shows the «Связи» block above «Добавить родственника» for the owner only', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ parents: [], unions: [], children_without_union: [], can_add_parent: true, can_add_sibling: false }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  document.body.append(card)
  await card.updateComplete

  const blocks = [...card.shadowRoot!.querySelectorAll('#family cats-family-editor, #family cats-relative-section')].map((item) => item.tagName.toLowerCase())
  expect(blocks).toEqual(['cats-family-editor', 'cats-relative-section'])
})
```

- [ ] **Step 2:** run both files → FAIL.

- [ ] **Step 3: Implement** `apps/web/src/pages/family-editor.ts`

```ts
import { LitElement, css, html, nothing } from 'lit'

import './relative-adder'
import './union-editor'
import { formatDateValueRu } from '../date-format'
import { fetchFamily, moveChild, removeParent, removeUnion, type DateValue, type FamilyOverview, type PersonRef, type UnionDetails } from '../owner-api'

/** Owner block «Связи»: replace/remove parents, edit/remove unions, move/remove children. */
export class CatsFamilyEditor extends LitElement {
  static properties = { personId: { attribute: false }, revision: { attribute: false }, family: { state: true }, replacing: { state: true }, editingUnion: { state: true }, moving: { state: true }, moveTarget: { state: true }, error: { state: true } }
  declare personId: string
  declare revision: number
  private declare family: FamilyOverview | null
  private declare replacing: PersonRef | null
  private declare editingUnion: string | null
  private declare moving: { child: PersonRef; fromPartner: PersonRef | null } | null
  private declare moveTarget: string
  private declare error: string
  confirm: (text: string) => boolean = (message) => window.confirm(message)

  constructor() { super(); this.personId = ''; this.revision = 0; this.family = null; this.replacing = null; this.editingUnion = null; this.moving = null; this.moveTarget = ''; this.error = '' }

  static styles = css`
    :host { display:block; margin-top:32px; }
    h3 { margin:0 0 12px; font-family:var(--font-serif,Georgia,serif); }
    h4 { margin:16px 0 8px; font-size:.9rem; }
    ul { list-style:none; padding:0; margin:0; display:grid; gap:6px; }
    li { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .union { border-top:1px solid var(--border,#dcdcd8); padding:10px 0; }
    .union-head { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .status { color:var(--text-3,#6b6d69); font-size:.85rem; }
    .children { margin:8px 0 0 16px; }
    button { min-height:2rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .7rem; background:transparent; color:var(--green,var(--cats-accent)); font:600 .8rem Inter,system-ui,sans-serif; cursor:pointer; }
    button:disabled { opacity:.5; cursor:default; }
    .move { display:grid; gap:6px; margin:6px 0; }
    select { height:2.25rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; font:inherit; }
    .move-note { font-size:.8rem; color:var(--text-3,#6b6d69); margin:0; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() { super.connectedCallback(); void this.load() }

  willUpdate(changed: Map<string, unknown>) {
    if ((changed.has('revision') && changed.get('revision') !== undefined) || (changed.has('personId') && changed.get('personId') !== undefined)) void this.load()
  }

  private async load() {
    const result = await fetchFamily(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.family = result.value
    this.replacing = null; this.editingUnion = null; this.moving = null
  }

  private async changed(request?: Promise<{ ok: boolean; message?: string }>) {
    if (request) {
      const result = await request
      if (!result.ok) { this.error = (result as { message: string }).message; return }
    }
    this.error = ''
    await this.load()
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }

  private removeParentLink(parent: PersonRef) {
    if (!this.confirm(`Убрать связь «${parent.display_name} — родитель»? Сам человек останется в архиве.`)) return
    void this.changed(removeParent(this.personId, parent.id))
  }

  private removeChildLink(child: PersonRef) {
    if (!this.confirm(`Убрать связь «${child.display_name} — ребёнок»? Сам человек останется в архиве.`)) return
    void this.changed(removeParent(child.id, this.personId))
  }

  private removeWholeUnion(union: UnionDetails) {
    if (!this.confirm(`Убрать союз${union.partner ? ` с ${union.partner.display_name}` : ''}?`)) return
    void this.changed(removeUnion(union.union_id))
  }

  private status(union: UnionDetails): string {
    const describe = (view: { date: DateValue | null; date_text: string | null } | null) => (view?.date ? formatDateValueRu(view.date) : view?.date_text ?? '')
    const parts: string[] = []
    if (union.marriage) parts.push(`брак: ${[describe(union.marriage), union.marriage.place].filter(Boolean).join(', ')}`)
    if (union.divorce) {
      const when = describe(union.divorce)
      parts.push(when ? `в разводе, развод: ${when}` : 'в разводе')
    }
    return parts.join('; ') || 'сведений о браке нет'
  }

  private moveForm() {
    if (!this.moving || !this.family) return nothing
    const { child, fromPartner } = this.moving
    const targets = this.family.unions.filter((union) => !union.children.some((item) => item.id === child.id))
    const target = this.family.unions.find((union) => union.union_id === this.moveTarget) ?? null
    const lost = fromPartner && fromPartner.id !== target?.partner?.id ? `; связь с ${fromPartner.display_name} будет убрана` : ''
    const note = `Ребёнок будет записан ${target ? `в союз с ${target.partner?.display_name ?? 'неизвестным партнёром'}` : 'без второго родителя'}${lost}.`
    return html`<div class="move">
      <select name="move-target" .value=${this.moveTarget} @change=${(event: Event) => { this.moveTarget = (event.target as HTMLSelectElement).value }}>
        <option value="" ?selected=${this.moveTarget === ''}>Второй родитель неизвестен</option>
        ${targets.map((union) => html`<option value=${union.union_id} ?selected=${this.moveTarget === union.union_id}>С ${union.partner?.display_name ?? 'неизвестным партнёром'}</option>`)}
      </select>
      <p class="move-note">${note}</p>
      <div><button @click=${() => this.changed(moveChild(this.personId, child.id, this.moveTarget || null))}>Перенести</button> <button @click=${() => { this.moving = null }}>Отмена</button></div>
    </div>`
  }

  private childRow(child: PersonRef, fromPartner: PersonRef | null) {
    return html`<li><a href="/people/${child.id}">${child.display_name}</a>
      <button @click=${() => { this.moving = { child, fromPartner }; this.moveTarget = '' }}>Перенести</button>
      <button @click=${() => this.removeChildLink(child)}>Убрать</button>
      ${this.moving?.child.id === child.id ? this.moveForm() : nothing}</li>`
  }

  render() {
    if (!this.family) return html`<h3>Связи</h3>${this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`}`
    const family = this.family
    return html`<h3>Связи</h3>
      ${this.error ? html`<p role="alert">${this.error}</p>` : nothing}
      <h4>Родители</h4>
      ${family.parents.length ? html`<ul class="parents">${family.parents.map((parent) => html`<li><a href="/people/${parent.id}">${parent.display_name}</a>
        <button @click=${() => { this.replacing = parent }}>Заменить</button><button @click=${() => this.removeParentLink(parent)}>Убрать</button></li>`)}</ul>` : html`<p class="status">Родители не указаны</p>`}
      ${this.replacing ? html`<cats-relative-adder .personId=${this.personId} .relation=${'parent'} .replaceParent=${this.replacing} @relative-added=${() => this.changed()} @adder-cancel=${() => { this.replacing = null }}></cats-relative-adder>` : nothing}
      <h4>Союзы</h4>
      ${family.unions.length ? html`<div class="unions">${family.unions.map((union) => html`<div class="union">
        <div class="union-head"><strong>С ${union.partner?.display_name ?? 'неизвестным партнёром'}</strong><span class="status">${this.status(union)}</span>
          <button @click=${() => { this.editingUnion = union.union_id }}>Изменить</button>
          <button ?disabled=${union.children.length > 0} title=${union.children.length ? 'Сначала перенесите или уберите детей' : ''} @click=${() => this.removeWholeUnion(union)}>Убрать союз</button></div>
        ${this.editingUnion === union.union_id ? html`<cats-union-editor .union=${union} @union-saved=${() => this.changed()} @union-cancel=${() => { this.editingUnion = null }}></cats-union-editor>` : nothing}
        ${union.children.length ? html`<ul class="children">${union.children.map((child) => this.childRow(child, union.partner))}</ul>` : nothing}
      </div>`)}</div>` : html`<p class="status">Союзов нет</p>`}
      ${family.children_without_union.length ? html`<h4>Дети без второго родителя</h4><ul class="single">${family.children_without_union.map((child) => this.childRow(child, null))}</ul>` : nothing}`
  }
}

customElements.define('cats-family-editor', CatsFamilyEditor)
```

`person-card.ts`: state `familyRevision = 0`; in `#family` before the relative section render `<cats-family-editor .personId=${person.id} .revision=${this.familyRevision} @person-changed=${this.bumpFamily}></cats-family-editor>` and pass `.revision=${this.familyRevision} @person-changed=${this.bumpFamily}` to `cats-relative-section` too, with `private bumpFamily = () => { this.familyRevision += 1 }` (the event keeps bubbling to the shell).

`relative-section.ts`: add `revision` property; in `willUpdate`, when `revision` changes (not first set) close the adder (`this.adding = null`) but keep `added`.

- [ ] **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 8: End-to-end check, docs, final verification

**Files:**
- Modify: `apps/web/e2e/owner-login.spec.ts` (append), `README.md`

- [ ] **Step 1: E2E** (skipped without the owner password; never saves):

```ts
test('the owner opens the union editor for a real marriage and cancels', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the union editor check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  const block = page.locator('cats-family-editor')
  await expect(block.getByRole('heading', { name: 'Связи' })).toBeVisible()
  await block.getByRole('button', { name: 'Изменить' }).first().click()
  await expect(block.getByText('В разводе')).toBeVisible()
  await block.getByRole('button', { name: 'Отмена' }).first().click()
  await expect(block.getByText('В разводе')).toHaveCount(0)
})
```

- [ ] **Step 2: README** — after «Добавление родственников»:

```markdown
### Исправление связей

На странице человека у владельца есть блок «Связи»: родителя можно заменить
(на нового человека или из архива) или убрать, союз — изменить (дата и место
брака, отметка «В разводе» и дата развода) или убрать, если в нём нет детей,
ребёнка — перенести в другой союз или убрать. Связи убираются без удаления
самих людей. Сайт сам называет супруга родителя отчимом или мачехой, ребёнка
супруга — пасынком или падчерицей, а супругов после развода — бывшими. В
дереве союз в разводе рисуется пунктиром.
```

- [ ] **Step 3: Restart the API** (Ctrl-C in «Cat's House dev», then `CATS_HOUSE_WEB_PORT=5176 bash scripts/dev-native.sh`). No migration is needed.

- [ ] **Step 4: Final verification** — each exits 0:

```bash
cd apps/api && .venv/bin/pytest -q
cd apps/web && npm test && npm run typecheck && npm run build && npm run test:e2e
```

Read-only real-data check: `family_overview` for Наталья Александровна Вахрамеева lists the union with Александр Иванович Иванов and children Екатерина and Алексей. Do not change real data unless the owner asks.

- [ ] **Step 5: Hand over** — independent whole-branch review, RED→GREEN fixes, report rulings and deferred minors; ask before commit/merge/push.
