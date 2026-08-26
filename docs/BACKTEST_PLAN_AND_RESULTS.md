# Backtest Plan & Results

Last updated: 2026-08-25. Summarizes the backtest methodology and every
experiment run so far, distilled from [FINDINGS.md](FINDINGS.md) (the
chronological source of truth — read that before re-running any
experiment) and cross-checked against [STRATEGY_RISK_SPEC.md](STRATEGY_RISK_SPEC.md)
for what's actually locked live.

## 1. Methodology

### 1.1 Cost model — [src/backtest/costs.py](../src/backtest/costs.py)

Every raw `r_multiple` from labeling has three cost components subtracted,
all converted to R-multiples (fractions of `sl_distance`) so they combine
directly:

| Cost | Model |
|---|---|
| Commission | round-trip taker fee (entry + exit), `TAKER_FEE = 0.0005` |
| Funding | summed over the holding window from actual historical funding-rate data; sign flips for LONG vs SHORT |
| Slippage | placeholder constant, `SLIPPAGE_PRICE_UNITS = 0.5` USD/side — real fills not yet measured (see §5) |

`net_r_multiple = r_multiple - commission_r - slippage_r - funding_r`

### 1.2 Significance testing — [src/backtest/significance.py](../src/backtest/significance.py)

One-sample bootstrap (`n_resamples=10,000`) on `net_r_multiple`: resample
with replacement, take the mean each time, and report a 95% CI plus a
two-sided p-value for H0: true mean ≤ 0. A result counts as significant
only if `p < 0.05` **and** the CI lower bound is above zero.

### 1.3 Splits used

- **Single split**: TRAIN (2023-2024) / HOLDOUT (2025-2026) — used for
  initial screening only.
- **Anchored walk-forward**: 12 quarterly folds spanning 2023-Q3 through
  2026-Q2, each fold anchored (grows the train window forward), with a
  12h embargo at fold boundaries to prevent leakage across the cut.
- Both use the same locked config across all folds — no per-fold
  re-tuning, to avoid the multiple-comparison problem.

## 2. Experiment log (chronological, from FINDINGS.md)

### 2.1 V0 strategy screening on BTC (single split)

EMA-pullback, Donchian breakout, and mean-reversion-fade tested on
BTC/USDT, full cost model applied.

| Strategy | TRAIN net_avg_r | HOLDOUT net_avg_r | PF (holdout) |
|---|---|---|---|
| EMA pullback (ADX35, SL2.5x) | -0.047 | -0.027 | 0.956 |
| Breakout | — | — | ~0.52 |
| Mean-reversion | — | — | ~0.52 |

**Conclusion**: no exploitable edge on BTC/USDT with any of the three
setups at M15. Closed question — do not retest these exact configs on
BTC without new information.

### 2.2 Multi-symbol pooled screening (BTC/ETH/SOL/BNB)

Same locked config, HOLDOUT (2025-2026) only, across 4 symbols (avoids
re-introducing per-symbol tuning bias).

| Symbol | net_avg_r | PF |
|---|---|---|
| BTC | -0.027 | 0.956 |
| **ETH** | **+0.152** | **1.278** ← only symbol clearing PF 1.10 |
| SOL | -0.504 | 0.474 |
| BNB | -0.307 | 0.616 |

ETH selected as sole live candidate. Supporting checks on the ETH
holdout:
- Bootstrap: **p = 0.0012**, 95% CI **[0.058, 0.246]** — positive mean
  survives resampling
- Slippage sensitivity 1x/2x/3x: PF stays above 1.10 even at 3x (1.143)
- Quarterly consistency within this holdout window: **7/7 positive**

### 2.3 Anchored 12-fold walk-forward on ETH (full 3-year history)

The single-split result above only tested one window (2025-2026). This
tests the same locked config across the full history to check whether
the edge generalizes.

**Result — materially weaker than the single-split test suggested:**

| Metric | Value |
|---|---|
| Folds positive | 8/12 (67%) — passes the §15 60% threshold, but barely |
| Folds individually significant | 2/12: 2024-Q1 (+0.471R, p<0.001), 2025-Q3 (+0.365R, p=0.0013) |
| Worst folds | **2023-Q3 (-0.479R, p=0.006)** and **2023-Q4 (-0.434R, p<0.001)** — both significantly negative |
| Std dev across fold means | 0.282, vs. pooled overall mean 0.038 — high variance relative to the average |

**Root cause of the 2023 H2 failure** (see FINDINGS.md for full detail):
ETH rallied +38% over the period but via a choppy, high-volatility path
(deep drawdown to $1,525 in Sep–Oct before the rally resumed). ATR
percentile averaged 64.5% during this window vs. 48.4% for the rest of
history. Both LONG (-0.457R, n=116) and SHORT (-0.433R, n=60) trades
lost, with 62% of all trades in the window exiting via SL — the
signature of a whipsaw regime, not a directional-bias failure.

