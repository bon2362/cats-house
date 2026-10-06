# Person Editing Implementation Plan (owner editor, stage 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The signed-in owner corrects an existing person — name parts, sex, birth and death (date with precision and qualifier, place, «died, date unknown»), hides and restores people — and every save is logged.

**Architecture:** New name columns on `people` plus a one-time backfill from AT5. A pure `dates.py` module converts structured dates ↔ stored GEDCOM-style text/bounds ↔ Russian labels and is used by the editor service, the public API and the tree. A `person_editing.py` service applies a whole-form save in one transaction with one change-log entry. The web app gets an owner API client, a date input, a person editor, and owner-only entry points (person page, tree inspector, header search, hidden person page).

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, pytest + testcontainers (Docker); Lit, TypeScript, Vitest (jsdom), Playwright (installed Google Chrome).

**Spec:** `docs/superpowers/specs/2026-10-06-person-editing-design.md` (read it first; it is the authority). Stage 0 context: `docs/superpowers/specs/2026-10-06-owner-access-design.md`.

## Global Constraints

- All user-visible text is Russian. API validation errors: `422` with a Russian string in `detail`.
- Owner endpoints use `Depends(require_owner)`; guests get `401`.
- `display_name` = non-empty parts joined as «Имя Отчество Фамилия»; `birth_surname` is never part of it.
- Saving requires `given_name` or `surname`. Name parts ≤ 255 chars, place ≤ 512 chars; whitespace collapsed, empty → `null`.
- Dates: qualifiers `exact|about|before|after|between`; year 1000…current year; day only with month; `between` end strictly after start; Gregorian only.
- Stored text forms: `6 APR 1926`, `APR 1926`, `1926`, `ABT …`, `BEF …`, `AFT …`, `BET … AND …`. Bounds: exact/about → full span of the precision; before → `lower=None`, `upper=first day − 1`; after → `lower=last day + 1`, `upper=None`; between → start of first … end of second.
- Russian labels: `6 апреля 1926`, `март 2004`, `ок. 1900`, `до марта 1944`, `после 1950`, `между 1900 и 1905`, `между мартом 1900 и маем 1905`.
- One BIRT and one DEAT event per person; more than one → `422` «У человека несколько событий рождения — исправьте их отдельно.» (смерти for DEAT).
- One save = at most one `change_logs` row (`entity_type="person"`) with only changed keys; unchanged save writes nothing.
- Public pages unchanged for hidden people (tree «Сведения скрыты», person 404).
- The e2e test never saves (real data). Never run `--apply` on the real database without asking the owner, and make a backup first (`scripts/create-local-backup.py`).
- Follow existing patterns: Lit `static styles = css\`…\``, no new dependencies, Alembic migrations idempotent via `sa.inspect`.
- Do not commit unless the owner asks (project rule). Work on branch `feature/person-editing`.

## Review Focus

1. A person with a stored date that does not parse (free text from some future import) must open in the editor and save other fields without losing that date — Task 5 (`keep_date_text`) and Task 8.
2. Switching death from «date» to «нет сведений» must delete the DEAT event, and the tree/home must stop showing the person as deceased — Task 5.
3. Archived people must stay invisible to guests in every public endpoint after this change (search with `birth_surname` must still filter `is_archived`) — Task 6.
4. February 29 in a non-leap year, day 31 in a 30-day month, and a `between` whose end equals start must all be rejected with Russian messages — Task 2.
5. The editor must not lose typed values when the server rejects a save — Task 8.

---

### Task 1: Name columns on `people`

**Files:**
- Create: `apps/api/alembic/versions/0006_person_name_parts.py`
- Modify: `apps/api/app/models/genealogy.py` (class `Person`)
- Test: `apps/api/tests/test_migrations.py`

**Interfaces:**
- Produces: `Person.surname`, `Person.given_name`, `Person.patronymic`, `Person.birth_surname` — `Mapped[str | None]`, `String(255)`, nullable.

- [ ] **Step 1: Failing test** — append to `apps/api/tests/test_migrations.py`:

```python
def test_people_have_optional_name_parts_after_upgrade(postgres_url):
    upgrade_database(postgres_url)

    columns = {column["name"]: column for column in inspect(create_engine(postgres_url)).get_columns("people")}

    for name in ("surname", "given_name", "patronymic", "birth_surname"):
        assert columns[name]["nullable"] is True
```

- [ ] **Step 2:** `cd apps/api && .venv/bin/pytest tests/test_migrations.py -q` → FAIL (`KeyError: 'surname'`).

- [ ] **Step 3: Migration**

```python
"""Store name parts separately from the composed display name."""

import sqlalchemy as sa
from alembic import op


revision = "0006_person_name_parts"
down_revision = "0005_parent_child_unions"
branch_labels = None
depends_on = None

NAME_COLUMNS = ("surname", "given_name", "patronymic", "birth_surname")


def upgrade() -> None:
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("people")}
    for name in NAME_COLUMNS:
        if name not in existing:
            op.add_column("people", sa.Column(name, sa.String(255), nullable=True))


def downgrade() -> None:
    for name in reversed(NAME_COLUMNS):
        op.drop_column("people", name)
```

Model (`Person`, after `display_name`):

```python
    surname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    given_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    patronymic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    birth_surname: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_migrations.py tests/test_models.py -q` → PASS.

---

### Task 2: Structured dates module

**Files:**
- Create: `apps/api/app/genealogy/dates.py`
- Test: `apps/api/tests/test_dates.py`

**Interfaces:**
- Produces: `DateError(ValueError)`; dataclasses `DatePoint(year, month=None, day=None)`, `DateValue(qualifier, start: DatePoint, end: DatePoint | None = None)`, `StoredDate(text, qualifier, lower, upper)`; functions `build_stored_date(value: DateValue, today: date | None = None) -> StoredDate`, `parse_stored_date(text: str | None) -> DateValue | None`, `format_date_ru(text: str | None) -> str | None`, `date_value_to_dict(value: DateValue | None) -> dict | None`.

- [ ] **Step 1: Failing tests** `apps/api/tests/test_dates.py`

```python
from datetime import date

import pytest

from app.genealogy.dates import DateError, DatePoint, DateValue, build_stored_date, date_value_to_dict, format_date_ru, parse_stored_date

TODAY = date(2026, 10, 6)


@pytest.mark.parametrize(
    ("value", "text", "lower", "upper"),
    [
        (DateValue("exact", DatePoint(1926, 4, 6)), "6 APR 1926", date(1926, 4, 6), date(1926, 4, 6)),
        (DateValue("exact", DatePoint(2004, 3)), "MAR 2004", date(2004, 3, 1), date(2004, 3, 31)),
        (DateValue("exact", DatePoint(1944)), "1944", date(1944, 1, 1), date(1944, 12, 31)),
        (DateValue("about", DatePoint(1900)), "ABT 1900", date(1900, 1, 1), date(1900, 12, 31)),
        (DateValue("before", DatePoint(1944, 3)), "BEF MAR 1944", None, date(1944, 2, 29)),
        (DateValue("after", DatePoint(1950)), "AFT 1950", date(1951, 1, 1), None),
        (DateValue("between", DatePoint(1900), DatePoint(1905)), "BET 1900 AND 1905", date(1900, 1, 1), date(1905, 12, 31)),
    ],
)
def test_builds_text_and_bounds_at_the_given_precision(value, text, lower, upper):
    stored = build_stored_date(value, TODAY)

    assert (stored.text, stored.qualifier, stored.lower, stored.upper) == (text, value.qualifier, lower, upper)
    assert parse_stored_date(stored.text) == value


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (DateValue("exact", DatePoint(1900, 2, 29)), "нет такого дня"),
        (DateValue("exact", DatePoint(1926, 4, 31)), "нет такого дня"),
        (DateValue("exact", DatePoint(1926, None, 5)), "только вместе с месяцем"),
        (DateValue("exact", DatePoint(999)), "от 1000 до 2026"),
        (DateValue("exact", DatePoint(2027)), "от 1000 до 2026"),
        (DateValue("between", DatePoint(1900), DatePoint(1900)), "позже первой"),
        (DateValue("between", DatePoint(1900)), "вторую дату"),
        (DateValue("about", DatePoint(1900), DatePoint(1905)), "только для периода"),
        (DateValue("someday", DatePoint(1900)), "Неизвестный вид даты"),
    ],
)
def test_rejects_dates_that_cannot_exist_with_a_russian_reason(value, message):
    with pytest.raises(DateError, match=message):
        build_stored_date(value, TODAY)


def test_reads_every_imported_form_and_rejects_free_text():
    assert parse_stored_date("6 APR 1926") == DateValue("exact", DatePoint(1926, 4, 6))
    assert parse_stored_date(" mar  2004 ") == DateValue("exact", DatePoint(2004, 3))
    assert parse_stored_date("EST 1890") == DateValue("about", DatePoint(1890))
    assert parse_stored_date("BET JAN 1900 AND 3 MAY 1905") == DateValue("between", DatePoint(1900, 1), DatePoint(1905, 5, 3))
    for text in (None, "", "весной 1900", "6 1926", "1926-04-06"):
        assert parse_stored_date(text) is None


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("6 APR 1926", "6 апреля 1926"),
        ("MAR 2004", "март 2004"),
        ("1944", "1944"),
        ("ABT 1900", "ок. 1900"),
        ("BEF MAR 1944", "до марта 1944"),
        ("AFT 1950", "после 1950"),
        ("BET 1900 AND 1905", "между 1900 и 1905"),
        ("BET MAR 1900 AND MAY 1905", "между мартом 1900 и маем 1905"),
        ("весной  1900", "весной 1900"),
        (None, None),
        ("  ", None),
    ],
)
def test_formats_dates_in_russian(text, label):
    assert format_date_ru(text) == label


def test_serialises_values_for_the_api():
    assert date_value_to_dict(DateValue("between", DatePoint(1900), DatePoint(1905, 5))) == {
        "qualifier": "between", "year": 1900, "month": None, "day": None, "end": {"year": 1905, "month": 5, "day": None},
    }
    assert date_value_to_dict(None) is None
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_dates.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement** `apps/api/app/genealogy/dates.py`

```python
"""Structured genealogy dates: owner input ↔ stored GEDCOM-style text and bounds, and Russian labels."""

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

MONTH_CODES = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
MONTHS_NOMINATIVE = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")
MONTHS_GENITIVE = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_INSTRUMENTAL = ("январём", "февралём", "мартом", "апрелем", "маем", "июнем", "июлем", "августом", "сентябрём", "октябрём", "ноябрём", "декабрём")
QUALIFIERS = ("exact", "about", "before", "after", "between")
_PREFIX = {"exact": "", "about": "ABT ", "before": "BEF ", "after": "AFT "}
_PARSED_PREFIX = {"ABT": "about", "EST": "about", "CAL": "about", "BEF": "before", "AFT": "after"}
_LABEL_PREFIX = {"exact": "", "about": "ок. ", "before": "до ", "after": "после "}
_POINT = r"(?:(\d{1,2})\s+)?(?:(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+)?(\d{4})"
_SINGLE = re.compile(rf"^(?:(ABT|EST|CAL|BEF|AFT)\s+)?{_POINT}$")
_BETWEEN = re.compile(rf"^BET\s+{_POINT}\s+AND\s+{_POINT}$")


