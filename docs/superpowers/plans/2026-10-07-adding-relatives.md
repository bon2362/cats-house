# Adding Relatives Implementation Plan (owner editor, stage 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From a person's page the owner adds a child, parent, spouse or sibling — a new person or an existing one — atomically, with duplicate warnings.

**Architecture:** `people`/`unions` lose the mandatory import reference. `person_editing.py` exposes its field assignment as `_assign` so a new person is filled exactly like an edit. A new `relatives.py` service holds the family overview, duplicate search and `add_relative` with all relation rules in one transaction. The web editor gains a `draft` mode (empty form that hands its payload to a parent instead of saving); a new `cats-relative-adder` panel combines it with existing-person search and duplicate suggestions; the person page hosts the panel for the owner.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest + testcontainers; Lit, TypeScript, Vitest (jsdom), Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-adding-relatives-design.md` (authority). Stage 1: `docs/superpowers/specs/2026-10-06-person-editing-design.md`.

## Global Constraints

- Russian user-visible text; validation errors are `422` with a Russian string `detail`; missing person/relative `404`; guests `401`.
- Relations: `child`, `parent`, `spouse`, `sibling`. Exactly one of a new person (`person`) or `existing_id`.
- Refusal texts (exact): «Эти люди уже в союзе.», «Нельзя сделать предка человека его ребёнком.», «Этот человек уже записан как ребёнок.», «У этого человека уже есть родители.», «Выбранный союз не принадлежит этому человеку.», «У человека уже два родителя.», «Этот человек уже записан как родитель.», «Нельзя сделать потомка человека его родителем.», «У человека не указаны родители — сначала добавьте родителя.», «Нельзя сделать предка или потомка человека его братом или сестрой.», «Нельзя связать человека с самим собой.», «Выберите нового или существующего человека.», «Выбранный человек не найден.» (404).
- New people and owner-created unions: `import_run_id = NULL`, `source_uid = NULL`; owner-created unions have `union_type = "marriage"`; links `relationship_type = "biological"`.
- One add = one transaction; change log rows for the created person, each created union/link and each re-pointed link.
- Duplicate search: same given name and a surname match (entered surname or birth surname against candidate surname or birth surname), case-insensitive, `ё`=`е`, up to 5, includes hidden people.
- The archive keeps `surname`, `given_name`, `patronymic`, `birth_surname`.
- The e2e test never saves. No new dependencies. Lit `static styles = css\`…\``. Alembic migrations idempotent via `sa.inspect`.
- Branch `feature/adding-relatives`; no commit/push/merge unless the owner asks.

## Review Focus

1. Adding a second parent to a child whose first parent already has several children: only this child's link is re-pointed to the new union; siblings keep theirs — Task 3.
2. Choosing an existing person who is an ancestor/descendant (cycles) for every relation — Task 3.
3. An exception after the new person was flushed (e.g. a refused relation) must leave no person, union, link or log row — Task 3.
4. The `/admin/people/similar` route must not be captured by `/admin/people/{person_id}` (UUID parse → 422) — Task 4.
5. Switching the adder from «Ребёнка» to «Родителя» must not carry over the selected union, chosen person or suggestions — Task 6.

---

### Task 1: Optional import reference and complete archive names

**Files:**
- Create: `apps/api/alembic/versions/0008_owner_created_records.py`
- Modify: `apps/api/app/models/genealogy.py` (`Person.import_run_id`, `Union.import_run_id`)
- Modify: `apps/api/app/genealogy/write_service.py` (`create_union`)
- Modify: `apps/api/app/exports/service.py` (`build_archive`, `restore_archive`)
- Test: `apps/api/tests/test_migrations.py`, `apps/api/tests/test_archive_service.py`, `apps/api/tests/test_owner_genealogy_api.py`

**Interfaces:**
- Produces: `Person.import_run_id: Mapped[UUID | None]`, `Union.import_run_id: Mapped[UUID | None]`; archive person dicts carry `surname`, `given_name`, `patronymic`, `birth_surname`.

- [ ] **Step 1: Failing tests**

`test_migrations.py`:

```python
def test_people_and_unions_may_exist_without_an_import(postgres_url):
    upgrade_database(postgres_url)
    inspector = inspect(create_engine(postgres_url))

    assert {column["name"]: column for column in inspector.get_columns("people")}["import_run_id"]["nullable"] is True
    assert {column["name"]: column for column in inspector.get_columns("unions")}["import_run_id"]["nullable"] is True
```

`test_archive_service.py`:

```python
def test_archive_keeps_name_parts_and_people_created_on_the_site(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as source:
        person = Person(import_run_id=None, source_uid=None, display_name="Анна Петровна Иванова", surname="Иванова", given_name="Анна", patronymic="Петровна", birth_surname="Сидорова")
        partner = Person(import_run_id=None, source_uid=None, display_name="Пётр Иванов", given_name="Пётр", surname="Иванов")
        source.add_all([person, partner])
        source.flush()
        source.add(Union(import_run_id=None, partner_one_id=person.id, partner_two_id=partner.id, union_type="marriage"))
        source.commit()
        archive = build_archive(source)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as target:
        restore_archive(target, archive)
        restored = target.query(Person).filter_by(display_name="Анна Петровна Иванова").one()
        assert (restored.surname, restored.given_name, restored.patronymic, restored.birth_surname) == ("Иванова", "Анна", "Петровна", "Сидорова")
        assert target.query(Union).count() == 1
```

`test_owner_genealogy_api.py` (append):

```python
def test_owner_links_people_from_different_imports(client, database_session):
    first = create_person(database_session)
    second = create_person(database_session)
    login(client)

    response = client.post("/api/v1/admin/unions", json={"partner_one_id": str(first.id), "partner_two_id": str(second.id), "union_type": "marriage"})

    assert response.status_code == 201
```

(`create_person` makes a new import run per call; `login` exists in the file since stage 1.)

