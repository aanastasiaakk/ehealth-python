"""Будує графіки й таблиці для звіту ЛР4 з CSV-файлів Locust і monitor.py.

    python loadtest/make_report.py loadtest/results/run      docs/images/lt-baseline
    python loadtest/make_report.py loadtest/results/stress   docs/images/lt-stress

Перший аргумент — префікс CSV Locust (--csv), другий — префікс для PNG.
Файл ресурсів шукається як <префікс>_resources.csv або resources.csv поруч.
Друкує Markdown-таблиці, які можна вставити у звіт.
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Палітра (перевірена на розрізнюваність для дальтоніків)
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 2,
    }
)


def num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_history(prefix: str, window: int = 5) -> list[dict]:
    """Рядки «Aggregated» з історії Locust.

    RPS і помилки/с рахуємо самі з приросту загальних лічильників
    (ковзне середнє за `window` с). Вбудований у Locust показник
    Requests/s «застигає» на останньому значенні, коли сервер узагалі
    перестає відповідати, і тоді вводить в оману.
    """
    rows = [
        r
        for r in csv.DictReader(open(f"{prefix}_stats_history.csv"))
        if r["Name"] == "Aggregated"
    ]
    t0 = int(rows[0]["Timestamp"])
    out = []
    for i, r in enumerate(rows):
        j = max(0, i - window)
        dt = max(1, int(r["Timestamp"]) - int(rows[j]["Timestamp"]))
        done = int(r["Total Request Count"]) - int(rows[j]["Total Request Count"])
        failed = int(r["Total Failure Count"]) - int(rows[j]["Total Failure Count"])
        out.append(
            {
                "t": int(r["Timestamp"]) - t0,
                "users": int(r["User Count"]),
                "rps": done / dt,
                "fails": failed / dt,
                # Перцентилі «0» означають, що за вікно не завершився жоден запит
                "p50": num(r["50%"]) or None,
                "p95": num(r["95%"]) or None,
            }
        )
    return out


def load_resources(prefix: str) -> list[dict]:
    path = Path(f"{prefix}_resources.csv")
    if not path.exists():
        path = Path(prefix).parent / "resources.csv"
    return [{k: float(v) for k, v in r.items()} for r in csv.DictReader(open(path))]


def label_end(ax, xs, ys, text, color, dy=0):
    """Підпис лінії праворуч від останньої точки (замість легенди-ключа)."""
    pts = [(x, y) for x, y in zip(xs, ys, strict=True) if y is not None]
    if pts:
        x, y = pts[-1]
        ax.annotate(
            text,
            (x, y),
            xytext=(6, dy),
            textcoords="offset points",
            color=INK,
            fontsize=9,
            va="center",
        )
        ax.plot([x], [y], "o", color=color, markersize=5)


def users_panel(ax, hist):
    ax.step([h["t"] for h in hist], [h["users"] for h in hist], color=MUTED, lw=1.5)
    ax.set_ylabel("користувачі")
    ax.set_xlabel("час від старту тесту, с")


def chart_latency(hist, out, title):
    fig, (ax, axu) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    xs = [h["t"] for h in hist]
    p50 = [h["p50"] for h in hist]
    p95 = [h["p95"] for h in hist]
    ax.plot(xs, p95, color=ORANGE, label="95-й перцентиль")
    ax.plot(xs, p50, color=BLUE, label="медіана (50%)")
    ax.set_yscale("log")
    ax.set_ylabel("час відповіді, мс (лог. шкала)")
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper right", frameon=False)
    users_panel(axu, hist)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def chart_throughput(hist, out, title):
    fig, (ax, axu) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    xs = [h["t"] for h in hist]
    rps = [h["rps"] for h in hist]
    fails = [h["fails"] for h in hist]
    ax.plot(xs, rps, color=BLUE, label="запити/с (RPS)")
    ax.plot(xs, fails, color=ORANGE, label="помилки/с")
    ax.set_ylabel("запитів за секунду")
    ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper left", frameon=False)
    users_panel(axu, hist)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def chart_resources(res, out, title):
    fig, (ax, axm) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 2]}
    )
    xs = [r["t"] for r in res]
    series = [
        ("cpu_total", BLUE, "уся машина (2 ядра)"),
        ("app_cpu", ORANGE, "застосунок (uvicorn)"),
        ("db_cpu", AQUA, "PostgreSQL"),
    ]
    for key, color, name in series:
        ax.plot(xs, [r[key] for r in res], color=color, label=name)
    ax.set_ylabel("CPU, % (100% = 1 ядро)")
    ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.legend(loc="upper left", frameon=False, ncol=3)
    axm.plot(xs, [r["app_mb"] for r in res], color=ORANGE, label="застосунок")
    axm.plot(xs, [r["db_mb"] for r in res], color=AQUA, label="PostgreSQL")
    label_end(axm, xs, [r["app_mb"] for r in res], "застосунок", ORANGE)
    label_end(axm, xs, [r["db_mb"] for r in res], "PostgreSQL", AQUA)
    axm.set_ylabel("RAM, МБ")
    axm.set_xlabel("час від старту моніторингу, с")
    axm.set_ylim(bottom=0)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def step_table(hist) -> str:
    """Метрики на кожній сходинці навантаження (без перших 10 с розгону)."""
    steps: dict[int, list[dict]] = {}
    for h in hist:
        if h["users"]:
            steps.setdefault(h["users"], []).append(h)
    # Лишаємо тільки «плато» — сходинки, що трималися >= 15 с (не розгін)
    steps = {u: rows for u, rows in steps.items() if len(rows) >= 15}
    lines = [
        "| Користувачів | RPS (сер.) | Медіана, мс | p95, мс | Помилки/с |",
        "|---:|---:|---:|---:|---:|",
    ]
    for users, rows in steps.items():
        steady = rows[10:] or rows

        def avg(key, rows=steady):
            vals = [r[key] for r in rows if r[key] is not None]
            return sum(vals) / len(vals) if vals else 0.0

        def med(key, rows=steady):
            vals = sorted(r[key] for r in rows if r[key] is not None)
            return vals[len(vals) // 2] if vals else None

        p50, p95 = med("p50"), med("p95")
        p50s = f"{p50:.0f}" if p50 else "—"
        p95s = f"{p95:.0f}" if p95 else "—"
        lines.append(
            f"| {users} | {avg('rps'):.1f} | {p50s} | {p95s} | {avg('fails'):.2f} |"
        )
    return "\n".join(lines)


def endpoint_table(prefix: str) -> str:
    lines = [
        "| Ендпоінт | Запитів | Помилки | RPS "
        "| Сер., мс | Min, мс | p95, мс | Max, мс |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in csv.DictReader(open(f"{prefix}_stats.csv")):
        reqs, fails = int(r["Request Count"]), int(r["Failure Count"])
        rate = 100 * fails / reqs if reqs else 0
        name = "**Разом**" if r["Name"] == "Aggregated" else f"`{r['Name']}`"
        lines.append(
            f"| {name} | {reqs} | {fails} ({rate:.2f}%) | {float(r['Requests/s']):.1f} "
            f"| {float(r['Average Response Time']):.0f} "
            f"| {float(r['Min Response Time']):.0f} | {r['95%']} "
            f"| {float(r['Max Response Time']):.0f} |"
        )
    return "\n".join(lines)


def resource_table(res) -> str:
    lines = ["| Показник | Середнє | Максимум |", "|---|---:|---:|"]
    names = {
        "cpu_total": "CPU машини, % (2 ядра = 100%)",
        "app_cpu": "CPU застосунку, % (100% = 1 ядро)",
        "db_cpu": "CPU PostgreSQL, %",
        "app_mb": "RAM застосунку, МБ",
        "db_mb": "RAM PostgreSQL, МБ",
    }
    for key, name in names.items():
        vals = [r[key] for r in res]
        lines.append(f"| {name} | {sum(vals) / len(vals):.1f} | {max(vals):.1f} |")
    return "\n".join(lines)


def main(prefix: str, out_prefix: str) -> None:
    hist = load_history(prefix)
    res = load_resources(prefix)
    Path(out_prefix).parent.mkdir(parents=True, exist_ok=True)
    chart_latency(hist, f"{out_prefix}-latency.png", "Час відповіді")
    chart_throughput(hist, f"{out_prefix}-throughput.png", "Пропускна здатність")
    chart_resources(res, f"{out_prefix}-resources.png", "Ресурси сервера")
    print("### По сходинках\n")
    print(step_table(hist))
    print("\n### По ендпоінтах\n")
    print(endpoint_table(prefix))
    print("\n### Ресурси\n")
    print(resource_table(res))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
