"""Службові ендпоінти для перевірки, що застосунок і база даних працюють.

Такі ендпоінти в реальних системах опитує балансувальник (Nginx) або
Kubernetes: якщо копія бекенду не відповідає, трафік на неї не йде.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Чи живий сам бекенд (без звернення до бази) і в якому середовищі."""
    return {"status": "ok", "environment": get_settings().app_env}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    """Чи є з'єднання з PostgreSQL: виконуємо найпростіший запит SELECT 1."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "connected"}
