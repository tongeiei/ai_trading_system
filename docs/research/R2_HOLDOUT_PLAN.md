# R2 (ORB + Fib pullback) — Sacred Holdout Evaluation Plan

เขียน: 2026-08-27 · owner track: GOLD (XAU/USD spot) · อ่าน `GOLD_HANDOFF.md` + `XAU_REDDIT_SCOUT.md` ก่อน

> สถานะเข้า plan นี้: R2 มี **in-sample signal เท่านั้น** (2 configs ผ่าน gate บน sweep 24 ตัว,
> gradient coherent) — ยังไม่ใช่ edge. เป้าหมายของแผนนี้คือ **พยายามฆ่า R2** ด้วย sacred holdout +
> cost stress. ถ้ามันรอด เราถึงจะเลื่อนสถานะเป็น "candidate edge". ถ้าไม่รอด = falsified แบบ R1 (ผลที่ดีพอกัน)
>
> แผนนี้ **ไม่เขียนโค้ด backtest** — เป็น pre-registration ให้ `gold-strategy-coder` ไปรัน

---

## 0. Mechanism (ทวนก่อน — เพราะ holdout ที่ผ่านต้องมี "คนจ่าย" รองรับ ไม่ใช่แค่เลขสวย)

R1 (ORB ดิบ) พังเพราะเทรดทุก breakout รวม **false breakout** เต็มไปหมด — ไม่มีใครถูกบังคับให้จ่าย
เราแค่ chase.

R2 เปลี่ยน mechanism: **break = ARM ทิศทางเท่านั้น ไม่เข้า** แล้วรอราคาย่อกลับเข้า Fib retracement
ของ opening range ค่อยเข้าด้วย limit fill. ผู้ที่ "จ่าย" ในเชิงสมมติฐาน:
- **คนที่ไล่ราคาตอน break** (momentum chasers / late breakout buyers) — เข้าแพงตอน break,
  พอราคาย่อพวกนี้ถือ loser อยู่ ต้อง cut → แรงย่อจบเร็วแล้วเด้งกลับทิศ breakout เดิม เราเป็นคนรับของถูก
- **false-breakout filter โครงสร้าง**: ถ้าราคาย่อทะลุ OR ฝั่งตรงข้าม (close < OR_low สำหรับ LONG) =
  breakout ปลอม เรา stand down ไม่เข้าเลย → ตัด failure mode ของ R1 ทิ้งตั้งแต่ต้น

ธงเตือน mechanism: edge บาง (+0.09R/ไม้) และกระจุกที่ fib ลึกสุดที่ลอง (0.618). ถ้า optimum จริง
ลึกกว่านี้เรื่อยๆ อาจแปลว่ากำลัง fit noise / เข้าเขต over-selective ไม่ใช่จับ mechanism จริง —
plan นี้ต้องแยกสองอย่างนี้ให้ออก (ดู §4 sensitivity + §6 kill criteria)

---

## 1. Rule spec ที่ lock (frozen — ห้ามแก้หลังเห็นผล holdout)

กฎมาจาก `src/strategy/gold_orb_pullback.py` — **ยึด "โครงสร้างที่ชนะ" ไม่ใช่ cell ที่ชนะ**
เพื่อกัน selection bias (HANDOFF §งานถัดไป ข้อ 1). โครงสร้างจาก sweep:
`fib ลึก + TP ต่ำ + long-bias` = ดีขึ้นสม่ำเสมอทุก or/tp/dir.

**Config หลักที่ lock (the one number we commit to before touching holdout):**

| param | ค่า lock | เหตุผล (จาก mechanism/gradient ไม่ใช่ grid search) |
|---|---|---|
| `or_start_hour` | 7 (London open UTC) | fix — session ที่ gold มี volume จริง |
| `or_minutes` | 60 | gradient: OR ยาว = noise น้อยลง (สอดคล้อง R1 ที่ OR60 ขาดทุนน้อยสุด) |
| `fib_ratio` | 0.618 | gradient: fib ลึก = entry แคบ, RR ดี, win rate สูง — ปลายที่ดีสุดของ sweep |
| `tp_r_mult` | 1.5 | gradient: pullback = mean-revert สั้น เหมาะ target ใกล้ (1.5R < 2.0R เสมอ) |
| `direction` | long | long-bias ทองเริ่มมีผลเมื่อ entry ดีขึ้น (ต่างจาก R1) |
| `cutoff_hour` | 16 | ไม่ arm ใหม่หลัง NY overlap จบ |

