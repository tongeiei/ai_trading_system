# XAU/USD — Reddit Scout (ชุดข้อมูลแรก)

ส่องจริงจาก **r/Forex** และ **r/Daytrading** (top posts, ย้อนหลัง 1 ปี) ผ่าน Reddit JSON
วันที่ส่อง: 2026-08-27

> ⚠️ **บริบทสำคัญก่อนอ่าน:** Reddit สองซับนี้ **~90% เป็น noise** — โพสต์ที่ขึ้น top
> ส่วนใหญ่คืออวดกำไร (PnL flex), meme, และคนขายคอร์ส/prop-firm affiliate
> Survivorship bias เต็มไปหมด (คนเจ๊งไม่โพสต์) และแทบไม่มีใครแนบ backtest/out-of-sample
> เพราะฉะนั้นสิ่งที่เก็บมาข้างล่าง = **"สมมติฐานให้ไปทดสอบ"** ไม่ใช่ edge ที่พิสูจน์แล้ว

---

## สิ่งที่พบ: theme ที่พูดถึงซ้ำๆ (มีเนื้อจริง ไม่ใช่แค่อวด)

| Theme | ที่มา (สรุป ไม่ใช่ verbatim) | testable? |
|---|---|---|
| **Opening Range Breakout (ORB)** | โพสต์ยอด upvote สูงสุด: ตี opening range 15–30 นาทีแรกของ session, ใช้ break high/low เป็น "สัญญาณทิศทาง" แต่ **ไม่เข้าตอน break** — รอ pullback | ✅ มาก |
| **ORB + Fib pullback** | ต่อจากบน: หลัง break แล้วรอราคาย่อมาที่ Fib retracement (ลากจาก session low→high) ค่อยเข้า → ลด false breakout | ✅ |
| **เทรด session เดียว วินัยสูง** | r/Forex: "1 setup, 1 pair, 1 session" ซ้ำหลายโพสต์ — เข้าน้อยครั้ง เลือกเฉพาะช่วงเวลาที่มี edge | ✅ (เป็นกฎ filter) |
| **Session timing** | London / NY overlap = ช่วง volume จริง; Asian range แคบใช้เป็นฐาน breakout | ✅ |
| **Gold ↔ DXY correlation** | พูดถึง gold เคลื่อนสวน DXY / ผูก risk sentiment | ✅ (ต้องหา DXY data เพิ่ม) |
| **Few-trades / risk discipline** | คนที่อ้าง consistent มัก "เข้า 1–2 ไม้/สัปดาห์" ไม่ overtrade | ⚠️ เป็นวินัย ไม่ใช่ signal |

---

## สมมติฐานกลั่นแล้ว → พร้อมยิง backtest บน `XAUUSD_*` (20 ปี)

เขียนเป็นกฎ if/then ที่ทดสอบได้ ยังไม่ผ่านการทดสอบทั้งหมด

| # | สมมติฐาน (กฎ) | ข้อมูลที่ต้องใช้ | สถานะ |
|---|---|---|---|
| R1 | **ORB ตรงๆ:** ตี range ของ N นาทีแรกหลังเปิด London (07:00 UTC) → เข้า long เมื่อ break high / short เมื่อ break low, SL อีกฝั่งของ range, TP = k×range | XAUUSD_15m + session time | ⬜ |
| R2 | **ORB + pullback (เวอร์ชันในโพสต์):** break range แล้ว **รอ** ราคาย่อกลับมา 0.5–0.618 Fib ของ range ค่อยเข้าในทิศ breakout | XAUUSD_1m/15m | ⬜ |
| R3 | **Asian-range breakout:** ใช้ range ช่วง Asia (00:00–07:00 UTC) เป็นกล่อง → breakout ช่วง London | XAUUSD_15m | ⬜ |
| R4 | **Session filter:** เทรดเฉพาะ London+NY overlap (12:00–16:00 UTC) เทียบกับเทรดทั้งวัน — expectancy ต่างมั้ย | XAUUSD_1h | ⬜ |
| R5 | **DXY filter:** เข้า long gold เฉพาะเมื่อ DXY อยู่ต่ำกว่า MA (USD อ่อน) และกลับกัน | XAUUSD + DXY (`data/raw/DXY_daily.parquet`, Yahoo DX-Y.NYB) | ❌ **FALSIFIED ที่ DEV gate** (ดู `docs/research/GOLD_HANDOFF.md` และ `docs/research/artifacts/xau_r5_dxy_filter.txt`) |
| R6 | **Few-trades quality filter:** จำกัดจำนวนไม้/สัปดาห์ (เข้าเฉพาะ setup คะแนนสูงสุด) เทียบ expectancy vs เข้าทุกสัญญาณ | ผลจาก R1–R4 | ⬜ |

---

## ธงแดงที่เจอ (ไว้เตือนตัวเอง)

