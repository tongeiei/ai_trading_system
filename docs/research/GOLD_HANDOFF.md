# Handoff — GOLD (XAU/USD) research track

อัปเดตล่าสุด: 2026-08-30 · อ่านไฟล์นี้ก่อนเริ่มงาน gold ทุกครั้ง
(ETH/crypto track ที่รันจริงอยู่คนละเส้น — ดู `docs/HANDOFF.md`)

## เป้าหมายของ track นี้
เทรด **XAU/USD forex แยกจาก ETH โดยสิ้นเชิง** (คนละ codebase path, คนละ config,
คนละ cost model). กำลังอยู่ช่วง **หา edge ด้วย backtest** ยังไม่แตะ live/paper.

## 📋 Master table — ทุก Round (อัปเดตทุกครั้งที่มีผลใหม่)

| # | สมมติฐาน (mechanism สั้นๆ) | จุดที่ล้ม / สถานะ | Plan doc |
|---|---|---|---|
| R1 | ORB (Opening Range Breakout) | ❌ FALSIFIED — 20y ทุก config, PF ดีสุด 0.76 | — |
| R2 | ORB + pullback (fib retrace ก่อนเข้า) | ❌ FALSIFIED — ผ่าน DEV+HOLDOUT แต่พังที่ cost stress 2× + optimum วิ่งหนี (fib0.618→0.75) | `R2_HOLDOUT_PLAN.md` |
| R3 | Asian-range breakout (กล่อง 00:00-07:00 UTC → breakout London) | ⬜ ยังไม่ทำ | `XAU_REDDIT_SCOUT.md` |
| R4 | Session filter (เทรดเฉพาะ London+NY overlap) | ⬜ ยังไม่ทำ | `XAU_REDDIT_SCOUT.md` |
| R5 | DXY regime filter (sign(DXY close−MA) เป็น filter/ทิศทาง) | ❌ FALSIFIED — DEV gate 15 cells, ไม่ต่างจาก short-bias เปล่า | `XAU_REDDIT_SCOUT.md` |
| R6 | Few-trades quality filter (จำกัดไม้/สัปดาห์ เฉพาะ setup คะแนนสูงสุด) | ⬜ ยังไม่ทำ (ขึ้นกับผล R1–R4) | `XAU_REDDIT_SCOUT.md` |
| R7 | Session-open mean reversion (overnight gap) | ⬜ ยังไม่ทำ — mechanism ok แต่ spot ไม่มี gap ชัดเท่า futures | `XAU_REDDIT_SCOUT.md` |
| R8 | Post-liquidation reversal (fade capitulation candle, รอ confirm exhaustion) | ❌ FALSIFIED — DEV+HOLDOUT ทุก config, PF 0.50-0.71 | `R8_PLAN.md` |
| R9 | SMA200 bounce | ⬜ ยังไม่ทำ — mechanism อ่อน | `XAU_REDDIT_SCOUT.md` |
| R10 | Multi-TF regime meta-filter (ครอบ R อื่นทุกตัว) | ⬜ ยังไม่ทำ (= R13 คอนกรีต) | `R11_R13_PLAN.md` |
| R11 | Wick-fill / imbalance revert (ไส้ยาวผิดปกติแท่งเดียว → fade) | ❌ FALSIFIED — DEV gate 36 cells, PF ดีสุด 0.87, ไม่ต่างจาก mean-rev เปล่า | `R11_R13_PLAN.md` |
| R12 | Momentum-candle breakout (R1 + range filter) | ⬜ ยังไม่ทำ | `R11_R13_PLAN.md` |
| R13 | Multi-TF trend alignment filter (= R10) | ⬜ ยังไม่ทำ | `R11_R13_PLAN.md` |
| R14 | Fake Zone — sweep ทะลุ pivot fractal แล้วปิดกลับเข้า (liquidity sweep) | ❌ FALSIFIED — DEV gate 48 cells, PF 0.56-0.67 | `XAU_REDDIT_SCOUT.md` |
| R15 | CHoCH — close ทะลุ swing point ที่ค้ำเทรนด์เดิม (structure-based stop-run) | ❌ FALSIFIED — DEV gate 36 cells, PF ดีสุด 0.82, ไม่ดีกว่า R12/ATR-based | `R15_R17_SMC_PLAN.md` |
| R16 | Order Block — retest โซนแท่งสุดท้ายก่อน CHoCH | ⬜ ข้าม (depend on R15 ที่ fail แล้ว — นิยามจาก CHoCH โดยตรง) | `R15_R17_SMC_PLAN.md` |
| R17 | FVG — เทรดย้อนเข้าไปเติมช่องว่างราคาแบบ 3 แท่ง | ❌ FALSIFIED — DEV gate 54 cells, PF ดีสุด 0.80, แย่กว่า R11 | `R15_R17_SMC_PLAN.md` |

