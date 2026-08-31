# Phase 7 — Max-Hold Extension (แผนถัดจาก Phase 6, track: ETH live)

เขียน: 2026-08-31 · track: ETH/USDT perp (live paper-trading) · อ่าน
`docs/research/ETH_V1_RESEARCH_REPORT.md` Phase 6 ก่อน

> ที่มา: Phase 6 (research_phase6_duration_analysis.py) วัด mark-to-market R
> ของ 1,412 V0-baseline trades ไว้*ก่อน*จะรู้ว่า EV gate จะปฏิเสธ ETH เกือบ
> ทุกสัญญาณ (docs/research/BTC_EDGE_SEARCH.md Round 6 addendum, 2026-08-28/30)
> — Phase 7 ไม่ใช่การย้อนไปหาข้ออ้างให้ ETH ผ่าน gate มันเป็นสมมติฐานที่
> Phase 6 ชี้เป้าไว้ล่วงหน้าแล้วยังไม่เคยทดสอบ

---

## 1. Mechanism (ทำไมถึงคาดว่าจะดีขึ้น — ไม่ใช่แค่ "ลองดู")

นี่ไม่ใช่กลไกตลาดแบบ "ใครถูกบังคับจ่าย" — มันคือสมมติฐานเรื่อง**ข้อผิดพลาด
ของ execution spec**: กฎ exit ของเราเองอาจตัดวิทยานิพนธ์การเทรดทิ้งก่อนที่
มันจะคลี่คลาย

Phase 6 วัดไว้บน 1,412 trade เดียวกันที่ใช้เป็น control ทั้งรายงาน:
- Mean mark-to-market R ไต่ขึ้นแบบ **monotonic ไม่ plateau** ตลอด 12h:
  +0.0015R (1h) → +0.0270R (2h) → +0.0683R (4h) → +0.1103R (8h) →
  +0.1608R (12h, final)
- ที่ 4h มีแค่ 40.7% ของไม้ที่คลี่คลายแล้ว (TP/SL touched)
- **20.9% ของไม้โดน timeout บังคับปิด** ด้วย MFE เฉลี่ย +1.12R ที่ยังไม่
  เคยแตะ (mean MAE เพียง -0.61R) — คือไม้ที่กำลังมีทิศทางบวกตอนถูกตัด
- รายงานเขียนไว้ตรงๆ ว่า "if anything the directional evidence favors...
  investigating a *longer* window as a separate, properly-tested
  hypothesis"

ถ้า 12h barrier คือข้อจำกัดที่ผูกอยู่จริง (binding constraint) การยืดมัน
ควรเพิ่ม net expectancy กลไกที่ต่อสู้กับสมมตินี้ถูกใส่ในโมเดลต้นทุนอยู่แล้ว
โดยไม่ต้องเพิ่มอะไรพิเศษ: `funding_cost_r` คิดจาก entry→exit จริง (ยิ่ง hold
ยาว ยิ่งจ่าย funding มากขึ้น ทุก 8h) และ hold ยาวขึ้น = เสี่ยง regime พลิก
ระหว่างถือมากขึ้น

## 2. Grid ที่ pre-register (มิติเดียว)

```
max_hold ∈ {12h (control, = สถานะปัจจุบัน), 18h, 24h, 36h, 48h}
```

ล็อกทุกอย่างอื่น: `ADX=35`, `SL=2.5×ATR`, `TP=2R`, entry trigger (EMA20
pullback cross) — **ห้ามแตะพารามิเตอร์อื่นระหว่างการศึกษานี้** ถ้า 5 จุดนี้
ไม่พอสรุป ให้เขียนแผนใหม่แยกต่างหาก ไม่ขยาย grid นี้กลางคัน (บทเรียนจาก R11:
grid ที่ขยายหลังเห็นผลคือ fitting)

## 3. Data & sacred split

- Data: `ETHUSDT_{15m,1h,1m}.parquet`, `ETHUSDT_USDT_funding.parquet`
  (ของเดิมทั้งหมด ไม่ต้อง fetch ใหม่)
