# BTC-Specific Edge Search

Separate from the ETH V1 research program (ETH untouched). Date: 2026-08-25.
Script: [scripts/research_btc_edge_search.py](../../scripts/research_btc_edge_search.py).
Raw: [artifacts/btc_edge_search_summary.csv](artifacts/btc_edge_search_summary.csv).

## Discipline framing

"Find a BTC-specific edge" is the highest false-discovery-risk request in
the project — [FINDINGS.md](../FINDINGS.md) records that ad-hoc re-tuning
already burned several configs on the same data. Handled accordingly:
- **Sacred holdout** (BTC bars ≥ 2026-07-01) excluded from everything here,
  reserved for one final check of any surviving candidate. **Untouched.**
- A small number of **pre-registered, economically-motivated** hypotheses
  with a fixed gate declared before results were seen. No parameter sweep.
- **Gate** (same as FINDINGS.md's crypto screening): PF > 1.10 AND ≥60% of
  WFO folds positive on the research pool. Below → REJECT, no re-tuning.
- Hypotheses tested this run: **2** (1 control + 1 pre-registered).

## Results

| | H0: BTC V0 control | H1: + high-liquidity session filter |
|---|---|---|
| n trades | 1,436 | 744 |
| trades/year | 510 | 264 |
| win rate | 39.6% | 39.8% |
| expectancy | -0.0395R | -0.0229R |
| PF | 0.935 | 0.963 |
| MaxDD | -82.2R | -49.9R |
| WFO folds positive | 5/11 (45%) | 5/10 (50%) |
| bootstrap 95% CI | [-0.106, 0.028] | [-0.119, 0.073] |
| **gate** | **FAIL** | **FAIL** |

H1 restricts V0 entries to LONDON / OVERLAP / NY sessions only — economic
rationale: BTC is more institutionally driven than ETH, so trend signals
during thin Asia/off hours may be noisier false starts. Structural, uses
the existing `session` feature, no parameter tuning.

## Findings

1. **Full WFO confirms BTC V0 is genuinely negative, more robustly than
   the prior single-split.** FINDINGS.md reported PF 0.956 on a single
   BTC holdout; the full 11-fold WFO here lands at PF 0.935 with only 45%
   of folds positive and a negative pooled expectancy. BTC V0 is not a
   near-miss — it's a consistent, mild loser across the history. The
   earlier single-split slightly flattered it.

2. **The session filter is the first hypothesis in the entire research
   program (ETH Phases 1-6 + this) to move *every* metric in the right
   direction at once** — PF, expectancy, MaxDD, and fold-consistency all
   improved, and MaxDD nearly halved. That's a genuine, coherent signal,
   not a single cherry-picked metric.

3. **But it is not enough.** H1 still fails the gate on both criteria
   (PF 0.963 < 1.10; 50% folds < 60%) and its expectancy is still
   *negative*. "Less bad" is not "good." Trading a net-negative edge with
   lower drawdown is still trading a net-negative edge.

## Decision

| Item | Classification | Rationale |
|---|---|---|
| BTC V0 (locked config) as a live strategy | **[REJECT]** | Full WFO: PF 0.935, 45% folds positive, negative expectancy — confirms and strengthens the FINDINGS.md rejection |
| High-liquidity session filter as a structural edge | **[RESEARCH]** | Only hypothesis to improve every metric coherently, but still fails the gate with negative expectancy — a real lead, not a live candidate |

## What NOT to do next (the trap)

The natural temptation is to now stack the session filter with another
tweak, or tune *which* sessions, until BTC crosses the gate. **That is
exactly the data-mining path FINDINGS.md warns about** — with enough
combinations something will cross 1.10 by chance. Do not.

## Falsification follow-up — session effect tested on ETH (RESOLVED)

Script: [scripts/research_session_falsification_eth.py](../../scripts/research_session_falsification_eth.py).
Raw: [artifacts/eth_session_falsification_summary.csv](artifacts/eth_session_falsification_summary.csv).

The disciplined test of whether the session effect is a real
market-structure phenomenon or noise fitted to BTC's history: apply the
*same* high-liquidity-session filter to **ETH**, where V0 already works.
Pre-registered verdict rule: it must improve PF **and** expectancy **and**
fold-consistency on ETH to count as a real effect.

| | ETH V0 control | ETH V0 + session filter |
|---|---|---|
| PF | 1.041 | **1.021** ↓ |
| expectancy | +0.0246R | **+0.0124R** ↓ (halved) |
| WFO folds positive | 7/11 (64%) | **6/11 (55%)** ↓ |
| MaxDD | -79.4R | -43.3R (down only from trading less) |

**Verdict: FALSIFIED.** The session filter *degrades* ETH on all three
quality metrics — PF, expectancy, and fold-consistency all drop, and the
only thing that improves (MaxDD) does so purely because it trades ~45%
fewer times (the identical mechanical pattern seen in Phase 5's
confirmation filters — fewer trades, smaller drawdown, no per-trade
quality gain).

So the session filter helped a *losing* BTC book but hurts a *working* ETH
book. That is the signature of a variable fitted to one asset's historical
noise, not a genuine market-structure edge. **The session hypothesis is
dropped** — reclassified from [RESEARCH] to **[REJECT]**.

This is the research program working as intended: the one lead that looked
coherent on its target asset was killed by a cheap, pre-registered
out-of-asset replication test, *before* any effort went into a holdout
check or live consideration.

## Final classification (updated)

| Item | Classification |
|---|---|
| BTC V0 (locked config) as a live strategy | **[REJECT]** — full WFO negative |
| High-liquidity session filter | **[REJECT]** — improved BTC but falsified on ETH; noise, not structure |

Net result of the BTC investigation: **no BTC-specific edge found**, and
the one promising lead was correctly ruled out rather than chased.

## Round 2 (2026-08-28) — on-chain data + vol-regime, agent-team process

Trigger: human wanted to resume BTC/USDT research. Diagnosis (Research
Lead): the OHLCV+funding data was already fully spent across the 4
hypotheses above — re-testing it would violate the multiple-comparison
discipline this doc itself established. Bottleneck reframed as "no
untested data dimension available," not "search harder."

New data acquired: Coin Metrics Community CSV (free, no API key) —
[fetch_btc_onchain_coinmetrics.py](../../scripts/fetch_btc_onchain_coinmetrics.py),
written to `data/raw/BTC_onchain_coinmetrics_daily.parquet` (2009-01-03 →
2026-05-24, daily). Usable columns after dropping unavailable premium
fields: `AdrActCnt`, `TxCnt`, `CapMrktCurUSD`, `HashRate`, `SplyCur`
(dropped — deterministic issuance schedule, no signal). All on-chain
features lagged 3 days before joining to price, as a conservative
mitigation for undocumented Coin Metrics publish-lag (Skeptic
challenge — no source confirms exact finalization timing).

Three more pre-registered hypotheses, same discipline as Round 1 (no
sweep, falsification condition fixed before results seen):

| | H5: Hashrate-price divergence | H6: NVT mean reversion | H7: Vol-regime (low-vol "less noise") |
|---|---|---|---|
| Rationale | Miner hashrate resuming growth after price capitulation (≥15% DD) signals cost-floor confidence, independent of price action | NVT (mkt cap / tx count) as a P/E-style valuation proxy; extremes should mean-revert | User hypothesis: high-volatility/news-heavy periods make edge harder to find, so a low-vol filter should improve quality |
| Test | n=10 trigger events (30D/60D hashrate MA cross after DD≥15%), fwd 20D return vs unconditional baseline | Rolling 365D NVT percentile, top/bottom decile fwd return vs mid | Rolling 365D realized-vol percentile tercile split, fwd 20D return by regime |
| Result | mean +3.89% (n=10) vs baseline +3.28% — indistinguishable from noise | TOP decile (expensive) fwd 20D +5.56%, BOTTOM (cheap) −0.61% — **opposite sign to hypothesis** | Raw: LOW +0.68%/win 47% vs HIGH +5.64%/win 62%, t-test p<0.0001 — but effective independent n is only ~41-71 (not 859/1317; daily rows are autocorrelated + 20D windows overlap). Resampled non-overlapping: LOW 95%CI [-1.6%,5.5%], HIGH [1.2%,10.3%] — CIs partially overlap, no longer clean separation. HIGH mean driven substantially by a single episode (Jan–Mar 2021 bull run, +14.4%) |
| Statistical note | 90% CI for 7/10 win rate: [39.3%, 91.3%]; P(≥7/10 by chance at p=0.5) = 17.2% — not evidence | Large sample (n=644/497), sign reversal is a genuine falsification, not underpowered noise | Naive test overstated significance by treating autocorrelated daily rows as independent; execution-realism caveat also flagged — high-vol periods carry the worst slippage, which would erode the already-weak raw edge further |
| **gate** | **FAIL** (underpowered) | **FAIL** (wrong direction) | **FAIL** (inflated significance; not robust to independence correction) |

## Final classification (Round 2, 2026-08-28)

| Item | Classification | Rationale |
|---|---|---|
| Hashrate-price divergence | **[REJECT]** | n=10 trigger events; 90% CI on win rate spans 39-91%, no discriminating power |
| NVT mean reversion | **[REJECT]** | Sign reversed vs hypothesis on a well-powered sample (n=644/497) — genuinely falsified, not just noisy |
| Vol-regime ("quiet market") filter | **[REJECT]** | Apparent significance (p<0.0001) was an artifact of treating ~860 autocorrelated daily rows as independent; true effective n ≈ 41-47 episodes, CIs overlap once corrected, and the mean is dominated by one 2021 bull episode |

## Round 3 (2026-08-28) — liquidity-sweep strategy family (adapted from gold)

Trigger: human proposed treating BTC as "a different strategy family"
rather than continuing to search the same OHLCV/valuation mechanism
classes already exhausted in Rounds 1-2. Diagnosis (Research Lead):
legitimate — microstructure liquidity-sweep/capitulation mechanics had
never been tested on BTC, and arguably apply *more* strongly to BTC than
to gold, since BTC perps carry real leverage and forced liquidations
(the literal mechanism these gold strategies were built around).

Discipline: reused the LOCKED gold configs verbatim — no parameter
tuning for BTC. Script: [research_btc_liquidity_family.py](../../scripts/research_btc_liquidity_family.py).
Raw: [artifacts/btc_liquidity_family_summary.csv](artifacts/btc_liquidity_family_summary.csv).
Same sacred holdout (< 2026-07-01) and gate (PF > 1.10 AND ≥60% WFO folds
positive) as all prior rounds.

| | H8: R8 liquidation-reversal | H9: R11 wick-fill |
|---|---|---|
| Source | [gold_r8_liquidation_reversal.py](../../src/strategy/gold_r8_liquidation_reversal.py), locked params | [gold_r11_wick_fill.py](../../src/strategy/gold_r11_wick_fill.py), locked params |
| n trades | 1,230 | 291 |
| PF | 0.466 | 0.305 |
| win rate | 42.0% | 35.1% |
| expectancy | -0.448R | -0.122R |
| MaxDD | -558.78R | -35.29R |
| bootstrap p-value | 0.0000 | 0.0000 |
| WFO folds positive | 0/12 (0%) | 2/9 (22%) |
| **gate** | **FAIL** | **FAIL** |

Unlike the underpowered Round 2 hashrate hypothesis (n=10), these results
are decisive: large sample, bootstrap p<0.0001, deeply negative
expectancy on both. The wick-fill/capitulation mechanism that works on
gold (see [R8_PLAN.md](R8_PLAN.md), [R11_R13_PLAN.md](R11_R13_PLAN.md))
does not transfer to BTC with the same thresholds — plausible cause:
gold's session structure (closed markets, London/NY opens) and ATR/wick
behavior around those opens is what the k_capit/k_wick thresholds and
session filter were calibrated against; BTC trades 24/7 with a
structurally different volatility/liquidity profile, so the same
numeric thresholds may simply be miscalibrated for this asset. Retuning
those thresholds to fit BTC would reintroduce the exact data-mining risk
this document exists to prevent, so this is classified as a rejected
mechanism transfer, not a candidate for re-tuning.

## Final classification (Round 3, 2026-08-28)

| Item | Classification | Rationale |
|---|---|---|
| Liquidation-reversal (R8, locked gold params) on BTC | **[REJECT]** | PF 0.466, 0/12 WFO folds positive, p<0.0001 — decisive negative |
| Wick-fill (R11, locked gold params) on BTC | **[REJECT]** | PF 0.305, 2/9 WFO folds positive, p<0.0001 — decisive negative |

## Round 4 (2026-08-28) — BTC-native volatility-scaled thresholds

Trigger: human proposal to derive `k_capit`/`k_wick` from BTC's own
range/ATR and wick/ATR distributions (percentile-matched to where gold's
static 2.5/1.5 sit in gold's own distribution) instead of reusing gold's
raw numbers, plus dropping the gold/forex `HIGH_LIQ_HOURS` session filter
since BTC trades 24/7 with no analogous session structure. Pre-registered
before running: only `k_capit`, `k_wick`, and `session_filter` are
touched; every other locked param (`close_frac`, `shrink`, `buf`, `M`,
`tp_r_mult`, `body_frac`) stays as-is, to keep this a structural
recalibration rather than a fresh tuning pass.

Percentile-matching result: gold's k_capit=2.5 sits at the 97.4th
percentile of gold's own range/ATR distribution, k_wick=1.5 at the 99.8th
percentile of gold's wick/ATR distribution. The BTC-native thresholds at
the *same* percentiles are k_capit=2.558, k_wick=1.666 — nearly identical
to gold's raw numbers, meaning the two assets' ATR-normalized
range/wick-tail distributions are already very similar shapes. This
falsifies the "threshold is on the wrong numeric scale" theory before
even looking at backtest PnL.

| | H10a: R8, native k_capit, no session | H10b: R11, native k_wick, no session |
|---|---|---|
| n trades | 1,636 | 288 |
| PF | 0.448 | 0.347 |
| win rate | 40.5% | 36.8% |
| expectancy | -0.470R | -0.105R |
| WFO folds positive | 0/12 (0%) | 1/8 (12%) |
| bootstrap p-value | 0.0000 | 0.0000 |
| **gate** | **FAIL** | **FAIL** |

Virtually unchanged from Round 3 (PF 0.448 vs 0.466, 0.347 vs 0.305).
Confirms the failure is not a threshold-scale or session-filter artifact
— the fade-the-shock *mechanism itself* does not work on BTC.

**Cross-round pattern worth flagging (not yet a tested hypothesis):**
Round 2's H7 found high-realized-vol regimes have *positive* forward
drift on BTC (momentum, not reversion — though that finding's own
significance was later weakened by an independence-correction audit).
Rounds 3-4 now show that *fading* violent single-candle shocks
(capitulation, wick) loses decisively. Together these point toward BTC
continuing in the shock's direction rather than reverting — the opposite
mechanism from what gold's R8/R11 assume. This has an independent
economic rationale distinct from gold's (leveraged perpetuals can
produce liquidation cascades: forced closes trigger further stops in the
*same* direction, unlike unleveraged spot gold) — but it is also the
kind of pattern-noticed-after-seeing-results setup that risks post-hoc
reasoning. Treated as its own explicitly-flagged, higher-skepticism-bar
hypothesis in Round 5 below, not folded into this round's numbers.

## Final classification (Round 4, 2026-08-28)

| Item | Classification | Rationale |
|---|---|---|
| R8 with BTC-native k_capit, no session filter | **[REJECT]** | PF 0.448, 0/12 WFO folds positive — threshold/session were not the problem |
| R11 with BTC-native k_wick, no session filter | **[REJECT]** | PF 0.347, 1/8 WFO folds positive — same conclusion |

**Total BTC hypotheses tested across four rounds: 11. All rejected.**

## Round 5 (2026-08-28) — momentum continuation (mirrored fade)

Trigger: the cross-round pattern flagged at the end of Round 4 (Round 2's
high-vol positive drift + Rounds 3-4's decisive fade failures both point
the same direction). Explicitly flagged as semi-post-hoc before testing
— has an independent rationale (leveraged perp liquidation cascades push
price further in the shock's direction, unlike unleveraged spot gold),
but was noticed only after seeing prior rounds' results, so held to a
higher bar than a fully blind hypothesis.

Implementation: same R8/R11 capitulation/wick triggers, direction and
SL/TP mirrored through the entry price (point reflection), fixed 1.5R
target both arms for a clean symmetric comparison, session filter off
(established in Round 4 as immaterial).

**First run had a bug and produced a too-good-to-be-true result that was
caught before being trusted** — worth recording as the discipline
working as intended, not just the final numbers. The initial mirror
implementation flipped `sl_price`/`tp_price` by point-reflection but left
the `sl_distance` column (used to normalize R-multiples) computed from
the *original*, un-mirrored risk distance. For R8 (fixed R8 tp_r_mult=1.5)
this silently rescaled every R-multiple by 1.5x; for R11's default
wick-fill mode (asymmetric target) it could shrink the effective
denominator to near zero, producing a nonsensical R-multiple of -84.86 on
one arm (MaxDD -36,815R — physically impossible for a risk-defined stop).
The other arm's *inflated* R-multiples produced an apparent PF of 2.48,
84.7% win rate, and 10/12 positive WFO folds — a result that should have
triggered "too-good-to-be-true" skepticism on its face even before the
root cause was found. Fixed by recomputing `sl_price`/`tp_price` from the
*preserved* `sl_distance` magnitude with a fixed 1.5R target on the
mirrored side, rather than reflecting price levels directly.

| | H11a: R8 continuation (fixed) | H11b: R11 continuation (fixed) |
|---|---|---|
| n trades | 1,743 | 436 |
| PF | 0.292 | 0.805 |
| win rate | 33.1% | 43.8% |
| expectancy | -0.849R | -0.124R |
| WFO folds positive | 0/12 (0%) | 4/11 (36%) |
| bootstrap p-value | 0.0000 | 0.0308 |
| **gate** | **FAIL** | **FAIL** |

Continuation is *worse* than the fade variants (Round 3-4 PF 0.45-0.47
vs this round's 0.29 for R8). The liquidation-cascade rationale does not
survive contact with the data either.

## Final classification (Round 5, 2026-08-28)

| Item | Classification | Rationale |
|---|---|---|
| R8-trigger momentum continuation | **[REJECT]** | PF 0.292, 0/12 WFO folds positive — worse than fading the same trigger |
| R11-trigger momentum continuation | **[REJECT]** | PF 0.805, 4/11 WFO folds positive |

**Total BTC hypotheses tested across five rounds: 13. All rejected.**
Both directions (fade and continuation) of the capitulation/wick trigger
now tested and rejected, alongside trend/carry (Round 1), on-chain/
vol-regime (Round 2), and threshold recalibration (Round 4). BTC 15m/1h
directional trading shows no exploitable edge under any tested mechanism
with the data currently available. Further BTC hypotheses on this same
data should not be attempted without a genuinely new angle (see Round 3's
closing note on new data types, or non-directional approaches like
perp-spot basis, which were not in scope for this directional-edge
search).

## Round 6 (2026-08-28) — perp-spot basis / funding carry (non-directional)

Trigger: human proposal to stop searching for directional edge and
instead test a market-neutral relative-value structure (long spot, short
perp, collect funding — the "cash and carry" trade), a mechanistically
different objective from all 13 prior directional hypotheses.

**Data-quality finding surfaced during setup (Systems Audit):**
`data/raw/BTCUSDT_daily.parquet` — used as "perp" in every prior round of
this document — is mislabeled. Its close prices matched Binance SPOT
almost exactly (2,794/2,795 days byte-identical) rather than the genuine
USDⓈ-M perpetual series, which should diverge from spot by a small basis
most days. Verified by pulling real perp OHLCV directly via `ccxt.
binanceusdm` (e.g. 2026-08-24: file said 78,992.75, real perp was
78,953.0 — a ~0.05% gap, the expected basis magnitude). New verified
source: [fetch_btc_perp_binanceusdm.py](../../scripts/fetch_btc_perp_binanceusdm.py)
→ `data/raw/BTCUSDT_PERP_VERIFIED_daily.parquet`. Also fetched genuine
spot via [fetch_btc_spot_binance.py](../../scripts/fetch_btc_spot_binance.py)
→ `data/raw/BTCUSDT_SPOT_daily.parquet`.

**Open item:** Rounds 1-5 above all traded off `BTCUSDT_15m`/`_1h`/`_1m`,
not `_daily`, so their entry/exit logic itself is unaffected — but this
raises the question of whether the intraday files share the same
mislabeling, which has not yet been checked. Flagged as a follow-up
audit, not yet resolved.

**Funding-carry analysis** (short perp + long spot, collect funding,
mark-to-market the basis daily as the P&L proxy for a delta-neutral
position), using the verified perp series:

| Year | Ann. return (gross, no cost) | Sharpe (gross, no cost) |
|---|---|---|
| 2023 (partial, from Aug) | +8.8% | 13.0 |
| 2024 | +12.0% | 15.2 |
| 2025 | +5.1% | 15.1 |
| 2026 (through Aug) | +2.4% | 7.2 |

Concentration check: top 10 days contribute only 8.8% of total cumulative
P&L — not a fluke driven by a handful of events (contrast with Round 2's
H7, which was ~40% attributable to one 2021 episode). Positive in every
year measured. This is the first BTC hypothesis across all 6 rounds that
is not immediately and decisively rejected on the raw numbers.

**Why it still doesn't clear the bar for live:**
1. **Declining trend** — gross annualized return fell from +12.0% (2024)
   to +2.4% (2026 ytd), consistent with a well-known institutional trade
   (crypto cash-and-carry) getting progressively arbitraged away.
2. **Realistic execution cost estimate cancels the edge.** Maintaining a
   dollar-neutral position requires periodic rebalancing as spot/perp
   values drift apart; a conservative estimate of weekly rebalancing at
   ~0.15% round-trip taker cost implies ~7.8%/year in costs — roughly
   equal to the *full-period* average gross carry (7.28%/yr) and larger
   than the most recent year's gross carry (2.4%). Net of realistic
   costs, the strategy is at or below breakeven in current conditions.

## Classification (Round 6, 2026-08-28)

| Item | Classification | Rationale |
|---|---|---|
| Perp-spot funding carry (delta-neutral) | **[RESEARCH]** — not [REJECT], not live-ready | Genuinely positive, non-concentrated, multi-year-consistent gross signal — but shrinking over time and roughly cancelled by realistic rebalancing costs in the current (2026) regime. Worth re-checking periodically (e.g. quarterly) in case the funding-cost gap widens again; not worth building execution infrastructure for at today's thin margin. |
| `BTCUSDT_daily.parquet` labeled as perp | **[DATA BUG — FLAGGED, NOT YET FIXED]** | Confirmed spot data mislabeled as perp; intraday files (`15m`/`1h`/`1m`, used by all directional strategies in this doc) not yet checked for the same issue |

**Orderbook depth / order-flow-imbalance data collection started
in parallel** (proposal item 1) — [collect_btc_orderbook.py](../../scripts/collect_btc_orderbook.py),
polling Binance perp L2 depth + last trade every 5s to
`data/raw/orderbook/BTCUSDT_orderbook_YYYY-MM-DD.csv`, running as a
detached background process from 2026-08-28. Cannot be backfilled;
needs roughly 2-3 months of continuous collection before there's enough
history for a depth-imbalance / short-horizon-drift hypothesis. Not yet
set up as a cron/launchd service — currently survives only as long as
the machine stays on and the process isn't killed. Resume command after
a reboot: `./scripts/resume_btc_orderbook_collector.sh`.

## Round 6 addendum — audit widened to the live ETH/XRP config, found and fixed two real bugs

Trigger: human asked to point the same agent-team process at the live
paper-trading config (`scripts/run_signal_cycle.py`) rather than more BTC
hypotheses. Not a BTC finding, but landed in this doc because it was
triggered mid-session by the same Round 6 data-quality audit and follows
the same process (Systems Audit → Skeptic → Trading Lead).

**Bug 1 — EV gate used ETH's stats for XRP too.** `src/live/ev_estimate.py`
had one hardcoded `HISTORICAL_WIN_RATE`/`AVG_WIN_R`/`AVG_LOSS_R` set,
labeled "ETH CAL fold," applied unconditionally to every symbol in
`estimate_ev()`. `run_signal_cycle.py` calls this same function for both
ETH and XRP with no branch. XRP has its own, materially different,
documented stats (docs/FINDINGS.md: XRP fires in a different regime mix
than ETH, PF 1.18 vs ETH's own numbers) — so XRP trades were being
gated on the wrong strategy's economics. Fix: `estimate_ev()` now takes
a `symbol` argument and looks up `SYMBOL_STATS[symbol]`, a dict with one
entry per symbol; a missing symbol raises `KeyError` instead of silently
falling back to another symbol's numbers. XRP's own CAL-fold stats
(same window, same `V0_CONFIG`, computed on `XRPUSDT_15m/1h/1m`, n=194)
were computed for the fix: `{win_rate: 0.4639, avg_win_r: 1.5309,
avg_loss_r: 0.9985}`.

**Bug 2 — ETH's own EV-gate stats were stale.** Sanity-checking the fix
by recomputing ETH's CAL fold with the *current* pipeline surfaced that
it no longer matched the hardcoded constants (0.4389/1.637/0.9773 vs
recomputed 0.4333/1.5496/1.0547). Root cause: commit `4545fa4` fixed
`src/backtest/costs.py`'s slippage model from a fixed $0.5/side
(calibrated for BTC's price level) to a proportional 2bps-of-price model
— correct for multi-symbol use, but ETH's EV-gate constants were never
re-derived after that fix landed, so the live gate had been running on
understated trading costs since 2026-08-26.

**Consequence surfaced by a full quarterly WFO re-check** (13 folds,
2023Q3-2026Q3, current cost model, `V0_CONFIG={"adx":35,"sl":2.5}`):
ETH's TRUE full-period gross edge is 0.038R (n=1,482), only 3/13
quarters individually clear the 0.15R gate threshold, and multiple
2023 quarters are sharply negative (-0.44R, -0.42R). The old (stale)
constants implied a 0.170R gross edge — comfortably above the gate.
Deploying the corrected constants means ETH will fail the EV gate on
most/all signals going forward.

**Trading Lead decision:** deploy the corrected constants for both
symbols anyway. The EV gate rejecting most ETH signals is the gate
doing its job with accurate inputs, not a malfunction to route around —
explicitly ruled out lowering `EV_THRESHOLD_R` or retuning `V0_CONFIG`
to force ETH signals back through the gate, since that is the exact
curve-fit-to-rescue-a-failing-strategy pattern this project's discipline
exists to prevent (same principle as the "no re-tuning to rescue a
rejected hypothesis" rule used throughout this document). If ETH is
meant to trade actively again, that requires new research into why its
true (cost-corrected) edge collapsed, not a constants patch.

Deployed: `src/live/ev_estimate.py` (`SYMBOL_STATS` dict, per-symbol),
`scripts/run_signal_cycle.py` (passes `symbol` into `estimate_ev`),
`tests/test_ev_estimate.py` (regression tests for both bugs — symbol
cross-contamination and the "ETH no longer clears the gate" behavior).
8/8 tests passing.

## Open items carried forward

1. Whether `BTCUSDT_15m`/`1h`/`1m` (used by all of Rounds 1-5's
   directional strategies) share the `_daily` file's spot-mislabeled-as-
   perp bug — not yet checked.
2. Whether ETH's/other symbols' intraday files have the same mislabeling
   — XRP's was checked and confirmed clean (real perp, not spot); ETH's
   was not checked.
3. Perp-spot basis carry (Round 6 main finding) reclassified as
   [RESEARCH] — worth a periodic (e.g. quarterly) recheck in case the
   funding-cost gap widens again, not worth building execution
   infrastructure for at today's thin post-cost margin.
4. ETH's true, cost-corrected edge instability (0.038R gross, 3/13 folds
   passing) is a standing open question for the ETH research program,
   separate from this BTC document — flagged here because it was found
   during this session, not investigated further here.
