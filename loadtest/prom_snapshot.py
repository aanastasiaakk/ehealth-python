"""Знімок дашборду Grafana за період тесту, з даних Prometheus (ЛР8).

    python loadtest/prom_snapshot.py http://127.0.0.1:9090 <start_unix> <end_unix> \\
        docs/images/lab8-dashboard.png

Бере ВСІ запити панелей із config/grafana/dashboards/ehealth.json,
виконує їх у Prometheus (query_range) і малює ті самі панелі однією
картинкою. Це той самий дашборд, що в Grafana, лише статичний — для
звіту. Живий дашборд: docker compose --profile monitoring up -d →
http://127.0.0.1:3000.
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from make_report import AQUA, BLUE, INK, MUTED, ORANGE

COLORS = [BLUE, ORANGE, AQUA, MUTED]
DASHBOARD = (
    Path(__file__).resolve().parent.parent / "config/grafana/dashboards/ehealth.json"
)
SCALE = {"bytes": (1 / 2**20, "МБ"), "s": (1000, "мс")}


def query_range(prom: str, expr: str, start: int, end: int, step: int) -> list:
    params = urllib.parse.urlencode(
        {"query": expr, "start": start, "end": end, "step": step}
    )
    with urllib.request.urlopen(f"{prom}/api/v1/query_range?{params}") as resp:
        return json.load(resp)["data"]["result"]


def legend(template: str, labels: dict) -> str:
    for key, value in labels.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def main(prom: str, start: int, end: int, out: str) -> None:
    panels = json.loads(DASHBOARD.read_text())["panels"]
    panels = [p for p in panels if p["type"] == "timeseries"]
    step = max(15, (end - start) // 400)
    cols = 2
    rows = (len(panels) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, 3.2 * rows))
    for ax, panel in zip(axes.flat, panels, strict=False):
        unit = panel["fieldConfig"]["defaults"].get("unit", "")
        factor, label = SCALE.get(unit, (1, unit))
        i = 0
        for target in panel["targets"]:
            for series in query_range(prom, target["expr"], start, end, step):
                xs = [(float(t) - start) / 60 for t, _ in series["values"]]
                ys = [float(v) * factor for _, v in series["values"]]
                name = legend(target["legendFormat"], series["metric"])
                ax.plot(xs, ys, color=COLORS[i % len(COLORS)], lw=1.5, label=name)
                i += 1
        ax.set_title(panel["title"], loc="left", color=INK, fontsize=10)
        ax.set_ylabel(label if label not in ("short", "none") else "")
        ax.set_ylim(bottom=0)
        ax.legend(loc="upper right", frameon=False, fontsize=7, ncol=2)
        ax.set_xlabel("хвилини від старту")
    for ax in list(axes.flat)[len(panels) :]:
        ax.axis("off")
    when = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M")
    fig.suptitle(
        f"Дашборд «e-Health Booking: огляд» (дані Prometheus, старт {when})",
        x=0.01,
        ha="left",
        color=INK,
    )
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
