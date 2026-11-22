from fastapi.testclient import TestClient

from app.instance import INSTANCE_ID
from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "sandbox",
        "instance": INSTANCE_ID,
    }


def test_every_response_says_which_instance_answered() -> None:
    # ЛР6: за заголовком видно, яка репліка обробила запит
    with TestClient(app) as client:
        for path in ("/health", "/specialties", "/no-such-page"):
            assert client.get(path).headers["x-instance"] == INSTANCE_ID


def test_health_db() -> None:
    with TestClient(app) as client:
        response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["database"] == "connected"
