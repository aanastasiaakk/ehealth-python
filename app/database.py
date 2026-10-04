"""Підключення до реляційної бази даних PostgreSQL через SQLAlchemy.

- engine — «двигун», який тримає пул з'єднань з базою.
- SessionLocal — фабрика сесій; одна сесія = одна «розмова» з базою.
- Base — батьківський клас для всіх моделей (таблиць).
- get_db — функція-залежність для FastAPI: відкриває сесію на час
  одного HTTP-запиту і гарантовано закриває її після.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_size=10,  # скільки з'єднань тримати відкритими постійно
    max_overflow=20,  # скільки додаткових можна відкрити під час піку
    pool_pre_ping=True,  # перевіряти, чи з'єднання ще живе, перед використанням
    echo=settings.debug,  # у режимі debug друкувати SQL-запити в консоль
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