class DateError(ValueError):
    """Owner-facing (Russian) reason why a date cannot be stored."""


@dataclass(frozen=True)
class DatePoint:
    year: int
    month: int | None = None
    day: int | None = None


@dataclass(frozen=True)
class DateValue:
    qualifier: str
    start: DatePoint
    end: DatePoint | None = None


@dataclass(frozen=True)
class StoredDate:
    text: str
    qualifier: str
    lower: date | None
    upper: date | None


def _check(point: DatePoint, today: date) -> None:
    if not 1000 <= point.year <= today.year:
        raise DateError(f"Год должен быть от 1000 до {today.year}.")
    if point.day is not None and point.month is None:
        raise DateError("День можно указать только вместе с месяцем.")
    if point.month is not None and not 1 <= point.month <= 12:
        raise DateError("Месяц должен быть от 1 до 12.")
    if point.day is not None and not 1 <= point.day <= monthrange(point.year, point.month)[1]:
        raise DateError("В этом месяце нет такого дня.")


def _span(point: DatePoint) -> tuple[date, date]:
    if point.month is None:
        return date(point.year, 1, 1), date(point.year, 12, 31)
    if point.day is None:
        return date(point.year, point.month, 1), date(point.year, point.month, monthrange(point.year, point.month)[1])
    exact = date(point.year, point.month, point.day)
    return exact, exact


def _text(point: DatePoint) -> str:
    parts = [str(point.day)] if point.day is not None else []
    if point.month is not None:
        parts.append(MONTH_CODES[point.month - 1])
    return " ".join([*parts, str(point.year)])


def build_stored_date(value: DateValue, today: date | None = None) -> StoredDate:
    today = today or date.today()
    if value.qualifier not in QUALIFIERS:
        raise DateError("Неизвестный вид даты.")
    _check(value.start, today)
    first, last = _span(value.start)
    if value.qualifier == "between":
        if value.end is None:
            raise DateError("Укажите вторую дату периода.")
        _check(value.end, today)
        end_first, end_last = _span(value.end)
        if end_first <= last:
            raise DateError("Вторая дата периода должна быть позже первой.")
        return StoredDate(f"BET {_text(value.start)} AND {_text(value.end)}", "between", first, end_last)
    if value.end is not None:
        raise DateError("Вторая дата нужна только для периода «между».")
    text = f"{_PREFIX[value.qualifier]}{_text(value.start)}"
    if value.qualifier == "before":
        return StoredDate(text, "before", None, first - timedelta(days=1))
    if value.qualifier == "after":
        return StoredDate(text, "after", last + timedelta(days=1), None)
    return StoredDate(text, value.qualifier, first, last)


def _point(day: str | None, month: str | None, year: str) -> DatePoint | None:
    if day and not month:
        return None
    return DatePoint(int(year), MONTH_CODES.index(month) + 1 if month else None, int(day) if day else None)


def parse_stored_date(text: str | None) -> DateValue | None:
    """Structured value of a stored date text, or None when it is free text."""
    if not text or not text.strip():
        return None
    cleaned = " ".join(text.upper().split())
    if match := _BETWEEN.match(cleaned):
        start, end = _point(*match.groups()[:3]), _point(*match.groups()[3:])
        return DateValue("between", start, end) if start and end else None
    if match := _SINGLE.match(cleaned):
        prefix, *point_parts = match.groups()
        point = _point(*point_parts)
        return DateValue(_PARSED_PREFIX[prefix] if prefix else "exact", point) if point else None
    return None


def _point_ru(point: DatePoint, case: str) -> str:
    if point.month is None:
        return str(point.year)
    if point.day is not None:
        return f"{point.day} {MONTHS_GENITIVE[point.month - 1]} {point.year}"
    names = {"nominative": MONTHS_NOMINATIVE, "genitive": MONTHS_GENITIVE, "instrumental": MONTHS_INSTRUMENTAL}[case]
    return f"{names[point.month - 1]} {point.year}"


def format_date_ru(text: str | None) -> str | None:
    """Russian label of a stored date; free text is returned with spaces tidied."""
    if not text or not text.strip():
        return None
    value = parse_stored_date(text)
    if value is None:
        return " ".join(text.split())
    if value.qualifier == "between":
        return f"между {_point_ru(value.start, 'instrumental')} и {_point_ru(value.end, 'instrumental')}"
    return _LABEL_PREFIX[value.qualifier] + _point_ru(value.start, "nominative" if value.qualifier == "exact" else "genitive")


def date_value_to_dict(value: DateValue | None) -> dict | None:
    if value is None:
        return None
    end = value.end
    return {
        "qualifier": value.qualifier,
        "year": value.start.year,
        "month": value.start.month,
        "day": value.start.day,
        "end": None if end is None else {"year": end.year, "month": end.month, "day": end.day},
    }
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_dates.py -q` → PASS.

---

### Task 3: Name parts backfill from AT5

**Files:**
- Modify: `apps/api/app/gedcom/at5.py` (append `read_at5_name_parts`)
- Create: `apps/api/app/imports/name_backfill.py`
- Create: `scripts/backfill-name-parts.py`
- Test: `apps/api/tests/test_name_backfill.py`

**Interfaces:**
- Consumes: Task 1 columns. AT5 facts: `ValuesStr` rows with `rec_table = 13` (persons) and `f_id` 64 = surname, 66 = given name, 67 = patronymic; `rec_id` = AT5 person id = suffix of `people.source_uid` (`<tree id>_<AT5 id>`).
- Produces: `read_at5_name_parts(path: Path) -> dict[int, dict[str, str]]`; `NameBackfillReport(applied, filled, already_filled, without_at5_names, without_source, display_name_differs)`; `backfill_name_parts(session, path: Path, apply: bool = False) -> NameBackfillReport`.

- [ ] **Step 1: Failing tests** `apps/api/tests/test_name_backfill.py`

```python
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.imports.name_backfill import backfill_name_parts
from app.models.genealogy import Base, ImportRun, Person


