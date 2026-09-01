# XAU/USD AI System — Existing Project Audit & Gap Analysis

เอกสารนี้คือ **First Output** ตาม `TASK_NEW_WORLD.md` §2 และ **Final Deliverable** ตาม §21
เขียนก่อนแก้โค้ดใด ๆ — ณ ตอนเขียนยังไม่มีการแก้ไฟล์ใดในโปรเจกต์

- วันที่: 2026-09-01
- Commit ฐาน: `b2d5708` (23 commits, branch `main`)
- ขอบเขตที่อ่าน: `src/` ทั้งหมด, `scripts/` (60 ไฟล์), `tests/` (52 tests — **รันแล้วผ่านทั้งหมด**),
  `docs/` + `docs/research/`, `config/`, `deploy/`, `.claude/agents/`, `PROJECT_PLAN.md`
- ⚠️ อ่านคู่กับ `docs/HANDOFF.md` (ETH track ที่รันจริง) และ `docs/research/GOLD_HANDOFF.md`
  (gold research track) — สองไฟล์นั้นคือแหล่งความจริงเรื่อง "อะไรพิสูจน์แล้ว/อะไรถูกปฏิเสธ"

---

## 0. สรุปผู้บริหาร (อ่านแค่นี้ก็ตัดสินใจได้)

โปรเจกต์นี้ **ไม่ใช่ repo ว่างเปล่า** และไม่ใช่ prototype — มันคือระบบเทรดที่ทำงานจริงบน VPS
อยู่แล้ว มี research discipline ระดับสูงผิดคาด (pre-registered falsification plan, sacred
holdout, cost stress, บันทึกสิ่งที่ล้มเหลวไว้ครบ) สิ่งที่มีค่าที่สุดในนี้ **ไม่ใช่ strategy
แต่คือ research/validation harness + risk plumbing + วินัยการบันทึกผลลบ**

สามข้อที่ต้องรู้ก่อนอนุมัติแผน:

1. **มีของเดิมให้ reuse เยอะกว่าที่คิด** — feature engine, triple-barrier labeling, WFO gate,
   bootstrap significance, log-before-execute journal, reconciliation, exchange-native SL/TP,
   alerting, dashboard, systemd deployment ทั้งหมดทำงานอยู่จริงและมี test