- โพสต์ upvote สูง = มัก PnL flex / prop-firm payout / ขายคอร์ส ไม่ใช่ edge
- ไม่มีใครแนบ spread/slippage ในผล → ผลจริงจะแย่กว่าที่อวดเสมอ โดยเฉพาะ gold (spread กว้าง)
- ORB เป็น strategy ที่ดังมาก → ถ้ามี edge จริงก็ถูก arbitrage เยอะแล้ว **ต้องเทสต์เองบนข้อมูลเรา** ห้ามเชื่อคำอ้าง
- "consistent 10-15k/month" ไม่มี track record ตรวจสอบได้ = ทิ้งไปได้เลย เก็บแค่ "โครงสร้างกฎ"

---

## Next step ที่แนะนำ

1. เริ่มจาก **R1 (ORB)** เพราะชัด เขียนกฎง่าย เทสต์ได้ทันทีบน `XAUUSD_15m` 20 ปี
2. ทำ walk-forward (แบ่ง in-sample / out-of-sample) กัน overfit ตั้งแต่ต้น
3. ถ้าจะทำ R5 ต้องหา **DXY historical** มาเพิ่ม (ตอนนี้ยังไม่มีใน data/raw)
4. ทุกผลบวก spread+slippage จริงของ gold ก่อนสรุป

_แหล่ง: r/Forex, r/Daytrading (top/year). สรุปเป็นแนวคิด ไม่ได้คัดลอกเนื้อหา verbatim._

---
---

# รอบ 2 — r/algotrading + (r/GoldTrading / r/XAUUSD)

วันที่ส่อง: 2026-08-27

## สถานะซับที่ตั้งใจส่อง
- **r/GoldTrading = private** เข้าไม่ได้ (403)
- **r/XAUUSD** (8.3k, restricted) — เปิดอ่านได้ แต่ **แทบร้าง**: top all-time upvote สูงสุดแค่ ~28 เป็นแชตเป้าราคา/physical gold ไม่มี strategy → **ทิ้งได้** ไม่มีค่า
- ทางเลือกที่มีค่าจริง = **r/algotrading** (คุณภาพสูงกว่า 2 ซับแรกมาก คนคุยเชิง quant/backtest จริง)

## ⭐ ของดีที่สุดที่เจอรอบนี้ — mindset เรื่อง "edge"

โพสต์ *"an edge is a reason someone pays you"* (r/algotrading, 310u) — ตรงกับหลัก quant ที่ดี:

> **เริ่มจาก "ใครเป็นคนจ่ายเงินให้เรา" ไม่ใช่เริ่มจาก indicator**

แหล่งของ edge จริง (mechanism) ที่เขายกมา แล้วค่อยแปลงเป็น feature/hypothesis:
- **Forced traders** — คนที่ถูกบังคับให้ปิด (liquidation, margin call) → สร้าง reversal ระยะสั้น
- **Overnight inventory** — ของค้างข้ามคืนต้องเคลียร์ตอน session จริงเปิด
- **Market makers โดนอัด** แล้ว fade กลับ
- **Underreaction** — ตลาด react ช้า 1 ชม. แล้วค่อยวิ่งต่อจนจบ move

หลักการ: *"มี mechanism → คาดว่าจะเห็นอะไรถ้ามันจริง → นั่นคือ feature → กำหนดว่ามันควรไปทางไหน → นั่นคือ hypothesis ที่ testable"*
ต่างจาก "RSI < 30 = bullish" (ซึ่งไม่มีเหตุผลว่าใครจ่าย) — **นี่คือมาตรฐานที่เราควรใช้กรอง R1–R6 ของรอบแรก**

## Reference: taxonomy strategy พื้นฐาน (จากโพสต์ 614u)

ไว้เป็น checklist ว่ามีอะไรให้ลองบ้าง (ยังไม่กรอง edge):
- **Trend/Momentum:** MA/EMA cross, MACD, New High/Low breakout, ATR, VWAP, momentum rotation
- **Mean Reversion:** revert-to-trend, revert-in-range, grid
- **Breakout:** **Open Range Breakout (ORB)**, SMA break-bounce (20/50/100/200), compression/wedge breakout
- **อื่นๆ:** arbitrage/pairs, seasonal, scalping, candlestick pattern, news/sentiment

## โพสต์ที่ควรตามอ่านต่อ (มี backtest จริง)
- *"Regime-Based Overnight Mean Reversion"* — อ้าง 3M: 24% return, WR 64.7%, Sharpe 3.51 (ต้องระวัง overfit/ช่วงสั้น แต่ **แนวคิด regime + overnight** ตรงกับ mechanism "overnight inventory" ข้างบน)
- *"simple mean reversion 70% WR but only invested 20% of the time"* — WR สูงเพราะเลือกเวลาเข้าน้อย (ตรงกับ R6 few-trades filter)

## สมมติฐานใหม่ที่เพิ่มเข้า backlog

