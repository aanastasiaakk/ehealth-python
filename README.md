# e-Health Booking

Сервіс електронного запису до державних лікарів.
Навчальний проєкт з дисципліни «Розробка високонавантажених систем на Python».

**Сценарій навантаження:** о 8:00 одночасно відкриваються нові слоти до
вузьких спеціалістів, тисячі пацієнтів намагаються записатися в ту саму
секунду, і двоє не повинні отримати один і той самий слот.

## Документація

- [1. Вибір предметної області та обґрунтування](docs/01-choice.md)
- [2. Архітектура системи, модель даних, схеми](docs/02-architecture.md)
- [3. Демонстрація pre-commit хуків](docs/03-pre-commit.md)
- [4. ЛР2: користувачі, ролі, розмежування прав](docs/04-lab2-auth.md)

![Архітектура](docs/images/architecture.png)

## Технології

| Що | Навіщо |
|---|---|
| Python 3.10+, **FastAPI**, uvicorn | веб-фреймворк і сервер |
| **PostgreSQL 16** (у Docker) | реляційна база даних |
| SQLAlchemy 2 + psycopg 3 | робота з базою з Python |
| pydantic-settings | налаштування з `.env` |
| PyJWT, bcrypt | токени входу та хешування паролів |
| Jinja2 | HTML-сторінки |
| **ruff**, **pre-commit** | контроль якості коду |
| pytest | тести |

## Структура проєкту

```
ehealth-booking/
├── app/                      # КОД застосунку
│   ├── main.py               #   точка входу: збирає всі частини разом
│   ├── config.py             #   налаштування (читає .env)
│   ├── database.py           #   підключення до PostgreSQL
│   ├── models.py             #   таблиці бази даних
│   ├── schemas.py            #   формати даних API (що приймаємо / віддаємо)
│   ├── security.py           #   паролі (bcrypt) і токени (JWT)
│   ├── dependencies.py       #   хто ти? що тобі можна? (401 / 403)
│   ├── services/             #   бізнес-логіка
│   │   ├── users.py          #     реєстрація, перевірка пароля
│   │   └── booking.py        #     запис, скасування, слоти
│   ├── api/                  #   JSON API
│   │   ├── auth.py           #     /auth/register, /auth/token
│   │   ├── users.py          #     /users/me, /users/{id}
│   │   ├── catalog.py        #     /specialties, /doctors, слоти
│   │   ├── appointments.py   #     /appointments
│   │   ├── doctor.py         #     /doctor/schedule
│   │   ├── admin.py          #     /admin/...
│   │   └── health.py         #     /health, /health/db
│   ├── web/pages.py          #   HTML-сторінки
│   └── templates/            #   HTML-шаблони
├── scripts/seed.py           # тестові дані для демонстрації
├── tests/                    # ТЕСТИ (86 шт.)
├── docs/                     # ДОКУМЕНТАЦІЯ та схеми
├── config/nginx/nginx.conf   # КОНФІГУРАЦІЇ (балансувальник, заплановано)
├── docker-compose.yml        # запуск PostgreSQL
├── .env.example              # шаблон налаштувань
├── requirements*.txt         # залежності
├── pyproject.toml            # налаштування ruff і pytest
└── .pre-commit-config.yaml   # pre-commit хуки
```

## Як запустити (macOS)

```bash
# 1. Віртуальне оточення та залежності
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Налаштування
cp .env.example .env

# 3. База даних (Docker Desktop має бути запущений)
docker compose up -d

# 4. Тестові дані: адмін, лікарі, пацієнт, слоти
python -m scripts.seed

# 5. Сервер
uvicorn app.main:app --reload
```

Відкрий http://127.0.0.1:8000 і увійди одним з демо-акаунтів:

| Роль | Email | Пароль |
|---|---|---|
| Адміністратор | admin@ehealth.ua | admin12345 |
| Лікар | kovalenko@ehealth.ua | doctor12345 |
| Пацієнт | patient@ehealth.ua | patient12345 |

Або зареєструй нового пацієнта на сторінці «Реєстрація».

API-документація: http://127.0.0.1:8000/docs (кнопка **Authorize** →
email у полі `username`, пароль → тепер можна викликати захищені методи).

## Основні маршрути API

| Метод і шлях | Хто має доступ |
|---|---|
| `POST /auth/register`, `POST /auth/token` | усі |
| `GET /specialties`, `GET /doctors`, `GET /doctors/{id}/slots` | усі |
| `GET /users/me` | будь-хто після входу |
| `GET/PATCH /users/{id}` | власник або адмін |
| `POST /appointments`, `GET /appointments/me` | пацієнт |
| `GET /appointments/{id}` | власник, його лікар, адмін |
| `DELETE /appointments/{id}` | власник або адмін |
| `GET /doctor/schedule` | лікар |
| `/admin/*` (статистика, користувачі, ролі, лікарі, слоти) | адмін |

## Тести та якість коду

```bash
pytest                          # усі тести (потрібна запущена БД)
pytest -v tests/test_access.py  # лише тести розмежування прав, детально
ruff check .                    # лінтер
ruff format .                   # форматування
pre-commit install              # один раз: підключити хуки до Git
pre-commit run --all-files      # прогнати всі перевірки вручну
```

## Якщо база з ЛР1 не хоче працювати

У ЛР2 змінилася структура таблиць (з'явилась `users`). Якщо в тебе
лишилась база з ЛР1, її простіше створити заново:

```bash
docker compose down -v   # -v видаляє і дані бази
docker compose up -d
python -m scripts.seed
```