2. **ส่วนที่ target architecture ต้องการมากที่สุดกลับยังไม่มีเลย 3 ก้อน**:
   (ก) **LLM layer — ไม่มีโค้ดแม้แต่บรรทัดเดียว** ไม่มี `anthropic` ใน venv, grep ทั้ง repo
   ไม่เจอ provider ใด ๆ (`.claude/agents/*.md` เป็น prompt persona สำหรับให้ "คนเรียก Claude
   Code" ใช้ ไม่ใช่ runtime integration)
   (ข) **Risk Engine ตัวจริงยังไม่มี** — มีแค่ position sizing + winrate multiplier;
   daily loss limit / max drawdown / max consecutive losses / max simultaneous risk /
   kill switch **ยังไม่ได้ implement เลย** ทั้งที่ §11 ระบุเป็น default
   (ค) **live feed ของ XAU/USD ไม่มี** — Dukascopy ที่ใช้อยู่เป็น historical-only,
   MT5 ยังไม่มีโค้ดสักบรรทัด (แต่ platform blocker ปิดแล้ว — ดู §15 ข้อ 2b)
3. **ธงแดงที่บันทึกไว้ (ยกขึ้นแล้ว และผู้ใช้ตัดสินใจแล้ว)**: gold track ทดสอบสมมติฐาน
   ครบกระบวนการแล้ว **8 ตัว falsified ทั้ง 8** (R1, R2, R5, R8, R11, R14, R15, R17 — ดู
   `GOLD_HANDOFF.md` master table) ครอบคลุมทั้ง pure price-action pattern และ cross-asset
   macro filter. ผมเสนอให้แทรก "Edge Gate" ก่อนสร้าง execution/AI stack เพื่อลดความเสี่ยง
   ที่จะได้ท่อที่ไม่มีอะไรไหลผ่าน — **ผู้ใช้ตัดสินใจไม่รับข้อเสนอนี้ ให้สร้าง stack ให้ครบ
   ตามลำดับ phase เดิมใน TASK_NEW_WORLD.md §19** (2026-09-01) แผนใน §10 จึงเป็นลำดับเดิม
   ตามที่สั่ง บันทึกความเสี่ยงไว้ที่ R-1 ใน §13 เพื่อการติดตาม ไม่ใช่เพื่อรื้อการตัดสินใจ

---

## 1. Current Architecture

มี **สองเส้นทางที่แยกกันเด็ดขาด** อยู่ใน repo เดียว:

```
TRACK A — ETH/XRP crypto (LIVE, รันอยู่จริงบน VPS, demo money)
  systemd timer (ทุก M15 bar close)
    → scripts/run_signal_cycle.py
      → ccxt binanceusdm (public fetch OHLCV M15+H1)
      → src/features/engine.build_features        (12 features, shift(1) ทุกตัว)
      → src/regime/rules.classify_regime          (TREND / RANGE)
      → src/strategy/v0_rules.generate_v0_signals (EMA20 pullback ใน TREND)
      → src/live/ev_estimate.estimate_ev          (EV gate จาก historical base rate)
      → src/live/guards.rolling_winrate_...       (ลด risk ครึ่งถ้า winrate < 30%)
      → src/risk/sizing.compute_position_size     (risk_amount / sl_distance)
      → src/live/order_executor                   (market entry + native SL + native TP)
      → SQLite (signals / risk_decisions / orders / trades)
      → LINE Messaging API alerts
    ข้าง ๆ: src/live/reconcile (orphan position), position_timeout (12h + organic exit)
    หน้าจอ: src/dashboard/app.py (Streamlit, 127.0.0.1:8501 ผ่าน SSH tunnel)

TRACK B — XAU/USD gold (RESEARCH ONLY, ไม่เคยแตะ live)
  scripts/run_gold_r*.py
    → src/backtest/gold_harness.run_gold_backtest
      → parquet XAUUSD_{1m,15m,1h} (Dukascopy 2006-2026)
      → build_features (reuse ตัวเดียวกับ track A)
      → signal_fn ของแต่ละ hypothesis (src/strategy/gold_*.py)
      → src/labeling/triple_barrier.label_all_signals (เดิน M1 path)
      → apply_gold_costs (spread+slip+commission, NO funding)
      → walk_forward gate (PF >= 1.10 AND >=60% quarterly folds บวก)
      → docs/research/artifacts/*.txt
```

**Track B ทั้งหมดยัง untracked ใน git** (ดู `git status` — `src/strategy/gold_*.py`,
`src/backtest/gold_harness.py`, `config/gold_spec.yaml`, `scripts/run_gold_*` ยังไม่ commit)

---

## 2. Current Components

| Component | ไฟล์ | สถานะ |
|---|---|---|
| Data loader (crypto) | `src/data/binance_loader.py`, `funding_rate_loader.py` | ใช้งานจริง |
| Data loader (gold hist) | `scripts/fetch_xau_dukascopy.py` | ใช้งานแล้ว, historical only |
| Data loader (DXY) | `scripts/fetch_dxy_dukascopy.py` + Yahoo → `DXY_daily.parquet` | ใช้งานแล้ว |
| DB schema | `src/data/db.py` — bars, funding_rates, signals, risk_decisions, orders, trades | ใช้งานจริง |
| Feature engine | `src/features/engine.py` — 12 features (f01–f12) | ใช้งานจริง, มี leakage test |
| Regime | `src/regime/rules.py` — TREND/RANGE + `vol_multiplier()` | ใช้งานจริง |
| Strategy (crypto) | `v0_rules.py` (locked), `breakout.py`, `mean_reversion.py` | v0 live, อีก 2 ตัวถูกปฏิเสธ |
| Strategy (gold) | `gold_orb`, `gold_orb_pullback`, `gold_r5_dxy_filter`, `gold_r8_*`, `gold_r11_*`, `gold_r14_*`, `gold_r15_choch`, `gold_r17_fvg` | **falsified ทั้งหมด** |
| Labeling | `src/labeling/triple_barrier.py` | ใช้ทั้งสอง track |
| Backtest core | `src/backtest/costs.py` (perp), `significance.py` (bootstrap), `gold_harness.py` (spot) | ใช้งานจริง |
| ML | `src/models/train.py`, `calibrate.py` (LightGBM) | **ถูกปฏิเสธที่ gate P5** (AUC 0.497) เก็บไว้อ้างอิง |
| Risk | `src/risk/sizing.py` | มีแค่ sizing |
| Live | `signal_service`, `order_executor`, `guards`, `reconcile`, `position_timeout`, `ev_estimate`, `logging_store`, `alerting` | ใช้งานจริงครบ |
| Dashboard | `src/dashboard/app.py` (Streamlit) | ใช้งานจริง |
| Deployment | `deploy/signal-cycle.{service,timer}`, `dashboard.service` | ใช้งานจริงบน VPS |
| Agent personas | `.claude/agents/*.md` (8 ไฟล์) | เป็น **prompt/เอกสาร** ไม่ใช่ runtime |
| Tests | `tests/` 9 ไฟล์ / 52 tests | **รันผ่านทั้งหมด (0.97s)** |

---

## 3. Current Data Flow

**Live (crypto):** ccxt `fetch_ohlcv` ดึง M15 warm-up 65 วัน + H1 85 วัน ทุก cycle → กรอง
เฉพาะแท่งที่ **ปิดแล้ว** (`b[0] + ms_per_candle <= end_ms` — เคยมีบั๊กที่แท่งกำลังก่อตัว
หลุดเข้ามาเป็น `iloc[-1]`, แก้แล้วและมี test) → dedupe/sort → build_features →
`merge_asof(direction="backward")` สำหรับ H1 → **`shift(1)` ทุก feature column**

**Research:** parquet → slice ช่วงเวลา → build_features → signal_fn → M1 path labeling

**สิ่งที่ยังไม่มีในสาย data:** validation layer จริง ๆ (gap detection ตอน runtime, outlier/
bad-tick, cross-source reconciliation, timezone/DST สำหรับ forex, ตรวจ session/holiday)
ตอนนี้มีแค่ dedupe + sort + gap report ใน fetch script เท่านั้น

**ข้อมูลที่มีจริงวันนี้ (ตรวจแล้ว):**

| ไฟล์ | rows | ช่วงเวลา |
|---|---|---|
| `XAUUSD_1m.parquet` | 7,376,388 | 2006-01-01 → 2026-08-25 |
| `XAUUSD_15m.parquet` | 505,247 | 2006-01-01 → 2026-08-25 |
| `XAUUSD_1h.parquet` | 127,254 | 2006-01-01 → 2026-08-25 |
| `DXY_daily.parquet` | 5,198 | 2006-01-03 → 2026-08-27 |
| `DXY_1h.parquet` | 46,587 | 2017-12-01 → 2026-08-27 |

⚠️ **ไม่มี M5** (target architecture ระบุ M5 = setup detection) และ **ไม่มี H4**
⚠️ `XAUUSDT_*` (perp บน crypto exchange, ~8 เดือน) เป็นคนละของกับ `XAUUSD_*` — อย่าปน

---

## 4. Current Strategy Flow / Execution Flow / AI Integration

**Strategy flow (live):** regime==TREND → H1 trend sign → close ตัดกลับข้าม EMA20 →
quality filter (ATR percentile, body ratio) → SL = 1.5–2.5×ATR (clip) → TP = 2R →
EV gate → sizing → order. ตัดสินใจที่ **bar close เท่านั้น** ไม่มี intrabar

**Execution flow:** `execute_signal_with_logging` = log signal → sizing (reject ได้) →
log risk decision → market entry → **exchange-native STOP_MARKET SL** → native
TAKE_PROFIT_MARKET TP → log orders → log trade. ถ้า SL วางไม่สำเร็จ **บังคับปิด position
ทันที** (ห้ามมี naked position). มี workaround สำหรับ Binance algo-order namespace ที่
ccxt มองไม่เห็น (`fetch_open_algo_orders`)

**AI integration: ไม่มี**
- grep ทั้ง repo หา `anthropic|openai|claude|llm|gpt` → เจอแค่คอมเมนต์ ไม่มีโค้ดเรียก API
- venv ไม่มี SDK ของ LLM provider ใด ๆ (มี `lightgbm`, `scikit-learn`, `ccxt`, `streamlit`)
- สิ่งที่ใกล้เคียงที่สุดคือ **LightGBM ที่ถูกปฏิเสธไปแล้ว** (AUC 0.497 บน holdout) —
  `ev_estimate.py` เขียนคอมเมนต์ยาวมากเตือนว่า "ห้ามเอา AI probability กลับมา"
- `.claude/agents/*.md` = persona 8 ตัว (Research Lead, Strategy Research, Risk Research,
  Systems Audit, Skeptic, Trading Lead, Backtest agent) — เป็น **แนวคิดที่ตรงกับ §6 มาก**
  แต่เป็น markdown ให้มนุษย์/Claude Code ใช้ตอน research ไม่ใช่ service ที่รันบน VPS

---

## 5. Current Database / Infrastructure / Scheduler / Monitoring / Tests

- **DB**: SQLite ผ่าน SQLAlchemy Core (`data/trading.db`) 6 ตาราง มี idempotent migration
  แบบง่าย (`_migrate_add_missing_columns`) — ไม่มี Alembic
- **Infra**: Oracle Cloud Free Tier, Ubuntu 24.04, UFW/fail2ban/key-only SSH.
  **ไม่มี Docker**, ไม่มี healthcheck endpoint, ไม่มี metrics exporter, ไม่มี DB backup
- **Scheduler**: systemd `OnCalendar=*:0/15:30` (one-shot ต่อ M15 bar + 30s buffer)
  — restart-safe กว่า long-lived loop ดี แต่ **ไม่มี M1 monitoring loop** ตามที่ §5 ต้องการ
- **Monitoring**: Streamlit dashboard (cache 30s, ต้องกด refresh เอง) + LINE push
  (trade opened/closed, critical, error, gate-blocked streak) — **ไม่มี Grafana/Prometheus**
- **Tests**: 52 tests ผ่านหมด ครอบคลุม sizing, guards, costs, triple_barrier, leakage,
  significance, logging_store, ev_estimate, signal_service
  นอกจากนี้มี integration/engineering script แยก (`scripts/test_fault_injection.py`,
  `test_db_integration.py`, `test_engineering_order_flow.py`, `test_live_replay.py`)
  ที่ **ต้องต่อ network/testnet** จึงไม่อยู่ใน `tests/`

---

## 6. Technical Debt (จัดลำดับตามผลกระทบ)

| # | หนี้ | ผลกระทบ |
|---|---|---|
| D1 | **Risk limits ตาม §11 ยังไม่มีจริง** — ไม่มี daily loss, max DD, max consecutive losses, max simultaneous risk, kill switch | สูงมาก — ระบบ "ไม่มีเบรก" นอกจาก SL ต่อไม้ |
| D2 | **Config ฝังอยู่ในโค้ด** — `SYMBOLS` list, `EV_THRESHOLD_R`, `SYMBOL_STATS`, `WINRATE_THRESHOLD`, `MAX_HOLD`, `SL_ATR_MULT` กระจายเป็น module constant | สูง — ขัด §18 โดยตรง, แยก dev/paper/live ไม่ได้ |
| D3 | **Track B ยังไม่ commit** (gold harness + 8 strategies + spec ทั้งหมด untracked) | สูง — งาน 8 rounds เสี่ยงหายถ้าเครื่องพัง |
| D4 | `PROJECT_PLAN.md` (92KB) และ `docs/TASKS.md` ยังเป็นยุค MT5/XAU เดิม ขัดกับ `HANDOFF.md` | กลาง — ทำให้ session ใหม่สับสน |
| D5 | `f12_spread_ratio` เป็น NaN ถาวร (placeholder ไม่เคยถูกเติม) | กลาง — feature ที่โฆษณาไว้ 12 ตัว ใช้จริง 11 |
| D6 | `detect_and_close_organic_exits` / `close_expired_positions` query `trades` **โดยไม่กรอง symbol** แล้วปิดด้วยราคาของ symbol ที่ส่งเข้ามา | กลาง-สูง — multi-symbol แล้วจะปิดผิดตัว (ตอนนี้รอด เพราะไม่เคยมีไม้เปิดพร้อมกัน) |
| D7 | ไม่มี Alembic / DB backup / retention | กลาง |
| D8 | `models/` (LightGBM) เป็น dead code ที่ถูกปฏิเสธไปแล้ว | ต่ำ — แต่ต้องมีป้ายชัดว่าห้ามใช้ |
| D9 | ไม่มี `requirements.txt` / `pyproject.toml` — venv reproduce ไม่ได้ | กลาง |
| D10 | Dashboard hard-code `CHART_SYMBOL = "ETH/USDT:USDT"` | ต่ำ |

---

## 7. Reusable / Replace / Do-Not-Touch

### ✅ Reusable ตรง ๆ (ยกมาใช้กับ XAU ได้เลย หรือแก้เล็กน้อย)
`src/features/engine.py` · `src/regime/rules.py` · `src/labeling/triple_barrier.py` ·
`src/backtest/significance.py` · `src/backtest/gold_harness.py` (WFO gate + spot cost model) ·
`src/risk/sizing.py` (สูตร risk/stop-distance ใช้ได้ทุก asset) · `src/live/guards.py` ·
`src/live/logging_store.py` · `src/live/reconcile.py` (แนวคิด) · `src/live/alerting.py` ·
`src/data/db.py` (schema ขยายได้) · `deploy/*` · `tests/*`

### ⚠️ Replace / เขียนใหม่
- `src/live/order_executor.py` — ผูกกับ ccxt Binance USDM ทั้งไฟล์ ต้องแตกเป็น
  `BrokerAdapter` interface + `MT5Adapter` (แต่ **ห้ามลบ** — Binance adapter ยังรัน ETH อยู่)
- `src/live/signal_service.py` — data source ต้องเปลี่ยนจาก ccxt เป็น MT5/broker feed
- `src/backtest/costs.py` — perp-shaped (มี funding) → gold ใช้ `apply_gold_costs` แทนแล้ว
- `src/strategy/gold_*.py` ทั้ง 8 ตัว — **เก็บเป็นบันทึกการทดลอง ห้ามเอามาใช้เป็น setup จริง**
  แต่ตัวตรวจจับข้างในมีค่ามาก (ดู §8 NEW-3)

### 🚫 ห้ามแตะ (Do NOT touch)
1. **`src/strategy/v0_rules.py` + ค่า config ที่ล็อกไว้ (adx=35, sl=2.5)** — retune โดยไม่มี
   holdout ใหม่ = เผา holdout ทิ้ง (บันทึกไว้ใน FINDINGS.md ว่าเคยเกิดแล้ว)
2. **`src/live/ev_estimate.py` `SYMBOL_STATS` / `EV_THRESHOLD_R`** — คอมเมนต์ในไฟล์ระบุชัดว่า
   การขยับ threshold เพื่อให้สัญญาณผ่าน = curve-fitting ที่โปรเจกต์นี้ตั้งใจกันไว้
3. **`src/models/`** — อย่า revive LightGBM gate
4. **ETH/XRP live cycle ที่รันอยู่** — งาน XAU ต้องไม่ทำให้ track A ล้ม
5. **`docs/FINDINGS.md` / `GOLD_HANDOFF.md` master table** — append เท่านั้น ห้ามลบผลลบ

---

## 8. Gap Analysis — CURRENT → TARGET → KEEP/MODIFY/REPLACE/NEW

| Target (TASK_NEW_WORLD §3) | ของเดิมที่ใกล้ที่สุด | Verdict | ช่องว่าง |
|---|---|---|---|
| Market Data Engine (XAU live) | `signal_service.fetch_recent_ohlcv` (ccxt) | **NEW** | ไม่มี live feed ของทอง — Dukascopy = historical เท่านั้น |
| Data Validation / Normalization / Time Sync | dedupe+sort เท่านั้น | **NEW** | gap/outlier/DST/holiday/session validation |
| Feature Engine | `features/engine.py` (11 ใช้ได้ + 1 NaN) | **MODIFY** | ขาด ADX(M15), EMA200, EMA slope, RSI, VWAP, swing H/L, BOS, CHoCH, FVG, liquidity sweep, displacement, distance-to-level, day-of-week, spread จริง, H4 |
| Macro features (DXY/US10Y/real yield/calendar) | มีแค่ `DXY_daily` | **NEW** | ไม่มี US10Y, real yield, economic calendar |
| Regime Detection | `regime/rules.py` (2 class) | **MODIFY** | ต้องได้ TREND/RANGE/EXPANSION/HIGH_VOL/UNKNOWN + persist `regime_confidence/features/timestamp` (ตอนนี้คืน Series เปล่า ไม่เก็บลง DB) |
| Setup Scanner (7 แบบ) | 8 gold strategies (falsified) + `v0_rules` | **NEW** | ต้องมี registry + status lifecycle (RESEARCH→…→LIVE/REJECTED) |
| ~~Fast AI Agent (Haiku-class)~~ | — | **ตัดทิ้ง** | งาน screening ทำโดย Setup Scanner + 6 คอลัมน์ deterministic แล้ว — ดู §16.8 ก |
| Strong AI Agent | — | **NEW** | ไม่มีอะไรเลย — เหลือ LLM จุดเดียวในระบบ (Macro + veto + thesis), provider ดู §16.8 |
| Research Agent (Opus-class) | `.claude/agents/*.md` + research scripts | **MODIFY** | มี persona + harness แล้ว ขาดแค่การเชื่อมเป็น loop |
| Risk Engine | `risk/sizing.py` + `guards.py` + EV gate | **MODIFY (ใหญ่)** | ขาด daily loss / max DD / consecutive losses / simultaneous risk / kill switch / news block |
| Execution Engine (MT5) | `order_executor.py` (Binance) | **REPLACE + abstraction** | ไม่มี MT5, ไม่มี pending order, trailing stop, partial close, duplicate-order protection แบบชัดเจน |
| Trade Journal | 4 ตารางใน SQLite, log NO_TRADE แล้ว | **MODIFY** | ขาด features snapshot, setup/strategy name, AI score/thesis, spread, slippage, MAE/MFE |
| Performance Attribution | — | **NEW** | ไม่มี |
| Research Loop (Hypothesis→BT→WFO→OOS) | `gold_harness` + plan docs + FINDINGS | **KEEP** ⭐ | แข็งแรงที่สุดในโปรเจกต์ ขาดแค่ promotion approval gate ที่เป็นโค้ด |
| Monitoring / Grafana | Streamlit + LINE | **MODIFY** | ไม่มี metrics/Grafana, ไม่มี data-feed health, ไม่มี auto-refresh |
| System Health (Docker/HC/backup/CB) | systemd only | **NEW** | ไม่มี Docker, circuit breaker, kill switch, backup |
| Configuration (yaml + env profiles) | `gold_spec.yaml` + constants ในโค้ด | **MODIFY** | ต้องมี `config/xau.yaml` + profile dev/research/paper/live |
| News / Macro filter (รวม NFP blackout) | `NEWS_BLACKOUT` เป็น no-op hook | **NEW** | ต้องมี calendar source + blackout logic + บันทึกเหตุผล block |
| Trading window จ–ศ 08:00–22:00 | ไม่มี (crypto 24/7) | **NEW** | ต้องมี session gate + timezone policy |

### NEW-3 — ของมีค่าที่ซ่อนอยู่ใน strategy ที่ falsified
`gold_r15_choch.py` มี `compute_choch_events()` (swing fractal + market-structure state machine),
`gold_r17_fvg.py` มี FVG detector, `gold_r14_fake_zone.py` มี pivot-sweep detector,
`gold_r11_wick_fill.py` มี wick/imbalance metric — **ตัว detector เหล่านี้ผ่านการ debug แล้ว
และเป็น feature ที่ §8 ต้องการพอดี** ข้อเสนอ: ยกออกมาเป็น `src/features/structure.py`
โดยไม่พาตรรกะ entry ที่ falsified ติดมาด้วย (feature ที่ไม่มี edge เดี่ยว ๆ ยังเป็น input
ที่ถูกต้องสำหรับ regime/AI context ได้)

---

## 9. Files to Modify / Create / Delete

### Modify
| ไฟล์ | ทำไม |
|---|---|
| `src/features/engine.py` | เพิ่ม feature ตาม §8, เติม `f12_spread_ratio` จริง, รองรับ H4 |
| `src/regime/rules.py` | ขยายเป็น 5 class + คืน confidence/features |
| `src/data/db.py` | ตาราง `regime_states`, `ai_analyses`, `news_events`; ขยาย `signals`/`trades` (setup, features_json, ai_score, ai_thesis, spread, slippage, mae, mfe) |
| `src/live/logging_store.py` | รองรับคอลัมน์ใหม่ |
| `src/live/signal_service.py` | รับ data source แบบ pluggable (ccxt / MT5) |
| `src/live/order_executor.py` | แตก interface, คง Binance adapter ไว้เหมือนเดิม |
| `src/dashboard/app.py` | multi-instrument, panel regime/AI/risk |
| `src/backtest/gold_harness.py` | ต่อ setup registry + status lifecycle |
| `config/gold_spec.yaml` | ผสานเข้ากับ `config/xau.yaml` โครงใหม่ |
| `docs/TASKS.md`, `PROJECT_PLAN.md` | ใส่ pivot notice รอบใหม่ (XAU กลับมา) กันสับสน |

### Create
```
config/xau.yaml                      config/profiles/{development,research,paper,live}.yaml
src/data/mt5_feed.py                 src/data/validation.py       src/data/calendar.py
src/features/structure.py            src/features/macro.py
src/regime/engine.py
src/scanner/__init__.py              src/scanner/registry.py      src/scanner/setups/*.py
src/ai/__init__.py                   src/ai/client.py             src/ai/monitor_agent.py
src/ai/analyst_agent.py              src/ai/schemas.py            src/ai/fallback.py
src/ai/scorecard.py                  src/ai/macro_agent.py        src/ai/provider.py  (ดู §16)
src/risk/engine.py                   src/risk/limits.py           src/risk/kill_switch.py
src/execution/broker.py (interface)  src/execution/mt5_adapter.py
src/execution/binance_adapter.py (ย้ายของเดิมมา)
src/journal/attribution.py
src/monitoring/metrics.py            src/monitoring/health.py
src/session/trading_window.py
tests/* (คู่กับทุกไฟล์ข้างบน)
docs/XAU_ARCHITECTURE_AUDIT.md (ไฟล์นี้)
Dockerfile, docker-compose.yml, requirements.txt / pyproject.toml
```

### Delete
**ยังไม่ลบอะไรในเฟสนี้** — ข้อเสนอสำหรับภายหลัง (ต้องขออนุมัติแยก):
- `src/models/train.py`, `calibrate.py` → ย้ายเป็น `docs/research/rejected/` พร้อมหมายเหตุ
- `src/strategy/breakout.py`, `mean_reversion.py` (ถูกปฏิเสธแล้ว) → เช่นเดียวกัน
- `data/trading_engineering_test.db` → artifact ทดสอบ

---

## 10. Migration Plan (13 phases ตาม §19 — ลำดับเดิม ตามที่ผู้ใช้ตัดสินใจ 2026-09-01)

ลำดับเป็นไปตาม TASK_NEW_WORLD.md §19 ทุกประการ ไม่มีการสลับหรือแทรก phase
(ข้อเสนอ Edge Gate ถูกยกขึ้นและถูกปฏิเสธแล้ว — ดู §0 ข้อ 3)

ข้อจำกัดเชิงความปลอดภัยที่ยังต้องเคารพภายในลำดับเดิม: AI (P6) มาก่อน Risk Engine (P7)
ได้โดยไม่ขัด §4 **ตราบใดที่ output ของ AI ไม่ถูกต่อเข้าเส้นทาง execution ใด ๆ ก่อน P7 จบ**
— ซึ่งเป็นจริงอยู่แล้วเพราะ Execution Engine คือ P8 P6 จะส่ง output ลง journal อย่างเดียว

| Phase | Goal | ผลลัพธ์ที่ต้องเห็น (Definition of Done) |
|---|---|---|
| P0 (งานบ้าน) | commit track B ที่ยัง untracked + `requirements.txt` + pivot notice รอบใหม่ | `git status` สะอาด, venv reproduce ได้ |
| P1 | Audit (ไฟล์นี้) | ✅ เสร็จ รอ review |
| P2 | XAU/USD data pipeline: เพิ่ม M5 + H4, validation layer, calendar, live-feed spike | ครบ 5 TF (M1/M5/M15/H1/H4), validation test ผ่าน |
| P3 | Feature engine ขยายตาม §8 + `structure.py` (ยก detector จาก R14/R15/R17) | leakage test ผ่านทุก feature ใหม่, `f12_spread_ratio` มีค่าจริง |
| P4 | Regime engine: TREND/RANGE/EXPANSION/HIGH_VOL/UNKNOWN + persist | regime + confidence + features + timestamp เขียนลง DB ทุกแท่ง |
| P5 | Setup scanner + registry + status lifecycle | setup ทุกตัวมีสถานะ RESEARCH/CANDIDATE/VALIDATED/PAPER/LIVE/REJECTED |
| P6 | AI integration (Haiku screen → Sonnet analyst, structured JSON) | AI down = NO NEW TRADE, ทุก call ถูก log, **ยังไม่ต่อ execution** |
| P7 | Risk Engine ครบตาม §11 + kill switch + news/NFP block | unit test ครบทุก limit, veto AI ได้จริง |
| P8 | MT5 (หรือ broker API) execution adapter | order flow test บน demo account ผ่าน |
| P9 | Trade journal ขยาย (features / AI thesis / MAE / MFE / spread / slippage) | NO_TRADE ถูกบันทึกพร้อมเหตุผลครบ |
| P10 | Monitoring (metrics + Grafana + health + data-feed alert) | dashboard ครบตาม §16 |
| P11 | Backtest / WFO บน pipeline ใหม่ทั้งชุด | reproduce ผล R1–R17 เดิมได้ ไม่มี leakage |
| P12 | Paper trading (จ–ศ 08:00–22:00 เวลาไทย, เว้นวัน NFP) | รันต่อเนื่อง 4 สัปดาห์ ไม่มี CRITICAL |
| P13 | Small live | risk 0.25% แล้วค่อยขยาย |

ทุก phase จบด้วย: Implement → Test → Run → Verify → Document → Commit

## 11. Dependencies / Infrastructure Changes

**Dependencies ใหม่**: `anthropic` (LLM), MT5 access layer, economic-calendar source,
`prometheus-client` (ถ้าใช้ Grafana), `alembic` (migration), `pytz/zoneinfo` policy

**⚠️ Infra risk ที่ใหญ่ที่สุด — MT5 บน Linux**: `MetaTrader5` python package เป็น
**Windows-only** VPS ปัจจุบันคือ Oracle Ubuntu (ARM, free tier) ทางเลือกคือ
(ก) Windows VPS แยก (ข) Wine bridge (เปราะ) (ค) broker REST/FIX API แทน MT5
(ง) ไม่ใช้ MT5 เลยแล้วใช้ broker ที่มี API — **ต้องตัดสินใจก่อน P8 ไม่ใช่ตอน P8**

**Infra อื่น**: Docker + compose, healthcheck, restart policy, DB backup (cron→object storage),
config backup, secret management (ตอนนี้ `.env` ธรรมดา), เพิ่ม service สำหรับ M1 monitor loop

---

## 12. Estimated Complexity

| Phase | Complexity | หมายเหตุ |
|---|---|---|
| P0, P4, P9 | S | ต่อยอดของที่มี |
| P2, P3, P5, P10, P11 | M | งานเยอะแต่ pattern ชัด |
| P6 (AI), P7 (Risk), P12 | L | ตรรกะใหม่ + ต้องการ test หนัก |
| P8 (MT5) | **L** | ลดจาก XL — platform blocker ปิดแล้ว เหลือแค่เลือก broker/บัญชี |


---

## 13. Risks

| # | ความเสี่ยง | ผลกระทบ | การรับมือ |
|---|---|---|---|
| R-1 | **8/8 hypotheses falsified** — อาจไม่มี edge ให้ execute | สูงสุด | ผู้ใช้เลือกสร้าง stack ให้ครบก่อน (2026-09-01) → รับความเสี่ยงนี้ไว้อย่างรู้ตัว; ลด exposure ด้วย P5 status lifecycle (ห้าม setup ที่ยังไม่ VALIDATED ขึ้น LIVE) + P11 WFO + P12 paper 4 สัปดาห์ |
| R-2 | ~~MT5 = Windows-only แต่ VPS = Linux ARM~~ | **ปิดแล้ว** | ย้าย dev/deploy ไป PC Windows (2026-09-01) — ดู §15 ข้อ 2b |
| R-3 | **LLM กลายเป็นทางกลับเข้ามาของสิ่งที่เคยปฏิเสธ** (ML gate AUC 0.497) — scorecard ที่จูนน้ำหนักด้วยมือคือรูปแบบเดียวกัน | สูง | §16.6: bucket test ก่อน, shadow mode, A/B ช่อง Macro, log ทุก call, LLM ลดคะแนนได้แต่เพิ่มไม่ได้, ห้าม bypass Risk Engine |
| R-4 | Lot size ของ XAU บนบัญชีเล็ก (เหตุผลเดิมที่ pivot ออกจาก MT5 — PROJECT_PLAN §0.1) | สูง | ยืนยัน broker/ประเภทบัญชี/ทุน ก่อน P8 |
| R-5 | Cost model ใน `gold_spec.yaml` เป็น "optimistic floor" | สูง | cost stress 2× ก่อนแตะ holdout เสมอ (บทเรียน R2) |
| R-6 | ทำ XAU แล้วทำ ETH/XRP track พัง | กลาง | แยก module path + ไม่แตะ ETH cycle + test เดิมต้องเขียว |
| R-7 | LLM cost บาน (M5 close ทุก 5 นาที) | กลาง | เรียกเฉพาะเมื่อ setup ผ่าน rule filter + budget cap + cache |
| R-8 | D6 (position_timeout ไม่กรอง symbol) ระเบิดเมื่อมีหลาย instrument | กลาง | แก้ก่อนเปิด multi-instrument |
| R-9 | Scope creep — target architecture ใหญ่มากเทียบกับผลวิจัยที่ยังไม่มี edge | กลาง | ยึด Definition of Done ต่อ phase ใน §10, ห้ามข้าม phase |

---

## 14. Testing Plan

- **ชั้น 1 — unit** (ต่อยอดจาก 52 tests ที่มี): feature correctness + **leakage test บังคับ
  ทุก feature ใหม่**, regime classification, risk limits ทุกข้อ (daily loss, DD, consecutive,
  simultaneous, kill switch), session/NFP window, AI schema validation + malformed-response
  handling, broker adapter (mock)
- **ชั้น 1.5 — scorecard bucket test** (§16.6.1): คะแนนสูงต้องให้ mean R ดีกว่าคะแนนต่ำ
  บน labeled trade ที่มีอยู่แล้ว มิฉะนั้น scorecard ไม่ผ่านไปเป็น gate
- **ชั้น 2 — backtest**: reproduce ผล R1–R17 เดิมได้เท่าเดิมหลัง refactor (regression guard),
  walk-forward gate, cost stress 2×/3×, parameter sensitivity plateau check
- **ชั้น 3 — engineering (demo/testnet)**: fault injection (broker down, AI down, data stale,
  order reject, partial fill), duplicate-order protection, reconciliation หลัง process kill
- **ชั้น 4 — shadow**: รันเต็ม pipeline บน feed จริงโดยไม่ยิง order วัด spread/slippage จริง
  เทียบ cost model
- **ชั้น 5 — paper แล้วค่อย small live**

**Regression guard ที่สำคัญที่สุด**: `PYTHONPATH=. .venv/bin/python -m pytest tests -q`
ต้องเขียวทุก commit และ ETH cycle ต้องรันได้เหมือนเดิม

---

## 15. คำตอบจากผู้ใช้ (2026-09-01) และสิ่งที่ยังเปิดอยู่

### ตอบแล้ว

**1. Timezone ของหน้าต่างเทรด = เวลาไทย (UTC+7)** — เหตุผล: เป็นเวลาที่ผู้ใช้เปิดเครื่องมารันเอง
ดังนั้นหน้าต่างจริงคือ **01:00–15:00 UTC**

⚠️ **แก้ข้อความที่ผมเขียนไว้ผิดในร่างแรก**: ผมเขียนว่าหน้าต่างนี้ "ขัดกับ high-liquidity
สาม session" ซึ่งแรงเกินจริง ตรวจกับข้อมูลจริง (`XAUUSD_15m.parquet`, 505k แท่ง, 20 ปี) แล้วได้:

| session (UTC) | อยู่ในหน้าต่าง 01:00–15:00 UTC ไหม |
|---|---|
| ASIA 00–08 | ครอบ 01–08 (ขาดชั่วโมงแรก) |
| LONDON 08–13 | **ครอบเต็ม** |
| OVERLAP 13–16 | ครอบ 13–15 (2 ใน 3 ชม.) |
| NY 16–21 | **ไม่ครอบเลย** |

หน้าต่างนี้กินแท่ง 59.3% ของทั้งหมด แต่กิน **62.4% ของ true-range รวม** — คือหนาแน่นกว่า
ค่าเฉลี่ยเล็กน้อย ไม่ใช่หน้าต่างที่แย่ สิ่งที่เสียไปจริง ๆ คือ **NY session (~37.6% ของ
range) ซึ่งเป็นที่ที่ข่าว US (NFP/CPI/FOMC) ออก** ผลที่ตามมาสองข้อ:
- ข้อดี: การเว้น NFP ตาม §12 แทบเกิดขึ้นเองโดยอัตโนมัติ (NFP ออก 12:30–13:30 UTC = 19:30–20:30
  เวลาไทย ซึ่ง**ยังอยู่ในหน้าต่าง** → ยังต้องทำ blackout จริง อย่าคิดว่ารอดอัตโนมัติ)
- ข้อควรระวัง: hypothesis ทุกตัวที่เคย falsified ถูกทดสอบบน **ทุก session** การจำกัดหน้าต่าง
  เป็นการเปลี่ยนเงื่อนไขการทดสอบ → P11 ต้องรัน WFO ใหม่ภายใต้ session filter นี้ (บังเอิญตรงกับ
  R4 ในแผนวิจัยที่ยังไม่เคยทำ)

**หมายเหตุเชิงสถาปัตยกรรม**: "เปิดเครื่องมารันเอง" หมายความว่า track นี้ **ไม่ใช่ VPS 24/7
เหมือน ETH track** → §17 (Docker/restart policy/health check) ยังทำ แต่ target การ deploy
คือเครื่องผู้ใช้ ไม่ใช่ Oracle VPS ต้องยืนยันข้อนี้ก่อน P10

**2. Broker / MT5 = ยังไม่มีบัญชี ยังไม่ได้เลือก** → P8 ยังไม่มี broker แต่ **มี target
platform แล้ว**

**2b. ย้าย development ไปเครื่อง PC Windows (2026-09-01)** — ผลกระทบใหญ่และเป็นบวก:
- **R-2 ตกไป**: `MetaTrader5` python package เป็น Windows-only ซึ่งเดิมชนกับ Oracle VPS
  (Ubuntu ARM) และ dev Mac (macOS) บน Windows ใช้ได้ตรง ๆ → P8 เดินตามแผน MT5 เดิมได้
  ไม่ต้องหา Wine/VM/REST fallback
- **คำถาม deploy target ได้คำตอบ**: XAU track deploy บนเครื่อง PC ของผู้ใช้ (เปิดเครื่อง
  รันเอง จ–ศ 08:00–22:00 เวลาไทย) **ไม่ใช่** Oracle VPS. ETH/XRP track ยังรันบน VPS ต่อไป
  แยกกัน → §17 (Docker/restart policy/health check) ยังทำ แต่ scope เปลี่ยนเป็น
  "เครื่องเดสก์ท็อปที่ปิดตอนกลางคืน" ซึ่งง่ายกว่า 24/7 uptime มาก
- **ที่ยังเปิดอยู่**: broker ไหน / ประเภทบัญชี / ทุน — PROJECT_PLAN §0.1 เคยพบว่า lot
  ขั้นต่ำของ XAU ทำให้ risk 1% เป็นไปไม่ได้บนทุนเล็ก (เหตุผลเดิมที่ pivot ออกจาก MT5)
  **ข้อนี้ยังไม่หายไปพร้อม R-2** ยังต้องยืนยันก่อน P8

**3. ลำดับ phase = ลำดับเดิม** ไม่แทรก Edge Gate (ดู §0 ข้อ 3 และ §10)

**4. AI layer = Setup Quality Scorecard** (2026-09-01) → รายละเอียดเต็มใน §16

**5. เลือกโมเดลสำหรับ agent team** (2026-09-01) — ตอบคำถาม DeepSeek vs Codex:
- **Layer runtime (§6 Agent 1/2)**: call volume ต่ำเกินกว่าที่ราคาจะเป็นตัวตัดสิน —
  หน้าต่าง 14 ชม. = 168 แท่ง M5/วัน ≈ 3,700 call/เดือน **ถ้าเรียกทุกแท่ง** แต่ §6 ให้เรียก
  เฉพาะตอน setup detected/regime changed ซึ่งเหลือหลักหน่วยต่อวัน → เลือกที่ reliability
  + คุณภาพ structured output ไม่ใช่ราคา คงตามที่ §6 ระบุไว้เดิม (fast/strong model)
  Codex เป็น coding agent ไม่ใช่ endpoint สำหรับตอบ JSON ต่อสัญญาณ — ผิดประเภทสำหรับ layer นี้
- **Layer dev/research (`.claude/agents/`)**: ใช้ Codex เป็น **ที่นั่ง Skeptic** (คนละ
  model family กับตัวที่เขียน strategy/รัน backtest) เหตุผลคือ **correlated blind spot** —
  `05_skeptic.md` มีหน้าที่หาเหตุผลว่าผลลัพธ์อาจเป็นภาพลวงตา ถ้าเป็นโมเดลตระกูลเดียวกับ
  ผู้ผลิตงาน มันจะพลาดจุดเดียวกัน นี่คือตำแหน่งเดียวที่การใช้คนละ vendor คุ้มจริง
- DeepSeek: พิจารณาเฉพาะ layer runtime ถ้าค่าใช้จ่ายกลายเป็นข้อจำกัดจริง ไม่เอาเข้า dev loop

### ยังเปิดอยู่ (ไม่ block P2 แต่ต้องตอบก่อน phase ที่ระบุ)
- **ก่อน P6**: งบ LLM ต่อเดือน (เพดานสำหรับ call policy — R-7)
- **ก่อน P6**: ETH/XRP track บน VPS ให้รันต่อคู่ขนาน หรือ freeze?
- **ก่อน P8**: broker / ประเภทบัญชี / ทุน (ดูข้อ 2b)

## 16. P6 Spec — AI Layer: Setup Quality Scorecard

ข้อกำหนดจากผู้ใช้ 2026-09-01 พร้อมการตัดสินใจที่ตกลงกันแล้ว เขียนไว้ที่นี่เพื่อให้ P6
มี spec ตั้งต้นที่ชัด ไม่ต้องออกแบบใหม่ตอนถึงเฟส

### 16.1 รูปแบบ output

```
Setup Quality
  Trend       82        Structure   76        Momentum    71
  Volatility  88        Session     91        Macro       42
  Risk        85
  Final Score = 78
```

เหตุผลที่ใช้ scorecard แทน `confidence` ตัวเดียว: แต่ละมิติ **falsifiable แยกกันได้** —
เวลาระบบขาดทุนเราตามได้ว่ามิติไหนให้คะแนนผิด ซึ่ง single score ทำไม่ได้

### 16.2 ใครคำนวณช่องไหน (บังคับ — มาจาก §4/§7/§11 ของ TASK_NEW_WORLD.md)

| มิติ | ผู้คำนวณ | แหล่งที่มา |
|---|---|---|
| Trend | **Python** | EMA20/50/200, ADX, H1 alignment (`f01`–`f04`) |
| Structure | **Python** | swing/BOS/CHoCH state machine — **มีโค้ดแล้ว** ใน `gold_r15_choch.py` |
| Momentum | **Python** | `f05_logret_4`, `f06_logret_12`, displacement |
| Volatility | **Python** | `f08_atr_percentile` |
| Session | **Python** | lookup จากชั่วโมง (`_session_for_hour`) |
| **Macro** | **LLM** | ตีความข่าว / event mix / สัญญาณที่ขัดกัน — ช่องเดียวที่ LLM ได้เปรียบจริง |
| Risk | **Python (บังคับ)** | spread, งบ daily-loss ที่เหลือ, ระยะถึง limit — §11 ให้ Risk Engine เป็นเจ้าของ veto |

**หน้าที่จริงของ LLM ใน P6** มี 3 อย่าง ไม่ใช่การให้คะแนนทั้งเจ็ดช่อง:
1. ให้คะแนน **Macro** ช่องเดียว
2. ตอบว่า "มีอะไรที่ตัวเลข 6 ช่องมองไม่เห็น และควร veto ไหม"
3. เขียน `thesis` + `invalidation` + `risk_factors` ตาม JSON schema ใน §6

**กฎทิศทางเดียว: LLM ลดคะแนน / ยับยั้งได้ แต่เพิ่มไม่ได้** — รักษาหลัก
"AI assists. Rules constrain. Risk Engine decides."

### 16.3 Gating policy (ตามที่ผู้ใช้ยืนยัน 2026-09-01)

```
Final Score < 60   → NO_TRADE
60 – 75            → small risk  = 0.25%
> 75               → normal risk = 0.5%   (ตาม §11 risk_per_trade)
```

⚠️ ร่างแรกของผู้ใช้เขียน `75-85 → normal` และ `>85 → normal` ซ้ำกัน — **ยืนยันแล้วว่า
พิมพ์ซ้ำ ไม่ใช่ตั้งใจให้เพิ่ม size** จึงรวมเป็น band เดียว ซึ่งสอดคล้องกับ §20
("❌ Increase leverage because AI confidence is high") ถ้าอนาคตจะให้คะแนนสูงมีผลเพิ่ม
ต้องแก้ §20 อย่างตั้งใจก่อน ห้ามค่อย ๆ เลื่อนเข้ามา

### 16.4 กฎ weakest-link (เพิ่มจากข้อเสนอ audit)

ค่าเฉลี่ยกลบจุดอ่อนได้ — ตัวอย่างที่ให้มา Macro = 42 แต่ Final ยังได้ 78
จึงเพิ่ม: **มิติใดต่ำกว่า 50 → block ทันที ไม่ว่าค่าเฉลี่ยจะเท่าไร**
อธิบายได้ตรงกว่าและจูนน้อยกว่าการไปขยับน้ำหนัก

### 16.5 ⚠️ ความเสี่ยงหลัก: free parameters

น้ำหนักของทั้ง 7 มิติ **ไม่เคยถูกระบุออกมา** และย้อนคำนวณจากตัวอย่างที่ให้มาได้ว่า:

```
equal weight       = 76.43     (ไม่ใช่ 78)
median             = 82
min                = 42
Macro 10% + ที่เหลือ 15% เท่ากัน → 78.15   ← ใกล้ 78 ที่สุด
```

รวม 7 น้ำหนัก + 3 threshold (60 / 75 / 50-weakest-link) = **10 free parameter ที่ตั้งด้วยมือ**
นี่คือรูปแบบเดียวกับที่ `docs/FINDINGS.md` เตือนไว้ และเป็นเหตุผลที่ ML gate เดิมถูกฆ่าทิ้ง
ที่ AUC 0.497 — scorecard ที่จูนด้วยมือคือกล่องดำใบเดิมที่อ่านง่ายขึ้นเท่านั้น

### 16.6 Definition of Done ของ P6 — shadow mode ก่อนเสมอ

1. **Bucket test (ทำได้ทันที ไม่ต้องเรียก LLM สักครั้ง)**: strategy ที่ falsified ทั้ง 8 ตัว
   ทิ้ง labeled trade ไว้หลักพันถึงหมื่นไม้พร้อม `net_r_multiple` (R17 ตัวเดียว n=3,300–10,300
   ต่อ config) → คำนวณ 6 ช่อง deterministic ย้อนหลังบนไม้เหล่านั้น → แบ่ง bucket ตามคะแนน →
   **ตรวจว่า mean R ไล่ขึ้นตามคะแนนจริงไหม** ถ้าคะแนนสูงไม่ได้ให้ R ดีกว่าคะแนนต่ำ
   scorecard คือของประดับ และเรารู้ก่อนลงแรงสร้าง P6 ทั้งเฟส (ราคาถูกมาก harness มีอยู่แล้ว)
2. **Shadow mode**: log scorecard ทุก setup แต่ **ยังไม่ให้คุม risk tier** จนกว่าข้อ 1 จะผ่าน
3. **A/B ของช่อง Macro**: log ทุก LLM call แล้ววัดว่าการเพิ่ม Macro เข้าไปทำให้ separation
   ดีขึ้นจริงหรือไม่ เทียบกับ 6 ช่อง deterministic ล้วน
4. **Fail-safe**: LLM ใช้ไม่ได้ → `Macro = null` → NO NEW TRADE (§17) ไม่ใช่เดาค่ากลางแล้วเทรดต่อ
5. ทุกช่อง + Final + เหตุผล veto ถูกเขียนลง journal **แม้เป็น NO_TRADE** (§14)

### 16.8 Model / provider choice (ตัดสินใจ 2026-09-01)

**ก) ตัด Agent 1 (Market Monitor) ทิ้ง** — §6 เดิมวาง 2 agent (fast screen → strong analyst)
แต่ในสถาปัตยกรรม §16.2 งานของ Agent 1 คือ "setup screening" ซึ่ง Setup Scanner (P5) +
6 คอลัมน์ deterministic ทำไปหมดแล้ว การเอา LLM กรองก่อน LLM อีกตัวทั้งที่ deterministic
layer กรองไปแล้ว = filter ซ้อน filter → **LLM แตะระบบจุดเดียว** (Macro + veto + thesis)
ลดพื้นที่ของ R-3 ไปในตัว

