# ETH V1 Research Report — Increasing Opportunity Without Degrading Edge

Living document, driven by [PLAN_CUSTOM.md](PLAN_CUSTOM.md). Updated
incrementally as each research phase completes. The live V0 config
([../STRATEGY_RISK_SPEC.md](../STRATEGY_RISK_SPEC.md)) is the unchanged
control group throughout — nothing here has been promoted to production.

## Methodology guardrails (read before adding any experiment)

- **Sacred holdout**: `2026-07-01` onward (~8 weeks) is excluded from every
  experiment below. Everything before it ("research pool", 2023-08-25 to
  2026-06-30, 2.85 years) is fair game for exploration, because prior work
  ([FINDINGS.md](../FINDINGS.md)) already consumed the full 2023-2026 history
  across screening + 12-fold WFO + the ATR-ceiling-filter test — that data is
  not a clean holdout anymore under strict anti-data-mining rules. Only the
  final selected variant(s), decided *without ever inspecting the sacred
  holdout beforehand*, get to be scored against it once.
- **Live config is the control group.** No experiment below changes
  `LIVE_ADX_THRESHOLD=35`, SL/TP, or risk. All research scripts derive their
  own copies of thresholds rather than importing/mutating
  `src/strategy/v0_rules.py`.
- Track hypothesis count as we go (§9 of PLAN_CUSTOM — multiple-testing
  discipline): **1 diagnostic run (Phase 0) + 4 entry-trigger variants
  (Phase 2) + 3 regime-filter variants (Phase 1) + 1 second-strategy
  candidate (Phase 3) + 2 RANGE mean-reversion variants (Phase 4) + 2
  multi-timeframe-confirmation variants (Phase 5). 0/12 strategy variants
  passed.**

---

## Phase 0 — Current V0 Opportunity Funnel (research question 1)

Script: [scripts/research_funnel_diagnosis.py](../../scripts/research_funnel_diagnosis.py).
Run on the research pool only (99,699 warmed-up M15 bars, 2.85 years).

| Stage | Bars kept | % of warmed-up bars | Drop from previous stage |
|---|---|---|---|
| M15 bars (warmed up) | 99,699 | 100.0% | — |
| → H1 TREND regime (ADX>35 & trend-strength>0.5) | 21,428 | 21.5% | **-78.5%** |
| → valid H1 direction (bullish/bearish, always true within TREND) | 21,428 | 21.5% | -0.0% |
| → EMA20 pullback candidate (cross trigger) | 1,412 | 1.4% | **-93.4%** |
| → ATR filter (no-op at live defaults) | 1,412 | 1.4% | -0.0% |
| → candle-quality filter (no-op at live defaults) | 1,412 | 1.4% | -0.0% |

LONG candidates: 682 · SHORT candidates: 730 · ≈**496 eligible setups/year**
pre-EV-gate (order-of-magnitude consistent with the ~147 trades/quarter seen
in the 2025-Q3 WFO fold in FINDINGS.md).

### Finding: the regime filter is NOT the primary bottleneck

PLAN_CUSTOM explicitly warned not to assume ADX>35 is the bottleneck — and
it isn't. The TREND regime filter removes 78.5% of bars, which is expected
and economically sensible (ranging markets are the majority of the time by
construction). But **within TREND regime bars, the H1-direction filter costs
nothing (0% drop)** — once ADX/trend-strength say "TREND", the H1 EMA-slope
sign is essentially always decisive.

**The real bottleneck is the EMA20-pullback cross trigger itself: -93.4%
of already-TREND, already-directional bars.** This is a single-bar,
exact-cross condition (`prev_dist_ema20 <= 0` then `dist_ema20 > 0` on the
same bar) — a narrow trigger by construction, since it only fires on the
one bar where price re-crosses EMA20. The ATR and candle-body filters
currently contribute **zero** attrition because their live thresholds
(`atr_pct∈[0,1]`, `min_body_ratio=0`) are no-ops — they exist in the code as
hooks but aren't actually restricting anything live today.

### Implication for the rest of the research plan

This directly prioritizes PLAN_CUSTOM's research questions:
- **Q3 (EMA pullback definition)** is the highest-leverage place to look for
  more opportunity — it's the actual bottleneck, not Q2 (regime threshold).
