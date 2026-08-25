# Handoff — AI Trading System (crypto pivot)

Last updated: 2026-08-25. Read this first in any new session before touching code.

## What this project is

Originally scoped as XAU/USD via MT5 (see PIVOT NOTICE at top of
PROJECT_PLAN.md), pivoted to **Binance Futures crypto perpetuals** because
MT5's lot-size minimums made 1% risk sizing impossible on a 2,000 THB
account. PROJECT_PLAN.md §0-§21 is still the XAU/MT5-era plan (kept for
reference); the crypto-specific execution details live in code + this repo's
docs/, not in PROJECT_PLAN.md.

**Read `docs/FINDINGS.md` before re-running any backtest/research experiment
— it records what's already been tried and rejected, to avoid repeating work.**

## Current infrastructure (all live and running)

- **VPS**: Oracle Cloud Free Tier, Ubuntu 24.04, `134.185.81.78`, user `ubuntu`
  - SSH key: `~/.ssh/oracle_trading_vps.key` (on the dev Mac, gitignored)
  - Hardened: UFW (only port 22 open), fail2ban, key-only SSH, root login
    disabled, unattended-upgrades auto-reboot disabled
- **Repo**: `https://github.com/tongeiei/ai_trading_system` (public), cloned
  to `~/ai_trading_system` on the VPS, kept in sync via `git pull`
- **systemd units** (`/etc/systemd/system/`, sources in `deploy/`):
  - `signal-cycle.timer` + `.service` — runs `scripts/run_signal_cycle.py`
    every M15 bar-close (`OnCalendar=*:0/15:30`)
  - `dashboard.service` — Streamlit dashboard, persistent, bound to
    `127.0.0.1:8501` only (view via SSH tunnel: `ssh -i ~/.ssh/oracle_trading_vps.key -N -L 8501:127.0.0.1:8501 ubuntu@134.185.81.78`, then open `http://localhost:8501`)
- **Binance**: testnet/demo trading only (`enable_demo_trading(True)` via
  ccxt) — no real money anywhere yet. API keys in `.env` on both dev Mac and
  VPS (gitignored, never committed).
- **`.env` required keys**: `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`,
  optionally `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_TARGET_ID` (alerting — not
  yet configured, see "Immediate next step" below).

## Strategy status — what's proven, what's not

- **Symbol**: ETH/USDT:USDT only. BTC/SOL/BNB tested and rejected (no edge).
- **Config (locked)**: EMA-pullback V0 rules, `ADX_threshold=35`, `SL=2.5x ATR`,
  `TP=2x SL`. Do not re-tune without a fresh, disjoint holdout — see
  docs/FINDINGS.md for why ad-hoc re-tuning already burned through several
  configs on the same data.
- **ML (LightGBM)**: tested and REJECTED at the P5 gate — AUC ~0.497 on
  holdout, indistinguishable from noise. Do not re-introduce an "AI
  probability" display or gate; `src/live/ev_estimate.py` uses historical
  backtest base rates instead, explicitly not ML, and is labeled as such
  everywhere (dashboard, code comments).
- **Walk-forward finding (important)**: edge is real but UNSTABLE. 8/12
  quarterly folds positive, only 2/12 individually statistically
  significant, and 2023 H2 was significantly NEGATIVE (whipsaw/high-vol
  regime). Base risk was lowered from planned 1-2% to **0.5%**
  (`BASE_RISK_PCT` in `scripts/run_signal_cycle.py`) because of this.
- A rolling win-rate guard (`rolling_winrate_risk_multiplier` in
  `src/live/guards.py`) halves risk automatically if the last 20 closed
  trades' win rate drops below 30% — an early warning modeled on the 2023
  H2 failure mode, triggers before DD/daily-loss thresholds would.

## What's implemented (all tested, 39 unit tests passing)

```
src/data/           binance_loader, funding_rate_loader, db (SQLite schema)
src/features/        engine.py — 12 features, leak-tested
src/regime/          rules.py — TREND/RANGE classifier
src/strategy/        v0_rules.py (locked config), breakout.py, mean_reversion.py (both rejected)
src/labeling/        triple_barrier.py
src/backtest/        costs.py, significance.py (bootstrap test)
src/models/          train.py, calibrate.py — LightGBM pipeline, kept for reference, NOT used live
src/risk/            sizing.py — position sizing, anti-martingale tested
src/live/
  order_executor.py    entry+SL+TP placement (exchange-native algo orders),
                        fetch_open_algo_orders (ccxt doesn't see these natively — workaround)
  guards.py            spread/stale-data/heartbeat/retry-limit/winrate guards
  reconcile.py         orphan-position detection (CRITICAL if position has no SL)
  position_timeout.py  12h forced close + organic SL/TP-fired detection
  ev_estimate.py       historical-stats EV gate (NOT ML — see above)
  alerting.py          LINE Messaging API alerts (needs LINE_CHANNEL_ACCESS_TOKEN
                        + LINE_TARGET_ID, not yet set)
  logging_store.py     log-before-execute helpers into signals/orders/trades/risk_decisions
  signal_service.py    live OHLCV fetch + feature/regime/signal generation
src/dashboard/app.py  Streamlit — heartbeat, candlestick chart w/ trade markers,
                       EV panel, equity curve, trades/signals/risk-decision tables
```

## Immediate next step (mid-task when context ran out)

Alerting switched from Discord to **LINE Messaging API** (Discord webhook
code replaced outright — LINE Notify, the simpler webhook-style option, was
shut down by LINE at end of March 2025, so this needs a LINE Official
Account + Messaging API channel instead). Code is written and deployed
(`src/live/alerting.py`, wired into `scripts/run_signal_cycle.py`), fails
safe if unconfigured (logs + skips, doesn't crash). Waiting on:

1. User creates a LINE Official Account (via LINE Official Account Manager,
   free) and enables the Messaging API for it, then issues a
   **channel access token** (long-lived) from the Messaging API settings
   page
2. User gets the target **userId** or **groupId** to push to — easiest way
   is to add the OA as a friend (or invite it to a group) and read the
   `userId`/`source.groupId` off an incoming webhook event, or use LINE's
   "Verify" tool in the console
3. User adds `LINE_CHANNEL_ACCESS_TOKEN=...` and `LINE_TARGET_ID=...` to
   `.env` on the dev Mac themselves (assistant should not see/type these —
   same handling as the Binance API keys)
4. Assistant scp's the updated `.env` to the VPS (same pattern used for the
   Binance keys — copy the file, never read its contents)
5. Restart `signal-cycle.service` on the VPS, verify a test alert fires

## Known gaps / honest todo list

- No trade has occurred on live/paper yet — ETH has been in RANGE regime
  continuously since automation started (~2026-08-24), which is statistically
  unremarkable (see conversation: P(no trade in 71 bars) ≈ 6-19% depending
  on window, not a bug).
- Mainnet shadow (Phase B proper, per the 5-layer testing framework
  discussed) hasn't happened — everything so far runs on demo trading, not
  against real mainnet orderbook depth. Real execution costs (spread/slippage)
  are still assumptions from the backtest cost model, not measured live.
- No robustness check yet on dropping the 2 outlier-good months (Aug 2025,
  Aug 2026) from the walk-forward — flagged as a next step, never done.
- `docs/TASKS.md` still reflects the original MT5/XAU-era phase breakdown;
  it hasn't been rewritten for the crypto pivot beyond the P0 section.
