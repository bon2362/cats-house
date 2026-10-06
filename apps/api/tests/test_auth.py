from pydantic import SecretStr

from app.auth.service import totp_code, verify_totp


def test_totp_accepts_current_code_and_rejects_wrong_code():
    secret = "JBSWY3DPEHPK3PXP"

    assert verify_totp(totp_code(secret, timestamp=1_700_000_000), secret, timestamp=1_700_000_000)
    assert not verify_totp("000000", secret, timestamp=1_700_000_000)


def test_admin_route_rejects_anonymous_client(client):
    response = client.get("/api/v1/admin/session")

    assert response.status_code == 401


def test_public_health_does_not_set_owner_cookie(client):
    response = client.get("/api/v1/health")

    assert "set-cookie" not in response.headers


def test_owner_login_sets_secure_http_only_session_cookie(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"password": "test-owner-password"},
    )

    assert response.status_code == 204
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()


def test_owner_session_allows_admin_route_after_login(client):
    client.post(
        "/api/v1/auth/login",
        json={"password": "test-owner-password"},
    )

    response = client.get("/api/v1/admin/session")

    assert response.status_code == 200
    assert response.json() == {"email": "owner@example.test"}


def test_status_reports_guest_then_owner_without_personal_data(client):
    assert client.get("/api/v1/auth/status").json() == {"authenticated": False, "totp_required": False}

    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert client.get("/api/v1/auth/status").json() == {"authenticated": True, "totp_required": False}


def test_status_reports_that_a_one_time_code_is_required(monkeypatch, settings):
    from httpx import ASGITransport, AsyncClient
    import asyncio
    from app.main import create_app

    configured = settings.model_copy(update={"owner_totp_secret": SecretStr("JBSWY3DPEHPK3PXP")})

    async def status():
        async with AsyncClient(transport=ASGITransport(app=create_app(configured)), base_url="https://testserver") as http_client:
            return (await http_client.get("/api/v1/auth/status")).json()

    assert asyncio.run(status()) == {"authenticated": False, "totp_required": True}


def test_logout_ends_the_owner_session_and_works_without_one(client):
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get("/api/v1/admin/session").status_code == 401
    assert client.get("/api/v1/auth/status").json()["authenticated"] is False


def test_fifth_failed_sign_in_blocks_even_the_correct_password(client):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"password": "wrong-password"}).status_code == 401

    blocked = client.post("/api/v1/auth/login", json={"password": "test-owner-password"})

    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Слишком много попыток входа."}
    assert 1 <= int(blocked.headers["retry-after"]) <= 900


def test_successful_sign_in_resets_the_failure_count(client):
    for _ in range(4):
        client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert client.post("/api/v1/auth/login", json={"password": "test-owner-password"}).status_code == 204

    for _ in range(4):
        assert client.post("/api/v1/auth/login", json={"password": "wrong-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"password": "test-owner-password"}).status_code == 204


def test_simultaneous_wrong_passwords_cannot_exceed_the_limit(settings):
    import asyncio
    from httpx import ASGITransport, AsyncClient
    from app.main import create_app

    app = create_app(settings)

    async def burst():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://testserver") as http_client:
            responses = await asyncio.gather(*(http_client.post("/api/v1/auth/login", json={"password": f"wrong-{index}"}) for index in range(10)))
        return sorted(response.status_code for response in responses)

    assert asyncio.run(burst()) == [401] * 5 + [429] * 5