- **DEV**: จุดเริ่มข้อมูล (warm-up แล้ว) – 2024-12-31
- **HOLDOUT**: 2025-01-01 เป็นต้นไป (ตรงกับ `HOLDOUT_START` ที่
  `research_xrp_vetting.py` ใช้ — sacred, แตะครั้งเดียว ต่อเมื่อ DEV +
  cost-stress ผ่านแล้วเท่านั้น)
- Embargo 12h ที่ fold boundary ตามที่ `eth_walkforward_multifold.py` ทำอยู่
  แล้ว — **ต้องขยาย embargo ให้เท่ากับ max_hold ที่กำลังทดสอบ** ไม่ใช่ 12h
  คงที่ (มิฉะนั้น trade ที่ hold ยาวจะรั่วข้าม fold boundary)

## 4. Gate (มาตรฐานเดิม ไม่ลดเกณฑ์ไม่ว่า max_hold จะเท่าไหร่)

1. Net PF ≥ 1.10 **และ** ≥60% ของ quarterly WFO fold เป็นบวก (DEV)
2. Bootstrap p < 0.05 บน mean net_r (HOLDOUT)
3. **Cost stress 2× ต้องผ่านก่อนแตะ holdout** (เช็ค DEV ก่อน ประหยัดเวลาถ้าตาย
   ที่ cost — บทเรียนจาก R2 §4 ใน GOLD_HANDOFF)
4. Gradient coherent ระหว่าง 5 จุด (12h→48h) ไม่มี cell เดียวที่กระโดด
5. **EV-gate relevance check (เกณฑ์ใหม่เฉพาะ Phase 7):** recompute
   `win_rate`/`avg_win_r`/`avg_loss_r` จาก CAL fold ของ max_hold ที่ชนะ
   (วิธีเดียวกับที่ `src/live/ev_estimate.py` SYMBOL_STATS ใช้) แล้วคำนวณ
   `ev_r` จริงที่ `sl_distance` เฉลี่ยที่เกิดขึ้นจริง — **ต้อง ≥ 0.15R
   ไม่งั้นถือว่าไม่สำเร็จ ต่อให้ PF/WFO ดีขึ้นก็ตาม** เป้าหมายของ Phase 7 คือ
   ทำให้ทุนกลับมาทำงาน ไม่ใช่แค่ทำให้ตัวเลข dashboard สวยขึ้น

## 5. Kill criteria (ลั่นไว้ก่อนเห็นผล — ห้ามเลื่อนหลังเห็นผล)

- **Runaway optimum → REJECT**: กลไกทำนาย plateau (พอไม้ส่วนใหญ่คลี่คลายแล้ว
  กำไรส่วนเพิ่มต้องแบนลง) ถ้า PF/expectancy ยังดีขึ้นต่อเนื่องไม่หยุดถึง 48h
  โดยไม่มีท่าทีอิ่มตัว = นี่กลายเป็นกลยุทธ์ trend-following ไม่มี time-stop
  ซึ่งเป็นสมมติฐานคนละตัว ยังไม่ผ่าน validation ของมันเอง → REJECT ทั้งชุด
  เหมือนที่เกิดกับ gold R2 (optimum วิ่งหนีจาก fib0.618→0.75)
- **Resolution-rate check**: % ไม้ที่จบด้วย TP/SL (ไม่ใช่ timeout) ต้องไต่
  เข้าใกล้ ~95%+ เมื่อ max_hold ยาวขึ้น ถ้า timeout% ยังสูงอยู่ที่ 48h
  แปลว่า barrier 12h ไม่เคยเป็นข้อจำกัดที่ผูกอยู่จริง (สมมติฐานผิดตั้งแต่ต้น)
- กำไรกระจุกอยู่ฝั่งเดียว (long-only หรือ short-only) หรือไตรมาสเดียวพยุงทั้ง
  หมด (เหมือน pattern ที่ ETH/XRP เดิมมีอยู่แล้ว — ต้องไม่แย่ลงกว่าเดิม)
  → ลดความเชื่อมั่น ไม่ REJECT อัตโนมัติ แต่ต้องรายงาน
- DEV ผ่านแต่ cost-stress 2× ตก → REJECT, ไม่แตะ holdout

## 6. Replication บน XRP (falsification ที่ถูกและแรงที่สุด)

