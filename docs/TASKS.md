# Task Breakdown by Phase

อ้างอิงจาก [PROJECT_PLAN.md](../PROJECT_PLAN.md) หัวข้อ 22 (Development Roadmap) และ 27 (Phase-by-Phase Implementation Tasks)

---

## PIVOT (2026-08-24): XAU/MT5 → Binance Futures (crypto)

มี Binance account แล้ว — เปลี่ยน execution/data layer เป็น Binance Futures ดูรายละเอียดเหตุผลใน [PROJECT_PLAN.md](../PROJECT_PLAN.md) หัว "PIVOT NOTICE" Phase P1 เป็นต้นไปแนวคิดเดิม (feature engineering, risk management, calibration, backtesting) ยังใช้ได้เกือบทั้งหมด — จะปรับรายละเอียด execution ทีละ phase ตอนถึงจริง

## สิ่งที่ต้องตัดสินใจก่อนเริ่ม Phase P0 (ปรับสำหรับ Binance)

- [x] ~~บัญชี cent หรือเพิ่มทุน~~ → ไม่ต้อง ใช้ fractional position size ของ Binance Futures แทน
- [ ] ยอมรับกรอบเวลา สำหรับเป้า 2,000 → 50,000 THB หรือไม่? (คำนวณ risk-of-ruin เดิมยังใช้ได้ ดูหัวข้อ 0.3 — เพดาน risk แนะนำ 2%/ไม้)
- [ ] ยอมรับหรือไม่ว่า Phase P5 อาจสรุปว่า "ไม่ต้องมี AI"?
- [ ] เลือกคู่เหรียญที่จะเทรด (แนะนำเริ่ม BTC/USDT หรือ ETH/USDT — สภาพคล่องสูงสุด, funding data ยาว, ไม่ผันผวนสุดโต่งเท่า alt เล็ก)
- [ ] VPS หรือเครื่องที่บ้านที่รันได้ 24/7 (crypto ไม่มี weekend — ต่างจาก MT5 เดิม)
- [ ] สร้าง API key แยก 2 ชุด: **testnet** (ทดสอบ) กับ **mainnet ชุดที่มีแค่สิทธิ์ trade ห้าม withdraw เด็ดขาด** (ดู §21b Security เดิม + ปรับเรื่อง API permission)

---

## Phase P0 — Foundation (Binance) (~1 สัปดาห์)

**Objective:** มีข้อมูลที่เชื่อถือได้ และรู้ spec ของ symbol จริงบน Binance Futures

- [ ] สมัคร/ยืนยัน Binance Futures mainnet account (มีแล้ว) + สร้าง **Testnet** account แยก (testnet.binancefuture.com) — API key คนละชุดจาก mainnet
- [ ] ตั้งค่า mainnet API key: **permission = trade only, withdraw = disabled** (บังคับ, กันขโมย key ถอนเงิน)
- [ ] ติดตั้ง `ccxt` เป็น abstraction layer (exchange-agnostic ตั้งแต่แรก)
- [ ] บันทึก symbol spec ลง `exchange_spec.yaml` (แทน `broker_spec.yaml`): `contractSize`, `tickSize`, `stepSize`, `minNotional`, `pricePrecision`, `quantityPrecision` — ดึงจาก `exchange.load_markets()`
- [ ] เขียน `binance_loader.py` ดึง OHLCV (klines) M1/M15/H1 ย้อนหลังให้ได้มากที่สุด (BTC/ETH มีข้อมูลยาวกว่า alt) → parquet
- [ ] เขียน `funding_rate_loader.py` ดึง funding rate history (ต้องใช้เป็น cost input ใน backtest — Binance มี endpoint แยก)
- [ ] เก็บ mark price แยกจาก last price (liquidation คำนวณจาก mark price)
- [ ] ตรวจ data gap (crypto 24/7 — ไม่ควรมี gap เลยนอกจาก exchange maintenance)
- [ ] สร้าง DB schema (หัวข้อ 13 เดิม ปรับ: เพิ่มคอลัมน์ funding_rate ใน bars/trades, เปลี่ยน `symbol` เป็น crypto pair format)
- [ ] เขียน unit test คำนวณ position size จาก `stepSize`/`minNotional` จริง (ไม่ใช่ lot/tick_value แบบ MT5 — สูตรง่ายกว่า ไม่มีปัญหา min lot)
- [ ] เขียน `test_no_martingale.py` (regression test — ทำตั้งแต่ P0 เลย เพราะไม่มี EA มาคุ้มกันให้)

