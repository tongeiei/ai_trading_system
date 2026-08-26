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