**ข) ไม่ใช้ Claude สำหรับ layer นี้** — เหตุผลจากผู้ใช้: สงวน Claude ไว้ให้งานหลัก
project นี้เป็น project เสริม

> บันทึกข้อเท็จจริงไว้เพื่อการทบทวนภายหลัง: Claude Code subscription (เครื่องมือ dev)
> กับ Anthropic API key (runtime call) เป็นคนละ billing กัน — runtime call ไม่กินโควตา
> Claude Code ผู้ใช้ทราบและยืนยันการตัดสินใจนี้บนฐานการจัดสรรงบรวม ไม่ใช่ความเข้าใจผิด

**ค) Provider: Gemini (Flash tier)** — เลือกเพราะตรงกับโจทย์ "project เสริม ไม่กินงบ":
free tier ครอบ volume ระดับนี้ได้ และมี structured output แบบ JSON schema เป็น first-class
ซึ่งเป็นข้อกำหนดเดียวที่เข้มจริงของ layer นี้
ทางเลือกรอง: **OpenAI** ถ้าเปิดบัญชีสำหรับ Codex (ที่นั่ง Skeptic ตาม §15 ข้อ 5) อยู่แล้ว
→ ผูก vendor เพิ่มเจ้าเดียวแทนสองเจ้า

**ง) ต้นทุนจริงที่ประเมินไว้** (5,000 in / 1,000 out tokens ต่อ call):

