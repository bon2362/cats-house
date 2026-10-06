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