- **Q2 (ADX threshold sensitivity)** is still worth testing since 78.5%
  attrition is a big number in absolute terms, but should not be expected
  to move trade count much unless it also changes which bars are
  "TREND" at the moment the EMA20 cross would otherwise occur — i.e. a
  looser ADX threshold only helps if it recovers pullback-cross bars that
  are currently sitting just outside the TREND window. Phase 1 should
  measure that directly, not just "how many more TREND bars."
- The ATR/candle-quality filters being no-ops live means there is currently
  **unused, already-built filtering capacity** — worth deciding deliberately
  (activate for quality, or leave as pure hooks) rather than by accident.

---

## Phase 1 — Regime filter sensitivity (research question 2)

Script: [scripts/research_phase1_adx_sensitivity.py](../../scripts/research_phase1_adx_sensitivity.py).
Raw output: [artifacts/phase1_adx_summary.csv](artifacts/phase1_adx_summary.csv).

Keeps the **winning entry trigger from Phase 2** (V0's exact single-bar
EMA20 cross — every broadened alternative underperformed it) and the
locked SL/TP. Only the regime classification changes: `trend_strength`
threshold (0.5) held constant throughout, since PLAN_CUSTOM's variants
here are specifically about the ADX side.

| Variant | TREND+dir bars (pre-trigger) | n trades | trades/yr | expectancy (R) | PF | WFO folds positive | bootstrap |
|---|---|---|---|---|---|---|---|
| **V0 baseline (ADX>35)** | 22,488 (22.5%) | 1,412 | 502 | **+0.0246** | **1.041** | **7/11 (64%)** | not sig. |
| A: ADX>30 | 32,820 (32.9%) | 2,087 | 737 | -0.0695 | 0.889 | 5/11 (45%) | **p=0.0144, CI [-0.123,-0.015] — significantly negative** |
| B: ADX>25 | 46,624 (46.7%) | 2,980 | 1,052 | -0.0957 | 0.850 | 3/11 (27%) | **p<0.0001, CI [-0.142,-0.049] — significantly negative** |
| C: continuous (ADX percentile >70%) | 27,688 (27.7%) | 1,732 | 612 | -0.0063 | 0.990 | 6/11 (55%) | not sig. |

### Finding: loosening ADX doesn't just dilute the edge — it inverts it, monotonically

This is a sharper result than Phase 2. Loosening the regime filter isn't
neutral-to-mildly-bad like the trigger variants were — it's **actively,
statistically significantly harmful**, and gets worse the more it's
loosened:

- ADX>30 and ADX>25 both produce a bootstrap 95% CI **entirely below
  zero** — i.e. these aren't "not proven to work," they're "proven not to
  work" on this data (p=0.0144 and p<0.0001 respectively)
- The degradation is monotonic: 35→30→25 tracks expectancy
  +0.0246→-0.0695→-0.0957 and fold-positive rate 64%→45%→27% in a straight
  line. ADX>25 fails the §15 threshold outright (27% vs 60% required) —
  worse than any variant tested so far in this research program
- More TREND bars pass through at looser thresholds (22.5%→32.9%→46.7% of
  pool bars), confirming the filter *is* doing real work — the bars it
  excludes at ADX 25-35 are net-harmful to trade, not just neutral noise
  that a stricter trigger further downstream could clean up
- The **continuous percentile-based variant (C)** — a genuinely different
  *mechanism* (relative "top 30% of recent ADX" rather than an absolute
  cutoff), not just a looser version of the same threshold — comes much
  closer to neutral (expectancy -0.0063, PF 0.990, not statistically
  significant either way) but still underperforms the fixed ADX>35
  baseline on every metric, including fold consistency (55% vs 64%)

### Decision

| Variant | Classification | Rationale |
|---|---|---|
| A_ADX30 | **[REJECT]** | Statistically significant negative expectancy (p=0.0144); fails §15 consistency |
| B_ADX25 | **[REJECT]** | Statistically significant negative expectancy (p<0.0001); fails §15 consistency badly (27%) |
| C_continuous_adx_pctl70 | **[REJECT]** | Not significantly negative, but strictly worse than control on every metric — no evidence it's an improvement |

