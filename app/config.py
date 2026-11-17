"""Налаштування застосунку.

Усі параметри (адреса бази даних, секретний ключ тощо) читаються
зі змінних оточення або з файлу `.env`. Завдяки цьому паролі не
потрапляють у код і в Git, а для різних середовищ (локально, сервер)
достатньо змінити лише `.env`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Значення за замовчуванням використовуються, якщо в .env нічого не вказано
    app_name: str = "e-Health Booking"
    debug: bool = False

    # Формат: драйвер://користувач:пароль@хост:порт/назва_бази
    database_url: str = "postgresql+psycopg://ehealth:ehealth@localhost:5432/ehealth"

    # ---- Автентифікація (ЛР2) ----
    # Секретний ключ, яким підписуються JWT-токени.
    # На справжньому сервері має бути довгим випадковим рядком!
    # Згенерувати: python3 -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "dev-secret-key-change-me-in-production-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Перший адміністратор створюється скриптом scripts/seed.py
    admin_email: str = "admin@ehealth.ua"
    admin_password: str = "admin12345"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Повертає налаштування. lru_cache гарантує, що .env читається один раз."""
    return Settings()
