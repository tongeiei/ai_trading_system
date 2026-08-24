# XAU/USD AI Trading System — System Design & Implementation Plan
Version 0.1 (design only, no code)

---

## PIVOT NOTICE (2026-08-24) — เปลี่ยนจาก MT5/XAUUSD ไปเป็น Binance Futures (crypto)

มี Binance account แล้ว → ตัดสินใจไปทาง **crypto perpetual futures** แทน XAU/USD/MT5

**เหตุผลหลัก** (สรุปจากบทสนทนา):
- แก้ปัญหา §0.1 (ทุน 2,000 บาท risk 1% เปิด lot บน XAU ไม่ได้) ได้ทันที — Binance รองรับ fractional position size
- Edge หา ได้ง่ายกว่า (ตลาดใหม่กว่า, inefficiency มากกว่า institutional forex)
- แลกกับ: ไม่มี "EA" ให้พึ่งพา (Risk Manager ต้องอยู่ใน Python execution service เอง), regime เปลี่ยนเร็วกว่า, ไม่มี session gap, testnet ให้ fill/spread เชื่อไม่ได้ (ต้องมีชั้น mainnet-shadow เพิ่ม)

**สถานะเอกสาร:** เนื้อหาหลัก (§0–§21, §22-27 เดิม) ยังเป็น **XAUUSD/MT5 version** และเก็บไว้เป็นข้อมูลอ้างอิง/ future branch — **Phase P0 ใหม่ (Binance) อยู่ท้ายเอกสารนี้** และ `docs/TASKS.md` ปรับ P0 ใหม่แล้ว ให้เริ่มจากตรงนั้น ส่วนที่เหลือ (feature list, risk management, calibration, backtesting) แนวคิดเดิมยังใช้ได้เกือบทั้งหมด เปลี่ยนแค่ execution/data layer — จะพอร์ตทีละหัวข้อเมื่อถึง phase นั้นจริง แทนที่จะ rewrite ทั้งฉบับตอนนี้ (ประหยัดเวลา, ป้องกันเขียนทิ้งของที่ยังไม่ได้ใช้)

**Testing protocol สำหรับ crypto (5 ชั้น) แทนที่ §16-17 เดิม:**
```
1. Unit/logic test (ไม่ต่อเน็ต) — sizing, anti-martingale, risk limits, leakage
2. Backtest offline (mainnet historical klines + funding rate + mark price)
3. Testnet engineering test (testnet.binancefuture.com) — fault injection, ไม่เชื่อ fill/spread
4. Mainnet shadow (real orderbook, ไม่ยิง order จริง) — วัด spread/slippage จริงเทียบ backtest model
5. Mainnet live เงินจริงขั้นต่ำ — risk 0.25% → 0.5% → 1% → 2% (เพดาน, ดู §0.3 คำนวณ risk-of-ruin)
```

---

## 0. Reality Check ก่อนอ่านทั้งหมด (สิ่งที่ต้อง challenge ก่อน)

### 0.1 ปัญหาใหญ่ที่สุด: 2,000 THB ไม่พอสำหรับ risk 1% บน XAUUSD standard account

XAUUSD contract spec มาตรฐาน:
- 1.00 lot = 100 oz → ราคาขยับ $1 = กำไร/ขาดทุน $100
- 0.01 lot (minimum ปกติ) = 1 oz → ราคาขยับ $1 = $1

ATR(14) บน M15 ของทองอยู่ราว **$2.5 – 4.5** (ปี 2024–2026 ผันผวนสูงกว่าอดีตมาก)
SL ที่สมเหตุสมผล = 1.5 × ATR ≈ **$4 – 6**

ดังนั้น **ขาดทุนต่อไม้ที่ lot เล็กที่สุด** = $4 – 6 ≈ **145 – 215 THB**

เทียบกับทุน 2,000 THB → **นั่นคือ 7 – 11% ต่อไม้** ไม่ใช่ 1%
เพื่อจะ risk 1% (20 THB ≈ $0.55) ต้องใช้ lot ≈ **0.0014** ซึ่ง **เปิดไม่ได้**

**สรุป: บัญชี standard/micro ปกติ ทำให้ Risk Management ทั้งหมดในเอกสารนี้ใช้ไม่ได้เลย**
คุณจะไม่ได้เทรดระบบที่ออกแบบไว้ คุณจะได้เทรดระบบ 8% risk ซึ่งล้างพอร์ตภายใน ~12 ไม้ติดลบ

### 0.2 ทางออก 3 ทาง (ต้องเลือกก่อนเริ่ม Phase 1)

| ทางเลือก | รายละเอียด | ประเมิน |
|---|---|---|
| **A. Cent Account** (แนะนำ) | ฝาก 2,000 THB (~$55) = 5,500 cent-USD. 0.01 cent-lot → risk ต่อไม้ ~$0.04. คำนวณ lot ได้ละเอียดจริง | ✅ ทางเดียวที่ทำให้แผนนี้ทำงานได้จริงตามที่ออกแบบ |
| **B. เพิ่มทุนเป็น ~20,000 THB** | ทำให้ 0.01 lot = ~1% risk พอดี | ✅ ถูกต้องทางคณิตศาสตร์ แต่ขัดโจทย์ |
| **C. ใช้ 2,000 THB แล้ว risk 8%/ไม้** | | ❌ นี่คือการพนัน ไม่ใช่ระบบ — ไม่แนะนำ |

**ข้อจำกัดของ Cent Account:** broker ที่มี cent account มักเป็น B-book, spread กว้างกว่า, execution แย่กว่า
→ ผลลัพธ์บน cent account จะ **แย่กว่า** backtest เสมอ และ **ห้ามใช้ผลจาก cent account ประเมิน edge ตรง ๆ** ให้ใช้เพื่อทดสอบ "ระบบทำงานถูกต้องหรือไม่" (engineering test) มากกว่า "ระบบมี edge หรือไม่" (statistical test)

### 0.3 คณิตศาสตร์ของเป้าหมาย 2,000 → 50,000 (25 เท่า)

สมมติระบบมี edge จริง: expectancy **+0.20R ต่อไม้** (ดีมากแล้วสำหรับ retail) และ risk 1%/ไม้
→ growth ต่อไม้ ≈ +0.2% (compounding)
→ จำนวนไม้ที่ต้องใช้ = ln(25) / ln(1.002) ≈ **1,610 ไม้**

ที่ 1–2 ไม้/วัน, 20 วันทำการ/เดือน → **40–80 ไม้/เดือน** → **20 – 40 เดือน (2–3.5 ปี)**

ถ้าเร่งเป็น risk 2%/ไม้ → ~805 ไม้ (~1–1.7 ปี) แต่ **risk of ruin เพิ่มแบบไม่เชิงเส้น** และ drawdown 15% cap จะโดนชนบ่อยมาก

**ข้อสรุปที่ต้องยอมรับ:** เป้าหมายนี้เป็นไปได้ แต่กรอบเวลาคือ **ปี ไม่ใช่เดือน** และ P(สำเร็จ) ตามจริงน่าจะ **< 10%** แม้ระบบดี — ไม่ใช่เพราะระบบ แต่เพราะ variance บนทุนเล็ก + cost drag (spread/commission เป็นสัดส่วนใหญ่ของ R เมื่อ SL แคบ)

### 0.4 สิ่งที่ผมเห็นด้วยกับคุณ (สมมติฐานที่ถูกต้องแล้ว)

- ✅ AI = probability filter ไม่ใช่ signal generator — **ถูกต้องมาก** นี่คือความต่างระหว่างระบบที่รอดกับไม่รอด
- ✅ Risk Manager อยู่ใน EA ใกล้ execution — **ถูกต้อง** Python ตายได้ EA ต้องยังปิดสถานะเป็น
- ✅ XGBoost/LightGBM + calibration > Deep Learning สำหรับ V1 — **ถูกต้อง** ดูหัวข้อ 6
- ✅ ห้าม Martingale/Grid/Averaging — **ถูกต้อง**
- ✅ NO TRADE เป็นคำตอบที่ยอมรับได้ — **ถูกต้อง** ระบบที่ดีจะ NO TRADE 80–90% ของเวลา

### 0.5 สิ่งที่ผมไม่เห็นด้วย / ต้องแก้

- ❌ Multi-timeframe H1+M15+M5 พร้อมกันตั้งแต่ V0 → **overkill** ดูหัวข้อ 3
- ❌ Feature list 18 รายการ → redundancy สูงมาก, ทุนเล็ก + ข้อมูลจำกัด = overfitting แน่นอน ดูหัวข้อ 4
- ❌ Max consecutive losses = 3 → **ต่ำเกินไป** ระบบ win rate 45% จะเจอแพ้ 3 ติดทุก ~15 ไม้ = หยุดระบบตลอดเวลา ควรเป็น 4–5 ดูหัวข้อ 9
- ❌ MCP สำหรับ news ตั้งแต่แรก → V2 เท่านั้น ไม่ใช่ V0/V1
- ⚠️ Market Regime 6 คลาส → V1 ควรมีแค่ 3 คลาส

---

# 1. Executive Summary

**สิ่งที่จะสร้าง:** ระบบเทรด XAU/USD กึ่งอัตโนมัติ ที่ใช้ ML เป็นตัวกรองความน่าจะเป็น ไม่ใช่ตัวตัดสินใจ โดยมี Risk Manager ที่ฝังอยู่ใน EA เป็น authority สุดท้าย

**ปรัชญาแกน:** ระบบไม่ได้ถูกออกแบบให้ชนะ ระบบถูกออกแบบให้ **ไม่ตาย** จนกว่าจะพิสูจน์ได้ว่ามี edge

**เส้นทาง:**

| Version | สาระ | Gate ที่ต้องผ่านก่อนไปต่อ |
|---|---|---|
| **V0** | Rule-based baseline (EMA/ATR/session filter) + Risk Manager เต็มรูปแบบ | Backtest 3 ปี, PF > 1.1, ระบบรันจริงบน demo 4 สัปดาห์ ไม่ crash |
| **V1** | LightGBM probability filter ทับ V0 + calibration | ต้องชนะ V0 อย่างมีนัยสำคัญ (ดูหัวข้อ 14.4) มิฉะนั้น **ตัด ML ทิ้ง** |
| **V2** | News/Economic calendar + MCP | ต้องลด max DD ของ V1 ได้อย่างน้อย 20% |
| **V3** | Advanced (multi-TF ensemble, regime-specific models) | ต้องชนะ V2 อย่างมีนัยสำคัญ |
| **V4** | Production (cent account live, monitoring, auto-retrain) | ผ่าน demo 3 เดือน + forward test |

**Minimum Viable Trading System (สร้างได้ใน 3–4 สัปดาห์):** ดูหัวข้อ 27.0

---

# 2. System Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        DATA LAYER                              │
│  MT5 History (OHLCV M5/M15/H1)  │  Economic Calendar (V2)      │
│  Tick data (spread/slippage)     │  News feed (V2)             │
└────────────┬───────────────────────────────────────────────────┘
             │
┌────────────▼───────────────────────────────────────────────────┐
│                  PYTHON RESEARCH / SIGNAL LAYER                │
│  feature_engine → regime_classifier → model(LGBM) →            │
│  calibrator(isotonic) → EV_calculator → signal_builder         │
│  Output: SignalMessage (JSON)                                  │
└────────────┬───────────────────────────────────────────────────┘
             │  file/socket/ZeroMQ  (signal only, never orders)