| # | สมมติฐาน (กฎ) | mechanism (ใครจ่าย) | ข้อมูล | สถานะ |
|---|---|---|---|---|
| R7 | **Overnight/session-open mean reversion:** gold ที่ gap/วิ่งแรงช่วงตลาดปิด-เบาบาง มักย้อนกลับตอน London เปิด | overnight inventory ต้องเคลียร์ | XAUUSD_1h + session time | ⬜ |
| R8 | **Post-liquidation reversal:** หลังแท่งวิ่งแรงผิดปกติ (range/ATR สูงมาก) + volume พุ่ง → เข้า fade ทิศตรงข้ามระยะสั้น | forced sellers/liquidation | XAUUSD_15m (ATR, range) | ⬜ |
| R9 | **SMA break-bounce:** ราคาแตะ/ทะลุ SMA200 (D) แล้วเด้ง — long ที่ bounce | ระดับที่คนดูเยอะ = self-fulfilling | XAUUSD_1h/daily | ⬜ |
| R10 | **Regime filter ครอบทุกกลยุทธ์:** แยก regime (trending vs ranging ด้วย ADX/ATR) แล้วเปิดเฉพาะกลยุทธ์ที่เข้ากับ regime | — (meta-filter) | XAUUSD ทุก tf | ⬜ |

## ข้อสรุปเชิงกลยุทธ์การส่อง
- 4 ซับที่ส่องมา คุณภาพ: **r/algotrading >> r/Daytrading > r/Forex >> r/XAUUSD (ทิ้ง)**, r/GoldTrading เข้าไม่ได้
- รอบต่อไปถ้าจะส่อง Reddit เพิ่ม แนะนำ **r/algotrading เจาะลึก** (ตาม flair "Strategy"/"Research") จะคุ้มกว่าซับเทรดทั่วไป
- แต่ ณ จุดนี้ **hypothesis สะสมพอเริ่มลงมือแล้ว (R1–R10)** — ขั้นต่อไปควรเป็น backtest ไม่ใช่ส่องเพิ่ม

_แหล่ง: r/algotrading, r/XAUUSD (r/GoldTrading private). สรุปเป็นแนวคิด ไม่คัดลอก verbatim._

---
---

# Backtest harness สำหรับ gold (แยกจาก ETH) — พร้อมเสียบ R1–R10

วางโครงเสร็จ 2026-08-27 · ใช้ **XAUUSD spot 20 ปี** (ไม่ใช่ perp 8 เดือน)

## ไฟล์
- [`config/gold_spec.yaml`](../../config/gold_spec.yaml) — instrument + **cost assumptions** (spread/slippage/commission เป็น bps, **ไม่มี funding** เพราะเป็น spot) + validation gate
- [`src/backtest/gold_harness.py`](../../src/backtest/gold_harness.py) — โครงหลัก reusable
- [`scripts/run_gold_backtest_smoke.py`](../../scripts/run_gold_backtest_smoke.py) — smoke test (พิสูจน์ pipe ครบวงจร)

## reuse จาก engine เดิม (ไม่ fork core)
`build_features` · `triple_barrier.label_all_signals` · `significance.bootstrap_mean_test`
ต่างหลักๆ: ข้อมูล spot 20 ปี + cost แบบ spread (ไม่มี funding) + WFO quarterly จริง (perp ทำไม่ได้)

## วิธีเสียบ hypothesis ใหม่ (R1–R10)
เขียน `signal_fn(m15, h1, features) -> DataFrame` ที่มีคอลัมน์:
`time_utc, close, action(LONG/SHORT/NO_TRADE), sl_price, tp_price, sl_distance`
แล้วเรียก `run_gold_backtest(signal_fn, spec, start=..., end=...)` → คืน `{trades, eval, wfo}`

```bash
PYTHONPATH=. .venv/bin/python scripts/run_gold_backtest_smoke.py         # ~3 ปีล่าสุด (เร็ว)
PYTHONPATH=. .venv/bin/python scripts/run_gold_backtest_smoke.py --full  # 20 ปีเต็ม
```

## สถานะ smoke (placeholder = long ทุก London open, ไม่ใช่ผลจริง)
pipe OK: 1,050 trades, gate FAIL ตามคาด (placeholder ไม่มี edge) → โครงพร้อมรับ R จริง

---

# ผลทดสอบ R2 — ORB + Fib pullback 🟡 มีสัญญาณ (ยังไม่ยืนยัน — in-sample เท่านั้น)

รัน 2026-08-27 · XAUUSD spot 20 ปี · ผลเต็ม: [`artifacts/xau_r2_orb_pullback_sweep.txt`](artifacts/xau_r2_orb_pullback_sweep.txt)

**baseline (OR30/fib0.5/TP2R/both):** win 49% · PF 0.83 · folds+ 34% — ดีกว่า R1 ชัด แต่ยัง FAIL

