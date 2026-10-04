"""Точка входу застосунку. Саме цей файл запускає uvicorn:

uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (імпорт реєструє таблиці в Base.metadata)
from app.api import health
from app.config import get_settings
from app.database import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Виконується один раз під час старту сервера:
    # створює таблиці в базі, якщо їх ще немає.
    # (У наступних лабах це можна замінити на міграції Alembic.)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Сервіс електронного запису до державних лікарів",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)


@app.get("/")
def root() -> dict:
    return {"message": f"Вітаємо в {settings.app_name}!", "docs": "/docs"}
