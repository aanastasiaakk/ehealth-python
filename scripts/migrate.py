"""Оновлює структуру бази даних (таблиці та індекси).

    APP_ENV=sandbox python -m scripts.migrate

У Docker цей скрипт запускає одноразовий сервіс `migrate` перед
стартом застосунку (див. docker-compose.yml).
"""

from app.config import get_settings
from app.database import engine
from app.migrations import apply_migrations


def main() -> None:
    print(f"Середовище: {get_settings().app_env}. Оновлюю структуру бази...")
    apply_migrations(engine)
    print("Структура бази актуальна.")


if __name__ == "__main__":
    main()
