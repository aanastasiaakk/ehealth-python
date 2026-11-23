"""Бізнес-логіка запису до лікаря (головна частина MVP)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import cache
from app.models import Appointment, Doctor, Role, Slot, User


class SlotNotFound(Exception):
    pass


class SlotUnavailable(Exception):
    pass


class AppointmentNotFound(Exception):
    pass


class CannotCancelPast(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Бронювання ----------


def book_slot(db: Session, patient: User, slot_id: int) -> Appointment:
    """Записує пацієнта на слот. Захист від race condition має ДВА рівні:

    1. `SELECT ... FOR UPDATE` блокує рядок слоту до кінця транзакції.
       Якщо двоє бронюють одночасно, друга транзакція чекає, поки перша
       завершиться, і вже бачить is_available = False.
    2. Обмеження UNIQUE(slot_id) у таблиці appointments — «останній рубіж»:
       навіть якщо щось піде не так, база не дозволить два записи на слот.
    """
    slot = db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())
    if slot is None:
        raise SlotNotFound(slot_id)
    if not slot.is_available or slot.starts_at <= _now():
        db.rollback()  # знімаємо блокування
        raise SlotUnavailable(slot_id)

    appointment = Appointment(slot_id=slot.id, patient_id=patient.id)
    slot.is_available = False
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SlotUnavailable(slot_id) from exc
    # ЛР7: список вільних слотів лікаря змінився — прибираємо його з кешу
    cache.delete(cache.slots_key(slot.doctor_id))
    db.refresh(appointment)
    return appointment


def get_appointment(db: Session, appointment_id: int) -> Appointment:
    appt = db.scalar(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .options(
            joinedload(Appointment.slot)
            .joinedload(Slot.doctor)
            .joinedload(Doctor.specialty)
        )
    )
    if appt is None:
        raise AppointmentNotFound(appointment_id)
    return appt


def cancel_appointment(db: Session, appointment: Appointment) -> None:
    """Скасовує запис і знову робить слот вільним.
    Перевірку «чи має користувач право» робить викликаючий код."""
    if appointment.slot.starts_at <= _now():
        raise CannotCancelPast(appointment.id)
    appointment.slot.is_available = True
    doctor_id = appointment.slot.doctor_id
    db.delete(appointment)
    db.commit()
    cache.delete(cache.slots_key(doctor_id))  # ЛР7: слот знову вільний


def list_patient_appointments(db: Session, patient_id: int) -> list[Appointment]:
    return list(
        db.scalars(
            select(Appointment)
            .join(Appointment.slot)
            .where(Appointment.patient_id == patient_id)
            .options(
                joinedload(Appointment.slot)
                .joinedload(Slot.doctor)
                .joinedload(Doctor.specialty)
            )
            .order_by(Slot.starts_at)
        )
    )


# ---------- Каталог ----------


def list_free_slots(
    db: Session, doctor_id: int, days: int = 14, limit: int = 200
) -> list[Slot]:
    """Вільні майбутні слоти лікаря на найближчі `days` днів."""
    now = _now()
    return list(
        db.scalars(
            select(Slot)
            .where(
                Slot.doctor_id == doctor_id,
                Slot.is_available.is_(True),
                Slot.starts_at > now,
                Slot.starts_at < now + timedelta(days=days),
            )
            .order_by(Slot.starts_at)
            .limit(limit)
        )
    )


def generate_slots(
    db: Session, doctor_id: int, start: datetime, end: datetime, minutes: int
) -> list[Slot]:
    """Створює слоти від start до end з кроком `minutes`.
    Слоти, що вже існують (той самий лікар і час), пропускаються."""
    existing = set(
        db.scalars(
            select(Slot.starts_at).where(
                Slot.doctor_id == doctor_id,
                Slot.starts_at >= start,
                Slot.starts_at < end,
            )
        )
    )
    created = []
    current = start
    while current + timedelta(minutes=minutes) <= end:
        if current not in existing:
            slot = Slot(doctor_id=doctor_id, starts_at=current, is_available=True)
            db.add(slot)
            created.append(slot)
        current += timedelta(minutes=minutes)
    db.commit()
    if created:
        cache.delete(cache.slots_key(doctor_id))  # ЛР7: з'явилися нові слоти
    return created


# ---------- Лікар ----------


def doctor_schedule(db: Session, doctor_id: int, days: int = 7) -> list[Slot]:
    """Розклад лікаря (вільні й зайняті слоти) від початку сьогоднішнього дня."""
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    return list(
        db.scalars(
            select(Slot)
            .where(
                Slot.doctor_id == doctor_id,
                Slot.starts_at >= today,
                Slot.starts_at < today + timedelta(days=days),
            )
            .options(joinedload(Slot.appointment).joinedload(Appointment.patient))
            .order_by(Slot.starts_at)
        )
    )


# ---------- Адмін ----------


def stats(db: Session) -> dict:
    def count(stmt) -> int:
        return db.scalar(stmt) or 0

    return {
        "users": count(select(func.count(User.id))),
        "patients": count(select(func.count(User.id)).where(User.role == Role.PATIENT)),
        "doctors": count(select(func.count(Doctor.id))),
        "slots_total": count(select(func.count(Slot.id))),
        "slots_free": count(
            select(func.count(Slot.id)).where(
                Slot.is_available.is_(True), Slot.starts_at > _now()
            )
        ),
        "appointments": count(select(func.count(Appointment.id))),
    }