**นับรวม: ทดสอบครบกระบวนการแล้ว 8 ตัว (R1,R2,R5,R8,R11,R14,R15,R17) — falsified ทั้งหมด 8/8.**
**Backlog ที่ยังไม่แตะ: R3, R4, R6, R7, R9, R10/R13, R12, R16 (7 ตัว, R16 ถูก block โดย R15).**

---

## สถานะปัจจุบัน (ทำถึงไหน)
1. ✅ **ข้อมูลพร้อม** — `data/raw/XAUUSD_{1m,15m,1h}.parquet` = spot 20 ปี
   (2006–2026, Dukascopy). **ไม่มี funding** (spot ไม่ใช่ perp).
   หมายเหตุ: `XAUUSDT_*` คือ perp บน crypto exchange แค่ 8 เดือน — **อย่าปนกัน**
2. ✅ **รวบรวมสมมติฐาน (R1–R10)** จาก Reddit → `docs/research/XAU_REDDIT_SCOUT.md`
   (r/algotrading ดีสุด, r/GoldTrading private, r/XAUUSD ร้าง)
   YouTube playlist ว่างรออยู่ → `docs/research/XAU_YOUTUBE_PLAYLIST.md`
3. ✅ **Backtest harness** วางเสร็จ (แยกจาก ETH) — ดู "ไฟล์สำคัญ" ล่าง
4. ✅ **R1 (ORB) = FALSIFIED** ทุก config ทั้ง 20 ปี PF ดีสุด 0.76 (ปิดเคส)
5. ✅ **R2 (ORB+pullback) = FALSIFIED ที่ sacred holdout** (`docs/research/R2_HOLDOUT_PLAN.md`
   ทำครบตามแผน ผลอยู่ที่ `docs/research/artifacts/xau_r2_holdout.txt`).
   Frozen config §1 (OR60/fib0.618/TP1.5R/long) ผ่าน DEV gate (PF1.33, folds+63%) และผ่าน
   HOLDOUT gate จริง (PF1.23, folds+65.5%, n=845, ไม่เสื่อมจาก DEV) — **แต่ตกที่ cost stress
   2× ทั้งคู่** (DEV PF 1.33→0.39, HOLDOUT PF 1.23→0.36 — พังไม่ใช่แค่เสื่อม) **และตกที่
   sensitivity plateau check**: optimum วิ่งหนีจาก fib=0.618 ไป fib=0.75 (PF สูงขึ้นเรื่อยๆ ถึง
   1.73 ที่ fib0.75/TP2.0) ตรงกับธงแดงที่ pre-commit ไว้ใน §7 (runaway optimum = fit noise
   ไม่ใช่ mechanism) → **verdict = FAIL** (ล้มที่ gate item 2 และ 5) ปิดเคส R2 เหมือน R1
