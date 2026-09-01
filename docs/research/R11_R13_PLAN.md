# R11–R13 — Research Plan (จากคลิป YouTube rtABo4mPxdM "โค้ชปอ")

เขียน: 2026-08-27 · track: GOLD (XAU/USD spot) · อ่าน `GOLD_HANDOFF.md` + `XAU_YOUTUBE_PLAYLIST.md` ก่อน

> ที่มา: กลั่นจากคลิปสอนเทรดทอง (discretionary price-action, ขายคอร์ส) → ตัดดุลยพินิจออก
> เขียนเป็นกฎ deterministic + ผูก mechanism. **คลิป = แหล่งสมมติฐาน ไม่ใช่หลักฐาน**
> verdict มาจาก backtest design ล่าง ไม่ใช่คำพูดในคลิป
>
> ทุก plan เสียบ `run_gold_backtest(signal_fn, spec, start, end)` — signal_fn คืน df คอลัมน์
> `time_utc, close(=entry), action(LONG/SHORT/NO_TRADE), sl_price, tp_price, sl_distance(>0)`
> Data ที่ยืนยันว่ามี: `XAUUSD_{1m,15m,1h}.parquet` (spot 20y). **ไม่ใช้ DXY/news** ทั้งสามตัว

---

## ลำดับความสำคัญ (ทำตามนี้)
1. **R11 (wick-fill)** — mechanism อิสระจากของเดิมมากสุด, ทำก่อน
2. **R13 (multi-TF filter)** — meta-filter, ทับ R10; ทำเป็น infra ใช้ครอบทุก R ได้
3. **R12 (momentum-candle breakout)** — R1 + range filter; ค่าหลักคือ "confirm falsification" ของ ORB

---

# R11 — Wick-Fill / Imbalance Revert

## 1. Mechanism (ใครจ่าย)
เมื่อแท่ง m15/h1 พุ่งเร็วแล้วทิ้ง **ไส้ยาวผิดปกติ** (long wick, body เล็ก) แปลว่าราคาแวะไปแตะ
ระดับหนึ่งแล้วถูกตีกลับทันที = มี **resting liquidity** ฝั่งตรงข้ามที่ absorb การพุ่งนั้น และ
**คนที่ไล่ราคาช่วงพุ่ง (momentum chasers) ถูก trap** ที่ปลายไส้ ต้องปิดขาดทุน → ราคามีแนวโน้ม
ย้อนกลับไป "เติมไส้" (คลิปเรียก week field/wick fill). ผู้จ่าย = chasers ที่เข้าปลายไส้ + stops ของพวกเขา

ระวัง (falsification honesty): "ราคาเติมไส้" อาจเป็นแค่ **mean-reversion ทั่วไป** ที่จะเกิดอยู่แล้ว
ไม่ว่าจะมีไส้หรือไม่ → ต้องมี **baseline เทียบ** (ดู §6) ไม่งั้นเราหลอกตัวเอง

## 2. Rule spec (if/then) — LONG (mirror สำหรับ SHORT)
ทำบน m15. ต่อแท่งปิด i:
```
atr        = ATR(atr_len) ที่แท่ง i
lower_wick = min(open_i, close_i) - low_i
body       = |close_i - open_i|
trigger LONG (fade ไส้ล่าง — คาดว่าราคาถูกดันกลับขึ้น):
  IF lower_wick >= k_wick * atr
  AND body <= body_frac * lower_wick        (แท่งลังเล/rejection ไม่ใช่แท่ง trend)
  THEN action=LONG ที่ close ของแท่ง i (close = entry price)
  sl_price    = low_i - buf * atr           (ใต้ปลายไส้เล็กน้อย)
  sl_distance = close_i - sl_price  (>0)
  tp_price    = จุด "เติมไส้" = midpoint หรือ open ของแท่ง i
                → tp_price = open_i  (ราค่าที่ไส้เริ่มถูกทิ้ง) ; ถ้า open_i ใกล้ close ใช้ high_i แทน
  ทางเลือก TP แบบ R-based: tp_price = close_i + tp_r_mult * sl_distance (ให้ grid ตัดสิน)
one-trade rule: ไม่ overlap — ถ้ามีไม้ค้าง (ยังไม่ชน barrier) ห้าม arm ใหม่ (harness/triple-barrier จัดการ)
session filter: เข้าเฉพาะ high_liquidity (London/Overlap/NY) — ไส้ช่วง Asia = noise เบาบาง
```
SHORT = ไส้บน (upper_wick) mirror ทุกอย่าง

## 3. Data
- `XAUUSD_15m.parquet` (signal) + `1m` (triple-barrier labeling). ATR คำนวณจาก m15 ใน `build_features`
  ถ้ามี ถ้าไม่มีให้ signal_fn คำนวณเอง (rolling True Range). ไม่ต้อง h1/DXY

