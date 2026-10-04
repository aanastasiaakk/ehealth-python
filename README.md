# e-Health Booking

Сервіс електронного запису до державних лікарів.
Навчальний проєкт з дисципліни «Розробка високонавантажених систем на Python».

**Сценарій навантаження:** о 8:00 одночасно відкриваються нові слоти до
вузьких спеціалістів, тисячі пацієнтів намагаються записатися в ту саму
секунду, і двоє не повинні отримати один і той самий слот.

## Документація

- [Вибір предметної області та обґрунтування](docs/01-choice.md)
- [Архітектура системи, модель даних, схеми](docs/02-architecture.md)
- [Демонстрація pre-commit хуків](docs/03-pre-commit.md)

![Архітектура](docs/images/architecture.png)

## Технології

| Що | Навіщо |
|---|---|
| Python 3.10+, **FastAPI**, uvicorn | веб-фреймворк і сервер |
| **PostgreSQL 16** (у Docker) | реляційна база даних |
| SQLAlchemy 2 + psycopg 3 | робота з базою з Python |
| pydantic-settings | налаштування з `.env` |
| **ruff** | лінтер і форматер коду |
| **pre-commit** | автоматична перевірка коду перед кожним комітом |
| pytest | тести |

## Структура проєкту

```
ehealth-booking/
├── app/                    # КОД застосунку
│   ├── main.py             #   точка входу: створює FastAPI-застосунок
│   ├── config.py           #   налаштування (читає .env)
│   ├── database.py         #   підключення до PostgreSQL
│   ├── models.py           #   таблиці бази даних
│   └── api/
│       └── health.py       #   ендпоінти перевірки стану
├── tests/                  # ТЕСТИ
├── docs/                   # ДОКУМЕНТАЦІЯ
│   ├── diagrams/           #   вихідні файли схем (Graphviz .dot)
│   └── images/             #   згенеровані PNG-схеми
├── config/                 # КОНФІГУРАЦІЇ інфраструктури
│   └── nginx/nginx.conf    #   балансувальник (заплановано)
├── docker-compose.yml      # запуск PostgreSQL
├── .env.example            # шаблон змінних оточення
├── requirements.txt        # залежності застосунку
├── requirements-dev.txt    # залежності для розробки
├── pyproject.toml          # налаштування ruff і pytest
└── .pre-commit-config.yaml # налаштування pre-commit хуків
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

# 4. Сервер
uvicorn app.main:app --reload
```

Відкрий у браузері:
- http://127.0.0.1:8000/health/db — перевірка з'єднання з базою
- http://127.0.0.1:8000/docs — автоматична документація API (Swagger)

## Контроль якості коду

```bash
pre-commit install            # один раз: підключити хуки до Git
ruff check .                  # знайти помилки та порушення стилю
ruff format .                 # автоматично відформатувати код
pre-commit run --all-files    # прогнати всі перевірки вручну
pytest                        # запустити тести (потрібна запущена БД)
```
