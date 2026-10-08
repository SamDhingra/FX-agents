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
             if [[ -d .git ]]; then git pull --ff-only || { echo; echo "git pull failed — nothing rebuilt (fix the above first)"; exit 1; }; fi
             $DC build fxagents && $DC up -d fxagents ;;
  localize)  # one-time: turn a full, hand-edited config into config.local.yaml (only your differences)
             #   ./fx.sh localize /tmp/server-config.yaml
             [[ -f "${2:-}" ]] || { echo "usage: ./fx.sh localize <copy of your full config.yaml>"; exit 1; }
             [[ -f config.local.yaml ]] && { echo "config.local.yaml already exists — edit it instead"; exit 1; }
             echo "Building image (quiet)..."; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/localize-build.log 2>&1 || { echo "build failed — see logs/localize-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_NO_LOCAL_CONFIG=1 -v "$(realpath "$2")":/tmp/mine.yaml:ro \
               fxagents python -m fxagents.config diff /tmp/mine.yaml </dev/null > config.local.yaml.tmp \
               || { rm -f config.local.yaml.tmp; echo "could not compare the configs (see above)"; exit 1; }
             mv config.local.yaml.tmp config.local.yaml
             echo "Wrote config.local.yaml:"; echo; cat config.local.yaml ;;
  test)      $DC build fxagents && $DC run --rm --no-deps -e FX_NO_LOCAL_CONFIG=1 fxagents python -m pytest -q -p no:cacheprovider ;;
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
  research)  # strategy research grid → playbook (≈10 min, low priority, own container). The running app picks
             # up the new playbook by itself within a few minutes.   ./fx.sh research [--tfs 3min 5min ...]
             need_env; mkdir -p logs; lf="logs/research-$(date +%Y%m%d-%H%M%S).log"
             echo "Building image (quiet)..."; BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/research-build.log 2>&1 || { echo "build failed — see logs/research-build.log"; exit 1; }
             nohup $DC run -T --rm --no-deps -e FX_MODE=sim fxagents nice -n 15 python run_research.py --workers 1 "${@:2}" \
               </dev/null >"$lf" 2>&1 &
             echo "Research started in the background (about 10 minutes). Results: dashboard → Playbook."
             echo "Follow the log with: tail -f $lf" ;;
  backup)    ts=$(date +%Y%m%d-%H%M); mkdir -p backups
             for j in journal journal_shadow; do
               $DC exec -T fxagents python -c "import os,sqlite3; p='/app/data/$j.sqlite'; os.path.exists(p) or exit(); s=sqlite3.connect(p); d=sqlite3.connect('/app/data/backup.sqlite'); s.backup(d); d.close()"
               [[ -f data/backup.sqlite ]] && mv data/backup.sqlite "backups/$j-$ts.sqlite"
             done; ls -lh backups | tail -6 ;;
  yeartest)  # every setup on N days of OANDA history + the weekly playbook replayed on it; publishes the report
             #   ./fx.sh yeartest [days=365] [--tfs 15min 1h] [--costs raw] [--classes …] [--symbols …] [--tag name]
             #   (background, ≈1 h for everything; progress published every 10 min)
             need_env; days="${2:-365}"; mkdir -p logs; lf="logs/yeartest-$(date +%Y%m%d-%H%M%S).log"
             [[ -f "$HOME/.ssh/fx_results" ]] || echo "note: results won't be published until you run ./fx.sh publish-setup once"
             echo "Building image (quiet)..."; BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/yeartest-build.log 2>&1 || { echo "build failed — see logs/yeartest-build.log"; exit 1; }
             nohup bash -c "
               $DC run -T --rm --no-deps -e FX_MODE=sim fxagents nice -n 15 python -m fxagents.year_test $days ${*:3} </dev/null &
               pid=\$!; while kill -0 \$pid 2>/dev/null; do sleep 600; ./fx.sh publish >/dev/null 2>&1; done
               wait \$pid; ./fx.sh publish" >"$lf" 2>&1 &
             echo "Started ($days days). Log: tail -f $lf"
             echo "The report is published to GitHub (branch 'results') as it progresses and when it finishes." ;;
  bbtest)    # Bollinger trend-continuation rules on 365 days (needs data/history_365d from ./fx.sh yeartest), both stop
             # readings × OANDA/raw costs; reports published to GitHub.   ./fx.sh bbtest [symbols…] (default NDQ US30 XAUUSD)
             need_env; syms="${*:2}"; syms="${syms:-NDQ US30 XAUUSD}"; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/bbtest-build.log 2>&1 || { echo "build failed — see logs/bbtest-build.log"; exit 1; }
             for mode in fixed trail; do for c in oanda raw; do
               extra=""; [[ $mode == trail ]] && extra="--trail-basis"
               $DC run --rm --no-deps -T -e FX_MODE=sim fxagents python -m fxagents.bb_trend $syms --days 365 --costs $c $extra \
                 --out "data/year_test/bb_${mode}_${c}" </dev/null | sed -n '/^## /,/^- no costs/p'
             done; done
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  newstrats) # the audit's 3 strategies (ORB / gap-fail / H1 trend) + controls on 365 days → data/year_test/astra_cfd, published
             # ./fx.sh newstrats 730 2025-10-07  → 730 days of history, tested only up to that date (the unseen earlier year)
             need_env; days="${2:-365}"; until="${3:-}"; tag="${days}d${until:+_to_$until}"; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/newstrats-build.log 2>&1 || { echo "build failed — see logs/newstrats-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.astra_cfd --days "$days" \
               ${until:+--until "$until"} --out "data/year_test/astra_cfd_${tag}" </dev/null | sed -n '/## Summary/,/^Verdict rule/p'
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  lab)       # strategy lab (same as the dashboard's Backtests → Strategy lab):
             #   ./fx.sh lab add trend_pullback --params '{"ema": 50}' --symbols XAUUSD NDQ --tfs 15min 30min --note "…"
             #   ./fx.sh lab run <id> [--days 365] · ./fx.sh lab list · ./fx.sh lab promote <id> · ./fx.sh lab reject <id>
             $DC exec -T fxagents nice -n 15 python -m fxagents.lab "${@:2}" ;;
  jevcheck)  # does Jev's grade predict results? every book's journal → data/year_test/jev_check, published to GitHub
             $DC exec -T fxagents python -m fxagents.jev_check | head -60
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  publish-setup) # one-time: a deploy key that can push ONLY to this repo, used to publish test reports
             KEY="$HOME/.ssh/fx_results"
             [[ -f "$KEY" ]] || ssh-keygen -q -t ed25519 -N "" -C "fx-agents results ($(hostname))" -f "$KEY"
             url=$(git remote get-url origin | sed -E 's#https://github.com/##; s#git@github.com:##; s#\.git$##')
             echo; echo "Add this key at https://github.com/$url/settings/keys/new"
             echo "  Title: fx-agents results · tick 'Allow write access' · Add key"; echo; cat "$KEY.pub"; echo ;;
  publish)   # push every data/year_test/<run>/{report.md,status.json,run.json,cells.csv,summary.json} to the 'results' branch
             KEY="$HOME/.ssh/fx_results"; R="$HOME/fx-results"
             [[ -f "$KEY" ]] || { echo "run ./fx.sh publish-setup first"; exit 1; }
             ls -d data/year_test/*/ >/dev/null 2>&1 || { echo "no test results yet"; exit 1; }
             url=$(git remote get-url origin | sed -E 's#https://github.com/##; s#git@github.com:##; s#\.git$##')
             export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
             if [[ ! -d "$R/.git" ]]; then git init -q -b results "$R"; git -C "$R" remote add origin "git@github.com:$url.git"; fi
             git -C "$R" fetch -q origin results 2>/dev/null && git -C "$R" reset -q --hard origin/results || true
             for d in data/year_test/*/; do                        # every run folder (365d, 365d_trend_raw, …)
               n=$(basename "$d"); mkdir -p "$R/year_test/$n"
               for f in report.md status.json run.json cells.csv summary.json; do [[ -f "$d$f" ]] && cp "$d$f" "$R/year_test/$n/"; done; cp "$d"report_w*.md "$R/year_test/$n/" 2>/dev/null || true
             done
             ls -t logs/yeartest-*.log 2>/dev/null | head -1 | xargs -r tail -n 80 > "$R/year_test/log_tail.txt"
             git -C "$R" add -A
             git -C "$R" -c user.name="fx-server" -c user.email="fx-server@localhost" commit -qm "test results $(date '+%F %R')" || true
             git -C "$R" push -q origin HEAD:results && echo "published: https://github.com/$url/tree/results/year_test" ;;
  setup-test) # backtest one setup on the cached history (own folder; research + playbook untouched)
             #   ./fx.sh setup-test london_breakout XAUUSD [--tfs 5min 15min]
             need_env; mkdir -p logs; echo "Building image (quiet)..."
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/setup-test-build.log 2>&1 || { echo "build failed — see logs/setup-test-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 15 python -m fxagents.setup_report "${@:2}" </dev/null ;;
  why)       # what each book saw and why it did/didn't trade in a time window (NY):  ./fx.sh why 20:00 23:59 2
             $DC exec -T fxagents python -m fxagents.why "${@:2}" ;;
  pause)     curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/pause; echo ;;
  resume)    curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/resume; echo ;;
  flatten)   read -rp "Flatten ALL positions and halt trading? [y/N] " a; [[ "$a" == y ]] || exit 0
             curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/flatten; echo ;;
  vnc)       echo "On your Mac:  ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem -L 5900:localhost:5900 ubuntu@<server-ip>"
             echo "then open vnc://localhost:5900 (needs VNC_SERVER_PASSWORD set in .env and ./fx.sh restart ib-gateway)" ;;
  *) cat <<USAGE
./fx.sh up | down | restart [svc] | logs [svc] | status | update | localize <file> | test | check | sim [days] | backtest [days] [opts] | research
        backup | why [from] [to] [days] | setup-test <setup> [symbols]
        yeartest [days] [opts] | bbtest [symbols] | newstrats [days] | jevcheck | lab … | publish-setup | publish | pause | resume | flatten | vnc
services: fxagents, cloudflared (+ ib-gateway when COMPOSE_PROFILES=ibkr)
USAGE
  ;;
esac
