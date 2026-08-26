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

---

## 2026-08 — XAU (gold) evaluated as a new instrument — price-only edge FALSIFIED

Motivation: Binance USDⓈ-M futures lists `XAU/USDT` perp; user asked whether
the system could trade gold. The connector/pipeline is symbol-parameterized,
so the real question was whether any tradeable edge exists on gold.

### Data
- Binance `XAU/USDT` perp only lists from **2025-12-11** (~8.5 months) — far
  too short to validate. First pass on it was labelled EXPLORATORY only.
- Sourced long history from **Dukascopy spot `XAU/USD`, 2006-2026 (~20yr)**:
  `data/raw/XAUUSD_{15m,1h,1m}.parquet` (M15 505k / H1 127k / M1 7.38M bars),
  fetched via `scripts/fetch_xau_dukascopy.py`. Gitignored (research-only,
  never deployed — live path fetches OHLCV from the exchange, reads no
  parquet). Saved as `XAUUSD_*` to sit alongside (not overwrite) the perp
  `XAUUSDT_*`.
- **CAVEAT:** Dukascopy is SPOT bid feed, not the Binance perp. Used for
  edge/regime discovery. Any survivor would still need re-validation on the
  perp's real microstructure. Research costs used Binance-perp taker fee +
  slippage + a synthetic ~6.7%/yr funding carry (measured perp mean).

### 20-year characterization (`scripts/research_xau_characterization_20y.py`)
- **Gold is RANGE ~79% of the time in EVERY year 2006-2026** (full sample
  TREND 20.7% / RANGE 79.3% at ADX35 on H1). The 8.5-month sample was not a
  fluke — trend-following is structurally disadvantaged on gold.
- Volatility concentrates in **London-NY OVERLAP** (~11.9 bps/bar vs Asia
  5.8). Weekend is near-dead (real gold market hours).
- M15 return autocorr(lag1) is **negative in ~19/21 years but tiny (−0.018)**
  — a hint toward mean-reversion, but economically marginal.

### Trend-following (exploratory, 8.5mo perp only)
Locked ETH-derived V0 (ADX35/SL2.5), plus session / weekday / daily-trend
filters (H0-H4). All LOSE (best −0.15R, PF 0.77). Adding a Daily top layer
did NOT help — H1 and Daily trend agreed ~90-95% of the time (collinear, no
new information). Weekday-only filter helped (weekend flow is toxic) but
still unprofitable.

### Mean-reversion — full 20yr FALSIFICATION (`scripts/research_xau_mr_falsification.py`)
Protocol: pre-registered variants, sacred holdout >= 2025-01-01 (gold's big
bull), quarterly WFO + 12h embargo, gate PF>1.10 AND >=60% folds positive.

| variant | n | win% | exp | PF | folds+ | gate |
|---|---|---|---|---|---|---|
| R0 MR default (entry_z=2, RANGE) | 42,053 | 33% | −0.99R | 0.17 | 0/76 | FAIL |
| R1 + high-liq sessions | 28,309 | 34% | −0.87R | 0.21 | 0/76 | FAIL |
| R2 + sessions + daily-trend guard | 14,167 | 35% | −0.82R | 0.22 | 0/76 | FAIL |

All FAIL hard: PF 0.17-0.22, **0 of 76 quarterly folds positive**, p=0.0000.
Guards reduce the bleed (exp −0.99→−0.82R, MaxDD −41k→−11.6kR) but come
nowhere near profitable. **Sacred holdout left untouched** (nothing passed
the pool gate, per protocol).

Reconciliation with the negative autocorr: it is a 1-bar (15-min) effect and
tiny; the MR strategy fades a 2σ extreme with up to 12h hold — a different
horizon at which gold's moves persist enough that fading loses after costs.
**Micro mean-reversion ≠ tradeable swing mean-reversion.**

### Conclusion
**No price-only edge (trend OR mean-reversion) survives on XAU with the
current feature set.** Both families are now falsified — mean-reversion
rigorously over 20 years. This is a robust negative result, not an 8.5-month
artifact.

The tradeable structure of gold is not in M15/H1 price patterns; it is
**macro-driven (DXY / real yields / Fed)** — signals the current features
cannot see.

**Decision:** stop price-only XAU work; keep resources on the ETH/crypto
program. Revisit XAU ONLY if a macro-feature layer (at minimum DXY) is built
as a genuinely orthogonal top-of-stack — a separate data-pipeline project,
not a parameter change. Do not re-run price-only trend/MR scans on XAU; this
entry is the settled record.

---

## 2026-08 — 2nd-symbol search: BTC-specific edge (none) + XRP candidate (marginal)

Goal (user): add a 2nd live symbol to increase trade opportunities / capital
deployment (NOT diversification). Current live symbol is ETH only.

### Slippage bug found (affects all low-priced coins)
`src/backtest/costs.py` uses a FIXED `SLIPPAGE_PRICE_UNITS = 0.5` (0.5 USD per
side, calibrated for BTC ~$60k). This is nonsensical for low-priced coins:
DOGE at $0.06 with a $0.000168 stop got ~5,900 R of "slippage" per trade,
producing impossible −477 R average results in the first screen. ETH/BTC are
unaffected (0.5 USD is negligible at their price).

**FIXED (2026-08, TDD):** `src/backtest/costs.py` now uses `SLIPPAGE_BPS = 2.0`
(2 bps/side of price, proportional) via `slippage_cost_r(sl_distance,
entry_price, slippage_bps)`. Callers updated (`apply_costs`, live
`ev_estimate.py`, `eth_walkforward_and_slippage.py`). ETH edge re-confirmed
under the new model: holdout PF 1.276 (was 1.278), p=0.001, CI [0.060, 0.246]
— unchanged, since 2 bps ~= ETH's old effective 1.7 bps. Regression tests added
in `tests/test_costs.py` (proportional + low-priced-coin sanity).