┌────────────▼───────────────────────────────────────────────────┐
│                      MT5 EA (MQL5)                             │
│  SignalReader → RiskManager (AUTHORITY) → OrderExecutor        │
│  + independent: DailyLossGuard, DDGuard, SpreadGuard,          │
│    StaleSignalGuard, PositionMonitor, TrailingStop             │
│  EA มีสิทธิ์ REJECT signal ทุกอันโดยไม่ต้องถาม Python           │
└────────────┬───────────────────────────────────────────────────┘
             │
┌────────────▼───────────────────────────────────────────────────┐
│                   PERSISTENCE / OBSERVABILITY                  │
│  SQLite (V0–V2) → PostgreSQL/TimescaleDB (V4)                  │
│  tables: bars, features, signals, orders, trades, model_runs   │
│  Grafana / Streamlit dashboard                                 │
└────────────────────────────────────────────────────────────────┘
```

**หลักการออกแบบ 5 ข้อ:**
1. **EA เป็น authority สุดท้าย** — Python เสนอ, EA ตัดสิน
2. **Fail-closed** — ทุก component ที่พังหรือเงียบ = ไม่เทรด (ไม่ใช่ "เทรดต่อโดยไม่มี filter")
3. **Signal มี TTL** — signal อายุเกิน 60 วินาที = ทิ้ง
4. **Idempotent** — signal มี unique id, EA ไม่ execute ซ้ำ
5. **ทุกอย่าง log ก่อน execute** — เขียน DB ก่อนส่ง order เสมอ

---

# 3. Trading Strategy V1 + Multi-Timeframe Analysis

## 3.1 วิเคราะห์ H1 + M15 + M5 — เหมาะสมหรือไม่?

**คำตอบ: เหมาะสมในเชิงแนวคิด แต่ไม่เหมาะที่จะทำตั้งแต่ V0/V1**

เหตุผลที่ **ควรใช้**:
- ทองมี trend persistence ที่ระดับ H1–H4 ชัดกว่า M5–M15 (M5 คือ noise เกือบทั้งหมด)
- Filter ทิศทางด้วย TF ใหญ่ ลด false signal ได้จริงและวัดได้

เหตุผลที่ **ยังไม่ควรทำตอนนี้**:
- 3 TF = 3 เท่าของ features = 3 เท่าของโอกาส overfit บนข้อมูลชุดเดียว
- M5 entry timing เพิ่ม latency และ slippage แต่ประโยชน์เชิงสถิติมัก **น้อยกว่าที่คิด** — ในการทดสอบส่วนใหญ่ M5 confirmation ให้ผลบวก < 0.05R และถูกกิน spread หมด
- ทองมี spread เฉลี่ย 15–35 points (0.15–0.35 USD) → entry timing ระดับ M5 ให้ประโยชน์ ~0.2 USD ซึ่ง **น้อยกว่า spread**

## 3.2 Architecture ที่แนะนำแทน

**V0/V1: 2 timeframes — H1 (regime) + M15 (setup + entry)**

```
H1  → Market Regime + Trend bias      (อัปเดตทุกแท่ง H1)
M15 → Setup detection + entry + exit  (ตัดสินใจที่ bar close เท่านั้น)
```

**เพิ่ม M5 เฉพาะเมื่อ** พิสูจน์ได้ใน V3 ว่า `E[R | with M5 filter] − E[R | without] > 0.05R` บน out-of-sample และมี trade count เพียงพอ

**ทำไมตัดสินใจที่ bar close เท่านั้น:** intrabar decision ทำให้ backtest กับ live ไม่ตรงกัน และเป็นแหล่ง look-ahead bias อันดับ 1

## 3.3 Strategy V0 (Rule-based baseline — ต้องสร้างก่อนเสมอ)

```
Regime (H1):
  EMA50 > EMA200 และ ADX(14) > 20  → TREND_UP
  EMA50 < EMA200 และ ADX(14) > 20  → TREND_DOWN
  อื่น ๆ                            → RANGE

Entry (M15) — เทรดเฉพาะตามทิศ regime:
  TREND_UP:   ราคา pullback แตะ EMA20(M15) แล้วปิดแท่งกลับขึ้นเหนือ EMA20 → LONG
  TREND_DOWN: mirror → SHORT
  RANGE:      NO TRADE (V0 ไม่เทรด range เลย)

Hard filters (ผ่านทุกข้อจึงเทรด):
  - Session: London 14:00–18:00 หรือ NY 19:30–23:00 (เวลาไทย) เท่านั้น
  - Spread ปัจจุบัน <= 2 × median spread ของ session นั้น
  - ATR(14) M15 อยู่ระหว่าง percentile 20–90 ของ 60 วันย้อนหลัง
  - ไม่มี high-impact news ใน ±30 นาที (V2; V0 ใช้ hardcoded blackout list)

SL = 1.5 × ATR(14) M15
TP = 2.0 × SL   (R:R = 1:2 คงที่)
```

นี่คือ **baseline ที่ ML ต้องเอาชนะให้ได้** ถ้า ML ชนะไม่ได้ → ไม่มี ML

## 3.4 Strategy V1 (ML overlay)

V0 เป็นตัว **สร้าง candidate setup** → ML ตอบว่า **ควรเข้าไหม และเข้าด้วย risk เท่าไร**

```
V0 setup detected
   ↓
Feature vector (ณ เวลา bar close, ไม่มีข้อมูลอนาคต)
   ↓
LightGBM → p_raw
   ↓
Isotonic calibrator → p_cal
   ↓
EV = p_cal × avgWin_R − (1 − p_cal) × 1.0 − cost_R
   ↓
EV >= +0.15R  → ส่ง signal
EV <  +0.15R  → NO TRADE
```

**สำคัญ:** ML ไม่ได้สร้าง setup ใหม่ ML แค่กรอง setup ของ V0 → เปรียบเทียบ V0 vs V1 ได้ตรง ๆ บน trade universe เดียวกัน นี่คือการทดลองที่ควบคุมตัวแปรได้

---

# 4. Feature Engineering

## 4.1 วิเคราะห์ feature list ที่คุณเสนอ

| Feature | เหตุผลเชิงสถิติสำหรับทอง | ตัดสิน V1 |
|---|---|---|
| Raw OHLC | ไม่ stationary — ห้ามใส่ดิบ ๆ เด็ดขาด | ❌ |
| Returns (log, 1/4/12 bars) | Stationary, เป็นฐานของทุกอย่าง | ✅ |
| EMA20/50/200 (ค่าดิบ) | ไม่ stationary | ❌ |
| **Distance from EMA / ATR** | ✅ Stationary + จับ mean-reversion ได้ดีในทอง | ✅ **สำคัญมาก** |
| RSI(14) | สหสัมพันธ์สูงกับ normalized returns — redundant | ⚠️ เลือกอันใดอันหนึ่ง |
| MACD | เป็นฟังก์ชันของ EMA — redundant กับ distance-from-EMA เกือบสมบูรณ์ | ❌ |
| **ATR(14) / ATR percentile** | ✅ ทองมี volatility clustering ชัดมาก | ✅ **สำคัญมาก** |
| **ADX(14)** | ✅ แยก trend/range ได้จริง มีค่าเชิงสถิติ | ✅ |
| Bollinger Bands | %B ≈ ฟังก์ชันของ (price − MA)/σ = redundant กับ distance/ATR | ❌ |
| Realized volatility (std of returns) | สหสัมพันธ์กับ ATR ~0.9 | ❌ เลือก ATR |
| Tick Volume | ทอง spot ไม่มี volume จริง; tick volume = proxy ของ activity เท่านั้น ใช้ได้แต่ noisy | ⚠️ V2 |
| Price structure (HH/HL/LH/LL) | มีค่า แต่ implement ยากและ subjective | ⚠️ V3 |
| Support/Resistance | ค่าขึ้นกับ definition มาก, overfit ง่ายที่สุดในบรรดา features ทั้งหมด | ❌ V1 |
| Breakout flag | ซ้ำกับ distance-from-EMA + ATR | ❌ |
| Candle characteristics (body/range) | ✅ ถูก, ราคาถูก, จับ rejection ได้ | ✅ |
| **Session (one-hot)** | ✅ ทองมี intraday seasonality แข็งแรงมาก (London/NY open) | ✅ **สำคัญมาก** |
| **Spread (ปัจจุบัน / median)** | ✅ เป็นทั้ง cost และ regime proxy | ✅ |
| Time of day (sin/cos ของชั่วโมง) | ซ้ำกับ session — เลือก session ก็พอ | ❌ |

## 4.2 Feature Set V1 (12 features — จบแค่นี้)

```
โครงสร้าง / ทิศทาง (4)
  f01  (close − EMA20_M15) / ATR14_M15
  f02  (close − EMA50_M15) / ATR14_M15
  f03  (EMA50_H1 − EMA200_H1) / ATR14_H1        ← trend ระดับใหญ่
  f04  ADX14_H1

Momentum (2)
  f05  log return 4 แท่ง M15
  f06  log return 12 แท่ง M15

Volatility (3)
  f07  ATR14_M15 / close                         ← normalized vol
  f08  ATR14_M15 percentile (60-day rolling)
  f09  ATR14_M15 / ATR14_M15[24 แท่งก่อน]         ← vol expansion ratio

Microstructure / บริบท (3)
  f10  candle body ratio = |close−open| / (high−low)
  f11  session one-hot {ASIA, LONDON, NY, OVERLAP, OFF}
  f12  spread ปัจจุบัน / median spread ของ session
```

**กติกาเหล็ก 3 ข้อ:**
1. ทุก feature คำนวณจาก **bar ที่ปิดแล้ว** เท่านั้น (`shift(1)` เสมอ)
2. ทุก rolling statistic (percentile, median) ใช้ **expanding/rolling window ที่มองย้อนหลังอย่างเดียว** — ห้ามใช้ค่าจากทั้ง dataset
3. เพิ่ม feature ใหม่ได้ก็ต่อเมื่อผ่าน **permutation importance บน out-of-sample** และเพิ่ม out-of-sample score จริง — ไม่ใช่ train score

## 4.3 Target Definition (สำคัญกว่า feature)

```
label = 1  ถ้า trade แตะ TP ก่อน SL
label = 0  ถ้า trade แตะ SL ก่อน TP
ถ้าไม่แตะทั้งคู่ภายใน N=48 แท่ง M15 (12 ชม.) → ปิดที่ราคาตลาด, label ตาม R ที่ได้ (>0 = 1)
```
ใช้ **triple-barrier method** (López de Prado) และคำนวณด้วย **tick/M1 data** ไม่ใช่ M15 OHLC — เพราะ M15 OHLC บอกไม่ได้ว่า high หรือ low มาก่อน (นี่คือ bug คลาสสิกที่ทำให้ backtest สวยเกินจริง 20–40%)

---

# 5. Market Regime Detection

## 5.1 Rule-based, ML หรือ Hybrid?

**คำตอบ: Rule-based สำหรับ V1, Hybrid สำหรับ V3, ห้ามใช้ pure-ML unsupervised**

- **Rule-based** ✅ อธิบายได้ 100%, ไม่ overfit, debug ได้, เพียงพอสำหรับ 3 regimes
- **HMM / GMM clustering** ❌ regime ที่ได้ไม่ stable ระหว่าง refit, ตีความไม่ได้, และ label สลับกันเองระหว่างรอบ train (label switching problem) — เป็นบ่อเกิดของ bug เงียบ
- **Supervised ML regime** ⚠️ ต้องมี label ซึ่งก็ต้องมาจาก rule อยู่ดี = วนกลับที่เดิม

## 5.2 Regime V1 — 3 คลาส (ไม่ใช่ 6)

```
NEWS_BLACKOUT   (ตรวจก่อนทุกอย่าง — override ทั้งหมด)
    เงื่อนไข: อยู่ในหน้าต่างข่าว high-impact  → หยุดเทรดทั้งหมด

