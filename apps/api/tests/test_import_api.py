from pathlib import Path


def gedcom_upload(name="complex-family.ged"):
    content = (Path(__file__).parent / "fixtures" / name).read_bytes()
    return {"file": (name, content, "text/plain")}


def login(client):
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})


def test_anonymous_client_cannot_preview_or_apply_import(client):
    assert client.post("/api/v1/admin/imports/preview", files=gedcom_upload()).status_code == 401
    assert client.post("/api/v1/admin/imports/not-an-id/apply").status_code == 401


def test_owner_can_preview_read_report_and_apply_once(client):
    login(client)
    preview = client.post("/api/v1/admin/imports/preview", files=gedcom_upload())

    assert preview.status_code == 201
    assert preview.json()["state"] == "previewed"
    report = client.get(f"/api/v1/admin/imports/{preview.json()['id']}")
    assert report.status_code == 200
    assert client.post(f"/api/v1/admin/imports/{preview.json()['id']}/apply").status_code == 200
    assert client.post(f"/api/v1/admin/imports/{preview.json()['id']}/apply").status_code == 409