## 4. Parameter grid (เล็ก, pre-registered — justify จาก mechanism)
- `k_wick` ∈ {1.0, 1.5, 2.0} — "ยาวผิดปกติ" แค่ไหนถึงนับ (แกนหลักของ mechanism)
- `body_frac` ∈ {0.3, 0.5} — คุมว่าเป็น rejection จริง ไม่ใช่ momentum candle
- `tp` mode ∈ {wick_fill(open_i), 1.0R, 1.5R} — เติมไส้ vs R-based
- `direction` ∈ {both, long} — เช็ค long-bias ทอง (เหมือน R2)
- fix: `atr_len=14`, `buf=0.1`, session=high_liquidity
→ 3×2×3×2 = 36 cells. **เลือกจากโครงสร้าง/gradient ไม่ใช่ max cell**

## 5. Validation design
- **Single-config WFO ก่อน** (quarterly folds, gate: net PF≥1.10 & ≥60% folds+)
- **Sacred holdout:** dev 2006–2018, ยืนยัน 2019–2026 (แตะครั้งเดียว, freeze config จากโครงสร้าง)
- **Cost stress:** base / 2× / 3× spread — ต้องรอด **2× เป็นอย่างน้อย**
- Pass = ผ่านทั้ง gate(dev) + plateau + holdout(PF≥1.10, mean_r≥60% ของ dev, ไม่ติดลบ) + cost 2× + n≥200

## 6. Red flags / kill criteria
- **BASELINE บังคับ:** เทียบ mean-reversion เปล่า (entry สุ่ม/ทุกแท่งในทิศเดียวกัน same session, same
  TP/SL) — ถ้า wick filter **ไม่ดีกว่า baseline อย่างมีนัยยะ** = ไส้ไม่ได้เพิ่ม edge → falsified
- optimum วิ่งไป k_wick สุดขอบเรื่อยๆ (ยิ่งเข้มยิ่งดีจนไม้เหลือน้อย) = over-selective, หยุด
- ถ้า wick_fill TP ชนะ R-based เฉพาะเพราะ TP ใกล้มาก (win% สูงแต่ mean_r บาง cost กิน) = artifact
- look-ahead: ATR/wick ต้องใช้ค่า ณ แท่งปิด i เท่านั้น, entry ที่ close_i (ไม่ใช่ราคาถัดไป)

---

# R12 — Momentum-Candle Breakout (R1 + range filter)

## 1. Mechanism (ใครจ่าย)
R1 (ORB ดิบ) falsified เพราะเข้าทุก breakout รวม false breakout. คลิปเสนอ filter: เข้าเฉพาะเมื่อ
แท่งที่ทะลุ **แรงจริง** (อุปมา "รถบรรทุก 120 กม/ชม ทะลุกำแพง"). Mechanism ที่จะทำให้ต่อเนื่อง:
breakout ที่มี range ใหญ่ = มี **stop-run / forced fills** จริงหลังทะลุระดับที่คนวางออเดอร์ไว้เยอะ
→ momentum ต่อเนื่องสั้นๆ. ผู้จ่าย = คนที่โดน stop ฝั่งตรงข้าม + late shorts ที่ต้อง cover

Honesty: นี่คือ **R1 ที่ falsified แล้ว + filter เดียว**. ค่าที่แท้จริงของการทดสอบนี้คือ
"filter กู้ ORB ทองได้มั้ย" — ถ้าไม่ได้ = ยืนยันซ้ำว่า breakout ทองไม่มี edge (ผลลบที่มีค่า)

## 2. Rule spec (if/then)
ต่อยอดจาก `gold_orb.py` เดิม เพิ่มเงื่อนไข range filter:
```
เหมือน R1: OR = N นาทีแรกหลัง London open (07:00 UTC)
break: บาร์ที่ close ทะลุ OR_high/OR_low
ADD FILTER: บาร์ที่ทะลุต้อง range(high-low) >= k_range * ATR(atr_len ก่อนหน้า)
            AND range บาร์ทะลุ > range บาร์ก่อนหน้า  (แท่งใหญ่ขึ้น = คลิปย้ำจุดนี้)
entry: ที่ close บาร์ทะลุ (chase — ต่างจาก R2 ที่รอ pullback)
sl_price: อีกฝั่งของ OR (long → OR_low)
tp_price: entry ± tp_r_mult * sl_distance
one-trade/day, ไม่ arm หลัง cutoff 16:00 UTC
```

## 3. Data
`XAUUSD_15m` + `1m`. ATR/range จาก m15. ไม่ต้อง h1/DXY

## 4. Parameter grid
- `k_range` ∈ {1.0, 1.5, 2.0} — เกณฑ์ "แท่งแรง" (แกนหลักที่คลิปเสนอ)
- `or_minutes` ∈ {30, 60}
- `tp_r_mult` ∈ {1.0, 1.5}
- `direction` ∈ {both, long}
- fix: `atr_len=14`, `cutoff=16`
→ 3×2×2×2 = 24 cells