TREND    ADX14_H1 > 22  และ |EMA50−EMA200|/ATR_H1 > 0.5
RANGE    นอกเหนือจากนั้น
```

`HIGH_VOLATILITY` และ `NEWS_SHOCK` **ไม่ควรเป็น regime** — ควรเป็น **risk multiplier แบบต่อเนื่อง** ไม่ใช่ discrete class:

```
vol_multiplier = clip(1.0 / (ATR_percentile / 50), 0.4, 1.0)
  ATR percentile 50 → ×1.00 risk
  ATR percentile 90 → ×0.55 risk
  ATR percentile 95+ → ×0.40 risk (หรือ NO TRADE)
```
เหตุผล: การทำ volatility เป็น discrete class ทำให้เกิด cliff behavior ที่ threshold และ backtest ไวต่อค่า threshold มาก (over-optimization trap)

## 5.3 Regime V3 (ถ้าและเมื่อ V1 พิสูจน์ตัวเองแล้ว)
ขยายเป็น 4 คลาส: TREND_UP / TREND_DOWN / RANGE / TRANSITION โดยใช้ rule + ให้ ML เรียน regime-specific model แยกกัน (ต้องมี ≥ 300 trades ต่อ regime จึงจะ train แยกได้)

---

# 6. AI Model Selection

## 6.1 เปรียบเทียบ

| Model | ข้อดี | ข้อเสียในบริบทนี้ | คะแนน V1 |
|---|---|---|---|
| **Logistic Regression** | อธิบายได้สมบูรณ์, calibrated โดยธรรมชาติ, ต้องการข้อมูลน้อย, overfit ยาก | จับ non-linearity/interaction ไม่ได้ | ⭐⭐⭐⭐ **ใช้เป็น sanity baseline** |
| Random Forest | ทน noise, ไม่ต้อง tune มาก | probability ไม่ calibrated (บีบเข้าหา 0.5), ช้ากว่า, ด้อยกว่า GBM ทุกด้าน | ⭐⭐ |
| XGBoost | แรงมาก, ecosystem ดี | tune ยากกว่า LGBM, ช้ากว่าบน dataset เล็ก | ⭐⭐⭐⭐ |
| **LightGBM** | เร็วที่สุด, จัดการ categorical (session) ได้ในตัว, regularization ดี, monotonic constraints ได้ | overfit ง่ายถ้า leaves เยอะ | ⭐⭐⭐⭐⭐ **เลือกอันนี้** |
| Neural Net (MLP) | จับ interaction ได้ | ต้องการข้อมูล 10–100× ที่คุณมี, probability ไม่ calibrated, ไม่อธิบายได้ | ⭐ |
| LSTM / Transformer | เหมาะกับ sequence | **ผิดเครื่องมือโดยสิ้นเชิงสำหรับ tabular ~5,000 samples** — จะ memorize เท่านั้น | ⭐ (ไม่แนะนำแม้ V3) |

## 6.2 คำตอบต่อสมมติฐานของคุณ

**คุณคิดถูกแล้ว** — LightGBM + probability calibration เหนือกว่า Deep Learning ในโจทย์นี้อย่างชัดเจน เหตุผลเชิงปริมาณ:
- คุณจะมี trade samples ประมาณ **3,000–8,000 ตัว** (3–5 ปี, 3–6 setup/สัปดาห์)
- Signal-to-noise ratio ของ financial data ≈ 0.01–0.05 — DL ต้องการ SNR สูงหรือ sample มหาศาล
- Tabular data ที่ sample < 10k → GBM ชนะ NN แทบทุกครั้ง (ผลนี้ยืนยันซ้ำในวรรณกรรม tabular learning)

## 6.3 Model Spec V1

```
Model:        LightGBM binary classifier
Objective:    binary logloss
Constraints:  num_leaves ≤ 15
              max_depth ≤ 4
              min_data_in_leaf ≥ 100      ← สำคัญที่สุดในการกัน overfit
              feature_fraction 0.7
              bagging_fraction 0.8, bagging_freq 1
              lambda_l2 = 5.0
              n_estimators: early stopping บน validation fold
Monotonic constraints: ใส่ที่ f04 (ADX) และ f12 (spread) ตามความรู้เชิงโดเมน
Baseline ที่ต้องชนะ: Logistic Regression บน feature ชุดเดียวกัน
```
ถ้า LightGBM ชนะ Logistic Regression **ไม่ถึง 3% AUC บน out-of-sample** → ใช้ Logistic Regression (เรียบง่ายกว่า, robust กว่า)

---

# 7. Probability Calibration

นี่คือส่วนที่คุณเน้นถูกที่สุด และเป็นส่วนที่ระบบเทรด retail ทำผิดมากที่สุด

## 7.1 Pipeline

```
train fold        → fit LightGBM        → p_raw
calibration fold  → fit Isotonic Regression (แยก fold, ห้ามใช้ fold เดียวกับ train)
                    → p_cal = isotonic(p_raw)
test fold         → วัด calibration บน p_cal เท่านั้น
```

**Isotonic vs Platt (sigmoid):**
- Isotonic ✅ ยืดหยุ่นกว่า, ไม่ assume รูปแบบ, ต้องการ ≥ 1,000 samples → **ใช้อันนี้ถ้ามีข้อมูลพอ**
- Platt scaling ใช้เมื่อ calibration set < 1,000 samples

## 7.2 Metrics ที่ต้องรายงานทุกครั้ง

| Metric | นิยาม | เกณฑ์ผ่าน |
|---|---|---|
| **Brier Score** | mean((p − y)²) | ต้องต่ำกว่า base rate Brier (= p̄(1−p̄)) |
| **Brier Skill Score** | 1 − BS/BS_ref | > 0.02 (ถือว่ามีสาระแล้วในตลาด) |
| **ECE** (Expected Calibration Error) | ถ่วงน้ำหนักโดยขนาด bin ของ \|acc − conf\| | **< 0.05** |
| **MCE** (Max Calibration Error) | max ต่อ bin | < 0.15 |
| **Reliability Curve** | plot 10 bins, predicted vs observed | ต้องอยู่ในแถบ 95% binomial CI |
| **AUC / PR-AUC** | discrimination | AUC > 0.55 out-of-sample (0.55 ถือว่าดีแล้วสำหรับตลาด) |

## 7.3 การทดสอบที่คุณขอโดยตรง ("70% ต้องชนะ ~70% จริงไหม")

**Calibration Bin Test** — รันบน out-of-sample ทุกครั้งก่อน deploy:
```
สำหรับแต่ละ bin [0.5–0.55), [0.55–0.60), ... [0.75–0.80), ...
  รายงาน: n, mean predicted p, observed win rate, 95% Wilson CI
  ผ่านก็ต่อเมื่อ: mean predicted p อยู่ใน CI ของ observed win rate
  bin ที่ n < 30 → ระบุว่า "ข้อมูลไม่พอ" และ ห้ามเทรดในช่วง p นั้น
```

**Guardrail สำคัญ:** ถ้า bin ใดมี n < 30 → EA ต้องปฏิเสธ signal ที่ตกใน bin นั้น
นี่คือกลไกที่ทำให้ระบบ "ไม่สร้างตัวเลข probability ที่ไม่มีความหมายทางสถิติ" ตามที่คุณต้องการ

## 7.4 Calibration Drift Monitoring (live)
ทุก 50 trades ที่ปิดจริง → คำนวณ ECE บน live trades → ถ้า ECE > 0.10 → **ระบบเข้าโหมด reduced risk (×0.5)** และแจ้งเตือน; ถ้า ECE > 0.15 → หยุดระบบ retrain

---

# 8. Expected Value

## 8.1 สูตร (แก้ไขจากที่คุณเสนอ — ของคุณลืม cost)

```
R_win  = (TP_distance − spread_entry − spread_exit − commission_in_R)
R_loss = (SL_distance + slippage_expected) / SL_distance   ≈ 1.0 + slip_R

EV_R = p_cal × R_win_R  −  (1 − p_cal) × R_loss_R
```

ตัวอย่างจริง (บัญชี cent, SL = $4.00, TP = $8.00, spread = $0.25, slippage เฉลี่ย $0.10):
```
R_win_R  = (8.00 − 0.25 − 0.10) / 4.00 = 1.91R   (ไม่ใช่ 2.00R!)
R_loss_R = (4.00 + 0.10) / 4.00       = 1.03R

p_cal = 0.45 → EV = 0.45(1.91) − 0.55(1.03) = 0.860 − 0.567 = +0.293R  ✅
p_cal = 0.38 → EV = 0.38(1.91) − 0.62(1.03) = 0.726 − 0.639 = +0.087R  ❌ (< 0.15 threshold)
```

**หมายเหตุ:** ตัวอย่างของคุณ (65% win, 1.5R, EV +0.625R) เป็นตัวเลขที่ **ดีเกินจริงมาก** ระบบที่มี EV +0.6R จะทำเงินได้เร็วกว่าที่แทบไม่มีใครทำได้ — ตัวเลขที่สมจริงคือ **+0.05R ถึง +0.25R**

## 8.2 Decision Rule

```
EV_R < 0.15                    → NO TRADE
0.15 ≤ EV_R < 0.30             → เทรดที่ base risk × 0.6
EV_R ≥ 0.30                    → เทรดที่ base risk × 1.0
EV_R ≥ 0.50 และ p_cal bin n≥100 → base risk × 1.25 (เพดาน)
```
**ห้ามใช้ Kelly เต็ม** — Kelly เต็มบน edge ที่ประมาณผิดจะล้างพอร์ต ใช้ **fractional Kelly ≤ 0.25×** เท่านั้น และเพดานที่ risk cap ด้านล่างเสมอ

**คำตอบต่อคำถามคุณ:** ใช่ ระบบจะปฏิเสธ trade ที่ probability สูงแต่ EV ติดลบได้ — เช่น p=0.70 แต่ TP แคบมาก (R_win = 0.3R) → EV = 0.7(0.3) − 0.3(1.03) = −0.10R → NO TRADE ✅

---

# 9. Risk Management (Risk Manager Spec)

## 9.1 Risk Manager อยู่ใน EA — Layered Checks

Signal ต้องผ่าน **ทุกชั้น** จึงจะถูก execute; ชั้นใดชั้นหนึ่ง fail → reject + log เหตุผล

```
L0  KILL SWITCH        global_enabled == true?
L1  SIGNAL VALIDITY    age < 60s? signature ถูกต้อง? id ไม่ซ้ำ?
L2  CONNECTION         terminal connected? ราคาล่าสุด < 5s?
L3  MARKET STATE       spread ≤ maxSpread? market open? ไม่อยู่ใน news blackout?
L4  ACCOUNT STATE      daily loss < limit? DD < limit? consecutive losses < limit?
L5  EXPOSURE           ไม่มี position เปิดอยู่ (V1 = 1 position เท่านั้น)? 
                       trades วันนี้ < maxTradesPerDay?
