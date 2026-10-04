from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class GenealogyDate:
    text: str
    qualifier: str
    lower: date | None = None
    upper: date | None = None


@dataclass(frozen=True)
class ParsedPerson:
    pointer: str
    name: str
    source_uid: str | None
    sex: str | None
    family_as_child: str | None
    families_as_spouse: tuple[str, ...]
    events: tuple[tuple[str, GenealogyDate | None], ...]


@dataclass(frozen=True)
class ParsedFamily:
    pointer: str
    husband: str | None
    wife: str | None
    children: tuple[str, ...]
    events: tuple[tuple[str, GenealogyDate | None], ...] = ()


@dataclass(frozen=True)
class ParentLink:
    parent_pointer: str
    child_pointer: str


@dataclass(frozen=True)
class PreviewEvent:
    event_type: str
    person_pointer: str | None = None
    union_pointer: str | None = None
    date: GenealogyDate | None = None


@dataclass(frozen=True)
class ImportIssue:
    severity: str
    message: str
    line_number: int | None = None
    tag: str | None = None


@dataclass(frozen=True)
class ParsedGedcom:
    people: tuple[ParsedPerson, ...]
    families: tuple[ParsedFamily, ...]
    issues: tuple[ImportIssue, ...] = ()


@dataclass(frozen=True)
class ImportPreview:
    people: tuple[ParsedPerson, ...]
    unions: tuple[ParsedFamily, ...]
    parent_links: tuple[ParentLink, ...]
    events: tuple[PreviewEvent, ...]
    issues: tuple[ImportIssue, ...]
    counts: dict[str, int]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)
