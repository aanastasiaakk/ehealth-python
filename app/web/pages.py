"""HTML-сторінки для браузера: вхід, реєстрація і домашні сторінки ролей.

Браузер не вміє сам додавати заголовок `Authorization`, тому після
входу токен кладемо в cookie з прапорцями:
- HttpOnly  — JavaScript на сторінці не може прочитати токен (захист від XSS);
- SameSite=Lax — cookie не надсилається з POST-запитами з чужих сайтів
  (базовий захист від CSRF).

Анонімного відвідувача захищені сторінки перенаправляють (302) на /login,
а користувача з іншою роллю — показують сторінку 403.
"""

from datetime import timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.database import get_db
from app.dependencies import COOKIE_NAME, get_optional_user
from app.models import Appointment, Doctor, Role, Slot, Specialty, User
from app.security import create_access_token
from app.services import booking
from app.services import users as user_service

settings = get_settings()
router = APIRouter(include_in_schema=False)  # не показувати сторінки в Swagger

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
KYIV = ZoneInfo("Europe/Kyiv")


def _local(dt) -> str:
    """Фільтр для шаблонів: показати час у київському часовому поясі."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KYIV).strftime("%d.%m %H:%M")


templates.env.filters["local"] = _local
templates.env.globals["app_name"] = settings.app_name

HOME_BY_ROLE = {Role.PATIENT: "/patient", Role.DOCTOR: "/doctor", Role.ADMIN: "/admin"}

MESSAGES = {
    "booked": ("success", "Ви успішно записалися!"),
    "taken": ("error", "На жаль, цей слот щойно зайняли. Оберіть інший."),
    "cancelled": ("success", "Запис скасовано."),
    "cannot_cancel": ("error", "Цей запис не можна скасувати."),
    "registered": ("success", "Реєстрація успішна. Ласкаво просимо!"),
}


# ---------- Перевірка доступу для сторінок ----------


class LoginRequired(Exception):
    """Відвідувач не увійшов → обробник у main.py перенаправить на /login."""


class PageForbidden(Exception):
    """Роль не підходить → обробник у main.py покаже сторінку 403."""


def page_user(*roles: Role):
    def dependency(
        request: Request, user: User | None = Depends(get_optional_user)
    ) -> User:
        request.state.user = user  # щоб сторінка 403 знала, хто увійшов
        if user is None:
            raise LoginRequired()
        if roles and user.role not in roles:
            raise PageForbidden()
        return user

    return dependency


def _login_response(user: User, url: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user.id),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
    )
    return response


def _render(request: Request, name: str, status_code: int = 200, **context):
    msg = MESSAGES.get(request.query_params.get("msg", ""))
    return templates.TemplateResponse(
        request, name, {"message": msg, **context}, status_code=status_code
    )


# ---------- Публічні сторінки ----------


@router.get("/", response_class=HTMLResponse)
def index(request: Request, user: User | None = Depends(get_optional_user)):
    if user:
        return RedirectResponse("/home", status_code=302)
    return _render(request, "index.html", user=None)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return _render(request, "login.html", user=None, error=None)


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = user_service.authenticate(db, email, password)
    if user is None:
        return _render(
            request,
            "login.html",
            status_code=401,
            user=None,
            error="Неправильний email або пароль",
            email=email,
        )
    return _login_response(user, "/home")


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return _render(request, "register.html", user=None, error=None, form={})


@router.post("/register", response_class=HTMLResponse)
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    form = {"email": email, "full_name": full_name, "phone": phone}
    error = None
    if len(password) < 8:
        error = "Пароль має містити щонайменше 8 символів"
    elif len(full_name.strip()) < 2:
        error = "Вкажіть ім'я"
    elif "@" not in email:
        error = "Некоректний email"
    if error is None:
        try:
            user = user_service.create_user(
                db, email.strip(), password, full_name.strip(), phone.strip() or None
            )
            return _login_response(user, "/home?msg=registered")
        except user_service.EmailAlreadyExists:
            error = "Користувач з таким email вже існує"
    return _render(
        request, "register.html", status_code=400, user=None, error=error, form=form
    )


@router.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/home")
def home(request: Request, user: User = Depends(page_user())):
    """Єдина точка входу після логіну: веде на домашню сторінку своєї ролі."""
    url = HOME_BY_ROLE[user.role]
    if request.query_params.get("msg"):
        url += f"?msg={request.query_params['msg']}"
    return RedirectResponse(url, status_code=302)


# ---------- Пацієнт ----------


@router.get("/patient", response_class=HTMLResponse)
def patient_home(
    request: Request,
    specialty_id: int | None = None,
    user: User = Depends(page_user(Role.PATIENT)),
    db: Session = Depends(get_db),
):
    specialties = db.scalars(select(Specialty).order_by(Specialty.name)).all()
    stmt = select(Doctor).options(joinedload(Doctor.specialty)).order_by(Doctor.id)
    if specialty_id:
        stmt = stmt.where(Doctor.specialty_id == specialty_id)
    doctors = db.scalars(stmt).all()
    # Для сторінки показуємо лише найближчі 6 вільних слотів кожного лікаря
    free = {d.id: booking.list_free_slots(db, d.id, days=14, limit=6) for d in doctors}
    return _render(
        request,
        "patient.html",
        user=user,
        appointments=booking.list_patient_appointments(db, user.id),
        specialties=specialties,
        selected_specialty=specialty_id,
        doctors=doctors,
        free=free,
    )


@router.post("/patient/book")
def patient_book(
    slot_id: int = Form(...),
    user: User = Depends(page_user(Role.PATIENT)),
    db: Session = Depends(get_db),
):
    try:
        booking.book_slot(db, user, slot_id)
    except (booking.SlotNotFound, booking.SlotUnavailable):
        return RedirectResponse("/patient?msg=taken", status_code=303)
    return RedirectResponse("/patient?msg=booked", status_code=303)


@router.post("/patient/cancel/{appointment_id}")
def patient_cancel(
    appointment_id: int,
    user: User = Depends(page_user(Role.PATIENT)),
    db: Session = Depends(get_db),
):
    try:
        appt = booking.get_appointment(db, appointment_id)
        if appt.patient_id != user.id:  # IDOR: чужий запис скасувати не можна
            raise PageForbidden()
        booking.cancel_appointment(db, appt)
    except (booking.AppointmentNotFound, booking.CannotCancelPast):
        return RedirectResponse("/patient?msg=cannot_cancel", status_code=303)
    return RedirectResponse("/patient?msg=cancelled", status_code=303)


# ---------- Лікар ----------


@router.get("/doctor", response_class=HTMLResponse)
def doctor_home(
    request: Request,
    user: User = Depends(page_user(Role.DOCTOR)),
    db: Session = Depends(get_db),
):
    profile = user.doctor_profile
    schedule = booking.doctor_schedule(db, profile.id) if profile else []
    return _render(request, "doctor.html", user=user, profile=profile, slots=schedule)


# ---------- Адміністратор ----------


@router.get("/admin", response_class=HTMLResponse)
def admin_home(
    request: Request,
    user: User = Depends(page_user(Role.ADMIN)),
    db: Session = Depends(get_db),
):
    users = db.scalars(select(User).order_by(User.id)).all()
    recent = db.scalars(
        select(Appointment)
        .options(
            joinedload(Appointment.patient),
            joinedload(Appointment.slot).joinedload(Slot.doctor),
        )
        .order_by(Appointment.created_at.desc())
        .limit(10)
    ).all()
    return _render(
        request,
        "admin.html",
        user=user,
        stats=booking.stats(db),
        users=users,
        recent=recent,
    )