def create_at5(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE ValuesStr (f_id INTEGER, f_db_id INTEGER, rec_id INTEGER, rec_db_id INTEGER, rec_table INTEGER, lang_id INTEGER, vstr TEXT);
        INSERT INTO ValuesStr VALUES
          (64, -1, 1, 0, 13, 0, 'Кошкин'), (66, -1, 1, 0, 13, 0, 'Петр'), (67, -1, 1, 0, 13, 0, 'Николаевич'),
          (66, -1, 2, 0, 13, 0, 'Вера'),
          (64, -1, 3, 0, 13, 0, 'Другой'),
          (50, -1, 1, 0, 9, 0, 'КОШКИН');
        """
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def session(postgres_url):
    engine = create_engine(postgres_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    Base.metadata.drop_all(engine)


@pytest.fixture
def people(session):
    run = ImportRun(original_filename="archive.json", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    session.add(run)
    session.flush()
    rows = {
        "petr": Person(import_run_id=run.id, display_name="Петр Николаевич Кошкин", source_uid="ABCD_1"),
        "vera": Person(import_run_id=run.id, display_name="Вера Иванова", source_uid="ABCD_2"),
        "edited": Person(import_run_id=run.id, display_name="Уже Исправлен", source_uid="ABCD_3", surname="Исправлен"),
        "absent": Person(import_run_id=run.id, display_name="Без Записи", source_uid="ABCD_9"),
        "new": Person(import_run_id=run.id, display_name="Добавлен На Сайте", source_uid=None),
    }
    session.add_all(rows.values())
    session.commit()
    return rows


def test_fills_only_people_without_name_parts_and_keeps_display_names(session, people, tmp_path):
    report = backfill_name_parts(session, create_at5(tmp_path / "tree.at5"), apply=True)

    session.expire_all()
    petr, vera, edited = people["petr"], people["vera"], people["edited"]
    assert (petr.surname, petr.given_name, petr.patronymic, petr.display_name) == ("Кошкин", "Петр", "Николаевич", "Петр Николаевич Кошкин")
    assert (vera.surname, vera.given_name, vera.patronymic, vera.display_name) == (None, "Вера", None, "Вера Иванова")
    assert (edited.surname, edited.given_name) == ("Исправлен", None)
    assert (report.filled, report.already_filled, report.without_at5_names, report.without_source, report.display_name_differs) == (2, 1, 1, 1, 1)
    assert session.query(ImportRun).filter_by(original_filename="tree.at5").one().state == "applied"


def test_dry_run_writes_nothing(session, people, tmp_path):
    report = backfill_name_parts(session, create_at5(tmp_path / "tree.at5"), apply=False)

    session.expire_all()
    assert report.applied is False and report.filled == 2
    assert people["petr"].surname is None
    assert session.query(ImportRun).filter_by(original_filename="tree.at5").count() == 0
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_name_backfill.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

Append to `apps/api/app/gedcom/at5.py`:

```python
# ValuesStr.f_id of person name parts in Древо Жизни (rec_table 13 = Persons).
NAME_PART_FIELDS = {64: "surname", 66: "given_name", 67: "patronymic"}
PERSONS_TABLE = 13


def read_at5_name_parts(path: Path) -> dict[int, dict[str, str]]:
    """Surname, given name and patronymic per AT5 person id, read-only."""
    if not path.is_absolute() or not path.is_file():
        raise At5ImportError("Укажите существующий абсолютный путь к файлу AT5.")
    connection = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = connection.execute(
            f"SELECT rec_id, f_id, vstr FROM ValuesStr WHERE rec_table = ? AND f_id IN ({', '.join('?' * len(NAME_PART_FIELDS))})",
            (PERSONS_TABLE, *NAME_PART_FIELDS),
        ).fetchall()
    except sqlite3.Error as error:
        raise At5ImportError("Не удалось прочитать имена из файла AT5.") from error
    finally:
        if connection is not None:
            connection.close()
    parts: dict[int, dict[str, str]] = {}
    for person_id, field_id, value in rows:
        cleaned = " ".join((value or "").split())
        if cleaned:
            parts.setdefault(person_id, {})[NAME_PART_FIELDS[field_id]] = cleaned
    return parts
```

`apps/api/app/imports/name_backfill.py`:

```python
"""Fill surname / given name / patronymic from AT5 for people who have none yet."""

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.gedcom.at5 import read_at5_name_parts
from app.models.genealogy import ImportRun, Person


@dataclass(frozen=True)
class NameBackfillReport:
    applied: bool
    filled: int
    already_filled: int
    without_at5_names: int
    without_source: int
    display_name_differs: int


def backfill_name_parts(session: Session, path: Path, apply: bool = False) -> NameBackfillReport:
    parts_by_at5 = read_at5_name_parts(path)
    filled = already_filled = without_names = without_source = differs = 0
    for person in session.scalars(select(Person).order_by(Person.id)):
        prefix, _, number = (person.source_uid or "").rpartition("_")
        if not prefix or not number.isdigit():
            without_source += 1
            continue
        if any((person.surname, person.given_name, person.patronymic, person.birth_surname)):
            already_filled += 1
            continue
        parts = parts_by_at5.get(int(number))
        if not parts:
            without_names += 1
            continue
        filled += 1
        composed = " ".join(part for part in (parts.get("given_name"), parts.get("patronymic"), parts.get("surname")) if part)
        if composed != person.display_name:
            differs += 1
        if apply:
            person.surname = parts.get("surname")
            person.given_name = parts.get("given_name")
            person.patronymic = parts.get("patronymic")
    report = NameBackfillReport(apply, filled, already_filled, without_names, without_source, differs)
    if not apply:
        session.rollback()
        return report
    session.add(
        ImportRun(
            original_filename=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            state="applied",
            normalized_payload={"mode": "name-parts-backfill", "report": asdict(report)},
            counts={"people": filled},
        )
    )
    session.commit()
    return report
```

`scripts/backfill-name-parts.py` (chmod +x):

```python
#!/usr/bin/env python3
"""Заполнить фамилию, имя и отчество из файла Древо Жизни AT5 у людей, где они ещё пусты.

Без --apply — пробный прогон: печатается отчёт из чисел, база не меняется.
Отображаемое имя людей не меняется.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Части имени из AT5")
    parser.add_argument("--at5", required=True, type=Path, help="Абсолютный путь к файлу Древо Жизни AT5")
    parser.add_argument("--apply", action="store_true", help="Записать изменения в базу")
    args = parser.parse_args()
    if not args.at5.is_absolute():
        parser.error("Укажите абсолютный путь к файлу AT5.")
    if not args.at5.is_file():
        parser.error("Файл AT5 не найден.")

    from app.core.config import Settings
    from app.db.session import create_session_factory
    from app.gedcom.at5 import At5ImportError
    from app.imports.name_backfill import backfill_name_parts

    with create_session_factory(Settings().database_url)() as session:
        try:
            report = backfill_name_parts(session, args.at5, apply=args.apply)
        except At5ImportError as error:
            print(f"Остановлено: {error}", file=sys.stderr)
            return 1
    print("Применено" if report.applied else "Пробный прогон: база не изменена")
    print(f"Заполнено людей: {report.filled}")
    print(f"Уже были заполнены: {report.already_filled}")
    print(f"Нет имени в AT5: {report.without_at5_names}")
    print(f"Без ссылки на AT5: {report.without_source}")
    print(f"Собранное имя отличается от отображаемого: {report.display_name_differs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_name_backfill.py -q` → PASS; `.venv/bin/python ../../scripts/backfill-name-parts.py --at5 relative.at5` → exit 2 with «абсолютный путь».

---

### Task 4: Person editing service

**Files:**
- Create: `apps/api/app/genealogy/person_editing.py`
- Modify: `apps/api/app/genealogy/write_service.py` (add `restore_person`; remove `rename_person`, now unused)
- Test: `apps/api/tests/test_person_editing.py`

**Interfaces:**
- Consumes: Task 1 columns, Task 2 `DateValue`, `build_stored_date`, `parse_stored_date`, `date_value_to_dict`, `DateError`.
- Produces:
  - `PersonEditError(ValueError)`
  - `LifeEventInput(date: DateValue | None, place: str | None, keep_date_text: bool = False)`
  - `PersonEdit(surname, given_name, patronymic, birth_surname, sex, birth: LifeEventInput | None, death_status: str, death: LifeEventInput | None)`
  - `compose_display_name(given_name, patronymic, surname) -> str`
  - `editable_person(session, person_id: UUID) -> dict` (shape of `EditablePerson` in the spec; raises `LookupError`)
  - `update_person(session, person_id: UUID, edit: PersonEdit, owner_email: str) -> dict`
  - `owner_search(session, query: str) -> list[dict]` (`id`, `display_name`, `years`, `is_archived`)
  - `restore_person(session, person_id, owner_email) -> Person` in `write_service`

- [ ] **Step 1: Failing tests** `apps/api/tests/test_person_editing.py`

```python
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
```

- [ ] **Step 2:** `.venv/bin/pytest tests/test_person_editing.py -q` → FAIL (module missing).

- [ ] **Step 3: Implement**

`apps/api/app/genealogy/write_service.py` — delete `rename_person`, add after `archive_person`:

```python
def restore_person(session: Session, person_id: UUID, owner_email: str) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    person.is_archived = False
    session.add(ChangeLog(entity_type="person", entity_id=person.id, owner_email=owner_email, before={"is_archived": True}, after={"is_archived": False}))
    session.commit()
    session.refresh(person)
    return person
```

`apps/api/app/genealogy/person_editing.py`:

```python
"""Owner corrections of an existing person: name parts, sex, birth and death, in one logged save."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.genealogy.dates import DateValue, build_stored_date, date_value_to_dict, parse_stored_date
from app.genealogy.read_service import normalize_public_name, public_person_summary
from app.models.genealogy import ChangeLog, Event, MediaLink, Person

MAX_NAME_LENGTH = 255
MAX_PLACE_LENGTH = 512
NAME_FIELDS = ("surname", "given_name", "patronymic", "birth_surname")
EVENT_WORDS = {"BIRT": "рождения", "DEAT": "смерти"}


class PersonEditError(ValueError):
    """Owner-facing (Russian) reason why a save is refused."""


@dataclass(frozen=True)
class LifeEventInput:
    date: DateValue | None
    place: str | None
    keep_date_text: bool = False


@dataclass(frozen=True)
class PersonEdit:
    surname: str | None
    given_name: str | None
    patronymic: str | None
    birth_surname: str | None
    sex: str | None
    birth: LifeEventInput | None
    death_status: str
    death: LifeEventInput | None


def _clean(value: str | None, limit: int, label: str) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if len(cleaned) > limit:
        raise PersonEditError(f"{label} не может быть длиннее {limit} символов.")
    return cleaned or None


def compose_display_name(given_name: str | None, patronymic: str | None, surname: str | None) -> str:
    return " ".join(part for part in (given_name, patronymic, surname) if part)


def _life_events(session: Session, person_id: UUID, kind: str) -> list[Event]:
    return list(session.scalars(
        select(Event).where(Event.person_id == person_id, Event.event_type == kind).order_by(Event.date_lower.asc().nulls_last(), Event.id)
    ))


def _single(session: Session, person_id: UUID, kind: str) -> Event | None:
    events = _life_events(session, person_id, kind)
    if len(events) > 1:
        raise PersonEditError(f"У человека несколько событий {EVENT_WORDS[kind]} — исправьте их отдельно.")
    return events[0] if events else None


def _event_view(event: Event | None) -> dict | None:
    if event is None:
        return None
    return {"date": date_value_to_dict(parse_stored_date(event.date_text)), "date_text": event.date_text, "place": event.place}


def _snapshot(session: Session, person: Person) -> dict:
    def summary(kind: str) -> dict | None:
        events = _life_events(session, person.id, kind)
        return {"date_text": events[0].date_text, "place": events[0].place} if events else None

    return {
        **{name: getattr(person, name) for name in NAME_FIELDS},
        "sex": person.sex,
        "display_name": person.display_name,
        "birth": summary("BIRT"),
        "death": summary("DEAT"),
    }


def editable_person(session: Session, person_id: UUID) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    births, deaths = _life_events(session, person.id, "BIRT"), _life_events(session, person.id, "DEAT")
    death = _event_view(deaths[0] if deaths else None)
    return {
        "id": str(person.id),
        "display_name": person.display_name,
        "is_archived": person.is_archived,
        **{name: getattr(person, name) for name in NAME_FIELDS},
        "sex": person.sex,
        "birth": _event_view(births[0] if births else None),
        "death": {"status": "deceased" if deaths else "unknown", **(death or {"date": None, "date_text": None, "place": None})},
    }


def _apply(session: Session, person: Person, kind: str, value: LifeEventInput | None) -> None:
    event = _single(session, person.id, kind)
    if value is None:
        if event is not None:
            linked = session.scalar(select(func.count()).select_from(MediaLink).where(MediaLink.event_id == event.id))
            if linked:
                raise PersonEditError("К событию привязаны материалы — сначала отвяжите их.")
            session.delete(event)
        return
    if event is None:
        event = Event(person_id=person.id, event_type=kind)
        session.add(event)
    keep_unparsed = value.keep_date_text and event.date_text and parse_stored_date(event.date_text) is None
    if not keep_unparsed:
        stored = build_stored_date(value.date) if value.date else None
        event.date_text = stored.text if stored else None
        event.date_qualifier = stored.qualifier if stored else None
        event.date_lower = stored.lower if stored else None
        event.date_upper = stored.upper if stored else None
    event.place = _clean(value.place, MAX_PLACE_LENGTH, "Место")


def update_person(session: Session, person_id: UUID, edit: PersonEdit, owner_email: str) -> dict:
    person = session.get(Person, person_id)
    if person is None:
        raise LookupError("Человек не найден.")
    try:
        names = {name: _clean(getattr(edit, name), MAX_NAME_LENGTH, "Часть имени") for name in NAME_FIELDS}
        if not names["given_name"] and not names["surname"]:
            raise PersonEditError("Укажите имя или фамилию.")
        if edit.sex not in (None, "M", "F"):
            raise PersonEditError("Неизвестное значение пола.")
        if edit.death_status not in ("unknown", "deceased"):
            raise PersonEditError("Неизвестное состояние смерти.")
        before = _snapshot(session, person)
        for name, value in names.items():
            setattr(person, name, value)
        person.sex = edit.sex
        person.display_name = compose_display_name(names["given_name"], names["patronymic"], names["surname"])
        _apply(session, person, "BIRT", edit.birth)
        _apply(session, person, "DEAT", (edit.death or LifeEventInput(None, None)) if edit.death_status == "deceased" else None)
        session.flush()
        after = _snapshot(session, person)
        changed = [key for key in after if after[key] != before[key]]
        if changed:
            session.add(ChangeLog(
                entity_type="person", entity_id=person.id, owner_email=owner_email,
                before={key: before[key] for key in changed}, after={key: after[key] for key in changed},
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return editable_person(session, person_id)


def owner_search(session: Session, query: str) -> list[dict]:
    normalized = query.strip().lower().replace("ё", "е")
    statement = select(Person)
    if normalized:
        def folded(column):
            return func.replace(func.lower(func.coalesce(column, "")), "ё", "е")
        statement = statement.where(or_(folded(Person.display_name).contains(normalized), folded(Person.birth_surname).contains(normalized)))
    people = session.scalars(statement.order_by(Person.display_name).limit(20))
    return [
        {"id": str(person.id), "display_name": normalize_public_name(person.display_name), "years": public_person_summary(session, person).years, "is_archived": person.is_archived}
        for person in people
    ]
```

- [ ] **Step 4:** `.venv/bin/pytest tests/test_person_editing.py -q` → PASS. Then `.venv/bin/pytest -q` — `tests/test_owner_genealogy_api.py` will fail on the removed rename endpoint; that is fixed in Task 5 (do not restore `rename_person`).

---

### Task 5: Owner API endpoints

**Files:**
- Modify: `apps/api/app/api/routes/admin_genealogy.py`
- Test: `apps/api/tests/test_owner_genealogy_api.py`

**Interfaces:**
- Consumes: Task 4 service functions, Task 2 `DateError`, `DatePoint`, `DateValue`.
- Produces: `GET /api/v1/admin/people?query=`, `GET /api/v1/admin/people/{id}`, `PATCH /api/v1/admin/people/{id}`, `POST /api/v1/admin/people/{id}/restore` (archive stays).

- [ ] **Step 1: Failing tests** — in `apps/api/tests/test_owner_genealogy_api.py` replace `test_anonymous_client_cannot_edit_person` and `test_owner_can_edit_person_and_change_is_logged` with the tests below (keep the other tests and helpers; add a `login(client)` helper if the file does not have one: `client.post("/api/v1/auth/login", json={"password": "test-owner-password"})`):

```python
FORM = {
    "surname": "Иванова", "given_name": "Анна", "patronymic": None, "birth_surname": "Петрова", "sex": "F",
    "birth": {"date": {"qualifier": "about", "year": 1900, "month": None, "day": None, "end": None}, "place": "Тула", "date_text_keep": False},
    "death": {"status": "unknown", "date": None, "place": None, "date_text_keep": False},
}


def login(client):
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})


def test_guests_cannot_read_or_edit_people_for_the_owner(client, database_session):
    person = create_person(database_session)

    assert client.get("/api/v1/admin/people").status_code == 401
    assert client.get(f"/api/v1/admin/people/{person.id}").status_code == 401
    assert client.patch(f"/api/v1/admin/people/{person.id}", json=FORM).status_code == 401
    assert client.post(f"/api/v1/admin/people/{person.id}/restore").status_code == 401


def test_owner_saves_the_form_and_the_change_is_logged(client, database_session):
    person = create_person(database_session)
    login(client)

    response = client.patch(f"/api/v1/admin/people/{person.id}", json=FORM)

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Анна Иванова"
    assert body["birth"] == {"date": {"qualifier": "about", "year": 1900, "month": None, "day": None, "end": None}, "date_text": "ABT 1900", "place": "Тула"}
    assert body["death"]["status"] == "unknown"
    assert client.get(f"/api/v1/admin/people/{person.id}").json() == body
    entry = database_session.query(ChangeLog).filter_by(entity_id=person.id).one()
    assert entry.after["display_name"] == "Анна Иванова"


def test_owner_gets_russian_validation_errors(client, database_session):
    person = create_person(database_session)
    login(client)

    no_name = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "surname": None, "given_name": " "})
    bad_day = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "birth": {"date": {"qualifier": "exact", "year": 1901, "month": 2, "day": 30, "end": None}, "place": None, "date_text_keep": False}})
    bad_type = client.patch(f"/api/v1/admin/people/{person.id}", json={**FORM, "sex": "X"})

    assert (no_name.status_code, no_name.json()) == (422, {"detail": "Укажите имя или фамилию."})
    assert (bad_day.status_code, bad_day.json()) == (422, {"detail": "В этом месяце нет такого дня."})
    assert bad_type.status_code == 422


def test_owner_finds_hidden_people_and_restores_them(client, database_session):
    person = create_person(database_session)
    login(client)
    client.post(f"/api/v1/admin/people/{person.id}/archive")

    assert client.get("/api/v1/people?query=Анна").json() == []
    assert client.get("/api/v1/admin/people?query=анна").json() == [{"id": str(person.id), "display_name": "Анна", "years": None, "is_archived": True}]

    assert client.post(f"/api/v1/admin/people/{person.id}/restore").status_code == 204
    assert client.get(f"/api/v1/admin/people/{person.id}").json()["is_archived"] is False


def test_unknown_person_is_404_for_the_owner(client, database_session):
    from uuid import uuid4

    login(client)
    assert client.get(f"/api/v1/admin/people/{uuid4()}").status_code == 404
    assert client.patch(f"/api/v1/admin/people/{uuid4()}", json=FORM).status_code == 404
```

The `client` fixture in `conftest.py` has `get`, `post`, `patch`; it keeps cookies between calls.

- [ ] **Step 2:** `.venv/bin/pytest tests/test_owner_genealogy_api.py -q` → the new tests FAIL (405/422/404).

- [ ] **Step 3: Implement** in `apps/api/app/api/routes/admin_genealogy.py`: remove `PersonUpdateRequest`, `PersonUpdateResponse`, the old `update_person` route and the `rename_person` import; add:

```python
from typing import Literal

from fastapi import Query

from app.genealogy.dates import DateError, DatePoint, DateValue
from app.genealogy.person_editing import LifeEventInput, PersonEdit, PersonEditError, editable_person, owner_search, update_person
from app.genealogy.write_service import archive_person, create_parent_child_link, create_person_event, create_union, restore_person


class DatePointBody(BaseModel):
    year: int
    month: int | None = None
    day: int | None = None


class DateBody(DatePointBody):
    qualifier: Literal["exact", "about", "before", "after", "between"]
    end: DatePointBody | None = None


class LifeEventBody(BaseModel):
    date: DateBody | None = None
    place: str | None = None
    date_text_keep: bool = False


class DeathBody(LifeEventBody):
    status: Literal["unknown", "deceased"]


class PersonEditBody(BaseModel):
    surname: str | None = None
    given_name: str | None = None
    patronymic: str | None = None
    birth_surname: str | None = None
    sex: Literal["M", "F"] | None = None
    birth: LifeEventBody | None = None
    death: DeathBody


def _date(body: DateBody | None) -> DateValue | None:
    if body is None:
        return None
    end = DatePoint(body.end.year, body.end.month, body.end.day) if body.end else None
    return DateValue(body.qualifier, DatePoint(body.year, body.month, body.day), end)


def _life(body: LifeEventBody | None) -> LifeEventInput | None:
    return None if body is None else LifeEventInput(_date(body.date), body.place, body.date_text_keep)


@router.get("/admin/people")
def search_people_for_owner(query: str = Query(default=""), owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> list[dict]:
    return owner_search(session, query)


@router.get("/admin/people/{person_id}")
def read_person_for_owner(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    try:
        return editable_person(session, person_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/admin/people/{person_id}")
def save_person(person_id: UUID, body: PersonEditBody, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> dict:
    edit = PersonEdit(
        surname=body.surname, given_name=body.given_name, patronymic=body.patronymic, birth_surname=body.birth_surname,
        sex=body.sex, birth=_life(body.birth), death_status=body.death.status, death=_life(body.death),
    )
    try:
        return update_person(session, person_id, edit, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (PersonEditError, DateError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/admin/people/{person_id}/restore", status_code=204)
def restore(person_id: UUID, owner: OwnerSession = Depends(require_owner), session: Session = Depends(get_session)) -> None:
    try:
        restore_person(session, person_id, owner.email)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
```

Keep the `GET /admin/people` route above `GET /admin/people/{person_id}` in the file.

- [ ] **Step 4:** `.venv/bin/pytest tests/test_owner_genealogy_api.py -q && .venv/bin/pytest -q` → all PASS.

---

### Task 6: Public API and tree use Russian dates and name parts

**Files:**
- Modify: `apps/api/app/genealogy/read_service.py` (`format_public_date` → delegate to `format_date_ru`; `search_people` also by `birth_surname`)
- Modify: `apps/api/app/api/routes/people.py` (`PersonResponse` + `birth_surname`, `sex`; `EventResponse` + `date_label_ru`, `place`)
- Modify: `apps/api/app/genealogy/tree_service.py` (`_life_labels` uses `format_date_ru`)
- Test: `apps/api/tests/test_public_people_api.py`, `apps/api/tests/test_public_tree_api.py`

**Interfaces:**
- Consumes: Task 2 `format_date_ru`.
- Produces: public person JSON fields `birth_surname`, `sex`, `events[].date_label_ru`, `events[].place`; tree `birth_label`/`death_label` in Russian.

- [ ] **Step 1: Failing tests** — append to `apps/api/tests/test_public_people_api.py` (it already has `add_person(session, name, archived=False)` and the `database_session` fixture):

```python
def test_person_page_carries_birth_surname_sex_and_russian_event_labels(client, database_session):
    person = add_person(database_session, "Анна Иванова")
    person.sex, person.birth_surname = "F", "Петрова"
    database_session.add(Event(person_id=person.id, event_type="BIRT", date_text="BEF MAR 1944", date_qualifier="before", place="Тула"))
    database_session.commit()

    body = client.get(f"/api/v1/people/{person.id}").json()

    assert body["birth_surname"] == "Петрова" and body["sex"] == "F"
    assert body["events"] == [{"event_type": "BIRT", "date_text": "BEF MAR 1944", "date_label_ru": "до марта 1944", "place": "Тула"}]
    assert body["birth_label"] == "до марта 1944"


def test_public_search_finds_the_birth_surname_but_never_hidden_people(client, database_session):
    visible = add_person(database_session, "Анна Иванова")
    hidden = add_person(database_session, "Мария Смирнова", archived=True)
    visible.birth_surname = hidden.birth_surname = "Ёлкина"
    database_session.commit()

    assert client.get("/api/v1/people?query=елкина").json() == [{"id": str(visible.id), "display_name": "Анна Иванова"}]
```

Append to `apps/api/tests/test_public_tree_api.py` (it has `create_person(session, run, name, sex=None)` and `database_session`; import `Event`, `ImportRun` if missing):

```python
def test_tree_labels_are_russian_for_approximate_dates(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    person = create_person(database_session, run, "Анна")
    database_session.add(Event(person_id=person.id, event_type="BIRT", date_text="ABT 1900", date_qualifier="about"))
    database_session.commit()

    people = client.get(f"/api/v1/tree/{person.id}?mode=close").json()["people"]

    assert next(item for item in people if item["id"] == str(person.id))["birth_label"] == "ок. 1900"
```

- [ ] **Step 2:** run both files → new tests FAIL.

- [ ] **Step 3: Implement**
  - `read_service.format_public_date(value)` body becomes `return format_date_ru(value)` (import from `app.genealogy.dates`); remove the now-unused `_MONTHS_RU`/`_QUALIFIERS_RU` only if nothing else uses them (grep first).
  - `search_people`: the `where` becomes `or_(normalized(display_name).contains(q), normalized(coalesce(birth_surname, '')).contains(q))` with the same `ё→е` folding; keep `Person.is_archived.is_(False)`.
  - `EventResponse`: add `date_label_ru: str | None = None`, `place: str | None = None`; build with `format_date_ru(event.date_text)` and `event.place`.
  - `PersonResponse`: add `birth_surname: str | None = None`, `sex: str | None = None`; fill from the person.
  - `tree_service._life_labels`: store `format_date_ru(event.date_text)` instead of the raw text.
  - Existing tests that asserted raw GEDCOM text in tree labels or person summaries (for example `"20 MAR 2004"` or `"MAR 2004"`) must be updated to the Russian label; do not change any other assertion.

- [ ] **Step 4:** `.venv/bin/pytest -q` → all PASS.

---

### Task 7: Web owner API client, date formatting and date input

**Files:**
- Create: `apps/web/src/owner-api.ts`
- Create: `apps/web/src/date-format.ts`
- Create: `apps/web/src/components/date-input.ts`
- Test: `apps/web/test/date-input.test.ts`

**Interfaces:**
- Produces (`owner-api.ts`):

```ts
export type Qualifier = 'exact' | 'about' | 'before' | 'after' | 'between'
export type DatePoint = { year: number; month: number | null; day: number | null }
export type DateValue = DatePoint & { qualifier: Qualifier; end: DatePoint | null }
export type LifeEventView = { date: DateValue | null; date_text: string | null; place: string | null }
export type EditablePerson = {
  id: string; display_name: string; is_archived: boolean
  surname: string | null; given_name: string | null; patronymic: string | null; birth_surname: string | null
  sex: 'M' | 'F' | null; birth: LifeEventView | null; death: LifeEventView & { status: 'unknown' | 'deceased' }
}
export type LifeEventInput = { date: DateValue | null; place: string | null; date_text_keep: boolean }
export type PersonEditPayload = {
  surname: string | null; given_name: string | null; patronymic: string | null; birth_surname: string | null
  sex: 'M' | 'F' | null; birth: LifeEventInput | null; death: LifeEventInput & { status: 'unknown' | 'deceased' }
}
export type OwnerSearchResult = { id: string; display_name: string; years: string | null; is_archived: boolean }
export type ApiResult<T> = { ok: true; value: T } | { ok: false; message: string }
export function fetchEditablePerson(id: string): Promise<ApiResult<EditablePerson>>
export function savePerson(id: string, payload: PersonEditPayload): Promise<ApiResult<EditablePerson>>
export function archivePerson(id: string): Promise<ApiResult<null>>
export function restorePerson(id: string): Promise<ApiResult<null>>
export function searchOwnerPeople(query: string): Promise<ApiResult<OwnerSearchResult[]>>
```

- Produces (`date-format.ts`): `MONTHS_NOMINATIVE: string[]` (12 names), `formatDateValueRu(value: DateValue): string` — same rules as backend `format_date_ru`.
- Produces `<cats-date-input>`: property `value: DateValue | null`, property `label: string`; event `date-change` (`detail: DateValue | null`, bubbles, composed). Controls (all with `aria-label`): `select[name=qualifier]` (Точно / Около / До / После / Между), `input[name=day]`, `select[name=month]` (`—` + 12 nominative names, values 1–12), `input[name=year]`; for «Между» a second group `input[name=end-day]`, `select[name=end-month]`, `input[name=end-year]`; a preview `.preview` with «Будет показано: …». An empty year emits `null`.

- [ ] **Step 1: Failing tests** `apps/web/test/date-input.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/components/date-input'
import { formatDateValueRu } from '../src/date-format'
import type { DateValue } from '../src/owner-api'

type DateInput = HTMLElement & { value: DateValue | null; updateComplete: Promise<boolean> }
const point = (year: number, month: number | null = null, day: number | null = null) => ({ year, month, day })

async function render(value: DateValue | null) {
  const element = document.createElement('cats-date-input') as DateInput
  element.value = value
  document.body.append(element)
  await element.updateComplete
  return element
}
function change(element: DateInput, name: string, value: string) {
  const control = element.shadowRoot!.querySelector(`[name="${name}"]`) as HTMLInputElement | HTMLSelectElement
  control.value = value
  control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'))
}

afterEach(() => document.body.replaceChildren())

describe('formatDateValueRu', () => {
  it.each([
    [{ qualifier: 'exact', ...point(1926, 4, 6), end: null }, '6 апреля 1926'],
    [{ qualifier: 'exact', ...point(2004, 3), end: null }, 'март 2004'],
    [{ qualifier: 'about', ...point(1900), end: null }, 'ок. 1900'],
    [{ qualifier: 'before', ...point(1944, 3), end: null }, 'до марта 1944'],
    [{ qualifier: 'after', ...point(1950), end: null }, 'после 1950'],
    [{ qualifier: 'between', ...point(1900, 3), end: point(1905, 5) }, 'между мартом 1900 и маем 1905'],
  ] as [DateValue, string][])('formats %j', (value, label) => {
    expect(formatDateValueRu(value)).toBe(label)
  })
})

describe('cats-date-input', () => {
  it('shows the stored value and its public label', async () => {
    const element = await render({ qualifier: 'about', ...point(1901, 4), end: null })

    expect((element.shadowRoot!.querySelector('[name="qualifier"]') as HTMLSelectElement).value).toBe('about')
    expect((element.shadowRoot!.querySelector('[name="month"]') as HTMLSelectElement).value).toBe('4')
    expect((element.shadowRoot!.querySelector('[name="year"]') as HTMLInputElement).value).toBe('1901')
    expect(element.shadowRoot!.querySelector('.preview')?.textContent).toContain('ок. апреля 1901')
  })

  it('emits a structured value as the owner types and null without a year', async () => {
    const element = await render(null)
    const changes: (DateValue | null)[] = []
    element.addEventListener('date-change', (event) => changes.push((event as CustomEvent).detail))

    change(element, 'year', '1944')
    change(element, 'month', '3')
    change(element, 'qualifier', 'before')
    change(element, 'year', '')

    expect(changes).toEqual([
      { qualifier: 'exact', year: 1944, month: null, day: null, end: null },
      { qualifier: 'exact', year: 1944, month: 3, day: null, end: null },
      { qualifier: 'before', year: 1944, month: 3, day: null, end: null },
      null,
    ])
  })

  it('asks for a second date only for a period', async () => {
    const element = await render({ qualifier: 'exact', ...point(1900), end: null })
    expect(element.shadowRoot!.querySelector('[name="end-year"]')).toBeNull()
    const changes: (DateValue | null)[] = []
    element.addEventListener('date-change', (event) => changes.push((event as CustomEvent).detail))

    change(element, 'qualifier', 'between')
    element.value = changes.at(-1)!
    await element.updateComplete
    change(element, 'end-year', '1905')

    expect(changes.at(-1)).toEqual({ qualifier: 'between', year: 1900, month: null, day: null, end: { year: 1905, month: null, day: null } })
  })
})
```

- [ ] **Step 2:** `cd apps/web && npx vitest run test/date-input.test.ts` → FAIL (modules missing).

- [ ] **Step 3: Implement**

`apps/web/src/date-format.ts`:

```ts
import type { DatePoint, DateValue } from './owner-api'

export const MONTHS_NOMINATIVE = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const MONTHS_GENITIVE = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const MONTHS_INSTRUMENTAL = ['январём', 'февралём', 'мартом', 'апрелем', 'маем', 'июнем', 'июлем', 'августом', 'сентябрём', 'октябрём', 'ноябрём', 'декабрём']
const PREFIX = { exact: '', about: 'ок. ', before: 'до ', after: 'после ' } as const

function pointRu(point: DatePoint, months: string[]): string {
  if (point.month === null) return String(point.year)
  if (point.day !== null) return `${point.day} ${MONTHS_GENITIVE[point.month - 1]} ${point.year}`
  return `${months[point.month - 1]} ${point.year}`
}

/** Same rules as the API's format_date_ru, for the preview under the date input. */
export function formatDateValueRu(value: DateValue): string {
  if (value.qualifier === 'between') return `между ${pointRu(value, MONTHS_INSTRUMENTAL)} и ${value.end ? pointRu(value.end, MONTHS_INSTRUMENTAL) : '…'}`
  return PREFIX[value.qualifier] + pointRu(value, value.qualifier === 'exact' ? MONTHS_NOMINATIVE : MONTHS_GENITIVE)
}
```

`apps/web/src/owner-api.ts` — the types above plus:

```ts
const UNAVAILABLE = 'Сервер недоступен. Попробуйте позже.'

async function request<T>(url: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    return { ok: false, message: UNAVAILABLE }
  }
  if (response.status === 401) return { ok: false, message: 'Войдите как владелец, чтобы изменять данные.' }
  if (response.status === 404) return { ok: false, message: 'Человек не найден.' }
  if (response.status === 422) {
    const detail = await response.json().then((data) => data?.detail, () => null)
    return { ok: false, message: typeof detail === 'string' ? detail : 'Проверьте заполнение полей.' }
  }
  if (!response.ok) return { ok: false, message: 'Не удалось сохранить. Попробуйте ещё раз.' }
  const text = await response.text()
  return { ok: true, value: (text ? JSON.parse(text) : null) as T }
}

const json = (method: string, body: unknown): RequestInit => ({ method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const fetchEditablePerson = (id: string) => request<EditablePerson>(`/api/v1/admin/people/${id}`)
export const savePerson = (id: string, payload: PersonEditPayload) => request<EditablePerson>(`/api/v1/admin/people/${id}`, json('PATCH', payload))
export const archivePerson = (id: string) => request<null>(`/api/v1/admin/people/${id}/archive`, { method: 'POST' })
export const restorePerson = (id: string) => request<null>(`/api/v1/admin/people/${id}/restore`, { method: 'POST' })
export const searchOwnerPeople = (query: string) => request<OwnerSearchResult[]>(`/api/v1/admin/people?query=${encodeURIComponent(query)}`)
```

`apps/web/src/components/date-input.ts`:

```ts
import { LitElement, css, html } from 'lit'

import { MONTHS_NOMINATIVE, formatDateValueRu } from '../date-format'
import type { DatePoint, DateValue, Qualifier } from '../owner-api'

const QUALIFIERS: [Qualifier, string][] = [['exact', 'Точно'], ['about', 'Около'], ['before', 'До'], ['after', 'После'], ['between', 'Между']]
const number = (raw: string) => (raw.trim() && Number.isFinite(Number(raw)) ? Number(raw) : null)

export class CatsDateInput extends LitElement {
  static properties = { value: { attribute: false }, label: {} }
  declare value: DateValue | null
  declare label: string
  private qualifier: Qualifier = 'exact'
  private start: { year: string; month: string; day: string } = { year: '', month: '', day: '' }
  private end: { year: string; month: string; day: string } = { year: '', month: '', day: '' }

  constructor() { super(); this.value = null; this.label = 'Дата' }

  static styles = css`
    :host { display:block; }
    .row { display:flex; gap:.5rem; flex-wrap:wrap; align-items:flex-end; margin-bottom:.5rem; }
    label { display:grid; gap:.25rem; font-size:.75rem; color:var(--text-2,#4a4c49); }
    input,select { height:2.25rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .5rem; font:inherit; background:#fff; }
    input[name$="day"] { width:3.5rem; } input[name$="year"] { width:5rem; }
    .preview { font-size:.8rem; color:var(--text-3,#6b6d69); }
  `

  willUpdate(changed: Map<string, unknown>) {
    if (!changed.has('value')) return
    const value = this.value
    const text = (point: DatePoint | null) => ({ year: point ? String(point.year) : '', month: point?.month ? String(point.month) : '', day: point?.day ? String(point.day) : '' })
    this.qualifier = value?.qualifier ?? this.qualifier
    this.start = text(value)
    this.end = text(value?.end ?? null)
  }

  private current(): DateValue | null {
    const year = number(this.start.year)
    if (year === null) return null
    const end = this.qualifier === 'between' && number(this.end.year) !== null
      ? { year: number(this.end.year)!, month: number(this.end.month), day: number(this.end.day) }
      : null
    return { qualifier: this.qualifier, year, month: number(this.start.month), day: number(this.start.day), end }
  }

  private emit() {
    this.requestUpdate()
    this.dispatchEvent(new CustomEvent('date-change', { detail: this.current(), bubbles: true, composed: true }))
  }

  private point(prefix: '' | 'end-', state: { year: string; month: string; day: string }) {
    const set = (key: 'year' | 'month' | 'day') => (event: Event) => { state[key] = (event.target as HTMLInputElement).value; this.emit() }
    return html`
      <label>День<input name="${prefix}day" inputmode="numeric" aria-label="День" .value=${state.day} @input=${set('day')} /></label>
      <label>Месяц<select name="${prefix}month" aria-label="Месяц" .value=${state.month} @change=${set('month')}>
        <option value="">—</option>${MONTHS_NOMINATIVE.map((name, index) => html`<option value=${String(index + 1)} ?selected=${state.month === String(index + 1)}>${name}</option>`)}
      </select></label>
      <label>Год<input name="${prefix}year" inputmode="numeric" aria-label="Год" .value=${state.year} @input=${set('year')} /></label>`
  }

  render() {
    const value = this.current()
    return html`<fieldset style="border:0;padding:0;margin:0"><legend class="preview">${this.label}</legend>
      <div class="row">
        <label>Вид<select name="qualifier" aria-label="Вид даты" .value=${this.qualifier} @change=${(event: Event) => { this.qualifier = (event.target as HTMLSelectElement).value as Qualifier; this.emit() }}>
          ${QUALIFIERS.map(([id, text]) => html`<option value=${id} ?selected=${this.qualifier === id}>${text}</option>`)}
        </select></label>
        ${this.point('', this.start)}
      </div>
      ${this.qualifier === 'between' ? html`<div class="row"><span class="preview">и</span>${this.point('end-', this.end)}</div>` : ''}
      ${value ? html`<p class="preview">Будет показано: ${formatDateValueRu(value)}</p>` : ''}
    </fieldset>`
  }
}

customElements.define('cats-date-input', CatsDateInput)
```

- [ ] **Step 4:** `npx vitest run test/date-input.test.ts && npm run typecheck` → PASS.

---

### Task 8: Person editor component

**Files:**
- Create: `apps/web/src/pages/person-editor.ts`
- Test: `apps/web/test/person-editor.test.ts`

**Interfaces:**
- Consumes: Task 7 `fetchEditablePerson`, `savePerson`, `archivePerson`, `restorePerson`, types; `<cats-date-input>`.
- Produces `<cats-person-editor>`: property `personId: string`, `standalone: boolean` (hidden-person page: shows banner «Человек скрыт с сайта» and no «Отмена»), `confirm: (text: string) => boolean` (default `window.confirm`, injectable for tests). Events (bubbles, composed): `person-saved` (`detail: EditablePerson`), `editor-cancel`, `person-visibility-changed` (`detail: { hidden: boolean }`).
- Form controls (names used by tests): `input[name=surname|given_name|patronymic|birth_surname]`, `select[name=sex]` (`""`, `M`, `F` → «Не указан», «Мужской», «Женский»), `select[name=birth-mode]` (`none` «Нет сведений», `date` «Дата»), `select[name=death-mode]` (`unknown` «Нет сведений», `deceased` «Умер(ла), дата неизвестна», `date` «Дата смерти»), `input[name=birth-place|death-place]` (visible when the mode is not «нет сведений»), two `cats-date-input` with `data-kind="birth"|"death"`, buttons «Сохранить», «Отмена», «Скрыть человека» / «Вернуть на сайт», `[role=alert]` for errors, `.notice` for «Дата в старом формате: …».

- [ ] **Step 1: Failing tests** `apps/web/test/person-editor.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from 'vitest'

import '../src/pages/person-editor'
import type { EditablePerson } from '../src/owner-api'

type Editor = HTMLElement & { personId: string; standalone: boolean; confirm: (text: string) => boolean; updateComplete: Promise<boolean> }
const settle = () => new Promise((resolve) => setTimeout(resolve, 0))
const PETR: EditablePerson = {
  id: 'p1', display_name: 'Петр Николаевич Кошкин', is_archived: false,
  surname: 'Кошкин', given_name: 'Петр', patronymic: 'Николаевич', birth_surname: null, sex: 'M',
  birth: { date: { qualifier: 'exact', year: 1901, month: null, day: null, end: null }, date_text: '1901', place: null },
  death: { status: 'deceased', date: { qualifier: 'exact', year: 1944, month: null, day: null, end: null }, date_text: '1944', place: null },
}
function api(person: EditablePerson, save: (body: any) => Response = (body) => new Response(JSON.stringify({ ...person, ...body }))) {
  return vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') return Promise.resolve(save(JSON.parse(String(init.body))))
    if (init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(new Response(JSON.stringify(person)))
  })
}
async function render(person: EditablePerson, fetchMock = api(person), standalone = false) {
  vi.stubGlobal('fetch', fetchMock)
  const editor = document.createElement('cats-person-editor') as Editor
  editor.personId = person.id
  editor.standalone = standalone
  editor.confirm = vi.fn(() => true)
  document.body.append(editor)
  await settle()
  await editor.updateComplete
  return { editor, fetchMock }
}
const root = (editor: Editor) => editor.shadowRoot!
function type(editor: Editor, name: string, value: string) {
  const control = root(editor).querySelector(`[name="${name}"]`) as HTMLInputElement | HTMLSelectElement
  control.value = value
  control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input'))
}
const button = (editor: Editor, text: string) => [...root(editor).querySelectorAll('button')].find((item) => item.textContent?.trim() === text) as HTMLButtonElement
async function click(editor: Editor, text: string) { button(editor, text).click(); await settle(); await editor.updateComplete }

afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

describe('cats-person-editor', () => {
  it('loads the form with the current values', async () => {
    const { editor } = await render(PETR)

    expect((root(editor).querySelector('[name="given_name"]') as HTMLInputElement).value).toBe('Петр')
    expect((root(editor).querySelector('[name="sex"]') as HTMLSelectElement).value).toBe('M')
    expect((root(editor).querySelector('[name="death-mode"]') as HTMLSelectElement).value).toBe('date')
  })

  it('saves the whole form and reports the saved person', async () => {
    const { editor, fetchMock } = await render(PETR)
    const saved = vi.fn()
    editor.addEventListener('person-saved', saved)

    type(editor, 'given_name', 'Пётр')
    type(editor, 'birth-place', 'Москва')
    type(editor, 'death-mode', 'deceased')
    await editor.updateComplete
    await click(editor, 'Сохранить')

    const [, init] = fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')!
    expect(JSON.parse(String(init!.body))).toEqual({
      surname: 'Кошкин', given_name: 'Пётр', patronymic: 'Николаевич', birth_surname: null, sex: 'M',
      birth: { date: PETR.birth!.date, place: 'Москва', date_text_keep: false },
      death: { status: 'deceased', date: null, place: null, date_text_keep: false },
    })
    expect(saved).toHaveBeenCalledTimes(1)
  })

  it('sends no birth or death when they are set to «нет сведений»', async () => {
    const { editor, fetchMock } = await render(PETR)

    type(editor, 'birth-mode', 'none')
    type(editor, 'death-mode', 'unknown')
    await editor.updateComplete
    await click(editor, 'Сохранить')

    const body = JSON.parse(String(fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]!.body))
    expect(body.birth).toBeNull()
    expect(body.death).toEqual({ status: 'unknown', date: null, place: null, date_text_keep: false })
  })

  it('keeps typed values and shows the server reason when a save is refused', async () => {
    const refuse = () => new Response(JSON.stringify({ detail: 'Укажите имя или фамилию.' }), { status: 422 })
    const { editor } = await render(PETR, api(PETR, refuse))

    type(editor, 'given_name', '')
    type(editor, 'surname', '')
    await click(editor, 'Сохранить')

    expect(root(editor).querySelector('[role="alert"]')?.textContent?.trim()).toBe('Укажите имя или фамилию.')
    expect((root(editor).querySelector('[name="patronymic"]') as HTMLInputElement).value).toBe('Николаевич')
  })

  it('keeps a date in an old free-text format unless the owner sets a new one', async () => {
    const legacy = { ...PETR, birth: { date: null, date_text: 'весной 1901', place: null } }
    const { editor, fetchMock } = await render(legacy)

    expect(root(editor).querySelector('.notice')?.textContent).toContain('весной 1901')
    await click(editor, 'Сохранить')

    const body = JSON.parse(String(fetchMock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]!.body))
    expect(body.birth).toEqual({ date: null, place: null, date_text_keep: true })
  })

  it('cancels without saving', async () => {
    const { editor, fetchMock } = await render(PETR)
    const cancelled = vi.fn()
    editor.addEventListener('editor-cancel', cancelled)

    await click(editor, 'Отмена')

    expect(cancelled).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })

  it('hides a person only after confirmation and can restore them', async () => {
    const { editor, fetchMock } = await render(PETR)
    const changed = vi.fn()
    editor.addEventListener('person-visibility-changed', changed)
    ;(editor.confirm as ReturnType<typeof vi.fn>).mockReturnValueOnce(false)

    await click(editor, 'Скрыть человека')
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/archive'))).toBe(false)

    await click(editor, 'Скрыть человека')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people/p1/archive', { method: 'POST' })
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ detail: { hidden: true } }))
    expect(button(editor, 'Вернуть на сайт')).toBeDefined()
  })

  it('shows the hidden banner on the standalone page', async () => {
    const { editor } = await render({ ...PETR, is_archived: true }, undefined, true)

    expect(root(editor).textContent).toContain('Человек скрыт с сайта')
    expect(button(editor, 'Отмена')).toBeUndefined()
    expect(button(editor, 'Вернуть на сайт')).toBeDefined()
  })
})
```

- [ ] **Step 2:** `npx vitest run test/person-editor.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement** `apps/web/src/pages/person-editor.ts`

```ts
import { LitElement, css, html } from 'lit'

import '../components/date-input'
import { archivePerson, fetchEditablePerson, restorePerson, savePerson, type DateValue, type EditablePerson, type PersonEditPayload } from '../owner-api'

type BirthMode = 'none' | 'date'
type DeathMode = 'unknown' | 'deceased' | 'date'
type Names = { surname: string; given_name: string; patronymic: string; birth_surname: string }
const text = (value: string) => value.trim() || null

export class CatsPersonEditor extends LitElement {
  static properties = { personId: { attribute: false }, standalone: { attribute: false }, person: { state: true }, names: { state: true }, sex: { state: true }, birthMode: { state: true }, deathMode: { state: true }, birthDate: { state: true }, deathDate: { state: true }, birthPlace: { state: true }, deathPlace: { state: true }, error: { state: true }, busy: { state: true } }
  declare personId: string
  declare standalone: boolean
  private declare person: EditablePerson | null
  private declare names: Names
  private declare sex: '' | 'M' | 'F'
  private declare birthMode: BirthMode
  private declare deathMode: DeathMode
  private declare birthDate: DateValue | null
  private declare deathDate: DateValue | null
  private declare birthPlace: string
  private declare deathPlace: string
  private declare error: string
  private declare busy: boolean
  confirm: (text: string) => boolean = (message) => window.confirm(message)

  constructor() {
    super()
    this.personId = ''; this.standalone = false; this.person = null; this.names = { surname: '', given_name: '', patronymic: '', birth_surname: '' }
    this.sex = ''; this.birthMode = 'none'; this.deathMode = 'unknown'; this.birthDate = null; this.deathDate = null; this.birthPlace = ''; this.deathPlace = ''; this.error = ''; this.busy = false
  }

  static styles = css`
    :host { display:block; } * { box-sizing:border-box; }
    form { display:grid; gap:1.25rem; max-width:44rem; }
    fieldset { border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:1rem; margin:0; display:grid; gap:.75rem; }
    legend { font-weight:700; padding:0 .25rem; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(12rem,1fr)); gap:.75rem; }
    label { display:grid; gap:.25rem; font-size:.8rem; color:var(--text-2,#4a4c49); font-weight:600; }
    input,select { height:2.5rem; border:1px solid var(--border-input,#cfcfca); border-radius:3px; padding:0 .6rem; font:inherit; background:#fff; }
    .actions { display:flex; gap:.5rem; flex-wrap:wrap; align-items:center; }
    button { min-height:2.5rem; border:1px solid var(--border,#dcdcd8); border-radius:3px; padding:0 1rem; background:#fff; font:600 .875rem Inter,system-ui,sans-serif; cursor:pointer; }
    button.primary { background:var(--green,#24513f); border-color:var(--green,#24513f); color:#fff; }
    button.danger { margin-left:auto; color:#7d2b20; }
    button:disabled { opacity:.6; cursor:default; }
    [role="alert"] { color:#7d2b20; margin:0; }
    .banner { background:#fbeee9; border:1px solid #e6c6bb; padding:.75rem 1rem; border-radius:3px; }
    .notice { font-size:.8rem; color:var(--text-3,#6b6d69); margin:0; }
  `

  connectedCallback() { super.connectedCallback(); void this.load() }

  private async load() {
    const result = await fetchEditablePerson(this.personId)
    if (!result.ok) { this.error = result.message; return }
    this.fill(result.value)
  }

  private fill(person: EditablePerson) {
    this.person = person
    this.names = { surname: person.surname ?? '', given_name: person.given_name ?? '', patronymic: person.patronymic ?? '', birth_surname: person.birth_surname ?? '' }
    this.sex = person.sex ?? ''
    this.birthMode = person.birth ? 'date' : 'none'
    this.birthDate = person.birth?.date ?? null
    this.birthPlace = person.birth?.place ?? ''
    this.deathMode = person.death.status === 'unknown' ? 'unknown' : person.death.date || person.death.date_text ? 'date' : 'deceased'
    this.deathDate = person.death.date
    this.deathPlace = person.death.place ?? ''
  }

  private payload(): PersonEditPayload {
    const person = this.person!
    const keepBirth = this.birthMode === 'date' && !this.birthDate && !person.birth?.date && Boolean(person.birth?.date_text)
    const keepDeath = this.deathMode === 'date' && !this.deathDate && !person.death.date && Boolean(person.death.date_text)
    return {
      surname: text(this.names.surname), given_name: text(this.names.given_name), patronymic: text(this.names.patronymic), birth_surname: text(this.names.birth_surname),
      sex: this.sex || null,
      birth: this.birthMode === 'none' ? null : { date: this.birthDate, place: text(this.birthPlace), date_text_keep: keepBirth },
      death: this.deathMode === 'unknown'
        ? { status: 'unknown', date: null, place: null, date_text_keep: false }
        : { status: 'deceased', date: this.deathMode === 'date' ? this.deathDate : null, place: text(this.deathPlace), date_text_keep: keepDeath },
    }
  }

  private async save(event: Event) {
    event.preventDefault()
    if (this.busy || !this.person) return
    this.busy = true; this.error = ''
    const result = await savePerson(this.person.id, this.payload())
    this.busy = false
    if (!result.ok) { this.error = result.message; return }
    this.fill(result.value)
    this.dispatchEvent(new CustomEvent('person-saved', { detail: result.value, bubbles: true, composed: true }))
  }

  private async toggleVisibility() {
    if (!this.person) return
    const hide = !this.person.is_archived
    if (hide && !this.confirm('Скрыть человека с сайта? Посетители перестанут видеть его имя и даты. Вернуть можно в любой момент.')) return
    const result = hide ? await archivePerson(this.person.id) : await restorePerson(this.person.id)
    if (!result.ok) { this.error = result.message; return }
    this.person = { ...this.person, is_archived: hide }
    this.dispatchEvent(new CustomEvent('person-visibility-changed', { detail: { hidden: hide }, bubbles: true, composed: true }))
  }

  private nameField(name: keyof Names, label: string) {
    return html`<label>${label}<input name=${name} .value=${this.names[name]} @input=${(event: Event) => { this.names = { ...this.names, [name]: (event.target as HTMLInputElement).value } }} /></label>`
  }

  private legacy(view: { date: DateValue | null; date_text: string | null } | null | undefined, current: DateValue | null) {
    return view && !view.date && view.date_text && !current ? html`<p class="notice">Дата в старом формате: «${view.date_text}». Она сохранится, пока вы не укажете новую.</p>` : ''
  }

  render() {
    if (!this.person) return this.error ? html`<p role="alert">${this.error}</p>` : html`<p>Загрузка…</p>`
    const person = this.person
    return html`
      ${person.is_archived ? html`<p class="banner">Человек скрыт с сайта. Посетители видят вместо него «Сведения скрыты».</p>` : ''}
      <form @submit=${this.save} novalidate>
        <fieldset><legend>Имя</legend><div class="grid">
          ${this.nameField('surname', 'Фамилия')}${this.nameField('given_name', 'Имя')}${this.nameField('patronymic', 'Отчество')}${this.nameField('birth_surname', 'Фамилия при рождении')}
          <label>Пол<select name="sex" .value=${this.sex} @change=${(event: Event) => { this.sex = (event.target as HTMLSelectElement).value as '' | 'M' | 'F' }}>
            <option value="" ?selected=${this.sex === ''}>Не указан</option><option value="M" ?selected=${this.sex === 'M'}>Мужской</option><option value="F" ?selected=${this.sex === 'F'}>Женский</option>
          </select></label>
        </div></fieldset>
        <fieldset><legend>Рождение</legend>
          <label>Сведения<select name="birth-mode" .value=${this.birthMode} @change=${(event: Event) => { this.birthMode = (event.target as HTMLSelectElement).value as BirthMode }}>
            <option value="none" ?selected=${this.birthMode === 'none'}>Нет сведений</option><option value="date" ?selected=${this.birthMode === 'date'}>Дата</option>
          </select></label>
          ${this.birthMode === 'date' ? html`
            <cats-date-input data-kind="birth" label="Дата рождения" .value=${this.birthDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.birthDate = event.detail }}></cats-date-input>
            ${this.legacy(person.birth, this.birthDate)}
            <label>Место рождения<input name="birth-place" .value=${this.birthPlace} @input=${(event: Event) => { this.birthPlace = (event.target as HTMLInputElement).value }} /></label>` : ''}
        </fieldset>
        <fieldset><legend>Смерть</legend>
          <label>Сведения<select name="death-mode" .value=${this.deathMode} @change=${(event: Event) => { this.deathMode = (event.target as HTMLSelectElement).value as DeathMode }}>
            <option value="unknown" ?selected=${this.deathMode === 'unknown'}>Нет сведений</option><option value="deceased" ?selected=${this.deathMode === 'deceased'}>Умер(ла), дата неизвестна</option><option value="date" ?selected=${this.deathMode === 'date'}>Дата смерти</option>
          </select></label>
          ${this.deathMode === 'date' ? html`
            <cats-date-input data-kind="death" label="Дата смерти" .value=${this.deathDate} @date-change=${(event: CustomEvent<DateValue | null>) => { this.deathDate = event.detail }}></cats-date-input>
            ${this.legacy(person.death, this.deathDate)}` : ''}
          ${this.deathMode !== 'unknown' ? html`<label>Место смерти<input name="death-place" .value=${this.deathPlace} @input=${(event: Event) => { this.deathPlace = (event.target as HTMLInputElement).value }} /></label>` : ''}
        </fieldset>
        ${this.error ? html`<p role="alert">${this.error}</p>` : ''}
        <div class="actions">
          <button class="primary" type="submit" ?disabled=${this.busy}>${this.busy ? 'Сохраняем…' : 'Сохранить'}</button>
          ${this.standalone ? '' : html`<button type="button" @click=${() => this.dispatchEvent(new CustomEvent('editor-cancel', { bubbles: true, composed: true }))}>Отмена</button>`}
          <button class="danger" type="button" @click=${this.toggleVisibility}>${person.is_archived ? 'Вернуть на сайт' : 'Скрыть человека'}</button>
        </div>
      </form>`
  }
}

customElements.define('cats-person-editor', CatsPersonEditor)
```

Note on the «deceased» test: `death-mode` = `deceased` sends `date: null` even though `deathDate` still holds 1944 — intended (the owner chose «дата неизвестна»).

- [ ] **Step 4:** `npx vitest run test/person-editor.test.ts && npm run typecheck` → PASS.

---

### Task 9: Owner entry points (person page, shell, tree inspector)

**Files:**
- Modify: `apps/web/src/pages/person-card.ts`
- Modify: `apps/web/src/app-shell.ts`
- Modify: `apps/web/src/pages/tree-page.ts`
- Test: `apps/web/test/person-card.test.ts`, `apps/web/test/app-shell.test.ts`, `apps/web/test/tree-page.test.ts`

**Interfaces:**
- Consumes: `<cats-person-editor>` (Task 8), `searchOwnerPeople` (Task 7), shell `ownerStatus` (stage 0).
- Produces: `cats-person-card.isOwner: boolean`, event `person-changed` (bubbles, composed) from the card; `cats-tree-page.isOwner: boolean`.

- [ ] **Step 1: Failing tests**

`apps/web/test/person-card.test.ts` — change the first import to `import { afterEach, expect, it, vi } from 'vitest'` and append:

```ts
const person = {
  id: 'p1', display_name: 'Анна Иванова', biography: null, events: [], parents: [], children: [], partners: [], media: [],
}
afterEach(() => { document.body.replaceChildren(); vi.unstubAllGlobals() })

it('shows «Изменить» only to the owner and opens the editor in place', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: person.id, display_name: person.display_name, is_archived: false, surname: null, given_name: 'Анна', patronymic: null, birth_surname: null, sex: null, birth: null, death: { status: 'unknown', date: null, date_text: null, place: null } }))))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  document.body.append(card)
  await card.updateComplete
  const edit = () => [...card.shadowRoot!.querySelectorAll('button')].find((item) => item.textContent?.trim() === 'Изменить')
  expect(edit()).toBeUndefined()

  card.isOwner = true
  await card.updateComplete
  edit()!.click()
  await card.updateComplete

  expect(card.shadowRoot!.querySelector('cats-person-editor')).not.toBeNull()
})

