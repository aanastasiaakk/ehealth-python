"""Залежності FastAPI для автентифікації та авторизації.

- Автентифікація (authentication) — «хто ти?»: перевіряємо токен.
- Авторизація (authorization) — «що тобі можна?»: перевіряємо роль і власника.

Токен шукаємо у двох місцях:
1. заголовок `Authorization: Bearer <token>` — так працюють API-клієнти,
   мобільні застосунки та Swagger (/docs);
2. cookie `access_token` — так працюють HTML-сторінки в браузері.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, User
from app.security import decode_access_token

COOKIE_NAME = "access_token"

# auto_error=False: якщо заголовка немає, не падаємо одразу,
# а ще перевіряємо cookie
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_optional_user(
    request: Request,
    bearer_token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """Повертає поточного користувача або None для анонімного відвідувача."""
    token = bearer_token or request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    # Користувача ЗАВЖДИ беремо з бази, а не лише з токена: так, якщо адмін
    # змінить роль або заблокує користувача, це подіє одразу.
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    """Вимагає входу. Анонім отримує 401 Unauthorized."""
    if user is None:
        raise _unauthorized()
    return user


def require_roles(*roles: Role):
    """Фабрика залежностей: пропускає лише користувачів з указаними ролями.

    Використання:  user: User = Depends(require_roles(Role.ADMIN))
    Користувач з іншою роллю отримує 403 Forbidden
    («я знаю, хто ти, але тобі сюди не можна»).
    """

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return checker


def ensure_owner_or_admin(user: User, owner_id: int) -> None:
    """Захист від IDOR (горизонтальне розмежування прав):
    змінювати ресурс може лише його власник або адміністратор."""
    if user.id != owner_id and user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can access only your own resources",
        )
