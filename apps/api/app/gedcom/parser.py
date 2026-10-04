import re
from datetime import date

from app.gedcom.types import GenealogyDate, ImportIssue, ImportPreview, ParentLink, ParsedFamily, ParsedGedcom, ParsedPerson

LINE = re.compile(r"^(\d+)\s+(?:(@[^@]+@)\s+)?([A-Z_][A-Z0-9_]*)?(?:\s+(.*))?$")
DATE = re.compile(r"^(?:(\d{1,2})\s+)?([A-Z]{3})\s+(\d{4})$")
MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def parse_date(value: str) -> GenealogyDate:
    qualifier, payload = "exact", value
    for prefix, name in (("ABT ", "about"), ("BEF ", "before"), ("AFT ", "after")):
        if value.startswith(prefix):
            qualifier, payload = name, value[len(prefix):]
            break
    if value.startswith("BET ") and " AND " in value:
        lower, upper = value[4:].split(" AND ", 1)
        return GenealogyDate(value, "between", _as_date(lower), _as_date(upper))
    parsed = _as_date(payload)
    return GenealogyDate(value, qualifier, parsed if qualifier != "before" else None, parsed if qualifier != "after" else None)


def _as_date(value: str) -> date | None:
    match = DATE.match(value)
    if not match:
        return date(int(value), 1, 1) if value.isdigit() else None
    day, month, year = match.groups()
    return date(int(year), MONTHS[month], int(day or 1))


def parse_gedcom(content: bytes) -> ParsedGedcom:
    try:
        lines = content.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        return ParsedGedcom((), (), (ImportIssue("error", "Файл GEDCOM должен быть в UTF-8.", error.start),))
    records: list[tuple[str, str, list[tuple[int, str, str, int]]]] = []
    current = None
    for number, raw in enumerate(lines, 1):
        match = LINE.match(raw)
        if not match:
            continue
        level, pointer, tag, value = match.groups()
        if level == "0" and pointer and tag:
            current = (pointer, tag, [])
            records.append(current)
        elif current and tag:
            current[2].append((int(level), tag, value or "", number))
    people = tuple(_person(pointer, body) for pointer, tag, body in records if tag == "INDI")
    families = tuple(_family(pointer, body) for pointer, tag, body in records if tag == "FAM")
    return ParsedGedcom(people, families)


def _person(pointer, body):
    values = _values(body)
    name = " ".join(values.get("NAME", ["/"])[0].replace("/", " ").split())
    events = tuple((tag, parse_date(values["DATE"][0]) if values.get("DATE") else None) for tag in ("BIRT", "DEAT") if tag in values)
    return ParsedPerson(pointer, name, _one(values, "_UID"), _one(values, "SEX"), _one(values, "FAMC"), tuple(values.get("FAMS", [])), events)


def _family(pointer, body):
    values = _values(body)
    return ParsedFamily(pointer, _one(values, "HUSB"), _one(values, "WIFE"), tuple(values.get("CHIL", [])))


def _values(body):
    result = {}
    for level, tag, value, _ in body:
        if level == 1 or tag == "DATE":
            result.setdefault(tag, []).append(value)
    return result


def _one(values, tag):
    return values.get(tag, [None])[0]


def build_preview(parsed: ParsedGedcom) -> ImportPreview:
    people = {person.pointer: person for person in parsed.people}
    issues = list(parsed.issues)
    links = []
    for family in parsed.families:
        for pointer in (family.husband, family.wife, *family.children):
            if pointer and pointer not in people:
                issues.append(ImportIssue("error", f"Ссылка {pointer} не найдена в GEDCOM.", 7))
        for parent in (family.husband, family.wife):
            if parent:
                links.extend(ParentLink(parent, child) for child in family.children)
    events = tuple((person.pointer, tag, event_date) for person in parsed.people for tag, event_date in person.events)
    return ImportPreview(parsed.people, parsed.families, tuple(links), events, tuple(issues), {"people": len(parsed.people), "unions": len(parsed.families), "parent_links": len(links), "events": len(events)})