L6  SIZING             lot ที่คำนวณ ≥ minLot และ ≤ maxLot? margin พอ?
L7  SANITY             SL/TP distance สมเหตุสมผล? SL อยู่ฝั่งถูกต้อง? 
                       risk คำนวณแล้ว ≤ hard cap?
→ EXECUTE
```

## 9.2 พารามิเตอร์ (แก้ไขจากที่คุณเสนอ)

| พารามิเตอร์ | ค่าคุณ | ค่าที่แนะนำ | เหตุผล |
|---|---|---|---|
| Risk / trade | 0.5–1% | **0.5% (เดือน 1–3) → 1.0% (หลังพิสูจน์ 100 trades)** | เริ่มต่ำจนกว่า calibration จะพิสูจน์ตัวเอง |
| Max daily loss | 3% | **3%** ✅ | เหมาะสม |
| Max consecutive losses | 3 | **5** ⚠️ **แก้** | ระบบ win rate 45% เจอแพ้ 3 ติด ทุก ~15 ไม้ (P=16.6%) → หยุดตลอดเวลาโดยไม่มีเหตุผลทางสถิติ. แพ้ 5 ติดที่ 45% WR = P 5% ต่อ window ซึ่งเป็นสัญญาณจริงกว่า |
| Max drawdown | 15% | **15% soft (หยุด 48 ชม. + review) / 25% hard (ปิดระบบถาวร รอ retrain)** | 15% เดียวเป็น hard stop จะจบเร็วเกินไป — DD 15% เป็นเรื่องปกติมากสำหรับระบบที่มี edge จริง |
| Max trades / day | ไม่ระบุ | **3** | กัน overtrading และ cost drag |
| Max positions | ไม่ระบุ | **1** | ทุนเล็ก, ห้ามมี correlated exposure |
| Cooldown หลังแพ้ | ไม่ระบุ | **2 แท่ง M15** | กัน re-entry ทันทีในสภาพตลาดเดิม |

## 9.3 Recovery Protocol (หลังชน limit)
```
Daily loss hit    → หยุดจนถึง 00:00 server time วันถัดไป (อัตโนมัติ)
5 consecutive     → หยุด 24 ชม. + ต้องมี manual review + risk ×0.5 สำหรับ 20 ไม้ถัดไป
DD 15%            → หยุด 48 ชม. + วิเคราะห์: bug? regime change? calibration drift?
                    กลับมาที่ risk ×0.5 เสมอ, ต้องทำกำไรกลับ 5% จึงกลับ risk เต็ม
DD 25%            → ปิดระบบ. ห้ามเปิดใหม่จนกว่าจะ retrain + re-validate เต็มรูปแบบ
```

## 9.4 สิ่งที่ห้ามเด็ดขาด (บังคับใน code review checklist)
- ❌ Martingale / เพิ่ม lot หลังแพ้ ทุกรูปแบบ
- ❌ Grid / averaging down / hedging
- ❌ ขยับ SL ให้ห่างออก (SL ขยับได้ทางเดียว: เข้าหากำไร)
- ❌ Daily profit target ที่บังคับให้ต้องเทรด
- ❌ "recovery mode" ที่เพิ่ม risk
- ❌ ปิดระบบ risk check ด้วย manual override ใด ๆ

**หมายเหตุ:** เขียน unit test ที่ assert ว่า `lot_size` ไม่เคยเป็นฟังก์ชันของ "ผลลัพธ์ trade ก่อนหน้า" — เป็น regression test ที่ต้องมี

---

# 10. Position Sizing

## 10.1 สูตร (ถูกต้องตาม MT5 spec)

```
risk_amount_acct = equity × risk_pct × vol_multiplier × ev_multiplier

sl_distance_price = |entry − sl|                      (หน่วย: ราคา, เช่น 4.00 USD)

value_per_lot_per_price_unit
    = (tick_value / tick_size)                        ← ได้จาก MT5 โดยตรง
      หมายเหตุ: tick_value เป็นสกุลของบัญชี ไม่ใช่ USD เสมอ

loss_per_lot = sl_distance_price × (tick_value / tick_size)

lot_raw = risk_amount_acct / loss_per_lot

lot = floor(lot_raw / lot_step) × lot_step
lot = clamp(lot, min_lot, max_lot)
```

## 10.2 ข้อมูลที่ต้องดึงจาก MT5 (ห้าม hardcode)

| MQL5 property | ใช้ทำอะไร |
|---|---|
| `SYMBOL_TRADE_CONTRACT_SIZE` | ตรวจสอบ spec (100 oz ปกติ, บาง broker 10) |
| `SYMBOL_TRADE_TICK_SIZE` | ตัวหารในสูตร |
| `SYMBOL_TRADE_TICK_VALUE` | ตัวคูณในสูตร (**สกุลบัญชี**) |
| `SYMBOL_VOLUME_MIN` | เพดานล่าง |
| `SYMBOL_VOLUME_MAX` | เพดานบน |
| `SYMBOL_VOLUME_STEP` | ปัดลง |
| `SYMBOL_TRADE_STOPS_LEVEL` | SL/TP ต้องห่างจากราคาอย่างน้อยเท่านี้ |
| `SYMBOL_TRADE_FREEZE_LEVEL` | ห้ามแก้ไข order ในระยะนี้ |
| `SYMBOL_DIGITS`, `SYMBOL_POINT` | ปัดราคา |
| `SYMBOL_SPREAD` (หรือ ask−bid) | filter + cost |
| `ACCOUNT_LEVERAGE`, `ACCOUNT_MARGIN_FREE` | ตรวจ margin |
| `SYMBOL_MARGIN_INITIAL` | ตรวจ margin |
| `ACCOUNT_CURRENCY` | ตรวจสอบสกุล + FX conversion |

## 10.3 กรณีวิกฤต — ตัวอย่างจริงกับทุนคุณ

**บัญชี standard, equity 2,000 THB (~$55), risk 1% = $0.55, SL = $4.00:**
```
loss_per_0.01lot = 4.00 × 1.0 = $4.00
lot_raw = 0.55 / 400 = 0.00138
→ ปัดเป็น 0.00 → EA ต้อง REJECT signal
```
**นี่คือพฤติกรรมที่ถูกต้อง** — EA ต้อง reject ไม่ใช่ "ปัดขึ้นเป็น min_lot" (การปัดขึ้นคือการทำลาย risk management ทั้งระบบ)

**บัญชี cent, equity 5,500 cent-USD, risk 1% = 55 cent-USD, SL = $4.00:**
```
loss_per_0.01lot(cent) = $0.04
lot_raw = 0.55 / 4.00 (ในหน่วย cent-account) → ~0.13 lot
→ ✅ execute ได้ และ granular พอที่จะ scale ตาม equity ได้จริง
```

**บังคับ:** EA ต้องมี boot-time check — คำนวณ lot ที่ risk เป้าหมายบน ATR ปัจจุบัน ถ้าได้ < min_lot → ขึ้น alert "ACCOUNT TOO SMALL FOR THIS SPEC" และปฏิเสธการทำงาน

---

# 11. SL / TP Logic

## 11.1 เปรียบเทียบ SL

| วิธี | ข้อดี | ข้อเสีย | V1? |
|---|---|---|---|
| **ATR-based** | ปรับตาม volatility อัตโนมัติ, objective, backtest ได้ตรง | ไม่รู้ว่ามี structure ตรงไหน | ✅ **เลือก** |
| Structure-based | มีเหตุผลทางตลาด, มักได้ R:R ดีกว่า | นิยาม swing ต่างกัน = ผลต่างกันมาก, overfit ง่าย | V3 |
| Fixed % / fixed pip | ง่ายที่สุด | พังทันทีเมื่อ volatility เปลี่ยน — ทองเปลี่ยนบ่อยมาก | ❌ |
| Volatility-adjusted | = ATR-based โดยเนื้อหา | — | (ซ้ำ) |

## 11.2 V1 Spec (เรียบง่ายที่สุด)

```
SL = 1.5 × ATR(14) M15
     พร้อมเพดาน: clamp(SL, 0.8 × ATR, 3.0 × ATR)
     และ SL ≥ SYMBOL_TRADE_STOPS_LEVEL + spread × 2

TP = 2.0 × SL   (R:R คงที่ 1:2)

ไม่มี trailing. ไม่มี partial close. ไม่มี breakeven move.
```

**ทำไมไม่มี trailing/partial ใน V1:** ทั้งสองอย่างเพิ่มพารามิเตอร์ให้ optimize = เพิ่มพื้นที่ overfit และทำให้ label (triple-barrier) กับ execution จริงไม่ตรงกัน → เปรียบเทียบ V0 vs V1 ไม่ได้อีกต่อไป

## 11.3 V2/V3 additions (ทดสอบทีละอย่าง เทียบกับ V1)
- Breakeven move เมื่อ +1R (ทดสอบว่าเพิ่ม expectancy หรือลด)
- Partial close 50% ที่ +1R, ที่เหลือ trail ด้วย 2×ATR
- Structure-based SL (swing low/high ล่าสุด + 0.5 ATR buffer)
**แต่ละอันต้องผ่าน walk-forward เทียบกับ V1 baseline ก่อนรับเข้า**

---

# 12. MT5 + Python + EA Architecture

## 12.1 คำตอบ: Python ส่ง signal → EA execute (ที่คุณสนใจ) — **ถูกต้อง**

| Architecture | ความปลอดภัย | ประเมิน |
|---|---|---|
| Python ส่ง order เอง (MetaTrader5 lib) | ❌ Python crash = position ค้างไม่มีใครดูแล; risk logic ตายไปพร้อม process | ไม่แนะนำสำหรับ live |
| **Python ส่ง signal → EA validate + execute** | ✅ EA รันใน terminal, มี OnTick() ตลอด, จัดการ position ได้แม้ Python ตาย | ✅ **เลือกอันนี้** |
| EA ทำทุกอย่าง (ML ใน MQL5) | ✅ ปลอดภัยที่สุด | ❌ ทำ ML ใน MQL5 ไม่คุ้ม |

## 12.2 Contract ระหว่าง Python กับ EA

**Transport V1:** ไฟล์ JSON ใน `MQL5/Files/signals/` (atomic write: เขียน `.tmp` แล้ว rename)
เหตุผล: ไม่มี dependency, debug ง่าย, ทน crash. **V4** ค่อยเปลี่ยนเป็น ZeroMQ ถ้าต้องการ latency ต่ำ (แต่ M15 bar close ไม่ต้องการ latency ต่ำเลย)

```json
{
  "signal_id": "uuid",
  "schema_version": 1,
  "created_at_utc": "2026-08-20T14:30:02Z",
  "expires_at_utc": "2026-08-20T14:31:02Z",
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "bar_time_utc": "2026-08-20T14:30:00Z",
  "action": "LONG",
  "p_long": 0.72, "p_short": 0.16, "p_notrade": 0.12,
  "p_calibrated": 0.68,
  "calibration_bin_n": 412,
  "regime": "TREND",
  "vol_percentile": 62,
  "news_risk": "LOW",
  "expected_value_r": 0.31,
  "suggested_sl_price": 3312.40,
  "suggested_tp_price": 3324.80,
  "suggested_risk_pct": 0.6,
  "model_version": "lgbm_v1.3_2026-07-01",
  "hmac": "..."
}
```

**สิ่งที่ EA ต้องทำ (ไม่ใช่แค่ execute ตาม):**
- คำนวณ lot **เอง** จาก spec ปัจจุบันของ broker (ไม่เชื่อ lot จาก Python)
- ตรวจ SL/TP ที่ Python ส่งมาว่าสมเหตุสมผลกับราคาปัจจุบัน (ราคาอาจขยับไปแล้ว)
- ถ้าราคาขยับเกิน 0.3 × SL จากราคาตอนสร้าง signal → **reject** (signal stale)
- ปฏิเสธได้เสมอ และ log เหตุผลลง DB

## 12.3 Process Layout
```
Windows VPS (หรือ Windows machine ที่เปิดตลอด)
├── MT5 Terminal  (EA attached to XAUUSD M15)
├── python signal_service.py   (รันทุก bar close M15 + 2 วินาที)
├── python heartbeat.py        (เขียน heartbeat ทุก 10 วินาที; EA อ่าน — ไม่มี heartbeat = ไม่รับ signal ใหม่)
└── SQLite / Postgres
```

---

# 13. Database Schema

```sql
-- ข้อมูลตลาด
bars(symbol, timeframe, time_utc PK, open, high, low, close, tick_volume, spread_avg)

