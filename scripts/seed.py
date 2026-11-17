"""Заповнює базу початковими даними.

Запуск (з кореня проєкту, з увімкненим .venv):

    APP_ENV=sandbox    python -m scripts.seed   # тестове середовище
    APP_ENV=production python -m scripts.seed   # робоче середовище

Скрипт можна запускати повторно: те, що вже існує, не дублюється.

У будь-якому середовищі створює адміністратора
(ADMIN_EMAIL / ADMIN_PASSWORD з файлу .env.<середовище>).

ЛИШЕ в sandbox додатково створює демо-дані: 4 спеціальності, 4 лікарів
з простими паролями, демо-пацієнта і слоти на 5 робочих днів.
У production демо-дані НЕ створюються, щоб тестові акаунти з відомими
паролями не потрапили в робоче середовище.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import models  # noqa: F401
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Doctor, Role, Specialty
from app.services import booking
from app.services import users as user_service

KYIV = ZoneInfo("Europe/Kyiv")
DOCTOR_PASSWORD = "doctor12345"
PATIENT_EMAIL = "patient@ehealth.ua"
PATIENT_PASSWORD = "patient12345"

DOCTORS = [
    ("Кардіолог", "Коваленко Олена Петрівна", "kovalenko@ehealth.ua"),
    ("Невролог", "Шевчук Андрій Іванович", "shevchuk@ehealth.ua"),
    ("Ендокринолог", "Бондар Марія Сергіївна", "bondar@ehealth.ua"),
    ("Офтальмолог", "Ткаченко Ігор Васильович", "tkachenko@ehealth.ua"),
]


def next_workdays(count: int) -> list[date]:
    days, current = [], date.today()
    while len(days) < count:
        current += timedelta(days=1)
        if current.weekday() < 5:  # 0-4 = пн-пт
            days.append(current)
    return days


def ensure_user(db, email, password, full_name, role, phone=None):
    user = user_service.get_user_by_email(db, email)
    if user is None:
        user = user_service.create_user(db, email, password, full_name, phone, role)
        # Пароль production-адміна в консоль не друкуємо
        shown = "***" if get_settings().is_production else password
        print(f"  + {role.value:8} {email} / {shown}")
    return user


def main() -> None:
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        raise SystemExit(
            f"Вкажіть ADMIN_EMAIL і ADMIN_PASSWORD у файлі .env.{settings.app_env}"
        )
    print(f"Середовище: {settings.app_env}")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("Користувачі:")
        ensure_user(
            db,
            settings.admin_email,
            settings.admin_password,
            "Адміністратор системи",
            Role.ADMIN,
        )
        if settings.is_production:
            print("Production: демо-дані не створюються. Готово!")
            return
        ensure_user(
            db,
            PATIENT_EMAIL,
            PATIENT_PASSWORD,
            "Демо Пацієнтка",
            Role.PATIENT,
            "+380501112233",
        )

        for specialty_name, full_name, email in DOCTORS:
            specialty = db.scalar(
                select(Specialty).where(Specialty.name == specialty_name)
            )
            if specialty is None:
                specialty = Specialty(name=specialty_name)
                db.add(specialty)
                db.commit()
            account = ensure_user(db, email, DOCTOR_PASSWORD, full_name, Role.DOCTOR)
            doctor = db.scalar(select(Doctor).where(Doctor.user_id == account.id))
            if doctor is None:
                doctor = Doctor(
                    full_name=full_name, specialty_id=specialty.id, user_id=account.id
                )
                db.add(doctor)
                db.commit()

        print("Слоти:")
        total = 0
        for doctor in db.scalars(select(Doctor)).all():
            for day in next_workdays(5):
                start = datetime.combine(day, time(9, 0), tzinfo=KYIV)
                end = datetime.combine(day, time(13, 0), tzinfo=KYIV)
                total += len(booking.generate_slots(db, doctor.id, start, end, 30))
        print(f"  + створено {total} нових слотів")
        print("Готово!")
    finally:
        db.close()


if __name__ == "__main__":
    main()
