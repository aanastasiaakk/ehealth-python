"""Моделі даних (таблиці бази даних).

Кожен клас нижче — це одна таблиця в PostgreSQL.
Кожен атрибут з mapped_column — це одна колонка.

Зміни в ЛР2: таблицю `patients` замінено на загальну таблицю `users`
з колонкою `role`. Пацієнт, лікар і адміністратор — це всі користувачі
системи, які відрізняються лише роллю (модель RBAC — Role-Based Access Control).
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Role(str, enum.Enum):
    """Ролі користувачів."""

    PATIENT = "patient"  # звичайний користувач: записується до лікаря
    DOCTOR = "doctor"  # бачить свій розклад і пацієнтів
    ADMIN = "admin"  # керує лікарями, слотами та користувачами


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Зберігаємо НЕ пароль, а його хеш (bcrypt). Відновити пароль з хешу неможливо.
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="user_role", values_callable=lambda e: [r.value for r in e]),
        default=Role.PATIENT,
    )
    # Заблокований користувач не може увійти, навіть з правильним паролем
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Якщо користувач — лікар, тут буде його профіль лікаря
    doctor_profile: Mapped["Doctor | None"] = relationship(back_populates="user")


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
    # Обліковий запис лікаря (один користувач = максимум один профіль лікаря)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), unique=True, default=None
    )

    specialty: Mapped[Specialty] = relationship(back_populates="doctors")
    slots: Mapped[list["Slot"]] = relationship(back_populates="doctor")
    user: Mapped[User | None] = relationship(back_populates="doctor_profile")


class Slot(Base):
    """Проміжок часу, на який можна записатися до лікаря."""

    __tablename__ = "slots"
    __table_args__ = (
        # Лікар не може мати два слоти, що починаються в той самий час.
        # Це обмеження створює індекс (doctor_id, starts_at), тому окремий
        # індекс лише по doctor_id зайвий (прибрано в ЛР7).
        UniqueConstraint("doctor_id", "starts_at"),
        # ЛР7: ЧАСТКОВИЙ індекс лише по ВІЛЬНИХ слотах. Найчастіший запит
        # системи — «вільні слоти лікаря від зараз», а зайняті й минулі
        # слоти (їх з часом більшість) у цей індекс не потрапляють:
        # він у рази менший, і базі не треба відкидати зайняті рядки.
        # Див. EXPLAIN ANALYZE у docs/09-lab7-optimization.md
        Index(
            "ix_slots_free_by_doctor",
            "doctor_id",
            "starts_at",
            postgresql_where=text("is_available"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    doctor: Mapped[Doctor] = relationship(back_populates="slots")
    appointment: Mapped["Appointment | None"] = relationship(back_populates="slot")


class Appointment(Base):
    """Запис пацієнта на конкретний слот."""

    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True — ключовий захист від race condition:
    # база даних фізично не дозволить створити два записи на один слот,
    # навіть якщо два запити прийдуть в одну й ту саму мілісекунду.
    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), unique=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    slot: Mapped[Slot] = relationship(back_populates="appointment")
    patient: Mapped[User] = relationship()