**Acceptance:** ข้อมูล klines ไม่มี gap นอกช่วง maintenance; funding rate history ครบ; unit test position sizing ผ่านครบ 5 เคส (รวมเคส `minNotional` ที่ order เล็กเกินไปต้อง reject ไม่ใช่ปัดขึ้น)

**Failure modes ที่ต้องระวัง:** ใช้ last price แทน mark price ผิดจุด; ลืม funding cost ใน backtest (ทำให้ EV สูงเกินจริง); mainnet API key ตั้ง withdraw permission เปิดอยู่โดยไม่รู้ตัว; rate limit โดน weight-based ไม่ใช่ request-count (Binance เฉพาะ)

---

## Phase P1 — V0 Strategy + Backtester (~2–3 สัปดาห์)

**Objective:** baseline ที่วัดได้

- [ ] เขียน feature engine 12 features (หัวข้อ 4.2) พร้อม `shift(1)` ทุกตัว
- [ ] เขียน regime classifier rule-based (TREND/RANGE + NEWS_BLACKOUT hardcoded list)
- [ ] เขียน V0 rule strategy (EMA pullback, หัวข้อ 3.3)
- [ ] เขียน triple-barrier labeling ด้วย M1/tick data (ไม่ใช้ M15 OHLC)
- [ ] เขียน event-driven backtester (ทีละแท่ง, มองเห็นแค่ข้อมูลถึงปัจจุบัน)
- [ ] เขียน cost model: spread time-varying, commission, swap, slippage model
- [ ] รัน parity test (รันซ้ำ ผลต้อง bit-exact เดิม)
- [ ] รัน V0 backtest เต็ม → PF, expectancy, trade count, breakdown ตามหัวข้อ 14.3
- [ ] ทดสอบ sensitivity slippage 1×/2×/3×
- [ ] เช็คเกณฑ์ผ่าน: PF > 1.10, trade count > 200, cost < 40% gross profit

**Acceptance:** backtester ผ่าน parity test bit-exact; PF > 1.10 OOS; trade count > 200; ผลไม่เปลี่ยนเกิน 15% เมื่อเพิ่ม slippage 2×

**Failure modes:** ใช้ M15 OHLC ตัดสิน TP/SL ก่อนหลัง; spread คงที่แทน time-varying; ลืม commission/swap; look-ahead จาก shift ผิด

---

## Phase P2 — EA + Risk Manager (~2 สัปดาห์)

**Objective:** execution layer ที่ปลอดภัย

- [ ] เขียน `SignalReader.mqh` (parse JSON, ตรวจ HMAC, TTL, dedupe by id)
- [ ] เขียน `RiskManager.mqh` ครบ L0–L7 (หัวข้อ 9.1) + position sizing (หัวข้อ 10.1)
- [ ] เขียน `OrderExecutor.mqh` (retry ≤2 ครั้ง, จัดการ retcode)
- [ ] เขียน `PositionMonitor.mqh`, `Guards.mqh` (Spread/Connection/StaleData/Heartbeat)
- [ ] เขียน `RiskState.mqh` — persist daily P&L / consecutive loss / DD ผ่าน terminal restart
- [ ] เขียน `Logger.mqh` เขียน log ก่อน execute เสมอ
- [ ] Unit test: lot size ต้องไม่เป็นฟังก์ชันของผล trade ก่อนหน้า (anti-martingale regression test)
- [ ] ทดสอบ fault injection 10 เคส (หัวข้อ 19): ตัดเน็ต, kill python, spread พุ่ง, orphan position ฯลฯ
- [ ] ทดสอบ kill switch หยุดได้ภายใน 1 tick

