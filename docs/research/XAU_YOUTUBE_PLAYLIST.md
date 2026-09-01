# XAU/USD — YouTube Playlist & Strategy Notes

แหล่งรวมคลิป YouTube สำหรับศึกษา strategy / edge ของ gold (XAU/USD)
แยกออกจาก ETH โดยสิ้นเชิง — ห้ามเอา parameter ข้ามตลาด

> **หลักการใช้ไฟล์นี้:** YouTube = แหล่ง *ตั้งสมมติฐาน (hypothesis)* เท่านั้น
> ไม่ใช่ strategy ที่ก็อปมาใช้ได้เลย ทุกไอเดียต้องผ่าน backtest บนข้อมูลตัวเอง
> (รวม spread + slippage + commission) ก่อน แล้วค่อย paper trade → live

---

## วิธีเก็บ (template ต่อ 1 คลิป)

คัดลอก block ด้านล่างไปเติม:

```
### [ชื่อคลิป]
- **URL:**
- **ช่อง / ผู้พูด:**
- **ความยาว / วันที่ดู:**
- **แนวคิดหลัก (concept):**
- **สมมติฐานที่ backtest ได้ (เขียนเป็นกฎ if/then):**
- **ต้องใช้ข้อมูลอะไร (DXY? session? news?):**
- **ธงแดง (curve-fit? ขายคอร์ส? ไม่มี out-of-sample?):**
- **สถานะ:** ⬜ ยังไม่ทดสอบ / 🔬 กำลัง backtest / ✅ ผ่าน / ❌ ตก
```

---

## Playlist

### (สอนเทรดทอง) เจอกราฟไหนก็เทรดได้ | จากเทรดไม่เป็น รับจบให้ ใน 40 นาที
- **URL:** https://youtu.be/rtABo4mPxdM
- **ช่อง / ผู้พูด:** MJ OPO — "โค้ชปอ" (สอนเทรดทอง)
- **ความยาว / วันที่ดู:** ~40 นาที · อัปโหลด 2026-02-25 · ดู 2026-08-27 (ผ่าน transcript อัตโนมัติ)
- **แนวคิดหลัก (concept):** discretionary price-action ล้วน. Top-down analysis
  (Day → 4h → 1h → 30m) ให้ทุก TF เห็นเทรนด์ตรงกันก่อนเข้า; เทรดตาม "โครงสร้าง"
  เทรนด์ (แนวรับ/แนวต้าน — เวลาเด้งขึ้น "ห้ามทะลุแนวต้านก่อนหน้า" ถึงจะลงต่อได้,
  ถ้าทะลุ = โครงสร้างเปลี่ยน 70–80%); เป้าหมายราคาคือ **"wick fill / week field"** =
  ราคาย้อนไปเติมไส้เทียน/โซนที่ทิ้งไว้; ยืนยันด้วยขนาดแท่ง/วอลุ่ม (แท่งใหญ่ = แรงพอ,
  แท่งเล็ก = ยังไม่คอนเฟิร์ม อย่าเพิ่งเข้า); เข้าเมื่อแท่งปิดพ้นแนวรับ/แนวต้านตามทิศเทรนด์,
  SL ปลายไส้แท่งก่อนหน้า, TP ที่ wick fill/โซนถัดไป; risk management แบบดุลยพินิจ
  (ออก 50% / เลื่อน SL เมื่อราคาเด้งกลับมาชนหน้าไม้)
- **สมมติฐานที่ backtest ได้ (เขียนเป็นกฎ if/then):** ดูตาราง backlog R11–R13 ล่าง
- **ต้องใช้ข้อมูลอะไร:** XAUUSD_15m/1h เท่านั้น (ไม่ต้อง DXY/news). ทุกกฎอิงราคา+โครงสร้าง
- **ธงแดง (curve-fit? ขายคอร์ส? ไม่มี out-of-sample?):**
  🚩 **ขายคอร์สชัดเจน** (~นาที 30: ค่าเรียน 3,000–5,000 บาท, "แค่วันเดียวก็คุ้ม", ทักไลน์ "1449")
  🚩 **hindsight ล้วน** — replay bar ใน backtest tool แล้วเล่าย้อนหลัง (เขาพูดเอง "มโนเอา")
  🚩 ไม่มีกฎ deterministic — "ดู TF ไหนแล้วง่ายก็ดู TF นั้น", ตีโซน/เลือกไส้ด้วยตา = ไม่ reproducible
  🚩 risk 5%/ไม้ (เขาเองบอกควร ≤2% แต่ทองล็อตไม่พอเลยดัน 5%) = reckless
  🚩 ตัวอย่างเทรดแรกในคลิป **ขาดทุน** (โดน SL) — เขายอมรับเอง; เทรดที่สองปิดกำไรบางส่วน
