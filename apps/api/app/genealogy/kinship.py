from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal, Sequence
from uuid import UUID


KinshipKind = Literal["blood-direct", "blood-sibling", "blood-collateral", "affinity", "descriptive"]
KinshipCertainty = Literal["confirmed", "descriptive"]


@dataclass(frozen=True)
class KinshipPerson:
    id: UUID
    sex: str | None
    is_archived: bool
    display_name: str | None = None


@dataclass(frozen=True)
class KinshipParentLink:
    parent_id: UUID
    child_id: UUID
    relationship_type: str


@dataclass(frozen=True)
class KinshipUnion:
    partner_one_id: UUID
    partner_two_id: UUID


@dataclass(frozen=True)
class KinshipResult:
    label: str
    kind: KinshipKind
    certainty: KinshipCertainty
    reason: str


def resolve_kinship(
    centre_id: UUID,
    target_id: UUID,
    people: dict[UUID, KinshipPerson],
    parent_links: Sequence[KinshipParentLink],
    unions: Sequence[KinshipUnion],
) -> KinshipResult | None:
    """Return a proven relationship from ``centre_id`` to ``target_id``.

    This deliberately depends only on graph facts.  Affinity rules are added
    below the blood classifier in a subsequent task; unions are accepted now
    so the public pure function's signature remains stable.
    """
    if centre_id == target_id or centre_id not in people or target_id not in people:
        return None

    parents = _biological_parents(parent_links)
    blood = _resolve_blood(centre_id, target_id, people, parents)
    if blood is not None:
        return blood
    return _resolve_affinity(centre_id, target_id, people, parents, unions)


def _resolve_blood(
    centre_id: UUID,
    target_id: UUID,
    people: dict[UUID, KinshipPerson],
    parents: dict[UUID, set[UUID]],
) -> KinshipResult | None:
    centre_ancestors = _ancestor_distances(centre_id, parents)
    target_ancestors = _ancestor_distances(target_id, parents)
    target = people[target_id]

    if target_id in centre_ancestors:
        return _direct_result(target.sex, centre_ancestors[target_id], direction="up")
    if centre_id in target_ancestors:
        return _direct_result(target.sex, target_ancestors[centre_id], direction="down")

    shared_parents = {
        ancestor_id
        for ancestor_id, distance in centre_ancestors.items()
        if distance == 1 and target_ancestors.get(ancestor_id) == 1
    }
    if shared_parents:
        return _sibling_result(target.sex, shared_parents, people)

    common = [
        (ancestor_id, centre_distance, target_ancestors[ancestor_id])
        for ancestor_id, centre_distance in centre_ancestors.items()
        if ancestor_id in target_ancestors
    ]
    if not common:
        return None
    shortest = min(centre_distance + target_distance for _, centre_distance, target_distance in common)
    labels = {
        _collateral_result(target.sex, centre_distance, target_distance).label
        for _, centre_distance, target_distance in common
        if centre_distance + target_distance == shortest
    }
    if len(labels) != 1:
        return KinshipResult(
            label="родственник по двум семейным линиям",
            kind="descriptive",
            certainty="descriptive",
            reason="несколько равных подтверждённых путей",
        )
    return next(
        _collateral_result(target.sex, centre_distance, target_distance)
        for _, centre_distance, target_distance in common
        if centre_distance + target_distance == shortest
    )


