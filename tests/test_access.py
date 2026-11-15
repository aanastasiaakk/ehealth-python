"""ІНТЕГРАЦІЙНІ тести розмежування прав.

- Вертикальне розмежування: різні РОЛІ мають різний доступ
  (пацієнт не може в адмінку).
- Горизонтальне розмежування (IDOR — Insecure Direct Object Reference):
  користувачі з ОДНАКОВОЮ роллю не мають доступу до даних одне одного
  (пацієнт А не може змінити профіль чи скасувати запис пацієнта Б,
  просто підставивши чужий id в URL).
"""

import pytest

from app.models import Appointment, Role, User
from tests.conftest import DEFAULT_PASSWORD, auth

# ---------- Сценарій 3: Вертикальне розмежування ролей → 403 ----------

ADMIN_ENDPOINTS = [
    ("get", "/admin/stats", None),
    ("get", "/admin/users", None),
    ("post", "/admin/specialties", {"name": "Хірург"}),
    ("patch", "/admin/users/1/role", {"role": "admin"}),
    ("patch", "/admin/users/1/active", {"is_active": False}),
]


@pytest.mark.parametrize("role", [Role.PATIENT, Role.DOCTOR])
@pytest.mark.parametrize("method,url,body", ADMIN_ENDPOINTS)
def test_non_admin_gets_403_on_admin_api(client, make_user, role, method, url, body):
    user = make_user(role)
    response = client.request(method, url, json=body, headers=auth(user))
    assert response.status_code == 403


def test_patient_cannot_promote_self_to_admin(client, db, make_user):
    patient = make_user(Role.PATIENT)
    response = client.patch(
        f"/admin/users/{patient.id}/role", json={"role": "admin"}, headers=auth(patient)
    )
    assert response.status_code == 403
    db.refresh(patient)
    assert patient.role == Role.PATIENT


def test_admin_has_access_to_admin_api(client, make_user):
    admin = make_user(Role.ADMIN)
    assert client.get("/admin/stats", headers=auth(admin)).status_code == 200
    assert client.get("/admin/users", headers=auth(admin)).status_code == 200


@pytest.mark.parametrize("role", [Role.PATIENT, Role.DOCTOR])
def test_non_admin_gets_403_on_admin_page(client, make_user, role):
    user = make_user(role)
    client.post("/login", data={"email": user.email, "password": DEFAULT_PASSWORD})
    response = client.get("/admin")
    assert response.status_code == 403
    assert "Доступ заборонено" in response.text


def test_patient_cannot_open_doctor_cabinet(client, make_user):
    patient = make_user(Role.PATIENT)
    assert client.get("/doctor/schedule", headers=auth(patient)).status_code == 403


def test_doctor_and_admin_cannot_book_as_patient(
    client, make_user, make_doctor, make_slot
):
    slot = make_slot(make_doctor())
    for role in (Role.DOCTOR, Role.ADMIN):
        user = make_user(role)
        response = client.post(
            "/appointments", json={"slot_id": slot.id}, headers=auth(user)
        )
        assert response.status_code == 403


def test_role_change_applies_immediately(client, db, make_user):
    """Роль береться з бази при кожному запиті, а не «зашивається» в токен."""
    user = make_user(Role.PATIENT)
    headers = auth(user)
    assert client.get("/admin/stats", headers=headers).status_code == 403

    admin = make_user(Role.ADMIN)
    client.patch(
        f"/admin/users/{user.id}/role", json={"role": "admin"}, headers=auth(admin)
    )
    assert client.get("/admin/stats", headers=headers).status_code == 200


def test_admin_cannot_demote_self(client, make_user):
    admin = make_user(Role.ADMIN)
    response = client.patch(
        f"/admin/users/{admin.id}/role", json={"role": "patient"}, headers=auth(admin)
    )
    assert response.status_code == 400


# ---------- Сценарій 4: Горизонтальне розмежування (IDOR) → 403 ----------


def test_patient_cannot_edit_other_patient_profile(client, db, make_user):
    alice = make_user(full_name="Аліса")
    bob = make_user(full_name="Боб")
    response = client.patch(
        f"/users/{bob.id}", json={"full_name": "Hacked"}, headers=auth(alice)
    )
    assert response.status_code == 403
    db.refresh(bob)
    assert bob.full_name == "Боб"  # дані не змінилися


