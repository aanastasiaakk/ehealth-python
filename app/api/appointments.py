"""Записи до лікаря (головна бізнес-логіка)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import ensure_owner_or_admin, get_current_user, require_roles
from app.models import Role, User
from app.schemas import AppointmentCreate, AppointmentOut
from app.services import booking

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post("", response_model=AppointmentOut, status_code=201)
def create_appointment(
    data: AppointmentCreate,
    patient: User = Depends(require_roles(Role.PATIENT)),
    db: Session = Depends(get_db),
):
    """Записатися на слот. Лише для пацієнтів.
    Пацієнт завжди записує САМОГО СЕБЕ: patient_id береться з токена,
    а не з тіла запиту, тому записати когось іншого неможливо."""
    try:
        appt = booking.book_slot(db, patient, data.slot_id)
    except booking.SlotNotFound as exc:
        raise HTTPException(404, "Slot not found") from exc
    except booking.SlotUnavailable as exc:
        raise HTTPException(409, "Slot is already taken or in the past") from exc
    return AppointmentOut.from_model(booking.get_appointment(db, appt.id))


@router.get("/me", response_model=list[AppointmentOut])
def my_appointments(
    patient: User = Depends(require_roles(Role.PATIENT)),
    db: Session = Depends(get_db),
):
    return [
        AppointmentOut.from_model(a)
        for a in booking.list_patient_appointments(db, patient.id)
    ]


@router.get("/{appointment_id}", response_model=AppointmentOut)
def read_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Переглянути запис може: пацієнт-власник, лікар цього запису, адмін."""
    try:
        appt = booking.get_appointment(db, appointment_id)
    except booking.AppointmentNotFound as exc:
        raise HTTPException(404, "Appointment not found") from exc
    # Лікар бачить записи до себе (але не може їх скасовувати)
    if user.role == Role.DOCTOR and appt.slot.doctor.user_id == user.id:
        return AppointmentOut.from_model(appt)
    ensure_owner_or_admin(user, appt.patient_id)
    return AppointmentOut.from_model(appt)


@router.delete("/{appointment_id}", status_code=204)
def cancel(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Скасувати запис може лише пацієнт-власник або адмін.
    Чужий пацієнт отримає 403 (захист від IDOR)."""
    try:
        appt = booking.get_appointment(db, appointment_id)
    except booking.AppointmentNotFound as exc:
        raise HTTPException(404, "Appointment not found") from exc
    ensure_owner_or_admin(user, appt.patient_id)
    try:
        booking.cancel_appointment(db, appt)
    except booking.CannotCancelPast as exc:
        raise HTTPException(409, "Cannot cancel a past appointment") from exc
    return Response(status_code=204)
