# Strategy & Risk Specification

Last updated: 2026-08-25. Describes what the system actually runs live, not
the original XAU/MT5 plan (see PROJECT_PLAN.md for that era; [HANDOFF.md](HANDOFF.md)
for the crypto-pivot context). Read [FINDINGS.md](FINDINGS.md) before changing
any parameter below — most of these values are locked because an earlier
config was already tried and rejected.

## 1. Scope

- **Symbol**: ETH/USDT:USDT only. BTC/SOL/BNB were backtested and rejected
  (no edge).
- **Timeframe**: M15 decisions, H1 used for trend confirmation. Signals are
  generated once per M15 bar-close (`scripts/run_signal_cycle.py`, triggered
  by `signal-cycle.timer`), never intrabar.
- **Live config is locked**: `ADX_threshold=35`, `SL=2.5x ATR`, `TP=2x SL`
  (`LOCKED_CONFIG` in [scripts/run_signal_cycle.py](../scripts/run_signal_cycle.py)).
  Do not re-tune without a fresh, disjoint holdout.

## 2. Regime classification

[src/regime/rules.py](../src/regime/rules.py) — rule-based, 2 live classes.

| Regime | Condition |
|---|---|
| `TREND` | H1 ADX(14) > `adx_threshold` **and** `\|EMA50-EMA200\|/ATR_H1` > 0.5 |
| `RANGE` | everything else |

- Defaults: `ADX_TREND_THRESHOLD = 22.0`, `TREND_STRENGTH_THRESHOLD = 0.5`.
  The live-locked config overrides ADX to **35** (stricter than the module
  default) — see `LOCKED_CONFIG` above.
- `NEWS_BLACKOUT` is a defined hook in the strategy signatures but is a
  no-op for crypto V1 — no economic-calendar blackout list exists yet
  (planned for a later phase).
- `vol_multiplier()` is a separate, continuous 0.40–1.0 risk multiplier
  derived from ATR percentile (not a discrete "HIGH_VOLATILITY" class, to
  avoid cliff behavior). Not currently wired into the live risk multiplier
  chain — the live multiplier comes from the win-rate guard (§4) only.

## 3. Entry strategies

All three share one output schema — one row per M15 bar with
`action ∈ {LONG, SHORT, NO_TRADE}` and `sl_price`/`tp_price` when acting —
so they're swappable in `scripts/compare_v0_strategies.py`. Only **V0
EMA-pullback** is used live; the other two are kept for reference.

### 3.1 V0 EMA-pullback (LIVE) — [src/strategy/v0_rules.py](../src/strategy/v0_rules.py)

Trend-following pullback entry, active only in `TREND` regime.

- **Long setup**: `TREND` regime, H1 trend bullish (`f03_h1_trend_atr > 0`),
  and price pulls back to EMA20 then closes back above it (`dist_ema20`
  crosses from ≤0 to >0 on this bar).
- **Short setup**: mirror — H1 bearish, `dist_ema20` crosses from ≥0 to <0.
- **Quality filters** (applied after the base setup): ATR percentile must
  be within `[atr_pct_min, atr_pct_max]` (default no-op, `[0, 1]`), and
  candle body ratio must be ≥ `min_body_ratio` (default no-op, `0`) — avoids
  dead/chaotic volatility and indecisive candles.
- **Stops**: `sl_distance = clip(ATR * sl_atr_mult, lower=ATR*0.8, upper=ATR*max(3.0, sl_atr_mult*1.2))`.
  Module defaults `SL_ATR_MULT=1.5`, `TP_R_MULT=2.0`; live-locked config uses
  `SL=2.5x ATR` instead (`TP_R_MULT` stays at module default, i.e. TP = 2R).
- Rows where features aren't warmed up yet (`f08_atr_percentile` is NaN)
  are forced to `NO_TRADE`.

### 3.2 Breakout (rejected, reference only) — [src/strategy/breakout.py](../src/strategy/breakout.py)

Donchian(20) channel breakout, requires H1 ADX > 20. Regime filter
deliberately dropped (breakout logic implies its own trend confirmation).
Channel is computed on bars strictly before the signal bar (`shift(1)`) so
the breakout bar can't leak into its own trigger level.

### 3.3 Mean-reversion (rejected, reference only) — [src/strategy/mean_reversion.py](../src/strategy/mean_reversion.py)

Fades `dist_ema20/ATR` beyond ±`entry_z` (default 2.0), `RANGE` regime only
— opposite thesis to the other two: bets on a snap-back to the mean rather
than continuation. Smaller `TP_R_MULT` (1.5 vs 2.0) since the target is the
mean, not a runner.