**Combined with Phase 2: two independent research questions (entry trigger
breadth, regime filter breadth) both point the same direction — the live
V0 config's apparent selectivity is not incidental over-filtering, it's
load-bearing.** Neither "trade the same setups more often" (Phase 2) nor
"trade a wider set of regimes" (Phase 1) recovered a better or even
comparable edge to the locked baseline.

## Phase 2 — EMA pullback definition variants (research question 3)

Script: [scripts/research_phase2_ema_variants.py](../../scripts/research_phase2_ema_variants.py).
Raw output: [artifacts/phase2_variant_summary.csv](artifacts/phase2_variant_summary.csv).

Same regime filter (ADX>35), same SL (2.5x ATR), same TP (2R) as live —
**only the pullback-trigger definition changes**, per the risk rule (no
SL/TP/risk changes). Evaluated on the research pool only (< 2026-07-01),
quarterly anchored WFO with 12h embargo, bootstrap significance on pooled
trades.

**Methodology note**: PLAN_CUSTOM's variants A ("touch EMA20 then close
above") and B ("low penetrates EMA20 but close remains above") describe the
same mechanic given only OHLC bar data (no sub-bar path) — implemented and
reported once as `A_touch_then_close_above` rather than run twice as
duplicate hypotheses (which would have inflated the multiple-testing count
without adding information).

| Variant | n | trades/yr | win rate | expectancy (R) | PF | MaxDD (R) | WFO folds positive | bootstrap p |
|---|---|---|---|---|---|---|---|---|
| **V0 baseline** (control) | 1,412 | 502 | 42.6% | **+0.0246** | **1.041** | -79.4 | **7/11 (64%)** | 0.466 |
| A: touch-then-close-above | 3,406 | 1,210 | 40.3% | -0.0127 | 0.979 | -182.8 | 6/11 (55%) | 0.590 |
| C: ±0.3 ATR tolerance band | 2,282 | 811 | 41.5% | -0.0107 | 0.982 | -146.1 | 5/11 (45%) | 0.681 |
| D: pullback within 3 bars | 3,167 | 1,125 | 41.0% | +0.0056 | 1.009 | -179.1 | 6/11 (55%) | 0.804 |
| E: multi-bar + momentum confirm | 2,120 | 753 | 39.3% | -0.0372 | 0.940 | -128.5 | 6/11 (55%) | 0.198 |

None of the trades counted here have passed the EV gate or live filters —
this table isolates the effect of the entry trigger alone.

*(Note: this independent re-implementation of the V0 baseline — built from
scratch in this script rather than importing `v0_rules.py` — landed at PF
1.041/expectancy +0.0246R/64% fold-positive on the research-pool window,
consistent with the pooled net_avg_r +0.038 and 8/12 (67%) reported for the
full 2023-2026 history in [FINDINGS.md](../FINDINGS.md); the small
difference is expected from excluding the sacred holdout quarter and
quarter-boundary alignment. This cross-check gives confidence the variant
harness isn't silently different from the production logic it's compared
against.)*

### Finding: every broadened trigger definition trades more but worse

All four variants increase trade count by **1.5x–2.4x** (as expected — they
were designed to relax the exact single-bar-cross condition identified as
the Phase 0 bottleneck). **None of them improve expectancy, PF, or WFO
consistency — all four underperform the V0 control on every quality metric
that matters:**

- Expectancy: only D stays barely positive (+0.0056R vs baseline's
  +0.0246R — less than a quarter of the edge); A, C, E go **negative**
- PF: none reach 1.0 except the baseline (1.041) and D (1.009, essentially
  breakeven)
- WFO consistency: **every variant drops below the baseline's 64%
  fold-positive rate** — C is worst at 45%, which fails the §15 60%
  threshold outright
- MaxDD scales roughly with trade count (as expected for more, weaker-edge
  trades) — 1.6x–2.3x worse than baseline in R terms

Even variant E, explicitly designed to be *more* selective (multi-bar
pullback + momentum confirmation, not just a looser single-bar condition),
still ended up trading 50% more often than baseline while producing the
**worst** expectancy of the group (-0.0372R) and the lowest win rate
(39.3%). Requiring a "cleaner" pattern didn't recover quality — it just
found a different, larger set of lower-quality setups.

