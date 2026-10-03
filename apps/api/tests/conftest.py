import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv(
        "CATS_HOUSE_DATABASE_URL",
        "postgresql+psycopg://cats_house:password@localhost:5432/cats_house",
    )
    monkeypatch.setenv("CATS_HOUSE_S3_ENDPOINT", "http://localhost:9000")
    monkeypatch.setenv("CATS_HOUSE_S3_BUCKET", "cats-house-media")
    monkeypatch.setenv("CATS_HOUSE_OWNER_EMAIL", "owner@example.test")
    return Settings()


@pytest.fixture
def client(settings):
    from app.main import create_app

    app = create_app(settings)

    class ApiClient:
        def get(self, path):
            async def send_request():
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as http_client:
                    return await http_client.get(path)

            return asyncio.run(send_request())

    return ApiClient()