### สิ่งที่น่าเชื่อกว่า "cell ที่ชนะ" = gradient ที่ coherent
ทั่วทั้ง sweep 24 configs เห็นแนวโน้มสม่ำเสมอ (ไม่ใช่จุดโดดเดี่ยว):
- **fib ลึกขึ้น 0.382 → 0.5 → 0.618 → ดีขึ้นทุกครั้ง** ทุก or/tp/dir (entry แคบ = RR ดี + win rate สูง)
- **TP 1.5R < 2.0R เสมอ** (pullback entry เป็น mean-revert สั้น เหมาะ target ใกล้)
- **long-only ดีกว่า both เล็กน้อย** (ต่างจาก R1 — long-bias ทองเริ่มมีผลเมื่อ entry ดีขึ้น)

### config ที่ "ผ่าน" gate (⚠️ in-sample):
| or | fib | tp | dir | n | win% | meanR | PF | folds+ | |
|----|-----|----|-----|---|------|-------|----|--------|--|
| 60 | 0.618 | 1.5 | long | 2176 | 68.5 | +0.138 | **1.29** | 64% | ✅ |
| 60 | 0.618 | 1.5 | both | 3205 | 66.3 | +0.091 | **1.18** | 65% | ✅ |
| 30 | 0.618 | 1.5 | long | 2535 | 69.8 | +0.067 | 1.15 | 59% | ~ |

### 🚨 ยังห้ามเชื่อ — นี่คือ in-sample sweep
- เลือก config ที่ดีสุดจาก 24 ตัวบนข้อมูลชุดเดียวกัน = **selection bias / p-hacking** (ตรงกับที่ PROJECT_PLAN เตือน: ต้อง sacred holdout)
- edge บาง: +0.09R/ไม้, PF 1.18 — **cost ใน yaml เป็นค่า optimistic** ถ้า spread จริงกว้างกว่านี้อาจหายหมด
- edge กระจุกที่ fib ลึกสุดที่ลอง (0.618) — อาจแปลว่า optimum จริงลึกกว่านี้ หรือกำลังเข้าเขต over-selective

### ✅ ขั้นต่อไปที่ถูกต้อง (ก่อนเชื่อ R2)
1. **Sacred holdout:** lock กฎจาก *โครงสร้าง* (fib ลึก + TP ต่ำ) ไม่ใช่ cell ที่ชนะ → dev บน 2006–2018, ยืนยันบน 2019–2026 ที่ไม่เคยแตะ
2. **Cost stress:** เพิ่ม spread 2–3 เท่า ดูว่า edge รอดมั้ย
3. **Per-fold refit WFO** (ตอนนี้เป็น single-config reporting)

**สรุป R2:** ต่างจาก R1 (พังทุกที่) อย่างมีนัยยะ — **มี structural signal จริง** แต่ยังเป็นแค่ "สมมติฐานที่ยังไม่ถูก falsify" ไม่ใช่ edge ที่ยืนยันแล้ว

---

# ผลทดสอบ R1 — Opening Range Breakout ❌ FALSIFIED

รัน 2026-08-27 · XAUUSD spot 20 ปี (5,342 ไม้) · ผลเต็ม: [`artifacts/xau_r1_orb_sweep.txt`](artifacts/xau_r1_orb_sweep.txt)

**baseline (OR=30m, TP=2R, both):** win 34.2% · mean_r −0.234 · PF 0.70 · folds+ 12% · **FAIL**

**sweep 18 configs** (OR 15/30/60m × TP 1/1.5/2R × both/long) — **ทุกตัว FAIL:**
- PF ดีสุด = **0.76** (OR60/TP2/both) ยังห่างจาก gate 1.10 มาก
- ทุก config mean_r **ติดลบ**, boot p=0.0 (แพ้อย่างมีนัยยะ ไม่ใช่แค่ noise)
- **long-only แย่กว่า both เสมอ** → long-bias ของทองไม่ช่วย ORB (shorts กลับช่วยพยุง)
- OR ยาวขึ้น (60m) ขาดทุนน้อยลงเล็กน้อย แต่ยังไม่มี edge

**สรุป:** ORB ดิบไม่มี edge บนทอง — gross แทบ breakeven, cost กินจนติดลบ
ตรงตามที่คาด (strategy ดังเกินไป = ถูก arbitrage) และตกเกณฑ์ "ใครเป็นคนจ่าย"
(เทรดทุก breakout รวม false breakout เต็มไปหมด)

**R1 = ปิดเคส** ✅ ประโยชน์ที่ได้: harness พิสูจน์แล้วว่า falsify ได้จริง สะอาด เร็ว

### เรียนรู้ต่อ → ทำไม R2/R8 น่าจะดีกว่า
- ปัญหาหลักของ R1 = **false breakout**. **R2 (ORB + pullback เข้าที่ Fib)** โจมตีตรงจุดนี้
- **R8 (post-liquidation reversal)** mechanism แข็งกว่า (มีคน "ถูกบังคับ" ให้จ่าย) — fade แทน chase

---