it('opens the editor directly for the owner on ?edit=1 and reports a save', async () => {
  history.pushState({}, '', `/people/${person.id}?edit=1`)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; isOwner: boolean; updateComplete: Promise<boolean> }
  card.person = person
  card.isOwner = true
  const changed = vi.fn()
  card.addEventListener('person-changed', changed)
  document.body.append(card)
  await card.updateComplete

  const editor = card.shadowRoot!.querySelector('cats-person-editor')!
  editor.dispatchEvent(new CustomEvent('person-saved', { detail: {}, bubbles: true, composed: true }))
  await card.updateComplete

  expect(changed).toHaveBeenCalledTimes(1)
  expect(card.shadowRoot!.querySelector('cats-person-editor')).toBeNull()
  expect(card.shadowRoot!.textContent).toContain('Сохранено')
  history.pushState({}, '', '/')
})

it('shows the birth surname by sex', async () => {
  const card = document.createElement('cats-person-card') as HTMLElement & { person: unknown; updateComplete: Promise<boolean> }
  card.person = { ...person, sex: 'F', birth_surname: 'Петрова' }
  document.body.append(card)
  await card.updateComplete

  expect(card.shadowRoot!.textContent).toContain('урождённая Петрова')
})
```

`apps/web/test/app-shell.test.ts` (append inside the describe; `statusFetch` and `settled` exist from stage 0 — extend the mock as shown):

```ts
  it('searches with the owner endpoint and marks hidden people', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.startsWith('/api/v1/admin/people?query=')) return Promise.resolve(new Response(JSON.stringify([{ id: 'h1', display_name: 'Анна Скрытая', years: null, is_archived: true }])))
      return Promise.resolve(new Response('[]'))
    })
    vi.stubGlobal('fetch', fetchMock)
    const element = await renderApp()
    await vi.runAllTimersAsync()
    const search = element.shadowRoot!.querySelector<HTMLInputElement>('input[type="search"]')!

    search.value = 'Анна'
    search.dispatchEvent(new Event('input'))
    await vi.runAllTimersAsync()
    await element.updateComplete

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/admin/people?query=%D0%90%D0%BD%D0%BD%D0%B0')
    expect(element.shadowRoot!.querySelector('.search-result')?.textContent).toContain('скрыт')
  })

  it('opens the editor for a hidden person when the owner is signed in', async () => {
    history.pushState({}, '', '/people/h1')
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/status')) return Promise.resolve(new Response(JSON.stringify({ authenticated: true, totp_required: false })))
      if (url.endsWith('/api/v1/people/h1')) return Promise.resolve(new Response('{}', { status: 404 }))
      return Promise.resolve(new Response('[]'))
    }))
    const element = await renderApp()
    await settled(element)
    await settled(element)

    const editor = element.shadowRoot!.querySelector('cats-person-editor') as HTMLElement & { personId: string; standalone: boolean }
    expect(editor.personId).toBe('h1')
    expect(editor.standalone).toBe(true)
  })
