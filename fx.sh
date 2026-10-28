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
             $DC build fxagents && mkdir -p candles_key && { [[ -f "$HOME/.ssh/fx_results" ]] && install -m 600 "$HOME/.ssh/fx_results" candles_key/key || echo "note: candles won't be pushed until you run ./fx.sh publish-setup once"; }
             $DC up -d fxagents fxbt fxcandles ;;
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
  astra15)   # Astra's frozen 15 strategies (fxagents/astra15, unchanged) on OANDA history; needs data/history_730d
             # (from ./fx.sh newstrats 730 …). Two runs: the unseen period before Astra's data, and the same dates as Astra's.
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/astra15-build.log 2>&1 || { echo "build failed — see logs/astra15-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 15 python -m fxagents.astra15_oanda --days 730 \
               --until 2026-03-25 --label "unseen: before Astra's data" --out data/year_test/astra15_unseen </dev/null | grep -v candidates
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 15 python -m fxagents.astra15_oanda --days 730 \
               --from 2026-02-01 --until 2026-09-25 --splits 2026-06-30 2026-07-31 2026-09-25 \
               --label "same dates as Astra's vendor data" --out data/year_test/astra15_overlap </dev/null | grep -v candidates
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  export)    # OANDA bid/ask candles → data/export/<name>/<SYM>_<GRAN>.csv.gz + manifest.json (market prices only)
             #   ./fx.sh export --name dev_m1 --gran M1 --from 2024-10-01 --until 2026-09-30
             #   ./fx.sh export --name dev_d --gran D --from 2016-01-01 --until 2026-09-30 --symbols XAUUSD NDQ WTICO_USD …
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/export-build.log 2>&1 || { echo "build failed — see logs/export-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents python -m fxagents.export_history "${@:2}" </dev/null ;;
  mgmtreplay) # the bot's REAL trades of the last N days replayed under other management rules (read-only)
             #   ./fx.sh mgmtreplay [days=7] [--books live playbook …]  → data/year_test/mgmt_replay/report.md
             $DC exec -T fxagents python -m fxagents.mgmt_replay --days "${2:-7}" "${@:3}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  reconcile) # practice-account journal vs OANDA's own trade records (read-only; R only, no amounts) — audit F9
             #   ./fx.sh reconcile [days=14]  → data/year_test/reconcile/report.md
             $DC exec -T fxagents python -m fxagents.reconcile --days "${2:-14}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  repair)    # journal rows stuck at 'open' (lost in old restarts): dry run; ./fx.sh repair --apply to fix (backs up first)
             $DC exec -T fxagents python -m fxagents.journal_repair "${@:2}" </dev/null ;;
  holdout)   # score a frozen outside strategy package on a holdout export, sandboxed: no network, no .env/token,
             # read-only package and data. ./fx.sh holdout <package dir> <export name> <tag>
             #   e.g. ./fx.sh holdout research/astra_v1 holdout_m1 astra_v1   → data/year_test/holdout_astra_v1, published
             pkg="${2:?package dir}"; set_="${3:?export name under data/export}"; tag="${4:?tag}"
             [[ -f "$pkg/backtest.py" ]] || { echo "no backtest.py in $pkg"; exit 1; }
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             out="data/year_test/holdout_$tag"; mkdir -p "$out"; chmod 777 "$out"
             mkdir -p logs; BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/holdout-build.log 2>&1 || { echo "build failed — see logs/holdout-build.log"; exit 1; }
             docker run --rm --network none --memory 1500m --user "$(id -u):$(id -g)" --entrypoint python \
               -v "$(realpath "$pkg"):/pkg:ro" -v "$(realpath "data/export/$set_"):/data:ro" -v "$(realpath "$out"):/out" \
               -w /pkg fx-agents:latest backtest.py --data-dir /data --out-dir /out </dev/null 2>&1 | tail -40
             ( cd "$out" && sha256sum "$(realpath "$OLDPWD/$pkg")"/*.py > package_sha256.txt 2>/dev/null; \
               { echo "# Holdout score: $tag on $set_"; echo; echo '```'; head -40 summary.csv 2>/dev/null; echo '```'; } > report.md
               cp summary.csv cells.csv 2>/dev/null || true )
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  rule)      # test a simple frozen rule (fxagents/simple_rules.py) on an export: ./fx.sh rule ema21_rsi55 dev_m1
             need_env; mkdir -p logs; r="${2:?rule}"; set_="${3:-dev_m1}"
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/rule-build.log 2>&1 || { echo "build failed — see logs/rule-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.simple_rules "$r" --data "$set_" \
               --out "data/year_test/${r}_${set_}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  regimecheck) # chop/trend routing rule (fxagents/regime.py) checked on a year test's trades: ./fx.sh regimecheck [365d_p2] [365]
             need_env; mkdir -p logs; run="${2:-365d_p2}"; days="${3:-365}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/regime-build.log 2>&1 || { echo "build failed — see logs/regime-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.regime_check --run "$run" --days "$days" \
               --out "data/year_test/regime_${run}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  cisd)      # CISD rule sets A/B (+ coin-flip control) on a bid/ask export: ./fx.sh cisd [dev_m1]
             need_env; mkdir -p logs; set_="${2:-dev_m1}"
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/cisd-build.log 2>&1 || { echo "build failed — see logs/cisd-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.cisd_test --data "$set_" \
               --out "data/year_test/cisd_${set_}" </dev/null | grep -v "^  " ; tail -n +5 "data/year_test/cisd_${set_}/report.md" | head -3
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  breakout)  # Gold Breakout 15M (WillyAlgoTrader) defaults + earlier closes, with coin-flip control: ./fx.sh breakout [dev_m1|holdout_m1]
             # holdout runs score only the frozen dev passers (fxagents/breakout_test.py FROZEN)
             need_env; mkdir -p logs; set_="${2:-dev_m1}"
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/breakout-build.log 2>&1 || { echo "build failed — see logs/breakout-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.breakout_test --data "$set_" \
               $([[ "$set_" == holdout* ]] && echo --frozen) --out "data/year_test/breakout_${set_}" </dev/null | grep -v "^  "
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  gemini)    # Gemini's three gold rules (fxagents/gemini_test.py) with their controls: ./fx.sh gemini [dev_m1|holdout_m1] [lny,xeq,pmrd]
             # holdout runs score only the rules in PASSED_DEV, unchanged
             need_env; mkdir -p logs; set_="${2:-dev_m1}"; only="${3:-lny,xeq,pmrd}"
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/gemini-build.log 2>&1 || { echo "build failed — see logs/gemini-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.gemini_test --data "$set_" --only "$only" \
               $([[ "$set_" == holdout* ]] && echo --frozen) --out "data/year_test/gemini_${set_}" </dev/null | grep -v "^  "
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  gemsmc)    # Gemini's rebuilt SMC/ICT/DTFX gold setups (revision 2), out-of-sample design (fxagents/gemini_smc.py): ./fx.sh gemsmc [bos,wick,sbs]
             # judged on dev_m1 before 2025-10-08 + all of holdout_m1; Oct 2025–Sep 2026 is in-sample and only shown
             need_env; mkdir -p logs; only="${2:-bos,wick,sbs}"
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/gemsmc-build.log 2>&1 || { echo "build failed — see logs/gemsmc-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.gemini_smc --data dev_m1,holdout_m1 \
               --only "$only" --out data/year_test/gemini_smc </dev/null | grep -v "^  "
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  pattest)   # chart patterns as entry signals, stage 2 (fxagents/pattern_test.py): ./fx.sh pattest [dev_m1]
             # XAUUSD, NDQ, US30 on 15m + 1h, real bid/ask, coin-flip control; holdout only via --frozen for passers
             need_env; mkdir -p logs; set_="${2:-dev_m1}"
             [[ -d "data/export/$set_" ]] || { echo "no data/export/$set_ — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/pattest-build.log 2>&1 || { echo "build failed — see logs/pattest-build.log"; exit 1; }
             extra=""; [[ "$set_" == holdout* ]] && extra="--frozen"
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.pattern_test --data "$set_" $extra \
               --out "data/year_test/patterns_$set_" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  patgold)   # pre-registered: chart patterns on gold 1h, all families as one rule — dev shown, HOLDOUT judged (once)
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/patgold-build.log 2>&1 || { echo "build failed — see logs/patgold-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.pattern_test --prereg gold_1h \
               --data dev_m1,holdout_m1 --out data/year_test/patterns_gold_1h </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  scalp)     # gold scalp: 15m EMA20/50 trend → 5m breakout + retest → 3m confirmation (fxagents/gold_scalp.py): ./fx.sh scalp
             need_env; mkdir -p logs
             [[ -d data/export/dev_m1 ]] || { echo "no data/export/dev_m1 — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/scalp-build.log 2>&1 || { echo "build failed — see logs/scalp-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.gold_scalp --data dev_m1 \
               --out data/year_test/gold_scalp_dev_m1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  sweepvwap) # gold scalp #2: liquidity sweep + VWAP, 15m → 5m → 3m, 08:00–11:30 NY (fxagents/sweep_vwap.py): ./fx.sh sweepvwap
             need_env; mkdir -p logs
             [[ -d data/export/dev_m1 ]] || { echo "no data/export/dev_m1 — run ./fx.sh export first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/sweepvwap-build.log 2>&1 || { echo "build failed — see logs/sweepvwap-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.sweep_vwap --data dev_m1 \
               --out data/year_test/sweep_vwap_dev_m1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  sweeponly) # pre-registered: sweep + VWAP gold scalp WITHOUT the EMA fallback — dev shown, HOLDOUT judged (once)
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/sweeponly-build.log 2>&1 || { echo "build failed — see logs/sweeponly-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.sweep_vwap --sweep-only \
               --data dev_m1,holdout_m1 --out data/year_test/sweep_only_gold </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  reclaimv2) # author's sweep_reclaim_v2 (fxagents/sweep_reclaim_v2.py): step 1 on the seen sets (dev_m1 + holdout_m1);
             # only if that passes is the untouched 2016–2020 export (old_m1) opened and judged, once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/reclaimv2-build.log 2>&1 || { echo "build failed — see logs/reclaimv2-build.log"; exit 1; }
             if [[ ! -f data/export/old_m1/XAUUSD_M1.csv.gz ]]; then
               echo "exporting untouched 2016–2020 gold (OANDA bid/ask, one-time, ~10–20 min)…"
               $DC run --rm --no-deps -T -e FX_MODE=sim fxagents python -m fxagents.export_history --name old_m1 --gran M1 \
                 --from 2016-01-01 --until 2020-12-31 --symbols XAUUSD </dev/null || { echo "export failed"; exit 1; }
             fi
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.sweep_reclaim_v2 \
               --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/sweep_reclaim_v2 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  smcidm)    # author's SMC inducement trap → 5m CHoCH → 3m OB limit (fxagents/smc_idm.py): step 1 on dev_m1 + holdout_m1;
             # only a pass opens the untouched 2016–2020 export (old_m1) and judges it once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/smcidm-build.log 2>&1 || { echo "build failed — see logs/smcidm-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.smc_idm \
               --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/smc_idm </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  volbrk)    # author's vol_breakout_v1 (fxagents/vol_breakout.py): step 1 on dev_m1 + holdout_m1; only a pass opens the
             # untouched 2016–2020 export (old_m1) and judges it once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/volbrk-build.log 2>&1 || { echo "build failed — see logs/volbrk-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.vol_breakout \
               --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/vol_breakout_v1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  h4don)     # author's h4_donchian_trend_v1 (fxagents/h4_donchian.py): step 1 on dev_m1 + holdout_m1; only a pass opens
             # the untouched 2016–2020 export (old_m1) and judges it once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/h4don-build.log 2>&1 || { echo "build failed — see logs/h4don-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.h4_donchian \
               --known dev_m1,holdout_m1 --judge old_m1 --out data/year_test/h4_donchian_trend_v1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  bt)        # backtest engine (fxagents/bt): ./fx.sh bt btplugins/<file>.py [seen] [SYMBOL] — the vault opens via the ledger only
             need_env; mkdir -p logs
             [[ -f "${2:-}" ]] || { echo "usage: ./fx.sh bt btplugins/<file>.py [dataset] [SYMBOL]"; ls btplugins/*.py 2>/dev/null; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/bt-build.log 2>&1 || { echo "build failed — see logs/bt-build.log"; exit 1; }
             n_=$(basename "$2" .py)
             $DC run --rm --no-deps -T fxbt nice -n 10 python -m fxagents.bt run "$2" --data "${3:-seen}" \
               ${4:+--symbol "$4"} --out "data/year_test/bt_${n_}_${3:-seen}${4:+_$4}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  btsetups)  # queue the bot's own ICT/SMC/DTFX/Stoic setups (one plugin each in btplugins/) on one instrument for the
             # fxbt worker: ./fx.sh btsetups BTCUSD ["5min 15min"] [setup …] — or run any single one from the page
             sym_="${2:?usage: ./fx.sh btsetups SYMBOL [\"5min 15min\"] [setup ...]}"; tfs_="${3:-5min 15min}"
             sts_="${*:4}"; [[ -n "$sts_" ]] || sts_="$(grep -l 'fxagents.bt.botsetups' btplugins/*.py | xargs -n1 basename | sed 's/\.py$//')"
             $DC up -d fxbt >/dev/null 2>&1
             for tf_ in $tfs_; do for st_ in $sts_; do
               $DC exec -T fxbt python -m fxagents.bt run "btplugins/$st_.py" --queue --symbol "$sym_" --set "tf=\"$tf_\"" </dev/null
             done; done ;;
  bthtf)     # Sam's three HTF point-of-interest models (fxagents/bt/htf_poi.py) × both entries × NDQ + US30 → 12 runs
             # queued for the fxbt worker on the seen data; results on the Backtest page
             $DC up -d fxbt >/dev/null 2>&1
             for sym_ in NDQ US30; do for p_ in htf_a_4h_fvg_m15_mss htf_b_daily_h1_cisd htf_c_h1_sweep_fvg; do for e_ in market limit_mid; do
               $DC exec -T fxbt python -m fxagents.bt run "btplugins/$p_.py" --queue --symbol "$sym_" --set "entry=\"$e_\"" </dev/null
             done; done; done ;;
  candles)   # candles for ChatGPT & co: refresh and push once now (the fxcandles container does it every 5 minutes)
             $DC exec -T fxcandles python -m fxagents.candles_publish --once ;;
  btcancel)  # cancel every queued backtest (and stop the one running)
             $DC exec -T fxbt python -m fxagents.bt cancel </dev/null ;;
  instcheck) # READ-ONLY: can this OANDA account trade an instrument; size, margin, financing, live + historical spread
             #   ./fx.sh instcheck BTC_USD
             need_env
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents python -m fxagents.instrument_check "${@:2}" </dev/null ;;
  fxcprobe)  # READ-ONLY FOREX.com spread probe (fxagents/forexcom_probe.py), no orders: ./fx.sh fxcprobe [days]
             need_env; mkdir -p logs
             for k in FOREXCOM_USERNAME FOREXCOM_PASSWORD FOREXCOM_APPKEY; do grep -q "^$k=." .env || { echo "add $k=... to .env"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/fxcprobe-build.log 2>&1 || { echo "build failed — see logs/fxcprobe-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents python -m fxagents.forexcom_probe --days "${2:-10}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  exitstudy) # protection before the first target, on the current playbook's entries (fxagents/exit_study.py): ./fx.sh exitstudy [days]
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/exitstudy-build.log 2>&1 || { echo "build failed — see logs/exitstudy-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.exit_study --days "${2:-365}" </dev/null | grep -v "^  "
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  analystcheck) # would a live trade analyst's exits (15m trend flip / 5m structure break / stall) have helped? Same
             # playbook entries as the exit study, replayed on 1m bars with real spread: ./fx.sh analystcheck [days]
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/analystcheck-build.log 2>&1 || { echo "build failed — see logs/analystcheck-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.exit_study --set analyst --days "${2:-365}" </dev/null | grep -v "^  "
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  weekly)    # a friend's weekly/daily rule books (research/weekly_rules, unchanged) on OANDA daily bid/ask, 13 markets incl.
             # the 5 main forex pairs, plus our controls (swap, 2x costs, coin flip, random timing, month-block 95% range).
             # ./fx.sh weekly [years=5] [placebo=200] → data/year_test/weekly_rules/report.md (5 years keeps 2016–2020 untouched)
             need_env; mkdir -p logs data/year_test/weekly_rules
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/weekly-build.log 2>&1 || { echo "build failed — see logs/weekly-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.weekly_rules --years "${2:-5}" --placebo "${3:-200}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  mtfwhatif) # what-if: was the 15m / 1H moving against the trade at entry? Four checks fixed in fxagents/mtf_whatif.py,
             # on the playbook's 2021→Sep 2026 trades from ./fx.sh pbtest → data/year_test/mtf_whatif/report.md
             need_env; mkdir -p logs
             [[ -d data/history_x/seen_2021_2026 ]] || { echo "no data/history_x/seen_2021_2026 — run ./fx.sh pbtest first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/mtf-build.log 2>&1 || { echo "build failed — see logs/mtf-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.mtf_whatif </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  mtfvault)  # registered confirmation of the 'm15_live' what-if: the eleven 3m/5m playbook cells (frozen in pbtest), run ONCE on
             # untouched 2016–2020, then m15_live judged on those trades → data/year_test/mtf_whatif_2016_2020/report.md
             need_env; mkdir -p logs
             f=data/year_test/playbook_test/cells_frozen.json
             [[ -f "$f" ]] || { echo "no $f — run ./fx.sh pbtest first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/mtfvault-build.log 2>&1 || { echo "build failed — see logs/mtfvault-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.playbook_test --cells-file "$f" \
               --tfs 3m,5m --judge-only --judge old_m1 --out data/year_test/mtf_vault_trades --workers "${2:-2}" \
               --why "Run for the registered confirmation of the m15_live what-if check (Oct 26 2026); the cells' own verdicts here are incidental." </dev/null
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.mtf_whatif --src data/year_test/mtf_vault_trades \
               --pattern trades_old_ --hist data/history_x/old_2016_2020 --confirm --out data/year_test/mtf_whatif_2016_2020 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  round3)    # round-3 context checks (A1 opposing path, A2 two-way chop — ChatGPT's code in research/round3 — and m15_live)
             # on the playbook's 3m/5m entries with the stricter judge (fxagents/whatif_judge.py).
             # ./fx.sh round3 [seen|vault] → data/year_test/round3_<period>/report.md  (vault needs ./fx.sh mtfvault first)
             need_env; mkdir -p logs; p_="${2:-seen}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/round3-build.log 2>&1 || { echo "build failed — see logs/round3-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.round3 --period "$p_" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  dynreport) # shadow review gate scorecard (fxagents/dynamic/score.py): arms A-D on closed trades, net of API cost.
             # ./fx.sh dynreport [books=live,playbook] → data/year_test/dynamic_review/{report.md,summary.json} (reads the journals only)
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/dynreport-build.log 2>&1 || { echo "build failed — see logs/dynreport-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.dynamic.score --books "${2:-live,playbook}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  dynbackfill) # run the shadow review (Claude + OpenAI, same prompts and rules as the live gate) ONCE on the book's last N closed
             # trades that were never reviewed, rebuilt as of their entry minute from OANDA candles (needs OANDA_API_TOKEN and the
             # provider keys from .env, and network, like liqtoday/weekly). Stored as source='backfill', scored apart from the live
             # scorecard. Prints the trades and a cost estimate first. n is capped at 50.
             #   ./fx.sh dynbackfill [book=live] [n=10]  → data/year_test/dynamic_backfill/report.md  (add dry as a 4th word to only estimate)
             #   redo (or --redo) also redoes backfilled trades where ANY provider's round 1 is ABSTAIN/NOT_REVIEWED (keeps the valid round-1
             #   answers, deletes the rest + all round 2 of source='backfill' rows, never live ones, then re-runs the exchange); combine: ./fx.sh dynbackfill live 10 redo dry
             #   fresh (or --fresh) reviews already-backfilled trades again from scratch on a newly built packet (old rows → dyn_archive):
             #   ./fx.sh dynbackfill live 20 fresh [dry]
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/dynbackfill-build.log 2>&1 || { echo "build failed — see logs/dynbackfill-build.log"; exit 1; }
             $DC run --rm --no-deps -T fxagents python -m fxagents.dynamic.backfill --book "${2:-live}" --last "${3:-10}" $(for w_ in "${@:4}"; do case "$w_" in dry|--dry-run) echo --dry-run;; redo|--redo) echo --redo;; fresh|--fresh) echo --fresh;; esac; done) </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  dynexplain) # the reviewers' reasons in full, trade by trade (action, what a WAIT was waiting for, evidence for/against, missing
             # data) next to what the trade did, plus a WAIT summary and any post-mortems. Journal only: no API calls, no network.
             #   ./fx.sh dynexplain [book=live]  → data/year_test/dynamic_explain/report.md
             mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/dynexplain-build.log 2>&1 || { echo "build failed — see logs/dynexplain-build.log"; exit 1; }
             $DC run --rm --no-deps -T fxagents python -m fxagents.dynamic.explain --book "${2:-live}" </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  dynpostmortem) # both reviewers look back at the book's reviewed LOSING trades (packet + their entry review + the 15m path after
             # entry from OANDA) and say why it lost, whether it was visible at entry, and ONE testable alternative rule. Hindsight:
             # hypotheses for the research loop, never evidence. Needs OANDA + provider keys from .env. n capped at 50 (~$0.03/trade).
             #   ./fx.sh dynpostmortem [book=live] [n=10] [dry]  → data/year_test/dynamic_postmortem/report.md
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/dynpostmortem-build.log 2>&1 || { echo "build failed — see logs/dynpostmortem-build.log"; exit 1; }
             $DC run --rm --no-deps -T fxagents python -m fxagents.dynamic.postmortem --book "${2:-live}" --last "${3:-10}" $(for w_ in "${@:4}"; do case "$w_" in dry|--dry-run) echo --dry-run;; esac; done) </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  dynprobe)  # cheap live probe of the shadow review providers: ONE round-1 review each (Claude + OpenAI, real code path) on a small
             # synthetic packet ("probe-<timestamp>"); prints model, action or ABSTAIN + the full error, latency, tokens, cost.
             # Stores nothing. Exit 0 only if every configured provider answered ENTER/WAIT/CANCEL. Needs the keys from .env.
             #   ./fx.sh dynprobe
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/dynprobe-build.log 2>&1 || { echo "build failed — see logs/dynprobe-build.log"; exit 1; }
             $DC run --rm --no-deps -T fxagents python -m fxagents.dynamic.probe </dev/null ;;
  round3g)   # round-3, Gemini's four what-if checks (research/round3/gemini, unchanged) on the playbook's 3m/5m entries,
             # stricter judge. ./fx.sh round3g [seen|vault] → data/year_test/round3_gemini_<period>/report.md
             # (vault: only chasing_exhausted_leg, and only if it passed on seen)
             need_env; mkdir -p logs; p_="${2:-seen}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/round3g-build.log 2>&1 || { echo "build failed — see logs/round3g-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.round3_gemini --period "$p_" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  roomcheck) # room to the next M15 level (registered Oct 28 2026, research/room/): a trade whose nearest M15 swing on the target side
             # is closer than its stop distance, on the playbook's 3m/5m entries, stricter judge. ./fx.sh roomcheck [seen|vault]
             # → data/year_test/room_<period>/report.md (vault only if room_swing passed on seen)
             need_env; mkdir -p logs; p_="${2:-seen}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/roomcheck-build.log 2>&1 || { echo "build failed — see logs/roomcheck-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.room_check --period "$p_" </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  m15timing) # M15 timing (registered Oct 28 2026, research/m15_timing/): A late entry on the M15 turn, B early exit on M15
             # invalidation, each trade replayed by the playbook's engine; paired vs as recorded, with random-timing controls.
             # ./fx.sh m15timing [seen|vault] → data/year_test/m15_timing_<period>/report.md (vault only for a check that passed on seen)
             need_env; mkdir -p logs; p_="${2:-seen}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/m15timing-build.log 2>&1 || { echo "build failed — see logs/m15timing-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.m15_timing --period "$p_" </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  newsstudy) # news event study, step 1 EXPLORE (descriptive): gold / NDQ / US30 around FOMC, CPI, NFP, PPI, 2021 → Nov 17 2023
             # only (later data and 2016–2020 are not read). docs/news_study.md. → data/year_test/news_study_explore/report.md
             need_env; mkdir -p logs
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/newsstudy-build.log 2>&1 || { echo "build failed — see logs/newsstudy-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.news_study </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  newsfade)  # news fade (registered Oct 28 2026, research/news_fade/): at T+30 after FOMC/CPI/NFP/PPI trade against the T-1..T+30
             # move, exit T+150 or 15:50, vs a size-matched no-release control. ./fx.sh newsfade [test|vault|nostop]
             # (nostop: the addendum's no-stop variant, judged once on 2016–2020)
             # → data/year_test/news_fade_<period>/report.md (vault only after a full pass on test)
             need_env; mkdir -p logs; p_="${2:-test}"
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/newsfade-build.log 2>&1 || { echo "build failed — see logs/newsfade-build.log"; exit 1; }
             if [[ "$p_" == nostop ]]; then a_=(--period vault --nostop); else a_=(--period "$p_"); fi
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.news_fade "${a_[@]}" </dev/null || exit $?
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  liqtest)   # higher-timeframe liquidity checks (fxagents/liquidity.py) on the playbook's 2021→Sep 2026 trades from
             # ./fx.sh pbtest: trap (4H+ level swept on the trade's side in the last hour) and no room (next 4H+ level
             # within 0.5 ATR 1H). Pre-registered; seen data only → data/year_test/liquidity/report.md
             need_env; mkdir -p logs
             [[ -d data/history_x/seen_2021_2026 ]] || { echo "no data/history_x/seen_2021_2026 — run ./fx.sh pbtest first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/liqtest-build.log 2>&1 || { echo "build failed — see logs/liqtest-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.liquidity test </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  liqtoday)  # the same liquidity context for the practice account's and playbook book's recent trades, from OANDA
             #   ./fx.sh liqtoday [days=1]  → data/year_test/liquidity_today/report.md (read-only)
             $DC exec -T fxagents python -m fxagents.liquidity today --days "${2:-1}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  pbtest)    # playbook two-step test (fxagents/playbook_test.py): every current playbook setup, as the bot trades it, on
             # 2021→Sep 2026 bid/ask with the real spread; passers only → untouched 2016–2020 (index data exported on demand)
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/pbtest-build.log 2>&1 || { echo "build failed — see logs/pbtest-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.playbook_test \
               --seen holdout_m1,dev_m1 --judge old_m1 --out data/year_test/playbook_test --workers "${2:-2}" </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  pbmacd)    # pre-registered follow-up: the playbook's macd_cross 5m NAS100 cell (frozen in last night's pbtest), judged ONCE
             # on untouched 2016–2020 NAS100 bid/ask (exported on demand)
             need_env; mkdir -p logs
             f=data/year_test/playbook_test/cells_frozen.json
             [[ -f "$f" ]] || { echo "no $f — run ./fx.sh pbtest first"; exit 1; }
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/pbmacd-build.log 2>&1 || { echo "build failed — see logs/pbmacd-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.playbook_test --cells-file "$f" \
               --only "macd_cross:5m@pb-ndq-d" --judge-only --judge old_m1 --out data/year_test/macd_ndq_2016_2020 --workers 1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  fbr)       # author's failed-breakout reversal v1.0 (fxagents/failed_breakout.py): step 1 on holdout_m1 + dev_m1; only a pass
             # opens the untouched 2016–2020 export (old_m1) and judges it once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -d "data/export/$s_" ]] || { echo "no data/export/$s_ — run ./fx.sh export first"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/fbr-build.log 2>&1 || { echo "build failed — see logs/fbr-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.failed_breakout \
               --known holdout_m1,dev_m1 --judge old_m1 --out data/year_test/failed_breakout_v1 </dev/null
             [[ -f "$HOME/.ssh/fx_results" ]] && ./fx.sh publish ;;
  ndqorb)    # author's ndq_orb_vwap_v1 (fxagents/ndq_orb.py): NAS100 09:30–09:45 ORB + cash VWAP. Step 1 on holdout_m1 + dev_m1;
             # only a pass opens untouched 2016–2020 NAS100 (old_m1_idx_NDQ, exported by ./fx.sh pbmacd) and judges it once
             need_env; mkdir -p logs
             for s_ in dev_m1 holdout_m1; do [[ -f "data/export/$s_/NDQ_M1.csv.gz" ]] || { echo "no data/export/$s_/NDQ_M1.csv.gz"; exit 1; }; done
             BUILDKIT_PROGRESS=plain $DC build fxagents </dev/null >logs/ndqorb-build.log 2>&1 || { echo "build failed — see logs/ndqorb-build.log"; exit 1; }
             $DC run --rm --no-deps -T -e FX_MODE=sim fxagents nice -n 10 python -m fxagents.ndq_orb \
               --known holdout_m1,dev_m1 --judge old_m1_idx_NDQ --out data/year_test/ndq_orb_vwap_v1 </dev/null
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
  record)    # closed-trade record per book and strategy for one instrument, as a Markdown table: ./fx.sh record XAUUSD
             $DC exec -T fxagents python -m fxagents.record "${2:-XAUUSD}" ;;
  pause)     curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/pause; echo ;;
  resume)    curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/resume; echo ;;
  flatten)   read -rp "Flatten ALL positions and halt trading? [y/N] " a; [[ "$a" == y ]] || exit 0
             curl -fsS -X POST -H "x-token: $(grep ^DASHBOARD_TOKEN .env | cut -d= -f2-)" localhost:8088/api/control/flatten; echo ;;
  vnc)       echo "On your Mac:  ssh -i ~/.ssh/LightsailDefaultKey-ca-central-1.pem -L 5900:localhost:5900 ubuntu@<server-ip>"
             echo "then open vnc://localhost:5900 (needs VNC_SERVER_PASSWORD set in .env and ./fx.sh restart ib-gateway)" ;;
  *) cat <<USAGE
./fx.sh up | down | restart [svc] | logs [svc] | status | update | localize <file> | test | check | sim [days] | backtest [days] [opts] | research
        backup | why [from] [to] [days] | setup-test <setup> [symbols]
        yeartest [days] [opts] | bbtest [symbols] | newstrats [days] | astra15 | export … | holdout … | rule … | regimecheck | cisd | breakout | gemini [set] [rules] | gemsmc [rules] | pattest [set] | patgold | scalp | sweepvwap | sweeponly | reclaimv2 | smcidm | volbrk | h4don | bt <plugin> [data] [SYM] | btsetups SYM | bthtf | btcancel | candles | mgmtreplay [days] | reconcile [days] | repair [--apply] | fxcprobe [days] | exitstudy [days] | analystcheck [days] | pbtest [workers] | roomcheck [seen|vault] | m15timing [seen|vault] | newsstudy | newsfade [test|vault|nostop] | liqtest | liqtoday [days] | dynbackfill [book] [n] [redo] [fresh] [dry] | dynprobe | dynexplain [book] | dynpostmortem [book] [n] [dry] | pbmacd | fbr | ndqorb | jevcheck | record [SYMBOL] | lab … | publish-setup | publish | pause | resume | flatten | vnc
services: fxagents, cloudflared (+ ib-gateway when COMPOSE_PROFILES=ibkr)
USAGE
  ;;
esac
