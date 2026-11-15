"""ЮНІТ-тести: перевіряють окремі функції безпеки без бази та HTTP."""

from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from app.config import get_settings
from app.dependencies import ensure_owner_or_admin, require_roles
from app.models import Role
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# ---------- Паролі ----------


def test_password_is_not_stored_in_plain_text():
    hashed = hash_password("secret-pass")
    assert hashed != "secret-pass"
    assert hashed.startswith("$2b$")  # формат bcrypt


def test_verify_password_correct_and_wrong():
    hashed = hash_password("secret-pass")
    assert verify_password("secret-pass", hashed) is True
    assert verify_password("wrong-pass", hashed) is False


def test_same_password_gives_different_hashes():
    # Завдяки солі однакові паролі в базі виглядають по-різному
    assert hash_password("same-pass") != hash_password("same-pass")


# ---------- JWT ----------


def test_token_roundtrip():
    token = create_access_token(42)
    assert decode_access_token(token) == 42


def test_expired_token_is_rejected():
    token = create_access_token(42, expires_minutes=-1)
    assert decode_access_token(token) is None


def test_tampered_token_is_rejected():
    token = create_access_token(42)
    header, payload, signature = token.split(".")
    # Міняємо перший символ підпису — токен має стати недійсним
    broken = ("A" if signature[0] != "A" else "B") + signature[1:]
    assert decode_access_token(f"{header}.{payload}.{broken}") is None


def test_token_signed_with_other_key_is_rejected():
    # Зловмисник створив токен «адміна» своїм ключем
    fake = jwt.encode(
        {"sub": "1"}, "hacker-key-that-is-long-enough-for-hs256!!", algorithm="HS256"
    )
    assert decode_access_token(fake) is None


def test_garbage_token_is_rejected():
    assert decode_access_token("not-a-token") is None


def test_secret_key_is_configured():
    assert len(get_settings().secret_key) >= 32


# ---------- Правила доступу ----------


def _user(user_id: int, role: Role):
    return SimpleNamespace(id=user_id, role=role)


def test_owner_can_access_own_resource():
    ensure_owner_or_admin(_user(1, Role.PATIENT), owner_id=1)  # без винятку


def test_admin_can_access_any_resource():
    ensure_owner_or_admin(_user(99, Role.ADMIN), owner_id=1)


def test_other_user_gets_403():
    with pytest.raises(HTTPException) as err:
        ensure_owner_or_admin(_user(2, Role.PATIENT), owner_id=1)
    assert err.value.status_code == 403


def test_require_roles_allows_and_forbids():
    only_admin = require_roles(Role.ADMIN)
    admin = _user(1, Role.ADMIN)
    assert only_admin(user=admin) is admin
    with pytest.raises(HTTPException) as err:
        only_admin(user=_user(2, Role.PATIENT))
    assert err.value.status_code == 403