6. ✅ **สร้าง 2 subagents** ไว้ช่วยงาน (ดูล่าง) — ยังไม่ได้ลองรันจริง
7. ✅ **R8 (post-liquidation reversal) = FALSIFIED** ทำครบตามแผน (`docs/research/R8_PLAN.md`,
   ผลอยู่ที่ `docs/research/artifacts/xau_r8_liquidation_reversal.txt`). กฎที่ pre-register
   (fade capitulation candle แล้ว**รอ confirm exhaustion**ก่อนเข้า) ล้มเหลวทุก config ที่ลอง —
   3y smoke, 20y baseline, sensitivity grid 13 cells (k_capit 2.0-3.0 × tp 1.0-2.0 × M{1,3} ×
   dir{both,long}), sacred DEV (2006-2018), sacred HOLDOUT (2019-2026) — PF 0.50-0.71 ทุกจุด
   (เกณฑ์ 1.10), folds+ 5-21% (เกณฑ์ 60%), ติดลบทุกปีเกือบหมดทั้ง DEV และ holdout (ไม่ใช่แค่
   2-3 ปีแย่ — แพ้ทุก regime) → **ตก gate item 1,3,4,5** (ผ่านแค่ sample size) = FAIL ชัดเจน
   ไม่ใช่ borderline แบบ R2
   **ข้อสังเกตสำคัญ (ยังไม่ใช่ edge)**: baseline ที่ไม่ pre-register — fade แท่ง capitulation
   ทันทีโดย**ไม่รอ confirm** — กลับแรงมาก (PF 2.2-2.4, folds+ 94-98%, ทั้ง DEV และ 20y) คือ
   ตรงข้ามกับ mechanism story ของ R8 เป๊ะ (confirm ทำให้แย่ลง ไม่ใช่ดีขึ้น) — นี่คือธงแดงที่
   R8_PLAN §6 เตือนไว้แล้ว ("knife-catching") ยังไม่ผ่าน sensitivity/holdout/cost-stress ใดๆ
   **ห้ามเรียกว่า edge** ต้องมี falsification plan ของตัวเองก่อน (เหมือน R2 ที่ผ่าน gate ในตอน
   แรกแต่พังทีหลัง) — บันทึกไว้เป็น candidate สำหรับ backlog ถ้าจะทำต่อ

8. ✅ **R11 (wick-fill / imbalance revert) = FALSIFIED ที่ DEV grid** (`docs/research/R11_R13_PLAN.md`
   R11 section, ผลอยู่ที่ `docs/research/artifacts/xau_r11_wick_fill.txt`). Grid pre-registered
   36 cells (k_wick∈{1.0,1.5,2.0} × body_frac∈{0.3,0.5} × tp_mode∈{wick_fill,1.0R,1.5R} ×
   direction∈{both,long}) บน DEV (2006-2018, 13y) — **ทุก cell PF<1.10 และ mean_r ติดลบหมด**
   (PF ช่วง 0.14-0.87). cell ที่ดีที่สุด (PF 0.87, k_wick=2.0/body0.5/tp1.0R/long) มี n=77
   และ folds_counted=0 — ตรงกับธงแดงที่ pre-commit ไว้ ("optimum วิ่งไป k_wick สุดขอบจนไม้เหลือ
   น้อย = over-selective ไม่ใช่ edge") **mandatory baseline** (mean-reversion เปล่า ไม่มี
   wick/body filter, session/SL/TP เดียวกัน) ก็ติดลบเหมือนกัน (PF 0.22-0.74) — ไส้ไม่ได้เพิ่ม
   edge เหนือ mean-reversion ทั่วไปเลย ตรงกับธงแดงบังคับใน §6 พอดี → **ตก gate item 1 (DEV WFO
   gate) ตั้งแต่ต้น ทุก config** ไม่ได้แตะ **sacred holdout** และ **cost stress** เลย (หลักการ
   เดียวกับที่บันทึกไว้ข้อ 4 ล่าง — ไม่ต้องรอ holdout ถ้าตายไปแล้วตั้งแต่ DEV gate)
   verdict = FAIL ชัดเจน ไม่ใช่ borderline