| | เรียกเฉพาะตอนมี setup (~100 call/ด.) | worst case ทุกแท่ง M5 ในหน้าต่าง (~3,700 call/ด.) |
|---|---|---|
| tier ถูก (Gemini Flash / Haiku-class) | ~$0–1 | ~$37 |
| tier กลาง (Sonnet-class) | ~$2 | ~$74 |
| tier บน (Opus-class) | ~$5 | ~$185 |

**บรรทัดซ้ายคือของจริง** — §6 ให้เรียกเฉพาะตอน setup detected/regime changed ส่วนต่าง
ระหว่างเจ้าแพงสุดกับถูกสุดจึงเป็นหลักดอลลาร์ต่อเดือน **"ประหยัด" ไม่ใช่เหตุผลเชิงเทคนิค
ที่มีน้ำหนักในการเลือก provider ที่นี่** — เหตุผลที่บันทึกไว้คือการจัดสรรงบข้ามโปรเจกต์

**จ) 4 หลักการที่ใช้ได้กับทุก provider** (ต้องมีครบไม่ว่าเลือกเจ้าไหน):
1. **Structured output ต้อง validate จริงด้วย JSON schema** ไม่ใช่ parse เอาเองแล้วภาวนา
2. **provider + model id อยู่ใน `config/xau.yaml`** ไม่ใช่ในโค้ด — `src/ai/macro_agent.py`
   เป็น interface การเปลี่ยนเจ้าต้องเป็นการแก้ config ไม่ใช่ refactor
