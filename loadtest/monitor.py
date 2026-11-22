"""Збирає завантаження CPU і RAM сервера під час тесту (ЛР4, ЛР6–ЛР8).

Раз на секунду записує в CSV:
- загальне CPU і RAM машини (у МБ і у %);
- CPU і RAM груп процесів: застосунок (усі процеси uvicorn разом),
  база даних (postgres), балансувальник (nginx), кеш (redis-server)
  і сам генератор навантаження (locust).

ЛР8: якщо задано MONITOR_DSN (адреса бази), ще й кількість з'єднань
до бази (pg_stat_activity) — за нею видно «витік» з'єднань.

Запуск у сусідньому терміналі ПЕРЕД стартом Locust:

    python loadtest/monitor.py loadtest/results/resources.csv
    MONITOR_DSN=postgresql://user:pass@localhost:5433/db \
        python loadtest/monitor.py loadtest/results/soak_resources.csv

Зупинка: Ctrl + C.
"""

import csv
import os
import sys
import time

import psutil

# Група → підрядок у командному рядку процесу
GROUPS = {
    "app": "uvicorn",
    "db": "postgres",
    "nginx": "nginx",
    "redis": "redis-server",
    # Генератор навантаження теж на цій машині: видно, чи не він «стеля»
    "locust": "locust",
}


# Сторонні інструменти моніторингу не зараховуємо до груп вище
IGNORE = ("exporter", "prometheus", "monitor.py")


def matches(proc: psutil.Process, *names: str) -> bool:
    try:
        cmd = " ".join(proc.cmdline()).lower()
        if any(word in cmd for word in IGNORE):
            return False
        return any(name in cmd for name in names)
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def group_usage(procs: list[psutil.Process]) -> tuple[float, float]:
    cpu = mem = 0.0
    for proc in procs:
        try:
            cpu += proc.cpu_percent(None)
            mem += proc.memory_info().rss / 2**20
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return cpu, mem


def db_connections_counter():
    """Функція, що повертає кількість з'єднань до бази (або None)."""
    dsn = os.getenv("MONITOR_DSN")
    if not dsn:
        return lambda: None
    import psycopg

    conn = psycopg.connect(dsn, autocommit=True)
    query = "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    return lambda: conn.execute(query).fetchone()[0]


def main(path: str) -> None:
    count_db_connections = db_connections_counter()
    psutil.cpu_percent(None)
    start = time.time()
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        header = ["t", "cpu_total", "ram_used_mb", "ram_percent"]
        for group in GROUPS:
            header += [f"{group}_cpu", f"{group}_mb"]
        header.append("db_connections")
        writer.writerow(header)
        while True:
            # Список процесів оновлюємо щоразу: uvicorn/postgres можуть
            # створювати нові процеси під навантаженням
            current = list(psutil.process_iter())
            procs = {
                group: [p for p in current if matches(p, name)]
                for group, name in GROUPS.items()
            }
            for group_procs in procs.values():
                for proc in group_procs:
                    try:
                        proc.cpu_percent(None)
                    except psutil.Error:
                        pass
            time.sleep(1)
            memory = psutil.virtual_memory()
            row = [
                round(time.time() - start),
                psutil.cpu_percent(None),
                round(memory.used / 2**20),
                memory.percent,
            ]
            for group_procs in procs.values():
                cpu, mb = group_usage(group_procs)
                row += [round(cpu, 1), round(mb)]
            row.append(count_db_connections())
            writer.writerow(row)
            fh.flush()


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "resources.csv")
    except KeyboardInterrupt:
        pass