**Acceptance:** ผ่าน fault injection ทุกเคส; RiskState รอด terminal restart; unit test ยืนยัน lot ไม่เป็นฟังก์ชันของผลไม้ก่อนหน้า; kill switch หยุดได้ภายใน 1 tick

**Failure modes:** SL เป็น virtual SL ไม่ถูกส่งไป server; ไม่เช็ค STOPS_LEVEL → order reject; retry loop ไม่จำกัด; counter reset ตอน restart

---

## Phase P3 — MVTS Go-live (~1 สัปดาห์)

**Objective:** ระบบเทรดจริงขั้นต่ำ

- [ ] เขียน Python signal service (logic V0 ล้วน ไม่มี ML) รันทุก bar close M15
- [ ] เขียน heartbeat.py
- [ ] Deploy บน VPS/เครื่องที่รันตลอด
- [ ] รัน demo 4 สัปดาห์ + ตรวจ live signal ตรงกับ backtest replay 100%
- [ ] เมื่อผ่าน → ไป cent live risk 0.25%

**Acceptance:** 4 สัปดาห์ไม่มี technical incident; ทุก trade มี record ครบ; live signal ตรงกับ backtest replay 100%

**Failure modes:** VPS restart; broker เปลี่ยน spec เงียบๆ; weekend gap

---

## Phase P4 — V1 ML + Calibration (~3–4 สัปดาห์)

**Objective:** probability filter ที่ calibrated

- [ ] เตรียม train/calibration/validation/test split ตามหัวข้อ 14.2 (ห้ามแตะ holdout จนกว่าจะพร้อม)
- [ ] Train LightGBM ตามสเปกหัวข้อ 6.3 (constraints ป้องกัน overfit)
- [ ] Train Logistic Regression baseline เทียบ
- [ ] Fit Isotonic calibrator บน fold แยกจาก train
- [ ] คำนวณ AUC, Brier, ECE, MCE, reliability curve, calibration bin test (หัวข้อ 7.2–7.3)
- [ ] เขียน EV calculator + decision rule (หัวข้อ 8.2)
- [ ] Optuna tuning ≤50 trials, log จำนวน trials ทั้งหมด
- [ ] Permutation test (shuffle label → AUC ≈ 0.50)
- [ ] Walk-forward กับ purging/embargo (หัวข้อ 15)

**Acceptance:** AUC OOS > 0.55; ECE < 0.05; ทุก bin ที่ใช้เทรดมี n ≥ 30 และ predicted p อยู่ใน 95% CI ของ observed; permutation test ผ่าน

**Failure modes:** calibrate บน train fold; percentile fit บนทั้ง dataset; optuna trials มากเกินไป → overfit validation set; label ใช้ M15 OHLC

---

## Phase P5 — V1 Validation Gate 🚦 (~2 สัปดาห์)

**Objective:** ตัดสินว่า ML คุ้มค่าหรือไม่

- [ ] เขียนเกณฑ์ตัดสินใจไว้ **ก่อน** ดูผล (ป้องกัน sunk cost bias)
- [ ] เปรียบเทียบ V0 vs V1 บน trade universe เดียวกัน
- [ ] Paired bootstrap test (10,000 resamples), เช็ค p < 0.05
- [ ] เช็ค walk-forward efficiency > 0.5, consistency ≥ 60% folds
- [ ] สรุปเอกสารการตัดสินใจ: ใช้ V1 ต่อ หรือ ตัด ML ทิ้งกลับไปใช้ V0

**Acceptance:** V1 expectancy − V0 expectancy ≥ +0.10R และ paired bootstrap p < 0.05 และ walk-forward efficiency > 0.5

