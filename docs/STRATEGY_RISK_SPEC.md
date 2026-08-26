# Strategy & Risk Specification

อัปเดตล่าสุด: 2026-08-25 อธิบายสิ่งที่ระบบรันจริงบน live ไม่ใช่แผนเดิมยุค
XAU/MT5 (ดู PROJECT_PLAN.md สำหรับยุคนั้น; [HANDOFF.md](HANDOFF.md) สำหรับ
บริบทการปรับทิศทางมา crypto) อ่าน [FINDINGS.md](FINDINGS.md) ก่อนเปลี่ยน
พารามิเตอร์ใดๆ ด้านล่าง — ค่าส่วนใหญ่ถูกล็อกไว้เพราะ config ก่อนหน้าเคยลอง
แล้วถูกปฏิเสธ

## 1. ขอบเขต

- **Symbol**: ETH/USDT:USDT เป็นตัวหลัก (risk 0.5%) + **XRP/USDT:USDT** เป็น
  tier-2 candidate ที่กำลัง paper-trade (risk 0.25%) — ดู
  [FINDINGS.md](FINDINGS.md) ส่วน "2nd-symbol search" BTC/SOL/BNB/DOGE/ADA/
  LINK/LTC/AVAX ถูก backtest แล้วปฏิเสธในรอบต่างๆ (ไม่มี edge หรือเปราะเกินไป)
- **Timeframe**: ตัดสินใจที่ M15, ใช้ H1 ยืนยันแนวโน้ม สร้าง signal ครั้งเดียว
  ต่อการปิดแท่ง M15 (`scripts/run_signal_cycle.py`, ถูกเรียกโดย
  `signal-cycle.timer`) ไม่มีการตัดสินใจกลางแท่ง
- **Config บน live ถูกล็อกไว้**: `ADX_threshold=35`, `SL=2.5x ATR`, `TP=2x SL`
  (ระบุต่อ symbol ใน `SYMBOLS` list ของ
  [scripts/run_signal_cycle.py](../scripts/run_signal_cycle.py))
  ห้าม tune ใหม่โดยไม่มี holdout ใหม่ที่แยกจากเดิมจริงๆ

## 2. การจำแนก Regime

[src/regime/rules.py](../src/regime/rules.py) — ใช้กฎตายตัว มี 2 class บน live

| Regime | เงื่อนไข |
|---|---|
| `TREND` | H1 ADX(14) > `adx_threshold` **และ** `\|EMA50-EMA200\|/ATR_H1` > 0.5 |
| `RANGE` | นอกเหนือจากนั้น |

- ค่า default: `ADX_TREND_THRESHOLD = 22.0`, `TREND_STRENGTH_THRESHOLD = 0.5`
  Config ที่ล็อกไว้บน live override ADX เป็น **35** (เข้มกว่าค่า default ของ
  module) — ดู `LOCKED_CONFIG` ด้านบน
- `NEWS_BLACKOUT` เป็น hook ที่นิยามไว้ใน signature ของกลยุทธ์ แต่ยังเป็น
  no-op สำหรับ crypto V1 — ยังไม่มี blacklist ปฏิทินเศรษฐกิจ (วางแผนไว้สำหรับ
  phase ถัดไป)
- `vol_multiplier()` เป็น risk multiplier แบบต่อเนื่อง 0.40–1.0 แยกต่างหาก
  คำนวณจาก ATR percentile (ไม่ใช่ class แบบ "HIGH_VOLATILITY" ที่กระโดดชัด
  เพื่อเลี่ยง cliff behavior) ปัจจุบันยังไม่ต่อเข้ากับ risk multiplier chain
  บน live — ตัว multiplier บน live มาจาก win-rate guard เท่านั้น (§4)

## 3. กลยุทธ์การเข้าไม้

ทั้ง 3 กลยุทธ์ใช้ output schema เดียวกัน — หนึ่งแถวต่อแท่ง M15 พร้อม
`action ∈ {LONG, SHORT, NO_TRADE}` และ `sl_price`/`tp_price` เมื่อมีการเข้าไม้
จึงสลับใช้กันได้ใน `scripts/compare_v0_strategies.py` มีแค่ **V0
EMA-pullback** ที่ใช้บน live อีก 2 ตัวเก็บไว้อ้างอิงเท่านั้น

### 3.1 V0 EMA-pullback (LIVE) — [src/strategy/v0_rules.py](../src/strategy/v0_rules.py)

Trend-following แบบ pullback entry ทำงานเฉพาะ regime `TREND`

- **Long setup**: regime `TREND`, แนวโน้ม H1 เป็นขาขึ้น (`f03_h1_trend_atr > 0`),
  ราคาย่อกลับมาที่ EMA20 แล้วปิดกลับขึ้นเหนือมัน (`dist_ema20` ข้ามจาก ≤0
  เป็น >0 ในแท่งนี้)
