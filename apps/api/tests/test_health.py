def test_health_returns_product_identity(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "Cat's House"}


def test_health_never_returns_database_url(client):
    response = client.get("/api/v1/health")

    assert "database" not in response.text.lower()
    assert "postgresql" not in response.text.lower()
