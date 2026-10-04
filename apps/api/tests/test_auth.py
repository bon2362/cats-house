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