## ⚠️ ยังไม่ได้ทำ (ต้องทำก่อนเชื่อผล)
- cost ใน yaml เป็น **ค่าสมมติแบบ optimistic** — ต้องเทียบ spread จริงจาก broker (โดยเฉพาะช่วงข่าว)
- WFO ตอนนี้เป็น single-config reporting **ยังไม่ได้ refit ต่อ fold** — ต้องเพิ่ม parameter search แบบ per-fold ตอนทำ R จริง
- R5 ยังต้องหา **DXY data** เพิ่ม

---
---

# รอบ Facebook — เพจ "หมีกระชากกราฟ" (idea ดิบ → กลั่นเป็น hypothesis)

วันประเมิน: 2026-08-27 · **แหล่ง = สมมติฐาน ไม่ใช่หลักฐาน** (โพสต์สอน/ขายคอร์ส, survivorship)

## Idea: "Fake Zone" (fake breakout / liquidity sweep) → verdict: **รับเป็น R14 แต่มีเงื่อนไข**

โพสต์อธิบาย: ราคาแกล้งทะลุ S/R zone หลอกให้คนเข้าตาม แล้วเด้งกลับเข้า zone ทันที
= รายใหญ่กวาด stop/liquidity ก่อนวิ่งจริง. แนะนำ "รอ confirm" (ทะลุแล้วอยู่ได้ไหม, มี
follow-through/volume ไหม, ปิดกลับเข้า zone ไหม) — ภาษา folklore ทั่วไป

### การตัดสิน distinctness (ซื่อสัตย์)
- **overlap กับ R2:** R2 มี stand-down กัน false breakout อยู่แล้ว **แต่ R2 เทรด "ตาม" breakout
  หลัง pullback** — Fake Zone เทรด "สวน" ตัว fake เอง (short หลัง fake ขึ้น). ทิศตรงข้าม → คนละกฎ
- **overlap กับ R8:** R8 fade แท่ง capitulation ที่ range/ATR สูง **ที่ราคาใดก็ได้ ไม่ผูก level**.
  Fake Zone **ผูกกับ structural level** (stop กระจุกเหนือ swing high/ใต้ swing low). level-anchoring คือของใหม่
- **overlap กับ R11 (wick-fill):** ใกล้สุด — fake breakout มักทิ้งไส้ทะลุ level. **แต่ R11 trigger จาก
  รูปแท่ง (ไส้ยาว) ที่ไหนก็ได้; R14 ต้องมี level ที่นิยามชัด + close กลับเข้า.** → distinct trigger
- **สรุป:** ของใหม่จริงคือ **"level-anchored liquidity sweep + close-back confirmation"** เท่านั้น
  ส่วน mechanism (chasers โดน trap + stop ถูกกวาด) เป็นเรื่องจริง (forced payer แท้) แต่ **ทับ R11 มาก**
  → รับเป็น R14 ได้ **ก็ต่อเมื่อ baseline vs R11/R8 พิสูจน์ว่า level-anchoring เพิ่ม edge จริง** (ดู kill)

### mechanism honesty
"stop-hunt liquidity sweep" = payer จริง (breakout traders โดน stop + stop cluster เหนือ/ใต้ swing
ที่คนดูเยอะ). **ไม่ใช่ folklore เปล่า** — ต่างจาก Elliott/Running-Flat ที่ปัดตกเพราะ hindsight.
**แต่** ภาษา confirm เรื่อง "volume/follow-through" ของโพสต์ **operationalize ไม่ได้บน spot** (Dukascopy
มีแค่ tick-volume เชื่อไม่ได้) → **ตัด volume ทิ้งทั้งหมด ใช้ price-only confirmation (close กลับเข้า zone)**

## R14 — Level-Anchored Liquidity Sweep (fake breakout reversal)

| # | สมมติฐาน (กฎ) | mechanism (ใครจ่าย) | ข้อมูล | สถานะ |
|---|---|---|---|---|
| R14 | **Sweep-and-reverse ที่ level:** ราคา sweep ทะลุ swing-level แล้ว **ปิดกลับเข้า** ภายใน N แท่ง → เข้า "สวน" (short หลัง fake ขึ้น / long หลัง fake ลง) | breakout chasers โดน trap + stop ที่กระจุกเหนือ swing ถูกกวาด → market maker fade | XAUUSD_15m/1h + 1m | ❌ **FALSIFIED ที่ DEV gate** (ดู `docs/research/GOLD_HANDOFF.md` และ `docs/research/artifacts/xau_r14_fake_zone.txt`) |