- **สถานะ:** 🔬 กลั่นเป็น R11–R13 แล้ว → ส่งต่อ backtest (ตัวคลิป = แหล่งสมมติฐาน ไม่ใช่หลักฐาน)

---

## หมวดหมู่ที่อยากได้ (ช่วยจัดโฟกัสตอนหาคลิป)

- [ ] **Macro drivers** — gold vs DXY / real yields / risk sentiment
- [ ] **Session timing** — London / NY overlap, Asian range
- [ ] **News events** — NFP, CPI, FOMC ทำอะไรกับ gold
- [x] **Price action / structure** — SMC, order blocks, liquidity (ระวัง hype มากสุด) ← คลิปนี้อยู่หมวดนี้
- [ ] **Indicator-based** — MA/RSI/ATR based systems
- [ ] **Risk & position sizing** — เฉพาะ gold volatility

---

## สมมติฐานที่กลั่นออกมาแล้ว (backlog สำหรับ backtest)

> กลั่นจากคลิป rtABo4mPxdM. เขียนให้ deterministic (ตัดดุลยพินิจออกให้หมด) และผูกกับ
> **mechanism (ใครจ่าย)** ตามมาตรฐาน track นี้. ตัวคลิปไม่ใช่หลักฐาน — ต้อง falsify เอง

| # | สมมติฐาน (กฎ if/then) | mechanism (ใครจ่าย) | ข้อมูล | สถานะ |
|---|---|---|---|---|
| R11 | **Wick-fill / imbalance revert:** หลังแท่ง m15/h1 ทิ้ง "ไส้ยาว" ผิดปกติ (wick length > k×ATR, body เล็ก) → เข้าในทิศ **ย้อนกลับไปเติมไส้**, TP = ปลายไส้ (ราคาเปิดโซนที่ทิ้งไว้), SL อีกฝั่งของแท่ง, timeout N แท่ง | resting liquidity ที่ปลายไส้ยังไม่ถูก fill + คนที่ไล่ราคาช่วงพุ่งแรงถูก trap ต้องคืน | XAUUSD_15m/1h (ATR, wick) | ❌ **FALSIFIED** (2026-08-27, DEV grid 36 cells ทุกจุด PF<1.10 ทุก mean_r ติดลบ, ดี ที่สุด PF 0.87 แต่ n=77/folds+0% = over-selective; baseline mean-rev เปล่าก็ติดลบเหมือนกัน PF 0.22-0.74 = ไส้ไม่ได้เพิ่ม edge เลย; ไม่แตะ sacred holdout เพราะไม่ผ่าน DEV gate ตั้งแต่แรก) → `docs/research/artifacts/xau_r11_wick_fill.txt` |
| R12 | **Momentum-candle breakout (R1 + range filter):** เหมือน ORB/level-break แต่เข้าเฉพาะเมื่อแท่งที่ทะลุ **range > k×ATR(น)** และ > แท่งก่อนหน้า (เขาเรียก "รถบรรทุก 120 กม/ชม") — ตัด false-breakout แท่งเล็ก | momentum ต่อเนื่องจาก forced fills/stop-run หลัง break แรง | XAUUSD_15m (ATR, range) | ⬜ |
| R13 | **Multi-TF trend alignment filter (meta):** เปิดสัญญาณ (R1/R2/R11/R12) เฉพาะเมื่อเทรนด์ h1/h4/daily (เช่น slope ของ MA หรือ HH/HL) **ชี้ทางเดียวกัน** เทียบกับไม่กรอง — expectancy ต่างมั้ย | ตัดการเทรดสวน HTF (จุดที่เขาบอก "เซล 5 นาทีตรงปลายไส้ h1") | XAUUSD_15m/1h + daily resample | ⬜ |

**หมายเหตุเชิงกลยุทธ์:** R13 ทับกับ R10 (regime filter) ในไฟล์ Reddit — ควรทำเป็น meta-filter
ตัวเดียวใช้ครอบทุก R. R12 คือ R1 (falsified) + range filter — ค่าที่ได้คือเช็คว่า filter นี้กู้ R1
ได้มั้ย (ถ้าไม่ = ยืนยันซ้ำว่า breakout ทองไม่มี edge). R11 (wick-fill) เป็นตัวที่ mechanism
อิสระจากของเดิมมากสุด → น่าลองสุดในสามตัว แต่ระวัง: "fill ไส้" อาจเป็น artifact ของ mean-reversion
ทั่วไป ต้องมี baseline เทียบ

_แหล่ง: YouTube (โค้ชปอ / MJ OPO). สรุปเป็นแนวคิด ไม่คัดลอก verbatim. คอร์สขาย = ทิ้ง เก็บแค่โครงกฎ_
</content>
