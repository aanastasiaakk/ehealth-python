"""Моделі даних (таблиці бази даних).

Кожен клас нижче — це одна таблиця в PostgreSQL.
Кожен атрибут з mapped_column — це одна колонка.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Specialty(Base):
    """Спеціальність лікаря: кардіолог, невролог тощо."""

    __tablename__ = "specialties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    doctors: Mapped[list["Doctor"]] = relationship(back_populates="specialty")


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialties.id"))

    specialty: Mapped[Specialty] = relationship(back_populates="doctors")
    slots: Mapped[list["Slot"]] = relationship(back_populates="doctor")


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(20), unique=True)


class Slot(Base):
    """Проміжок часу, на який можна записатися до лікаря."""

    __tablename__ = "slots"
    # Лікар не може мати два слоти, що починаються в той самий час
    __table_args__ = (UniqueConstraint("doctor_id", "starts_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped[Doctor] = relationship(back_populates="slots")


class Appointment(Base):
    """Запис пацієнта на конкретний слот."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True — ключовий захист від race condition:
    # база даних фізично не дозволить створити два записи на один слот,
    # навіть якщо два запити прийдуть в одну й ту саму мілісекунду.
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), unique=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
