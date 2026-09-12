def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_prefix_is_versioned(client):
    """docs/API-SPEC.md pins the base at /api/v1."""
    assert client.get("/api/v1/ping").status_code == 200