3. **Fail-safe ครอบทุกทาง**: exception / timeout / refusal / schema ไม่ผ่าน → `Macro = null`
   → **NO NEW TRADE** (§17) ห้ามเดาค่ากลางแล้วเทรดต่อ
4. **เริ่มที่ reasoning effort ต่ำแล้ววัด** — งานให้คะแนนที่มีขอบเขตชัดมักไม่ต้องใช้ effort สูง
   เป็น cost lever ที่ปรับได้โดยไม่เปลี่ยน provider

**ฉ) การตัดสินใจนี้ reversible** — ด้วยข้อ (จ)2 การสลับ provider คือแก้ config 2 บรรทัด
จึง**ห้ามให้เรื่องนี้บล็อก P2** เลือกไว้ก่อนแล้วทบทวนเมื่อ A/B ใน §16.6.3 มีข้อมูลจริง

**ช) เกณฑ์ที่จะทำให้ทบทวน** (เขียนล่วงหน้ากันการเปลี่ยนใจแบบไร้เกณฑ์):
- ค่าใช้จ่ายจริงเกินเพดาน → ลด effort ก่อน แล้วค่อยลดชั้นโมเดล
- structured output ไม่ผ่าน schema บ่อยจนต้อง retry เป็นประจำ → เปลี่ยน provider
- **A/B (§16.6.3) บอกว่าคอลัมน์ Macro ไม่เพิ่ม separation → ลบ LLM layer ทิ้งทั้งก้อน
  ไม่ใช่ไปหา provider ที่ถูกกว่า** ถ้ามันไม่ช่วย เจ้าที่ถูกกว่าก็ไม่ช่วยเหมือนกัน