- **Short setup**: กลับด้าน — H1 เป็นขาลง, `dist_ema20` ข้ามจาก ≥0 เป็น <0
- **ตัวกรองคุณภาพ** (ใช้หลัง setup พื้นฐาน): ATR percentile ต้องอยู่ใน
  `[atr_pct_min, atr_pct_max]` (ค่า default คือ no-op, `[0, 1]`), และอัตราส่วน
  body ของแท่งเทียนต้อง ≥ `min_body_ratio` (ค่า default คือ no-op, `0`) —
  หลีกเลี่ยงความผันผวนที่ตายด้าน/สับสน และแท่งเทียนที่ไม่เด็ดขาด
- **Stop**: `sl_distance = clip(ATR * sl_atr_mult, lower=ATR*0.8, upper=ATR*max(3.0, sl_atr_mult*1.2))`
  ค่า default ของ module คือ `SL_ATR_MULT=1.5`, `TP_R_MULT=2.0`; config ที่
  ล็อกบน live ใช้ `SL=2.5x ATR` แทน (`TP_R_MULT` คงค่า default ของ module
  คือ TP = 2R)
- แถวที่ feature ยัง warm-up ไม่เสร็จ (`f08_atr_percentile` เป็น NaN) จะถูก
  บังคับเป็น `NO_TRADE`

### 3.2 Breakout (ถูกปฏิเสธ, เก็บไว้อ้างอิง) — [src/strategy/breakout.py](../src/strategy/breakout.py)

Breakout ของ Donchian(20) channel ต้องการ H1 ADX > 20 ตั้งใจตัด regime
filter ออก (ตรรกะ breakout มีการยืนยันแนวโน้มในตัวอยู่แล้ว) คำนวณ channel
จากแท่งก่อนหน้าแท่ง signal อย่างเคร่งครัด (`shift(1)`) เพื่อไม่ให้แท่งที่
breakout leak เข้าไปเป็น trigger level ของตัวเอง

### 3.3 Mean-reversion (ถูกปฏิเสธ, เก็บไว้อ้างอิง) — [src/strategy/mean_reversion.py](../src/strategy/mean_reversion.py)

ฟาดสวน `dist_ema20/ATR` ที่เกิน ±`entry_z` (default 2.0), ทำงานเฉพาะ regime
`RANGE` — เป็นสมมติฐานตรงข้ามกับอีก 2 ตัว: เดิมพันว่าราคาจะดีดกลับเข้าหา
ค่าเฉลี่ยแทนที่จะไปต่อ `TP_R_MULT` เล็กกว่า (1.5 เทียบกับ 2.0) เพราะเป้าหมาย
คือค่าเฉลี่ย ไม่ใช่การวิ่งยาว

## 4. Risk Sizing และ Guard

### 4.1 Position Sizing — [src/risk/sizing.py](../src/risk/sizing.py)

`compute_position_size(equity, risk_pct, entry_price, sl_price, spec)`:

```
risk_amount = equity * risk_pct
qty = floor((risk_amount / |entry_price - sl_price|) / stepSize) * stepSize
```

- ปัดเศษ**ลง**เป็น `stepSize` เสมอ — ถ้าปัดขึ้นจะทำให้ risk เกินที่ตั้งใจไว้
  โดยไม่รู้ตัว
- โยน `PositionRejected` (ผู้เรียกห้ามปัดขึ้นเพื่อชดเชย) ถ้า `qty < amount_min`
  หรือ `notional < min_notional` — บัญชีเล็กเกินไปสำหรับ `risk_pct`/ระยะ SL นี้
  ที่ราคาปัจจุบัน
- `risk_pct` ถูกตรวจสอบให้อยู่ใน `(0, 0.05]` เป็นขอบเขตความสมเหตุสมผล
- ไม่ต้องแปลง lot/tick-value (ต่างจากแผน MT5 เดิม) — การคำนวณขนาดของ crypto
  เป็นการหารตรงๆ ระหว่าง risk-amount ÷ ระยะ SL

### 4.2 Base Risk และ Win-rate Guard

- **Base risk**: กำหนดต่อ symbol ผ่าน `base_risk_pct` ใน `SYMBOLS` list ของ
  [scripts/run_signal_cycle.py](../scripts/run_signal_cycle.py) — ETH ที่
  **0.5%**, XRP ที่ **0.25%** ค่า ETH ถูกลดจากแผนเดิม 1–2% หลัง walk-forward
  testing แสดงว่า edge ของ ETH เป็นของจริงแต่**ไม่เสถียร**: 8/12 quarterly
  fold เป็นบวก มีแค่ 2/12 ที่ significant ทางสถิติจริงๆ และ 2023 H2 ติดลบ
  อย่าง significant (regime whipsaw/vol สูงที่ train/holdout split เดียว
  มองไม่เห็น)
