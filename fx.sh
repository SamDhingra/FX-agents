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
  up)        need_env; mkdir -p data backups
             # the app runs as uid 1000 inside the container; a root-owned ./data (Docker creates it that way) breaks the journal
             [[ -w data ]] || sudo chown -R 1000:1000 data
             $DC up -d --build; $DC ps ;;
  down)      $DC down ;;
  restart)   $DC restart "${2:-fxagents}" ;;
  logs)      $DC logs -f --tail=200 "${2:-fxagents}" ;;
  status)    $DC ps; echo; curl -fsS localhost:8088/healthz && echo " ← app healthy" || echo "app not answering on :8088" ;;
  update)    # pull new code (git) or after you rsync'd files, rebuild and restart only the app
             [[ -d .git ]] && git pull --ff-only || true
             $DC build fxagents && $DC up -d fxagents ;;
  test)      $DC build fxagents && $DC run --rm --no-deps fxagents python -m pytest -q -p no:cacheprovider ;;
  check)     # read-only broker connection check (OANDA): account, instruments, prices. No orders.
             need_env; $DC build fxagents && $DC run --rm --no-deps fxagents python check_oanda.py "${@:2}" ;;
  sim)       # quick end-to-end check without a broker (separate throwaway container)
             $DC build fxagents && $DC run --rm --no-deps -e FX_MODE=sim -e FX_DB_PATH=/tmp/sim.sqlite fxagents \
               python main.py --no-dashboard --exit-after-sim --days "${2:-2}" ;;
  backtest)  # full-system replay on cached OANDA history, in its own low-priority container (live bot unaffected)
             #   ./fx.sh backtest 60 [--no-learner] [--jev live] [--name label]
             need_env; days="${2:-60}"; shift 2 2>/dev/null || shift $#; mkdir -p logs
             echo "Building image (quiet)..."; BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/backtest-build.log 2>&1 || { echo "build failed — see logs/backtest-build.log"; exit 1; }
             mkdir -p logs; lf="logs/backtest-$(date +%Y%m%d-%H%M%S).log"
             # no -d and no TTY: some compose versions fail "failed to get console" with run -d; nohup keeps it running after logout
             nohup $DC run -T --rm --no-deps -e FX_MODE=sim fxagents nice -n 15 python run_backtest.py --days "$days" "$@" \
               </dev/null >"$lf" 2>&1 &
             echo "Backtest started in the background. Progress and results: dashboard → Backtests."
             echo "Follow the log with: tail -f $lf" ;;
  backup)    ts=$(date +%Y%m%d-%H%M); mkdir -p backups
             for j in journal journal_shadow; do
               $DC exec -T fxagents python -c "import os,sqlite3; p='/app/data/$j.sqlite'; os.path.exists(p) or exit(); s=sqlite3.connect(p); d=sqlite3.connect('/app/data/backup.sqlite'); s.backup(d); d.close()"
               [[ -f data/backup.sqlite ]] && mv data/backup.sqlite "backups/$j-$ts.sqlite"
             done; ls -lh backups | tail -6 ;;
  pause)     curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/pause; echo ;;
  resume)    curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/resume; echo ;;
  flatten)   read -rp "Flatten ALL positions and halt trading? [y/N] " a; [[ "$a" == y ]] || exit 0
             curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/flatten; echo ;;
  vnc)       echo "On your Mac:  ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem -L 5900:localhost:5900 ubuntu@<server-ip>"
             echo "then open vnc://localhost:5900 (needs VNC_SERVER_PASSWORD set in .env and ./fx.sh restart ib-gateway)" ;;
  *) cat <<USAGE
./fx.sh up | down | restart [svc] | logs [svc] | status | update | test | check | sim [days] | backtest [days] [opts]
        backup | pause | resume | flatten | vnc
services: fxagents, cloudflared (+ ib-gateway when COMPOSE_PROFILES=ibkr)
USAGE
  ;;
esac