## 5. Validation design
เหมือน R11 (WFO → sacred holdout 2006–2018 / 2019–2026 → cost stress 2×–3×)

## 6. Red flags / kill criteria
- **เทียบกับ R1 baseline โดยตรง:** filter ต้องยก PF/mean_r ขึ้นอย่างมีนัยยะจาก R1 (PF~0.70–0.76)
  ถ้าแค่ลดจำนวนไม้แต่ mean_r ยังติดลบ = filter ไม่กู้ ORB → **R12 falsified, ปิดเคส breakout ทอง**
- ถ้า k_range สูงสุดชนะเสมอจนไม้เหลือ < min_trades = over-selective ไม่ใช่ edge
- ระวัง survivorship ของ filter: ต้องผ่าน holdout ไม่ใช่แค่ dev

---

# R13 — Multi-TF Trend Alignment (meta-filter, ทับ R10)

## 1. Mechanism (ใครจ่าย)
คลิปเน้น top-down (Day→4h→1h→30m ต้องชี้ทางเดียวกัน). Mechanism: การเทรด **สวน HTF trend** =
เข้าฝั่งที่ inventory/positioning ใหญ่กว่าดันสวน (จุดที่คลิปเตือน "เซล m5 ตรงปลายไส้ h1" แล้วโดนเด้ง)
R13 ไม่ใช่ strategy เดี่ยว — เป็น **filter ครอบ R1/R2/R11/R12** เพื่อวัดว่า HTF alignment เพิ่ม
expectancy จริงมั้ย. นี่คือ R10 (regime filter) เวอร์ชันคอนกรีต

## 2. Rule spec (if/then)
```
คำนวณ HTF trend จาก h1 (resample เป็น h4, daily ได้จาก m15/h1 ที่มี):
  trend_tf = sign( EMA(ema_fast) - EMA(ema_slow) )  ต่อ TF  (หรือ HH/HL structure)
  aligned_up   = trend_h1>0 AND trend_h4>0 AND trend_d1>0
  aligned_down = ทุกตัว < 0
wrap base strategy S (เช่น R2):
  IF S สร้าง LONG signal AND aligned_up   → คงไว้
  IF S สร้าง SHORT signal AND aligned_down → คงไว้
  ELSE → action = NO_TRADE
```
เปรียบเทียบ: S เปล่า vs S+R13 filter บน expectancy/PF/n (A/B test)

## 3. Data
`XAUUSD_15m` (signal ของ S) + `1h` (context) + daily resample จาก h1. ไม่ต้อง DXY

## 4. Parameter grid (เล็กมาก — filter ไม่ควรมี knob เยอะ)
- `ema_fast/ema_slow` ∈ {(20,50), (50,200)} — 2 ตัวเลือกมาตรฐาน
- HTF set ∈ {(h1,h4,d1), (h4,d1)} — เข้ม vs กลาง
- base strategy S = R2 (config ที่ผ่าน dev) เป็นตัวหลัก; ลอง R11 ด้วยถ้า R11 รอด
→ 2×2 = 4 cells ต่อ base

## 5. Validation design
- **A/B บน dev เท่านั้น:** S vs S+filter — filter ต้องเพิ่ม PF/mean_r โดยไม่ฆ่า n จนต่ำกว่า floor
- ถ้าเพิ่ม expectancy จริง → ยืนยันบน sacred holdout เดียวกับ base (ไม่ optimize filter บน holdout)
- cost stress: filter ลดจำนวนไม้ → ตรวจว่า PF ที่เหลือยังทน 2×

## 6. Red flags / kill criteria
- **filter ที่แค่ลด n แต่ไม่ยก mean_r = ไร้ค่า** (ตัดไม้มั่ว ไม่ได้ตัดไม้แพ้เจาะจง) → ทิ้ง
- ระวัง double-dipping: อย่า tune ทั้ง base config **และ** filter บนชุดเดียวกัน = selection bias ซ้อน
  → freeze base config ก่อน แล้วค่อยลอง filter
- look-ahead ร้ายแรงสุดที่นี่: HTF trend ต้องใช้ค่า **ณ เวลา signal ของ m15** เท่านั้น
  (resample daily ต้องเป็นแท่งที่ปิดแล้ว ห้ามใช้ daily close ของวันเดียวกันที่ยังไม่จบ)

---

## Deliverable ที่ขอจาก `gold-strategy-coder`
ต่อ R: ตาราง dev (grid) + 1 บรรทัด holdout + cost-stress (base/2×/3×) + baseline comparison
(R11 vs mean-rev เปล่า, R12 vs R1, R13 vs base เปล่า) + verdict PASS/FAIL/NEEDS_MORE_TESTING
บันทึกลง `docs/research/artifacts/xau_r11..r13_*.txt` + อัปเดต backlog ใน `XAU_YOUTUBE_PLAYLIST.md`
และสถานะใน `GOLD_HANDOFF.md`
</content>
