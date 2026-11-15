"""Тести бізнес-логіки запису (MVP), включно з race condition."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Appointment, Role, Slot
from app.services import booking
from tests.conftest import auth


def _book(client, slot_id, user):
    return client.post("/appointments", json={"slot_id": slot_id}, headers=auth(user))


def test_patient_books_free_slot(client, db, make_user, make_doctor, make_slot):
    patient = make_user()
    slot = make_slot(make_doctor())
    response = _book(client, slot.id, patient)
    assert response.status_code == 201
    body = response.json()
    assert body["patient_id"] == patient.id
    assert body["specialty"] == "Кардіолог"
    db.refresh(slot)
    assert slot.is_available is False


def test_booking_taken_slot_gets_409(client, make_user, make_doctor, make_slot):
    slot = make_slot(make_doctor())
    assert _book(client, slot.id, make_user()).status_code == 201
    assert _book(client, slot.id, make_user()).status_code == 409


def test_booking_past_slot_gets_409(client, make_user, make_doctor, make_slot):
    slot = make_slot(make_doctor(), hours=-2)
    assert _book(client, slot.id, make_user()).status_code == 409


def test_booking_unknown_slot_gets_404(client, make_user):
    assert _book(client, 999, make_user()).status_code == 404


def test_cancel_frees_the_slot(client, db, make_user, make_doctor, make_slot):
    patient = make_user()
    slot = make_slot(make_doctor())
    appt_id = _book(client, slot.id, patient).json()["id"]
    response = client.delete(f"/appointments/{appt_id}", headers=auth(patient))
    assert response.status_code == 204
    db.refresh(slot)
    assert slot.is_available is True
    # Слот знову можна забронювати
    assert _book(client, slot.id, make_user()).status_code == 201


def test_my_appointments_lists_only_mine(client, make_user, make_doctor, make_slot):
    doctor = make_doctor()
    alice, bob = make_user(), make_user()
    s1, s2 = make_slot(doctor, 24), make_slot(doctor, 48)
    _book(client, s1.id, alice)
    _book(client, s2.id, bob)
    mine = client.get("/appointments/me", headers=auth(alice)).json()
    assert [a["slot_id"] for a in mine] == [s1.id]


def test_free_slots_listing_hides_taken(client, make_user, make_doctor, make_slot):
    doctor = make_doctor()
    s1, s2 = make_slot(doctor, 24), make_slot(doctor, 25)
    _book(client, s1.id, make_user())
    free = client.get(f"/doctors/{doctor.id}/slots").json()
    assert [s["id"] for s in free] == [s2.id]


def test_admin_creates_doctor_and_slots(client, make_user):
    admin = make_user(Role.ADMIN)
    h = auth(admin)
    spec = client.post("/admin/specialties", json={"name": "Хірург"}, headers=h).json()
    doctor = client.post(
        "/admin/doctors",
        json={
            "full_name": "Лікар Новий",
            "specialty_id": spec["id"],
            "email": "new.doctor@test.ua",
            "password": "doctorpass1",
        },
        headers=h,
    )
    assert doctor.status_code == 201
    start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
        hour=6, minute=0, second=0, microsecond=0
    )
    slots = client.post(
        f"/admin/doctors/{doctor.json()['id']}/slots",
        json={
            "start": start.isoformat(),
            "end": (start + timedelta(hours=2)).isoformat(),
            "duration_minutes": 30,
        },
        headers=h,
    )
    assert slots.status_code == 201
    assert len(slots.json()) == 4
    # Новий лікар може увійти і бачить свій розклад
    token = client.post(
        "/auth/token",
        data={"username": "new.doctor@test.ua", "password": "doctorpass1"},
    ).json()["access_token"]
    schedule = client.get(
        "/doctor/schedule", headers={"Authorization": f"Bearer {token}"}
    )
    assert schedule.status_code == 200
    assert len(schedule.json()) == 4


def test_race_condition_only_one_booking_wins(db, make_user, make_doctor, make_slot):
    """Головний сценарій навантаження: 20 пацієнтів ОДНОЧАСНО бронюють
    той самий слот (кожен у своєму потоці й зі своїм з'єднанням з базою).
    Успішним має бути рівно один."""
    slot = make_slot(make_doctor())
    patients = [make_user() for _ in range(20)]

    def try_book(patient) -> bool:
        session = SessionLocal()
        try:
            booking.book_slot(session, patient, slot.id)
            return True
        except booking.SlotUnavailable:
            return False
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(try_book, patients))

    assert results.count(True) == 1
    assert results.count(False) == 19
    count = db.scalar(
        select(func.count(Appointment.id)).where(Appointment.slot_id == slot.id)
    )
    assert count == 1
    db.expire_all()
    assert db.get(Slot, slot.id).is_available is False