def _resolve_affinity(
    centre_id: UUID,
    target_id: UUID,
    people: dict[UUID, KinshipPerson],
    parents: dict[UUID, set[UUID]],
    unions: Sequence[KinshipUnion],
) -> KinshipResult | None:
    partners: dict[UUID, set[UUID]] = {}
    for union in unions:
        partners.setdefault(union.partner_one_id, set()).add(union.partner_two_id)
        partners.setdefault(union.partner_two_id, set()).add(union.partner_one_id)
    centre = people[centre_id]
    target = people[target_id]

    if target_id in partners.get(centre_id, set()):
        return _spouse_result(target.sex)

    children = {child_id for child_id, parent_ids in parents.items() if centre_id in parent_ids}
    if any(target_id in partners.get(child_id, set()) for child_id in children):
        return _gendered_affinity(target.sex, "зять", "невестка", "супруг ребёнка")

    siblings = {person_id for person_id, parent_ids in parents.items() if person_id != centre_id and parent_ids & parents.get(centre_id, set())}
    if any(target_id in partners.get(sibling_id, set()) for sibling_id in siblings):
        return _gendered_affinity(target.sex, "зять", "невестка", "супруг сиблинга")

    for spouse_id in partners.get(centre_id, set()):
        if target_id in parents.get(spouse_id, set()):
            return _spouse_parent_result(centre.sex, target.sex)
        if parents.get(target_id, set()) & parents.get(spouse_id, set()):
            return _spouse_sibling_result(centre.sex, target.sex)

    if _is_female(centre.sex) and _is_female(target.sex):
        for centre_spouse in partners.get(centre_id, set()):
            for target_spouse in partners.get(target_id, set()):
                if (
                    _is_male(people.get(centre_spouse, KinshipPerson(centre_spouse, None, False)).sex)
                    and _is_male(people.get(target_spouse, KinshipPerson(target_spouse, None, False)).sex)
                    and len(parents.get(centre_spouse, set()) & parents.get(target_spouse, set())) >= 2
                ):
                    return KinshipResult("ятровка", "affinity", "confirmed", "жёны двух родных братьев")
    return None


def _spouse_result(sex: str | None) -> KinshipResult:
    return _gendered_affinity(sex, "муж", "жена", "супруг центра")


def _gendered_affinity(sex: str | None, male: str, female: str, reason: str) -> KinshipResult:
    if not _is_known_sex(sex):
        return KinshipResult("родственник по браку", "descriptive", "descriptive", reason)
    return KinshipResult(_gendered(sex, male, female, ""), "affinity", "confirmed", reason)


def _spouse_parent_result(centre_sex: str | None, target_sex: str | None) -> KinshipResult:
    if _is_male(centre_sex):
        return _gendered_affinity(target_sex, "тесть", "тёща", "родитель супруги")
    if _is_female(centre_sex):
        return _gendered_affinity(target_sex, "свёкор", "свекровь", "родитель супруга")
    return KinshipResult("родственник по браку", "descriptive", "descriptive", "родитель супруга центра")


def _spouse_sibling_result(centre_sex: str | None, target_sex: str | None) -> KinshipResult:
    if _is_male(centre_sex):
        return _gendered_affinity(target_sex, "шурин", "свояченица", "сиблинг супруги")
    if _is_female(centre_sex):
        return _gendered_affinity(target_sex, "деверь", "золовка", "сиблинг супруга")
    return KinshipResult("родственник по браку", "descriptive", "descriptive", "сиблинг супруга центра")


def _biological_parents(links: Sequence[KinshipParentLink]) -> dict[UUID, set[UUID]]:
    parents: dict[UUID, set[UUID]] = {}
    for link in links:
        if link.relationship_type == "biological":
            parents.setdefault(link.child_id, set()).add(link.parent_id)
    return parents


def _ancestor_distances(person_id: UUID, parents: dict[UUID, set[UUID]]) -> dict[UUID, int]:
    distances = {person_id: 0}
    queue = deque([person_id])
    while queue:
        child_id = queue.popleft()
        for parent_id in parents.get(child_id, ()):
            if parent_id not in distances:
                distances[parent_id] = distances[child_id] + 1
                queue.append(parent_id)
    return distances


