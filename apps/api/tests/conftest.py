import asyncio

import pytest
from argon2 import PasswordHasher
from httpx import ASGITransport, AsyncClient
from testcontainers.community.postgres import PostgresContainer

from app.core.config import Settings


@pytest.fixture(scope="session")
def postgres_url():
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def settings(monkeypatch, postgres_url):
    monkeypatch.setenv(
        "CATS_HOUSE_DATABASE_URL",
        postgres_url,
    )
    monkeypatch.setenv("CATS_HOUSE_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("CATS_HOUSE_S3_BUCKET", "cats-house-media")
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "owner@example.test")
    monkeypatch.setenv(
        "CATS_HOUSE_OWNER_PASSWORD_HASH",
        PasswordHasher().hash("test-owner-password"),
    )
    monkeypatch.setenv(
        "CATS_HOUSE_SESSION_SECRET",
        "test-session-secret-with-at-least-thirty-two-characters",
    )
    monkeypatch.setenv("CATS_HOUSE_ENVIRONMENT", "production")
    return Settings()


@pytest.fixture
def client(settings):
    from app.main import create_app

    app = create_app(settings)

    from sqlalchemy import create_engine
    from app.models.genealogy import Base

    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)

    class ApiClient:
        def __init__(self):
            self.cookies = None
            self.app = app

        def request(self, method, path, json=None, files=None):
            async def send_request():
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport,
                    base_url="https://testserver",
                    cookies=self.cookies,
                ) as http_client:
                    response = await http_client.request(method, path, json=json, files=files)
                    self.cookies = http_client.cookies
                    return response

            return asyncio.run(send_request())

        def get(self, path):
            return self.request("GET", path)

        def post(self, path, json=None, files=None):
            return self.request("POST", path, json=json, files=files)

        def patch(self, path, json=None):
            return self.request("PATCH", path, json=json)

    yield ApiClient()
    Base.metadata.drop_all(engine)
