# แผนและผล Backtest

อัปเดตล่าสุด: 2026-08-25 สรุปวิธีการ backtest และทุกการทดลองที่รันมาแล้ว
กลั่นมาจาก [FINDINGS.md](FINDINGS.md) (แหล่งข้อมูลจริงตามลำดับเวลา — อ่าน
ไฟล์นั้นก่อนรันการทดลองซ้ำ) และตรวจสอบไขว้กับ
[STRATEGY_RISK_SPEC.md](STRATEGY_RISK_SPEC.md) ว่าอะไรถูกล็อกไว้บน live จริง

## 1. วิธีการ

### 1.1 Cost model — [src/backtest/costs.py](../src/backtest/costs.py)

`r_multiple` ดิบจากการ label ทุกตัวถูกหักต้นทุน 3 ส่วน แปลงเป็น R-multiple
ทั้งหมด (สัดส่วนของ `sl_distance`) เพื่อรวมกันได้ตรงๆ:

| ต้นทุน | โมเดล |
|---|---|
| Commission | taker fee แบบ round-trip (เข้า + ออก), `TAKER_FEE = 0.0005` |
| Funding | รวมตลอดช่วงถือครองจากข้อมูล funding rate ประวัติศาสตร์จริง; เครื่องหมายกลับด้านสำหรับ LONG กับ SHORT |
| Slippage | สัดส่วนราคาคงที่ `SLIPPAGE_BPS = 2.0` (2 bps/side) — แก้จาก USD คงที่เดิมแล้ว (ดู §5) |

`net_r_multiple = r_multiple - commission_r - slippage_r - funding_r`

### 1.2 การทดสอบนัยสำคัญ — [src/backtest/significance.py](../src/backtest/significance.py)

Bootstrap แบบ one-sample (`n_resamples=10,000`) บน `net_r_multiple`: สุ่ม
ตัวอย่างซ้ำแบบมีการแทนที่ คำนวณค่าเฉลี่ยแต่ละรอบ แล้วรายงาน 95% CI พร้อม
p-value แบบ two-sided สำหรับ H0: ค่าเฉลี่ยจริง ≤ 0 ผลจะนับว่า significant
ก็ต่อเมื่อ `p < 0.05` **และ** ขอบล่างของ CI สูงกว่าศูนย์

### 1.3 การแบ่งข้อมูลที่ใช้

- **Single split**: TRAIN (2023-2024) / HOLDOUT (2025-2026) — ใช้สำหรับ
  screening เบื้องต้นเท่านั้น
- **Anchored walk-forward**: 12 quarterly fold ตั้งแต่ 2023-Q3 ถึง 2026-Q2
  แต่ละ fold แบบ anchored (ขยาย train window ไปข้างหน้าเรื่อยๆ) มี embargo
  12 ชม. ที่รอยต่อของแต่ละ fold เพื่อป้องกัน leakage ข้ามรอยตัด
- ทั้งสองแบบใช้ config ที่ล็อกไว้ชุดเดียวกันทุก fold — ไม่มีการ re-tune ราย
  fold เพื่อเลี่ยงปัญหา multiple-comparison

## 2. บันทึกการทดลอง (ตามลำดับเวลา จาก FINDINGS.md)

### 2.1 คัดกรองกลยุทธ์ V0 บน BTC (single split)

เทส EMA-pullback, Donchian breakout, และ mean-reversion-fade บน BTC/USDT
ใช้ cost model เต็มรูปแบบ

| กลยุทธ์ | TRAIN net_avg_r | HOLDOUT net_avg_r | PF (holdout) |
|---|---|---|---|
| EMA pullback (ADX35, SL2.5x) | -0.047 | -0.027 | 0.956 |
| Breakout | — | — | ~0.52 |
| Mean-reversion | — | — | ~0.52 |

**บทสรุป**: ไม่มี edge ที่ใช้ได้จริงบน BTC/USDT ด้วย setup ทั้ง 3 แบบที่ M15
ปิดประเด็นแล้ว — ห้ามเทส config ชุดนี้เป๊ะๆ กับ BTC ซ้ำโดยไม่มีข้อมูลใหม่