9. ✅ **R14 (Fake Zone / level-anchored liquidity sweep) = FALSIFIED ที่ DEV gate**
   (`docs/research/XAU_REDDIT_SCOUT.md` ส่วน "รอบ Facebook", ผลอยู่ที่
   `docs/research/artifacts/xau_r14_fake_zone.txt`). เดิม plan มีเงื่อนไข "ต้องชนะ R8/R11"
   ก่อนจะเริ่มทำ — แต่เนื่องจาก R8/R11 ล้มเหลวเอง (net-losing) เงื่อนไขนี้ไม่มีความหมาย
   (ชนะกลยุทธ์ที่ขาดทุนพิสูจน์อะไรไม่ได้) จึงตัดทิ้งตามคำสั่งผู้ใช้ แล้วรัน R14 ผ่าน pipeline
   มาตรฐานเต็มรูปแบบแทน (DEV grid → sacred holdout → cost stress, เกณฑ์เดียวกับ R2/R8/R11
   ไม่มีข้อยกเว้น) — mechanism: sweep ทะลุ pivot fractal (w แท่งซ้าย/ขวายืนยัน, ไม่มี
   look-ahead) แล้ว**ปิดกลับเข้า**ภายใน N แท่ง = fade "สวน" ทิศทาง
   **DEV grid 48 cells (w∈{3,5} × b_break∈{0.25,0.5} × N∈{1,3} × tp_r_mult∈{1.0,1.5,2.0} ×
   direction∈{both,long}) บน 2006–2018 (13y) → PF 0.56–0.67 ทุก cell (เกณฑ์ 1.10), folds+
   0–18% ทุก cell (เกณฑ์ 60%), mean_r ติดลบทุก cell** — gradient coherent สม่ำเสมอ ไม่มี
   cell ไหนหนีออกจากกลุ่ม (ไม่ใช่ over-selective optimum แบบ R2/R11) คือความล้มเหลวเชิง
   โครงสร้างจริง ไม่ใช่ borderline **ไม่ได้แตะ sacred holdout** (ตายที่ DEV แล้ว ตามกฎ
   pre-commit ไม่เปลืองการแตะ holdout ครั้งเดียว) → **ตก gate item 1 ตั้งแต่ต้น** verdict =
   FALSIFIED ชัดเจน เหมือน R11

   **สรุปภาพรวม track (สำคัญ, ต้องพูดตรงๆ):** ทดสอบมาแล้ว 5 สมมติฐานเชิงกลไก (R1, R2, R8,
   R11, R14) — **falsified ทั้งหมด 5/5** (R1 ล้มตั้งแต่ 20y baseline, R2 ผ่าน DEV+HOLDOUT แต่
   พังที่ cost stress 2×, R8/R11/R14 ล้มตั้งแต่ DEV gate). ทุกตัวเป็น mechanical price-action
   pattern (ORB, wick-fill, candle-fade, liquidity-sweep) บน timeframe m15 ของ spot gold —
   สิ่งที่ implied คือ pattern ประเภท "เห็นด้วยตาเปล่าง่ายๆ" พวกนี้ **ไม่รอด cost model ที่
   สมจริงบน spot gold** (spread+slippage แม้จะเป็น optimistic floor) แม้จะมี mechanism story
   ที่ฟังขึ้น (forced payer จริง) ก็ตาม — น่าจะเป็นเพราะกลไกเหล่านี้ arbitraged away ไปนานแล้ว
   ในตลาดสภาพคล่องสูงแบบ gold spot, หรือ mechanism มีจริงแต่ edge size เล็กกว่า cost เสมอ.
   ข้อเสนอ: **เปลี่ยนทิศ** ไปทาง R5 (DXY correlation, ต้องหา data เพิ่ม) หรือ R7/R9 (session
   gap / SMA200 bounce) แต่ **เตรียมใจว่าอาจ falsified เหมือนกัน**, หรือพิจารณาว่า track นี้
   อาจต้องการ timeframe/data ที่ต่างไปเลย (เช่น cross-asset, macro-driven signal) แทน pure
   price-action pattern — 5/5 falsified ไม่ใช่เรื่องบังเอิญ

