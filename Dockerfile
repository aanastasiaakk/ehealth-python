# Образ бекенду e-Health Booking (ЛР5).
#
# Багатоетапне збирання (multi-stage build):
#   1) builder — «майстерня»: повний образ python:3.12 з компіляторами
#      (gcc, заголовки бібліотек). Тут встановлюємо залежності у
#      віртуальне оточення /opt/venv.
#   2) runtime — «готовий продукт»: легкий python:3.12-slim, куди
#      копіюємо ЛИШЕ /opt/venv і код. Компілятори, кеш pip і тимчасові
#      файли встановлення лишаються в першому етапі й у фінальний образ
#      не потрапляють.
#
# Зібрати й запустити все разом:  docker compose up --build
# Лише зібрати образ:             docker build -t ehealth-booking .

# ---------- Етап 1: встановлення залежностей ----------
FROM python:3.12 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Спочатку копіюємо ЛИШЕ список залежностей. Docker кешує кожен крок:
# поки requirements.txt не змінився, pip install не виконується повторно,
# навіть якщо змінився код. Збирання займає секунди, а не хвилини.
COPY requirements.txt .
RUN pip install -r requirements.txt


# ---------- Етап 2: фінальний легкий образ ----------
FROM python:3.12-slim AS runtime

# PYTHONDONTWRITEBYTECODE — не створювати файли .pyc у контейнері;
# PYTHONUNBUFFERED — логи одразу потрапляють у `docker compose logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Застосунок працює НЕ від root: якщо зловмисник знайде вразливість,
# він отримає права звичайного користувача, а не адміністратора контейнера.
RUN useradd --create-home --uid 1000 appuser

# Робоча директорія: тут лежить код, звідси виконуються команди
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts

USER appuser
EXPOSE 8000

# Docker сам перевіряє, чи живий застосунок. Статус видно в
# `docker compose ps`: starting → healthy (або unhealthy).
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

# Команда запуску сервера. --host 0.0.0.0 — приймати запити ззовні
# контейнера (за замовчуванням uvicorn слухає лише сам себе).
# --proxy-headers — довіряти заголовкам X-Forwarded-* від Nginx (ЛР6).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