- [ ] **Step 2:** `cd apps/api && .venv/bin/pytest tests/test_migrations.py tests/test_archive_service.py tests/test_owner_genealogy_api.py -q` → the three new tests FAIL.

- [ ] **Step 3: Implement**

Migration `0008_owner_created_records.py`:

```python
"""People and unions created on the site have no import run."""

import sqlalchemy as sa
from alembic import op


revision = "0008_owner_created_records"
down_revision = "0007_person_display_name_length"
branch_labels = None
depends_on = None


def _make_nullable(table: str) -> None:
    columns = {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table)}
    if not columns["import_run_id"]["nullable"]:
        op.alter_column(table, "import_run_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)


def upgrade() -> None:
    _make_nullable("people")
    _make_nullable("unions")


def downgrade() -> None:
    op.alter_column("unions", "import_run_id", nullable=False)
    op.alter_column("people", "import_run_id", nullable=False)
```

(Import `from sqlalchemy.dialects import postgresql` and use `postgresql.UUID(as_uuid=True)` if `sa.dialects.postgresql` is not resolvable.) Check the real `down_revision` id with `ls apps/api/alembic/versions` before writing it.

Models: `import_run_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_runs.id"), nullable=True)` on `Person` and `Union`.

`create_union`: delete the `if first.import_run_id != second.import_run_id: raise ValueError(...)` block; set `import_run_id=first.import_run_id if first.import_run_id == second.import_run_id else None`.

`build_archive` person dict: add `"surname": person.surname, "given_name": person.given_name, "patronymic": person.patronymic, "birth_surname": person.birth_surname`. `restore_archive`: pass `surname=data.get("surname"), given_name=data.get("given_name"), patronymic=data.get("patronymic"), birth_surname=data.get("birth_surname")` to `Person(...)`.

- [ ] **Step 4:** run the same command → PASS; then `.venv/bin/pytest -q` → all PASS (a test that asserted the old «одному импорту» refusal, if any, is removed because the rule no longer exists).

---

### Task 2: Shared field assignment, family overview, duplicate search

**Files:**
- Modify: `apps/api/app/genealogy/person_editing.py` (extract `_assign`)
- Create: `apps/api/app/genealogy/relatives.py`
- Test: `apps/api/tests/test_relatives.py`

**Interfaces:**
- Produces in `person_editing.py`: `_assign(session, person: Person, edit: PersonEdit) -> None` (validates and writes names, sex, display name, birth, death; no commit, no log). `update_person` keeps its behaviour and calls it.
- Produces in `relatives.py`: `RelativeError(PersonEditError)`, `RELATIONS`, `family_overview(session, person_id: UUID) -> dict`, `find_similar(session, given_name: str, surname: str, birth_surname: str, limit: int = 5) -> list[dict]`.

- [ ] **Step 1: Failing tests** `apps/api/tests/test_relatives.py` (the file grows in Task 3)

```python
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.genealogy.person_editing import LifeEventInput, PersonEdit
from app.genealogy.relatives import family_overview, find_similar
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
        for item in sorted([marriage, lonely], key=lambda record: str(record.id))
    ]
    assert (overview["can_add_parent"], overview["can_add_sibling"]) == (False, True)
    assert family_overview(session, wife.id)["can_add_sibling"] is False


def test_family_overview_of_a_missing_person_is_a_lookup_error(session):
    with pytest.raises(LookupError):
        family_overview(session, uuid4())


def test_similar_people_match_given_name_and_any_surname_including_hidden(session):
    by_surname = person(session, "Анна", "Иванова")
    by_birth = person(session, "Анна", "Петрова", birth_surname="Иванова")
    hidden = person(session, "Анна", "Ёлкина", archived=True)
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
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_relatives.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

In `person_editing.py`, move the body of `update_person` between the `try:` and `before = _snapshot(...)`/assignment into `_assign`, so that:

```python
def _assign(session: Session, person: Person, edit: PersonEdit) -> None:
    """Validate the form and write it into the person (no commit, no change log)."""
    names = {name: _clean(getattr(edit, name), MAX_NAME_LENGTH, "Часть имени") for name in NAME_FIELDS}
    if not names["given_name"] and not names["surname"]:
        raise PersonEditError("Укажите имя или фамилию.")
    if edit.sex not in (None, "M", "F"):
        raise PersonEditError("Неизвестное значение пола.")
    if edit.death_status not in ("unknown", "deceased"):
        raise PersonEditError("Неизвестное состояние смерти.")
    for name, value in names.items():
        setattr(person, name, value)
    person.sex = edit.sex
    person.display_name = compose_display_name(names["given_name"], names["patronymic"], names["surname"])
    _apply(session, person, "BIRT", edit.birth)
    _apply(session, person, "DEAT", (edit.death or LifeEventInput(None, None)) if edit.death_status == "deceased" else None)
```

and `update_person` becomes: lookup → `try:` `before = _snapshot(session, person)`; `_assign(session, person, edit)`; `session.flush()`; `after`/diff/log/commit as before → `except` rollback/raise. (Keep the exact error-precedence: `_assign` validates before writing anything.)

`apps/api/app/genealogy/relatives.py` (Task 3 appends `add_relative`):

```python
"""Owner adds relatives: family overview, duplicate search and relation rules."""