10. ✅ **R5 (DXY regime filter) = FALSIFIED ที่ DEV gate** (`docs/research/XAU_REDDIT_SCOUT.md`
    ส่วน "ผลทดสอบ R5", ผลอยู่ที่ `docs/research/artifacts/xau_r5_dxy_filter.txt`). data blocker
    เดิม (ไม่มี DXY history) แก้แล้ว — ได้ `data/raw/DXY_daily.parquet` (Yahoo DX-Y.NYB, 2006-2026,
    ครอบ 20y เดียวกับ XAU เต็ม). Rule pre-register เอง (ไม่มี plan doc แยก เพราะ scope เล็ก เขียน
    ในไฟล์ scout แทน): regime = sign(DXY_close − DXY_MA_n) รายวัน (n∈{20,50,100,200}), ใช้
    DXY close วันก่อนหน้าแบบมี safety lag เต็มวัน (กัน look-ahead แน่นอน) เป็น filter/direction
    บน entry คงที่รายวัน (ATR-stop ที่ London open 08:00 UTC, ไม่ sweep entry mechanics เพื่อ
    แยกตัวแปร DXY ออกมาให้ชัด) — **DEV grid 15 cells (2006–2018) ตกทุก cell**: PF 0.57–0.81
    (เกณฑ์ 1.10), folds+ 6–34% (เกณฑ์ 60%), mean_r ติดลบทุก cell, gradient coherent ไม่มี
    runaway optimum. **mandatory baseline**: `regime_short_filter` (PF 0.74-0.81) แทบไม่ต่างจาก
    `always_short` ไม่มี filter เลย (PF 0.77) — DXY ไม่ได้เพิ่ม edge เหนือ short-bias เปล่าของ
    entry rule เอง. **asymmetry check**: `inverted_directional` (สลับ mapping) ได้ PF 0.70
    ใกล้เคียง `regime_directional` ปกติ (PF 0.65) มาก — ไม่มี asymmetry ที่มีความหมาย ยืนยันว่า
    ไม่ใช่ macro relationship ที่ operationalize ได้ด้วยกฎนี้ **ไม่แตะ sacred holdout** (ตายที่
    DEV แล้ว) → **verdict = FALSIFIED ชัดเจน** — **สรุปคือ 6/6 hypothesis ที่ทดสอบมาล้มเหลวหมด**
    (R1, R2, R8, R11, R14, R5) ครอบคลุมทั้ง pure price-action pattern และ cross-asset macro
    filter — เป็นผลลัพธ์ระดับ track ที่ชัดเจนแล้วว่า **naive rule-based approach บน XAU/USD
    spot (ไม่ว่าจะเป็น pattern เดี่ยวหรือ regime filter ง่ายๆ) ไม่มี edge ที่รอด cost model
    ได้เลยจนถึงตอนนี้**

11. ✅ **R15 (CHoCH) = FALSIFIED ที่ DEV gate** (`docs/research/R15_R17_SMC_PLAN.md`, ผลอยู่ที่
    `docs/research/artifacts/xau_r15_choch.txt`). state machine
    ของ market structure (swing high/low fractal ยืนยันด้วย w แท่ง, trend UP/DOWN/UNKNOWN,
    CHoCH = close ทะลุ swing ที่ค้ำเทรนด์เดิม, cooldown กัน whipsaw) — **DEV grid 36 cells
    (w∈{3,5,8} × k_range∈{1.5,2.5} × tp_r_mult∈{1.0,1.5,2.0} × direction∈{both,long}) บน
    2006-2018 → PF 0.65-0.82 ทุก cell (เกณฑ์ 1.10), folds+ 4-40% (เกณฑ์ 60%), mean_r ติดลบ
    ทุก cell**. Gradient coherent (k_range กว้างขึ้น + long-only ดีขึ้นต่อเนื่อง ไม่กระโดด)
    ไม่มี over-selective optimum. **mandatory baseline R12** (ATR-range breakout, falsified
    เดิม PF~0.70-0.76): CHoCH (PF 0.65-0.82) อยู่ในช่วงเดียวกัน ไม่ดีกว่าอย่างมีนัยยะ → ยืนยัน
    kill criteria ที่ pre-commit ไว้ว่า "นิยาม trigger จาก swing structure ไม่เพิ่ม edge เหนือ
    นิยามจาก ATR" **ไม่แตะ sacred holdout** (ตายที่ DEV แล้ว) → verdict = FALSIFIED ชัดเจน
    **ผลกระทบ R16**: ข้ามไปเลยตามเงื่อนไขที่ตั้งไว้ล่วงหน้าในแผนเอง (R16 นิยามจาก CHoCH ของ R15
    โดยตรง ถ้า R15 ไม่มีนัยสำคัญทางสถิติ การกรองด้วย OB retest บนสัญญาณที่ไม่มี edge ไม่มี
    ความหมาย)

