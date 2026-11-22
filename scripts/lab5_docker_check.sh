#!/usr/bin/env bash
# ЛР5: повна перевірка контейнеризації однією командою.
#
#   bash scripts/lab5_docker_check.sh
#
# Що робить (і друкує результат кожного кроку):
#   1. збирає образ і піднімає всю систему: docker compose up -d --build
#   2. показує стан сервісів (healthy / exited (0))
#   3. перевіряє API і базу в контейнері (/health, /health/db, /doctors)
#   4. перевіряє, що дані бази ПЕРЕЖИВАЮТЬ зупинку контейнерів (volume):
#      реєструє пацієнта → docker compose down → up → входить ним же
#   5. порівнює розмір образу: етап builder (як було б без multi-stage)
#      проти фінального runtime
#
# Вивід також зберігається у файл docs/evidence/lab5-docker-check.txt
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/evidence
exec > >(tee docs/evidence/lab5-docker-check.txt) 2>&1

URL=http://127.0.0.1:8080
step() { printf '\n===== %s =====\n' "$1"; }
wait_app() {
  for _ in $(seq 1 60); do
    curl -fsS "$URL/health/db" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "Застосунок не відповів за 2 хв. Логи: docker compose logs app"
  exit 1
}

step "1. docker compose up -d --build"
docker compose up -d --build || exit 1
wait_app

step "2. Стан сервісів"
docker compose ps -a

step "3. API і база в контейнері"
echo "GET /health    → $(curl -fsS $URL/health)"
echo "GET /health/db → $(curl -fsS $URL/health/db)"
echo "GET /doctors   → $(curl -fsS $URL/doctors | head -c 160)..."
echo
echo "Логи міграцій (сервіс migrate):"
docker compose logs --no-log-prefix migrate | tail -n 12

step "4. Дані переживають перезапуск (Docker volume)"
EMAIL="volume-check-$(date +%s)@ehealth.ua"
curl -fsS -X POST "$URL/auth/register" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"volume12345\",\"full_name\":\"Volume Check\"}" \
  >/dev/null && echo "Зареєстровано: $EMAIL"
echo "docker compose down (контейнери ВИДАЛЯЮТЬСЯ, том лишається)..."
docker compose down
docker volume ls | grep pgdata
echo "docker compose up -d ..."
docker compose up -d
wait_app
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$URL/auth/token" \
  -d "username=$EMAIL&password=volume12345")
echo "Вхід тим самим користувачем після перезапуску: HTTP $CODE (200 = дані збереглися)"

step "5. Розмір образу: multi-stage"
docker build -q --target builder -t ehealth-booking:builder-stage . >/dev/null
docker image ls --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' | grep -E 'REPOSITORY|ehealth-booking'
echo
echo "builder-stage — так виглядав би образ БЕЗ multi-stage (повний python + компілятори)"
echo "latest        — фінальний образ, який реально запускається"

step "Готово"
echo "Застосунок у Docker: $URL"
