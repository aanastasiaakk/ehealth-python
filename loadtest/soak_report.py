"""Звіт тривалого тесту стабільності (Soak), ЛР8.

    python loadtest/soak_report.py loadtest/results/lab8/soak docs/images/lab8-soak

Читає CSV Locust (<префікс>_stats.csv, _stats_history.csv) і моніторингу
(<префікс>_resources.csv), будує графіки за весь тест і друкує:
- підсумковий протокол (RPS, Avg/Min/Max, p50/p95/p99, Error Rate, CPU, RAM);
- таблицю по 10-хвилинних відрізках (чи є деградація з часом);
- нахил трендів RAM і p95 (лінійна регресія): чи росте пам'ять і затримка.
"""

import csv
import sys

import matplotlib.pyplot as plt
from make_report import AQUA, BLUE, INK, MUTED, ORANGE, load_history

WINDOW = 600  # с — розмір відрізка в таблиці деградації
WARMUP = 120  # с — розгін і прогрів не враховуємо в трендах


def load_resources(prefix: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(open(f"{prefix}_resources.csv")):
        rows.append(
            {k: float(v) if v not in ("", "None") else None for k, v in r.items()}
        )
    return rows


def slope_per_hour(xs: list[float], ys: list[float]) -> float:
    """Нахил прямої найменших квадратів, одиниць за годину."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den * 3600 if den else 0.0


def avg(values) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


def protocol(prefix: str, hist: list[dict], res: list[dict]) -> str:
    total = next(
        r
        for r in csv.DictReader(open(f"{prefix}_stats.csv"))
        if r["Name"] == "Aggregated"
    )
    reqs, fails = int(total["Request Count"]), int(total["Failure Count"])
    steady = [h for h in hist if h["t"] >= WARMUP]
    steady_res = [r for r in res if r["t"] >= WARMUP]
    duration = hist[-1]["t"]
    cpu = [r["cpu_total"] for r in steady_res]
    sut_cpu = [
        (r["app_cpu"] + r["db_cpu"] + r["nginx_cpu"] + r["redis_cpu"]) / 2
        for r in steady_res
    ]
    rows = [
        ("Тривалість", f"{duration / 60:.0f} хв"),
        ("Запитів усього", f"{reqs:,}".replace(",", " ")),
        ("RPS (середній на плато)", f"{avg(h['rps'] for h in steady):.1f}"),
        ("Latency Avg", f"{float(total['Average Response Time']):.1f} мс"),
        ("Latency Min", f"{float(total['Min Response Time']):.1f} мс"),
        ("Latency Max", f"{float(total['Max Response Time']):.0f} мс"),
        ("Latency p50", f"{total['50%']} мс"),
        ("Latency p95", f"{total['95%']} мс"),
        ("Latency p99", f"{total['99%']} мс"),
        ("Error Rate", f"{100 * fails / reqs:.3f} % ({fails} з {reqs})"),
        ("CPU машини, сер. / макс.", f"{avg(cpu):.1f} % / {max(cpu):.1f} %"),
        (
            "CPU системи (app+nginx+БД+Redis), сер. / макс.",
            f"{avg(sut_cpu):.1f} % / {max(sut_cpu):.1f} %",
        ),
        (
            "RAM машини, сер. / макс.",
            f"{avg(r['ram_percent'] for r in steady_res):.1f} % / "
            f"{max(r['ram_percent'] for r in steady_res):.1f} %",
        ),
        (
            "RAM застосунку (3 репліки), початок → кінець",
            f"{steady_res[0]['app_mb']:.0f} → {res[-1]['app_mb']:.0f} МБ",
        ),
    ]
    lines = ["| Метрика | Значення |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def windows_table(hist: list[dict], res: list[dict]) -> str:
    lines = [
        "| Відрізок, хв | RPS | Медіана, мс | p95, мс | Помилки/с "
        "| CPU машини, % | RAM app, МБ | З'єднань з БД |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    end = hist[-1]["t"]
    start = 0
    while start < end:
        h = [x for x in hist if start <= x["t"] < start + WINDOW]
        r = [x for x in res if start <= x["t"] < start + WINDOW]
        p95 = sorted(x["p95"] for x in h if x["p95"])
        p50 = sorted(x["p50"] for x in h if x["p50"])
        conns = avg(x.get("db_connections") for x in r)
        lines.append(
            f"| {start // 60}–{min(start + WINDOW, end) // 60} "
            f"| {avg(x['rps'] for x in h):.1f} "
            f"| {p50[len(p50) // 2] if p50 else 0:.0f} "
            f"| {p95[len(p95) // 2] if p95 else 0:.0f} "
            f"| {avg(x['fails'] for x in h):.3f} "
            f"| {avg(x['cpu_total'] for x in r):.1f} "
            f"| {avg(x['app_mb'] for x in r):.0f} "
            f"| {conns:.0f} |"
        )
        start += WINDOW
    return "\n".join(lines)


def trends(hist: list[dict], res: list[dict]) -> str:
    steady_res = [r for r in res if r["t"] >= WARMUP]
    steady = [h for h in hist if h["t"] >= WARMUP and h["p95"]]
    items = [
        (
            "RAM застосунку",
            slope_per_hour(
                [r["t"] for r in steady_res], [r["app_mb"] for r in steady_res]
            ),
            "МБ/год",
        ),
        (
            "RAM PostgreSQL",
            slope_per_hour(
                [r["t"] for r in steady_res], [r["db_mb"] for r in steady_res]
            ),
            "МБ/год",
        ),
        (
            "p95 затримки",
            slope_per_hour([h["t"] for h in steady], [h["p95"] for h in steady]),
            "мс/год",
        ),
        (
            "RPS",
            slope_per_hour([h["t"] for h in steady], [h["rps"] for h in steady]),
            "RPS/год",
        ),
    ]
    conns = [r for r in steady_res if r.get("db_connections") is not None]
    if conns:
        items.append(
            (
                "З'єднання з БД",
                slope_per_hour(
                    [r["t"] for r in conns], [r["db_connections"] for r in conns]
                ),
                "з'єднань/год",
            )
        )
    lines = ["| Показник | Нахил тренду |", "|---|---:|"]
    lines += [f"| {name} | {value:+.2f} {unit} |" for name, value, unit in items]
    return "\n".join(lines)


def rolling(values: list, size: int = 30) -> list:
    out = []
    for i in range(len(values)):
        chunk = [v for v in values[max(0, i - size + 1) : i + 1] if v is not None]
        out.append(sum(chunk) / len(chunk) if chunk else None)
    return out


def charts(hist: list[dict], res: list[dict], out_prefix: str) -> None:
    minutes = [h["t"] / 60 for h in hist]

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    ax.plot(minutes, rolling([h["p95"] for h in hist]), color=ORANGE, label="p95")
    ax.plot(minutes, rolling([h["p50"] for h in hist]), color=BLUE, label="медіана")
    ax.set_ylabel("мс (ковзне сер. 30 с)")
    ax.set_ylim(bottom=0)
    ax.set_title("Час відповіді за весь тест", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper right", frameon=False)
    ax2.plot(minutes, rolling([h["rps"] for h in hist]), color=BLUE, label="RPS")
    ax2.plot(
        minutes, rolling([h["fails"] for h in hist]), color=ORANGE, label="помилки/с"
    )
    ax2.set_ylabel("запитів/с")
    ax2.set_ylim(bottom=0)
    ax2.set_xlabel("хвилини від старту")
    ax2.set_title("Пропускна здатність", loc="left", color=INK, fontsize=12)
    ax2.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(f"{out_prefix}-latency-throughput.png", dpi=130)
    plt.close(fig)

    rmin = [r["t"] / 60 for r in res]
    fig, (ax, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
    ax.plot(
        rmin, rolling([r["cpu_total"] for r in res]), color=MUTED, label="уся машина"
    )
    ax.plot(
        rmin,
        rolling([r["app_cpu"] / 2 for r in res]),
        color=ORANGE,
        label="застосунок (3 репліки)",
    )
    ax.plot(
        rmin,
        rolling([r["locust_cpu"] / 2 for r in res]),
        color=AQUA,
        label="Locust (генератор)",
    )
    ax.plot(
        rmin, rolling([r["db_cpu"] / 2 for r in res]), color=BLUE, label="PostgreSQL"
    )
    ax.axhline(80, color=INK, lw=1, ls="--")
    ax.annotate("межа 80 %", (rmin[0], 80), xytext=(4, 4), textcoords="offset points")
    ax.set_ylabel("CPU, % від 2 ядер")
    ax.set_ylim(0, 100)
    ax.set_title("CPU (ковзне сер. 30 с)", loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper right", frameon=False, ncol=4, fontsize=8)
    ax2.plot(rmin, [r["app_mb"] for r in res], color=ORANGE, label="застосунок")
    ax2.plot(rmin, [r["redis_mb"] for r in res], color=AQUA, label="Redis")
    ax2.plot(rmin, [r["nginx_mb"] for r in res], color=BLUE, label="Nginx")
    ax2.set_ylabel("RAM, МБ")
    ax2.set_ylim(bottom=0)
    ax2.set_title("Пам'ять процесів (витоки)", loc="left", color=INK, fontsize=12)
    ax2.legend(loc="center right", frameon=False)
    if res[0].get("db_connections") is not None:
        ax3.plot(rmin, [r["db_connections"] for r in res], color=BLUE)
    ax3.set_ylabel("з'єднань")
    ax3.set_ylim(bottom=0)
    ax3.set_xlabel("хвилини від старту")
    ax3.set_title("З'єднання з PostgreSQL", loc="left", color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(f"{out_prefix}-resources.png", dpi=130)
    plt.close(fig)


def main(prefix: str, out_prefix: str) -> None:
    hist = load_history(prefix)
    res = load_resources(prefix)
    charts(hist, res, out_prefix)
    print("### Підсумковий протокол\n")
    print(protocol(prefix, hist, res))
    print("\n### По 10-хвилинних відрізках\n")
    print(windows_table(hist, res))
    print("\n### Тренди (без перших 2 хв)\n")
    print(trends(hist, res))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
