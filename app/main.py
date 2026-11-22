"""Точка входу застосунку. Саме цей файл запускає uvicorn:

uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from app import models  # noqa: F401  (імпорт реєструє таблиці в Base.metadata)
from app.api import admin, appointments, auth, catalog, doctor, health, users
from app.config import get_settings
from app.database import engine
from app.errors import setup_error_handling
from app.instance import INSTANCE_ID
from app.limiter import ConcurrencyLimitMiddleware
from app.metrics import setup_metrics
from app.migrations import apply_migrations
from app.web import pages

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Виконується один раз під час старту сервера: створює таблиці й
    # індекси, яких ще немає. У Docker вимкнено (AUTO_MIGRATE=false):
    # там це робить окремий сервіс `migrate` до старту застосунку.
    if settings.auto_migrate:
        apply_migrations(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description="Сервіс електронного запису до державних лікарів",
    version="0.8.0",
    lifespan=lifespan,
    # У production debug завжди False (перевіряє app/config.py)
    debug=settings.debug,
    # Swagger можна вимкнути (у production за замовчуванням вимкнений)
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Помилки 500 без стектрейсів для користувача, сторінка 404 (ЛР3)
setup_error_handling(app)


class InstanceHeaderMiddleware:
    """Додає до КОЖНОЇ відповіді заголовок X-Instance з ім'ям копії
    застосунку (ЛР6): так видно, яку репліку обрав Nginx.

    Написано як «чисте» ASGI-проміжне ПЗ: воно лише дописує заголовок
    і майже не додає затримки, на відміну від BaseHTTPMiddleware."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-instance", INSTANCE_ID.encode()),
                ]
            await send(message)

        await self.app(scope, receive, send_with_header)


# ЛР7: не більше max_concurrent_requests запитів одночасно (див. app/limiter.py)
app.add_middleware(
    ConcurrencyLimitMiddleware,
    limit=settings.max_concurrent_requests,
    queue_timeout=settings.request_queue_timeout,
)
# Додається останнім = виконується першим: X-Instance є навіть у відповіді 503
app.add_middleware(InstanceHeaderMiddleware)

# ЛР8: метрики для Prometheus на /metrics (див. app/metrics.py)
setup_metrics(app)

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
