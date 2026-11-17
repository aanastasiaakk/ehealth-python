"""Збирає завантаження CPU і RAM сервера під час тесту (ЛР4).

Раз на секунду записує в CSV:
- загальне CPU і RAM машини;
- CPU і RAM процесів застосунку (uvicorn) і бази даних (postgres).

Запуск у сусідньому терміналі ПЕРЕД стартом Locust:

    python loadtest/monitor.py loadtest/results/resources.csv

Зупинка: Ctrl + C.
"""

import csv
import sys
import time

import psutil


def matches(proc: psutil.Process, *names: str) -> bool:
    try:
        cmd = " ".join(proc.cmdline()).lower()
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


def main(path: str) -> None:
    psutil.cpu_percent(None)
    start = time.time()
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["t", "cpu_total", "ram_used_mb", "app_cpu", "app_mb", "db_cpu", "db_mb"]
        )
        app, db = [], []
        while True:
            # Список процесів оновлюємо щоразу: uvicorn/postgres можуть
            # створювати нові процеси під навантаженням
            current = list(psutil.process_iter())
            app = [p for p in current if matches(p, "uvicorn")]
            db = [p for p in current if matches(p, "postgres")]
            for proc in app + db:
                try:
                    proc.cpu_percent(None)
                except psutil.Error:
                    pass
            time.sleep(1)
            app_cpu, app_mb = group_usage(app)
            db_cpu, db_mb = group_usage(db)
            writer.writerow(
                [
                    round(time.time() - start),
                    psutil.cpu_percent(None),
                    round(psutil.virtual_memory().used / 2**20),
                    round(app_cpu, 1),
                    round(app_mb),
                    round(db_cpu, 1),
                    round(db_mb),
                ]
            )
            fh.flush()


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "resources.csv")
    except KeyboardInterrupt:
        pass
