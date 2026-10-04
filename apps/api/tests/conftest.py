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
def settings(monkeypatch):
    monkeypatch.setenv(
        "CATS_HOUSE_DATABASE_URL",
        "postgresql+psycopg://cats_house:password@localhost:5432/cats_house",
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

    class ApiClient:
        def __init__(self):
            self.cookies = None

        def request(self, method, path, json=None):
            async def send_request():
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport,
                    base_url="https://testserver",
                    cookies=self.cookies,
                ) as http_client:
                    response = await http_client.request(method, path, json=json)
                    self.cookies = http_client.cookies
                    return response

            return asyncio.run(send_request())

        def get(self, path):
            return self.request("GET", path)

        def post(self, path, json=None):
            return self.request("POST", path, json=json)

    return ApiClient()
