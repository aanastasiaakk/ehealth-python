"""ЛР8: метрики для Prometheus і конфігурація моніторингу."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_metrics_endpoint_exposes_http_process_and_app_metrics(client):
    client.get("/specialties")
    text = client.get("/metrics").text
    for name in (
        "http_requests_total",
        "http_request_duration_highr_seconds_bucket",
        "process_resident_memory_bytes",
        "process_cpu_seconds_total",
        "ehealth_db_pool_checked_out",
        "ehealth_db_pool_open",
        "ehealth_requests_in_flight",
        "ehealth_requests_queued",
    ):
        assert name in text, name
    assert 'handler="/specialties"' in text


def test_metrics_endpoint_is_not_counted_and_not_in_api_docs(client):
    client.get("/metrics")
    assert 'handler="/metrics"' not in client.get("/metrics").text
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_metrics_are_hidden_from_the_outside_by_nginx():
    conf = (ROOT / "config/nginx/templates/default.conf.template").read_text()
    assert "location = /metrics" in conf


def test_monitoring_stack_is_an_optional_profile():
    services = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]
    for name in ("prometheus", "grafana", "postgres-exporter"):
        assert services[name]["profiles"] == ["monitoring"]
    assert services["grafana"]["ports"] == ["127.0.0.1:3000:3000"]


def test_prometheus_scrapes_every_replica():
    config = yaml.safe_load((ROOT / "config/prometheus/prometheus.yml").read_text())
    app_job = next(
        j for j in config["scrape_configs"] if j["job_name"] == "ehealth-app"
    )
    assert app_job["dns_sd_configs"][0]["names"] == ["app"]
    assert app_job["dns_sd_configs"][0]["port"] == 8000


def test_grafana_dashboard_uses_metrics_that_exist(client):
    exposed = client.get("/metrics").text
    dashboard = json.loads(
        (ROOT / "config/grafana/dashboards/ehealth.json").read_text()
    )
    exprs = [t["expr"] for p in dashboard["panels"] for t in p["targets"]]
    assert len(dashboard["panels"]) >= 10
    for metric in ("http_requests_total", "process_resident_memory_bytes"):
        assert any(metric in e for e in exprs)
    for expr in exprs:
        for token in expr.replace("(", " ").replace("{", " ").split():
            if token.startswith(("http_", "ehealth_", "process_")):
                assert token in exposed, token