### Rule spec (if/then) — SHORT หลัง fake breakout ขึ้น (mirror สำหรับ LONG)
ทำบน m15 (หรือ h1). ต่อแท่งปิด i:
```
level:   swing high ล่าสุดที่ยังไม่ถูกทะลุ = pivot high (fractal) โดยมี w แท่งซ้าย/ขวาต่ำกว่า
break:   ระหว่างแท่ง j..i มี high > level + b_break * ATR  (ทะลุจริง ไม่ใช่จิ้มปลาย)
fake confirm: แท่ง i **ปิด** กลับใต้ level (close_i < level) ภายใน N แท่งนับจาก break
  THEN action=SHORT ที่ close_i (=entry)
  sl_price    = max(high ช่วง sweep) + buf*ATR   (เหนือจุดกวาด)
  sl_distance = sl_price - close_i  (>0)
  tp_price    = close_i - tp_r_mult * sl_distance  (reversal สั้น -> target ใกล้ เหมือน R2/R8)
invalidate:  ถ้าไม่ปิดกลับเข้าภายใน N แท่ง = breakout จริง -> ยกเลิก (ห้าม fade breakout จริง)
session:     เข้าเฉพาะ high_liquidity (London/Overlap/NY); level ที่ Asia บาง = fake ปลอม
one-trade:   ไม่ overlap
```

### สิ่งที่ต้อง PRE-REGISTER (กัน hindsight — level เป็นตัวอันตรายสุด)
- **นิยาม level:** pivot fractal width `w` ∈ {3, 5} (ล็อกก่อน ห้ามเลือก level ด้วยตา)
- **break threshold** `b_break` ∈ {0.25, 0.5} × ATR — กันนับ 1-tick touch เป็น breakout
- **close-back window** `N` ∈ {1, 3} แท่ง — เร็ว = sweep แท้, ช้า = อาจเป็น reversal ทั่วไป
- **tp_r_mult** ∈ {1.0, 1.5, 2.0} · **direction** ∈ {both, long}
- fix: `atr_len=14`, `buf=0.1`, session=high_liquidity -> 2×2×2×3×2 = 48 cells (เลือกจาก gradient)

### Validation + kill criteria
- Single-config WFO -> sacred holdout (dev 2006–2018 / confirm 2019–2026) -> cost stress 2×–3×.
  Pass = gate(dev PF>=1.10 & >=60% folds+) + plateau + holdout ไม่ติดลบ + cost 2× + n>=200
- **KILL/เงื่อนไขหลัก — baseline บังคับ:** R14 ต้องชนะ **R11 (wick-fade เปล่า) และ R8 (candle-fade เปล่า)**
  อย่างมีนัยยะบน dev เดียวกัน. ถ้า level-anchoring **ไม่เพิ่ม edge เหนือ R11/R8** = R14 คือ R11/R8
  พูดใหม่ -> **ปัดตก ไม่ต้องทำต่อ** (fold "close-back confirmation" กลับเข้า R11 เป็น optional filter)
- kill อื่น: b_break/w วิ่งสุดขอบจนไม้เหลือน้อย = over-fit level; edge มาจาก 2–3 ปี = ไม่ robust;
  look-ahead: pivot ต้อง confirmed (มี w แท่งขวาปิดแล้ว), entry ที่ close แท่ง confirm เท่านั้น
- **ลำดับ:** ทำ **หลัง** R11/R8 เสมอ (ต้องมีผล R11/R8 เป็น baseline ก่อน) — ไม่ใช่ตัวถัดไปทันที

### ผลจริง (2026-08-27)
เนื่องจาก R8/R11 ทั้งคู่ล้มเหลว (net-losing) เอง เกณฑ์ "ต้องชนะ R8/R11" จึงไม่มีความหมาย
(ชนะกลยุทธ์ที่ขาดทุนไม่ได้พิสูจน์อะไร) — ผู้ใช้ตัดเงื่อนไขนี้ทิ้งและสั่งรัน R14 ผ่าน pipeline
มาตรฐาน (DEV grid → sacred holdout → cost stress) ตามเกณฑ์ปกติของ track แทน ไม่มีข้อยกเว้น

**DEV grid 48 cells (2006–2018) = FAIL ทุก cell** PF 0.56–0.67 (เกณฑ์ 1.10), folds+ 0–18%
(เกณฑ์ 60%), mean_r ติดลบทุก cell (-0.177 ถึง -0.383). gradient coherent ไม่มี runaway
optimum — ล้มเหลวสม่ำเสมอทั้ง grid ไม่ใช่ borderline. **ไม่แตะ sacred holdout** (ตามกฎ
pre-commit: ตายที่ DEV ไม่ต้องเปลืองการแตะ holdout ครั้งเดียว) → **verdict = FALSIFIED ที่
DEV gate** เหมือน R11 ดูรายละเอียดเต็มที่ `docs/research/artifacts/xau_r14_fake_zone.txt`

---
---

# ผลทดสอบ R5 — DXY regime filter ❌ FALSIFIED ที่ DEV gate

รัน 2026-08-27 · ข้อมูล DXY ใหม่: `data/raw/DXY_daily.parquet` (5,198 แถว, 2006-01-03 ถึง
2026-08-27, Yahoo Finance DX-Y.NYB / ICE US Dollar Index) — ครอบคลุม 20y เดียวกับ XAU spot
เต็มพอดี ผลเต็ม: [`artifacts/xau_r5_dxy_filter.txt`](artifacts/xau_r5_dxy_filter.txt)