**Failure modes:** แรงกดดันทางจิตใจที่จะยอมรับ V1 ทั้งที่ไม่ผ่าน (sunk cost) — ต้องเขียนเกณฑ์ก่อนดูผล และผูกมัดกับมัน

---

## Phase P6 — V2 News/MCP (~3 สัปดาห์)

**Objective:** ลด tail risk จากข่าว

- [ ] สร้าง `econ_events`/`news_items` แบบ point-in-time (แยก `event_time_utc` vs `actual_published_at_utc`)
- [ ] เขียน MCP servers (econ-calendar, news, market-context, journal) — อยู่นอก critical path เท่านั้น
- [ ] เขียน `news_ingestion_service.py` รันทุก 15 นาที เขียนลง DB
- [ ] Implement blackout filter ตามตาราง news risk (หัวข้อ 9b) — ทำก่อน ML features
- [ ] Leakage test: backtest ปิด/เปิด `actual` เทียบกัน ผลต้องใกล้เคียงกัน
- [ ] เช็คเกณฑ์ผ่าน: max DD ลด ≥ 20% เทียบ V1

**Acceptance:** max DD ลดลง ≥ 20% เทียบ V1; ไม่มี trade เปิดใน blackout window ในการทดสอบ 3 เดือน; leakage test ผ่าน

**Failure modes:** timestamp leakage (หัวข้อ 20.2); calendar API เปลี่ยน schema; timezone/DST; ข่าวเลื่อนเวลาแล้ว calendar ไม่อัปเดต

---

## Phase P7 — V3 Advanced (4+ สัปดาห์, ทำทีละอย่าง)

**Objective:** เพิ่ม performance ทีละอย่าง โดยแต่ละอย่างต้องพิสูจน์ตัวเอง

- [ ] (1) Breakeven/trailing stop → ทดสอบกับ walk-forward เทียบ V1 baseline
- [ ] (2) Regime-specific model (ต้องมี ≥ 300 trades/regime)
- [ ] (3) M5 confirmation → ต้องพิสูจน์ `E[R|with M5] − E[R|without] > 0.05R` OOS
- [ ] (4) News เป็น ML feature (point-in-time data เท่านั้น)
- [ ] แต่ละอย่างผ่านเกณฑ์แบบ P5 ก่อนรับเข้า ห้ามเพิ่มพร้อมกันหลายอย่าง

**Acceptance:** แต่ละอย่างต้องผ่านเกณฑ์แบบ P5 เทียบกับเวอร์ชันก่อนหน้า

**Failure modes:** เพิ่มหลายอย่างพร้อมกัน → ไม่รู้ว่าอันไหนช่วย; over-optimization สะสม

---

## Phase P8 — V4 Production (~2 สัปดาห์)

**Objective:** ระบบที่ดูแลตัวเองได้

- [ ] Monitoring dashboard (Grafana/Streamlit) realtime + daily/weekly/monthly report
- [ ] Alerting ครบ 4 ระดับ (INFO/WARN/ERROR/CRITICAL) + ทดสอบส่งจริง
- [ ] Auto-retrain pipeline (reproducible จาก git commit) — ต้องมี human gate ก่อน deploy เสมอ
- [ ] Reconciliation loop ทุก 60 วิ (เทียบ MT5 position กับ DB)
- [ ] DR test: กู้จาก backup สำเร็จ
- [ ] Go-live checklist เต็ม (หัวข้อ 17) ก่อนขยับ risk stage

**Acceptance:** alert ทุกระดับทดสอบแล้ว; retrain pipeline reproducible จาก git commit; DR test สำเร็จ

**Failure modes:** auto-retrain deploy model แย่โดยอัตโนมัติ (ต้องมี human gate เสมอ); alert fatigue

---

**รวมประมาณ 5–6 เดือนถ้าทำ part-time** — และควรใช้เวลานี้ ไม่ควรเร่ง (หัวข้อ 22)
