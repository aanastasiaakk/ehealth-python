"""Налаштування застосунку.

Усі параметри (адреса бази даних, назва застосунку тощо) читаються
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    """Повертає налаштування. lru_cache гарантує, що .env читається один раз."""
    return Settings()