Rule if/then (mirror สำหรับ short ถ้าทดสอบ `both` เป็น secondary):
```
range   = OR_high - OR_low                     (OR = 07:00–08:00 UTC, 60m)
break   : บาร์แรกที่ close > OR_high            -> ARM LONG (ยังไม่เข้า)
fib_lvl = OR_high - 0.618 * range               (entry limit)
entry   : บาร์ถัดมาที่ low <= fib_lvl            -> fill LONG ที่ fib_lvl
stop    : OR_low        (sl_distance = fib_lvl - OR_low, ต้อง > 0)
target  : entry + 1.5 * sl_distance
invalid : ถ้า close < OR_low ก่อน fill          -> stand down (ไม่เทรดวันนั้น)
limit   : 1 trade/day, ไม่ arm ใหม่ตั้งแต่ 16:00 UTC
```
SignalFn contract columns: `time_utc, close(=fib_lvl entry), action(LONG), sl_price(=OR_low),
tp_price, sl_distance`. ตรงกับ output ปัจจุบันของ `generate_orb_pullback_signals` แล้ว.

---

## 2. Data — ยืนยันว่ามีจริง (ไม่สมมติ)

- `data/raw/XAUUSD_15m.parquet` (505k) = signal tf ✅
- `data/raw/XAUUSD_1m.parquet` (7.4M) = triple-barrier labeling ✅
- `data/raw/XAUUSD_1h.parquet` = context (R2 ไม่ใช้ แต่ pipe โหลดอยู่) ✅
- **ไม่ต้องใช้ DXY** (นั่นคือ R5) — R2 ใช้แค่ราคา XAUUSD + session time
- ไม่มี funding (spot) — cost = spread + slippage + commission ตาม `config/gold_spec.yaml`

---

## 3. Holdout split (sacred) — หัวใจของแผนนี้

**แบ่งเวลาเด็ดขาด แตะได้ครั้งเดียว:**

| ช่วง | ปี | ใช้ทำอะไร | แตะได้กี่ครั้ง |
|---|---|---|---|
| **DEV (in-sample)** | 2006-01-01 → 2018-12-31 (~13y) | ยืนยันว่า config §1 ผ่าน gate + ดู sensitivity ได้เต็มที่ | ไม่จำกัด |
| **HOLDOUT (sacred OOS)** | 2019-01-01 → 2026-08-27 (~7.5y) | รัน **ครั้งเดียว** ด้วย config ที่ frozen จาก DEV | **1 ครั้ง เท่านั้น** |

กติกา sacred holdout (กัน selection bias / p-hacking):
1. **Freeze ก่อนแตะ holdout** — config §1 ต้องถูกยืนยันบน DEV ก่อน จากนั้น "ปิดผนึก"
   ห้ามเปลี่ยน param ใดๆ หลังเห็นเลข holdout. ถ้าอยากลอง param อื่น = กลับไปทำบน DEV เท่านั้น
2. **1 shot** — รัน holdout ครั้งเดียวต่อ config. ถ้ารันแล้วไม่ผ่านแล้วไป tweak แล้วรันซ้ำ = holdout
   ปนเปื้อน กลายเป็น in-sample ทันที (burnt). ถ้าเกิดเหตุนี้ต้องประกาศ holdout ว่า burned และเลื่อน
   window ออกไป (ไม่มี window ใหม่แล้ว → รอข้อมูลอนาคต หรือประกาศ inconclusive)