## 4. Risk sizing and guards

### 4.1 Position sizing — [src/risk/sizing.py](../src/risk/sizing.py)

`compute_position_size(equity, risk_pct, entry_price, sl_price, spec)`:

```
risk_amount = equity * risk_pct
qty = floor((risk_amount / |entry_price - sl_price|) / stepSize) * stepSize
```

- Always rounds **down** to `stepSize` — rounding up would silently exceed
  the intended risk.
- Raises `PositionRejected` (caller must not round up to compensate) if
  `qty < amount_min` or `notional < min_notional` — account too small for
  this `risk_pct`/SL distance at the current price.
- `risk_pct` is validated to `(0, 0.05]` as a sanity bound.
- No lot/tick-value conversion needed (unlike the original MT5 plan) —
  crypto sizing is direct risk-amount ÷ SL-distance.

### 4.2 Base risk and the win-rate guard

- **Base risk**: `BASE_RISK_PCT = 0.005` (0.5%) in
  [scripts/run_signal_cycle.py](../scripts/run_signal_cycle.py). Lowered
  from the originally-planned 1–2% after walk-forward testing showed the
  ETH edge is real but **unstable**: 8/12 quarterly folds positive, only
  2/12 individually statistically significant, and 2023 H2 was
  significantly negative (a whipsaw/high-vol regime the single
  train/holdout split had missed).
- **Rolling win-rate guard** — `rolling_winrate_risk_multiplier()` in
  [src/live/guards.py](../src/live/guards.py): looks at the last
  `WINRATE_WINDOW=20` closed trades' net R-multiples; if win rate over that
  tail drops below `WINRATE_THRESHOLD=0.30`, risk is halved
  (`reduced_multiplier=0.5`) until it recovers. Returns 1.0 (no reduction)
  if fewer than 20 trades exist — too noisy to act on with a smaller
  sample. Modeled directly on the 2023 H2 failure mode (win rate ~27%,
  both LONG and SHORT losing together) — triggers earlier than a
  drawdown/daily-loss threshold would.
- Effective live risk per trade: `BASE_RISK_PCT * risk_multiplier`, i.e.
  0.5% normally, 0.25% when the guard is active.

### 4.3 Pre-trade guards — [src/live/guards.py](../src/live/guards.py)

Pure functions, no exchange calls, all fail closed:

| Guard | Blocks trading when | Default threshold |
|---|---|---|
| `spread_guard` | current spread > `max_ratio` × median spread | 3.0x |
| `stale_data_guard` | last tick older than `max_age_sec` | 30s |
| `heartbeat_guard` | signal-cycle heartbeat older than `max_age_sec` | 60s |
| `rolling_winrate_risk_multiplier` | see §4.2 | win rate < 30% over last 20 trades |

`retry_with_limit()` caps order-placement retries at 2 (`RetryLimitExceeded`
raised after that) — never retries unboundedly, to avoid turning a
transient error into a duplicate/runaway order.

### 4.4 EV gate

`src/live/ev_estimate.py` gates entries using **historical backtest base
rates**, not a model prediction. This was already tried with LightGBM
(`src/models/`) and rejected at the P5 gate — holdout AUC ~0.497,
indistinguishable from noise. `estimate_ev` is explicitly labeled
non-ML everywhere it's surfaced (code comments, dashboard) to prevent this
from being reintroduced as an "AI probability" display.

### 4.5 Position lifecycle safety

- `src/live/reconcile.py` — orphan-position detection; the signal cycle
  refuses to open a new trade if a position with no matching SL exists.
- `src/live/position_timeout.py` — forces a close after 12h, and detects
  organic SL/TP-fired exits (ccxt doesn't natively surface exchange-native
  algo-order fills, see `order_executor.fetch_open_algo_orders`).

## 5. Known limitations (do not treat as solved)

- Edge is statistically real but unstable across regimes (§4.2) — do not
  raise `BASE_RISK_PCT` without a fresh disjoint holdout confirming
  stability.
- No trade has occurred live/paper yet as of this writing; ETH has stayed
  in `RANGE` regime since automation started — not itself evidence of a
  bug (see [HANDOFF.md](HANDOFF.md) known-gaps section for the probability
  analysis).
- All live activity so far is on demo/testnet trading — real spread/slippage
  are still backtest cost-model assumptions, not measured against mainnet
  orderbook depth.
- `vol_multiplier()` (§2) exists but is not currently wired into the live
  risk-multiplier chain.