### 2.2 คัดกรองแบบ pooled หลาย symbol (BTC/ETH/SOL/BNB)

Config ที่ล็อกไว้ชุดเดียวกัน ใช้แค่ HOLDOUT (2025-2026) ข้าม 4 symbol
(เลี่ยงการนำ bias จากการ tune รายตัวกลับมา)

| Symbol | net_avg_r | PF |
|---|---|---|
| BTC | -0.027 | 0.956 |
| **ETH** | **+0.152** | **1.278** ← ตัวเดียวที่ผ่าน PF 1.10 |
| SOL | -0.504 | 0.474 |
| BNB | -0.307 | 0.616 |

เลือก ETH เป็นตัวเดียวที่ขึ้น live การเช็คสนับสนุนบน ETH holdout:
- Bootstrap: **p = 0.0012**, 95% CI **[0.058, 0.246]** — ค่าเฉลี่ยบวกรอด
  การ resample
- Slippage sensitivity 1x/2x/3x: PF ยังสูงกว่า 1.10 แม้ที่ 3x (1.143)
- ความสม่ำเสมอรายไตรมาสภายใน holdout window นี้: **7/7 เป็นบวก**

### 2.3 Anchored 12-fold walk-forward บน ETH (ประวัติเต็ม 3 ปี)

ผล single-split ด้านบนเทสแค่ window เดียว (2025-2026) การทดสอบนี้ใช้
config ที่ล็อกไว้ชุดเดียวกันข้ามประวัติศาสตร์ทั้งหมด เพื่อเช็คว่า edge
generalize ได้จริงไหม

**ผล — อ่อนกว่าที่ single-split test บอกไว้อย่างมีนัยสำคัญ:**

| Metric | ค่า |
|---|---|
| Fold ที่บวก | 8/12 (67%) — ผ่านเกณฑ์ §15 ที่ 60% แต่เฉียดมาก |
| Fold ที่ significant รายตัว | 2/12: 2024-Q1 (+0.471R, p<0.001), 2025-Q3 (+0.365R, p=0.0013) |
| Fold ที่แย่ที่สุด | **2023-Q3 (-0.479R, p=0.006)** และ **2023-Q4 (-0.434R, p<0.001)** — ติดลบอย่าง significant ทั้งคู่ |
| ส่วนเบี่ยงเบนมาตรฐานข้าม fold | 0.282 เทียบกับค่าเฉลี่ยรวม 0.038 — variance สูงเมื่อเทียบกับค่าเฉลี่ย |

**สาเหตุหลักของความล้มเหลวใน 2023 H2** (ดูรายละเอียดเต็มใน FINDINGS.md):
ETH พุ่งขึ้น +38% ตลอดช่วงนี้ แต่ผ่านเส้นทางที่สับสนและผันผวนสูง (ดิ่งลงลึก
ถึง $1,525 ช่วงก.ย.-ต.ค. ก่อนจะพุ่งต่อ) ATR percentile เฉลี่ย 64.5% ในช่วงนี้
เทียบกับ 48.4% ของช่วงอื่น ทั้ง LONG (-0.457R, n=116) และ SHORT (-0.433R,
n=60) ขาดทุนทั้งคู่ โดย 62% ของเทรดทั้งหมดในช่วงนี้ออกทาง SL — ลายเซ็นของ
regime whipsaw ไม่ใช่ความล้มเหลวจากทิศทาง bias