3. Implementation: ใช้ `run_gold_backtest(signal_fn, spec, start=..., end=...)` — DEV = start/end
   2006/2018, HOLDOUT = start 2019-01-01 end None. **แยก 2 รันคนละคำสั่ง อย่าให้ signal_fn
   เห็นข้อมูล holdout ตอน dev** (มันไม่เห็นอยู่แล้วเพราะ split ด้วย start/end ก่อนเข้า signal_fn)

---

## 4. Parameter sensitivity (ทำบน DEV เท่านั้น — ห้ามบน holdout)

จุดประสงค์: แยก "จับ mechanism จริง" ออกจาก "fit จุดโดดเดี่ยว". เราต้องเห็น **plateau ไม่ใช่ spike**
รอบ config §1. Grid เล็ก pre-registered:

- `fib_ratio` ∈ {0.5, 0.618, 0.75} — เพิ่ม 0.75 เพื่อเช็ค: ถ้าลึกกว่ายังดีขึ้นเรื่อยๆ = ธงแดง
  (optimum วิ่งหนี = over-selective/fit). ถ้า 0.75 เริ่มแย่/trade น้อยลงมาก = 0.618 คือ plateau จริง
- `tp_r_mult` ∈ {1.0, 1.5, 2.0}
- `or_minutes` ∈ {30, 60}
- `direction` ∈ {long, both} (both เป็น robustness check ของ mechanism ฝั่ง short)

**เกณฑ์ผ่าน sensitivity (บน DEV):** cell รอบ §1 ต้องเป็นบวกยกแผง (neighbours ไม่พังเป็นหน้าผา);
sign ของ mean_r ไม่พลิกเมื่อขยับ 1 knob. ถ้า §1 เป็นเกาะเดี่ยวล้อมรอบด้วยเลขติดลบ = **reject
ก่อนถึง holdout** (อย่าเปลือง holdout กับ config เปราะ)

---

## 5. Cost stress (รันทั้งบน DEV และ holdout)

cost ใน yaml เป็น **optimistic floor** (spread 1.5 + slip 1.0 = 2.5 bps/side). Gold spread กว้าง
ช่วงข่าว (NFP/CPI/FOMC) และ Asian session. edge R2 บาง (+0.09R) → cost เป็นตัวฆ่าอันดับหนึ่ง.

3 scenario (แก้ `config/gold_spec.yaml` costs หรือ override spec dict ตอนรัน):

| scenario | spread/side | slip/side | ใช้ตัดสิน |
|---|---|---|---|
| **base** | 1.5 bps | 1.0 bps | เลขหลัก (แต่ optimistic) |
| **stress 2×** | 3.0 bps | 2.0 bps | เกณฑ์จริงที่ต้องผ่าน |
| **stress 3×** | 4.5 bps | 3.0 bps | worst-case retail/news |

**เงื่อนไข:** edge ต้องรอดที่ **stress 2× เป็นอย่างน้อย** จึงจะนับว่า tradeable. ถ้าผ่านแค่ base
แต่ตายที่ 2× = edge เป็นแค่ artifact ของ cost ที่มองโลกสวย → ปฏิบัติเหมือน fail

---

## 6. Pass / Fail gate (pre-committed — เขียนก่อนเห็นผล)

R2 = **PASS (candidate edge)** ก็ต่อเมื่อ **ครบทุกข้อ**:

1. **DEV**: config §1 ผ่าน harness gate — net PF ≥ 1.10 **และ** ≥60% ของ quarterly folds เป็นบวก
   (`walk_forward` gate ใน `gold_spec.yaml`)
2. **Sensitivity (DEV)**: §1 อยู่บน plateau ไม่ใช่ spike (§4)
3. **HOLDOUT (2019–2026, base cost)**: net PF ≥ 1.10 **และ** ≥55% ของ folds เป็นบวก
   (ผ่อน folds จาก 60→55% ได้ เพราะ holdout สั้นกว่า fold น้อยกว่า — แต่ PF ห้ามผ่อน)
4. **HOLDOUT degradation**: holdout mean_r ≥ 60% ของ DEV mean_r (เสื่อมได้แต่ห้ามพัง;
   ถ้า holdout mean_r ติดลบ = fail ทันทีไม่ว่า PF)