รัน grid เดียวกัน (12h/18h/24h/36h/48h) บน `XRPUSDT_*` ด้วย — mechanism ที่
เป็นจริงกับตัว exit-rule ของ V0 ต้องให้รูปทรงคล้ายกันบนทั้งสองเหรียญ **ถ้า
เวิร์กเฉพาะ ETH = fit กับประวัติเฉพาะของ ETH ไม่ใช่ mechanism ที่ generalize**
(ใช้ `HOLDOUT_START` เดียวกับที่ XRP vetting เดิมใช้)

## 7. โค้ดที่แตะ

- `src/labeling/triple_barrier.py` — `MAX_HOLD_BARS_M1` เป็น default
  parameter ของ `label_signal`/`label_all_signals` (เช่น
  `max_hold_bars: int = MAX_HOLD_BARS_M1`) ไม่เปลี่ยน default, ไม่กระทบ
  caller เดิม — TDD, เทสต์เดิมต้องผ่านไม่มีการแก้
- `scripts/research_phase7_hold_extension.py` — ใหม่, reuse
  `build_features`/`classify_regime`/`generate_v0_signals`/
  `label_all_signals`/`apply_costs`/`bootstrap_mean_test` เดิมทั้งหมด รันทั้ง
  ETH และ XRP, ทั้ง DEV grid และ (ถ้า DEV+cost-stress ผ่าน) holdout
- ผลลง `docs/research/artifacts/eth_phase7_hold_extension.txt`
- **ไม่แตะ `scripts/run_signal_cycle.py`, `src/live/position_timeout.py`,
  หรือค่า live ใดๆ จนกว่าจะผ่านครบทุก gate ในข้อ 4** ถ้าผ่าน การ deploy คือ
  เปลี่ยนค่าคงที่ 2 จุด (`triple_barrier.MAX_HOLD_BARS_M1`,
  `position_timeout.MAX_HOLD`) เป็นงานแยกที่รอ sign-off อีกครั้ง

## 8. คำตัดสินที่รอ

หลัง gate ครบ (ข้อ 4) + kill criteria ไม่โดน (ข้อ 5) + replicate บน XRP ได้
(ข้อ 6): เสนอ max_hold ที่ผ่าน กับตัวเลขเต็ม (PF, WFO%, holdout CI, cost
stress, ev_r ที่ recompute) ให้ตัดสินใจ deploy หรือไม่ — ไม่ deploy อัตโนมัติ
จากผลสถิติอย่างเดียว

---

## ผล (2026-08-31) — FALSIFIED

Script: `scripts/research_phase7_hold_extension.py`, ผลเต็ม:
`docs/research/artifacts/eth_phase7_hold_extension.csv` (log run:
ดู commit message)

### ตารางผลเต็ม (DEV / cost-stress 2× / holdout / EV-gate CAL-fold)

**ETH** (n_dev=696, n_holdout=784 ทุก hold — เพราะ trade universe เดียวกัน
ถูก re-label ที่ barrier ต่างกันเท่านั้น)

| hold | dev_pf | dev fold+ | cost-stress 2× pf | holdout mean_r (p) | ev_r (CAL 2025H1) |
|---|---|---|---|---|---|
| 12h (control) | 0.859 | 2/5 (40%) | 0.672 | +0.153R (p=0.001) | +0.074R fail |
| 18h | 0.910 | 2/5 (40%) | 0.726 | +0.167R (p=0.001) | +0.124R fail |
| 24h | 0.924 | 2/5 (40%) | 0.741 | +0.168R (p=0.002) | +0.171R PASS |
| 36h | 0.973 | 2/5 (40%) | 0.785 | +0.157R (p=0.004) | +0.193R PASS |
| 48h | 0.975 | 2/5 (40%) | 0.788 | +0.174R (p=0.002) | +0.199R PASS |

**XRP** (n_dev=679, n_holdout=683)