**Conclusion: the EMA20 exact-cross trigger is narrow, but its narrowness
is doing real work, not just needlessly filtering out good trades.** The
extra candidates every variant picks up skew toward chop/false starts
rather than genuine trend-continuation. This is a case where PLAN_CUSTOM's
anticipated "correct answer" applies directly: **do not broaden the
pullback trigger** — none of the four hypotheses tested here should be
promoted.

### Decision

| Variant | Classification | Rationale |
|---|---|---|
| A_touch_then_close_above | **[REJECT]** | Worse expectancy, PF<1, fold-consistency below §15 threshold |
| C_tolerance_band_0.3atr | **[REJECT]** | Worst fold-consistency (45%) of all variants tested |
| D_pullback_within_3bars | **[REJECT]** | Least-bad of the four but still strictly worse than control on every metric; not a genuine improvement |
| E_multibar_momentum_confirm | **[REJECT]** | Worst expectancy and win rate despite being designed for more selectivity, not less |

## Phase 3 — Second TREND strategy validation (research question 4)

Script: [scripts/research_phase3_breakout_eth.py](../../scripts/research_phase3_breakout_eth.py).
Raw output: [artifacts/phase3_breakout_summary.csv](artifacts/phase3_breakout_summary.csv).

Tests **one** hypothesis — [src/strategy/breakout.py](../../src/strategy/breakout.py)'s
existing Donchian(20) breakout, completely unchanged (Donchian period 20,
H1 ADX>20 own trend confirmation, SL=2.0x ATR, TP=2R) — independently
validated on **ETH specifically** for the first time (it was previously
only tested on BTC single-split, PF≈0.52, rejected — see
[FINDINGS.md](../FINDINGS.md)). No parameter sweep, per PLAN_CUSTOM's rule
against selecting on tuned historical return.

| | V0 baseline (reference) | Breakout (Donchian20, ADX>20) on ETH |
|---|---|---|
| n | 1,412 | **5,632** |
| trades/year | 502 | 1,984 |
| win rate | 42.6% | 28.6% |
| expectancy | +0.0246R | **-0.3597R** |
| PF | 1.041 | **0.559** |
| MaxDD | -79.4R | **-2,027.6R** |
| WFO folds positive | 7/11 (64%) | **0/12 (0%)** |
| bootstrap 95% CI | [-0.041, 0.094] | **[-0.393, -0.326]** — entirely negative, p<0.0001 |

### Finding: breakout fails on ETH even more decisively than it failed on BTC

This is the clearest rejection in the research program so far. Every
single quarterly WFO fold was negative (0/12, vs V0's 7/11) — not "weak,"
uniformly losing. The bootstrap 95% CI sits entirely below zero
(`[-0.393, -0.326]`, p<0.0001), meaning the negative expectancy is not
sampling noise; it's a robust, statistically confident loss. (Note: the
`significant_at_5pct` flag from `bootstrap_mean_test` is `False` here
because that function only tests for significance in the *positive*
direction — the CI being entirely negative is the relevant evidence for a
significant *negative* result, and should be read directly rather than
from that flag.)

