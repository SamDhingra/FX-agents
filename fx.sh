#!/usr/bin/env bash
# FX-Agents operations helper (same idea as jev.sh).  Usage: ./fx.sh <command>
set -euo pipefail
cd "$(dirname "$0")"
DC="docker compose"

need_env() {
  [[ -f .env ]] || { echo "No .env — run: cp .env.cloud.example .env && chmod 600 .env, then fill it in"; exit 1; }
  local perm; perm=$(stat -c %a .env 2>/dev/null || stat -f %Lp .env)
  [[ "$perm" == "600" ]] || { echo "Tightening .env permissions to 600"; chmod 600 .env; }
}

case "${1:-help}" in
  up)        need_env; mkdir -p data backups; $DC up -d --build; $DC ps ;;
  down)      $DC down ;;
  restart)   $DC restart "${2:-fxagents}" ;;
  logs)      $DC logs -f --tail=200 "${2:-fxagents}" ;;
  status)    $DC ps; echo; curl -fsS localhost:8088/healthz && echo " ← app healthy" || echo "app not answering on :8088" ;;
  update)    # pull new code (git) or after you rsync'd files, rebuild and restart only the app
             [[ -d .git ]] && git pull --ff-only || true
             $DC build fxagents && $DC up -d fxagents ;;
  test)      $DC run --rm --no-deps fxagents python -m pytest -q -p no:cacheprovider ;;
  check)     # read-only broker connection check (OANDA): account, instruments, prices. No orders.
             need_env; $DC run --rm --no-deps fxagents python check_oanda.py "${@:2}" ;;
  sim)       # quick end-to-end check without a broker (separate throwaway container)
             $DC run --rm --no-deps -e FX_MODE=sim -e FX_DB_PATH=/tmp/sim.sqlite fxagents \
               python main.py --no-dashboard --exit-after-sim --days "${2:-2}" ;;
  backup)    ts=$(date +%Y%m%d-%H%M); mkdir -p backups
             $DC exec -T fxagents python -c "import sqlite3; s=sqlite3.connect('/app/data/journal.sqlite'); d=sqlite3.connect('/app/data/backup.sqlite'); s.backup(d); d.close()"
             mv data/backup.sqlite "backups/journal-$ts.sqlite"; ls -lh backups | tail -5 ;;
  pause)     curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/pause; echo ;;
  resume)    curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/resume; echo ;;
  flatten)   read -rp "Flatten ALL positions and halt trading? [y/N] " a; [[ "$a" == y ]] || exit 0
             curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/flatten; echo ;;
  vnc)       echo "On your Mac:  ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem -L 5900:localhost:5900 ubuntu@<server-ip>"
             echo "then open vnc://localhost:5900 (needs VNC_SERVER_PASSWORD set in .env and ./fx.sh restart ib-gateway)" ;;
  *) cat <<USAGE
./fx.sh up | down | restart [svc] | logs [svc] | status | update | test | check | sim [days]
        backup | pause | resume | flatten | vnc
services: fxagents, cloudflared (+ ib-gateway when COMPOSE_PROFILES=ibkr)
USAGE
  ;;
esac
