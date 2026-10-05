from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.genealogy import ImportRun, ParentChild, Person, Union


@pytest.fixture
def database_session(client, settings):
    with Session(create_engine(settings.database_url)) as session:
        yield session


def create_person(session, run, name):
    person = Person(import_run_id=run.id, display_name=name, source_uid=str(uuid4()))
    session.add(person)
    session.flush()
    return person


def test_all_mode_returns_entire_connected_public_component(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="f" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    ancestor = create_person(database_session, run, "Анна")
    root = create_person(database_session, run, "Борис")
    sibling = create_person(database_session, run, "Вера")
    partner = create_person(database_session, run, "Глеб")
    archived_parent = create_person(database_session, run, "Скрытая Дина")
    archived_parent.is_archived = True
    unrelated = create_person(database_session, run, "Егор")
    unrelated_partner = create_person(database_session, run, "Жанна")
    database_session.add_all((
        ParentChild(parent_id=ancestor.id, child_id=root.id),
        ParentChild(parent_id=ancestor.id, child_id=sibling.id),
        ParentChild(parent_id=archived_parent.id, child_id=partner.id),
        Union(import_run_id=run.id, partner_one_id=sibling.id, partner_two_id=partner.id, union_type="marriage"),
        Union(import_run_id=run.id, partner_one_id=unrelated.id, partner_two_id=unrelated_partner.id, union_type="marriage"),
    ))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=all&depth=1")

    assert response.status_code == 200
    body = response.json()
    assert {person["id"] for person in body["people"]} == {
        str(ancestor.id), str(root.id), str(sibling.id), str(partner.id), str(archived_parent.id),
    }
    assert [person["id"] for person in body["people"]] == sorted(person["id"] for person in body["people"])
    hidden = next(person for person in body["people"] if person["id"] == str(archived_parent.id))
    assert hidden["is_hidden"] is True
    assert hidden["display_name"] is None
    assert hidden["birth_label"] is None
    assert hidden["death_label"] is None
    assert {(link["parent_id"], link["child_id"]) for link in body["parent_links"]} == {
        (str(ancestor.id), str(root.id)),
        (str(ancestor.id), str(sibling.id)),
        (str(archived_parent.id), str(partner.id)),
    }
    assert {(union["partner_one_id"], union["partner_two_id"]) for union in body["unions"]} == {
        (str(sibling.id), str(partner.id)),
    }


def test_descendant_tree_respects_depth(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="0" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    root = create_person(database_session, run, "Анна")
    child = create_person(database_session, run, "Борис")
    grandchild = create_person(database_session, run, "Вера")
    database_session.add_all((ParentChild(parent_id=root.id, child_id=child.id), ParentChild(parent_id=child.id, child_id=grandchild.id)))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=descendants&depth=1")

    assert response.status_code == 200
    assert {person["display_name"] for person in response.json()["people"]} == {"Анна", "Борис"}
    assert response.json()["links"] == [{"parent_id": str(root.id), "child_id": str(child.id)}]


def test_tree_normalizes_unknown_name_fragments_for_public_cards(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="n" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    root = create_person(database_session, run, "Евдокия ??? ???")
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=mixed&depth=1")

    assert response.status_code == 200
    assert response.json()["people"][0]["display_name"] == "Евдокия"


def test_descendant_tree_returns_union_and_typed_parent_link(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="2" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    root = create_person(database_session, run, "Анна")
    partner = create_person(database_session, run, "Пётр")
    child = create_person(database_session, run, "Мария")
    union = Union(import_run_id=run.id, partner_one_id=root.id, partner_two_id=partner.id, union_type="marriage")
    database_session.add(union)
    database_session.flush()
    database_session.add(ParentChild(parent_id=root.id, child_id=child.id, relationship_type="biological", union_id=union.id))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=descendants&depth=1")

    assert response.status_code == 200
    assert response.json()["unions"] == [
        {
            "id": str(union.id),
            "partner_one_id": str(root.id),
            "partner_two_id": str(partner.id),
            "union_type": "marriage",
        }
    ]
    assert response.json()["parent_links"] == [
        {
            "parent_id": str(root.id),
            "child_id": str(child.id),
            "relationship_type": "biological",
            "union_id": str(union.id),
        }
    ]


def test_ancestor_and_mixed_tree_include_parents(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="1" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    root = create_person(database_session, run, "Борис")
    child = create_person(database_session, run, "Вера")
    database_session.add_all((ParentChild(parent_id=parent.id, child_id=root.id), ParentChild(parent_id=root.id, child_id=child.id)))
    database_session.commit()

    ancestors = client.get(f"/api/v1/tree/{root.id}?mode=ancestors&depth=1")
    mixed = client.get(f"/api/v1/tree/{root.id}?mode=mixed&depth=1")

    assert {person["display_name"] for person in ancestors.json()["people"]} == {"Анна", "Борис"}
    assert {person["display_name"] for person in mixed.json()["people"]} == {"Анна", "Борис", "Вера"}
    assert {(link["parent_id"], link["child_id"]) for link in mixed.json()["links"]} == {
        (str(parent.id), str(root.id)),
        (str(root.id), str(child.id)),
    }


def test_mixed_tree_excludes_siblings_and_their_descendants(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="a" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    root = create_person(database_session, run, "Борис")
    sibling = create_person(database_session, run, "Вера")
    nephew = create_person(database_session, run, "Глеб")
    child = create_person(database_session, run, "Дина")
    database_session.add_all((
        ParentChild(parent_id=parent.id, child_id=root.id),
        ParentChild(parent_id=parent.id, child_id=sibling.id),
        ParentChild(parent_id=sibling.id, child_id=nephew.id),
        ParentChild(parent_id=root.id, child_id=child.id),
    ))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=mixed&depth=2")

    assert {person["id"] for person in response.json()["people"]} == {str(parent.id), str(root.id), str(child.id)}


def test_tree_keeps_an_archived_parent_as_a_hidden_placeholder(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="3" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    archived_parent = create_person(database_session, run, "Скрытая Анна")
    archived_parent.is_archived = True
    child = create_person(database_session, run, "Борис")
    database_session.add(ParentChild(parent_id=archived_parent.id, child_id=child.id, relationship_type="biological"))
    database_session.commit()

    response = client.get(f"/api/v1/tree/{child.id}?mode=ancestors&depth=1")

    assert response.status_code == 200
    node = next(person for person in response.json()["people"] if person["id"] == str(archived_parent.id))
    assert node["is_hidden"] is True
    assert node["display_name"] is None
    assert response.json()["parent_links"] == [
        {
            "parent_id": str(archived_parent.id),
            "child_id": str(child.id),
            "union_id": None,
            "relationship_type": "biological",
        }
    ]


def test_tree_keeps_children_under_their_actual_union(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="4" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    first_partner = create_person(database_session, run, "Пётр")
    second_partner = create_person(database_session, run, "Сергей")
    first_child = create_person(database_session, run, "Мария")
    second_child = create_person(database_session, run, "Вера")
    first_union = Union(import_run_id=run.id, partner_one_id=parent.id, partner_two_id=first_partner.id, union_type="marriage")
    second_union = Union(import_run_id=run.id, partner_one_id=parent.id, partner_two_id=second_partner.id, union_type="marriage")
    database_session.add_all(
        (
            first_union,
            second_union,
            ParentChild(parent_id=parent.id, child_id=first_child.id, relationship_type="biological"),
            ParentChild(parent_id=parent.id, child_id=second_child.id, relationship_type="biological"),
        )
    )
    database_session.commit()

    response = client.get(f"/api/v1/tree/{parent.id}?mode=descendants&depth=1")

    assert response.status_code == 200
    assert {item["id"] for item in response.json()["unions"]} == {str(first_union.id), str(second_union.id)}
    assert {(item["parent_id"], item["child_id"]) for item in response.json()["parent_links"]} == {
        (str(parent.id), str(first_child.id)),
        (str(parent.id), str(second_child.id)),
    }


def test_tree_deduplicates_cycle_without_infinite_traversal(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="5" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    first = create_person(database_session, run, "Анна")
    second = create_person(database_session, run, "Борис")
    database_session.add_all(
        (
            ParentChild(parent_id=first.id, child_id=second.id, relationship_type="biological"),
            ParentChild(parent_id=second.id, child_id=first.id, relationship_type="biological"),
        )
    )
    database_session.commit()

    response = client.get(f"/api/v1/tree/{first.id}?mode=mixed&depth=5")

    assert response.status_code == 200
    assert {person["id"] for person in response.json()["people"]} == {str(first.id), str(second.id)}
    assert len(response.json()["people"]) == 2


def test_close_relatives_include_parent_sibling_partner_and_child(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="6" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    root = create_person(database_session, run, "Борис")
    sibling = create_person(database_session, run, "Вера")
    partner = create_person(database_session, run, "Глеб")
    child = create_person(database_session, run, "Дина")
    database_session.add_all(
        (
            ParentChild(parent_id=parent.id, child_id=root.id, relationship_type="biological"),
            ParentChild(parent_id=parent.id, child_id=sibling.id, relationship_type="biological"),
            ParentChild(parent_id=root.id, child_id=child.id, relationship_type="biological"),
            Union(import_run_id=run.id, partner_one_id=root.id, partner_two_id=partner.id, union_type="marriage"),
        )
    )
    database_session.commit()

    response = client.get(f"/api/v1/tree/{root.id}?mode=close&depth=1")

    assert response.status_code == 200
    assert {person["id"] for person in response.json()["people"]} == {
        str(parent.id),
        str(root.id),
        str(sibling.id),
        str(partner.id),
        str(child.id),
    }


def test_path_mode_returns_shortest_chain_and_common_ancestor(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="7" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    parent = create_person(database_session, run, "Анна")
    first = create_person(database_session, run, "Борис")
    second = create_person(database_session, run, "Вера")
    database_session.add_all(
        (
            ParentChild(parent_id=parent.id, child_id=first.id, relationship_type="biological"),
            ParentChild(parent_id=parent.id, child_id=second.id, relationship_type="biological"),
        )
    )
    database_session.commit()

    response = client.get(f"/api/v1/tree/{first.id}?mode=path&to={second.id}")

    assert response.status_code == 200
    assert response.json()["relation_path"] == {
        "person_ids": [str(first.id), str(parent.id), str(second.id)],
        "labels": ["родитель", "ребёнок"],
        "common_ancestor_id": str(parent.id),
    }


def test_path_mode_returns_null_for_unrelated_people(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="8" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    first = create_person(database_session, run, "Анна")
    unrelated = create_person(database_session, run, "Борис")
    database_session.commit()

    response = client.get(f"/api/v1/tree/{first.id}?mode=path&to={unrelated.id}")

    assert response.status_code == 200
    assert response.json()["relation_path"] is None


def test_tree_rejects_depth_below_one(client, database_session):
    run = ImportRun(original_filename="family.ged", sha256="9" * 64, state="applied", normalized_payload={}, counts={})
    database_session.add(run)
    database_session.flush()
    person = create_person(database_session, run, "Анна")
    database_session.commit()

    response = client.get(f"/api/v1/tree/{person.id}?mode=close&depth=0")

    assert response.status_code == 422
