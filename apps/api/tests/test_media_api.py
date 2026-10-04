from dataclasses import dataclass, field

from app.models.genealogy import Media


@dataclass
class FakeMediaStorage:
    objects: dict[str, tuple[bytes, str]] = field(default_factory=dict)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.objects[key] = (content, content_type)


def test_anonymous_client_cannot_upload_media(client):
    response = client.post("/api/v1/admin/media", files={"file": ("cat.jpg", b"image-data", "image/jpeg")})

    assert response.status_code == 401


def test_owner_uploads_published_media_to_storage(client):
    client.app.state.media_storage = FakeMediaStorage()
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    response = client.post("/api/v1/admin/media", files={"file": ("cat.jpg", b"image-data", "image/jpeg")})

    assert response.status_code == 201
    with client.app.state.session_factory() as session:
        media = session.get(Media, response.json()["id"])
        assert media.original_filename == "cat.jpg"
        assert media.is_published is False
        assert client.app.state.media_storage.objects[media.storage_key] == (b"image-data", "image/jpeg")
