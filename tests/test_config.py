"""Тести ЛР3: конфігурації середовищ і безпечна обробка помилок."""

import logging

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import app

GOOD_KEY = "x" * 64
PROD_DB = "postgresql+psycopg://ehealth_prod:pw@localhost:5434/ehealth_production"


@pytest.fixture
def clean_env(monkeypatch):
    """Прибираємо змінні оточення, щоб перевіряти лише те, що передали явно."""
    for name in ("DATABASE_URL", "SECRET_KEY", "DEBUG", "APP_ENV", "DOCS_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def make(**kwargs) -> Settings:
    # _env_file=None: не читати жодних .env-файлів, лише передані значення
    return Settings(_env_file=None, **kwargs)


# ---------- Немає hardcoded секретів ----------


def test_database_url_and_secret_key_are_required(clean_env):
    with pytest.raises(ValidationError) as err:
        make()
    missing = {e["loc"][0] for e in err.value.errors()}
    assert {"database_url", "secret_key"} <= missing


def test_short_secret_key_is_rejected(clean_env):
    with pytest.raises(ValidationError):
        make(database_url=PROD_DB, secret_key="short")


def test_settings_are_read_from_environment(clean_env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PROD_DB)
    monkeypatch.setenv("SECRET_KEY", GOOD_KEY)
    settings = make()
    assert settings.database_url == PROD_DB


def test_settings_are_read_from_env_file(clean_env, tmp_path):
    env_file = tmp_path / ".env.sandbox"
    env_file.write_text(
        "DATABASE_URL=postgresql+psycopg://u:p@localhost:5433/ehealth_sandbox\n"
        f"SECRET_KEY={GOOD_KEY}\nDEBUG=true\n"
    )
    settings = Settings(_env_file=env_file)
    assert settings.debug is True
    assert settings.database_url.endswith("/ehealth_sandbox")


# ---------- Захист production ----------


def test_valid_production_config(clean_env):
    settings = make(app_env="production", database_url=PROD_DB, secret_key=GOOD_KEY)
    assert settings.is_production
    assert settings.debug is False


def test_production_refuses_debug(clean_env):
    with pytest.raises(ValidationError, match="DEBUG must be false"):
        make(
            app_env="production", database_url=PROD_DB, secret_key=GOOD_KEY, debug=True
        )


def test_production_refuses_sandbox_database(clean_env):
    sandbox_db = "postgresql+psycopg://u:p@localhost:5433/ehealth_sandbox"
    with pytest.raises(ValidationError, match="sandbox database"):
        make(app_env="production", database_url=sandbox_db, secret_key=GOOD_KEY)


def test_production_refuses_placeholder_secret(clean_env):
    with pytest.raises(ValidationError, match="placeholder"):
        make(
            app_env="production",
            database_url=PROD_DB,
            secret_key="CHANGE-ME-generate-a-real-secret-key-0000000000",
        )


def test_unknown_environment_is_rejected(clean_env):
    with pytest.raises(ValidationError):
        make(app_env="staging", database_url=PROD_DB, secret_key=GOOD_KEY)


def test_env_examples_have_no_real_production_secrets():
    """Шаблон production містить лише заглушки, а не справжні паролі."""
    text = open(".env.production.example", encoding="utf-8").read()
    assert "DEBUG=false" in text
    for line in text.splitlines():
        if line.startswith(("SECRET_KEY=", "ADMIN_PASSWORD=")):
            assert "CHANGE-ME" in line


def test_tests_run_in_sandbox(client):
    assert client.get("/health").json()["environment"] == "sandbox"


# ---------- Помилки: користувач не бачить стектрейс ----------

boom = APIRouter()


@boom.get("/__test_boom__")
def _explode():
    raise RuntimeError("secret internal detail: password=hunter2")


app.include_router(boom)


@pytest.fixture
def raw_client():
    # raise_server_exceptions=False: поводимось як справжній сервер
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_500_api_response_has_no_stacktrace(raw_client, caplog):
    with caplog.at_level(logging.ERROR, logger="ehealth"):
        response = raw_client.get("/__test_boom__")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert len(body["error_id"]) == 8
    assert "Traceback" not in response.text
    assert "hunter2" not in response.text
    # ...а розробник бачить повний стектрейс у лозі з тим самим кодом
    assert body["error_id"] in caplog.text
    assert "RuntimeError" in caplog.text


def test_500_html_page_for_browser(raw_client):
    response = raw_client.get("/__test_boom__", headers={"Accept": "text/html"})
    assert response.status_code == 500
    assert "Щось пішло не так" in response.text
    assert "Traceback" not in response.text
    assert "hunter2" not in response.text


def test_404_html_page_for_browser(client):
    response = client.get("/no-such-page", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "Сторінку не знайдено" in response.text


def test_404_json_for_api(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_401_still_has_auth_header(client):
    """Наш обробник не ламає стандартні помилки API."""
    response = client.get("/users/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