**Conclusion**: ETH shows a real but **unstable** edge — strong in some
quarters, absent or negative in others, correlated with a specific
choppy-high-volatility regime that occurred in 2023 H2 and may recur.
This finding is why live `BASE_RISK_PCT` was set to 0.5% instead of the
originally planned 1–2%, and why the rolling win-rate guard exists (see
[STRATEGY_RISK_SPEC.md §4.2](STRATEGY_RISK_SPEC.md#42-base-risk-and-the-win-rate-guard)).

### 2.4 Tested fix: `atr_pct_max=0.75` volatility ceiling filter — REJECTED

Hypothesis: capping trades to ATR percentile ≤ 75% would filter out the
2023 H2 whipsaw regime without hurting the good quarters (2024-Q1,
2025-Q3).

**Result: hypothesis rejected**, made things worse across the board:
- Consistency dropped from 8/12 (67%) to 6/12 (50%) — now fails the §15
  threshold
- Overall pooled `net_avg_r` flipped from **+0.038 to -0.031**
- 2023-Q3 got *worse*, not better (-0.435R → -0.754R)
- The filter cut good trades roughly as much as bad ones (2025-Q3 trade
  count dropped 147→84) — high ATR percentile isn't a clean proxy for
  "bad trade" here; some of the best trades (2024-Q1, 2025-Q3) also
  occurred in elevated-vol conditions

**Conclusion**: do not retry simple ATR-percentile ceiling filters on
this strategy without a more specific mechanism that can distinguish
"high vol from a clean breakout" from "high vol from chop" — a single
threshold can't do that. (Experiment script was deleted after confirming
the negative result; the FINDINGS.md entry is the only record.)

### 2.5 ML (LightGBM) — REJECTED

Not itself a backtest-P&L experiment, but relevant to the same pipeline:
tested at the P5 statistical gate, holdout AUC ≈ 0.497 — indistinguishable
from noise. `src/models/` kept for reference only, not used live. Live EV
gate (`src/live/ev_estimate.py`) uses historical backtest base rates
instead, explicitly labeled non-ML everywhere it's surfaced.

## 3. Where this leaves the live strategy

- **Not proven robust enough for the originally-planned 1–2% risk** — the
  2023 H2 result shows real drawdown risk the single-holdout test never
  surfaced.
- **Not dead either** — 2/12 quarters show genuine statistical
  significance in the positive direction, and this remains the best
  result across everything tested (4 symbols × 3 strategy families ×
  multiple SL/ADX configs).
- **Decision taken**: keep paper-trading on testnet at the current
  cadence; live risk reduced to 0.5%/trade with an automatic halving
  guard on a rolling win-rate drop (see [STRATEGY_RISK_SPEC.md](STRATEGY_RISK_SPEC.md)).
  Do not raise risk back toward 1–2% without either (a) more live
  paper-trade data, or (b) a mechanism-based (not threshold-based)
  explanation for the 2023 H2 failure, tested against a fresh holdout.

## 4. Backtest scripts (reference)

| Script | Purpose |
|---|---|
| [scripts/run_v0_backtest_smoke.py](../scripts/run_v0_backtest_smoke.py) | Fast sanity-check run |
| [scripts/run_v0_backtest_with_costs.py](../scripts/run_v0_backtest_with_costs.py) | Full cost-adjusted backtest |
| [scripts/run_v0_holdout_final.py](../scripts/run_v0_holdout_final.py) | Single train/holdout split run |
| [scripts/run_v0_pooled_multi_symbol.py](../scripts/run_v0_pooled_multi_symbol.py) | Multi-symbol pooled screening (§2.2) |
| [scripts/eth_walkforward_multifold.py](../scripts/eth_walkforward_multifold.py) | 12-fold anchored walk-forward (§2.3) |
| [scripts/eth_walkforward_and_slippage.py](../scripts/eth_walkforward_and_slippage.py) | Walk-forward + slippage sensitivity |
| [scripts/test_eth_significance.py](../scripts/test_eth_significance.py) | Bootstrap significance test |
| [scripts/compare_v0_strategies.py](../scripts/compare_v0_strategies.py) | Side-by-side strategy comparison |
| [scripts/tune_v0_filters.py](../scripts/tune_v0_filters.py) | Filter-parameter sweep (used for the atr_pct_max experiment, §2.4) |

## 5. Known gaps in the backtest itself

- Slippage is still a **constant placeholder** (`0.5` USD/side), not
  measured against real order-book depth — flagged for the mainnet-shadow
  phase, not yet run (see [HANDOFF.md](HANDOFF.md)).
- No robustness check yet on dropping the 2 outlier-good months (Aug
  2025, Aug 2026) from the walk-forward — flagged as a next step, never
  done.
- No trade has occurred live/paper yet as of this writing, so there is
  no live-vs-backtest divergence data beyond what was already found and
  fixed (missing-TP + timeout divergence bug, see git history around
  `df8513b`).
