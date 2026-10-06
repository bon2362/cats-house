from uuid import UUID, uuid4

from app.genealogy.kinship import KinshipParentLink, KinshipPerson, resolve_kinship


def person(sex: str | None = None) -> KinshipPerson:
    return KinshipPerson(id=uuid4(), sex=sex, is_archived=False)


def link(parent: KinshipPerson, child: KinshipPerson) -> KinshipParentLink:
    return KinshipParentLink(parent_id=parent.id, child_id=child.id, relationship_type="biological")


def resolve(
    centre: KinshipPerson,
    target: KinshipPerson,
    links: list[KinshipParentLink],
    *known_people: KinshipPerson,
):
    people = {item.id: item for item in (centre, target, *known_people)}
    for item_id in {edge.parent_id for edge in links} | {edge.child_id for edge in links}:
        people.setdefault(item_id, KinshipPerson(id=item_id, sex=None, is_archived=False))
    return resolve_kinship(centre.id, target.id, people, links, [])


def test_blood_resolves_full_sister_from_two_shared_biological_parents():
    father, mother = person("male"), person("female")
    centre, sister = person("male"), person("female")

    result = resolve(centre, sister, [link(father, centre), link(mother, centre), link(father, sister), link(mother, sister)])

    assert result is not None
    assert result.label == "сестра"
    assert result.reason == "общие родители"


def test_blood_distinguishes_paternal_and_maternal_half_siblings():
    father, mother = person("male"), person("female")
    centre, paternal_sister, maternal_brother = person("male"), person("female"), person("male")

    paternal = resolve(centre, paternal_sister, [link(father, centre), link(father, paternal_sister)], father)
    maternal = resolve(centre, maternal_brother, [link(mother, centre), link(mother, maternal_brother)], mother)

    assert paternal is not None and paternal.label == "единокровная сестра"
    assert maternal is not None and maternal.label == "единоутробный брат"


def test_blood_resolves_three_great_grandchildren_with_hyphens():
    centre = person("female")
    descendants = [person() for _ in range(4)]
    target = person("male")
    chain = [centre, *descendants, target]

    result = resolve(centre, target, [link(parent, child) for parent, child in zip(chain, chain[1:])])

    assert result is not None
    assert result.label == "пра-пра-пра-внук"


def test_blood_resolves_first_and_second_cousins_from_nearest_common_ancestor():
    ancestor = person()
    centre_parent, target_parent = person(), person()
    centre, first_cousin = person("male"), person("female")
    first_links = [link(ancestor, centre_parent), link(ancestor, target_parent), link(centre_parent, centre), link(target_parent, first_cousin)]

    first = resolve(centre, first_cousin, first_links)

    assert first is not None and first.label == "двоюродная сестра"

    second_ancestor = person()
    centre_line = [person(), person(), person("female")]
    target_line = [person(), person(), person("male")]
    second_links = [
        link(second_ancestor, centre_line[0]), link(centre_line[0], centre_line[1]), link(centre_line[1], centre_line[2]),
        link(second_ancestor, target_line[0]), link(target_line[0], target_line[1]), link(target_line[1], target_line[2]),
    ]

    second = resolve(centre_line[2], target_line[2], second_links)

    assert second is not None and second.label == "троюродный брат"


def test_blood_resolves_aunt_and_nephew_and_unknown_sex():
    grandparent = person()
    centre_parent, aunt, centre, nephew, unknown_parent = person(), person("female"), person("male"), person("male"), person()
    aunt_result = resolve(centre, aunt, [link(grandparent, centre_parent), link(grandparent, aunt), link(centre_parent, centre)])
    nephew_result = resolve(aunt, nephew, [link(grandparent, centre_parent), link(grandparent, aunt), link(centre_parent, nephew)])
    unknown_result = resolve(centre, unknown_parent, [link(unknown_parent, centre)])

    assert aunt_result is not None and aunt_result.label == "тётя"
    assert nephew_result is not None and nephew_result.label == "племянник"
    assert unknown_result is not None and unknown_result.label == "родитель"


def test_blood_returns_descriptive_result_for_equally_short_incompatible_paths():
    first_ancestor, second_ancestor = person(), person()
    centre_parent, target_parent = person(), person()
    centre, target = person("male"), person("female")
    # Equal-length paths make the target both an aunt and a niece.
    links = [
        link(first_ancestor, centre), link(first_ancestor, target_parent), link(target_parent, target),
        link(second_ancestor, centre_parent), link(centre_parent, centre), link(second_ancestor, target),
    ]

    result = resolve(centre, target, links)

    assert result is not None
    assert result.kind == "descriptive"
    assert result.certainty == "descriptive"
