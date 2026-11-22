"""Створення та оновлення структури бази даних (ЛР5).

Раніше таблиці створювалися під час старту кожного процесу застосунку.
Коли копій застосунку кілька (Docker, ЛР6), вони стартують одночасно й
можуть «битися» за створення однієї таблиці. Тому структуру бази тепер
оновлює ОКРЕМИЙ одноразовий крок — сервіс `migrate` у docker-compose.yml
(скрипт `python -m scripts.migrate`), а застосунок стартує лише після
того, як цей крок успішно завершився.

`create_all` створює лише таблиці, яких ще немає, і НЕ додає нові
індекси до вже наявних таблиць. Тому індекси перевіряємо окремо:
`checkfirst=True` створює індекс, лише якщо його ще немає.
Функцію можна запускати скільки завгодно разів: нічого не дублюється.
"""

from sqlalchemy import Engine, text

from app import models  # noqa: F401  (реєструє всі таблиці в Base.metadata)
from app.database import Base

# Індекси, які прибрали з моделей, але які ще є в старих базах (ЛР7):
# ix_slots_doctor_id дублює індекс обмеження UNIQUE(doctor_id, starts_at)
# і лише сповільнює вставку слотів.
OBSOLETE_INDEXES = ["ix_slots_doctor_id"]


def apply_migrations(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        for name in OBSOLETE_INDEXES:
            conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
