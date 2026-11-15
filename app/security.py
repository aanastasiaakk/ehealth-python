"""Безпека: хешування паролів і JWT-токени.

Це «чисті» функції без бази даних і HTTP, тому їх зручно
покривати юніт-тестами (див. tests/test_security.py).
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

settings = get_settings()


# ---------- Паролі ----------


def _to_bytes(password: str) -> bytes:
    # bcrypt враховує лише перші 72 байти пароля (обмеження алгоритму)
    return password.encode()[:72]


def hash_password(password: str) -> str:
    """Перетворює пароль на хеш. Сіль (salt) генерується випадково щоразу,
    тому однакові паролі мають різні хеші."""
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Перевіряє, чи відповідає введений пароль збереженому хешу."""
    return bcrypt.checkpw(_to_bytes(password), password_hash.encode())


# ---------- JWT-токени ----------
# JWT — це рядок з трьох частин: заголовок.дані.підпис
# Дані (payload) може прочитати будь-хто, але ПІДРОБИТИ їх неможливо
# без secret_key: сервер перевіряє підпис при кожному запиті.


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    if expires_minutes is None:
        expires_minutes = settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),  # subject — кому виданий токен
        "iat": now,  # issued at — коли виданий
        "exp": now + timedelta(minutes=expires_minutes),  # коли стане недійсним
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """Повертає id користувача з токена або None, якщо токен
    підроблений, пошкоджений чи прострочений."""
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
