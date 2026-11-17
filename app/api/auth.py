"""Реєстрація та вхід через API (для мобільних застосунків і Swagger)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import COOKIE_NAME
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    """Реєстрація ЗВИЧАЙНОГО користувача (пацієнта).
    Роль не можна передати в запиті — її призначає лише адміністратор."""
    try:
        return user_service.create_user(
            db, data.email, data.password, data.full_name, data.phone
        )
    except user_service.EmailAlreadyExists as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Email already registered"
        ) from exc


@router.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Вхід для будь-якої ролі. У полі `username` передається email.

    Формат запиту (form-data з username/password) — стандарт OAuth2,
    завдяки йому працює кнопка «Authorize» у Swagger (/docs).
    """
    user = user_service.authenticate(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.post("/logout", status_code=204)
def logout(response: Response):
    """Видаляє cookie з токеном (для браузера)."""
    response.delete_cookie(COOKIE_NAME)
