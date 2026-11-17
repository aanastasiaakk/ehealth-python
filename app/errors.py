"""Обробка помилок (ЛР3).

Мета: користувач НІКОЛИ не бачить внутрішній стектрейс коду.

- Непередбачена помилка (500): користувач отримує коротке повідомлення
  та «код помилки» (error_id), а повний стектрейс з тим самим кодом
  записується в лог сервера. Так розробник може знайти точну причину,
  а зловмисник не дізнається нічого про внутрішню будову системи.
- 404 у браузері: зрозуміла HTML-сторінка замість сирого JSON.

Відповідь підлаштовується під клієнта: браузер (Accept: text/html)
отримує HTML-сторінку, API-клієнт — JSON.

Важливо: у sandbox з DEBUG=true FastAPI сам показує детальну сторінку
зі стектрейсом — це зручно для розробки. У production DEBUG завжди false,
і спрацьовує обробник нижче.
"""

import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings

logger = logging.getLogger("ehealth")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


def _page(request: Request, name: str, status_code: int, **context):
    context.setdefault("user", None)
    context.setdefault("message", None)
    context["app_name"] = get_settings().app_name
    return templates.TemplateResponse(request, name, context, status_code=status_code)


async def unhandled_exception_handler(request: Request, exc: Exception):
    error_id = uuid.uuid4().hex[:8]
    # Повний стектрейс — лише в лог сервера
    logger.exception(
        "Unhandled error %s on %s %s", error_id, request.method, request.url.path
    )
    if _wants_html(request):
        return _page(request, "500.html", 500, error_id=error_id)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_id": error_id},
    )


async def not_found_or_http_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and _wants_html(request):
        return _page(request, "404.html", 404)
    # Усі інші HTTP-помилки (401, 403, 409...) — стандартна JSON-відповідь
    return await http_exception_handler(request, exc)


def setup_error_handling(app: FastAPI) -> None:
    logging.basicConfig(
        level=logging.DEBUG if get_settings().debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.add_exception_handler(StarletteHTTPException, not_found_or_http_handler)