from collections import deque
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.genealogy.person_editing import PersonEditError
from app.genealogy.read_service import normalize_public_name, public_person_summary
from app.models.genealogy import ParentChild, Person, Union

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
```

Note for the overview test: `unions` are ordered by `Union.id` (UUID order); the test sorts by `str(id)` — if Postgres UUID order differs from string order, sort the test's expectation with `key=lambda record: record.id` instead. Do not change the service order.

- [ ] **Step 4:** `.venv/bin/pytest tests/test_relatives.py tests/test_person_editing.py -q` → PASS.

---

### Task 3: `add_relative`

**Files:**
- Modify: `apps/api/app/genealogy/relatives.py` (append)
- Test: `apps/api/tests/test_relatives.py` (append)

**Interfaces:**
- Consumes: `_assign`, `_snapshot`, `editable_person`, `PersonEdit` from `person_editing.py`.
- Produces: `add_relative(session, person_id: UUID, relation: str, new: PersonEdit | None, existing_id: UUID | None, union_id: UUID | None, owner_email: str) -> dict` returning `{"relation", "created", "person": editable_person(...)}`.

- [ ] **Step 1: Failing tests** (append to `test_relatives.py`; add `add_relative`, `RelativeError` to the import from `app.genealogy.relatives`)

```python
def parents_of(session, child):
    return {(link.parent_id, link.union_id) for link in session.query(ParentChild).filter_by(child_id=child.id)}


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

    with pytest.raises(RelativeError.__mro__[1], match="Укажите имя или фамилию"):
        add_relative(session, anchor.id, "spouse", new_person(" "), None, None, OWNER)
    assert session.query(Person).count() == 1


def test_hidden_people_can_be_linked(session):
    anchor, hidden = person(session, "Иван"), person(session, "Мария", archived=True)
    session.commit()

    result = add_relative(session, anchor.id, "spouse", None, hidden.id, None, OWNER)

    assert result["created"] is False and result["person"]["is_archived"] is True
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_relatives.py -q` → new tests FAIL (`ImportError: add_relative`).

- [ ] **Step 3: Implement** — append to `relatives.py` (extend the imports: `from app.genealogy.person_editing import PersonEdit, PersonEditError, _assign, _snapshot, editable_person` and `from app.models.genealogy import ChangeLog, ParentChild, Person, Union`):

```python
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
    if relative.id in _lineage(session, anchor.id, "up"):
        raise RelativeError("Нельзя сделать предка человека его ребёнком.")
    current = set(_parent_ids(session, relative.id))
    if anchor.id in current:
        raise RelativeError("Этот человек уже записан как ребёнок.")
    other = None
    if union_id is not None:
        chosen = session.get(Union, union_id)
        if chosen is None or anchor.id not in (chosen.partner_one_id, chosen.partner_two_id):
            raise RelativeError("Выбранный союз не принадлежит этому человеку.")
        other = chosen.partner_two_id if chosen.partner_one_id == anchor.id else chosen.partner_one_id
    new_parents = [parent for parent in (anchor.id, other) if parent is not None]
    if len(current | set(new_parents)) > 2:
        raise RelativeError("У этого человека уже есть родители.")
    for parent in new_parents:
        if parent not in current:
            _new_link(session, parent, relative.id, union_id, owner_email)


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
```

In `test_a_new_relative_with_an_invalid_form_is_refused`, `RelativeError.__mro__[1]` is `PersonEditError`; replace it with an explicit `from app.genealogy.person_editing import PersonEditError` import if clearer.

- [ ] **Step 4:** `.venv/bin/pytest tests/test_relatives.py -q && .venv/bin/pytest -q` → PASS.

---

### Task 4: Owner API routes

**Files:**
- Modify: `apps/api/app/api/routes/admin_genealogy.py`
- Test: `apps/api/tests/test_owner_genealogy_api.py`

**Interfaces:**
- Consumes: Task 2/3 services; stage-1 `PersonEditBody` and its conversion.
- Produces: `GET /api/v1/admin/people/similar`, `GET /api/v1/admin/people/{id}/family`, `POST /api/v1/admin/people/{id}/relatives` (201).

- [ ] **Step 1: Failing tests** (append; `FORM`, `login`, `create_person` exist from stage 1)

```python
def test_guests_cannot_add_relatives_or_see_family_tools(client, database_session):
    person = create_person(database_session)

    assert client.get("/api/v1/admin/people/similar?given_name=Анна&surname=Иванова").status_code == 401
    assert client.get(f"/api/v1/admin/people/{person.id}/family").status_code == 401
    assert client.post(f"/api/v1/admin/people/{person.id}/relatives", json={"relation": "spouse", "person": FORM}).status_code == 401


def test_owner_adds_a_new_spouse_and_sees_it_in_the_family(client, database_session):
    person = create_person(database_session)
    login(client)

    response = client.post(f"/api/v1/admin/people/{person.id}/relatives", json={"relation": "spouse", "person": FORM, "existing_id": None, "union_id": None})

    assert response.status_code == 201
    body = response.json()
    assert body["relation"] == "spouse" and body["created"] is True and body["person"]["display_name"] == "Анна Иванова"
    family = client.get(f"/api/v1/admin/people/{person.id}/family").json()
    assert [item["partner"]["display_name"] for item in family["unions"]] == ["Анна Иванова"]


def test_similar_route_is_not_taken_for_a_person_id(client, database_session):
    person = create_person(database_session)
    login(client)
    client.patch(f"/api/v1/admin/people/{person.id}", json=FORM)

    response = client.get("/api/v1/admin/people/similar?given_name=анна&surname=иванова")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(person.id)]


def test_relative_refusals_are_russian_422_and_missing_people_404(client, database_session):
    from uuid import uuid4

    person = create_person(database_session)
    login(client)

    both = client.post(f"/api/v1/admin/people/{person.id}/relatives", json={"relation": "spouse", "person": FORM, "existing_id": str(person.id)})
    missing = client.post(f"/api/v1/admin/people/{person.id}/relatives", json={"relation": "spouse", "existing_id": str(uuid4())})
    unknown_anchor = client.post(f"/api/v1/admin/people/{uuid4()}/relatives", json={"relation": "spouse", "person": FORM})

    assert (both.status_code, both.json()) == (422, {"detail": "Выберите нового или существующего человека."})
    assert (missing.status_code, missing.json()) == (404, {"detail": "Выбранный человек не найден."})
    assert unknown_anchor.status_code == 404
