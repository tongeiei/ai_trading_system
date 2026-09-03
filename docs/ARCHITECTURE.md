# System Architecture

Generated 2026-09-03. This is a snapshot diagram, not a source of truth — trust
`docs/HANDOFF.md` (crypto live track), `docs/XAU_LIVE_HANDOFF.md` (XAU machine/account
prep), and `docs/XAU_ARCHITECTURE_AUDIT.md` (XAU target architecture + phase status) over
this file if they disagree. Regenerate this diagram rather than hand-editing it as the
system evolves.

```mermaid
flowchart TD
    subgraph TrackA["Track A — ETH/XRP Live (Oracle VPS, systemd timer, demo trading)"]
        A1["systemd timer<br/>M15 bar close"] --> A2["scripts/run_signal_cycle.py"]
        A2 --> A3["binance_loader / signal_service<br/>fetch_recent_ohlcv (ccxt)"]
        A3 --> A4["features/engine.py<br/>build_features (12 features)"]
        A4 --> A5["regime/rules.py<br/>TREND / RANGE"]
        A5 --> A6["strategy/v0_rules.py<br/>EMA pullback signal"]
        A6 --> A7["live/ev_estimate.py<br/>historical-stats EV gate"]
        A7 --> A8["live/guards.py<br/>rolling win-rate risk multiplier"]
        A8 --> A9["live/logging_store.py<br/>log signal (incl. NO_TRADE)"]
        A9 --> A10["live/order_executor.py<br/>risk/sizing.py + exchange order"]
        A10 --> A11["alerting.py → LINE"]
        A9 --> A12["data/db.py (SQLite)<br/>bars/signals/orders/trades"]
        A12 --> A13["dashboard/app.py (Streamlit)"]
    end

    subgraph TrackB["Track B — XAU/USD Gold (Windows PC)"]
        subgraph B_Data["Data pipeline — P2 done (2026-09-03)"]
            B1["scripts/fetch_xau_dukascopy.py<br/>M1/M5/M15/H1/H4 from Dukascopy"] --> B2["data/validation.py<br/>gap / outlier / reconciliation / session checks"]
            B2 --> B3["data/raw/XAUUSD_*.parquet<br/>2006 → present, 5 timeframes"]
        end

        subgraph B_Backtest["Backtest harness (research only)"]
            B3 --> B4["backtest/gold_harness.py<br/>load_gold_data / load_gold_data_all"]
            B4 --> B5["features/engine.py<br/>build_features (M15+H1, shared w/ Track A)"]
            B5 --> B6["scripts/run_gold_r*.py<br/>R1–R17 hypotheses — 8/8 falsified"]
            B6 --> B7["backtest/significance.py<br/>bootstrap + walk-forward gate"]
        end

        subgraph B_Live["Live-feed spike (prototype only)"]
            B8["data/mt5_feed.py<br/>MetaTrader5 → XAUUSDm"] --> B2
            B8 -.->|"verified against"| B9["Exness Standard demo<br/>(MT5 terminal, this PC)"]
        end

        B10["config/gold_spec.yaml<br/>cost model, WFO gate"] --> B4
    end

    subgraph Future["Target architecture — not yet built (P3–P13)"]
        F1["Feature engine expansion (P3)"] --> F2["Regime engine<br/>TREND/RANGE/EXPANSION/HIGH_VOL (P4)"]
        F2 --> F3["Setup scanner + registry (P5)"]
        F3 --> F4["AI layer — Setup Quality Scorecard<br/>DeepSeek, $10/mo (P6)"]
        F4 --> F5["Risk Engine<br/>daily loss / max DD / kill switch (P7)"]
        F5 --> F6["MT5 execution adapter (P8)"]
        F6 --> F7["Trade journal + monitoring (P9–P10)"]
        F7 --> F8["Paper trading → small live (P12–P13)"]
    end

    B3 -.->|feeds| F1
    B8 -.->|becomes| F6

    classDef live fill:#2b6a4f,color:#fff
    classDef research fill:#5a5a8c,color:#fff
    classDef planned fill:#8c8c8c,color:#fff,stroke-dasharray: 5 5

    class A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A11,A12,A13 live
    class B1,B2,B3,B4,B5,B6,B7,B8,B9,B10 research
    class F1,F2,F3,F4,F5,F6,F7,F8 planned
```

## Legend

- **Green (Track A)** — ETH/XRP: live on the Oracle VPS right now (demo trading, no real money).
- **Purple (Track B)** — XAU/USD: data pipeline + validation complete as of P2 (2026-09-03);
  backtest harness is research-only (all 8 tested hypotheses R1–R17 falsified, see
  `docs/research/GOLD_HANDOFF.md`); the MT5 live-feed module is a feasibility spike, not a
  production loop.
- **Gray, dashed (Future)** — P3–P13 of the XAU target architecture per
  `docs/XAU_ARCHITECTURE_AUDIT.md` §10 — none of this exists in code yet.
