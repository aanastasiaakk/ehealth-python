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

from sqlalchemy import Engine

from app import models  # noqa: F401  (реєструє всі таблиці в Base.metadata)
from app.database import Base


def apply_migrations(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(bind=engine, checkfirst=True)