12. ✅ **R17 (FVG) = FALSIFIED ที่ DEV gate** (`docs/research/R15_R17_SMC_PLAN.md`, ผลอยู่ที่
    `docs/research/artifacts/xau_r17_fvg.txt`). 3-candle gap
    มาตรฐาน (`low[i] > high[i-2]` หรือ mirror) + gap-size filter เทียบ ATR + retest ภายใน N
    แท่ง — **DEV grid 54 cells (k_gap∈{0.3,0.5,0.8} × N∈{5,10,20} × tp_r_mult∈{1.0,1.5,2.0} ×
    direction∈{both,long}) บน 2006-2018 → PF 0.48-0.80 ทุก cell (เกณฑ์ 1.10), folds+ 2-29%
    (เกณฑ์ 60%), mean_r ติดลบทุก cell (-0.09 ถึง -0.38R), n สูงมาก (3,300-10,300/config) —
    ไม่ใช่ปัญหา sample size**. Gradient monotonic ไปทาง k_gap ใหญ่ (0.8) ดีขึ้นต่อเนื่องแต่จุด
    ที่ดีที่สุดในกริด (PF 0.80) ยังห่างจากเกณฑ์มาก ไม่ใช่ borderline ที่ต้องขยาย grid ต่อ.
    **mandatory baseline R11** (wick-fill, falsified เดิม PF ดีสุด 0.87): R17 **แย่กว่า R11
    ในทุก config** (ดีสุด 0.80 < 0.87) → ยืนยัน kill criteria "การเติม imbalance ไม่มี edge
    เหนือ mean-reversion เปล่า" ไม่ต้องรอ mean-rev baseline เพิ่มเพราะแพ้ทั้งตัวที่แพ้ baseline
    ไปแล้ว **ไม่แตะ sacred holdout** → verdict = FALSIFIED ชัดเจน

    **สรุปภาพรวม track (อัปเดต 2026-08-30):** ทดสอบครบกระบวนการแล้ว 8 สมมติฐาน (R1, R2, R5, R8,
    R11, R14, R15, R17) — **falsified ทั้งหมด 8/8**. รอบ SMC (R15/R17) ยืนยันซ้ำ pattern เดิม:
    price-action pattern ที่มองด้วยตาบน chart (ไม่ว่าจะเป็น breakout, wick, sweep, structure
    break, หรือ gap) ไม่มี edge เหนือ cost model สมจริงบน spot gold m15 ดู master table ด้านบน
    สำหรับสถานะทุก round รวม backlog

## 👉 งานถัดไป (ค้างไว้ตรงนี้)
R2, R5, R8, R11, R14, R15, R17 ปิดเคสแล้ว (falsified ทั้งเจ็ด — ดูข้างบน/master table). ต่อไปใน
ลำดับความสำคัญ backlog: R12 (momentum-candle breakout, R1+range filter) หรือ R13/R10 (multi-TF
filter, ทำเป็น infra ครอบทุก R) ตามลำดับใน `docs/research/R11_R13_PLAN.md`. อื่นๆ:
1. backlog ที่เหลือ: R7 (overnight/session-open mean reversion, mechanism ok แต่ spot ไม่มี gap
   ชัดเท่า futures), R9 (SMA200 bounce, mechanism อ่อน) — ดู `docs/research/XAU_REDDIT_SCOUT.md`
2. R5 ทำเสร็จแล้ว (falsified) — DXY data พร้อมใช้ที่ `data/raw/DXY_daily.parquet` ถ้าจะใช้ต่อ
   ในบริบทอื่น (เช่น R10 regime-meta-filter ครอบ R อื่น)
3. ถ้าจะสานต่อ "naive capitulation fade" ที่ดูแรงจาก R8 (ดูข้อ 7 บน) — ต้องเขียน plan ใหม่
   แยกต่างหาก (rule spec + param grid + sacred DEV/HOLDOUT ที่ยังไม่แตะ + cost stress + เช็ค
   look-ahead/quantization ให้ละเอียด) ก่อนจะเชื่อเลข ห้ามข้ามขั้นตอนแม้ตัวเลขจะดูดี
4. บทเรียนจาก R2: cost model ใน `gold_spec.yaml` (spread1.5+slip1.0bps) เป็น "optimistic floor"
   จริงจัง — edge ที่ผ่าน gate ที่ base cost แต่ hair-trigger พังที่ 2× ต้องเช็ค cost stress
   **ก่อน** จะไปถึง holdout เสมอ (ประหยัดเวลา ไม่ต้องรอ holdout ถ้า cost stress ตายไปแล้ว)

