"""Метрики для Prometheus і Grafana (ЛР8).

Кожна репліка віддає на /metrics (формат Prometheus):

- стандартні метрики HTTP (бібліотека prometheus-fastapi-instrumentator):
  http_requests_total{handler, method, status} — лічильник запитів;
  http_request_duration_highr_seconds_bucket — гістограма часу відповіді
  (з неї рахуються p50/p95/p99);
  http_requests_inprogress — скільки запитів обробляється зараз;
- метрики процесу Python: process_cpu_seconds_total (CPU),
  process_resident_memory_bytes (RAM) — за ними видно витоки пам'яті;
- власні метрики застосунку (нижче): зайняті з'єднання пулу БД і стан
  «турнікета» запитів з ЛР7 — за ними видно накопичення незакритих
  з'єднань.

Prometheus опитує /metrics кожної репліки напряму (через внутрішню мережу
Docker). Ззовні, через Nginx, /metrics недоступний.
"""

from prometheus_client import Gauge
from prometheus_fastapi_instrumentator import Instrumentator

from app.database import engine
from app.limiter import STATE

DB_POOL_CHECKED_OUT = Gauge(
    "ehealth_db_pool_checked_out", "Database connections currently in use"
)
DB_POOL_CHECKED_OUT.set_function(lambda: engine.pool.checkedout())

DB_POOL_OPEN = Gauge(
    "ehealth_db_pool_open", "Database connections currently open (in use + idle)"
)
DB_POOL_OPEN.set_function(lambda: engine.pool.checkedout() + engine.pool.checkedin())

REQUESTS_IN_FLIGHT = Gauge(
    "ehealth_requests_in_flight", "Requests being processed (concurrency limiter)"
)
REQUESTS_IN_FLIGHT.set_function(lambda: STATE["in_flight"])

REQUESTS_QUEUED = Gauge(
    "ehealth_requests_queued", "Requests waiting in the concurrency limiter queue"
)
REQUESTS_QUEUED.set_function(lambda: STATE["queued"])


def setup_metrics(app) -> None:
    Instrumentator(
        excluded_handlers=["/metrics"],
        should_instrument_requests_inprogress=True,
    ).instrument(app).expose(app, include_in_schema=False)
