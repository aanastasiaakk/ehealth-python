"""Схеми Pydantic: описують, які дані API приймає і повертає.

FastAPI автоматично перевіряє вхідні дані за цими схемами (наприклад,
що email справді схожий на email, а пароль не коротший за 8 символів)
і повертає 422, якщо щось не так.

Важливо: у схемах відповідей (UserOut тощо) НЕМАЄ password_hash,
тому хеш пароля ніколи не потрапить у відповідь API.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Role

# ---------- Користувачі ----------


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=20)


class UserUpdate(BaseModel):
    """Що користувач може змінити у своєму профілі. Роль тут змінити НЕ можна."""

    full_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=20)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    role: Role
    is_active: bool


class RoleUpdate(BaseModel):
    role: Role


class ActiveUpdate(BaseModel):
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Каталог ----------


class SpecialtyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class SpecialtyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class DoctorCreate(BaseModel):
    """Адмін створює лікаря разом з його обліковим записом."""

    full_name: str = Field(min_length=2, max_length=200)
    specialty_id: int
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class DoctorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    specialty: SpecialtyOut


class SlotsCreate(BaseModel):
    """Згенерувати слоти для лікаря: з start до end з кроком duration хвилин."""

    start: datetime
    end: datetime
    duration_minutes: int = Field(default=20, ge=5, le=240)


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    starts_at: datetime
    is_available: bool


# ---------- Записи ----------


class AppointmentCreate(BaseModel):
    slot_id: int


class AppointmentOut(BaseModel):
    id: int
    slot_id: int
    patient_id: int
    created_at: datetime
    starts_at: datetime
    doctor_name: str
    specialty: str

    @classmethod
    def from_model(cls, appt) -> "AppointmentOut":
        return cls(
            id=appt.id,
            slot_id=appt.slot_id,
            patient_id=appt.patient_id,
            created_at=appt.created_at,
            starts_at=appt.slot.starts_at,
            doctor_name=appt.slot.doctor.full_name,
            specialty=appt.slot.doctor.specialty.name,
        )


class ScheduleItem(BaseModel):
    """Рядок розкладу лікаря."""

    slot_id: int
    starts_at: datetime
    is_available: bool
    patient_name: str | None = None
    patient_phone: str | None = None


class Stats(BaseModel):
    users: int
    patients: int
    doctors: int
    slots_total: int
    slots_free: int
    appointments: int