- **Rolling win-rate guard** — `rolling_winrate_risk_multiplier()` ใน
  [src/live/guards.py](../src/live/guards.py): ดู net R-multiple ของ 20
  เทรดที่ปิดล่าสุด (`WINRATE_WINDOW=20`) **แยกตาม symbol** ผ่าน
  `recent_closed_r_multiples()` — ถ้า win rate ในช่วงนั้นต่ำกว่า
  `WINRATE_THRESHOLD=0.30` risk จะถูกลดครึ่งหนึ่ง (`reduced_multiplier=0.5`)
  จนกว่าจะฟื้น คืนค่า 1.0 (ไม่ลด) ถ้ามีเทรดน้อยกว่า 20 ไม้ — noise เยอะเกินไป
  ที่จะตัดสินใจจาก sample เล็กขนาดนั้น จำลองมาจาก failure mode ของ 2023 H2
  โดยตรง (win rate ~27%, ทั้ง LONG และ SHORT ขาดทุนพร้อมกัน) — trigger เร็ว
  กว่า threshold drawdown/daily-loss
- Risk จริงต่อเทรดบน live: `base_risk_pct * risk_multiplier` เช่น ETH ปกติ
  0.5%, เหลือ 0.25% เมื่อ guard ทำงาน

### 4.3 Guard ก่อนเข้าไม้ — [src/live/guards.py](../src/live/guards.py)

ฟังก์ชัน pure ไม่มีการเรียก exchange, ทุกตัว fail closed:

| Guard | บล็อกการเทรดเมื่อ | Threshold เริ่มต้น |
|---|---|---|
| `spread_guard` | spread ปัจจุบัน > `max_ratio` × spread มัธยฐาน | 3.0x |
| `stale_data_guard` | tick ล่าสุดเก่ากว่า `max_age_sec` | 30 วิ |
| `heartbeat_guard` | heartbeat ของ signal-cycle เก่ากว่า `max_age_sec` | 60 วิ |
| `rolling_winrate_risk_multiplier` | ดู §4.2 | win rate < 30% ใน 20 เทรดล่าสุด (ต่อ symbol) |

`retry_with_limit()` จำกัดการ retry การวางไม้ไว้ที่ 2 ครั้ง (โยน
`RetryLimitExceeded` หลังจากนั้น) — ไม่ retry ไม่จำกัดเด็ดขาด เพื่อไม่ให้
error ชั่วคราวกลายเป็นไม้ซ้ำ/วิ่งเถื่อน

### 4.4 EV Gate

`src/live/ev_estimate.py` กรองการเข้าไม้ด้วย **base rate จาก backtest
ประวัติศาสตร์** ไม่ใช่การทำนายจาก model เคยลอง LightGBM มาแล้ว
(`src/models/`) และถูกปฏิเสธที่ gate P5 — holdout AUC ~0.497 แยกไม่ออกจาก
noise `estimate_ev` ถูก label ว่าไม่ใช่ ML อย่างชัดเจนทุกที่ที่แสดงผล
(comment ในโค้ด, dashboard) เพื่อกันไม่ให้กลับมาใช้เป็น "AI probability"
display อีก

### 4.5 ความปลอดภัยของวงจรชีวิต Position

- `src/live/reconcile.py` — ตรวจจับ position กำพร้า; signal cycle ปฏิเสธ
  การเปิดไม้ใหม่ถ้ามี position ที่ไม่มี SL คู่กันอยู่
- `src/live/position_timeout.py` — บังคับปิดหลัง 12 ชม. และตรวจจับ SL/TP ที่
  ยิงเองบน exchange (ccxt ไม่เห็น fill ของ algo-order แบบ native โดยตรง ดู
  `order_executor.fetch_open_algo_orders`)

## 5. ข้อจำกัดที่รู้อยู่แล้ว (อย่าคิดว่าแก้แล้ว)

- Edge เป็นของจริงทางสถิติแต่ไม่เสถียรข้าม regime (§4.2) — ห้ามขึ้น
  `base_risk_pct` โดยไม่มี holdout ใหม่ที่แยกจากเดิมมายืนยันความเสถียร
- ETH ยังไม่มีเทรดเกิดขึ้นบน live/paper นับจากที่เขียนไฟล์นี้ — ETH อยู่ใน
  regime `RANGE` ต่อเนื่องตั้งแต่ระบบอัตโนมัติเริ่มทำงาน — ไม่ใช่หลักฐานของ
  bug ในตัวมันเอง (ดูส่วน known-gaps ใน [HANDOFF.md](HANDOFF.md) สำหรับการ
  วิเคราะห์ความน่าจะเป็น)
- กิจกรรม live ทั้งหมดตอนนี้อยู่บน demo/testnet trading — spread/slippage
  จริงยังเป็นสมมติฐานจาก cost model ของ backtest ยังไม่ได้วัดกับความลึกของ
  orderbook จริงบน mainnet
- `vol_multiplier()` (§2) มีอยู่แต่ยังไม่ได้ต่อเข้ากับ risk-multiplier chain
  บน live
- Slippage ใน `src/backtest/costs.py` แก้เป็นสัดส่วนราคาแล้ว (`SLIPPAGE_BPS`,
  เดิมเป็น USD คงที่ที่ทำให้ coin ราคาต่ำได้ค่าเพี้ยน) ETH edge ถูก
  re-confirm แล้วว่าไม่เปลี่ยน — ดู FINDINGS.md
