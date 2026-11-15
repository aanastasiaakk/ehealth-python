"""Сценарій навантажувального тестування (ЛР4), інструмент — Locust.

Імітує ранковий пік о 8:00: люди відкривають сервіс, шукають лікаря,
дивляться вільні слоти, входять і записуються.

Два типи віртуальних користувачів:

1. Visitor (60 %) — анонімний відвідувач: головна сторінка, список
   спеціальностей, лікарів і вільних слотів. Найчастіший тип трафіку.
2. Patient (40 %) — пацієнт: входить (POST /auth/token), переглядає
   слоти, свої записи, записується на вільний слот і інколи скасовує.

Запуск (сервер sandbox має працювати на :8000):

    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000

і відкрий http://localhost:8089 (веб-інтерфейс Locust), або без інтерфейсу:

    locust -f loadtest/locustfile.py --host http://127.0.0.1:8000 \\
        --headless --csv loadtest/results/run --csv-full-history \\
        --html loadtest/results/report.html

Профіль навантаження задає клас StepLoadShape нижче (сходинки
25 → 50 → 100 → 150 → 200 користувачів). Змінити його можна змінними
оточення LT_STEPS (напр. "10,20,40") і LT_STEP_SECONDS.
"""

import os
import random

from locust import HttpUser, LoadTestShape, between, task

PATIENTS = int(os.getenv("LT_PATIENTS", "200"))
PASSWORD = os.getenv("LT_PASSWORD", "loadtest123")


class CatalogMixin:
    """Спільні дії: перегляд каталогу (найпопулярніші запити о 8:00)."""

    doctor_ids: list[int] = []

    def load_doctors(self) -> None:
        resp = self.client.get("/doctors", name="GET /doctors")
        if resp.ok:
            self.doctor_ids = [d["id"] for d in resp.json()]

    def view_slots(self) -> list[dict]:
        if not self.doctor_ids:
            self.load_doctors()
        if not self.doctor_ids:
            return []
        doctor_id = random.choice(self.doctor_ids)
        resp = self.client.get(
            f"/doctors/{doctor_id}/slots", name="GET /doctors/[id]/slots"
        )
        return resp.json() if resp.ok else []


class Visitor(CatalogMixin, HttpUser):
    """Анонімний відвідувач: лише читає каталог."""

    weight = 3
    wait_time = between(1, 3)  # «думає» 1–3 с між діями, як людина

    def on_start(self) -> None:
        self.client.get("/", name="GET / (page)")
        self.load_doctors()

    @task(3)
    def specialties(self) -> None:
        self.client.get("/specialties", name="GET /specialties")

    @task(3)
    def doctors(self) -> None:
        self.load_doctors()

    @task(5)
    def slots(self) -> None:
        self.view_slots()

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")


class Patient(CatalogMixin, HttpUser):
    """Пацієнт: входить і записується до лікаря."""

    weight = 2
    wait_time = between(1, 3)

    def on_start(self) -> None:
        email = f"loadtest{random.randint(1, PATIENTS)}@ehealth.ua"
        resp = self.client.post(
            "/auth/token",
            data={"username": email, "password": PASSWORD},
            name="POST /auth/token (login)",
        )
        token = resp.json().get("access_token") if resp.ok else None
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"
        self.load_doctors()

    @task(5)
    def slots(self) -> None:
        self.view_slots()

    @task(2)
    def my_appointments(self) -> None:
        self.client.get("/appointments/me", name="GET /appointments/me")

    @task(2)
    def book(self) -> None:
        free = self.view_slots()
        if not free:
            return
        # Як люди о 8:00: більшість хоче найближчий час, тому
        # беремо один із перших слотів — це створює конкуренцію за слот
        slot = random.choice(free[:5])
        with self.client.post(
            "/appointments",
            json={"slot_id": slot["id"]},
            name="POST /appointments (book)",
            catch_response=True,
        ) as resp:
            # 409 «слот щойно зайняли» — нормальний бізнес-результат,
            # а не помилка сервера: система правильно відмовила другому
            if resp.status_code in (201, 409):
                resp.success()

    @task(1)
    def cancel(self) -> None:
        resp = self.client.get("/appointments/me", name="GET /appointments/me")
        if not resp.ok or not resp.json():
            return
        appt = random.choice(resp.json())
        self.client.delete(
            f"/appointments/{appt['id']}", name="DELETE /appointments/[id]"
        )


class StepLoadShape(LoadTestShape):
    """Сходинковий профіль: на кожній сходинці тримаємо однакову кількість
    користувачів STEP_SECONDS секунд, потім додаємо ще. Так видно, після
    якої кількості користувачів затримка починає різко рости."""

    steps = [int(x) for x in os.getenv("LT_STEPS", "25,50,100,150,200").split(",")]
    step_seconds = int(os.getenv("LT_STEP_SECONDS", "45"))
    spawn_rate = float(os.getenv("LT_SPAWN_RATE", "5"))

    def tick(self):
        run_time = self.get_run_time()
        index = int(run_time // self.step_seconds)
        if index >= len(self.steps):
            return None  # тест завершено
        return self.steps[index], self.spawn_rate