```

- [ ] **Step 2:** run the file → new tests FAIL.

- [ ] **Step 3: Implement** — read the current `admin_genealogy.py` first. Extract the stage-1 body→dataclass conversion used by the PATCH route into `def _edit(body: PersonEditBody) -> PersonEdit` and use it in both routes. Add (the `similar` route must be declared **above** `@router.get("/admin/people/{person_id}")`):

```python
from app.genealogy.relatives import add_relative, family_overview, find_similar


class RelativeBody(BaseModel):
    relation: Literal["child", "parent", "spouse", "sibling"]
    person: PersonEditBody | None = None
    existing_id: UUID | None = None
    union_id: UUID | None = None


@router.get("/admin/people/similar")
def similar_people(given_name: str = Query(default=""), surname: str = Query(default=""), birth_surname: str = Query(default=""), owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> list[dict]:
    return find_similar(session, given_name, surname, birth_surname)


@router.get("/admin/people/{person_id}/family")
def person_family(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return family_overview(session, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/admin/people/{person_id}/relatives", status_code=201)
def add_person_relative(person_id: UUID, body: RelativeBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return add_relative(session, person_id, body.relation, _edit(body.person) if body.person else None, body.existing_id, body.union_id, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (PersonEditError, DateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_owner_genealogy_api.py -q && .venv/bin/pytest -q` → PASS.

---

### Task 5: Web client and editor draft mode

**Files:**
- Modify: `apps/web/src/owner-api.ts`
- Modify: `apps/web/src/pages/person-editor.ts`
- Test: `apps/web/test/person-editor.test.ts`

**Interfaces:**
- Produces in `owner-api.ts`:

```ts
export type Relation = 'child' | 'parent' | 'spouse' | 'sibling'
export type PersonRef = { id: string; display_name: string }
export type FamilyOverview = { parents: PersonRef[]; unions: { union_id: string; partner: PersonRef | null }[]; can_add_parent: boolean; can_add_sibling: boolean }
export type AddRelativePayload = { relation: Relation; person: PersonEditPayload | null; existing_id: string | null; union_id: string | null }
export type AddRelativeResult = { relation: Relation; created: boolean; person: EditablePerson }
export const fetchFamily = (id: string) => request<FamilyOverview>(`/api/v1/admin/people/${id}/family`)
export const findSimilarPeople = (names: { given_name: string; surname: string; birth_surname: string }) => request<OwnerSearchResult[]>(`/api/v1/admin/people/similar?${new URLSearchParams(names)}`)
export const addRelative = (id: string, payload: AddRelativePayload) => request<AddRelativeResult>(`/api/v1/admin/people/${id}/relatives`, json('POST', payload))
```

- Produces on `<cats-person-editor>`: properties `draft: boolean` (default `false`) and `submitLabel: string` (default `''` → «Сохранить»). In draft: no request on connect (empty form), no hide/restore button, submit dispatches `person-draft` (`detail: PersonEditPayload`, bubbles, composed) after the existing client-side date validation instead of calling `savePerson`; every name input dispatches `draft-names` (`detail: { given_name, surname, birth_surname }` as raw strings). `editor-cancel` unchanged.

- [ ] **Step 1: Failing tests** (append to `apps/web/test/person-editor.test.ts`; it has `render`, `type`, `button`, `click`, `root`, `settle` helpers — read the file and reuse them; the draft editor needs its own small render because it must not fetch):

```ts
describe('cats-person-editor in draft mode', () => {
  async function renderDraft() {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const editor = document.createElement('cats-person-editor') as HTMLElement & { draft: boolean; submitLabel: string; updateComplete: Promise<boolean> }
    editor.draft = true
    editor.submitLabel = 'Добавить'
    document.body.append(editor)
    await editor.updateComplete
    return { editor, fetchMock }
  }

  it('starts empty, without hiding, and never calls the API', async () => {
    const { editor, fetchMock } = await renderDraft()

    expect((editor.shadowRoot!.querySelector('[name="given_name"]') as HTMLInputElement).value).toBe('')
    expect([...editor.shadowRoot!.querySelectorAll('button')].map((item) => item.textContent?.trim())).toEqual(['Добавить', 'Отмена'])
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('hands the filled form to its parent and reports names as they are typed', async () => {
    const { editor, fetchMock } = await renderDraft()
    const drafts: unknown[] = [], names: unknown[] = []
    editor.addEventListener('person-draft', (event) => drafts.push((event as CustomEvent).detail))
    editor.addEventListener('draft-names', (event) => names.push((event as CustomEvent).detail))

    type(editor as never, 'given_name', 'Мария')
    type(editor as never, 'surname', 'Иванова')
    await editor.updateComplete
    await click(editor as never, 'Добавить')

    expect(names.at(-1)).toEqual({ given_name: 'Мария', surname: 'Иванова', birth_surname: '' })
    expect(drafts).toEqual([{ surname: 'Иванова', given_name: 'Мария', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, place: null, date_text_keep: false } }])
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
```

- [ ] **Step 2:** `cd apps/web && npx vitest run test/person-editor.test.ts` → new tests FAIL.

- [ ] **Step 3: Implement** in `person-editor.ts`:
  - `static properties` add `draft: { attribute: false }, submitLabel: { attribute: false }`; `declare draft: boolean; declare submitLabel: string`; constructor `this.draft = false; this.submitLabel = ''`.
  - Constant `const EMPTY_PERSON: EditablePerson = { id: '', display_name: '', is_archived: false, surname: null, given_name: null, patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } }`.
  - `connectedCallback`: `if (this.draft) this.fill(EMPTY_PERSON); else void this.load()`.
  - `save()`: after the date validation loop, `if (this.draft) { this.dispatchEvent(new CustomEvent('person-draft', { detail: this.payload(), bubbles: true, composed: true })); return }`.
  - `nameField` input handler: after updating `this.names`, `if (this.draft) this.dispatchEvent(new CustomEvent('draft-names', { detail: { given_name: this.names.given_name, surname: this.names.surname, birth_surname: this.names.birth_surname }, bubbles: true, composed: true }))`.
  - `render()`: hide-banner and the danger button only when `!this.draft`; submit text `${this.busy ? 'Сохраняем…' : this.submitLabel || 'Сохранить'}`.
  - Add the `owner-api.ts` types and functions from Interfaces.

- [ ] **Step 4:** `npx vitest run test/person-editor.test.ts && npm run typecheck` → PASS.

---

### Task 6: Relative adder panel

**Files:**
- Create: `apps/web/src/pages/relative-adder.ts`
- Test: `apps/web/test/relative-adder.test.ts`

**Interfaces:**
- Consumes: Task 5 client functions and draft editor; `searchOwnerPeople`.
- Produces `<cats-relative-adder>`: properties `personId: string`, `relation: Relation`, `similarDelay: number` (default 300; tests set 0). Events (bubbles, composed): `relative-added` (`detail: AddRelativeResult`), `adder-cancel`. DOM contract for tests: heading `h3` («Добавить ребёнка» / «Добавить родителя» / «Добавить супруга» / «Добавить брата или сестру»); radios `input[name="other-parent"]` with `value` = union id or `""` («Второй родитель неизвестен»), only for `child`; mode buttons «Новый человек» / «Уже есть в архиве» with `aria-pressed`; `.similar` block with «Возможно, это уже есть в архиве» and «Выбрать» buttons; `input[name="relative-search"]` and result buttons «Выбрать»; `.chosen` «Выбрано: …» with «Изменить выбор» and «Добавить»; `.blocked` text when the relation is unavailable; `[role="alert"]` for errors; «Отмена» button.

- [ ] **Step 1: Failing tests** `apps/web/test/relative-adder.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/relative-adder'
import type { FamilyOverview, Relation } from '../src/owner-api'

type Adder = HTMLElement & { personId: string; relation: Relation; similarDelay: number; updateComplete: Promise<boolean> }
const settle = async (element: Adder) => { for (let index = 0; index < 3; index += 1) { await new Promise((resolve) => setTimeout(resolve, 0)); await element.updateComplete } }
const FAMILY: FamilyOverview = {
  parents: [{ id: 'mom', display_name: 'Анна' }],
  unions: [{ union_id: 'u1', partner: { id: 'wife', display_name: 'Мария' } }],
  can_add_parent: true, can_add_sibling: true,
}
const ADDED = { relation: 'child', created: true, person: { id: 'new', display_name: 'Иван Петров' } }

function api(family: FamilyOverview = FAMILY, add: () => Response = () => new Response(JSON.stringify(ADDED), { status: 201 })) {
  return vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('/family')) return Promise.resolve(new Response(JSON.stringify(family)))
    if (url.includes('/similar?')) return Promise.resolve(new Response(JSON.stringify([{ id: 'dup', display_name: 'Иван Петров', years: '1950 – ?', is_archived: false }])))
    if (url.includes('/admin/people?query=')) return Promise.resolve(new Response(JSON.stringify([{ id: 'p1', display_name: 'Пётр', years: null, is_archived: false }, { id: 'old', display_name: 'Олег', years: null, is_archived: true }])))
    if (init?.method === 'POST') return Promise.resolve(add())
    return Promise.resolve(new Response('{}', { status: 404 }))
  })
}
async function render(relation: Relation, fetchMock = api()) {
  vi.stubGlobal('fetch', fetchMock)
  const adder = document.createElement('cats-relative-adder') as Adder
  adder.personId = 'p1'
  adder.relation = relation
  adder.similarDelay = 0
  document.body.append(adder)
  await settle(adder)
  return { adder, fetchMock }
}
const root = (adder: Adder) => adder.shadowRoot!
const button = (adder: Adder, text: string) => [...root(adder).querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement | undefined
const editor = (adder: Adder) => root(adder).querySelector('cats-person-editor') as HTMLElement
const postBody = (fetchMock: ReturnType<typeof api>) => JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')![1]!.body))
const DRAFT = { surname: 'Петров', given_name: 'Иван', patronymic: null, birth_surname: null, sex: 'M', birth: null, death: { status: 'unknown', date: null, place: null, date_text_keep: false } }

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-relative-adder', () => {
  it('adds a new child of the only union, preselected', async () => {
    const { adder, fetchMock } = await render('child')
    const added = vi.fn()
    adder.addEventListener('relative-added', added)

    expect(root(adder).querySelector('h3')?.textContent).toBe('Добавить ребёнка')
    expect((root(adder).querySelector('input[name="other-parent"][value="u1"]') as HTMLInputElement).checked).toBe(true)
    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1/relatives', expect.objectContaining({ method: 'POST' }))
    expect(postBody(fetchMock)).toEqual({ relation: 'child', person: DRAFT, existing_id: null, union_id: 'u1' })
    expect(added).toHaveBeenCalledWith(expect.objectContaining({ detail: ADDED }))
  })

  it('lets the owner say the other parent is unknown', async () => {
    const { adder, fetchMock } = await render('child')
    const unknown = root(adder).querySelector('input[name="other-parent"][value=""]') as HTMLInputElement
    unknown.checked = true
    unknown.dispatchEvent(new Event('change'))
    await adder.updateComplete

    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(postBody(fetchMock).union_id).toBeNull()
  })

  it('warns about a possible duplicate and adds the existing person instead', async () => {
    const { adder, fetchMock } = await render('spouse')
    expect(root(adder).querySelector('input[name="other-parent"]')).toBeNull()

    editor(adder).dispatchEvent(new CustomEvent('draft-names', { detail: { given_name: 'Иван', surname: 'Петров', birth_surname: '' }, bubbles: true, composed: true }))
    await settle(adder)
    expect(root(adder).querySelector('.similar')?.textContent).toContain('Возможно, это уже есть в архиве')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/similar?given_name=%D0%98%D0%B2%D0%B0%D0%BD&surname=%D0%9F%D0%B5%D1%82%D1%80%D0%BE%D0%B2&birth_surname=')

    root(adder).querySelector('.similar button')!.dispatchEvent(new MouseEvent('click'))
    await settle(adder)
    expect(root(adder).querySelector('.chosen')?.textContent).toContain('Иван Петров')
    button(adder, 'Добавить')!.click()
    await settle(adder)

    expect(postBody(fetchMock)).toEqual({ relation: 'spouse', person: null, existing_id: 'dup', union_id: null })
  })

  it('finds an existing person, never offers the person themselves, and marks hidden ones', async () => {
    const { adder } = await render('parent')
    button(adder, 'Уже есть в архиве')!.click()
    await adder.updateComplete
    const search = root(adder).querySelector('input[name="relative-search"]') as HTMLInputElement
    search.value = 'О'
    search.dispatchEvent(new Event('input'))
    await settle(adder)

    const results = [...root(adder).querySelectorAll('.results li')].map((item) => item.textContent?.replace(/\s+/g, ' ').trim())
    expect(results).toEqual(['Олег скрыт Выбрать'])
  })

  it('explains why a relation is not available', async () => {
    const { adder } = await render('parent', api({ ...FAMILY, can_add_parent: false }))
    expect(root(adder).querySelector('.blocked')?.textContent).toContain('У человека уже два родителя')
    expect(editor(adder)).toBeNull()

    adder.relation = 'sibling'
    await settle(adder)
    expect(root(adder).querySelector('.blocked')).toBeNull()
  })

  it('shows the server reason and keeps the panel open', async () => {
    const { adder } = await render('spouse', api(FAMILY, () => new Response(JSON.stringify({ detail: 'Эти люди уже в союзе.' }), { status: 422 })))

    editor(adder).dispatchEvent(new CustomEvent('person-draft', { detail: DRAFT, bubbles: true, composed: true }))
    await settle(adder)

    expect(root(adder).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Эти люди уже в союзе.')
    expect(editor(adder)).not.toBeNull()
  })

  it('resets its choices when the relation changes', async () => {
    const { adder } = await render('spouse')
    editor(adder).dispatchEvent(new CustomEvent('draft-names', { detail: { given_name: 'Иван', surname: 'Петров', birth_surname: '' }, bubbles: true, composed: true }))
    await settle(adder)
    root(adder).querySelector('.similar button')!.dispatchEvent(new MouseEvent('click'))
    await settle(adder)

    adder.relation = 'child'
    await settle(adder)

    expect(root(adder).querySelector('.chosen')).toBeNull()
    expect(root(adder).querySelector('.similar')).toBeNull()
    expect(button(adder, 'Новый человек')?.getAttribute('aria-pressed')).toBe('true')
  })

  it('cancels', async () => {
    const { adder } = await render('spouse')
    const cancelled = vi.fn()
    adder.addEventListener('adder-cancel', cancelled)

    button(adder, 'Отмена')!.click()

    expect(cancelled).toHaveBeenCalledTimes(1)
  })
})
```

The draft editor's own «Отмена» emits `editor-cancel`; the adder forwards it as `adder-cancel`. The adder also renders its own «Отмена» for the «Уже есть в архиве» mode; the cancel test is in «Новый человек» mode, where the only «Отмена» in the adder's own shadow root is the adder's — make the adder render its «Отмена» button in both modes.

- [ ] **Step 2:** `npx vitest run test/relative-adder.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement** `apps/web/src/pages/relative-adder.ts`

```ts
import { LitElement, css, html } from 'lit'

import './person-editor'
import { addRelative, fetchFamily, findSimilarPeople, searchOwnerPeople, type FamilyOverview, type OwnerSearchResult, type PersonEditPayload, type Relation } from '../owner-api'

const TITLES: Record<Relation, string> = { child: 'Добавить ребёнка', parent: 'Добавить родителя', spouse: 'Добавить супруга', sibling: 'Добавить брата или сестру' }

export class CatsRelativeAdder extends LitElement {
  static properties = { personId: { attribute: false }, relation: { attribute: false }, family: { state: true }, mode: { state: true }, unionId: { state: true }, similar: { state: true }, results: { state: true }, chosen: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  declare relation: Relation
  private declare family: FamilyOverview | null
  private declare mode: 'new' | 'existing'
  private declare unionId: string | null
  private declare similar: OwnerSearchResult[]
  private declare results: OwnerSearchResult[]
  private declare chosen: OwnerSearchResult | null
  private declare error: string
  private declare busy: boolean
  similarDelay = 300
  private similarTimer: number | undefined

  constructor() {
    super()
    this.personId = ''; this.relation = 'child'; this.family = null; this.mode = 'new'; this.unionId = null
    this.similar = []; this.results = []; this.chosen = null; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; margin-top:1rem; padding:1rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; background:var(--sheet,#fff); }
    h3 { margin:0 0 1rem; }
    .row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; margin-bottom:1rem; }
    fieldset { border:0; padding:0; margin:0 0 1rem; display:grid; gap:.35rem; }
    button { min-height:2.25rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 .9rem; background:#fff; font:600 .85rem Inter,system-ui,sans-serif; cursor:pointer; }
    button[aria-pressed="true"],button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    input[name="relative-search"] { height:2.5rem; width:min(24rem,100%); border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; }
    ul { list-style:none; padding:0; margin:.5rem 0; display:grid; gap:.35rem; }
    li { display:flex; gap:.5rem; align-items:center; }
    .tag { font-size:.75rem; color:#7d2b20; }
    .similar { background:#f7f3e6; border:1px solid #e6dcb8; padding:.75rem; border-radius:3px; margin-bottom:1rem; }
    [role="alert"] { color:#7d2b20; }
  `

  connectedCallback() { super.connectedCallback(); void this.loadFamily() }

  willUpdate(changed: Map<string, unknown>) {
    if (changed.has('relation') && changed.get('relation') !== undefined) this.reset()
  }

  private reset() {
    this.mode = 'new'; this.similar = []; this.results = []; this.chosen = null; this.error = ''
    this.unionId = this.relation === 'child' && this.family?.unions.length === 1 ? this.family.unions[0].union_id : null
  }

  private async loadFamily() {
    const result = await fetchFamily(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.family = result.value
    this.reset()
  }

  private blocked(): string {
    if (!this.family) return ''
    if (this.relation === 'parent' && !this.family.can_add_parent) return 'У человека уже два родителя.'
    if (this.relation === 'sibling' && !this.family.can_add_sibling) return 'У человека не указаны родители — сначала добавьте родителя.'
    return ''
  }

  private onNames(names: { given_name: string; surname: string; birth_surname: string }) {
    window.clearTimeout(this.similarTimer)
    this.similarTimer = window.setTimeout(async () => {
      if (!names.given_name.trim() || !(names.surname.trim() || names.birth_surname.trim())) { this.similar = []; return }
      const result = await findSimilarPeople(names)
      this.similar = result.ok ? result.value.filter((item) => item.id !== this.personId) : []
    }, this.similarDelay)
  }

  private async search(query: string) {
    if (!query.trim()) { this.results = []; return }
    const result = await searchOwnerPeople(query)
    this.results = result.ok ? result.value.filter((item) => item.id !== this.personId) : []
  }

  private choose(item: OwnerSearchResult) { this.chosen = item; this.mode = 'existing' }

  private async submit(person: PersonEditPayload | null) {
    if (this.busy) return
    this.busy = true; this.error = ''
    const result = await addRelative(this.personId, {
      relation: this.relation, person, existing_id: person ? null : this.chosen?.id ?? null, union_id: this.relation === 'child' ? this.unionId : null,
    })
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.dispatchEvent(new CustomEvent('relative-added', { detail: result.value, bubbles: true, composed: true }))
  }

  private cancel() { this.dispatchEvent(new CustomEvent('adder-cancel', { bubbles: true, composed: true })) }

  private person(item: OwnerSearchResult) {
    return html`${item.display_name}${item.years ? html` <span class="years">${item.years}</span>` : ''}${item.is_archived ? html` <span class="tag">скрыт</span>` : ''}`
  }

  private otherParent() {
    if (this.relation !== 'child' || !this.family) return ''
    const pick = (value: string | null) => () => { this.unionId = value }
    return html`<fieldset><legend>Второй родитель</legend>
      ${this.family.unions.map((item) => html`<label><input type="radio" name="other-parent" value=${item.union_id} .checked=${this.unionId === item.union_id} @change=${pick(item.union_id)} /> ${item.partner?.display_name ?? 'Партнёр не указан'}</label>`)}
      <label><input type="radio" name="other-parent" value="" .checked=${this.unionId === null} @change=${pick(null)} /> Второй родитель неизвестен</label>
    </fieldset>`
  }

  private newPerson() {
    return html`
      ${this.similar.length ? html`<div class="similar"><strong>Возможно, это уже есть в архиве:</strong><ul>${this.similar.map((item) => html`<li>${this.person(item)} <button type="button" @click=${() => this.choose(item)}>Выбрать</button></li>`)}</ul></div>` : ''}
      <cats-person-editor .draft=${true} .submitLabel=${'Добавить'} @person-draft=${(event: CustomEvent<PersonEditPayload>) => this.submit(event.detail)} @draft-names=${(event: CustomEvent) => this.onNames(event.detail)} @editor-cancel=${this.cancel}></cats-person-editor>`
  }

  private existingPerson() {
    if (this.chosen) {
      return html`<p class="chosen">Выбрано: ${this.person(this.chosen)}</p>
        <div class="row"><button class="primary" type="button" ?disabled=${this.busy} @click=${() => this.submit(null)}>Добавить</button><button type="button" @click=${() => { this.chosen = null }}>Изменить выбор</button></div>`
    }
    return html`<input name="relative-search" type="search" placeholder="Имя или фамилия" aria-label="Найти человека в архиве" @input=${(event: Event) => this.search((event.target as HTMLInputElement).value)} />
      <ul class="results">${this.results.map((item) => html`<li>${this.person(item)} <button type="button" @click=${() => this.choose(item)}>Выбрать</button></li>`)}</ul>`
  }

  render() {
    const title = html`<h3>${TITLES[this.relation]}</h3>`
    if (!this.family) return html`${title}${this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`}`
    const blocked = this.blocked()
    if (blocked) return html`${title}<p class="blocked">${blocked}</p><button type="button" @click=${this.cancel}>Отмена</button>`
    return html`${title}${this.otherParent()}
      <div class="row">
        <button type="button" aria-pressed=${String(this.mode === 'new')} @click=${() => { this.mode = 'new' }}>Новый человек</button>
        <button type="button" aria-pressed=${String(this.mode === 'existing')} @click=${() => { this.mode = 'existing' }}>Уже есть в архиве</button>
        <button type="button" @click=${this.cancel}>Отмена</button>
      </div>
      ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
      ${this.mode === 'new' ? this.newPerson() : this.existingPerson()}`
  }
}

customElements.define('cats-relative-adder', CatsRelativeAdder)
```

- [ ] **Step 4:** `npx vitest run test/relative-adder.test.ts && npm run typecheck` → PASS.

---

### Task 7: Person page integration

**Files:**
- Modify: `apps/web/src/pages/person-card.ts`
- Test: `apps/web/test/person-card.test.ts`

**Interfaces:**
- Consumes: `<cats-relative-adder>` (Task 6).
- Produces: in the «Семья» section, for the owner only, `.add-relative` with heading «Добавить родственника» and buttons «Ребёнка», «Родителя», «Супруга», «Брата или сестру»; the adder below them; after `relative-added` a status «Добавлено: <a href="/people/{id}">Имя</a>» and a `person-changed` event.

- [ ] **Step 1: Failing tests** (append to `person-card.test.ts`; the file has a `person` fixture since stage 1 — read it and reuse):

```ts
it('offers adding relatives only to the owner and reports the added person', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ parents: [], unions: [], can_add_parent: true, can_add_sibling: false }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  document.body.append(card)
  await card.updateComplete
  expect(card.shadowRoot!.querySelector('.add-relative')).toBeNull()

  card.isOwner = true
  await card.updateComplete
  const changed = vi.fn()
  card.addEventListener('person-changed', changed)
  ;[...card.shadowRoot!.querySelectorAll('.add-relative button')].find((item) => item.textContent?.trim() === 'Супруга')!.dispatchEvent(new MouseEvent('click'))
  await card.updateComplete
  const adder = card.shadowRoot!.querySelector('cats-relative-adder') as HTMLElement & { relation: string }
  expect(adder.relation).toBe('spouse')

  adder.dispatchEvent(new CustomEvent('relative-added', { detail: { relation: 'spouse', created: true, person: { id: 'new', display_name: 'Мария Иванова' } }, bubbles: true, composed: true }))
  await card.updateComplete

  expect(card.shadowRoot!.querySelector('cats-relative-adder')).toBeNull()
  expect(card.shadowRoot!.querySelector('.add-relative [role="status"] a')?.getAttribute('href')).toBe('/people/new')
  expect(changed).toHaveBeenCalledTimes(1)
})
```

- [ ] **Step 2:** `npx vitest run test/person-card.test.ts` → FAIL.

- [ ] **Step 3: Implement** in `person-card.ts`:
  - `import './relative-adder'` and `import type { Relation } from '../owner-api'`.
  - State `adding: Relation | null` (default `null`), `added: { id: string; display_name: string } | null` (default `null`); reset both when `isOwner` becomes false (same `willUpdate` place that closes the editor).
  - In the `#family` section, after the family columns: `${this.isOwner ? this.renderAdder() : nothing}` with

```ts
  private renderAdder() {
    const choices: [Relation, string][] = [['child', 'Ребёнка'], ['parent', 'Родителя'], ['spouse', 'Супруга'], ['sibling', 'Брата или сестру']]
    return html`<div class="add-relative"><h3>Добавить родственника</h3>
      <div class="actions">${choices.map(([relation, label]) => html`<button class="button" aria-pressed=${String(this.adding === relation)} @click=${() => { this.adding = relation; this.added = null }}>${label}</button>`)}</div>
      ${this.added ? html`<p class="saved" role="status">Добавлено: <a href="/people/${this.added.id}">${this.added.display_name}</a></p>` : nothing}
      ${this.adding ? html`<cats-relative-adder .personId=${this.person.id} .relation=${this.adding} @relative-added=${this.onRelativeAdded} @adder-cancel=${() => { this.adding = null }}></cats-relative-adder>` : nothing}
    </div>`
  }

  private onRelativeAdded = (event: CustomEvent<{ person: { id: string; display_name: string } }>) => {
    this.added = event.detail.person
    this.adding = null
    this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true }))
  }
```

  - Style `.add-relative { margin-top:32px; } .add-relative .actions { display:flex; gap:8px; flex-wrap:wrap; }` (reuse existing `.button` look).

- [ ] **Step 4:** `npm test && npm run typecheck` → PASS.

---

### Task 8: End-to-end check, docs, migration on the real database, final verification

**Files:**
- Modify: `apps/web/e2e/owner-login.spec.ts` (append)
- Modify: `README.md` (after «Исправление людей»)

- [ ] **Step 1: E2E** (append; skipped without the owner password; never saves):

```ts
test('the owner opens «Добавить ребёнка» for a real person and cancels', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the add-relative check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  await page.getByRole('button', { name: 'Ребёнка' }).click()
  await expect(page.getByRole('heading', { name: 'Добавить ребёнка' })).toBeVisible()
  await expect(page.getByText('Второй родитель неизвестен')).toBeVisible()
  await page.locator('cats-relative-adder').getByRole('button', { name: 'Отмена' }).first().click()
  await expect(page.getByRole('heading', { name: 'Добавить ребёнка' })).toHaveCount(0)
})
```

- [ ] **Step 2: README** — add after «Исправление людей»:

```markdown
### Добавление родственников

На странице человека владелец видит блок «Добавить родственника»: ребёнка,
родителя, супруга, брата или сестру. Родственника можно ввести как нового
человека или выбрать из архива; при вводе нового сайт показывает возможные
дубли. Для ребёнка выбирается второй родитель или «неизвестен». Каждое
добавление выполняется целиком или не выполняется совсем и пишется в журнал
правок. Резервная копия сохраняет части имени и людей, добавленных на сайте.
```

- [ ] **Step 3: Restart the stack** (Ctrl-C in the «Cat's House dev» tab; `CATS_HOUSE_WEB_PORT=5176 bash scripts/dev-native.sh`) — this applies migration `0008`. Make a backup first (`scripts/create-local-backup.py --output "/Users/ekoshkin/Cat's House backups"` with the `.env` loaded as `dev-native.sh` does). Confirm `alembic_version` is `0008_owner_created_records` and that `GET /api/v1/admin/people/similar` answers 401 to a guest.

- [ ] **Step 4: Final verification** — each exits 0:

```bash
cd apps/api && .venv/bin/pytest -q
cd apps/web && npm test && npm run typecheck && npm run build && npm run test:e2e
```

Manual check at `http://localhost:5176` with the owner signed in: open «Петр Николаевич Кошкин», «Ребёнка» → second-parent choice shows «Мария Николаевна Архипова» preselected; type «Юрий» / «Кошкин» → the duplicate warning lists «Юрий Петрович Кошкин»; press «Отмена». Do not add real people unless the owner asks.

- [ ] **Step 5: Hand over** — independent whole-branch review, fix Critical/Important via RED→GREEN, report rulings and deferred minors; ask before commit/merge/push.
