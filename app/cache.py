"""Кеш у Redis (ЛР7, оптимізація №2).

У ЛР4 73 % усіх запитів — читання каталогу (спеціальності, лікарі,
вільні слоти). Ці дані однакові для всіх користувачів, тому готову
JSON-відповідь кладемо в Redis і наступні запити віддаємо звідти:
без бази, без ORM і без повторної серіалізації.

Час життя (TTL):
- каталог (спеціальності, лікарі) — CACHE_TTL_CATALOG, 300 с;
- вільні слоти лікаря — CACHE_TTL_SLOTS, 5 с. Крім того, після кожного
  запису, скасування чи створення слотів ключ лікаря видаляється
  одразу (інвалідація), тож застарілий список живе максимум 5 с, і то
  лише через плин часу. Подвійного запису це не дозволяє: сам запис
  завжди перевіряється в базі з блокуванням рядка (ЛР2).

Кеш «необов'язковий»: якщо REDIS_URL не задано або Redis недоступний,
застосунок просто читає з бази (повільніше, але працює).
"""

import logging
import time
from collections.abc import Callable

from fastapi import Response
from pydantic import TypeAdapter
from redis import Redis, RedisError

from app.config import get_settings

logger = logging.getLogger("ehealth.cache")

# Після помилки Redis пауза, щоб кожен запит не чекав тайм-ауту
RETRY_AFTER_ERROR = 5.0

_client: Redis | None = None
_disabled_until = 0.0


def get_client() -> Redis | None:
    global _client
    url = get_settings().redis_url
    if not url or time.monotonic() < _disabled_until:
        return None
    if _client is None:
        _client = Redis.from_url(url, socket_timeout=0.2, socket_connect_timeout=0.2)
    return _client


def set_client(client: Redis | None) -> None:
    """Підмінити клієнт (для тестів)."""
    global _client, _disabled_until
    _client, _disabled_until = client, 0.0


def _failed(exc: Exception) -> None:
    global _disabled_until
    _disabled_until = time.monotonic() + RETRY_AFTER_ERROR
    logger.warning(
        "Redis unavailable, cache bypassed for %ss: %s", RETRY_AFTER_ERROR, exc
    )


def get(key: str) -> bytes | None:
    client = get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except RedisError as exc:
        _failed(exc)
        return None


def put(key: str, value: bytes, ttl: int) -> None:
    client = get_client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except RedisError as exc:
        _failed(exc)


def delete(*keys: str) -> None:
    client = get_client()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except RedisError as exc:
        _failed(exc)


# ---------- Ключі ----------

SPECIALTIES = "catalog:specialties"


def doctors_key(specialty_id: int | None) -> str:
    return f"catalog:doctors:{specialty_id if specialty_id is not None else 'all'}"


def slots_key(doctor_id: int) -> str:
    return f"slots:{doctor_id}"


def invalidate_catalog() -> None:
    """Після змін в адмінці: нова спеціальність або лікар."""
    client = get_client()
    if client is None:
        return
    try:
        keys = list(client.scan_iter("catalog:*"))
        if keys:
            client.delete(*keys)
    except RedisError as exc:
        _failed(exc)


# ---------- Готова відповідь з кешу або з бази ----------


def cached_json(
    key: str, ttl: int, adapter: TypeAdapter, load: Callable[[], object]
) -> Response:
    """Віддає JSON з кешу (X-Cache: HIT) або викликає load(), перетворює
    результат на JSON, кладе в кеш і віддає (X-Cache: MISS)."""
    body = get(key)
    status = "HIT"
    if body is None:
        status = "MISS"
        data = adapter.validate_python(load(), from_attributes=True)
        body = adapter.dump_json(data)
        put(key, body, ttl)
    return Response(body, media_type="application/json", headers={"X-Cache": status})
