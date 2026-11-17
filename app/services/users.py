"""Бізнес-логіка, пов'язана з користувачами.

Логіку винесено з обробників HTTP-запитів в окремий шар сервісів, щоб:
- її могли використовувати і API, і HTML-сторінки, і скрипт seed;
- її можна було тестувати без HTTP.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Role, User
from app.security import hash_password, verify_password


class EmailAlreadyExists(Exception):
    pass


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email.lower()))


def create_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    phone: str | None = None,
    role: Role = Role.PATIENT,
) -> User:
    """Створює користувача. Через публічну реєстрацію роль завжди PATIENT —
    інші ролі призначає лише адміністратор."""
    if get_user_by_email(db, email):
        raise EmailAlreadyExists(email)
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        phone=phone,
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Повертає користувача, якщо email і пароль правильні, інакше None.

    Навмисно не розрізняємо «немає такого email» і «неправильний пароль»:
    так зловмисник не зможе дізнатися, які email зареєстровані.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