**บทสรุป**: ETH มี edge จริงแต่**ไม่เสถียร** — แข็งแรงในบางไตรมาส หายไปหรือ
ติดลบในไตรมาสอื่น สัมพันธ์กับ regime สับสน-ผันผวนสูงเฉพาะที่เกิดใน 2023 H2
และอาจเกิดซ้ำได้ นี่คือเหตุผลที่ `base_risk_pct` ของ ETH บน live ถูกตั้งไว้
ที่ 0.5% แทนที่จะเป็น 1–2% ตามแผนเดิม และเป็นเหตุผลที่มี rolling win-rate
guard (ดู [STRATEGY_RISK_SPEC.md §4.2](STRATEGY_RISK_SPEC.md#42-base-risk-และ-win-rate-guard))

### 2.4 ทดสอบวิธีแก้: ตัวกรองเพดาน volatility `atr_pct_max=0.75` — ถูกปฏิเสธ

สมมติฐาน: การจำกัดเทรดให้ ATR percentile ≤ 75% จะกรอง regime whipsaw ของ
2023 H2 ออกโดยไม่กระทบไตรมาสที่ดี (2024-Q1, 2025-Q3)

**ผล: สมมติฐานถูกปฏิเสธ** ทำให้แย่ลงในทุกด้าน:
- ความสม่ำเสมอลดจาก 8/12 (67%) เหลือ 6/12 (50%) — ตอนนี้ไม่ผ่านเกณฑ์ §15
- `net_avg_r` รวมทั้งหมดกลับจาก **+0.038 เป็น -0.031**
- 2023-Q3 *แย่ลง* ไม่ใช่ดีขึ้น (-0.435R → -0.754R)
- ตัวกรองตัดเทรดดีออกพอๆ กับเทรดแย่ (จำนวนเทรด 2025-Q3 ลดจาก 147→84) —
  ATR percentile สูงไม่ใช่ตัวแทนที่สะอาดของ "เทรดแย่" ในกรณีนี้ เทรดที่ดี
  ที่สุดบางไม้ (2024-Q1, 2025-Q3) ก็เกิดขึ้นในสภาวะ vol สูงเช่นกัน

**บทสรุป**: อย่าลองตัวกรองเพดาน ATR-percentile แบบง่ายซ้ำกับกลยุทธ์นี้โดย
ไม่มีกลไกที่เฉพาะเจาะจงกว่านี้ที่แยก "vol สูงจาก breakout ที่สะอาด" ออกจาก
"vol สูงจากความสับสน" ได้ — threshold เดียวทำแบบนั้นไม่ได้ (script การ
ทดลองถูกลบหลังยืนยันผลลบแล้ว; entry ใน FINDINGS.md คือบันทึกเดียวที่เหลืออยู่)

### 2.5 ML (LightGBM) — ถูกปฏิเสธ

ไม่ใช่การทดลอง backtest-P&L โดยตรง แต่เกี่ยวข้องกับ pipeline เดียวกัน: เทส
ที่ gate สถิติ P5, holdout AUC ≈ 0.497 — แยกไม่ออกจาก noise `src/models/`
เก็บไว้อ้างอิงเท่านั้น ไม่ได้ใช้บน live EV gate บน live
(`src/live/ev_estimate.py`) ใช้ base rate จาก backtest ประวัติศาสตร์แทน
label ว่าไม่ใช่ ML อย่างชัดเจนทุกที่ที่แสดงผล

## 3. สรุปว่ากลยุทธ์บน live อยู่ตรงไหน

- **ยังไม่พิสูจน์ว่าแข็งแรงพอสำหรับ risk 1–2% ตามแผนเดิม** — ผล 2023 H2
  แสดง drawdown risk จริงที่ single-holdout test ไม่เคยเปิดเผยมาก่อน
- **ก็ไม่ได้ตายเช่นกัน** — 2/12 ไตรมาสแสดง significant ทางสถิติจริงในทิศทาง
  บวก และนี่ยังคงเป็นผลที่ดีที่สุดในบรรดาทุกอย่างที่เทสมา (4 symbol × 3
  ตระกูลกลยุทธ์ × หลาย config SL/ADX)
- **การตัดสินใจที่ทำไปแล้ว**: paper-trade บน testnet ต่อไปที่ cadence
  ปัจจุบัน; ลด risk บน live เหลือ 0.5%/เทรด พร้อม guard ที่ลดครึ่งอัตโนมัติ
  เมื่อ rolling win-rate ตก (ดู [STRATEGY_RISK_SPEC.md](STRATEGY_RISK_SPEC.md))
  ห้ามขึ้น risk กลับไปทาง 1–2% โดยไม่มี (ก) ข้อมูล live paper-trade เพิ่มเติม
  หรือ (ข) คำอธิบายเชิงกลไก (ไม่ใช่ threshold) สำหรับความล้มเหลวของ 2023 H2
  ที่เทสกับ holdout ใหม่แล้ว

## 4. Backtest Script (อ้างอิง)

| Script | จุดประสงค์ |
|---|---|
| [scripts/run_v0_backtest_smoke.py](../scripts/run_v0_backtest_smoke.py) | รันตรวจสอบเบื้องต้นแบบเร็ว |
| [scripts/run_v0_backtest_with_costs.py](../scripts/run_v0_backtest_with_costs.py) | Backtest เต็มรูปแบบพร้อมต้นทุน |
| [scripts/run_v0_holdout_final.py](../scripts/run_v0_holdout_final.py) | รัน single train/holdout split |
| [scripts/run_v0_pooled_multi_symbol.py](../scripts/run_v0_pooled_multi_symbol.py) | คัดกรองแบบ pooled หลาย symbol (§2.2) |
| [scripts/eth_walkforward_multifold.py](../scripts/eth_walkforward_multifold.py) | Anchored walk-forward 12 fold (§2.3) |
| [scripts/eth_walkforward_and_slippage.py](../scripts/eth_walkforward_and_slippage.py) | Walk-forward + slippage sensitivity |
| [scripts/test_eth_significance.py](../scripts/test_eth_significance.py) | ทดสอบ bootstrap significance |
| [scripts/compare_v0_strategies.py](../scripts/compare_v0_strategies.py) | เปรียบเทียบกลยุทธ์แบบเคียงข้างกัน |
| [scripts/tune_v0_filters.py](../scripts/tune_v0_filters.py) | Sweep พารามิเตอร์ตัวกรอง (ใช้กับการทดลอง atr_pct_max, §2.4) |
| [scripts/research_btc_edge_search.py](../scripts/research_btc_edge_search.py), [research_btc_cme_gap.py](../scripts/research_btc_cme_gap.py) | หา edge เฉพาะ BTC (4 hypotheses, ทั้งหมด fail — ดู FINDINGS.md) |
| [scripts/research_second_symbol_screen.py](../scripts/research_second_symbol_screen.py), [research_xrp_vetting.py](../scripts/research_xrp_vetting.py) | คัดกรอง+vet symbol ที่ 2 (XRP ได้รับเลือก, tier-2) |
| [scripts/research_xau_*.py](../scripts/) | โปรแกรมวิจัย XAU (ทอง) — สรุปว่าไม่มี price-only edge, ดู FINDINGS.md |

## 5. ช่องว่างที่ยังมีในตัว backtest เอง

- Slippage ตอนนี้เป็นสัดส่วนราคาแล้ว (`SLIPPAGE_BPS = 2.0`, แก้จาก USD คงที่
  เดิมที่ทำให้ coin ราคาต่ำได้ค่าเพี้ยน — ดู FINDINGS.md) แต่ยังเป็นค่าคงที่
  ที่ตั้งไว้ ไม่ได้วัดจากความลึกของ order book จริง — flag ไว้สำหรับ phase
  mainnet-shadow ที่ยังไม่ได้รัน (ดู [HANDOFF.md](HANDOFF.md))
- ยังไม่มีการเช็ค robustness จากการตัด 2 เดือนที่ผลดีผิดปกติ (ส.ค. 2025,
  ส.ค. 2026) ออกจาก walk-forward — flag ไว้เป็นขั้นต่อไป แต่ยังไม่ได้ทำ
- ยังไม่มีเทรดเกิดขึ้นบน live/paper นับจากที่เขียนไฟล์นี้ (ETH) จึงยังไม่มี
  ข้อมูลความคลาดเคลื่อน live-vs-backtest เพิ่มเติมนอกจากที่เคยเจอและแก้ไป
  แล้ว (bug ความคลาดเคลื่อนเรื่อง missing-TP + timeout ดู git history รอบๆ
  `df8513b`)
