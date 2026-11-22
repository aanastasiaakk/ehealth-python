"""Порівняльні графіки й таблиці кількох прогонів Locust (ЛР6, ЛР7).

    python loadtest/compare.py docs/images/lab7-stress \\
        "До оптимізації=loadtest/results/lab7/before_stress" \\
        "Після оптимізації=loadtest/results/lab7/after_stress"

Перший аргумент — префікс для PNG, далі пари «Назва=префікс CSV».
Будує два графіки (пропускна здатність і 95-й перцентиль затримки в
часі, лінії прогонів одна поверх одної) і друкує Markdown-таблиці:
по сходинках навантаження і підсумок за весь прогін.
"""

import csv
import sys

import matplotlib.pyplot as plt
from make_report import BLUE, INK, MUTED, ORANGE, load_history

AQUA = "#1baf7a"
COLORS = [BLUE, ORANGE, AQUA]


def load_run(prefix: str) -> dict:
    hist = load_history(prefix)
    total = next(
        r
        for r in csv.DictReader(open(f"{prefix}_stats.csv"))
        if r["Name"] == "Aggregated"
    )
    return {"hist": hist, "total": total}


def steps(hist: list[dict]) -> dict[int, dict]:
    """Середні значення на кожній сходинці (без перших 10 с розгону)."""
    grouped: dict[int, list[dict]] = {}
    for h in hist:
        if h["users"]:
            grouped.setdefault(h["users"], []).append(h)
    out = {}
    for users, rows in grouped.items():
        if len(rows) < 15:  # розгін між сходинками, а не плато
            continue
        steady = rows[10:]
        p95 = sorted(r["p95"] for r in steady if r["p95"])
        out[users] = {
            "rps": sum(r["rps"] for r in steady) / len(steady),
            "fails": sum(r["fails"] for r in steady) / len(steady),
            "p95": p95[len(p95) // 2] if p95 else None,
        }
    return out


def chart(runs: dict[str, dict], key: str, out: str, title: str, ylabel: str):
    fig, (ax, axu) = plt.subplots(
        2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    for (name, run), color in zip(runs.items(), COLORS, strict=False):
        xs = [h["t"] for h in run["hist"]]
        ax.plot(xs, [h[key] for h in run["hist"]], color=color, label=name)
    if key == "p95":
        ax.set_yscale("log")
    else:
        ax.set_ylim(bottom=0)
    ax.set_title(title, loc="left", color=INK, fontsize=12)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper left", frameon=False, labelcolor=MUTED)
    # Під графіком — профіль навантаження (однаковий для всіх прогонів)
    first = next(iter(runs.values()))["hist"]
    axu.step([h["t"] for h in first], [h["users"] for h in first], color=MUTED, lw=1.5)
    axu.set_ylabel("користувачі")
    axu.set_xlabel("час від старту тесту, с")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def fmt(value, pattern="{:.0f}") -> str:
    return pattern.format(value) if value is not None else "—"


def step_table(runs: dict[str, dict]) -> str:
    per_run = {name: steps(run["hist"]) for name, run in runs.items()}
    users = sorted({u for s in per_run.values() for u in s})
    names = list(runs)
    head = "| Користувачів | " + " | ".join(
        f"RPS: {n} | p95, мс: {n} | помилки/с: {n}" for n in names
    )
    lines = [head + " |", "|---:" + "|---:" * 3 * len(names) + "|"]
    for u in users:
        cells = []
        for n in names:
            s = per_run[n].get(u)
            cells += (
                [fmt(s["rps"], "{:.1f}"), fmt(s["p95"]), fmt(s["fails"], "{:.2f}")]
                if s
                else ["—"] * 3
            )
        lines.append(f"| {u} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def total_table(runs: dict[str, dict]) -> str:
    lines = [
        "| Прогін | Запитів | Помилки | Сер., мс | Медіана, мс | p95, мс "
        "| p99, мс | Max, мс |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, run in runs.items():
        t = run["total"]
        reqs, fails = int(t["Request Count"]), int(t["Failure Count"])
        rate = 100 * fails / reqs if reqs else 0
        lines.append(
            f"| {name} | {reqs} | {fails} ({rate:.2f}%) "
            f"| {float(t['Average Response Time']):.0f} | {t['50%']} | {t['95%']} "
            f"| {t['99%']} | {float(t['Max Response Time']):.0f} |"
        )
    return "\n".join(lines)


def main(out_prefix: str, specs: list[str]) -> None:
    runs = {}
    for spec in specs:
        name, prefix = spec.split("=", 1)
        runs[name] = load_run(prefix)
    chart(
        runs,
        "rps",
        f"{out_prefix}-throughput.png",
        "Пропускна здатність",
        "запитів за секунду",
    )
    chart(
        runs,
        "p95",
        f"{out_prefix}-latency.png",
        "95-й перцентиль часу відповіді",
        "мс (лог. шкала)",
    )
    print("### По сходинках\n")
    print(step_table(runs))
    print("\n### За весь прогін\n")
    print(total_table(runs))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
