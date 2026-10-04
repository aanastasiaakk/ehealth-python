from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db() -> None:
    with TestClient(app) as client:
        response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