| hold | dev_pf | dev fold+ | cost-stress 2× pf | holdout mean_r (p) | ev_r (CAL 2025H1) |
|---|---|---|---|---|---|
| 12h (control) | 1.123 | 2/5 (40%) | 0.913 | +0.104R (p=0.039) | +0.177R PASS |
| 18h | 1.173 | 2/5 (40%) | 0.968 | +0.113R (p=0.033) | +0.193R PASS |
| 24h | 1.177 | **4/5 (80%)** | 0.976 | +0.113R (p=0.034) | +0.198R PASS |
| 36h | 1.207 | **4/5 (80%)** | 1.006 | +0.115R (p=0.036) | +0.243R PASS |
| 48h | 1.210 | **4/5 (80%)** | 1.010 | +0.114R (p=0.038) | +0.224R PASS |

### Verdict per gate ที่ pre-register ไว้ (§4)

1. **DEV gate (item 1)**: ETH ตกทุกจุด — fold+ ค้างที่ 40% ตลอด 5 hold ไม่ขยับ
   แม้แต่จุดเดียว (ไม่ใช่แค่ PF ต่ำกว่า 1.10) XRP ผ่านที่ 24h/36h/48h
   (fold+ กระโดดจาก 40%→80% ที่ 24h)
2. **Cost-stress 2× (item 3, เช็คก่อนแตะ holdout)**: **ตกทุกจุดทั้งสองเหรียญ**
   แม้แต่จุดที่ดีที่สุด — ETH 0.788 ที่ 48h, XRP 1.010 ที่ 48h (ยังไม่ถึง
   1.10) นี่คือจุดตายอิสระที่ไม่ต้องพึ่ง kill criteria ด้านล่างเลย
3. **Runaway-optimum kill criterion (§5)**: **โดนทั้งสองเหรียญ** — PF/ev_r
   ยังไต่ขึ้นต่อเนื่องไม่หยุดถึง 48h ไม่มี plateau ตรงกับธงแดงที่ล็อกไว้ก่อน
   เห็นผลว่า "= trend-following ไม่มี time-stop ไม่ใช่การแก้ barrier ที่ผูก
   อยู่จริง" → REJECT ทั้ง grid
4. **Resolution-rate check (§5)**: สอดคล้องกับข้อ 3 — resolution rate ไต่จาก
   ~78-80% (ที่ 12h) ไปเกือบ 97-99% (ที่ 48h) ไม่เคยอิ่มตัวในช่วงที่ทดสอบ
   แปลว่าไม่เคยเจอจุดที่ barrier "พอแล้ว" มีแต่ขยายจนไม้เกือบทั้งหมดจบเอง
   ตามธรรมชาติ = กลยุทธ์คนละตัวที่ยังไม่ผ่าน validation ของมันเอง

### หมายเหตุสำคัญ — อย่าอ่าน EV-gate PASS ของ ETH เป็นหลักฐานสนับสนุน

`ev_r_cal_fold` ของ ETH ผ่าน 0.15R ที่ hold≥24h แต่ **CAL fold (2025-01..
2025-06) อยู่ในช่วงที่รู้อยู่แล้วว่าเป็นช่วงแข็งแรงที่สุดของ ETH ในประวัติ**
(docs/research/BTC_EDGE_SEARCH.md Round 6 addendum: edge เต็มช่วง 13 ไตรมาส
จริงๆ มีแค่ 0.038R, ผ่าน gate แค่ 3/13 ไตรมาส) DEV gate ที่ครอบคลุมกว้างกว่า
คือตัวชี้ที่น่าเชื่อกว่า และ ETH ไม่ผ่านเลยสักจุดในนั้น — บรรทัด EV-gate PASS
นี้จึงเป็น artifact ของการเลือก window ไม่ใช่หลักฐานว่าปัญหาถูกแก้

### คำตัดสิน

**REJECT ทั้ง grid ทั้งสองเหรียญ** — 12h barrier ไม่ใช่ข้อจำกัดที่ยืดแล้วแก้
ได้ตรงๆ ตามที่ Phase 6 ชี้เป้าไว้ ปิดเคส Phase 7 ไม่ deploy อะไรเข้า live
(`triple_barrier.MAX_HOLD_BARS_M1`/`position_timeout.MAX_HOLD` คงค่าเดิม
12h) V0 บน ETH/XRP ยังตก EV gate ที่ deploy จริงอยู่ (commit 59c59e2) —
สถานะ "ไม่มีไม้เข้า" ยังคงอยู่ตามความจริงของตัวเลข
