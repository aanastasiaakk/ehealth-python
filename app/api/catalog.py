"""Публічний каталог: спеціальності, лікарі, вільні слоти.

Ці дані може переглядати будь-хто без входу — як на реальних сайтах
запису. Саме ці ендпоінти отримують найбільше запитів о 8:00, тому
в наступних лабах їх відповіді кешуватимуться в Redis.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Doctor, Specialty
from app.schemas import DoctorOut, SlotOut, SpecialtyOut
from app.services import booking

router = APIRouter(tags=["catalog"])


@router.get("/specialties", response_model=list[SpecialtyOut])
def list_specialties(db: Session = Depends(get_db)):
    return db.scalars(select(Specialty).order_by(Specialty.name)).all()


@router.get("/doctors", response_model=list[DoctorOut])
def list_doctors(specialty_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Doctor).options(joinedload(Doctor.specialty)).order_by(Doctor.id)
    if specialty_id is not None:
        stmt = stmt.where(Doctor.specialty_id == specialty_id)
    return db.scalars(stmt).all()


@router.get("/doctors/{doctor_id}/slots", response_model=list[SlotOut])
def list_doctor_slots(doctor_id: int, days: int = 14, db: Session = Depends(get_db)):
    if db.get(Doctor, doctor_id) is None:
        raise HTTPException(404, "Doctor not found")
    return booking.list_free_slots(db, doctor_id, days=min(days, 60))