-- feature snapshot ณ เวลาตัดสินใจ (immutable, สำหรับ reproducibility)
features(id PK, symbol, timeframe, bar_time_utc, feature_json, feature_set_version,
         created_at_utc)

-- regime
regimes(bar_time_utc PK, symbol, regime, adx, atr_percentile, vol_multiplier)

-- economic calendar (V2)
econ_events(id PK, event_time_utc, country, event_name, importance,
            forecast, previous, actual, actual_published_at_utc,  -- สำคัญ! กัน leakage
            surprise_z, source, ingested_at_utc)

-- news (V2)
news_items(id PK, published_at_utc, ingested_at_utc, headline, source,
           sentiment_score, relevance_gold, entities_json)

-- signal ทุกอันที่ model สร้าง (รวมที่ NO TRADE)
signals(signal_id PK, created_at_utc, bar_time_utc, symbol, timeframe,
        action, p_long, p_short, p_notrade, p_calibrated, calibration_bin_n,
        regime, news_risk, expected_value_r,
        suggested_sl, suggested_tp, suggested_risk_pct,
        model_version, feature_id FK, decision, decision_reason)

-- การตัดสินของ EA (สำคัญมากสำหรับ error analysis)
risk_decisions(id PK, signal_id FK, received_at_utc, accepted BOOL,
               reject_layer, reject_reason, computed_lot,
               equity_at_decision, spread_at_decision, daily_pnl_at_decision)

-- คำสั่งและผลลัพธ์
orders(order_id PK, signal_id FK, sent_at_utc, mt5_ticket, type, requested_price,
       requested_lot, retcode, retcode_comment)

trades(trade_id PK, order_id FK, signal_id FK,
       entry_time_utc, entry_price, exit_time_utc, exit_price, lot,
       sl_price, tp_price, exit_reason,        -- TP/SL/manual/timeout/failsafe
       gross_pnl, commission, swap, net_pnl,
       r_multiple, mae_r, mfe_r,               -- max adverse/favorable excursion
       spread_entry, spread_exit, slippage_entry, slippage_exit,
       regime, session, news_state)

-- การประเมินโมเดล
model_runs(run_id PK, model_version, trained_at_utc, train_start, train_end,
           val_start, val_end, test_start, test_end,
           feature_set_version, hyperparams_json,
           auc_train, auc_val, auc_test, brier_test, ece_test, mce_test,
           n_train, n_val, n_test, artifact_path, git_commit)

calibration_bins(run_id FK, bin_lo, bin_hi, n, mean_pred, observed_rate, ci_lo, ci_hi)

-- สถานะระบบ
system_state(key PK, value, updated_at_utc)   -- kill_switch, daily_pnl, consec_losses, ...
system_events(id PK, time_utc, severity, component, event, detail_json)
equity_curve(time_utc PK, balance, equity, open_positions, drawdown_pct)
```

**หลักการ:** `signals` เก็บ **ทุก** signal รวมที่ไม่ได้เทรด — ไม่งั้นจะประเมิน model ไม่ได้เลย (survivorship bias ในข้อมูลตัวเอง)

---

# 14. Backtesting Framework

## 14.1 สถาปัตยกรรม
```
Event-driven backtester (ห้ามใช้ vectorized สำหรับ final validation)
  ทำงานทีละแท่ง, มองเห็นเฉพาะข้อมูลถึงแท่งปัจจุบัน
  ใช้ M1 หรือ tick data ในการจำลอง intrabar path (ตัดสิน TP/SL ก่อนหลัง)
  จำลอง: spread จริงตามเวลา (ไม่ใช่ค่าคงที่), commission, swap, slippage model
```

**Slippage model V1:**
```
slippage = base_slip + k × (spread_ratio − 1) + news_slip
  base_slip = 0.05 USD (นอกข่าว)
  news_slip = 0.50 USD (ภายใน 5 นาทีหลังข่าวใหญ่)
  ทดสอบ sensitivity ที่ 1× / 2× / 3× ของ slippage — ถ้าระบบพังที่ 2× แปลว่า edge บาง
```

## 14.2 Data Split
```
2019–2022  Train           (4 ปี)
2023       Calibration     (1 ปี, แยกจาก train)
2024       Validation      (1 ปี — ใช้ tune hyperparams)
2025–2026  Test / Holdout  (แตะได้ครั้งเดียว ก่อน deploy)
```
**กติกาเหล็ก:** Holdout ดูได้ **ครั้งเดียว** ถ้าดูแล้วไม่ผ่านแล้วกลับไปแก้ model → holdout กลายเป็น validation set และคุณไม่มี holdout อีกแล้ว ต้องรอข้อมูลใหม่

## 14.3 Metrics ที่ต้องรายงาน (ตามที่คุณขอ + เพิ่ม)

| กลุ่ม | Metrics |
|---|---|
| Return | Total return, CAGR, Expectancy (R), Average R, Median R |
| Risk | Max DD %, Max DD duration, Ulcer Index, Max consecutive losses |
| Ratio | Profit Factor, Sharpe (annualized), Sortino, Calmar, Recovery Factor |
| Quality | Win rate, Payoff ratio, **t-stat ของ mean R**, **Deflated Sharpe Ratio** |
| Cost | Total spread paid (R), total slippage (R), **cost เป็น % ของ gross profit** |
| Breakdown | ผลตาม regime / session / วันในสัปดาห์ / ATR percentile / news state / p_cal bin |
| Stability | Rolling 100-trade expectancy, equity curve linearity (R² ของ log equity) |

**เกณฑ์ผ่านของ V0 (ถือว่ามี baseline ที่ใช้ได้):**
- Profit Factor > 1.10 บน out-of-sample
- Trade count > 200
- Cost < 40% ของ gross profit
- ผลเป็นบวกในอย่างน้อย 3 จาก 4 ไตรมาสของ test period

**เกณฑ์ผ่านของ V1 (ML คุ้มค่า):** ดู 14.4

## 14.4 Minimum Sample Size — คำตอบตรงคำถามคุณ

ใช้ t-test บน mean R เพื่อหาจำนวนไม้ที่ต้องมี:
```
n ≥ (t_crit × σ_R / expectancy)²
```
ด้วย σ_R ≈ 1.2 (ปกติสำหรับระบบ R:R 1:2) และ t_crit = 1.96:

| Expectancy จริง | ไม้ที่ต้องมีเพื่อมั่นใจ 95% |
|---|---|
| +0.40R (ดีมาก) | ~35 ไม้ |
| +0.25R (ดี) | ~90 ไม้ |
| +0.15R (สมจริง) | **~250 ไม้** |
| +0.10R (บาง) | ~550 ไม้ |
| +0.05R | ~2,200 ไม้ |

**คำตอบปฏิบัติ:**
- **< 100 ไม้** → ไม่มีความหมายเลย อย่าสรุปอะไรทั้งสิ้น
- **200–300 ไม้** → เริ่มมีสัญญาณ พอเริ่ม demo ได้
- **500+ ไม้ ครอบคลุม ≥ 2 regime ต่างกัน** → เริ่มเชื่อได้จริง
- **ต้องครอบคลุมอย่างน้อย 2 ปีปฏิทิน** เพื่อให้เจอ regime หลากหลาย (ทองปี 2022 ต่างจาก 2024 มาก)

**เกณฑ์ "ML คุ้มค่า" (สำหรับตัดสินว่าจะตัด AI ทิ้งไหม):**
```
V1 ต้องมี expectancy สูงกว่า V0 อย่างน้อย +0.10R
และ paired bootstrap test (10,000 resamples) ให้ p < 0.05
บน trade set เดียวกัน (V1 เป็น subset ของ V0 signals)
ถ้าไม่ผ่าน → deploy V0 อย่างเดียว ตัด ML ทิ้ง
```

---

# 15. Walk-Forward Testing

```
Anchored walk-forward, retrain ทุก 3 เดือน:

Fold 1:  train 2019-01..2021-12 | cal 2022-Q1 | test 2022-Q2
Fold 2:  train 2019-01..2022-03 | cal 2022-Q2 | test 2022-Q3
Fold 3:  train 2019-01..2022-06 | cal 2022-Q3 | test 2022-Q4
...
รวม ~14 folds จนถึง 2026
```

**Purging & Embargo (บังคับ):**
- **Purge:** ตัด sample ที่ label window ทับกับ test period ออกจาก train (label ใช้เวลา 12 ชม. → purge 12 ชม.)
- **Embargo:** ทิ้ง 1 วันทำการหลัง train period ก่อนเริ่ม test (กัน serial correlation leakage)

**สิ่งที่ walk-forward บอกเราจริง ๆ:**
- **Walk-Forward Efficiency** = OOS expectancy / IS expectancy → ต้อง **> 0.5** (ถ้า < 0.3 = overfit ชัดเจน)
- **Consistency** — กี่ fold ที่เป็นบวก → ต้อง ≥ 60% ของ folds
- **Parameter stability** — hyperparams ที่เลือกในแต่ละ fold ควรใกล้เคียงกัน ถ้ากระโดดไปมา = ไม่มี signal จริง

---

# 16. Demo Testing (Forward Test)

```
Phase A — Engineering validation (2 สัปดาห์)
  Objective: พิสูจน์ว่าระบบทำงานถูกต้อง (ไม่ใช่ทำกำไร)
  วัด: - signal ที่ Python สร้าง ตรงกับที่ backtest จะสร้าง 100% หรือไม่ (replay test)
       - EA reject ถูกต้องทุกกรณีหรือไม่ (fault injection: ตัดเน็ต, spread พุ่ง, kill Python)
       - ทุก trade มี record ครบใน DB
  Acceptance: 0 discrepancy, 0 unhandled exception, 0 orphan position

Phase B — Statistical forward test (8–12 สัปดาห์, demo account)
  Objective: OOS จริงที่ไม่มีทางโกงได้
  วัด: expectancy, ECE บน live signals, slippage จริง vs model, spread จริง vs backtest
  Acceptance: - expectancy ≥ 50% ของที่ backtest ทำนาย
              - ECE < 0.08 บน live predictions
              - slippage จริง ≤ 1.5× ที่ model ไว้
              - ไม่มี unexplained trade
  ถ้า expectancy จริง < 30% ของ backtest → กลับไป Phase 15, สงสัย leakage
