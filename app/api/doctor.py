"""Кабінет лікаря (API)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import Role, User
from app.schemas import ScheduleItem
from app.services import booking

router = APIRouter(prefix="/doctor", tags=["doctor"])


@router.get("/schedule", response_model=list[ScheduleItem])
def my_schedule(
    days: int = 7,
    user: User = Depends(require_roles(Role.DOCTOR)),
    db: Session = Depends(get_db),
):
    """Розклад поточного лікаря: слоти та хто на них записаний."""
    if user.doctor_profile is None:
        raise HTTPException(404, "Doctor profile is not linked to this account")
    slots = booking.doctor_schedule(db, user.doctor_profile.id, days=min(days, 60))
    return [
        ScheduleItem(
            slot_id=s.id,
            starts_at=s.starts_at,
            is_available=s.is_available,
            patient_name=s.appointment.patient.full_name if s.appointment else None,
            patient_phone=s.appointment.patient.phone if s.appointment else None,
        )
        for s in slots
    ]