### Candidate screen (locked V0 ADX35/SL2.5, no tuning, corrected slippage)
Pre-registered shortlist (fixed before results): XRP, DOGE, ADA, LINK, LTC,
AVAX (6 most-liquid long-listed perps not already tested). Gate = holdout
PF>1.10 AND full-history WFO >=60% folds positive AND holdout bootstrap p<0.05.

| symbol | hold PF | exp_r | WFO folds+ | boot p | gate |
|---|---|---|---|---|---|
| ETH (ref) | 1.28 | +0.15 | 8/12 (67%) | 0.001 | PASS |
| BTC (ref) | 0.87 | −0.08 | 4/12 | 0.096 | fail |
| XRP | 1.18 | +0.10 | 7/12 (58%) | 0.047 | near-miss |
| LINK | 1.17 | +0.09 | 7/12 (58%) | 0.063 | near-miss |
| AVAX | 0.89 | −0.07 | 8/12 (67%) | 0.136 | fail |
| DOGE | 0.86 | −0.09 | 4/12 | 0.066 | fail |
| ADA | 0.83 | −0.10 | 6/12 | 0.043 | fail |
| LTC | 0.75 | −0.17 | 1/12 | — | fail |

None cleared the full gate. XRP and LINK are genuine near-misses (positive
expectancy, PF>1.17), failing only on WFO consistency (58% vs 60%).

### BTC-specific edge search — 4 pre-registered hypotheses, ALL fail
User chose to pursue a BTC-specific edge rather than force V0 onto BTC. Tested
(sacred holdout 2026-07-01, gate PF>1.10 AND >=60% yearly buckets AND p<0.05):

| hypothesis | PF | exp_r | years+ | gate |
|---|---|---|---|---|
| V0 control | 0.94 | −0.04 | — | fail |
| V0 + high-liq sessions | 0.96 | −0.02 | — | fail |
| CME weekend gap-fill | 0.76 | −0.17 | 1/4 | fail |
| Funding-extreme contrarian | 0.81 | −0.41 | 2/4 | fail |

Pattern: 2023-2024 strongly negative on every hypothesis, 2025-2026 mildly
positive — if a BTC edge is emerging it is recent and not yet robust. CME
gap-fill fill-rate was only 41% after costs ("gaps always fill" folklore does
not hold 2023-2026). **Conclusion: BTC is efficient/hard at M15-daily horizons
for these mechanisms; no BTC-specific edge found. Stop testing more BTC
hypotheses (multiple-comparison budget spent — 4 used).** Scripts:
`research_btc_edge_search.py`, `research_btc_cme_gap.py`.

### XRP full ETH-grade vetting (`research_xrp_vetting.py`)
XRP given the exact battery ETH passed:
- **WFO 12 folds:** 7/12 positive (58%), std 0.239; 2 folds significant
  positive (2024Q1 +0.48***, 2026Q1 +0.49***), 1 significant negative
  (2025Q4 −0.26*). Same "few big quarters carry it" profile as ETH.
- **Holdout:** PF 1.185, +0.104R, p=0.047, 95% CI [0.001, 0.205] — passes but
  the CI lower bound essentially touches zero (fragile).
- **Slippage sensitivity:** PF 1.19 / 1.13 / 1.07 at 1x/2x/3x (2/4/6 bps).
  **Breaks below 1.10 at 3x** — ETH held 1.14 at 3x. XRP is less slippage-
  robust AND less liquid, so real-world slippage risk is higher.
- **Long/short:** LONG PF 1.40 (+0.21R) strong; SHORT PF 1.055 (+0.03R) barely
  positive — edge is mostly long-side.
- **Overlay vs ETH (favourable surprise):** fold-mean correlation only +0.19.
  XRP does NOT share ETH's 2023 H2 weakness (2023Q3: XRP +0.34 vs ETH −0.40).
  Underlying prices correlate ~0.8 daily, but the V0 *strategy P&L* on XRP vs
  ETH is nearly uncorrelated (setups fire in different regimes). So XRP adds
  both opportunities AND genuine equity-curve diversification.

**Verdict:** XRP is a real but TIER-2 candidate — weaker and more fragile than
ETH (WFO 58%, CI touches 0, fails at 3x slippage, edge concentrated in a few
quarters and on the long side), but with a genuinely low correlation to ETH's
strategy returns. If added, treat it accordingly: paper-trade first, reduced
risk_pct (e.g. 0.25% vs ETH's 0.5%), and fix the shared slippage model before
any live use. Not an ETH equal — a cautious satellite, not a co-anchor.

**Decision:** BTC shelved (no edge). XRP is the only viable 2nd-symbol
candidate found, at reduced conviction. Engineering prerequisites for adding
any 2nd symbol: (1) price-proportional slippage fix in costs.py [DONE], (2) multi-
symbol support in run_signal_cycle.py [DONE] — refactored to a `SYMBOLS` config
list (per-symbol config + base_risk_pct), each symbol run in an isolated
`run_symbol_cycle()` (one symbol's failure can't block the rest), and the
rolling-winrate risk guard now reads per-symbol history via
`recent_closed_r_multiples()`. ETH stays the only active entry; XRP is present
commented-out at 0.25% risk, ready to enable for paper-trading when chosen.