## ไฟล์สำคัญ
- `config/gold_spec.yaml` — instrument + cost (spread-based, no funding) + gate
- `src/backtest/gold_harness.py` — โครงหลัก. `run_gold_backtest(signal_fn, spec, start, end)`
  - **SignalFn contract:** คืน df คอลัมน์ `time_utc, close(=entry price), action
    (LONG/SHORT/NO_TRADE), sl_price, tp_price, sl_distance(>0)`
  - reuse `build_features` / `triple_barrier` / `bootstrap` เดิม (ไม่ fork core)
  - **gate:** net PF ≥ 1.10 **และ** ≥60% ของ quarterly folds เป็นบวก
- `src/strategy/gold_orb.py` (R1) · `src/strategy/gold_orb_pullback.py` (R2)
  · `src/strategy/gold_r8_liquidation_reversal.py` (R8) · `src/strategy/gold_r11_wick_fill.py` (R11)
  · `src/strategy/gold_r14_fake_zone.py` (R14) · `src/strategy/gold_r5_dxy_filter.py` (R5)
  · `src/strategy/gold_r15_choch.py` (R15, ยังมี `compute_choch_events()` แยกไว้ให้ R16 reuse
    ถ้าจะสานต่อในอนาคต) · `src/strategy/gold_r17_fvg.py` (R17)
- `scripts/run_gold_r1_orb.py` · `scripts/run_gold_r2_orb_pullback.py` · `scripts/run_gold_r2_holdout.py`
  · `scripts/run_gold_r8_liquidation_reversal.py` · `scripts/run_gold_r8_holdout.py`
  · `scripts/run_gold_r11_wick_fill.py` · `scripts/run_gold_r14_fake_zone.py`
  · `scripts/run_gold_r5_dxy_filter.py` · `scripts/run_gold_backtest_smoke.py`
  · `scripts/run_gold_r15_choch.py` · `scripts/run_gold_r17_fvg.py`
- ผล: `docs/research/artifacts/xau_r1_orb_sweep.txt`, `..._r2_orb_pullback_sweep.txt`,
  `..._r2_holdout.txt`, `..._r8_liquidation_reversal.txt`, `..._r11_wick_fill.txt`,
  `..._r14_fake_zone.txt`, `..._r5_dxy_filter.txt`, `..._r15_choch.txt`, `..._r17_fvg.txt`
- `data/raw/DXY_daily.parquet` — DXY spot daily 2006-2026 (Yahoo DX-Y.NYB), ใช้กับ R5

## วิธีรัน
```bash
PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r2_orb_pullback.py         # 3y เร็ว
PYTHONPATH=. .venv/bin/python -u scripts/run_gold_r2_orb_pullback.py --full  # 20y + sweep
```
labeling ~30s/config บน M1 7.4M แถว → sweep ยาวให้รัน background แล้วรอ

## Subagents (project-level `.claude/agents/`)
- **gold-research-plan** (Opus 4.8) — ไอเดียดิบ → research plan ที่ falsifiable
- **gold-strategy-coder** (Sonnet 5) — plan → signal_fn + รัน backtest + รายงานผล
- ⚠️ agent picker อาจต้องเปิด session ใหม่ถึงจะเห็น (roster โหลดตอนเริ่ม session)

## หลักการที่ยึด (อย่าลืม)
- **"an edge is a reason someone pays you"** — เริ่มจาก mechanism (ใครถูกบังคับให้จ่าย)
  ไม่ใช่ indicator. RSI<30=bullish ตกเกณฑ์
- **Reddit/YouTube = แหล่งสมมติฐาน ไม่ใช่หลักฐาน** (survivorship + ขายคอร์ส)
- **sweep winner = in-sample** ห้ามเรียกว่า edge จนกว่าจะผ่าน holdout + cost stress
- gradient ที่ coherent น่าเชื่อกว่า cell เดียวที่ชนะ
- ยังไม่ commit เข้า git (ทั้ง track นี้เป็น untracked ทั้งหมด ณ ตอน handoff)
