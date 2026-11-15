"""Точка входу застосунку. Саме цей файл запускає uvicorn:

uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app import models  # noqa: F401  (імпорт реєструє таблиці в Base.metadata)
from app.api import admin, appointments, auth, catalog, doctor, health, users
from app.config import get_settings
from app.database import Base, engine
from app.web import pages

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Виконується один раз під час старту сервера:
    # створює таблиці в базі, якщо їх ще немає.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Сервіс електронного запису до державних лікарів",
    version="0.2.0",
    lifespan=lifespan,
)

# ---- JSON API ----
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(catalog.router)
app.include_router(appointments.router)
app.include_router(doctor.router)
app.include_router(admin.router)

# ---- HTML-сторінки ----
app.include_router(pages.router)


@app.exception_handler(pages.LoginRequired)
def redirect_to_login(request: Request, _: pages.LoginRequired):
    """Анонім на захищеній сторінці → 302 на сторінку входу."""
    return RedirectResponse("/login", status_code=302)


@app.exception_handler(pages.PageForbidden)
def forbidden_page(request: Request, _: pages.PageForbidden):
    """Не та роль → HTML-сторінка з кодом 403."""
    user = getattr(request.state, "user", None)
    return pages.templates.TemplateResponse(
        request, "403.html", {"user": user, "message": None}, status_code=403
    )
