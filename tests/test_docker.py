"""ЛР5: міграції та конфігурація Docker.

Самі контейнери тут не запускаються (це робить окрема задача CI
«Docker»), а перевіряється, що файли налаштовані правильно.
"""

from pathlib import Path

import yaml
from sqlalchemy import inspect, text

from app.database import engine
from app.migrations import apply_migrations

ROOT = Path(__file__).resolve().parent.parent


def _index_names(table: str) -> set[str]:
    return {ix["name"] for ix in inspect(engine).get_indexes(table)}


def test_migrations_can_run_many_times():
    apply_migrations(engine)
    apply_migrations(engine)  # повторний запуск нічого не ламає


def test_migrations_restore_missing_index():
    # create_all не додає індекси до існуючих таблиць — apply_migrations додає
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX ix_slots_starts_at"))
    assert "ix_slots_starts_at" not in _index_names("slots")
    apply_migrations(engine)
    assert "ix_slots_starts_at" in _index_names("slots")


def _compose(name: str = "docker-compose.yml") -> dict:
    return yaml.safe_load((ROOT / name).read_text())


def test_compose_start_order_uses_healthchecks():
    services = _compose()["services"]
    assert "healthcheck" in services["db-sandbox"]
    app_deps = services["app"]["depends_on"]
    assert app_deps["db-sandbox"]["condition"] == "service_healthy"
    assert app_deps["migrate"]["condition"] == "service_completed_successfully"


def test_compose_database_data_survives_in_volumes():
    compose = _compose()
    for db in ("db-sandbox", "db-production"):
        volume = compose["services"][db]["volumes"][0].split(":")[0]
        assert volume in compose["volumes"]


def test_compose_database_is_not_on_public_network():
    services = _compose()["services"]
    assert services["db-sandbox"]["networks"] == ["backend"]
    assert set(services["app"]["networks"]) == {"backend", "frontend"}


def test_dockerignore_keeps_secrets_out_of_image():
    ignored = (ROOT / ".dockerignore").read_text().split()
    for pattern in (".env", ".env.*", ".git", "__pycache__"):
        assert pattern in ignored


def test_dockerfile_is_multi_stage_and_not_root():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert dockerfile.count("FROM ") == 2
    assert "COPY --from=builder" in dockerfile
    assert "USER appuser" in dockerfile


def test_dev_override_enables_hot_reload():
    app = _compose("docker-compose.dev.yml")["services"]["app"]
    assert "--reload" in app["command"]
    assert any(v.startswith("./app:") for v in app["volumes"])
