"""Налаштування застосунку для різних середовищ (ЛР3).

Середовище обирається змінною оточення APP_ENV:

    APP_ENV=sandbox     → читається файл .env.sandbox     (тестове середовище)
    APP_ENV=production  → читається файл .env.production  (робоче середовище)

У коді НЕМАЄ жодних паролів, ключів чи адрес баз даних: обов'язкові
параметри (DATABASE_URL, SECRET_KEY) не мають значень за замовчуванням.
Якщо їх забули вказати, застосунок навіть не запуститься і чітко скаже,
чого бракує, замість того щоб тихо працювати з «дефолтним» паролем.

Пріоритет джерел (від найвищого):
1. справжні змінні оточення (так налаштовують сервер і CI);
2. файл .env.<середовище>;
3. значення за замовчуванням нижче (лише для НЕсекретних параметрів).
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["sandbox", "production"]


def current_env() -> str:
    return os.getenv("APP_ENV", "sandbox").strip().lower()


class Settings(BaseSettings):
    app_env: Environment = "sandbox"
    app_name: str = "e-Health Booking"

    # Режим відладки: детальні помилки зі стектрейсом і SQL-запити в консолі.
    # У production ЗАВЖДИ False (перевіряється нижче).
    debug: bool = False
    # Swagger-документація /docs. У production її краще ховати,
    # щоб не показувати всім структуру API.
    docs_enabled: bool = True

    # ---- Секрети: обов'язкові, без значень за замовчуванням ----
    database_url: str
    secret_key: str = Field(min_length=32)

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Пул з'єднань до БД (у production можна збільшити)
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Створювати таблиці під час старту застосунку (зручно для локального
    # запуску). У Docker це робить окремий сервіс `migrate`, тому там
    # AUTO_MIGRATE=false (ЛР5).
    auto_migrate: bool = True

    # Перший адміністратор (створюється скриптом scripts/seed.py)
    admin_email: str | None = None
    admin_password: str | None = None

    model_config = SettingsConfigDict(
        env_file=f".env.{current_env()}",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        """Захист від небезпечних налаштувань у робочому середовищі."""
        if not self.is_production:
            return self
        problems = []
        if self.debug:
            problems.append("DEBUG must be false in production")
        if "sandbox" in self.database_url:
            problems.append("production must not use the sandbox database")
        key = self.secret_key.lower()
        if "change-me" in key or key.startswith(("dev-", "sandbox-")):
            problems.append("SECRET_KEY looks like a placeholder, generate a real one")
        if problems:
            raise ValueError("Unsafe production config: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    """Повертає налаштування. lru_cache гарантує, що файл читається один раз."""
    return Settings(app_env=current_env())