```

**Backtest–Live divergence เป็นสัญญาณเตือนที่สำคัญที่สุด** — ถ้าห่างกันมาก แปลว่า backtest ผิด ไม่ใช่ "ตลาดเปลี่ยน"

---

# 17. Live Deployment

```
Stage 1  Cent account, risk 0.25%, 4 สัปดาห์  → เป้าหมาย: ไม่มี technical incident
Stage 2  Cent account, risk 0.50%, 8 สัปดาห์  → เป้าหมาย: expectancy > 0 ที่ n ≥ 60
Stage 3  Cent account, risk 1.00%             → เมื่อสะสม 150+ live trades ที่ expectancy > 0
Stage 4  พิจารณาย้ายไป standard account       → เมื่อ equity ≥ 20,000 THB เท่านั้น
```

**Go-live checklist:**
- [ ] Kill switch ทดสอบแล้ว (หยุดได้ภายใน 1 tick)
- [ ] ทดสอบ VPS restart แล้ว position ไม่ค้าง
- [ ] Alert ส่งถึงมือถือได้จริง (ทดสอบแล้ว)
- [ ] DB backup อัตโนมัติทำงาน
- [ ] Broker spec ตรงกับที่ backtest (contract size, tick value, commission)
- [ ] มีเงินที่ยอมเสียได้ทั้งหมดเท่านั้นในบัญชี

---

# 18. Monitoring

**Realtime (EA + heartbeat):** connection, spread, equity, DD, open position, signal age
**Daily (automated report):** trades, P&L in R, reject reasons breakdown, slippage vs model
**Weekly:** expectancy rolling 50/100 trades, calibration ECE, performance by regime
**Monthly:** full re-evaluation, decide retrain

**Alert levels:**
| Level | ตัวอย่าง | Action |
|---|---|---|
| INFO | trade เปิด/ปิด | log |
| WARN | spread สูงผิดปกติ, reject rate > 80% | แจ้งเตือน |
| ERROR | MT5 disconnect, DB write fail, signal service ตาย | แจ้งเตือน + หยุดเปิด position ใหม่ |
| CRITICAL | DD > 12%, orphan position, calibration ECE > 0.15 | **kill switch อัตโนมัติ** + แจ้งเตือนทันที |

---

# 19. Failure Handling (Fail-safe Matrix)

หลักการเดียว: **ถ้าไม่แน่ใจ → ไม่เทรด** และ **position ที่เปิดอยู่ต้องมี SL ที่ broker เสมอ** (server-side, ไม่ใช่ virtual)

| Failure | Detection | พฤติกรรมกับ position ที่เปิดอยู่ | พฤติกรรมกับ trade ใหม่ |
|---|---|---|---|
| Python service ตาย | heartbeat file เก่ากว่า 60s | คงไว้ (SL/TP อยู่ที่ server แล้ว) | ❌ หยุดรับ signal |
| MT5 disconnect | `TerminalInfoInteger(TERMINAL_CONNECTED)` | คงไว้ (SL อยู่ที่ server) | ❌ หยุด |
| Price data stale | tick ล่าสุด > 30s ในเวลาตลาดเปิด | ❌ **ปิด position ทันทีที่กลับมา** | ❌ หยุด |
| Spread ผิดปกติ | spread > 3× median | คงไว้ (ห้ามปิดตอน spread กว้าง) | ❌ หยุดจนกว่า normalize 5 นาที |
| Slippage สูง | slippage ไม้ล่าสุด > 2× model | — | ⚠️ risk ×0.5, ถ้าเกิด 3 ครั้งติด → หยุด |
| DB ล่ม | write exception | คงไว้ | ❌ หยุด (ห้ามเทรดโดยไม่ log ได้) |
| MCP/News ไม่ตอบ (V2) | timeout | คงไว้ | ❌ หยุด — **ถือว่า news risk = HIGH** |
| Model artifact ไม่ตรง checksum | boot check | — | ❌ ไม่ start |
| Daily loss ชน | RM counter | คงไว้ให้ SL/TP ทำงาน | ❌ หยุดถึงวันถัดไป |
| DD ชน | RM counter | **ปิดทุก position** | ❌ หยุดตาม protocol 9.3 |
| Consecutive losses ชน | RM counter | — | ❌ หยุด 24 ชม. |
| Order ส่งไม่สำเร็จ | retcode != DONE | — | retry สูงสุด 2 ครั้ง แล้วยกเลิก signal (**ห้าม retry ไม่จำกัด**) |
| Orphan position (มี position ที่ไม่มีใน DB) | reconcile ทุก 60s | 🚨 alert CRITICAL + ปิดทันที | ❌ หยุด |

**Reconciliation loop (สำคัญมาก):** ทุก 60 วินาที เทียบ position ใน MT5 กับ DB — ต่างกันเมื่อไร = CRITICAL

---

# 20. Anti-Overfitting

## 20.1 Checklist ที่ต้องผ่านก่อน deploy ทุกเวอร์ชัน

| Bias | วิธีตรวจ |
|---|---|
| **Look-ahead** | ทดสอบ: รัน pipeline บนข้อมูลที่ตัดท้ายทิ้ง 1 แท่ง — ค่า feature ของแท่งก่อนหน้าต้อง **ไม่เปลี่ยน** เลย |
| **Data leakage** | ตรวจว่าไม่มี scaler/percentile/median ที่ fit บนทั้ง dataset; ทุกอย่างต้อง rolling |
| **Feature leakage** | permutation test: สลับ label แบบสุ่ม → AUC ต้องกลับไป ~0.50 ถ้าไม่ = มี leak |
| **Label leakage** | triple-barrier ต้องใช้ M1/tick; ตรวจว่า label ไม่ใช้ข้อมูลก่อนเวลา entry |
| **News timestamp leakage** | ⚠️ อันตรายที่สุด — ดู 20.2 |
| **Over-optimization** | นับจำนวน configuration ที่ทดสอบทั้งหมด → ใช้ Deflated Sharpe Ratio; ถ้าทดสอบ 500 combination แล้วเจอ 1 อันที่ดี = noise |
| **Regime overfit** | ต้องมีผลบวกในอย่างน้อย 2 ปีที่มีลักษณะตลาดต่างกัน |
| **Survivorship** | ไม่เกี่ยวกับ single-symbol โดยตรง แต่ระวัง "เลือก broker/period ที่ผลดี" |
| **Backtest overfitting โดยรวม** | **Reality check:** สุ่มสับ label แล้ว backtest 100 รอบ → ผลจริงต้องอยู่นอก 95th percentile ของ null distribution |

## 20.2 News Timestamp Leakage — ตามที่คุณเน้น

นี่คือจุดที่ระบบ news-based ส่วนใหญ่ตายอย่างเงียบ ๆ

**กติกา:**
1. `econ_events` ต้องแยก `event_time_utc` (เวลาที่ข่าวออกตามกำหนด) กับ `actual_published_at_utc` (เวลาที่ตัวเลข actual มีให้เห็นจริง) — **ห้ามใช้ `actual` ก่อน `actual_published_at_utc`**
2. `forecast` และ `previous` ใช้ได้ก่อนเวลาข่าว (รู้ล่วงหน้าจริง) แต่ **`actual` และ `surprise` ใช้ได้เฉพาะหลัง publish**
3. Calendar revision: ผู้ให้บริการ calendar มักแก้ forecast ย้อนหลัง → ต้องเก็บ snapshot ณ `ingested_at_utc` ไม่ใช่ query ค่าปัจจุบัน
4. News sentiment ต้องใช้ `published_at_utc` ของ source ไม่ใช่เวลาที่เรา ingest — และต้องบวก latency buffer อย่างน้อย 60 วินาที
5. **Backtest ที่ใช้ข่าว ต้องรันด้วย point-in-time database เท่านั้น** ถ้าไม่มี point-in-time data → **อย่าใส่ news features ใน model** ใช้เป็น blackout filter อย่างเดียว (ซึ่งปลอดภัยและมักคุ้มกว่า)

**คำแนะนำที่หนักแน่น:** V2 ให้ใช้ news เป็น **blackout filter (rule)** ก่อน อย่าเพิ่งใส่เป็น ML feature — ประโยชน์ 80% มาจาก blackout และความเสี่ยง leakage 90% มาจากการใส่เป็น feature

---

# 8b / 21. News + MCP Architecture

## 8b.1 MCP ควรทำอะไร / ไม่ควรทำอะไร

**MCP ควรเป็น: data access layer ที่มี schema ชัดเจน และ deterministic**

✅ MCP **ควร** ทำ:
- `get_economic_events(from, to, importance, countries)` → structured JSON
- `get_news(from, to, query)` → structured items พร้อม `published_at_utc`
- `get_treasury_yields(date)`, `get_dxy(date)`
- `query_trading_journal(filters)` → ให้คุณ (มนุษย์) หรือ LLM วิเคราะห์ผลย้อนหลัง
- Cache + rate limit + normalize timezone เป็น UTC ทั้งหมด
- คืน `as_of` timestamp ในทุก response (บังคับ — เพื่อ point-in-time correctness)

❌ MCP **ไม่ควร** ทำ:
- ❌ ตัดสินใจเทรด หรือคืนค่า "BUY/SELL"
- ❌ อยู่ใน critical path ของการ execute order (ถ้า MCP ช้า = ระบบต้องไม่ค้าง)
- ❌ ให้ LLM อ่าน headline แล้วสรุปเป็น signal โดยตรง
- ❌ เขียนข้อมูลกลับเข้า trading system โดยไม่ผ่าน validation

## 8b.2 Architecture

```
┌──────────────┐
│ MCP Servers  │
│  ├─ mcp-econ-calendar   (Investing/FMP/TradingEconomics API)
│  ├─ mcp-news            (news API + sentiment)
│  ├─ mcp-market-context  (DXY, US10Y, VIX)
│  └─ mcp-journal         (read-only ต่อ trading DB)
└──────┬───────┘
       │ (async, นอก critical path)
┌──────▼────────────────────────────┐
│ news_ingestion_service.py         │
│  รันทุก 15 นาที, เขียนลง DB       │
│  แปลงเป็น structured features     │
└──────┬────────────────────────────┘
       │