## Rule spec (pre-registered ก่อนรัน — ไม่มี plan doc แยกเพราะ scope เล็ก เขียนในนี้แทน)

**Mechanism ("ใครจ่าย"):** ต่างจาก R1/R2/R8/R11/R14 (pattern บนทองอย่างเดียว) — R5 อ้างว่า
regime มหภาค (USD แข็ง/อ่อนเทียบค่าเฉลี่ยของตัวมันเอง) มีข้อมูลทิศทางสำหรับทองที่มองจาก
ทองอย่างเดียวไม่เห็น (ทองตีราคาเป็น USD; USD อ่อนลงเชิงกลไกทำให้ทองถูกลงสำหรับผู้ซื้อสกุลอื่น
และมักขับเคลื่อนจาก driver เดียวกับทอง คือ real-rate expectation/risk sentiment)

**กฎ (ต่อวัน, entry คงที่ 08:00 UTC London open เพื่อแยกตัวแปร DXY ออกจากการจูน entry-timing):**
```
regime_t = sign(DXY_close_asof(t) - DXY_MA_n_asof(t))   n ∈ {20,50,100,200} วัน
  asof(t) = DXY daily bar ล่าสุดที่ "ปิดสมบูรณ์" ก่อนเวลา t จริง — ใช้ available_time =
  normalize(DXY.time_utc) + 1 วันเต็ม (DXY bar ประทับเวลา ~04:00-05:00 UTC วันที่ D
  แต่บังคับให้ใช้ได้ตั้งแต่ 00:00 UTC วันที่ D+1 เป็น safety margin กันชนกับ time-of-day
  quirk ของ Yahoo) → merge_asof(direction="backward") เข้ากับแท่ง entry ของ XAU
  regime=-1 (USD ต่ำกว่า MA, "USD อ่อน") / regime=+1 (USD สูงกว่า MA, "USD แข็ง")

direction modes (grid): regime_directional (long เมื่อ weak / short เมื่อ strong) ·
  regime_long_filter (long เฉพาะ weak, ไม่งั้น NO_TRADE) · regime_short_filter (short
  เฉพาะ strong) · always_long / always_short (baseline ไม่มี filter) ·
  inverted_directional (สลับ mapping — เช็ค asymmetry: ถ้า mapping ตรงข้ามก็ "ได้ผล"
  เหมือนกัน แปลว่าเป็น noise ไม่ใช่ macro relationship จริง)

entry:  แท่ง m15 แรกของวันที่ hour==8 minute==0 (UTC), entry price = open ของแท่งนั้น
sl:     entry -/+ k_sl * ATR14(m15) ที่คำนวณถึงแท่งก่อนหน้า (shift 1, กัน look-ahead)
tp:     entry +/- tp_r_mult * sl_distance
fix (ไม่ sweep เพื่อแยก DXY ออกมาเป็นตัวแปรเดียว): entry_hour=8, k_sl=1.5, tp_r_mult=2.0,
  atr_len=14
```

**Grid ที่ pre-register:** ma_len ∈ {20,50,100,200} × mode ∈ {regime_directional,
regime_long_filter, regime_short_filter} = 12 cells + always_long/always_short baseline
(mode-invariant) + inverted_directional ที่ ma_len=50 (asymmetry check) = 15 cells รวม

**Validation:** sacred DEV (2006–2018) → ถ้าผ่าน gate ทุก config ค่อยแตะ HOLDOUT
(2019–2026, ครั้งเดียว) → cost stress 2×/3×. เกณฑ์เดียวกับ R2/R8/R11/R14 ทุกอย่าง (PF≥1.10,
folds+≥60% บน DEV) — ไม่ผ่านไม่แตะ holdout (ประหยัดการแตะครั้งเดียว)

## ผลจริง DEV grid (2006–2018, 13y)

| ma | mode | n | win% | meanR | PF | folds+ | |
|----|------|---|------|-------|----|--------|--|
| -- | always_long | 3371 | 31.8 | -0.367 | 0.59 | 6% | fail |
| -- | always_short | 3371 | 37.9 | -0.184 | **0.77** | 29% | fail |
| 20 | regime_directional | 3349 | 35.1 | -0.266 | 0.69 | 6% | fail |
| 20 | regime_long_filter | 1655 | 32.3 | -0.351 | 0.60 | 15% | fail |
| 20 | regime_short_filter | 1694 | 37.9 | -0.183 | 0.78 | 31% | fail |
| 50 | regime_directional | 3318 | 33.9 | -0.305 | 0.65 | 10% | fail |
| 50 | regime_long_filter | 1709 | 31.1 | -0.389 | 0.57 | 11% | fail |
| 50 | regime_short_filter | 1609 | 36.9 | -0.215 | 0.74 | 26% | fail |
| 100 | regime_directional | 3267 | 34.4 | -0.293 | 0.66 | 12% | fail |
| 100 | regime_long_filter | 1761 | 31.5 | -0.382 | 0.58 | 6% | fail |
| 100 | regime_short_filter | 1506 | 37.9 | -0.190 | 0.77 | 34% | fail |
| 200 | regime_directional | 3164 | 35.5 | -0.268 | 0.69 | 18% | fail |
| 200 | regime_long_filter | 1659 | 32.0 | -0.376 | 0.58 | 10% | fail |
| 200 | regime_short_filter | 1505 | 39.3 | -0.149 | **0.81** | 33% | fail |
| 50 | inverted_directional | 3318 | 35.7 | -0.252 | 0.70 | 10% | fail |