```

`apps/web/test/tree-page.test.ts` (append): select `boris` via a `person-select` event as in the existing inspector test; with `element.isOwner = true` the inspector contains `a[href="/people/boris?edit=1"]` with text «Изменить»; with `isOwner = false` it does not.

- [ ] **Step 2:** run the three files → new tests FAIL.

- [ ] **Step 3: Implement**

`person-card.ts`:
- `import './person-editor'`; extend `PublicPerson` with `birth_surname?: string | null; sex?: string | null`.
- `static properties = { person: { attribute: false }, isOwner: { attribute: false }, editing: { state: true }, saved: { state: true } }`; defaults `isOwner = false`, `editing = false`, `saved = false`.
- `willUpdate(changed)`: if `changed.has('isOwner') && this.isOwner && new URLSearchParams(window.location.search).get('edit') === '1'` → `this.editing = true`.
- In the hero actions, when `this.isOwner && !this.editing`: `<button class="button" @click=${() => { this.editing = true; this.saved = false }}>Изменить</button>`; when `this.saved`: `<span class="saved" role="status">Сохранено</span>`.
- When `this.editing`, render instead of the hero: `<cats-person-editor .personId=${person.id} @person-saved=${this.onSaved} @editor-cancel=${() => { this.editing = false }} @person-visibility-changed=${this.onSaved}></cats-person-editor>` where `onSaved = () => { this.editing = false; this.saved = true; this.dispatchEvent(new CustomEvent('person-changed', { bubbles: true, composed: true })) }`.
- Under the `h1`, when `person.birth_surname`: `<p class="life">${person.sex === 'F' ? 'урождённая' : person.sex === 'M' ? 'урождённый' : 'при рождении'} ${person.birth_surname}</p>`.
- Add `.button` styling for `<button>` identical to the existing `.button` links (reuse the same class).

`app-shell.ts`:
- `import { searchOwnerPeople } from './owner-api'` and `import './pages/person-editor'`.
- State `hiddenPersonId: string | null` (default `null`). In `loadPersonFromPath`: on a non-OK response set `this.hiddenPersonId = match[1]` and `this.person = null`; on OK set `hiddenPersonId = null`.
- Render branch before the person card: `!this.person && this.hiddenPersonId && this.ownerStatus.authenticated` → `<section style="padding:2rem 1rem;max-width:60rem;margin:0 auto"><cats-person-editor .personId=${this.hiddenPersonId} .standalone=${true} @person-visibility-changed=${() => this.loadPersonFromPath()}></cats-person-editor></section>`.
- Person card: `<cats-person-card .person=${this.person} .isOwner=${this.ownerStatus.authenticated} @person-changed=${() => this.loadPersonFromPath()}>`.
- Tree page: add `.isOwner=${this.ownerStatus.authenticated}`.
- `requestSearch`: when `this.ownerStatus.authenticated`, call `searchOwnerPeople(this.query)` and map `{ id, display_name, years, is_archived }` to the existing result type (extend `SearchPerson` usage with an optional `is_archived?: boolean`); otherwise keep the public request. In the result markup append `${person.is_archived ? html`<span class="result-meta">скрыт</span>` : ''}`.

`tree-page.ts`:
- `static properties` add `isOwner: { attribute: false }`; `declare isOwner: boolean`; constructor `this.isOwner = false`.
- In the inspector actions after «Открыть страницу»: `${this.isOwner ? html`<a href="/people/${person.id}?edit=1">Изменить</a>` : ''}`.

- [ ] **Step 4:** `npm test && npm run typecheck` → all PASS.

---

### Task 10: Real data, end-to-end check, docs and final verification

**Files:**
- Modify: `apps/web/e2e/owner-login.spec.ts` (append test)
- Modify: `README.md` («Вход владельца» section → add «Исправление людей»)

- [ ] **Step 1: E2E** (append; runs only with the owner password; never saves):

```ts
test('the owner opens the editor for a real person and cancels without saving', async ({ page }) => {
  test.skip(!password, 'Set CATS_HOUSE_E2E_OWNER_PASSWORD to run the owner editor check.')
  await page.goto('/login?next=%2Fpeople%2Fca7750a8-ecfe-4cf4-a58c-9e9806656913')
  await page.getByLabel('Пароль').fill(password!)
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page).toHaveURL(/\/people\/ca7750a8/)

  await page.getByRole('button', { name: 'Изменить' }).click()
  await expect(page.getByLabel('Фамилия')).toHaveValue(/.+/)
  await page.getByRole('button', { name: 'Отмена' }).click()
  await expect(page.getByRole('button', { name: 'Изменить' })).toBeVisible()
})
```

- [ ] **Step 2: README** — after the «Вход владельца» section add:

```markdown
### Исправление людей

