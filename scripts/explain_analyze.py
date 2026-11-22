"""EXPLAIN ANALYZE найчастішого запиту ДО і ПІСЛЯ зміни індексів (ЛР7).

    APP_ENV=sandbox python -m scripts.explain_analyze > docs/evidence/lab7-explain.txt

Демо-база маленька (2 560 слотів), і на ній будь-який план виконується
за частки мілісекунди. Тому скрипт створює ОКРЕМУ тимчасову базу
`<sandbox-база>_explain` з обсягом, як у реальної поліклініки за рік:
200 лікарів × 395 днів × 32 слоти ≈ 2,5 млн слотів (рік історії + місяць
наперед; 85 % минулих і 30 % майбутніх слотів зайняті). Робочі бази
не змінюються. Працює лише в sandbox.

Порівнюються два стани таблиці slots:
  ДО    — індекси ЛР2–ЛР6: UNIQUE(doctor_id, starts_at), ix_slots_doctor_id,
          ix_slots_starts_at;
  ПІСЛЯ — ЛР7: замість ix_slots_doctor_id частковий індекс
          ix_slots_free_by_doctor (doctor_id, starts_at) WHERE is_available.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import get_settings

DOCTORS, DAYS_BACK, DAYS_AHEAD, PER_DAY = 200, 365, 30, 32

# Те саме, що робить booking.list_free_slots (вільні слоти лікаря на 14 днів)
FREE_SLOTS = """
SELECT id, doctor_id, starts_at, is_available FROM slots
WHERE doctor_id = 42 AND is_available AND starts_at > now()
  AND starts_at < now() + interval '14 days'
ORDER BY starts_at LIMIT 200
"""
# Статистика адміністратора: скільки вільних майбутніх слотів
FREE_COUNT = "SELECT count(*) FROM slots WHERE is_available AND starts_at > now()"

SCHEMA = """
DROP TABLE IF EXISTS slots;
CREATE TABLE slots (
    id serial PRIMARY KEY,
    doctor_id integer NOT NULL,
    starts_at timestamptz NOT NULL,
    is_available boolean NOT NULL,
    UNIQUE (doctor_id, starts_at)
);
INSERT INTO slots (doctor_id, starts_at, is_available)
SELECT d,
       date_trunc('day', now()) + make_interval(days => day)
         + interval '8 hours' + make_interval(mins => 15 * s),
       CASE WHEN day < 0 THEN random() > 0.85 ELSE random() > 0.30 END
FROM generate_series(1, :doctors) d,
     generate_series(-:back, :ahead - 1) day,
     generate_series(0, :per_day - 1) s;
"""

BEFORE = """
DROP INDEX IF EXISTS ix_slots_free_by_doctor;
CREATE INDEX IF NOT EXISTS ix_slots_doctor_id ON slots (doctor_id);
CREATE INDEX IF NOT EXISTS ix_slots_starts_at ON slots (starts_at);
"""
AFTER = """
DROP INDEX IF EXISTS ix_slots_doctor_id;
CREATE INDEX IF NOT EXISTS ix_slots_free_by_doctor
    ON slots (doctor_id, starts_at) WHERE is_available;
"""


def run_sql(conn, script: str, **params) -> None:
    for statement in script.split(";"):
        if statement.strip():
            conn.execute(text(statement), params)


def explain(conn, title: str, query: str) -> None:
    print(f"--- {title}")
    print(query.strip())
    plan = conn.execute(text(f"EXPLAIN (ANALYZE, BUFFERS) {query}")).scalars()
    for line in plan:
        print("    " + line)
    print()


def index_sizes(conn) -> None:
    rows = conn.execute(
        text(
            "SELECT indexrelname, pg_size_pretty(pg_relation_size(indexrelid)) "
            "FROM pg_stat_user_indexes WHERE relname = 'slots' ORDER BY 1"
        )
    )
    print("Індекси таблиці slots:")
    for name, size in rows:
        print(f"    {name:40} {size}")
    print()


def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("explain_analyze працює лише в sandbox")
    base = make_url(settings.database_url)
    url = base.set(database=f"{base.database}_explain")

    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}"'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        run_sql(
            conn,
            SCHEMA,
            doctors=DOCTORS,
            back=DAYS_BACK,
            ahead=DAYS_AHEAD,
            per_day=PER_DAY,
        )
        total, free = conn.execute(
            text("SELECT count(*), count(*) FILTER (WHERE is_available) FROM slots")
        ).one()
        print(f"Тестові дані: {total:,} слотів, з них вільних {free:,}\n")

        for title, script in (("ДО (індекси ЛР2–ЛР6)", BEFORE), ("ПІСЛЯ (ЛР7)", AFTER)):
            run_sql(conn, script)
            conn.execute(text("VACUUM ANALYZE slots"))
            print(f"=================== {title} ===================\n")
            index_sizes(conn)
            # Перший прогін прогріває кеш PostgreSQL, міряємо другий
            conn.execute(text(FREE_SLOTS))
            explain(conn, "Вільні слоти лікаря (GET /doctors/{id}/slots)", FREE_SLOTS)
            conn.execute(text(FREE_COUNT))
            explain(conn, "Кількість вільних слотів (статистика адміна)", FREE_COUNT)
    engine.dispose()

    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}"'))
    admin.dispose()


if __name__ == "__main__":
    main()
