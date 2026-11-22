#!/usr/bin/env bash
# ЛР6: перевірка балансування навантаження однією командою.
#
#   bash scripts/lab6_balancer_check.sh
#
# Що робить (і друкує результат кожного кроку):
#   1. піднімає систему: Nginx + 3 репліки застосунку + база
#   2. робить 15 запитів поспіль і показує, яка репліка відповіла (Round Robin)
#   3. зупиняє одну репліку і показує, що всі запити й далі успішні,
#      але йдуть лише на 2 «здорові» репліки
#   4. запускає репліку знову — вона повертається в ротацію
#   5. перемикає алгоритм на least_conn і повторює запити
#
# Вивід також зберігається у файл docs/evidence/lab6-balancer-check.txt
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p docs/evidence
exec > >(tee docs/evidence/lab6-balancer-check.txt) 2>&1

URL=http://127.0.0.1:8080
step() { printf '\n===== %s =====\n' "$1"; }
wait_ready() {
  for _ in $(seq 1 60); do
    curl -fsS "$URL/health/db" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "Система не відповіла за 2 хв. Логи: docker compose logs nginx app"
  exit 1
}
# N запитів поспіль: номер, HTTP-код, репліка (X-Instance) і її IP (X-Upstream)
requests() {
  for i in $(seq 1 "$1"); do
    curl -s -o /dev/null -D - "$URL/health" | tr -d '\r' | awk -v n="$i" '
      /^HTTP/ {code=$2} /^x-instance:/ {inst=$2} /^[Xx]-[Uu]pstream:/ {up=$2}
      END {printf "запит %2d  HTTP %s  репліка %s  (%s)\n", n, code, inst, up}'
  done
}
summary() { awk '{print $6}' | sort | uniq -c | sed 's/^/   /'; }

step "1. Система: Nginx + 3 репліки"
docker compose up -d --build || exit 1
wait_ready
docker compose ps

step "2. Round Robin: 15 запитів поспіль"
requests 15 | tee /tmp/lab6_rr.txt
echo "Скільки запитів обробила кожна репліка:"
summary < /tmp/lab6_rr.txt

step "3. Збій: зупиняємо одну репліку"
VICTIM=$(docker compose ps -q app | sed -n 2p)
VICTIM_NAME=$(docker inspect -f '{{.Config.Hostname}}' "$VICTIM")
echo "docker stop $VICTIM_NAME"
docker stop "$VICTIM" >/dev/null
docker compose ps app
echo
requests 12 | tee /tmp/lab6_fail.txt
echo "Скільки запитів обробила кожна репліка (зупиненої $VICTIM_NAME немає):"
summary < /tmp/lab6_fail.txt
echo
echo "Як Nginx помітив збій (лог помилок Nginx):"
docker compose logs --no-log-prefix nginx 2>&1 | grep -iE "failed|timed out|unreachable|refused" | tail -n 3 || echo "   (у лозі немає помилок: Nginx прибрав репліку зі списку за даними DNS ще до запиту)"

step "4. Відновлення: запускаємо репліку знову"
docker start "$VICTIM" >/dev/null
echo "Чекаємо, поки репліка стане healthy і мине fail_timeout (15 с)..."
sleep 15
requests 9 | tee /tmp/lab6_back.txt
summary < /tmp/lab6_back.txt

step "5. Інший алгоритм: least_conn"
NGINX_LB=least_conn docker compose up -d nginx
wait_ready
docker compose exec nginx grep -E "include|server app" /etc/nginx/conf.d/default.conf
requests 9

step "Повертаємо Round Robin"
docker compose up -d nginx
wait_ready
echo "Готово. Лог балансувальника: docker compose logs nginx"