### 16.7 ไฟล์ที่ต้องสร้าง (เพิ่มเข้า §9)

```
src/ai/scorecard.py        6 ช่อง deterministic + รวมคะแนน + weakest-link
src/ai/macro_agent.py      ช่อง Macro (LLM) + veto/thesis
tests/test_scorecard.py    รวมถึง monotonicity/บั๊ก weight, weakest-link, fail-safe เมื่อ Macro=null
scripts/research_scorecard_bucket_test.py   ข้อ 16.6.1
```

## 17. สถานะเอกสาร

**P0 (git hygiene) เสร็จแล้ว** 2026-09-01 — แก้ `.gitignore` ที่กลืน
`docs/research/artifacts/` (ผลวิจัย 23 ไฟล์ไม่เคยเข้า git), commit gold track ทั้ง track,
เพิ่ม `requirements.txt` (Python 3.13.7), ตั้ง upstream แล้ว push ขึ้น `origin/main`
— เป็นเงื่อนไขจำเป็นก่อนย้ายเครื่องไป PC

**ยังไม่ implement โค้ดของ target architecture** ตาม §21 ("อย่า implement ก่อนส่ง
Architecture/GAP Analysis ให้ review") คำถาม blocking ใน §15 ได้คำตอบครบแล้ว
งานถัดไปคือ **P2 (XAU data pipeline: เพิ่ม M5/H4 + validation layer)**

### สิ่งที่ไม่เดินทางไปกับ `git clone` (ต้องย้ายเอง)
| ของ | ขนาด | วิธี |
|---|---|---|
| `data/raw/` | 548M (`XAUUSD_1m.parquet` 154M) | ก๊อปตรง — re-fetch M1 จาก Dukascopy ใช้ ~1–2 ชม. |
| `.env` | — | พิมพ์ใหม่บน PC (Binance testnet keys, LINE token) ห้าม commit |
| `.venv/` | — | สร้างใหม่จาก `requirements.txt` ต้องมี Python 3.13.7 |
| `~/.ssh/oracle_trading_vps.key` | — | ก๊อป หรือสร้าง key ใหม่ ถ้ายังต้องคุม VPS ที่รัน ETH/XRP |
