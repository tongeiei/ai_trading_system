# Feasibility Memo — Adding XAU/USD as a Second Instrument

Analysis only. No code changed, no execution route chosen. Written to
inform a go/no-go decision, in the same spirit as
[ETH_V1_RESEARCH_REPORT.md](ETH_V1_RESEARCH_REPORT.md). Date: 2026-08-25.

## 1. Why this is worth asking (vs. the Phase 1-6 research)

The ETH V1 research (0/12 hypotheses passed) tried to extract more
opportunity from the **same asset**, and repeatedly found only
lower-quality versions of the same trades. Gold is fundamentally
different: **XAU/USD is largely uncorrelated — often inversely correlated —
to crypto**, because it's driven by macro (Fed policy, DXY, real yields,
risk-off flows), not crypto-native flows. If V0's trend-pullback logic
generalizes to gold at all, it would be a *genuinely independent* return
stream — the real diversification that a second correlated crypto strategy
could never provide.

**But this is a hypothesis, not a given.** BTC/SOL/BNB all failed the
exact same validation ETH passed. Gold could easily fail too. Nothing
below assumes V0 works on gold — it must earn its place through the full
pipeline (screening → WFO → sacred holdout), same as every crypto symbol.

## 2. The blocker from project history

Per [../HANDOFF.md](../HANDOFF.md): this project **started** as XAU/USD via
MT5 and pivoted *away* precisely because MT5's lot-size minimums made 1%
risk sizing impossible on a ~2,000 THB account. Any route that goes back
through a lot-based broker reintroduces that exact blocker. The crypto
pivot's key advantage was direct `risk_amount / sl_distance` sizing with no
lot/contract granularity — that's the property to preserve.

## 3. Execution routes compared

| | **PAXG on Binance** | **XAU/USD via broker (MT5/API)** | **Gold futures (MGC)** |
|---|---|---|---|
| What it is | Pax Gold token, 1:1 physical gold, spot pair PAXG/USDT | Real spot gold / CFD | COMEX micro gold future |
| Reuses current infra | **Yes — fully** (ccxt, keys, order code, crypto-style sizing) | No — new data + execution pipeline | No |
| Sizing granularity | Fine (crypto step size) — **no lot blocker** | Lot-based — **blocker returns** | 10 oz/contract (~$33k notional) — far too big for a $2k account |
| Long/Short | **Long only** (Binance has PAXG spot, no PAXG perp) | Both | Both |
| Leverage | None (spot) | Yes | Yes (but notional already too big) |
| Tracks real XAU | Closely, with small premium/discount + its own thin liquidity | Exactly (is the thing) | Exactly |
| Weekend/session gaps | Trades ~24/7 like crypto (token) | Real gold hours, weekend gap | Real gold hours, weekend gap |
| Verdict | **Best fit for this system, with real limits** | Full-featured but heavy + reintroduces the pivot blocker | **Reject** — contract too large |

## 4. The honest catch with PAXG (the best-fit route)

PAXG looks ideal because it drops into the existing stack unchanged, but
two limits are material:

1. **Spot only → long only.** V0 is a symmetric long/short strategy. On
   ETH, SHORT trades actually carried the edge in some windows (e.g.
   Phase 1/2 baseline: SHORT avg +0.13R vs LONG -0.09R). A long-only gold
   book throws away half the strategy by construction — and in a
   sustained gold *downtrend*, V0 would simply sit out rather than profit.
   This alone could make PAXG-V0 much weaker than the ETH result.
2. **Thin liquidity / wider spread.** PAXG volume is a fraction of ETH's.
   The backtest cost model's slippage assumption (a placeholder even for
   ETH — see [BACKTEST_PLAN_AND_RESULTS.md](../BACKTEST_PLAN_AND_RESULTS.md))
   would be *less* trustworthy here, not more. Cost sensitivity would need
   explicit testing at higher slippage multiples.

There's also a subtle point: **PAXG is not identical to XAU.** It carries a
small, time-varying premium/discount to spot gold and has its own
token-specific liquidity events. A V0 edge measured on PAXG history is an
edge on *PAXG*, which is *mostly* but not exactly gold.

## 5. Data availability for a backtest

- **PAXG route**: PAXG/USDT klines are pullable from Binance public API
  with the existing `src/data/binance_loader.py` (no new code, just a new
  symbol) — **can start a backtest immediately**. History depth is shorter
  than ETH's 3 years (PAXG launched later / thinner early data) — worth
  checking the usable range before committing to WFO folds.
- **Broker XAU route**: needs a separate historical data source (broker
  export, or a paid feed like Dukascopy/TrueFX). Not in the repo today.

## 6. Recommendation (pre-execution)

**If we pursue gold at all, start with PAXG as a research-only backtest** —
it's the only route that costs almost nothing to *investigate* (one symbol
added to the loader, then the standard V0 → screening → WFO pipeline). The
decision tree:

1. Pull PAXG history, check usable date range.
2. Run V0 (locked config, long+short in backtest even though live would be
   long-only, to see the full picture) through the same funnel + WFO +
   sacred-holdout process ETH went through.
3. **Gate**: does long-only PAXG-V0 clear PF > 1.10 and ≥60% WFO fold
   consistency on out-of-sample data — *and* survive a higher slippage
   assumption than ETH needed? If not → **[REJECT]**, same as BTC/SOL/BNB.
4. Only if it passes: then the harder conversation about spot-only long-only
   live execution, portfolio risk budget (do NOT just add another 0.5% —
   size the two instruments jointly), and whether the broker route is worth
   the integration cost to recover the short side.

**Do not** go straight to the broker/MT5 route to get shorts — that's the
expensive path *and* the one that reintroduces the lot-size blocker. Prove
there's any gold edge at all on the cheap (PAXG backtest) before spending
integration effort.

## 7. Classification

| Item | Status |
|---|---|
| Adding XAU/USD as a diversifying instrument | **[RESEARCH]** — economically motivated (genuine low correlation to ETH), but zero validation yet; V0 is not assumed to transfer |
| PAXG-on-Binance as the access route | **[RESEARCH — start here]** — cheapest to investigate, reuses all infra, but spot/long-only and thin-liquidity caveats are real |
| Broker/MT5 XAU route | **[DEFER]** — only if PAXG shows an edge worth recovering the short side for; reintroduces the original lot-size blocker |
| Gold futures (MGC) | **[REJECT]** — contract notional far exceeds account size |

## 8. Exact next experiment (if you want to proceed)

Add `PAXG/USDT` to `data/raw` via the existing loader, then run the Phase-0
funnel + a V0 backtest with full costs on PAXG, reporting the same metric
set as the ETH research. One symbol, one locked config, no tuning — a clean
yes/no on whether gold has any V0-detectable edge before any execution
work.