┌──────▼────────────────────────────┐
│ DB (econ_events, news_items)      │  ← signal service อ่านจากตรงนี้เท่านั้น
└───────────────────────────────────┘
```

**หัวใจ: signal service ไม่เคยเรียก MCP โดยตรง** — อ่านจาก DB ที่ ingestion service เขียนไว้ ถ้าข้อมูลใน DB เก่าเกิน 60 นาที → `news_risk = UNKNOWN = HIGH` → ไม่เทรด

## 8b.3 News → Structured Features (ตามที่คุณขอ)

```
event_risk_score     = Σ over events ใน ±60 นาที ของ (importance_weight × time_decay)
time_to_next_high    = นาทีจนถึง high-impact event ถัดไป (cap 480)
time_since_last_high = นาทีนับจาก high-impact event ล่าสุด (cap 480)
in_blackout          = boolean
surprise_z           = (actual − forecast) / std(surprise ย้อนหลัง 24 ครั้ง)   ← หลัง publish เท่านั้น
usd_impact_direction = sign(surprise_z) × event_usd_sign
news_sentiment_gold  = weighted mean sentiment ของข่าวที่ relevance_gold > 0.5 ใน 4 ชม.ล่าสุด
news_volume_z        = จำนวนข่าวใน 1 ชม. เทียบ baseline
```

## 9b. News Risk Rules สำหรับ XAU/USD โดยเฉพาะ

ทองไวต่อข่าว USD มากกว่า pair ส่วนใหญ่ — spread ขยายจาก 20 points เป็น 100–500 points ได้ใน 1 วินาที

| ประเภทข่าว | ห้ามเปิดก่อน | ห้ามเปิดหลัง | เหตุผล |
|---|---|---|---|
| **FOMC decision / statement** | 60 นาที | 90 นาที | ผลกระทบยาว, มี press conference ตามมา |
| **FOMC press conference (Powell)** | 15 นาที | 60 นาที หลังจบ | ผันผวนกลางงานพูด |
| **NFP** | 30 นาที | 60 นาที | spike รุนแรงที่สุด, มักกลับทิศใน 15–30 นาที |
| **CPI (US)** | 30 นาที | 60 นาที | driver อันดับ 1 ของทองในยุคนี้ |
| **PCE** | 20 นาที | 30 นาที | ผลกระทบปานกลาง |
| **GDP (advance)** | 15 นาที | 30 นาที | |
| **Jobless Claims** | 10 นาที | 15 นาที | ผลกระทบน้อยยกเว้นตัวเลขผิดคาดมาก |
| **Fed speeches (voting members)** | 10 นาที | 20 นาที | ไม่แน่นอน |
| **Geopolitical shock** | ตรวจไม่ได้ล่วงหน้า | ใช้ volatility circuit breaker แทน | |

**คำตอบคำถามคุณ "ควรปรับตามประเภทข่าวหรือไม่": ใช่ ต้องปรับแน่นอน** — window เดียวสำหรับทุกข่าวจะทำให้คุณ (ก) หยุดเทรดมากเกินจำเป็นสำหรับข่าวเล็ก และ (ข) หยุดน้อยเกินไปสำหรับ FOMC

**เงื่อนไขกลับมาเทรดหลังข่าว (ต้องผ่านทุกข้อ):**
1. พ้น window ขั้นต่ำตามตาราง
2. spread กลับมา ≤ 1.5 × median ติดต่อกัน 3 นาที
3. ATR(14) M5 ≤ 2.0 × ค่าเฉลี่ยก่อนข่าว
4. มีแท่ง M15 ปิดสมบูรณ์อย่างน้อย 1 แท่งหลังพ้น window
→ จากนั้นให้ model ประเมินใหม่ตามปกติ (ไม่มี logic พิเศษ "เล่นข่าว")

**คำแนะนำ:** ทุนคุณเล็กมาก — **อย่าเทรดรอบข่าวเลยใน V1–V2** ประโยชน์ต่อความเสี่ยงไม่คุ้มที่ทุนขนาดนี้

---

# 21b. Security

- **Credentials:** MT5 login/password, API keys อยู่ใน `.env` (ไม่เข้า git) หรือ OS keyring; ห้าม hardcode
- **Signal integrity:** HMAC-SHA256 บน signal payload ด้วย shared secret — EA ตรวจก่อนอ่าน (กันไฟล์ปลอม/แก้)
- **Least privilege:** MCP journal server = read-only DB user
- **Investor password:** ให้ใช้ investor (read-only) password สำหรับ monitoring tools ทุกตัว
- **Model artifact:** เก็บ SHA256 ใน `model_runs`; EA/service ตรวจ checksum ก่อนโหลด
- **VPS:** disable RDP จาก public IP, ใช้ key auth, 2FA ที่ broker portal
- **DB:** encrypted backup รายวัน off-site
- **ห้ามเด็ดขาด:** อย่าให้ LLM/agent ใด ๆ มีสิทธิ์ส่งคำสั่งเทรดโดยตรง หรือแก้ค่า risk parameter ณ runtime

---

# 22. Development Roadmap

| Phase | ระยะเวลา | Deliverable |
|---|---|---|
| P0 Foundation | 1 สัปดาห์ | data pipeline, DB, broker spec audit |
| P1 V0 Rule-based + Backtester | 2–3 สัปดาห์ | event-driven backtester + V0 results |
| P2 EA + Risk Manager | 2 สัปดาห์ | EA เต็มรูปแบบ, demo engineering test |
| P3 **MVTS Go-live (V0 บน cent)** | 1 สัปดาห์ | ระบบเทรดจริงขั้นต่ำ |
| P4 V1 ML + Calibration | 3–4 สัปดาห์ | LightGBM + isotonic + walk-forward |
| P5 V1 validation gate | 2 สัปดาห์ | ตัดสิน: ML เข้าหรือตัดทิ้ง |
| P6 V2 News/MCP | 3 สัปดาห์ | blackout filter ก่อน, features ทีหลัง |
| P7 V3 Advanced | 4+ สัปดาห์ | regime-specific, M5, trailing — ทีละอย่าง |
| P8 V4 Production | 2 สัปดาห์ | monitoring, auto-retrain, alerting |

**รวมประมาณ 5–6 เดือนถ้าทำ part-time** — และควรใช้เวลานี้ ไม่ควรเร่ง

---

# 23. Directory Structure

```
xauusd-ai-trading/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── base.yaml              # symbol, timeframes, sessions
│   ├── risk.yaml              # risk params (ค่าเดียวที่ EA และ Python ใช้ร่วมกัน)
│   ├── features_v1.yaml
│   └── model_v1.yaml
├── src/
│   ├── data/       {mt5_loader.py, calendar_loader.py, news_loader.py, store.py}
│   ├── features/   {engine.py, indicators.py, sessions.py, registry.py}
│   ├── regime/     {rules.py}
│   ├── labeling/   {triple_barrier.py}
│   ├── models/     {train.py, calibrate.py, predict.py, evaluate.py}
│   ├── strategy/   {v0_rules.py, v1_ml.py, ev.py, signal_builder.py}
│   ├── backtest/   {engine.py, costs.py, slippage.py, metrics.py, walkforward.py}
│   ├── risk/       {sizing.py, limits.py}          # mirror ของ EA logic (สำหรับ backtest)
│   ├── live/       {signal_service.py, heartbeat.py, reconcile.py}
│   ├── mcp/        {econ_server.py, news_server.py, journal_server.py}
│   └── monitoring/ {daily_report.py, alerts.py, dashboard.py}
├── mql5/
│   ├── Experts/XauAiTrader.mq5
│   └── Include/XauAi/{RiskManager.mqh, SignalReader.mqh, OrderExecutor.mqh,
│                      PositionMonitor.mqh, Guards.mqh, Logger.mqh}
├── notebooks/      # research เท่านั้น — ห้ามมี production logic
├── tests/          {test_sizing.py, test_leakage.py, test_risk_limits.py,
│                    test_backtest_parity.py, test_no_martingale.py}
├── scripts/        {download_data.py, run_backtest.py, run_walkforward.py, train.py}
├── artifacts/      # models + checksums (git-lfs หรือนอก git)
└── docs/           {PROJECT_PLAN.md, decisions/ (ADR), runbook.md}
```

---

# 24. Required Python Packages

```
# core
pandas, numpy, pyarrow, scipy
# MT5
MetaTrader5
# ML
lightgbm, scikit-learn (isotonic, metrics), optuna (จำกัด trials!)
# validation
statsmodels, arch (สำหรับ vol/bootstrap)
# db
sqlalchemy, sqlite3 → psycopg2 (V4)
# config / infra
pydantic, pydantic-settings, pyyaml, structlog, tenacity
# mcp
mcp (official python sdk), httpx
# viz / monitoring
matplotlib, plotly, streamlit
# testing
pytest, pytest-cov, hypothesis
```
**หมายเหตุ:** จำกัด `optuna` ที่ **≤ 50 trials** และบันทึกจำนวน trials ทั้งหมดที่เคยรัน — ต้องใช้ในการคำนวณ Deflated Sharpe Ratio

---

# 25. MT5 Components

| Component | หน้าที่ |
|---|---|
| `XauAiTrader.mq5` | main EA, OnTick/OnTimer orchestration |
| `SignalReader.mqh` | อ่าน+validate JSON signal, ตรวจ HMAC, ตรวจ TTL, dedupe by id |
| `RiskManager.mqh` | **L0–L7 checks** (หัวข้อ 9.1), คำนวณ lot, เป็น authority สุดท้าย |
| `OrderExecutor.mqh` | ส่ง order พร้อม SL/TP, retry logic จำกัด, จัดการ retcode |
| `PositionMonitor.mqh` | เฝ้า position, timeout exit, emergency close |
| `Guards.mqh` | SpreadGuard, ConnectionGuard, StaleDataGuard, HeartbeatGuard |
| `Logger.mqh` | เขียน log + สถานะไป file/DB |
| `RiskState.mqh` | persist daily P&L, consecutive losses, DD (ต้องรอด terminal restart) |

**สำคัญ:** RiskState ต้อง persist ลง file — ไม่งั้น restart terminal = reset counter = ระบบเทรดต่อทั้งที่ควรหยุด (นี่คือ bug ที่พบบ่อยมาก)

---

# 26. MCP Components

| Server | Tools | Fail behavior |
|---|---|---|
| `mcp-econ-calendar` | `get_events(from,to,importance)`, `get_event_detail(id)` | ไม่ตอบ → news_risk=HIGH → ไม่เทรด |
| `mcp-news` | `search_news(query,from,to)`, `get_sentiment(items)` | ไม่ตอบ → ข้าม news feature (ถ้าเป็น optional) |
| `mcp-market-context` | `get_dxy()`, `get_yields()`, `get_vix()` | optional |
| `mcp-journal` | `query_trades(filters)`, `get_performance(period)`, `get_calibration_report()` | read-only, ไม่กระทบ trading |

ทุก response ต้องมี `as_of` และ `source_published_at` — ไม่มี = ทิ้ง

---

# 27. Phase-by-Phase Implementation Tasks

## 27.0 ⭐ Minimum Viable Trading System (สิ่งที่ควรสร้างก่อนทุกอย่าง)

**MVTS = V0 rule-based + Risk Manager เต็มรูปแบบ + logging เท่านั้น ไม่มี ML ไม่มี MCP ไม่มี news API**

```
1. เลือก broker + เปิด cent demo → บันทึก spec ทั้งหมด (25 บรรทัด)
2. ดาวน์โหลด XAUUSD M1/M15/H1 ย้อนหลัง 5 ปี → parquet
3. เขียน feature engine 12 features (หัวข้อ 4.2)
4. เขียน V0 rule strategy (หัวข้อ 3.3)
5. เขียน event-driven backtester + cost model
6. รัน V0 backtest → ดู PF, expectancy, trade count
7. เขียน EA: SignalReader + RiskManager + OrderExecutor + Guards
8. Python signal service (V0 logic, ไม่มี ML)
9. รัน demo 4 สัปดาห์ + fault injection test
10. ถ้าผ่าน → cent live ที่ risk 0.25%
```
**ประเมิน 3–4 สัปดาห์ part-time** และคุณจะได้ระบบที่ **เทรดจริงได้และไม่ทำให้พอร์ตตาย** ซึ่งมีค่ามากกว่า ML model ที่ยังไม่มี infrastructure รองรับ

---

## Phase P0 — Foundation
- **Objective:** มีข้อมูลที่เชื่อถือได้ และรู้ spec ของ broker จริง
- **Input:** MT5 terminal, broker account
- **Output:** parquet OHLCV M1/M15/H1 5 ปี, `broker_spec.yaml`, DB schema สร้างแล้ว
- **Technology:** MetaTrader5 python, pandas, pyarrow, SQLAlchemy
- **Acceptance:** ข้อมูลไม่มี gap เกิน 5 นาทีในเวลาตลาดเปิด; spread histogram สมเหตุสมผล; คำนวณ lot จาก spec จริงได้ถูกต้องด้วย unit test 5 เคส
- **Failure modes:** ข้อมูล M1 จาก broker ไม่ครบ (broker ส่วนใหญ่เก็บ M1 ย้อนหลังจำกัด) → ต้องหา third-party tick data; timezone ของ broker ไม่ใช่ UTC (พลาดบ่อยมาก); DST shift ทำให้ session mapping ผิด

## Phase P1 — V0 Strategy + Backtester
- **Objective:** baseline ที่วัดได้
- **Input:** P0 output
- **Output:** backtest report V0 พร้อม metrics ครบหัวข้อ 14.3
- **Technology:** pure python event loop, pytest
- **Acceptance:** backtester ผ่าน parity test (รันเดิม 2 ครั้ง ผลเหมือนกัน bit-exact); PF > 1.10 OOS; trade count > 200; ผลไม่เปลี่ยนเกิน 15% เมื่อเพิ่ม slippage 2×
- **Failure modes:** ใช้ M15 OHLC ตัดสิน TP/SL ก่อนหลัง (ทำให้ผลดีเกินจริง); spread คงที่แทนที่จะเป็น time-varying; ลืม commission/swap; look-ahead จากการ shift ผิด

## Phase P2 — EA + Risk Manager
- **Objective:** execution layer ที่ปลอดภัย
- **Input:** signal schema, risk.yaml
- **Output:** EA compiled + demo test log
- **Technology:** MQL5
- **Acceptance:** ผ่าน fault injection 10 เคส (หัวข้อ 19) ทุกเคส; RiskState รอด terminal restart; unit test ยืนยันว่า lot ไม่เป็นฟังก์ชันของผลไม้ก่อนหน้า; kill switch หยุดได้ภายใน 1 tick
- **Failure modes:** SL ไม่ถูกส่งไป server (virtual SL = อันตรายมาก); ไม่เช็ค STOPS_LEVEL → order reject; retry loop ไม่จำกัด → order ซ้ำ; counter reset ตอน restart

## Phase P3 — MVTS Go-live
- **Objective:** ระบบเทรดจริงขั้นต่ำ
- **Output:** cent account live ที่ risk 0.25%
- **Acceptance:** 4 สัปดาห์ไม่มี technical incident; ทุก trade มี record ครบ; live signal ตรงกับ backtest replay 100%
- **Failure modes:** VPS restart; broker เปลี่ยน spec เงียบ ๆ; weekend gap

## Phase P4 — V1 ML + Calibration
- **Objective:** probability filter ที่ calibrated
- **Input:** features + triple-barrier labels
- **Output:** LightGBM artifact + isotonic calibrator + calibration report
- **Technology:** lightgbm, sklearn, optuna (≤50 trials)
- **Acceptance:** AUC OOS > 0.55; ECE < 0.05; ทุก bin ที่ใช้เทรดมี n ≥ 30 และ predicted p อยู่ใน 95% CI ของ observed; permutation test ผ่าน (shuffled label → AUC ≈ 0.50)
- **Failure modes:** calibrate บน train fold (ทำให้ calibration ดูดีปลอม ๆ); percentile fit บนทั้ง dataset; optuna 1000 trials → overfit validation set; label ใช้ M15 OHLC

## Phase P5 — V1 Validation Gate 🚦
- **Objective:** ตัดสินว่า ML คุ้มค่าหรือไม่
- **Input:** V0 และ V1 บน holdout เดียวกัน
- **Output:** **การตัดสินใจที่เขียนเป็นเอกสาร** — deploy V1 หรือ ตัด ML ทิ้ง
- **Acceptance:** V1 expectancy − V0 expectancy ≥ +0.10R และ paired bootstrap p < 0.05 และ walk-forward efficiency > 0.5
- **Failure modes:** ⚠️ **แรงกดดันทางจิตใจที่จะยอมรับ V1 ทั้งที่ไม่ผ่าน** — เพราะลงแรงไปเยอะแล้ว (sunk cost). ต้องเขียนเกณฑ์ก่อนดูผล และผูกมัดกับมัน

## Phase P6 — V2 News/MCP
- **Objective:** ลด tail risk จากข่าว
- **Output:** blackout filter ทำงาน + econ_events DB point-in-time
- **Acceptance:** max DD ลดลง ≥ 20% เทียบ V1; ไม่มี trade เปิดใน blackout window ในการทดสอบ 3 เดือน; leakage test ผ่าน (backtest ที่ปิด `actual` ให้ผลใกล้เคียงกับที่เปิด — ถ้าต่างมาก = มี leakage)
- **Failure modes:** timestamp leakage (หัวข้อ 20.2); calendar API เปลี่ยน schema; timezone/DST; ข่าวเลื่อนเวลาแล้ว calendar ไม่อัปเดต

## Phase P7 — V3 Advanced
- **Objective:** เพิ่ม performance ทีละอย่าง โดยแต่ละอย่างต้องพิสูจน์ตัวเอง
- **Order ที่แนะนำ:** (1) breakeven/trailing → (2) regime-specific model → (3) M5 confirmation → (4) news ML features
- **Acceptance:** แต่ละอย่างต้องผ่านเกณฑ์แบบ P5 เทียบกับเวอร์ชันก่อนหน้า
- **Failure modes:** เพิ่มหลายอย่างพร้อมกัน → ไม่รู้ว่าอันไหนช่วย; over-optimization สะสม

## Phase P8 — V4 Production
- **Objective:** ระบบที่ดูแลตัวเองได้
- **Output:** monitoring dashboard, alerting, auto-retrain pipeline, runbook
- **Acceptance:** alert ทุกระดับทดสอบแล้ว; retrain pipeline reproducible จาก git commit; DR test (กู้จาก backup) สำเร็จ
- **Failure modes:** auto-retrain ที่ deploy model แย่โดยอัตโนมัติ (**ต้องมี human gate เสมอ**); alert fatigue

---

# 18b. Growth Plan (2,000 → 50,000 THB)

## Risk scaling ตาม milestone

| Equity (THB) | Risk/trade | Max daily loss | หมายเหตุ |
|---|---|---|---|
| 2,000 – 3,000 | 0.5% | 2% | ช่วงพิสูจน์ระบบ — ห้ามเร่ง |
| 3,000 – 5,000 | 0.75% | 3% | ต้องมี ≥ 100 live trades ที่ expectancy > 0 |
| 5,000 – 10,000 | 1.0% | 3% | ต้องมี ≥ 200 live trades |
| 10,000 – 20,000 | 1.0% | 3% | **ย้ายไป standard account ได้แล้ว** (0.01 lot ≈ 1% risk พอดี) |
| 20,000 – 50,000 | 0.75% | 2.5% | **ลด risk %** — เงินมากขึ้น ควรปกป้องมากขึ้น ไม่ใช่เสี่ยงมากขึ้น |
| 50,000+ | 0.5% | 2% | เป้าหมายเปลี่ยนจาก "โต" เป็น "รักษา" |

**หลักการที่สำคัญที่สุด:** risk % ควร **ลดลง** เมื่อ equity โต ไม่ใช่เพิ่ม — เพราะเงินที่เสียมีค่ามากขึ้นเรื่อย ๆ และ psychological pressure สูงขึ้น

## Kill Switch & Withdrawal Rules — **คำตอบ: ควรมีทั้งคู่**

**Withdrawal rule (แนะนำอย่างยิ่ง):**
```
ที่ 10,000 THB  → ถอน 2,000 THB (คืนทุนเริ่มต้น) — จากนี้เทรดด้วยกำไรล้วน
ที่ 20,000 THB  → ถอน 5,000 THB
ที่ 30,000 THB  → ถอน 7,500 THB
ที่ 50,000 THB  → ถอน 20,000 THB
```
เหตุผล: การถอนเป็นสิ่งเดียวที่ทำให้ผลลัพธ์ **เป็นจริง** — equity ในบัญชียังเป็นตัวเลข ไม่ใช่เงิน และระบบที่โต 25 เท่าก็สามารถกลับลงมา 0 ได้ในเวลาสั้นกว่ามาก

**Kill switch (บังคับ):**
```
ถาวร:  DD 25% จาก peak → ปิดระบบ, ถอนเงินที่เหลือ, retrain ใหม่ทั้งหมด
       expectancy บน 100 trades ล่าสุด < 0 → ปิดระบบ, วิเคราะห์
       ECE > 0.15 → ปิด, recalibrate