**ทุก cell (15/15) ตกเกณฑ์** PF สูงสุดที่เจอ = 0.81 (ห่างจาก gate 1.10 มาก), folds+ 6-34%
ทุก cell (เกณฑ์ 60%), mean_r ติดลบทุก cell (-0.149 ถึง -0.389) — **gradient coherent สม่ำเสมอ**
ทั้ง grid ไม่มี cell ไหนหนีออกไปทาง PF≥1 หรือ n เล็กผิดปกติ (n อยู่ที่ 1,505-3,371 ทุก cell)
ไม่ใช่ over-selective optimum — ล้มเหลวเชิงโครงสร้างจริง ไม่ใช่ borderline

### mandatory baseline check (item 4 ในโจทย์)
- `regime_short_filter` (PF 0.74-0.81) แทบไม่ต่างจาก `always_short` baseline ไม่มี filter
  เลย (PF 0.77) — DXY regime **ไม่ได้เพิ่ม edge เหนือ short-bias เปล่าๆ** ของ entry rule เอง
  แค่ ~0-4 pts PF ต่างกัน คือ noise ระดับ sampling ไม่ใช่ signal
- `inverted_directional` (mapping สลับข้าง) ได้ PF 0.70 ใกล้เคียงกับ `regime_directional`
  ปกติ (PF 0.65) มาก — **ถ้า mapping ตรงข้ามก็ยังแย่พอๆ กัน แปลว่าไม่มี asymmetry ที่มีความหมาย**
  ทั้งสองทิศทางของ regime ไม่ได้ทำนายอะไรที่ต่างจาก noise — ยืนยันว่านี่ไม่ใช่ macro
  relationship จริงที่ operationalize ได้ด้วยกฎนี้
- entry ดิบเอง (ATR-stop London-open, ไม่มี filter ใดๆ) ก็แพ้อยู่แล้ว (always_long PF 0.59,
  always_short PF 0.77) — สอดคล้องกับ short-bias ที่เห็นใน R1 (`long-only แย่กว่า both เสมอ`)
  แต่ทั้งคู่ยังห่างเกณฑ์มาก ไม่ใช่ฐานที่ดีจะ filter อะไรต่อ

### Look-ahead check
- DXY regime ใช้ `available_time = normalize(DXY.time_utc) + 1 วัน` (safety lag เต็มวัน
  เกินกว่า timestamp ของแท่ง DXY เอง ~04:00-05:00 UTC) แล้ว `merge_asof(direction="backward")`
  เข้ากับแท่ง entry — ตรวจแล้วว่าไม่มีแท่ง DXY ไหนถูกใช้ก่อนเวลาที่ควรจะ "ปิดสมบูรณ์และสังเกตได้"
- ATR ใช้ `.shift(1)` (ถึงแท่งก่อนหน้าเท่านั้น) และ entry price = **open** ของแท่ง entry
  (ไม่ใช่ close) — ไม่มี look-ahead ภายในแท่งเดียวกัน

**ไม่แตะ sacred HOLDOUT** (ตามกฎ pre-commit เดียวกับ R11/R14 — ตายที่ DEV grid ทั้ง 15/15
cell ไม่ต้องเปลืองการแตะ holdout ครั้งเดียว) → **verdict = FALSIFIED ที่ DEV gate**

**สรุป R5:** สมมติฐานที่ 6 ของ track (หลัง R1, R2, R8, R11, R14) — **falsified เช่นกัน**
mechanism ฟังขึ้น (ทองตีราคาเป็น USD จริง) แต่ operationalize เป็นกฎ "regime filter บน
entry คงที่รายวัน" แล้วไม่มี edge เลย ทั้ง DXY-regime เองในฐานะ standalone directional
signal (regime_directional, inverted ก็แย่พอกัน) และในฐานะ filter ทับ baseline (แทบไม่ต่าง
จาก always_short เปล่า) — ห่างไกลจากประเด็นเรื่อง cost stress ด้วยซ้ำ (PF สูงสุด 0.81 <
1.10 ที่ต้นทุนฐานอยู่แล้ว ไม่ต้องรอ 2× cost มาฆ่า)
