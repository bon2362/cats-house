from pathlib import Path

import pytest

from app.gedcom.parser import build_preview, parse_date, parse_gedcom


def fixture_bytes(name: str) -> bytes:
    return (Path(__file__).parent / "fixtures" / name).read_bytes()


def test_parser_keeps_utf8_bom_cyrillic_and_source_uid():
    preview = build_preview(parse_gedcom(b"\xef\xbb\xbf" + fixture_bytes("cyrillic-family.ged")))

    assert preview.people[0].name == "Анна Иванова"
    assert preview.people[0].source_uid == "E403332A_50"


@pytest.mark.parametrize(
    ("value", "qualifier"),
    [("ABT 1900", "about"), ("BEF 1900", "before"), ("AFT 1900", "after"), ("BET 1900 AND 1910", "between")],
)
def test_parser_preserves_uncertain_dates(value, qualifier):
    assert parse_date(value).qualifier == qualifier


def test_parser_keeps_multiple_unions_and_children_in_correct_union():
    preview = build_preview(parse_gedcom(fixture_bytes("complex-family.ged")))

    assert len(preview.unions) == 2
    assert {link.child_pointer for link in preview.parent_links} == {"@I4@", "@I5@"}


def test_parser_reports_missing_person_reference_with_line_number():
    preview = build_preview(parse_gedcom(fixture_bytes("invalid-reference.ged")))

    issue = next(issue for issue in preview.issues if issue.severity == "error")
    assert issue.line_number == 7
    assert "@I404@" in issue.message
