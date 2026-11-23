"""ЛР7: оптимізації — кеш у Redis, обмеження одночасних запитів, пул БД."""

import asyncio

import httpx
import pytest
from redis import RedisError

from app import cache
from app.config import get_settings
from app.limiter import ConcurrencyLimitMiddleware
from tests.conftest import auth


class FakeRedis:
    """Мінімальна заміна Redis у пам'яті (справжній сервер тестам не потрібен)."""

    def __init__(self):
        self.data: dict[str, bytes] = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    def scan_iter(self, pattern):
        prefix = pattern.rstrip("*")
        return [k for k in list(self.data) if k.startswith(prefix)]


class BrokenRedis(FakeRedis):
    def get(self, key):
        raise RedisError("connection refused")


@pytest.fixture
def fake_redis(monkeypatch):
    monkeypatch.setattr(get_settings(), "redis_url", "redis://fake")
    fake = FakeRedis()
    cache.set_client(fake)
    yield fake
    cache.set_client(None)


# ---------- Кеш ----------


def test_slots_second_request_comes_from_cache(
    client, fake_redis, make_doctor, make_slot
):
    doctor = make_doctor()
    make_slot(doctor)
    first = client.get(f"/doctors/{doctor.id}/slots")
    second = client.get(f"/doctors/{doctor.id}/slots")
    assert first.headers["x-cache"] == "MISS"
    assert second.headers["x-cache"] == "HIT"
    assert first.json() == second.json() and len(first.json()) == 1
    assert cache.slots_key(doctor.id) in fake_redis.data


def test_booking_removes_stale_slots_from_cache(
    client, fake_redis, make_doctor, make_slot, make_user
):
    doctor = make_doctor()
    slot = make_slot(doctor)
    patient = make_user()
    assert len(client.get(f"/doctors/{doctor.id}/slots").json()) == 1  # у кеші

    booked = client.post(
        "/appointments", json={"slot_id": slot.id}, headers=auth(patient)
    )
    assert booked.status_code == 201

    after = client.get(f"/doctors/{doctor.id}/slots")
    assert after.headers["x-cache"] == "MISS"  # кеш скинуто одразу
    assert after.json() == []


def test_cancel_returns_slot_to_cache(
    client, fake_redis, make_doctor, make_slot, make_user
):
    doctor = make_doctor()
    slot = make_slot(doctor)
    patient = make_user()
    appt = client.post(
        "/appointments", json={"slot_id": slot.id}, headers=auth(patient)
    ).json()
    assert client.get(f"/doctors/{doctor.id}/slots").json() == []
    client.delete(f"/appointments/{appt['id']}", headers=auth(patient))
    assert len(client.get(f"/doctors/{doctor.id}/slots").json()) == 1


def test_catalog_is_cached_and_reset_by_admin(client, fake_redis, make_user):
    from app.models import Role

    admin = make_user(Role.ADMIN)
    assert client.get("/specialties").json() == []
    assert client.get("/specialties").headers["x-cache"] == "HIT"
    client.post("/admin/specialties", json={"name": "Хірург"}, headers=auth(admin))
    fresh = client.get("/specialties")
    assert fresh.headers["x-cache"] == "MISS"
    assert [s["name"] for s in fresh.json()] == ["Хірург"]


def test_unknown_doctor_is_404_and_not_cached(client, fake_redis):
    assert client.get("/doctors/999/slots").status_code == 404
    assert cache.slots_key(999) not in fake_redis.data


def test_without_redis_everything_still_works(client, make_doctor, make_slot):
    doctor = make_doctor()
    make_slot(doctor)
    for _ in range(2):
        response = client.get(f"/doctors/{doctor.id}/slots")
        assert response.status_code == 200
        assert response.headers["x-cache"] == "MISS"


def test_broken_redis_falls_back_to_database(
    client, monkeypatch, make_doctor, make_slot
):
    monkeypatch.setattr(get_settings(), "redis_url", "redis://broken")
    cache.set_client(BrokenRedis())
    try:
        doctor = make_doctor()
        make_slot(doctor)
        response = client.get(f"/doctors/{doctor.id}/slots")
        assert response.status_code == 200 and len(response.json()) == 1
    finally:
        cache.set_client(None)


# ---------- Обмеження одночасних запитів ----------


async def _slow_app(scope, receive, send):
    await asyncio.sleep(0.3)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _limited_client(limit: int, queue_timeout: float) -> httpx.AsyncClient:
    app = ConcurrencyLimitMiddleware(
        _slow_app, limit=limit, queue_timeout=queue_timeout
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    )


def test_requests_over_the_limit_wait_in_queue():
    async def scenario():
        async with _limited_client(limit=1, queue_timeout=5) as client:
            return await asyncio.gather(client.get("/a"), client.get("/b"))

    assert [r.status_code for r in asyncio.run(scenario())] == [200, 200]


def test_too_long_in_queue_gets_fast_503():
    async def scenario():
        async with _limited_client(limit=1, queue_timeout=0.05) as client:
            return await asyncio.gather(client.get("/a"), client.get("/b"))

    codes = sorted(r.status_code for r in asyncio.run(scenario()))
    assert codes == [200, 503]


def test_health_is_never_queued():
    async def scenario():
        async with _limited_client(limit=1, queue_timeout=0.05) as client:
            return await asyncio.gather(client.get("/a"), client.get("/health"))

    assert [r.status_code for r in asyncio.run(scenario())] == [200, 200]


def test_db_pool_is_bigger_than_concurrent_requests():
    # Головна причина зависання в ЛР4: з'єднань було менше, ніж запитів у роботі
    settings = get_settings()
    pool = settings.db_pool_size + settings.db_max_overflow
    assert pool > settings.max_concurrent_requests
    assert settings.db_pool_timeout <= 10


# ---------- Індекси ----------


def test_migrations_add_partial_index_and_drop_redundant_one():
    from sqlalchemy import inspect, text

    from app.database import engine
    from app.migrations import apply_migrations

    with engine.begin() as conn:  # стара база з ЛР2–ЛР6
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_slots_doctor_id ON slots (doctor_id)")
        )
        conn.execute(text("DROP INDEX IF EXISTS ix_slots_free_by_doctor"))
    apply_migrations(engine)
    indexes = {ix["name"]: ix for ix in inspect(engine).get_indexes("slots")}
    assert "ix_slots_doctor_id" not in indexes
    assert indexes["ix_slots_free_by_doctor"]["column_names"] == [
        "doctor_id",
        "starts_at",
    ]
    assert (
        "is_available"
        in indexes["ix_slots_free_by_doctor"]["dialect_options"]["postgresql_where"]
    )
