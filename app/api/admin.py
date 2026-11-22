"""Адмін-панель (API). УСІ маршрути доступні лише ролі ADMIN.

Перевірку ролі підключено один раз на рівні роутера (dependencies=...),
тому неможливо «забути» захистити новий адмінський ендпоінт.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app import cache
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Doctor, Role, Specialty, User
from app.schemas import (
    ActiveUpdate,
    DoctorCreate,
    DoctorOut,
    RoleUpdate,
    SlotOut,
    SlotsCreate,
    SpecialtyCreate,
    SpecialtyOut,
    Stats,
    UserOut,
)
from app.services import booking
from app.services import users as user_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles(Role.ADMIN))],
)


@router.get("/stats", response_model=Stats)
def get_stats(db: Session = Depends(get_db)):
    return booking.stats(db)


# ---------- Користувачі ----------


@router.get("/users", response_model=list[UserOut])
def list_users(role: Role | None = None, db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    return db.scalars(stmt).all()


def _get_other_user(db: Session, user_id: int, admin: User) -> User:
    if user_id == admin.id:
        # Щоб адмін випадково не позбавив себе прав і не лишив систему без адміна
        raise HTTPException(400, "You cannot change your own role or status")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_role(
    user_id: int,
    data: RoleUpdate,
    admin: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _get_other_user(db, user_id, admin)
    user.role = data.role
    db.commit()
    return user


@router.patch("/users/{user_id}/active", response_model=UserOut)
def change_active(
    user_id: int,
    data: ActiveUpdate,
    admin: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Заблокувати / розблокувати користувача."""
    user = _get_other_user(db, user_id, admin)
    user.is_active = data.is_active
    db.commit()
    return user


# ---------- Каталог ----------


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
def create_specialty(data: SpecialtyCreate, db: Session = Depends(get_db)):
    specialty = Specialty(name=data.name)
    db.add(specialty)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Specialty already exists") from exc
    cache.invalidate_catalog()  # ЛР7: нова спеціальність видна одразу
    return specialty


@router.post("/doctors", response_model=DoctorOut, status_code=201)
def create_doctor(data: DoctorCreate, db: Session = Depends(get_db)):
    """Створює лікаря та його обліковий запис з роллю DOCTOR."""
    if db.get(Specialty, data.specialty_id) is None:
        raise HTTPException(404, "Specialty not found")
    try:
        account = user_service.create_user(
            db, data.email, data.password, data.full_name, role=Role.DOCTOR
        )
    except user_service.EmailAlreadyExists as exc:
        raise HTTPException(409, "Email already registered") from exc
    doctor = Doctor(
        full_name=data.full_name, specialty_id=data.specialty_id, user_id=account.id
    )
    db.add(doctor)
    db.commit()
    cache.invalidate_catalog()  # ЛР7: новий лікар видний одразу
    return db.scalar(
        select(Doctor)
        .where(Doctor.id == doctor.id)
        .options(joinedload(Doctor.specialty))
    )


@router.post(
    "/doctors/{doctor_id}/slots", response_model=list[SlotOut], status_code=201
)
def create_slots(doctor_id: int, data: SlotsCreate, db: Session = Depends(get_db)):
    """Згенерувати слоти для лікаря (наприклад, з 9:00 до 13:00 по 20 хв)."""
    if db.get(Doctor, doctor_id) is None:
        raise HTTPException(404, "Doctor not found")
    if data.start.tzinfo is None or data.end.tzinfo is None:
        raise HTTPException(422, "start and end must include a timezone, e.g. +03:00")
    if data.end <= data.start:
        raise HTTPException(422, "end must be after start")
    return booking.generate_slots(
        db, doctor_id, data.start, data.end, data.duration_minutes
    )