Владелец открывает страницу человека и нажимает «Изменить»: фамилия, имя,
отчество, фамилия при рождении, пол, даты и места рождения и смерти. Даты
вводятся по частям и бывают точными, приблизительными («около»), «до»,
«после» и «между». Там же человека можно скрыть с сайта и вернуть. Скрытых
людей владелец находит поиском в шапке. Каждое сохранение пишется в журнал
правок. После первой правки пересборка событий из AT5 больше не запускается.

Части имени один раз заполняются из AT5 (пробный прогон, затем `--apply`):

```sh
apps/api/.venv/bin/python scripts/backfill-name-parts.py --at5 "/абсолютный/путь/к/Древо.at5"
```
```

- [ ] **Step 3: Restart the running stack** (Ctrl-C in the «Cat's House dev» terminal tab, then `CATS_HOUSE_WEB_PORT=5176 bash scripts/dev-native.sh`), so the migration 0006 is applied and the new API is served. Confirm `GET http://localhost:8000/api/v1/auth/status` answers 200.

- [ ] **Step 4: Backfill dry run on the real database** (read-only):

```bash
apps/api/.venv/bin/python scripts/backfill-name-parts.py --at5 "/Users/ekoshkin/Downloads/Древо 2.at5"
```

Expected: «Пробный прогон», «Заполнено людей: 280», «Собранное имя отличается от отображаемого: 0» (all 280 names matched AT5 when checked on 2026-10-06). **Stop and ask the owner before `--apply`.** If they agree: `apps/api/.venv/bin/python scripts/create-local-backup.py --output "/Users/ekoshkin/Cat's House backups"` (run with the `.env` loaded the way `dev-native.sh` does), then the same backfill command with `--apply`.

- [ ] **Step 5: Final verification** — each must exit 0:

```bash
cd apps/api && .venv/bin/pytest -q
cd apps/web && npm test && npm run typecheck && npm run build && npm run test:e2e
```

Then check by hand at `http://localhost:5176`: sign in, open «Петр Николаевич Кошкин», «Изменить», set birth to «Около · 1901» and look at the preview, press «Отмена» (do not save real data unless the owner asks).

- [ ] **Step 6: Hand over** — report results, rulings and deferred minors; do not commit, push or merge unless the owner asks.
