# Research Findings Log

Chronological record of what was tested and what was concluded — so we don't
re-litigate settled questions or re-run experiments that already failed.
Every entry here represents real backtest output, not speculation.

---

## 2026-08 — V0 strategy screening (BTC, single-split)

Tested EMA pullback, Donchian breakout, and mean-reversion-fade as V0
candidates on BTC/USDT, TRAIN(2023-2024)/HOLDOUT(2025-2026) split, full cost
model (commission + funding + slippage) applied.

**Result:** none beat PF 1.10. EMA pullback (ADX35, SL2.5x) was best —
TRAIN net_avg_r -0.047, HOLDOUT net_avg_r -0.027, PF 0.956. Breakout and
mean-reversion were both clearly worse (PF ~0.52) on both splits.

**Conclusion:** BTC/USDT has no exploitable edge with any of these three
setups at M15. Do not re-test these exact configs on BTC again without new
information.

## 2026-08 — Multi-symbol pooled screening (BTC/ETH/SOL/BNB)

Same LOCKED config (ADX35, SL2.5x, no per-symbol tuning) run across 4
symbols, HOLDOUT (2025-2026) only, to avoid re-introducing the
multiple-comparison problem from ad-hoc per-symbol tuning.

**Result:**
- BTC: net_avg_r -0.027, PF 0.956
- **ETH: net_avg_r +0.152, PF 1.278** ← only symbol clearing PF 1.10
- SOL: net_avg_r -0.504, PF 0.474
- BNB: net_avg_r -0.307, PF 0.616

**Conclusion:** ETH selected as the sole live candidate. Bootstrap test on
ETH holdout: p=0.0012, 95% CI [0.058, 0.246] — positive mean survives
resampling. Slippage sensitivity 1x/2x/3x: PF stays above 1.10 even at 3x
(1.143). Quarterly consistency within the holdout: 7/7 positive.

## 2026-08 — Anchored multi-fold walk-forward on ETH, full 3-year history

The single train/holdout split above only tested ONE window (2025-2026).
Ran 12 anchored quarterly folds (2023-Q3 through 2026-Q2) with 12h embargo
at fold boundaries, same locked config, no re-tuning.

**Result — materially weaker than the single-split test suggested:**
- 8/12 folds positive (67%) — passes the §15 60% threshold, but barely
- Only 2/12 folds individually statistically significant: 2024-Q1
  (+0.471R, p<0.001) and 2025-Q3 (+0.365R, p=0.0013)
- **2023-Q3 and 2023-Q4 were both significantly NEGATIVE**
  (-0.479R p=0.006, -0.434R p<0.001) — a regime the single-split test never
  saw because it only used 2025-2026 as holdout
- Std dev across fold means: 0.282, vs. overall pooled mean 0.038 — high
  variance relative to the average

**Root cause analysis of 2023 H2 (see conversation log):** ETH rallied
+38% over the period but via a choppy, high-volatility path (deep drawdown
to $1525 in Sep-Oct before the rally resumed). ATR percentile averaged
64.5% during this window vs 48.4% for the rest of history. Both LONG
(-0.457R, n=116) and SHORT (-0.433R, n=60) trades lost, with 62% of all
trades in the window exiting via SL — the signature of a whipsaw regime,
not a directional-bias failure.

**Conclusion:** ETH shows a real but UNSTABLE edge — strong in some
quarters, absent or negative in others, correlated with a specific kind of
choppy-high-volatility regime that occurred in 2023 H2 and may recur.

## 2026-08 — Tested fix: `atr_pct_max=0.75` volatility ceiling filter

Hypothesis: capping trades to ATR percentile <= 75% would filter out the
whipsaw regime that hurt 2023 H2 without meaningfully hurting the good
quarters (2024-Q1, 2025-Q3).

**Result: hypothesis REJECTED.** The filter made things worse across the
board:
- Consistency dropped from 8/12 (67%) to 6/12 (50%) — now FAILS the §15
  threshold
- Overall pooled net_avg_r flipped from +0.038 to **-0.031**
- 2023-Q3 got WORSE, not better (-0.435R -> -0.754R)
- The filter cut good trades (2025-Q3 n dropped 147->84) roughly as much as
  bad ones — "high volatility" is not a clean proxy for "bad trade" here;
  some of the best trades (2024-Q1, 2025-Q3) also occurred in elevated-vol
  conditions

**Conclusion:** do not re-try simple ATR-percentile ceiling filters on this
strategy without a more specific mechanism (e.g. distinguishing "high vol
because of a clean breakout" from "high vol because of chop" — a single
threshold can't do that). This experiment's script was deleted after
confirming the negative result; this log entry is the only record.

---

## Where this leaves the ETH candidate (current status)

- **Not proven robust enough for risk 2%/trade** as originally planned in
  the growth-scaling table — the 2023 H2 result shows real drawdown risk
  that the single-holdout test didn't surface.
- **Not dead either** — 2/12 quarters show genuine statistical significance
  in the positive direction, and the strategy is still the best of
  everything tested across 4 symbols x 3 strategy families x multiple SL/ADX
  configs.
- **Decision:** keep paper-trading on testnet at the current cadence,
  reduce planned live risk_pct below the 1-2% range until either (a) more
  paper-trade data accumulates, or (b) a mechanism-based (not
  threshold-based) explanation for the 2023 H2 failure is found and tested
  properly against a fresh holdout.
