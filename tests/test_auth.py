"""ІНТЕГРАЦІЙНІ тести: анонімний доступ, реєстрація, вхід.

Інтеграційні — бо перевіряють усю систему разом:
HTTP-запит → FastAPI → залежності безпеки → PostgreSQL → відповідь.
"""

import pytest

from app.models import Role
from tests.conftest import DEFAULT_PASSWORD, auth

# ---------- Сценарій 1: Анонімний доступ → 401 / 302 ----------

PROTECTED_API = [
    ("get", "/users/me"),
    ("patch", "/users/1"),
    ("get", "/appointments/me"),
    ("post", "/appointments"),
    ("delete", "/appointments/1"),
    ("get", "/doctor/schedule"),
    ("get", "/admin/stats"),
    ("get", "/admin/users"),
]


@pytest.mark.parametrize("method,url", PROTECTED_API)
def test_anonymous_api_request_gets_401(client, method, url):
    response = client.request(method, url, json={})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("url", ["/home", "/patient", "/doctor", "/admin"])
def test_anonymous_page_request_redirects_to_login(client, url):
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_invalid_token_gets_401(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer abc.def"})
    assert response.status_code == 401


def test_public_catalog_is_available_without_login(client):
    assert client.get("/specialties").status_code == 200
    assert client.get("/doctors").status_code == 200


# ---------- Реєстрація ----------


def test_register_creates_patient(client):
    response = client.post(
        "/auth/register",
        json={
            "email": "Olena@Test.ua",
            "password": "strongpass1",
            "full_name": "Олена Тестова",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "patient"
    assert body["email"] == "olena@test.ua"
    assert "password" not in body and "password_hash" not in body


def test_register_cannot_choose_admin_role(client):
    """Спроба «зареєструватися адміном» через зайве поле в запиті."""
    response = client.post(
        "/auth/register",
        json={
            "email": "hacker@test.ua",
            "password": "strongpass1",
            "full_name": "Hacker",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == "patient"


def test_register_duplicate_email_gets_409(client, make_user):
    make_user(email="taken@test.ua")
    response = client.post(
        "/auth/register",
        json={"email": "TAKEN@test.ua", "password": "strongpass1", "full_name": "X Y"},
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "strongpass1", "full_name": "X Y"},
        {"email": "a@test.ua", "password": "short", "full_name": "X Y"},
    ],
)
def test_register_validation_errors_get_422(client, payload):
    assert client.post("/auth/register", json=payload).status_code == 422


# ---------- Сценарій 2: Успішна автентифікація та помилки входу ----------


@pytest.mark.parametrize("role", [Role.PATIENT, Role.DOCTOR, Role.ADMIN])
def test_login_success_for_every_role(client, make_user, role):
    user = make_user(role)
    response = client.post(
        "/auth/token", data={"username": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == role.value


def test_login_wrong_password_gets_401(client, make_user):
    user = make_user()
    response = client.post(
        "/auth/token", data={"username": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    assert "access_token" not in response.json()


def test_login_unknown_email_gets_401(client):
    response = client.post(
        "/auth/token", data={"username": "ghost@test.ua", "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 401


def test_blocked_user_cannot_login(client, db, make_user):
    user = make_user()
    user.is_active = False
    db.commit()
    response = client.post(
        "/auth/token", data={"username": user.email, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 401


def test_blocked_user_token_stops_working(client, db, make_user):
    """Токен виданий раніше, але користувача заблокували → доступ одразу закрито."""
    user = make_user()
    headers = auth(user)
    assert client.get("/users/me", headers=headers).status_code == 200
    user.is_active = False
    db.commit()
    assert client.get("/users/me", headers=headers).status_code == 401


# ---------- Вхід через HTML-форму (cookie) ----------


def test_web_login_sets_cookie_and_opens_home_page(client, make_user):
    user = make_user(Role.PATIENT)
    response = client.post(
        "/login",
        data={"email": user.email, "password": DEFAULT_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "access_token" in response.cookies
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie

    home = client.get("/home", follow_redirects=False)
    assert home.status_code == 302
    assert home.headers["location"] == "/patient"
    assert client.get("/patient").status_code == 200


def test_web_login_wrong_password(client, make_user):
    user = make_user()
    response = client.post(
        "/login", data={"email": user.email, "password": "nope-nope"}
    )
    assert response.status_code == 401
    assert "Неправильний email або пароль" in response.text


def test_web_register_and_logout(client):
    response = client.post(
        "/register",
        data={"email": "new@test.ua", "password": "strongpass1", "full_name": "Нова"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/patient").status_code == 200

    client.post("/logout")
    client.cookies.clear()  # TestClient не завжди видаляє cookie сам
    assert client.get("/patient", follow_redirects=False).status_code == 302


@pytest.mark.parametrize(
    "role,page",
    [(Role.PATIENT, "/patient"), (Role.DOCTOR, "/doctor"), (Role.ADMIN, "/admin")],
)
def test_each_role_is_sent_to_its_home_page(client, make_user, role, page):
    user = make_user(role)
    client.post("/login", data={"email": user.email, "password": DEFAULT_PASSWORD})
    response = client.get("/home", follow_redirects=False)
    assert response.headers["location"] == page
