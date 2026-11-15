"""Заповнює базу тестовими даними для демонстрації.

Запуск (з кореня проєкту, з увімкненим .venv):

    python -m scripts.seed

Скрипт можна запускати повторно: те, що вже існує, не дублюється.
Створює:
- адміністратора (email і пароль з .env: ADMIN_EMAIL / ADMIN_PASSWORD);
- 4 спеціальності та 4 лікарів з обліковими записами;
- демо-пацієнта;
- слоти на 5 найближчих робочих днів (9:00–13:00 по 30 хв, за Києвом).
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
        print(f"  + {role.value:8} {email} / {password}")
    return user


def main() -> None:
    settings = get_settings()
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