5. **Cost stress**: ทั้ง DEV และ holdout ยังผ่าน PF ≥ 1.10 ที่ **stress 2×**
6. **Sample size**: holdout n_trades ≥ 200 **และ** n_folds_counted ≥ 8 (folds ที่ ≥20 ไม้).
   config long-only/OR60 คาดได้ ~800–1000 ไม้ใน 7.5y — น่าจะพอ. ถ้า holdout ได้ < 200 ไม้ =
   **NEEDS_MORE_TESTING** ไม่ใช่ pass (edge บนกลุ่มตัวอย่างเล็กเชื่อไม่ได้)

**FAIL** = ข้อใดข้อหนึ่งใน 1–5 ไม่ผ่าน → R2 falsified แบบ R1 (ผลสะอาดที่มีค่า ปิดเคส)
**NEEDS_MORE_TESTING** = ผ่านเกือบหมดแต่ติดข้อ 6 (sample) หรือ holdout borderline (PF 1.05–1.10)

---

## 7. Red flags / สิ่งที่จะถือว่า p-hacking (pre-commit ว่าจะไม่ทำ)

- ❌ รัน holdout แล้ว fail → tweak param → รันซ้ำ. **ห้ามเด็ดขาด** (§3 กติกา 2). holdout ใช้แล้วใช้เลย
- ❌ ย้ายเส้นแบ่ง DEV/HOLDOUT หลังเห็นผลเพื่อให้ผ่าน (เช่นตัดปี 2020 COVID ทิ้ง)
- ❌ เลือก "cell ที่ชนะ" จาก sweep DEV มาเป็น §1 (เราเลือกจาก **โครงสร้าง/gradient** ไม่ใช่ max PF cell)
- ❌ รายงานเฉพาะ base cost แล้วเงียบเรื่อง stress
- ❌ optimum วิ่งหนีลึกขึ้นเรื่อยๆ (fib 0.618→0.75→... ดีขึ้นตลอด) แล้วตาม optimum ไป = fit noise
  → ถ้าเห็นอาการนี้ให้ **หยุดและรายงานว่า over-selective** ไม่ใช่ chase ต่อ
- ❌ look-ahead ในกฎ: ตรวจว่า OR (07:00–08:00) ปิดก่อน bar แรกที่ arm ได้ (arm ต้องเกิด ≥08:00);
  fib_lvl คำนวณจาก OR ที่ปิดแล้วเท่านั้น; entry fill ใช้ `low<=fib_lvl` ของบาร์ **หลัง** arm
  (implementation ปัจจุบันสแกน `after_or` แบบ stateful ไปข้างหน้า — ยืนยันว่าไม่มีบาร์อนาคตรั่ว)
- ❌ leakage ผ่าน triple-barrier: labeling ใช้ m1 หลัง entry time — ยืนยันว่า barrier ไม่ใช้ราคา
  ก่อน entry และ TP/SL วัดจาก fib_lvl (entry) ไม่ใช่ราคา break

---

## 8. Deliverable ที่ขอจาก `gold-strategy-coder`

1. ตาราง DEV: config §1 + sensitivity grid (§4) → PF, mean_r, win%, n, folds+ ต่อ cell
2. **1 บรรทัด holdout** ต่อ config §1: PF, mean_r, win%, n, n_folds_counted, folds+ (base cost)
3. ตาราง cost stress (base / 2× / 3×) ทั้ง DEV และ holdout
4. verdict ตาม gate §6: PASS / FAIL / NEEDS_MORE_TESTING พร้อมข้อที่ตก
5. บันทึกผลลง `docs/research/artifacts/xau_r2_holdout.txt` + อัปเดต `GOLD_HANDOFF.md` สถานะ R2

รันผ่าน `run_gold_backtest(make_signal_fn(**config§1), spec, start, end)` แยก DEV/HOLDOUT คนละคำสั่ง
(อย่ารวม). อย่า refit อะไรบน holdout.
</content>
</invoke>