def _direct_result(sex: str | None, distance: int, *, direction: Literal["up", "down"]) -> KinshipResult:
    if direction == "up":
        if distance == 1:
            label = _gendered(sex, "отец", "мать", "родитель")
        elif distance == 2:
            label = _gendered(sex, "дедушка", "бабушка", "дедушка или бабушка")
        elif _is_known_sex(sex):
            label = _pra(distance - 2) + _gendered(sex, "дедушка", "бабушка", "")
        else:
            label = "предок"
    else:
        if distance == 1:
            label = _gendered(sex, "сын", "дочь", "ребёнок")
        elif distance == 2:
            label = _gendered(sex, "внук", "внучка", "внук или внучка")
        elif _is_known_sex(sex):
            label = _pra(distance - 2) + _gendered(sex, "внук", "внучка", "")
        else:
            label = "потомок"
    return KinshipResult(label=label, kind="blood-direct", certainty="confirmed", reason="прямая линия родства")


def _sibling_result(sex: str | None, parent_ids: set[UUID], people: dict[UUID, KinshipPerson]) -> KinshipResult:
    if len(parent_ids) >= 2:
        return KinshipResult(_gendered(sex, "брат", "сестра", "сиблинг"), "blood-sibling", "confirmed", "общие родители")
    parent = people.get(next(iter(parent_ids)))
    if _is_male(parent.sex if parent else None):
        prefix = "единокровный"
    elif _is_female(parent.sex if parent else None):
        prefix = "единоутробный"
    else:
        prefix = "неполнородный"
    label = _gendered_adjective_noun(sex, prefix, "брат", "сестра", "сиблинг")
    return KinshipResult(label, "blood-sibling", "confirmed", "один общий родитель")


def _collateral_result(sex: str | None, centre_distance: int, target_distance: int) -> KinshipResult:
    if centre_distance == target_distance:
        prefix = _cousin_prefix(centre_distance)
        label = _gendered_adjective_noun(sex, prefix, "брат", "сестра", "сиблинг")
        return KinshipResult(label, "blood-collateral", "confirmed", "ближайший общий предок")
    if abs(centre_distance - target_distance) == 1:
        if target_distance < centre_distance:
            if target_distance == 1:
                label = _gendered(sex, "дядя", "тётя", "дядя или тётя")
            else:
                label = _gendered_adjective_noun(sex, _cousin_prefix(target_distance), "дядя", "тётя", "дядя или тётя")
        else:
            if centre_distance == 1:
                label = _gendered(sex, "племянник", "племянница", "племянник или племянница")
            else:
                label = _gendered_adjective_noun(sex, _cousin_prefix(centre_distance), "племянник", "племянница", "племянник или племянница")
        return KinshipResult(label, "blood-collateral", "confirmed", "ближайший общий предок")
    return KinshipResult(
        label="родственник по боковой линии",
        kind="descriptive",
        certainty="descriptive",
        reason="подтверждённый общий предок на разных поколениях",
    )


def _pra(count: int) -> str:
    return "пра-" * count


def _cousin_prefix(distance: int) -> str:
    if distance == 2:
        return "двоюродный"
    if distance == 3:
        return "троюродный"
    return f"{distance}-юродный"


def _gendered(sex: str | None, male: str, female: str, unknown: str) -> str:
    if _is_male(sex):
        return male
    if _is_female(sex):
        return female
    return unknown


def _gendered_adjective_noun(sex: str | None, adjective: str, male: str, female: str, unknown: str) -> str:
    if _is_male(sex):
        return f"{adjective} {male}"
    if _is_female(sex):
        feminine = adjective[:-2] + "ая" if adjective.endswith("ый") else adjective
        return f"{feminine} {female}"
    return f"{adjective} {unknown}"


def _is_male(sex: str | None) -> bool:
    return sex is not None and sex.lower() in {"m", "male", "м", "мужской"}


def _is_female(sex: str | None) -> bool:
    return sex is not None and sex.lower() in {"f", "female", "ж", "женский"}


def _is_known_sex(sex: str | None) -> bool:
    return _is_male(sex) or _is_female(sex)