ชั่วคราว: ตามหัวข้อ 9.3
```

**⚠️ สิ่งที่ต้องยอมรับ:** เมื่อบัญชีโต 25 เท่า คุณจะเจอ DD ที่เป็นเงินจริงมากขึ้นเรื่อย ๆ — DD 15% ที่ 30,000 THB = 4,500 THB ซึ่งเจ็บกว่า 300 THB มาก. **ความล้มเหลวส่วนใหญ่เกิดที่นี่ ไม่ใช่ที่ระบบ**

---

# 19b. Important Constraint — ยืนยัน

ระบบนี้ถูกออกแบบให้:
- ✅ **NO TRADE เป็น default** — คาดว่าจะเทรด 3–8 ไม้/สัปดาห์ และมีสัปดาห์ที่ไม่เทรดเลย
- ✅ **ไม่มี daily/weekly/monthly profit target** ที่บังคับให้เทรด
- ✅ วัดผลด้วย **expectancy ต่อไม้** ไม่ใช่ P&L รายวัน
- ✅ ถ้าไม่มี edge ระบบต้องเงียบ — และการเงียบคือการทำงานที่ถูกต้อง

**Metric เดียวที่ควรดูรายวัน:** "ระบบทำตามกฎครบทุกข้อหรือไม่" — ไม่ใช่ P&L

---

# สรุปสิ่งที่ต้องตัดสินใจก่อนเริ่ม Phase P0

1. **บัญชี cent หรือเพิ่มทุน?** — ต้องตอบก่อน ไม่งั้นทั้งแผนใช้ไม่ได้ (หัวข้อ 0.1–0.2)
2. **ยอมรับกรอบเวลา 2–3.5 ปี สำหรับเป้า 50,000 หรือไม่?** (หัวข้อ 0.3)
3. **ยอมรับหรือไม่ว่า P5 อาจสรุปว่า "ไม่ต้องมี AI"?** — ถ้ายอมรับไม่ได้ อย่าสร้าง gate นี้ตั้งแต่แรก (แต่ก็จะไม่รู้ว่า AI ช่วยจริงไหม)
4. **Broker ไหน?** — ต้องมี cent account, spread ทองต่ำ, ยอมให้รัน EA, execution ยอมรับได้
5. **VPS หรือเครื่องที่บ้าน?** — ระบบต้องรัน 24/5
