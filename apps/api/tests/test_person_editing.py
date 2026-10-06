from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.genealogy.dates import DateError, DatePoint, DateValue
from app.genealogy.person_editing import LifeEventInput, PersonEdit, PersonEditError, editable_person, owner_search, update_person
from app.genealogy.write_service import archive_person, restore_person
from app.models.genealogy import Base, ChangeLog, Event, ImportRun, Person

OWNER = "owner@example.test"


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def petr(session):
    run = ImportRun(original_filename="archive.json", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    person = Person(import_run_id=run.id, display_name="Петр Николаевич Кошкин", source_uid="A_11", surname="Кошкин", given_name="Петр", patronymic="Николаевич", sex="M")
    session.add(person)
    session.flush()
    session.add_all([
        Event(person_id=person.id, event_type="BIRT", date_text="1901", date_qualifier="exact", date_lower=date(1901, 1, 1), date_upper=date(1901, 12, 31)),
        Event(person_id=person.id, event_type="DEAT", date_text="1944", date_qualifier="exact", date_lower=date(1944, 1, 1), date_upper=date(1944, 12, 31)),
    ])
    session.commit()
    return person


def unchanged_edit(**changes) -> PersonEdit:
    values = dict(
        surname="Кошкин", given_name="Петр", patronymic="Николаевич", birth_surname=None, sex="M",
        birth=LifeEventInput(DateValue("exact", DatePoint(1901)), None),
        death_status="deceased", death=LifeEventInput(DateValue("exact", DatePoint(1944)), None),
    )
    values.update(changes)
    return PersonEdit(**values)


def life_events(session, person, kind):
    return session.query(Event).filter_by(person_id=person.id, event_type=kind).all()


def test_reads_the_form_with_structured_dates(session, petr):
    form = editable_person(session, petr.id)

    assert form["given_name"] == "Петр" and form["is_archived"] is False
    assert form["birth"] == {"date": {"qualifier": "exact", "year": 1901, "month": None, "day": None, "end": None}, "date_text": "1901", "place": None}
    assert form["death"]["status"] == "deceased" and form["death"]["date_text"] == "1944"


def test_saves_names_dates_places_and_logs_only_changed_fields(session, petr):
    edit = unchanged_edit(
        given_name="  Пётр ", birth_surname="Иванов",
        birth=LifeEventInput(DateValue("about", DatePoint(1901, 4)), "  Москва  "),
    )

    form = update_person(session, petr.id, edit, OWNER)

    assert form["display_name"] == "Пётр Николаевич Кошкин"
    assert form["birth_surname"] == "Иванов"
    birth = life_events(session, petr, "BIRT")[0]
    assert (birth.date_text, birth.date_qualifier, birth.place) == ("ABT APR 1901", "about", "Москва")
    entry = session.query(ChangeLog).one()
    assert set(entry.after) == {"given_name", "birth_surname", "display_name", "birth"}
    assert entry.before["given_name"] == "Петр" and entry.after["given_name"] == "Пётр"
    assert entry.after["birth"] == {"date_text": "ABT APR 1901", "place": "Москва"}


def test_a_save_without_changes_writes_no_log(session, petr):
    update_person(session, petr.id, unchanged_edit(), OWNER)

    assert session.query(ChangeLog).count() == 0


def test_death_has_three_states(session, petr):
    update_person(session, petr.id, unchanged_edit(death=LifeEventInput(None, None)), OWNER)
    assert [(event.date_text, event.date_lower) for event in life_events(session, petr, "DEAT")] == [(None, None)]

    update_person(session, petr.id, unchanged_edit(death_status="unknown", death=None), OWNER)
    assert life_events(session, petr, "DEAT") == []
    assert editable_person(session, petr.id)["death"] == {"status": "unknown", "date": None, "date_text": None, "place": None}

    update_person(session, petr.id, unchanged_edit(), OWNER)
    assert [event.date_text for event in life_events(session, petr, "DEAT")] == ["1944"]


def test_birth_can_be_removed_and_created(session, petr):
    update_person(session, petr.id, unchanged_edit(birth=None), OWNER)
    assert life_events(session, petr, "BIRT") == []

    update_person(session, petr.id, unchanged_edit(birth=LifeEventInput(DateValue("exact", DatePoint(1901, 2, 3)), None)), OWNER)
    assert [event.date_text for event in life_events(session, petr, "BIRT")] == ["3 FEB 1901"]


def test_an_unparsed_stored_date_is_kept_when_asked(session, petr):
    birth = life_events(session, petr, "BIRT")[0]
    birth.date_text = "весной 1901"
    session.commit()
    form = editable_person(session, petr.id)
    assert form["birth"]["date"] is None and form["birth"]["date_text"] == "весной 1901"

    update_person(session, petr.id, unchanged_edit(given_name="Пётр", birth=LifeEventInput(None, "Тула", keep_date_text=True)), OWNER)

    birth = life_events(session, petr, "BIRT")[0]
    assert (birth.date_text, birth.place) == ("весной 1901", "Тула")


@pytest.mark.parametrize(
    ("changes", "error", "message"),
    [
        (dict(given_name=" ", surname=None), PersonEditError, "Укажите имя или фамилию"),
        (dict(sex="X"), PersonEditError, "пола"),
        (dict(surname="К" * 256), PersonEditError, "255"),
        (dict(birth=LifeEventInput(DateValue("exact", DatePoint(1901)), "М" * 513)), PersonEditError, "512"),
        (dict(birth=LifeEventInput(DateValue("exact", DatePoint(1901, 2, 30)), None)), DateError, "нет такого дня"),
    ],
)
def test_invalid_saves_change_nothing(session, petr, changes, error, message):
    with pytest.raises(error, match=message):
        update_person(session, petr.id, unchanged_edit(**changes), OWNER)

    session.expire_all()
    assert petr.given_name == "Петр" and session.query(ChangeLog).count() == 0
    assert [event.date_text for event in life_events(session, petr, "BIRT")] == ["1901"]


def test_duplicate_life_events_block_the_save(session, petr):
    session.add(Event(person_id=petr.id, event_type="BIRT", date_text="1902"))
    session.commit()

    with pytest.raises(PersonEditError, match="несколько событий рождения"):
        update_person(session, petr.id, unchanged_edit(given_name="Пётр"), OWNER)


def test_missing_person_is_a_lookup_error(session, petr):
    from uuid import uuid4

    with pytest.raises(LookupError):
        editable_person(session, uuid4())


def test_hidden_people_are_found_by_the_owner_and_can_be_restored(session, petr):
    archive_person(session, petr.id, OWNER)

    results = owner_search(session, "кошкин")
    assert [(item["display_name"], item["is_archived"], item["years"]) for item in results] == [("Петр Николаевич Кошкин", True, "1901 – 1944")]
    assert editable_person(session, petr.id)["is_archived"] is True

    restore_person(session, petr.id, OWNER)
    assert owner_search(session, "")[0]["is_archived"] is False
    assert [entry.after for entry in session.query(ChangeLog).order_by(ChangeLog.created_at)][-1] == {"is_archived": False}


def test_owner_search_also_matches_the_birth_surname(session, petr):
    petr.birth_surname = "Ёлкин"
    session.commit()

    assert [item["display_name"] for item in owner_search(session, "елкин")] == ["Петр Николаевич Кошкин"]
