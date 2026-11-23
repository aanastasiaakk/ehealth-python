"""Публічний каталог: спеціальності, лікарі, вільні слоти.

Ці дані може переглядати будь-хто без входу — як на реальних сайтах
запису. Саме ці ендпоінти отримують найбільше запитів о 8:00 (73 % у
тесті ЛР4), тому з ЛР7 їхні відповіді кешуються в Redis (app/cache.py).
Заголовок відповіді X-Cache показує, звідки вона: HIT — з кешу,
MISS — з бази.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app import cache
from app.config import get_settings
from app.database import get_db
from app.models import Doctor, Specialty
from app.schemas import DoctorOut, SlotOut, SpecialtyOut
from app.services import booking

router = APIRouter(tags=["catalog"])

SPECIALTIES = TypeAdapter(list[SpecialtyOut])
DOCTORS = TypeAdapter(list[DoctorOut])
SLOTS = TypeAdapter(list[SlotOut])
DEFAULT_DAYS = 14


@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(db: Session = Depends(get_db)):
    return cache.cached_json(
        cache.SPECIALTIES,
        get_settings().cache_ttl_catalog,
        SPECIALTIES,
        lambda: db.scalars(select(Specialty).order_by(Specialty.name)).all(),
    )


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(specialty_id: int | None = None, db: Session = Depends(get_db)):
    def load():
        stmt = select(Doctor).options(joinedload(Doctor.specialty)).order_by(Doctor.id)
        if specialty_id is not None:
            stmt = stmt.where(Doctor.specialty_id == specialty_id)
        return db.scalars(stmt).all()

    return cache.cached_json(
        cache.doctors_key(specialty_id), get_settings().cache_ttl_catalog, DOCTORS, load
    )


@router.get("/doctors/{doctor_id}/slots", response_model=list[SlotOut])
def list_doctor_slots(
    doctor_id: int, days: int = DEFAULT_DAYS, db: Session = Depends(get_db)
):
    days = min(days, 60)

    def load():
        if db.get(Doctor, doctor_id) is None:
            raise HTTPException(404, "Doctor not found")
        return booking.list_free_slots(db, doctor_id, days=days)

    if days != DEFAULT_DAYS:
        # Нестандартний період буває рідко — його не кешуємо
        return load()
    return cache.cached_json(
        cache.slots_key(doctor_id), get_settings().cache_ttl_slots, SLOTS, load
    )
