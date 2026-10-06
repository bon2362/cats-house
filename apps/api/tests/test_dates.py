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
