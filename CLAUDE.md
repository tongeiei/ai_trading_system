# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first, every session

This repo has pivoted direction twice and runs two independent trading tracks at once. Docs go stale fast — always trust the dated handoff docs over `PROJECT_PLAN.md`/`TASK_NEW_WORLD.md`, which are historical design docs kept for reference, not current state.

1. **`docs/HANDOFF.md`** — authoritative state of the **live crypto track** (what's actually running on the VPS right now). Read before touching any `src/live/`, `src/risk/`, `scripts/run_signal_cycle.py` code.
2. **`docs/FINDINGS.md`** — chronological log of every backtest/research result and what was rejected. Read before re-running or re-litigating any experiment — most "obvious" ideas (more timeframes, more symbols, ML overlay, tighter/looser risk params) have already been tried and falsified here.
3. **`docs/research/GOLD_HANDOFF.md`** — authoritative state of the **XAU/USD gold research track** (pure backtest, separate codebase path/config/cost model from crypto, no live/paper trading). All 8 gold strategies tested so far (R1, R2, R5, R8, R11, R14, R15, R17) are **falsified**.
4. **`docs/XAU_ARCHITECTURE_AUDIT.md`** — the current forward-looking plan (dated 2026-09-01, written per `TASK_NEW_WORLD.md`'s audit-before-code process). §17 tracks which phase is next. Despite the "XAU" name, this is about building the full target architecture (LLM analysis layer, real Risk Engine, setup-quality scorecard) — read §0 and §17 for exact current status before assuming any of it exists in code yet. As of the last update, **none of the target-architecture code exists** — no LLM/provider integration anywhere in the repo, and no real Risk Engine (daily loss limit, max DD, kill switch, etc. are all still unimplemented; only position sizing + a rolling win-rate multiplier exist today).
5. **`docs/STRATEGY_RISK_SPEC.md`** — snapshot of exactly what's locked on live crypto (symbols, regime rules, entry/exit config).
6. **`docs/XAU_LIVE_HANDOFF.md`** — authoritative state of the **XAU live-track machine/account prep** (started 2026-09-02, still pre-refactor at time of writing): broker/capital/LLM decisions, what's verified working on this Windows dev machine (Python, venv, MT5 connectivity/order execution), and what's still open before P2 can start.

Do not propose re-tuning locked parameters, re-testing rejected symbols/strategies, or reviving the ML/LightGBM probability filter without a new holdout dataset that's genuinely separate from what's already been burned — see `docs/FINDINGS.md` for why.

## What's actually true right now (as of docs/HANDOFF.md, 2026-08-26)

- **Live (demo/testnet only, no real money anywhere)**: Binance Futures perpetuals via `ccxt`, `enable_demo_trading(True)`. Two symbols run independently in `scripts/run_signal_cycle.py`'s `SYMBOLS` list: `ETH/USDT:USDT` (risk 0.5%, proven-but-fragile edge) and `XRP/USDT:USDT` (risk 0.25%, tier-2, paper-trading only). BTC/SOL/BNB/DOGE/ADA/LINK/LTC/AVAX were backtested and rejected.
- **Strategy**: locked rule-based V0 EMA-pullback (`src/strategy/v0_rules.py`) — `ADX_threshold=35`, `SL=2.5x ATR`, `TP=2x SL`. This is the baseline the (now-abandoned) ML overlay had to beat and didn't (AUC ~0.497 on holdout, statistically indistinguishable from noise). **Do not reintroduce an "AI probability" display or gate** — `src/live/ev_estimate.py` deliberately uses historical base rates, not ML, and is labeled as such everywhere (code comments, dashboard).
- **Decision cadence**: one signal per M15 bar close, triggered by a systemd timer (`deploy/signal-cycle.timer`) firing `scripts/run_signal_cycle.py` — not a long-running loop. H1 is used only for regime/trend context.
- Infra runs on an Oracle Cloud VPS (`134.185.81.78`); see `README.md` for the SSH tunnel command to view the dashboard and the one-liner to check timer/journal status remotely.

## Commands

```bash
pip install -r requirements.txt        # Python 3.13.7; no venv/lockfile committed
cp .env.example .env                   # fill BINANCE_TESTNET_API_KEY/SECRET (+ LINE token for alerts)

pytest                                 # run full test suite (no pytest.ini — plain discovery from repo root)
pytest tests/test_sizing.py            # single file
pytest tests/test_sizing.py -k name    # single test

python scripts/run_signal_cycle.py     # run one signal cycle manually (same entrypoint the systemd timer fires)
streamlit run src/dashboard/app.py     # local dashboard (deployed copy binds 127.0.0.1:8501 on the VPS only)
```

There is no linter config (no ruff/flake8/black) and no CI workflow in this repo — tests are run manually.

## Architecture — live crypto pipeline

```
scripts/run_signal_cycle.py  (fired per M15 close, per symbol, isolated try/except so one symbol's failure never blocks another)
  1. write heartbeat (guards.py reads this — no heartbeat = EA/guards stop trusting new signals)
  2. close_expired_positions / detect_and_close_organic_exits (position_timeout.py)
       — the exchange fires SL/TP on its own; this process gets no callback, so this
         is the only way trades get recorded as closed
  3. reconcile_symbol (reconcile.py) — refuses to act if a position exists without
     matching state (CRITICAL) or if one is already open (no pyramiding)
  4. generate_live_signal (signal_service.py) → features (engine.py) → regime (regime/rules.py)
     → v0_rules.py entry logic
  5. estimate_ev (ev_estimate.py) — historical-stats EV gate, NOT ML (see above)
  6. rolling_winrate_risk_multiplier (guards.py) — halves risk if last 20 closed
     trades (per symbol) have <30% win rate; an early-warning independent of the
     DD/daily-loss thresholds
  7. log_signal (logging_store.py) — logs EVERY signal including NO_TRADE, before
     any execution, to avoid survivorship bias in the system's own data
  8. execute_signal_with_logging (order_executor.py) — sizes position (risk/sizing.py),
     places exchange-native entry+SL+TP as one algo order, logs before/around execution
  9. alerting.py sends real-time LINE messages (Discord was dropped when LINE Notify
     shut down) — the dashboard is not real-time, it caches 30s and needs a manual refresh
```

Key modules:
- `src/data/` — `binance_loader.py`, `funding_rate_loader.py`, `db.py` (SQLAlchemy/SQLite schema: `bars`, `signals`, `orders`, `trades`, `risk_decisions`, etc.)
- `src/features/engine.py` — 12 features, leakage-tested (`tests/test_leakage.py`)
- `src/regime/rules.py` — rule-based TREND/RANGE classifier (deliberately not ML — see `TASK_NEW_WORLD.md` §7 rationale, still followed)
- `src/labeling/triple_barrier.py` — López de Prado triple-barrier labeling
- `src/backtest/` — `costs.py` (slippage/fees as basis points of price, not a fixed USD amount — a past bug), `significance.py` (bootstrap tests), `gold_harness.py` (separate harness for the XAU track, do not conflate with the crypto backtester)
- `src/risk/sizing.py` — position sizing against `ExchangeSpec` (step size / min notional from `exchange.load_markets()`); has anti-martingale regression tests — lot size must never be a function of the previous trade's outcome
- `src/models/` — LightGBM train/calibrate pipeline; **kept for reference only, not used in the live pipeline** (rejected per `docs/FINDINGS.md`)
- `src/dashboard/app.py` — Streamlit: heartbeat, candlestick + trade markers, EV panel, equity curve, signals/trades/risk-decisions tables

`config/exchange_spec.yaml` is the crypto perp cost/precision spec (fetched from Binance); `config/gold_spec.yaml` is a **completely separate** spec for the XAU backtest track (spot, no funding rate, Dukascopy data) — never merge these or apply crypto funding-cost logic to gold backtests.

## Repository layout notes

- `scripts/` is a mix of the one production entrypoint (`run_signal_cycle.py`) and ~50 one-off research/backtest scripts (`research_*.py`, `run_gold_r*.py`, `fetch_*.py`, phase-numbered exploration scripts). These are research artifacts, not a library API — don't assume they're maintained or re-run without checking `docs/FINDINGS.md`/`docs/research/GOLD_HANDOFF.md` for whether that line of inquiry is already closed.
- `docs/research/` holds narrative reports per research round plus `artifacts/` (raw CSV/txt result dumps) — these were previously gitignored by accident (23 files never committed) and were only recovered/committed in a later cleanup; don't re-add them to `.gitignore`.
- `.claude/agents/` defines a multi-agent "trading research team" persona set (Research Lead, Strategy Research, Risk Research, Systems Audit, Skeptic, Trading Lead, Backtest agent — see `00_team_overview.md` for the workflow and veto rules) for structuring research work done *through* Claude Code sessions. This is prompt scaffolding, not a runtime integration — there is no code anywhere in the repo that calls an LLM API.
- `TASK_NEW_WORLD.md` is the original task brief for building a full LLM-assisted 24/7 architecture (regime engine → setup scanner → AI analysis → risk engine → execution → journal → feedback loop). It's a spec to audit against, not a description of what exists — cross-check against `docs/XAU_ARCHITECTURE_AUDIT.md` §0/§17 for the actual gap.
