# R8 — Post-Liquidation Reversal (แผนถัดไป, mechanism แข็งสุดใน backlog)

เขียน: 2026-08-27 · track: GOLD (XAU/USD spot) · อ่าน `GOLD_HANDOFF.md` + `XAU_REDDIT_SCOUT.md` ก่อน

> ที่มา: R8 ในbacklog Reddit (r/algotrading — "an edge is a reason someone pays you").
> HANDOFF ระบุ R8 = mechanism แข็งสุด (มีคน "ถูกบังคับ" ให้จ่ายจริง — ต่างจาก R1/R2/R12 ที่ chase)
> **นี่คือ "หา strategy ต่อไป" ที่ควรทำหลัง/คู่ขนานกับ R11–R13**

---

## 1. Mechanism (ใครจ่าย — ชัดสุดในทั้ง backlog)
เมื่อมีแท่งวิ่งแรงผิดปกติ (range/ATR สูงมาก) แบบ **capitulation** — นั่นคือสัญญาณของ
**forced sellers/liquidation** (margin call, stop cascade, leveraged CFD/futures โดนบังคับปิด).
คนกลุ่มนี้ **ไม่ได้เลือกจะขายที่ราคานี้ — เขาถูกบังคับ** → ราคาเลย overshoot เกินมูลค่าจริงชั่วคราว
เมื่อ flow บังคับหมด (แท่งถัดไปแรงลด) liquidity providers ที่รับของถูกดันราคากลับ → **reversal สั้น**.
ผู้จ่าย = คนที่ถูก liquidate (ขายที่ก้น/ซื้อที่ยอด) + market makers ที่ต้อง unwind inventory

นี่ต่างจาก R1/R12 (chase breakout — ไม่มีใครถูกบังคับ) โดยพื้นฐาน: R8 **fade** capitulation
= รับฝั่งตรงข้ามกับคนที่ถูกบังคับ. Fade ต้องระวังจังหวะ (มีดร่วง) → กฎต้องรอ "flow หมดแรง" ก่อน

## 2. Rule spec (if/then) — fade แท่ง capitulation ขาลง → LONG (mirror ขาขึ้น → SHORT)
ทำบน m15:
```
atr       = ATR(atr_len) ก่อนแท่งสัญญาณ
range_i   = high_i - low_i
capitulation DOWN (แท่ง i):
  IF close_i < open_i                         (แท่งแดง)
  AND range_i >= k_capit * atr                (วิ่งแรงผิดปกติ)
  AND (close_i - low_i) <= close_frac * range_i  (ปิดใกล้ low = แรงขายครอง, ยังไม่มี rejection)
  THEN ARM long-reversal
exhaustion confirm (แท่ง i+1 ... i+M):
  รอแท่งที่ range หดลง (range < range_i * shrink)  OR แท่งที่ปิดเขียว (close>open)
  = flow บังคับหมดแรง → เข้า LONG ที่ close ของแท่ง confirm นั้น
  sl_price    = min(low ตั้งแต่ i ถึง confirm) - buf*atr   (ใต้ก้น capitulation)
  sl_distance = entry - sl_price (>0)
  tp_price    = entry + tp_r_mult * sl_distance   (reversal สั้น → target ใกล้)
invalidate: ถ้าไม่มี confirm ภายใน M แท่ง → ยกเลิก (ไม่ fade มีดที่ยังร่วง)
session: เข้าเฉพาะ high_liquidity (capitulation ช่วง Asia บาง = ระวัง fake)
one-trade: ไม่ overlap
```

## 3. Data
`XAUUSD_15m` (signal) + `1m` (triple-barrier). ATR/range จาก m15. ไม่ต้อง h1/DXY/volume
(หมายเหตุ: spot Dukascopy ไม่มี volume จริง — ใช้ **range เป็น proxy ของ capitulation** ตามที่ backlog เขียน)

## 4. Parameter grid (เล็ก, justify จาก mechanism)
- `k_capit` ∈ {2.0, 2.5, 3.0} — "แรงผิดปกติ" แค่ไหนถึงนับเป็น liquidation (แกนหลัก)
- `tp_r_mult` ∈ {1.0, 1.5, 2.0} — reversal เร็ว → คาดว่า TP ใกล้ชนะ (เหมือน R2)
- `M` (confirm window) ∈ {1, 3} — รอ exhaustion กี่แท่ง
- `direction` ∈ {both, long} — long-bias ทอง
- fix: `atr_len=14`, `close_frac=0.35`, `shrink=0.7`, `buf=0.1`, session=high_liquidity
→ 3×3×2×2 = 36 cells. **เลือกจาก gradient ไม่ใช่ max cell**

## 5. Validation design
- Single-config WFO (quarterly, gate PF≥1.10 & ≥60% folds+)
- **Sacred holdout:** dev 2006–2018, confirm 2019–2026 (แตะครั้งเดียว, freeze จากโครงสร้าง)
- **Cost stress:** base/2×/3× — fade entry มักได้ราคาดี (เข้าที่ extreme) แต่ต้องรอด 2×
- Pass = gate(dev) + plateau + holdout(PF≥1.10, mean_r≥60% dev, ไม่ติดลบ) + cost 2× + n≥200

## 6. Red flags / kill criteria
- **"จับมีดร่วง":** ถ้า config ที่ไม่รอ confirm (M เล็ก/close_frac หลวม) ขาดทุนหนัก แต่ config รอ confirm
  ดีขึ้นชัด = mechanism จริง (exhaustion สำคัญ). ถ้ารอ confirm แล้วยังแพ้ = fade ทองไม่มี edge → falsified
- **regime dependency:** capitulation reversal มักดีในตลาด range/mean-revert, พังในตลาด trending แรง
  (2020, 2022–2024 ทองขาขึ้นยาว) → ดู folds+ ต่อปี; ถ้า edge มาจาก 2–3 ปีเดียว = ไม่ robust
- optimum วิ่งไป k_capit สุดขอบจนไม้เหลือน้อย = over-selective
- baseline เทียบ: fade ทุกแท่งแดงใหญ่ (ไม่รอ confirm) — confirm ต้องเพิ่ม edge อย่างมีนัยยะ
- look-ahead: ATR/range ใช้ ณ แท่งปิด, entry ที่ close ของแท่ง confirm (ไม่ใช่ราคาถัดไป),
  SL ใช้ low ที่เกิดแล้วเท่านั้น

---

## ทำไม R8 คือตัวถัดไปที่ถูกต้อง (เทียบ backlog ที่เหลือ)
- **R8** = mechanism แข็งสุด (forced traders จ่ายจริง), independent จาก ORB family → **ทำก่อน**
- **R7** (overnight/session-open mean reversion) — mechanism ดี (overnight inventory) แต่ spot ไม่มี
  gap ชัดเท่า futures; รองลงมา
- **R5** (DXY filter) — ยังติดที่ **ไม่มี DXY data** ใน `data/raw/` ต้องดึงก่อน (ยังไม่พร้อม)
- **R9** (SMA200 bounce) — mechanism อ่อน (self-fulfilling) — ลำดับท้าย

## สถานะ backlog หลังแผนนี้
R1 ❌ · R2 🟡(holdout รอ) · R11/R12/R13 ⬜(รอ coder รัน) · **R8 ⬜ พร้อมส่งต่อ** · R5 ⛔(รอ DXY) · R7/R9 backlog
</content>
