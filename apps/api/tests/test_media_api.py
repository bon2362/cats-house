import io
from uuid import uuid4

from PIL import Image

from app.models.genealogy import Person

PASSWORD = {"password": "test-owner-password"}


def image_bytes(kind="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", (800, 600), "blue").save(buffer, kind)
    return buffer.getvalue()


def make_person(client, name="Анна", archived=False):
    with client.app.state.session_factory() as session:
        person = Person(display_name=name, is_archived=archived)
        session.add(person)
        session.commit()
        return str(person.id)


def upload(client, person_id, name="anna.jpg", content=None):
    return client.post(f"/api/v1/admin/people/{person_id}/media", files={"file": (name, image_bytes() if content is None else content, "image/jpeg")})


def as_guest(client):
    client.cookies = None


def test_guests_cannot_upload_or_change_media(client):
    person_id = make_person(client)
    media_id = str(uuid4())

    assert upload(client, person_id).status_code == 401
    assert client.get(f"/api/v1/admin/people/{person_id}/media").status_code == 401
    assert client.patch(f"/api/v1/admin/media/{media_id}", json={"caption": "x"}).status_code == 401
    assert client.request("DELETE", f"/api/v1/admin/media/{media_id}").status_code == 401
    assert client.request("PUT", f"/api/v1/admin/people/{person_id}/portrait", json={"media_id": None}).status_code == 401
    assert client.patch(f"/api/v1/admin/people/{person_id}/biography", json={"biography": "x"}).status_code == 401


def test_owner_uploads_a_photo_and_guests_see_it_and_its_files(client):
    person_id = make_person(client)
    client.post("/api/v1/auth/login", json=PASSWORD)

    uploaded = upload(client, person_id, "Анна у дома.jpg")
    as_guest(client)

    assert uploaded.status_code == 201
    view = uploaded.json()
    assert (view["is_published"], view["is_portrait"], view["media_type"]) == (True, False, "image/jpeg")
    page = client.get(f"/api/v1/people/{person_id}").json()
    # The public page omits empty fields (response_model_exclude_none), as for the rest of the person.
    assert page["media"] == [{key: view[key] for key in ("id", "original_filename", "media_type", "file_url", "preview_url")}]
    file = client.get(view["file_url"])
    assert file.status_code == 200 and file.content == image_bytes()
    assert file.headers["content-type"] == "image/jpeg" and file.headers["x-content-type-options"] == "nosniff"
    assert file.headers["content-disposition"] == "inline; filename*=UTF-8''%D0%90%D0%BD%D0%BD%D0%B0%20%D1%83%20%D0%B4%D0%BE%D0%BC%D0%B0.jpg"
    preview = client.get(view["preview_url"])
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"


def test_hidden_deleted_and_hidden_person_files_are_404_for_guests(client):
    person_id, hidden_person = make_person(client), make_person(client, "Скрытый", archived=True)
    client.post("/api/v1/auth/login", json=PASSWORD)
    hidden = upload(client, person_id).json()
    deleted = upload(client, person_id).json()
    of_hidden_person = upload(client, hidden_person).json()
    client.patch(f"/api/v1/admin/media/{hidden['id']}", json={"is_published": False})
    client.request("DELETE", f"/api/v1/admin/media/{deleted['id']}")

    assert client.get(hidden["file_url"]).status_code == 200
    assert client.get(deleted["file_url"]).status_code == 404
    as_guest(client)
    for url in (hidden["file_url"], hidden["preview_url"], deleted["file_url"], of_hidden_person["file_url"]):
        response = client.get(url)
        assert (response.status_code, response.json()) == (404, {"detail": "Файл не найден."})
    assert client.get(f"/api/v1/people/{person_id}").json()["media"] == []


def test_pdf_has_no_preview_and_upload_refusals_are_russian(client):
    person_id = make_person(client)
    client.post("/api/v1/auth/login", json=PASSWORD)

    pdf = upload(client, person_id, "doc.pdf", b"%PDF-1.4 test").json()
    wrong = upload(client, person_id, "virus.jpg", b"MZ\x90\x00")
    big = upload(client, person_id, "big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024))
    missing = upload(client, str(uuid4()))

    assert pdf["preview_url"] is None and client.get(f"/api/v1/media/{pdf['id']}/preview").status_code == 404
    assert (wrong.status_code, wrong.json()) == (422, {"detail": "Разрешены JPEG, PNG и PDF."})
    assert (big.status_code, big.json()) == (422, {"detail": "Файл не должен превышать 10 МБ."})
    assert (missing.status_code, missing.json()) == (404, {"detail": "Человек не найден."})


def test_portrait_appears_on_the_person_page_and_in_the_tree(client):
    person_id = make_person(client)
    client.post("/api/v1/auth/login", json=PASSWORD)
    photo = upload(client, person_id).json()
    pdf = upload(client, person_id, "doc.pdf", b"%PDF-1.4").json()

    before = client.get(f"/api/v1/tree/{person_id}?mode=close").json()["people"][0]["photo_url"]
    chosen = client.request("PUT", f"/api/v1/admin/people/{person_id}/portrait", json={"media_id": photo["id"]})
    refused = client.request("PUT", f"/api/v1/admin/people/{person_id}/portrait", json={"media_id": pdf["id"]})
    as_guest(client)

    assert before is None
    assert chosen.json() == {"portrait_media_id": photo["id"]}
    assert (refused.status_code, refused.json()) == (422, {"detail": "Портретом может быть только фото."})
    assert client.get(f"/api/v1/people/{person_id}").json()["portrait"] == {"id": photo["id"], "preview_url": photo["preview_url"], "file_url": photo["file_url"]}
    assert client.get(f"/api/v1/tree/{person_id}?mode=close").json()["people"][0]["photo_url"] == photo["preview_url"]


def test_owner_edits_caption_and_biography_and_sees_hidden_files(client):
    person_id = make_person(client)
    client.post("/api/v1/auth/login", json=PASSWORD)
    photo = upload(client, person_id).json()

    changed = client.patch(f"/api/v1/admin/media/{photo['id']}", json={"caption": "Свадьба", "date_label": "1950", "is_published": False})
    biography = client.patch(f"/api/v1/admin/people/{person_id}/biography", json={"biography": "Первый.\n\nВторой."})
    too_long = client.patch(f"/api/v1/admin/people/{person_id}/biography", json={"biography": "я" * 20001})

    assert (changed.json()["caption"], changed.json()["date_label"], changed.json()["is_published"]) == ("Свадьба", "1950", False)
    assert biography.json() == {"biography": "Первый.\n\nВторой."}
    assert too_long.status_code == 422
    assert [item["is_published"] for item in client.get(f"/api/v1/admin/people/{person_id}/media").json()] == [False]
    assert client.get(f"/api/v1/admin/people/{person_id}").json()["biography"] == "Первый.\n\nВторой."
    as_guest(client)
    assert client.get(f"/api/v1/people/{person_id}").json()["biography"] == "Первый.\n\nВторой."
