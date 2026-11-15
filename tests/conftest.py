"""Спільні налаштування тестів (pytest автоматично підхоплює цей файл).

Тести працюють з ОКРЕМОЮ базою даних `<назва>_test`, щоб не зіпсувати
дані, з якими ти працюєш локально. База створюється автоматично
(потрібен запущений PostgreSQL: `docker compose up -d`).
Перед кожним тестом усі таблиці очищаються, тому тести незалежні один від одного.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings

# ---------- 1. Перемикаємо застосунок на тестову базу ----------
# Робимо це ДО імпорту app.database, бо там одразу створюється engine.
_base = make_url(Settings().database_url)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _base.set(
    database=f"{_base.database}_test"
).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
get_settings.cache_clear()


def _create_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": url.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


_create_test_database()

# ---------- 2. Пришвидшуємо bcrypt ----------
# У реальному застосунку хешування навмисно повільне (≈0.2 с), щоб
# ускладнити підбір паролів. У тестах це зайве: зменшуємо складність.
_original_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _original_gensalt(4, prefix)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Doctor, Role, Slot, Specialty  # noqa: E402
from app.security import create_access_token  # noqa: E402
from app.services import users as user_service  # noqa: E402

DEFAULT_PASSWORD = "password123"


# ---------- 3. Фікстури ----------


@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Один раз на весь запуск: створюємо таблиці з нуля."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    """Перед кожним тестом: порожні таблиці, лічильники id з 1."""
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(db):
    """Фабрика користувачів: make_user(Role.ADMIN), make_user(email="a@b.c")."""
    counter = {"n": 0}

    def factory(role: Role = Role.PATIENT, email: str | None = None, **kwargs):
        counter["n"] += 1
        email = email or f"{role.value}{counter['n']}@test.ua"
        return user_service.create_user(
            db,
            email=email,
            password=kwargs.pop("password", DEFAULT_PASSWORD),
            full_name=kwargs.pop("full_name", f"Test {role.value} {counter['n']}"),
            role=role,
            **kwargs,
        )

    return factory


@pytest.fixture
def make_doctor(db, make_user):
    """Фабрика лікарів: створює спеціальність, акаунт з роллю DOCTOR і профіль."""

    def factory(specialty_name: str = "Кардіолог"):
        specialty = db.query(Specialty).filter_by(name=specialty_name).first()
        if specialty is None:
            specialty = Specialty(name=specialty_name)
            db.add(specialty)
            db.commit()
        account = make_user(Role.DOCTOR)
        doctor = Doctor(
            full_name=account.full_name, specialty_id=specialty.id, user_id=account.id
        )
        db.add(doctor)
        db.commit()
        return doctor

    return factory


@pytest.fixture
def make_slot(db):
    """Фабрика слотів. hours=24 — слот через добу; hours=-1 — у минулому."""

    def factory(doctor: Doctor, hours: float = 24):
        slot = Slot(
            doctor_id=doctor.id,
            starts_at=datetime.now(timezone.utc) + timedelta(hours=hours),
            is_available=True,
        )
        db.add(slot)
        db.commit()
        return slot

    return factory


def auth(user) -> dict:
    """Заголовок авторизації для користувача: {"Authorization": "Bearer ..."}."""
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}
