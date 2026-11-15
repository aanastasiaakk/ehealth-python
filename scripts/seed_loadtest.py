"""Готує sandbox-базу до навантажувального тестування (ЛР4).

Запуск (після звичайного scripts.seed):

    APP_ENV=sandbox python -m scripts.seed_loadtest

Створює:
- 200 пацієнтів loadtest1@ehealth.ua ... loadtest200@ehealth.ua
  з паролем loadtest123 — під ними «входять» віртуальні користувачі Locust;
- багато вільних слотів: кожному лікарю на 20 робочих днів, 8:00–16:00
  по 15 хв, щоб під час тесту слоти не закінчились.

Працює ЛИШЕ в sandbox: тестові акаунти не повинні з'являтися в production.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Doctor, Role
from app.services import booking
from app.services import users as user_service
from scripts.seed import next_workdays

KYIV = ZoneInfo("Europe/Kyiv")
USERS = 200
PASSWORD = "loadtest123"


def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("seed_loadtest працює лише в sandbox")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0
        for i in range(1, USERS + 1):
            email = f"loadtest{i}@ehealth.ua"
            if user_service.get_user_by_email(db, email) is None:
                user_service.create_user(
                    db, email, PASSWORD, f"Load Test {i}", role=Role.PATIENT
                )
                created += 1
        print(f"Пацієнтів для тесту створено: {created} (усього {USERS})")

        doctors = db.scalars(select(Doctor)).all()
        if not doctors:
            raise SystemExit("Немає лікарів: спершу запустіть python -m scripts.seed")
        slots = 0
        for doctor in doctors:
            for day in next_workdays(20):
                start = datetime.combine(day, time(8, 0), tzinfo=KYIV)
                end = datetime.combine(day, time(16, 0), tzinfo=KYIV)
                slots += len(booking.generate_slots(db, doctor.id, start, end, 15))
        print(f"Нових слотів створено: {slots}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