The Donchian breakout does generate far more raw opportunity (1,984
trades/year vs V0's 502) — confirming that "more trades" is trivially
available if quality is not the constraint — but every extra trade comes at
a steep cost: MaxDD of -2,028R dwarfs V0's -79R by more than 25x.

**Overlap check**: 29.4% of breakout trades' holding windows overlap a
concurrent V0 trade. Even if breakout had passed (it didn't), this is
low enough to have counted as a reasonably independent situation rather
than a duplicate of V0 — but that's moot given the outright rejection.

### Decision

| Variant | Classification | Rationale |
|---|---|---|
| Breakout_Donchian20_ADXmin20_ETH | **[REJECT]** | 0/12 WFO folds positive, PF 0.559, statistically significant negative expectancy (CI entirely below zero) — worse on ETH than it was on BTC |

**PLAN_CUSTOM listed volatility breakout and momentum continuation as
further candidates for this research question.** Given how decisively the
Donchian variant failed (not a marginal miss — a uniform, high-confidence
loss across every fold), and per the anti-overfitting instruction to not
keep testing until something looks good, these are noted as open next
steps (§14) rather than run speculatively in this pass — see the "exact
experiments to run next" section for the specific, falsifiable form each
should take before being tried.

## Phase 4 — RANGE opportunity research (research question 5)

Script: [scripts/research_phase4_range_meanreversion.py](../../scripts/research_phase4_range_meanreversion.py).
Raw output: [artifacts/phase4_range_summary.csv](artifacts/phase4_range_summary.csv).

RANGE regime bars make up **78.6%** of the research pool — by far the
largest untapped opportunity surface, since V0 doesn't trade RANGE at all.
Tests two disciplined hypotheses (not a continuous `entry_z` sweep, per
PLAN_CUSTOM's explicit instruction not to optimize `entry_z` to maximize
backtest profit):

- **A — baseline**: [src/strategy/mean_reversion.py](../../src/strategy/mean_reversion.py)
  unchanged (`entry_z=2.0`, SL=1.5x ATR, TP=1.5R, RANGE only). Previously
  only tested on BTC (single-split, PF≈0.52, rejected); this is its first
  independent ETH validation.
- **B — reversion-confirmation**: economically motivated variant — instead
  of entering the instant price crosses the extreme-deviation threshold
  (risking a "falling knife" that keeps extending), requires the extreme
  to have occurred within the last 3 bars **and** the current bar to show
  contraction back toward EMA20 (an actual reversal in progress).

| | V0 baseline (reference) | A: baseline mean-reversion | B: reversion-confirmation |
|---|---|---|---|
| n | 1,412 | 7,639 | 7,683 |
| trades/year | 502 | 2,691 | 2,703 |
| win rate | 42.6% | 38.9% | 39.7% |
| expectancy | +0.0246R | **-0.2501R** | **-0.2321R** |
| PF | 1.041 | 0.657 | 0.677 |
| MaxDD | -79.4R | -1,918.7R | -1,790.4R |
| WFO folds positive | 7/11 (64%) | **0/12 (0%)** | **0/12 (0%)** |
| bootstrap 95% CI | [-0.041, 0.094] | [-0.277, -0.224], p<0.0001 | [-0.259, -0.206], p<0.0001 |
| overlap with V0 trades | — | 5.6% | 5.9% |

### Finding: RANGE mean-reversion fails as decisively as breakout did, and the "fix" doesn't fix it

Both variants lose on **every single quarterly fold** (0/12), with bootstrap
CIs entirely and substantially below zero — the same severity of rejection
as Phase 3's breakout result, not a marginal miss. Adding the
reversion-confirmation logic (variant B) moved expectancy from -0.250R to
-0.232R — a small improvement in absolute terms, but cosmetic: still a
deeply negative, statistically robust loss. This confirms the earlier
BTC-based rejection generalizes to ETH RANGE conditions too, and that the
core mechanism (fade extreme EMA20 deviation) is unsound here, not just
mistimed.

**Independence check (positive result within an otherwise negative
phase)**: only 5.6-5.9% of these trades' holding windows overlap a
concurrent V0 trade — RANGE mean-reversion genuinely would occupy a
different slice of time than V0 if it worked. It doesn't change the
verdict, but confirms that *if* a working RANGE strategy is ever found, it
would legitimately diversify rather than duplicate V0 — relevant to the
portfolio-risk-budget question PLAN_CUSTOM raises for any future multi-strategy
setup.

### Decision

| Variant | Classification | Rationale |
|---|---|---|
| A_meanrev_baseline_entryZ2.0_ETH | **[REJECT]** | 0/12 WFO folds positive, PF 0.657, statistically significant negative expectancy |
| B_meanrev_reversion_confirmation_ETH | **[REJECT]** | Same severity of failure as A; the confirmation logic doesn't address the underlying issue |

**Volatility-compression and failed-breakout hypotheses (also listed in
PLAN_CUSTOM for this question) were intentionally not run** in this pass —
same reasoning as Phase 3's unrun breakout variants: two mean-reversion
formulations have now failed decisively and uniformly, and continuing to
try reformulations without a new economic rationale would drift toward
exactly the kind of "keep testing until something looks good" pattern the
anti-overfitting rules warn against. Noted in §14 as a possible future
direction only if a specific, falsifiable mechanism is proposed first.

## Phase 5 — Multi-timeframe confirmation (research question 6)

Script: [scripts/research_phase5_mtf_confirmation.py](../../scripts/research_phase5_mtf_confirmation.py).
Raw output: [artifacts/phase5_mtf_summary.csv](artifacts/phase5_mtf_summary.csv).
M5/M30 bars resampled directly from the existing M1 parquet (299,698 M5 /
49,950 M30 bars in the research pool) — no new data collection needed.

PLAN_CUSTOM lists 4 variants; **D (H1 regime + M15 setup) is not a new
hypothesis — it's already the live V0 architecture**, so this phase tests
B and C only: an M5 or M30 confirmation **filter** added on top of the
same winning M15 entry trigger. Confirmation rule (fixed, not swept): the
most recently *closed* M5/M30 candle at signal time must be bullish for a
LONG or bearish for a SHORT, joined via `merge_asof(direction="backward")`
so no partially-formed or future bar is ever used.

Because this is an AND-filter on top of the existing trigger, it can only
ever **reduce** trade count relative to the M15-only baseline — this phase
tests whether that reduction buys better quality, not whether it finds
more opportunity (which isn't possible by construction).

| | A: M15 only (=V0) | B: M15+M5 confirm | C: M15+M30 confirm |
|---|---|---|---|
| n | 1,412 | 1,024 | 852 |
| trades/year | 502 | 364 | 303 |
| win rate | 42.6% | 42.3% | 43.1% |
| expectancy | +0.0246R | +0.0120R | +0.0137R |
| PF | 1.041 | 1.020 | 1.023 |
| MaxDD | -79.4R | -61.7R | -56.4R |
| WFO folds positive | 7/11 (64%) | 7/11 (64%) | **5/11 (45%)** |
| bootstrap | not sig. | not sig. | not sig. |

### Finding: confirmation filters mostly just add noise, exactly as PLAN_CUSTOM's framing anticipated

Unlike Phases 1-4 (which showed decisive, statistically significant
rejections), this result is milder but still negative: **neither filter
improves anything.** M5 confirmation (B) cuts the trade count by 27% while
expectancy drops to about half the baseline (+0.0120R vs +0.0246R) and PF
stays roughly flat — the WFO fold-positive rate does tie the baseline
(64%), but there's no metric where B is actually *better*, only smaller.
M30 confirmation (C) is worse: it also roughly halves expectancy AND drops
fold-consistency to 45%, below the §15 threshold.

MaxDD shrinks proportionally with trade count in both cases, which is the
mechanical effect of trading less, not evidence of better risk-adjusted
quality — expectancy and PF are the metrics that would show a real quality
improvement, and neither confirmation timeframe delivers one.

**This directly answers PLAN_CUSTOM's framing of the question**: "does
lower/higher-timeframe confirmation increase valid opportunities or merely
add noise?" — it cannot increase opportunities by construction (it's a
strict subset filter), and the subset it keeps is not meaningfully
higher-quality than the trades it discards. The M5/M30 candle-direction
signal at the moment of an M15 pullback entry does not appear to carry
useful additional information for this setup.

### Decision

| Variant | Classification | Rationale |
|---|---|---|
| B_M15_plus_M5_confirmation | **[REJECT]** | No expectancy/PF/consistency improvement over control; only reduces sample size |
| C_M15_plus_M30_confirmation | **[REJECT]** | Same, and additionally fails the §15 WFO consistency threshold (45%) |

Note this only tested MTF as a *confirmation filter* on the existing V0
trigger. A different framing — e.g. an independent M5-native or
H4/daily-native setup — was not tested here and would be a genuinely
separate hypothesis, not a variant of this one; noted in §14 if worth
pursuing later.

## Phase 6 — Trade duration / MFE-MAE analysis (research question 7)

Script: [scripts/research_phase6_duration_analysis.py](../../scripts/research_phase6_duration_analysis.py).
Raw per-trade output: [artifacts/phase6_duration_raw.csv](artifacts/phase6_duration_raw.csv).
Analysis only — informational, does not change the live 12h timeout, per
PLAN_CUSTOM's explicit instruction. Measured on the same 1,412 V0-baseline
research-pool trades used as the control throughout.

**Exit reason breakdown**: SL 49.4% · TP 29.7% · TIMEOUT 20.9%

| | Time to TP | Time to SL |
|---|---|---|
| median | 4.83h | 3.39h |
| mean | 5.21h | 4.10h |
| 25th pctile | 2.73h | 1.77h |
| 75th pctile | 7.41h | 5.89h |

| | MFE (mean) | MAE (mean) |
|---|---|---|
| TP trades | +2.22R (target is exactly 2.0R — 0.22R average bar-level overshoot before the exit bar closes) | -0.38R |
| SL trades | +0.52R (some favorable excursion before reversing to loss) | -1.16R (target is -1.0R — some overshoot past the exact stop, from same-bar gap/conservative-fill assumption) |
| TIMEOUT trades | +1.12R | -0.61R |

**Mark-to-market return at fixed checkpoints** (mean R across all 1,412 trades, position value if evaluated at that elapsed time):

| Checkpoint | mean R | % trades resolved (TP/SL hit) by then |
|---|---|---|
| 1h | +0.0015R | 7.1% |
| 2h | +0.0270R | 19.2% |
| 4h | +0.0683R | 40.7% |
| 8h | +0.1103R | 67.2% |
| 12h (=final) | +0.1608R | 79.1% (remaining 20.9% forced-closed at timeout) |

### Finding: setups do NOT resolve quickly — most of the edge accrues late in the hold

Mean mark-to-market R climbs steadily and monotonically from essentially
zero at 1h to +0.16R at 12h — **it does not plateau early.** By the 4h
mark, only 40.7% of trades have even resolved (hit TP or SL), and the mean
return at that point (+0.068R) is less than half of the eventual 12h
figure (+0.161R). The last third of the position's life (8h→12h) —
resolving the remaining ~33% of trades from 67% to 79% — still meaningfully
adds to mean R (+0.110R → +0.161R).

**This is evidence against shortening the 12h timeout.** A shorter window
would force-close the slower-developing trades before they've had the
chance to reach TP, converting some fraction of eventual winners into
worse (or artificially timed-out) outcomes — exactly the trades least
represented in the early checkpoints. Per PLAN_CUSTOM's instruction, the
live timeout is **not changed** based on this alone, but if anything the
directional evidence favors leaving it as-is or investigating a *longer*
window as a separate, properly-tested hypothesis — not shortening it.

TP trades show only a small average overshoot beyond the exact 2.0R target
(+0.22R) at the bar where TP is touched — the fixed TP is capturing close
to the full favorable move for winners at the point of exit, i.e. there
isn't strong evidence of large amounts of "profit left on the table" that
a trailing-stop mechanism would obviously capture (though this specific
question — trailing exits — was not directly tested and would need its
own hypothesis and WFO validation, not inferred from MFE alone).

### No promotion/rejection classification for this phase

Phase 6 is descriptive analysis, not a strategy variant — there is nothing
to classify as KEEP/REJECT. Its output is evidence to inform *future*
hypotheses (e.g., "should the timeout be lengthened" or "would a
trail-to-breakeven rule after 8h help") rather than a candidate itself.

---

## Running decision log

| Item | Status | Evidence |
|---|---|---|
| ADX>35 regime filter is the bottleneck | **Rejected as primary cause** | Phase 0: 0% incremental drop from direction filter, -93.4% at pullback stage instead |
| EMA20-pullback cross definition is overly narrow / should be broadened | **Rejected** | Phase 2: all 4 broader variants underperform V0 control on expectancy, PF, and WFO consistency; the narrow trigger is filtering for quality, not just quantity |
| ADX>35 regime filter is unnecessarily restrictive | **Rejected — and inverted** | Phase 1: ADX>30/25 both give a *statistically significant negative* bootstrap CI, monotonically worse with more loosening; continuous ADX-percentile variant is closer to neutral but still strictly worse than the fixed cutoff on every metric |
| Donchian(20) breakout is a viable second ETH strategy | **Rejected, decisively** | Phase 3: 0/12 WFO folds positive, PF 0.559, bootstrap CI entirely negative — fails harder on ETH than it did on BTC |
| RANGE mean-reversion (extreme EMA20/ATR deviation) is a viable RANGE strategy | **Rejected, decisively** | Phase 4: both baseline and reversion-confirmation variants get 0/12 WFO folds positive, PF 0.66-0.68, bootstrap CI entirely negative |
| M5/M30 confirmation filter improves M15 entry quality | **Rejected** | Phase 5: both cut expectancy roughly in half with no PF/consistency gain; M30 additionally fails the §15 threshold (45%) |