def test_patient_cannot_view_other_patient_profile(client, make_user):
    alice, bob = make_user(), make_user()
    assert client.get(f"/users/{bob.id}", headers=auth(alice)).status_code == 403


def test_patient_can_edit_own_profile(client, make_user):
    alice = make_user()
    response = client.patch(
        f"/users/{alice.id}", json={"phone": "+380991234567"}, headers=auth(alice)
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+380991234567"


def test_profile_update_cannot_change_role(client, db, make_user):
    alice = make_user()
    client.patch(f"/users/{alice.id}", json={"role": "admin"}, headers=auth(alice))
    db.refresh(alice)
    assert alice.role == Role.PATIENT


def test_admin_can_edit_any_profile(client, make_user):
    admin, bob = make_user(Role.ADMIN), make_user()
    response = client.patch(
        f"/users/{bob.id}", json={"full_name": "Боб Оновлений"}, headers=auth(admin)
    )
    assert response.status_code == 200


@pytest.fixture
def bobs_appointment(client, make_user, make_doctor, make_slot):
    """Пацієнт Боб записався до лікаря. Повертає (боб, лікар, id_запису)."""
    bob = make_user(full_name="Боб")
    doctor = make_doctor()
    slot = make_slot(doctor)
    response = client.post(
        "/appointments", json={"slot_id": slot.id}, headers=auth(bob)
    )
    assert response.status_code == 201
    return bob, doctor, response.json()["id"]


def test_patient_cannot_cancel_other_patient_appointment(
    client, db, make_user, bobs_appointment
):
    _, _, appt_id = bobs_appointment
    alice = make_user(full_name="Аліса")
    response = client.delete(f"/appointments/{appt_id}", headers=auth(alice))
    assert response.status_code == 403
    assert db.get(Appointment, appt_id) is not None  # запис Боба на місці


def test_patient_cannot_view_other_patient_appointment(
    client, make_user, bobs_appointment
):
    _, _, appt_id = bobs_appointment
    alice = make_user()
    response = client.get(f"/appointments/{appt_id}", headers=auth(alice))
    assert response.status_code == 403


def test_patient_cannot_cancel_other_appointment_via_web_form(
    client, db, make_user, bobs_appointment
):
    _, _, appt_id = bobs_appointment
    alice = make_user()
    client.post("/login", data={"email": alice.email, "password": DEFAULT_PASSWORD})
    response = client.post(f"/patient/cancel/{appt_id}", follow_redirects=False)
    assert response.status_code == 403
    assert db.get(Appointment, appt_id) is not None


def test_owner_can_view_and_cancel_own_appointment(client, bobs_appointment):
    bob, _, appt_id = bobs_appointment
    assert client.get(f"/appointments/{appt_id}", headers=auth(bob)).status_code == 200
    response = client.delete(f"/appointments/{appt_id}", headers=auth(bob))
    assert response.status_code == 204


def test_doctor_sees_only_appointments_to_themselves(
    client, db, make_doctor, bobs_appointment
):
    _, doctor, appt_id = bobs_appointment
    own_doctor = db.get(User, doctor.user_id)
    other_doctor = db.get(User, make_doctor("Невролог").user_id)
    url = f"/appointments/{appt_id}"
    assert client.get(url, headers=auth(own_doctor)).status_code == 200
    assert client.get(url, headers=auth(other_doctor)).status_code == 403


def test_doctor_cannot_cancel_patient_appointment(client, db, bobs_appointment):
    _, doctor, appt_id = bobs_appointment
    doctor_user = db.get(User, doctor.user_id)
    response = client.delete(f"/appointments/{appt_id}", headers=auth(doctor_user))
    assert response.status_code == 403


def test_admin_can_cancel_any_appointment(client, make_user, bobs_appointment):
    _, _, appt_id = bobs_appointment
    admin = make_user(Role.ADMIN)
    response = client.delete(f"/appointments/{appt_id}", headers=auth(admin))
    assert response.status_code == 204
