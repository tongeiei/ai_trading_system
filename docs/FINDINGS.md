# บันทึกผลการวิจัย (Research Findings Log)

บันทึกตามลำดับเวลาว่าอะไรถูกเทสแล้วและสรุปว่าอะไร — เพื่อไม่ให้กลับไปเถียง
ประเด็นที่ตกลงกันแล้ว หรือรันการทดลองซ้ำที่เคยล้มเหลวไปแล้ว ทุก entry ที่นี่
คือผล backtest จริง ไม่ใช่การคาดเดา

---

## 2026-08 — คัดกรองกลยุทธ์ V0 (BTC, single-split)

เทส EMA pullback, Donchian breakout, และ mean-reversion-fade เป็น V0
candidate บน BTC/USDT, แบ่ง TRAIN(2023-2024)/HOLDOUT(2025-2026) ใช้ cost
model เต็มรูปแบบ (commission + funding + slippage)

**ผล:** ไม่มีตัวไหนเอาชนะ PF 1.10 ได้ EMA pullback (ADX35, SL2.5x) ดีที่สุด —
TRAIN net_avg_r -0.047, HOLDOUT net_avg_r -0.027, PF 0.956 Breakout และ
mean-reversion แย่กว่าชัดเจน (PF ~0.52) ทั้งสอง split

**บทสรุป:** BTC/USDT ไม่มี edge ที่ใช้ประโยชน์ได้ ด้วย setup ทั้ง 3 แบบที่
M15 ห้ามเทส config ชุดนี้เป๊ะๆ กับ BTC ซ้ำอีกโดยไม่มีข้อมูลใหม่

## 2026-08 — คัดกรองแบบ pooled หลาย symbol (BTC/ETH/SOL/BNB)

Config ที่ล็อกไว้ชุดเดียวกัน (ADX35, SL2.5x, ไม่ tune รายตัว) รันข้าม 4
symbol ใช้แค่ HOLDOUT (2025-2026) เพื่อเลี่ยงปัญหา multiple-comparison จาก
การ tune รายตัวแบบเฉพาะกิจ

**ผล:**
- BTC: net_avg_r -0.027, PF 0.956
- **ETH: net_avg_r +0.152, PF 1.278** ← ตัวเดียวที่ผ่าน PF 1.10
- SOL: net_avg_r -0.504, PF 0.474
- BNB: net_avg_r -0.307, PF 0.616

**บทสรุป:** เลือก ETH เป็น live candidate ตัวเดียว Bootstrap test บน ETH
holdout: p=0.0012, 95% CI [0.058, 0.246] — ค่าเฉลี่ยบวกรอดการ resample
Slippage sensitivity 1x/2x/3x: PF ยังสูงกว่า 1.10 แม้ที่ 3x (1.143) ความ
สม่ำเสมอรายไตรมาสภายใน holdout: 7/7 เป็นบวก

## 2026-08 — Anchored multi-fold walk-forward บน ETH ประวัติเต็ม 3 ปี

Single train/holdout split ด้านบนเทสแค่ window เดียว (2025-2026) รัน 12
anchored quarterly fold (2023-Q3 ถึง 2026-Q2) พร้อม embargo 12 ชม. ที่รอย
ต่อแต่ละ fold, config ที่ล็อกไว้ชุดเดียวกัน ไม่ re-tune

**ผล — อ่อนกว่าที่ single-split test บอกไว้อย่างมีนัยสำคัญ:**
- 8/12 fold เป็นบวก (67%) — ผ่านเกณฑ์ §15 ที่ 60% แต่เฉียดมาก
- มีแค่ 2/12 fold ที่ significant ทางสถิติจริงๆ: 2024-Q1
  (+0.471R, p<0.001) และ 2025-Q3 (+0.365R, p=0.0013)
- **2023-Q3 และ 2023-Q4 ติดลบอย่าง significant ทั้งคู่**
  (-0.479R p=0.006, -0.434R p<0.001) — เป็น regime ที่ single-split test
  ไม่เคยเห็นเพราะใช้แค่ 2025-2026 เป็น holdout
- ส่วนเบี่ยงเบนมาตรฐานข้าม fold: 0.282 เทียบกับค่าเฉลี่ยรวม 0.038 — variance
  สูงเมื่อเทียบกับค่าเฉลี่ย

**วิเคราะห์สาเหตุหลักของ 2023 H2 (ดู conversation log):** ETH พุ่งขึ้น +38%
ตลอดช่วงนี้ แต่ผ่านเส้นทางที่สับสนและผันผวนสูง (ดิ่งลึกถึง $1525 ช่วง
ก.ย.-ต.ค. ก่อนจะพุ่งต่อ) ATR percentile เฉลี่ย 64.5% ในช่วงนี้ เทียบกับ
48.4% ของช่วงอื่น ทั้ง LONG (-0.457R, n=116) และ SHORT (-0.433R, n=60)
ขาดทุนทั้งคู่ โดย 62% ของเทรดทั้งหมดในช่วงนี้ออกทาง SL — ลายเซ็นของ regime
whipsaw ไม่ใช่ความล้มเหลวจากทิศทาง bias

**บทสรุป:** ETH มี edge จริงแต่**ไม่เสถียร** — แข็งแรงในบางไตรมาส หายไปหรือ
ติดลบในไตรมาสอื่น สัมพันธ์กับ regime สับสน-ผันผวนสูงเฉพาะที่เกิดใน 2023 H2
และอาจเกิดซ้ำได้

## 2026-08 — ทดสอบวิธีแก้: ตัวกรองเพดาน volatility `atr_pct_max=0.75`

สมมติฐาน: การจำกัดเทรดให้ ATR percentile <= 75% จะกรอง regime whipsaw ที่
ทำร้าย 2023 H2 ออก โดยไม่กระทบไตรมาสที่ดี (2024-Q1, 2025-Q3) อย่างมี
นัยสำคัญ

**ผล: สมมติฐานถูก**ปฏิเสธ** ตัวกรองทำให้แย่ลงในทุกด้าน:**
- ความสม่ำเสมอลดจาก 8/12 (67%) เหลือ 6/12 (50%) — ตอนนี้**ไม่ผ่าน**เกณฑ์ §15
- `net_avg_r` รวมทั้งหมดกลับจาก +0.038 เป็น **-0.031**
- 2023-Q3 *แย่ลง* ไม่ใช่ดีขึ้น (-0.435R -> -0.754R)
- ตัวกรองตัดเทรดดีออก (n ของ 2025-Q3 ลดจาก 147->84) พอๆ กับเทรดแย่ — "vol
  สูง" ไม่ใช่ตัวแทนที่สะอาดของ "เทรดแย่" ในกรณีนี้ เทรดที่ดีที่สุดบางไม้
  (2024-Q1, 2025-Q3) ก็เกิดขึ้นในสภาวะ vol สูงเช่นกัน

**บทสรุป:** อย่าลองตัวกรองเพดาน ATR-percentile แบบง่ายซ้ำกับกลยุทธ์นี้อีก
โดยไม่มีกลไกที่เฉพาะเจาะจงกว่านี้ (เช่น แยก "vol สูงจาก breakout ที่สะอาด"
ออกจาก "vol สูงจากความสับสน" — threshold เดียวทำแบบนั้นไม่ได้) script ของ
การทดลองนี้ถูกลบหลังยืนยันผลลบแล้ว entry นี้คือบันทึกเดียวที่เหลืออยู่

---

## สรุปสถานะ ETH candidate (ปัจจุบัน ณ ตอนนั้น)

- **ยังไม่พิสูจน์ว่าแข็งแรงพอสำหรับ risk 2%/เทรด** ตามที่วางแผนไว้เดิมใน
  ตาราง growth-scaling — ผล 2023 H2 แสดง drawdown risk จริงที่
  single-holdout test ไม่เคยเปิดเผยมาก่อน
- **ก็ไม่ได้ตายเช่นกัน** — 2/12 ไตรมาสแสดง significant ทางสถิติจริงในทิศทาง
  บวก และกลยุทธ์นี้ยังคงเป็นตัวที่ดีที่สุดในบรรดาทุกอย่างที่เทสมา (4 symbol
  × 3 ตระกูลกลยุทธ์ × หลาย config SL/ADX)
- **การตัดสินใจ:** paper-trade บน testnet ต่อไปที่ cadence ปัจจุบัน ลด
  risk_pct บน live ที่วางแผนไว้ให้ต่ำกว่าช่วง 1-2% จนกว่าจะมี (ก) ข้อมูล
  paper-trade สะสมเพิ่มเติม หรือ (ข) คำอธิบายเชิงกลไก (ไม่ใช่ threshold)
  สำหรับความล้มเหลวของ 2023 H2 ที่ถูกค้นพบและเทสอย่างถูกต้องกับ holdout ใหม่

---

## 2026-08 — ประเมิน XAU (ทอง) เป็น instrument ใหม่ — price-only edge ถูก FALSIFY

แรงจูงใจ: Binance USDⓈ-M futures มี `XAU/USDT` perp; user ถามว่าระบบเทรดทอง
ได้ไหม connector/pipeline เป็น symbol-parameterized อยู่แล้ว คำถามจริงคือ
มี edge ที่เทรดได้บนทองหรือไม่

### ข้อมูล
- Binance `XAU/USDT` perp เพิ่งลิสต์ตั้งแต่ **2025-12-11** (~8.5 เดือน) —
  สั้นเกินไปที่จะ validate การผ่านครั้งแรกถูก label ว่า EXPLORATORY เท่านั้น
- หาประวัติยาวจาก **Dukascopy spot `XAU/USD`, 2006-2026 (~20 ปี)**:
  `data/raw/XAUUSD_{15m,1h,1m}.parquet` (M15 505k / H1 127k / M1 7.38M
  แท่ง) ดึงผ่าน `scripts/fetch_xau_dukascopy.py` อยู่ใน gitignore
  (research-only ไม่เคย deploy — live path ดึง OHLCV จาก exchange ไม่อ่าน
  parquet) บันทึกเป็น `XAUUSD_*` ให้อยู่คู่ (ไม่ทับ) กับ perp `XAUUSDT_*`
- **ข้อควรระวัง:** Dukascopy เป็น SPOT bid feed ไม่ใช่ Binance perp ใช้
  สำหรับหา edge/regime ตัวรอดยังต้อง re-validate กับ microstructure จริง
  ของ perp ต้นทุนในงานวิจัยใช้ Binance-perp taker fee + slippage + synthetic
  funding carry ~6.7%/ปี (ค่าเฉลี่ย perp ที่วัดได้จริง)

### Characterization 20 ปี (`scripts/research_xau_characterization_20y.py`)
- **ทองเป็น RANGE ~79% ของเวลา ในทุกปี 2006-2026** (full sample TREND
  20.7% / RANGE 79.3% ที่ ADX35 บน H1) sample 8.5 เดือนไม่ใช่เรื่องบังเอิญ
  — trend-following เสียเปรียบเชิงโครงสร้างบนทอง
- Volatility กระจุกที่ **London-NY OVERLAP** (~11.9 bps/แท่ง เทียบ Asia
  5.8) วันหยุดสุดสัปดาห์แทบตาย (ตามเวลาตลาดทองจริง)
- M15 return autocorr(lag1) เป็น**ลบใน ~19/21 ปีแต่เล็กมาก (−0.018)** —
  บ่งชี้ไปทาง mean-reversion แต่เล็กน้อยเชิงเศรษฐศาสตร์

### Trend-following (exploratory, perp 8.5 เดือนเท่านั้น)
Locked ETH-derived V0 (ADX35/SL2.5) บวกตัวกรอง session / weekday /
daily-trend (H0-H4) **ขาดทุนทั้งหมด** (ดีที่สุด −0.15R, PF 0.77) การเพิ่ม
Daily เป็นชั้นบนสุด**ไม่ช่วย** — H1 กับ Daily trend เห็นตรงกัน ~90-95% ของ
เวลา (collinear ไม่มีข้อมูลใหม่) ตัวกรอง weekday-only ช่วย (flow วันหยุด
เป็นพิษ) แต่ก็ยังขาดทุน

### Mean-reversion — FALSIFICATION เต็มรูปแบบ 20 ปี (`scripts/research_xau_mr_falsification.py`)
Protocol: variant ที่ pre-register ไว้, sacred holdout >= 2025-01-01 (bull
ใหญ่ของทอง), quarterly WFO + embargo 12 ชม., gate PF>1.10 และ >=60% fold
เป็นบวก

| variant | n | win% | exp | PF | folds+ | gate |
|---|---|---|---|---|---|---|
| R0 MR default (entry_z=2, RANGE) | 42,053 | 33% | −0.99R | 0.17 | 0/76 | FAIL |
| R1 + high-liq sessions | 28,309 | 34% | −0.87R | 0.21 | 0/76 | FAIL |
| R2 + sessions + daily-trend guard | 14,167 | 35% | −0.82R | 0.22 | 0/76 | FAIL |

ทุก variant **fail หนัก**: PF 0.17-0.22, **0 จาก 76 quarterly fold เป็น
บวก**, p=0.0000 Guard ช่วยลดเลือดออก (exp −0.99→−0.82R, MaxDD −41k→−11.6kR)
แต่ไม่ใกล้เคียงกำไรเลย **Sacred holdout ไม่ถูกแตะเลย** (ไม่มีอะไรผ่าน pool
gate ตาม protocol)

Reconcile กับ autocorr ที่เป็นลบ: มันเป็นผลระดับ 1 แท่ง (15 นาที) และเล็ก
มาก; กลยุทธ์ MR ฟาดสวน extreme 2σ ถือได้ถึง 12 ชม. — คนละ horizon ที่การ
เคลื่อนไหวของทอง persist มากพอจนการฟาดสวนขาดทุนหลังหักต้นทุน **Micro
mean-reversion ≠ swing mean-reversion ที่เทรดได้จริง**

### บทสรุป
**ไม่มี price-only edge (ทั้ง trend หรือ mean-reversion) รอดบน XAU ด้วย
feature set ปัจจุบัน** ทั้งสองตระกูลถูก falsify แล้ว — mean-reversion
อย่างเข้มงวดตลอด 20 ปี นี่คือผลลบที่แข็งแกร่ง ไม่ใช่ความผิดพลาดจาก sample
8.5 เดือน

โครงสร้างที่เทรดได้ของทองไม่ได้อยู่ใน price pattern ของ M15/H1; มันถูก
**ขับเคลื่อนด้วย macro (DXY / real yields / Fed)** — สัญญาณที่ feature
ปัจจุบันมองไม่เห็น

**การตัดสินใจ:** หยุดงาน price-only บน XAU; เก็บทรัพยากรไว้กับโปรแกรม
ETH/crypto จะกลับมาดู XAU อีกครั้งก็ต่อเมื่อสร้างชั้น macro-feature (อย่าง
น้อยคือ DXY) เป็นชั้นบนสุดที่ orthogonal จริงๆ — เป็นโปรเจกต์ data-pipeline
แยกต่างหาก ไม่ใช่แค่เปลี่ยนพารามิเตอร์ ห้ามรัน price-only trend/MR scan บน
XAU ซ้ำอีก; entry นี้คือ record ที่ settled แล้ว

---

## 2026-08 — หา symbol ที่ 2: BTC-specific edge (ไม่มี) + XRP candidate (marginal)

เป้าหมาย (user): เพิ่ม symbol ที่ 2 บน live เพื่อเพิ่มโอกาสเทรด/deploy ทุน
(**ไม่ใช่**เพื่อ diversification) Symbol บน live ปัจจุบันมีแค่ ETH

### พบ Slippage bug (กระทบทุก coin ราคาต่ำ)
`src/backtest/costs.py` ใช้ `SLIPPAGE_PRICE_UNITS = 0.5` คงที่ (0.5 USD ต่อ
side, calibrate ไว้กับ BTC ~$60k) ซึ่งไม่สมเหตุสมผลกับ coin ราคาต่ำ: DOGE
ที่ $0.06 กับ stop $0.000168 ได้ "slippage" ~5,900R ต่อเทรด ทำให้เกิดผลที่
เป็นไปไม่ได้ทางฟิสิกส์ −477R เฉลี่ยในการ screen รอบแรก ETH/BTC ไม่กระทบ
(0.5 USD จิ๊บจ๊อยที่ราคาระดับนั้น)

**แก้แล้ว (2026-08, TDD):** `src/backtest/costs.py` ตอนนี้ใช้
`SLIPPAGE_BPS = 2.0` (2 bps/side ของราคา, เป็นสัดส่วน) ผ่าน
`slippage_cost_r(sl_distance, entry_price, slippage_bps)` แก้ caller ครบ
(`apply_costs`, live `ev_estimate.py`, `eth_walkforward_and_slippage.py`)
ETH edge ถูก re-confirm แล้วภายใต้โมเดลใหม่: holdout PF 1.276 (เดิม 1.278),
p=0.001, CI [0.060, 0.246] — แทบไม่เปลี่ยน เพราะ 2 bps ≈ อัตราที่ ETH เคย
validate จริงที่ 1.7 bps เพิ่ม regression test ใน `tests/test_costs.py`
(proportional + low-priced-coin sanity)

### คัดกรอง candidate (locked V0 ADX35/SL2.5, ไม่ tune, slippage ที่แก้แล้ว)
Shortlist ที่ pre-register ไว้ (fix ก่อนเห็นผล): XRP, DOGE, ADA, LINK, LTC,
AVAX (6 ตัวที่ liquid สุด/ลิสต์นานสุดที่ยังไม่เคยเทส) Gate = holdout
PF>1.10 และ full-history WFO >=60% fold เป็นบวก และ holdout bootstrap
p<0.05

| symbol | hold PF | exp_r | WFO folds+ | boot p | gate |
|---|---|---|---|---|---|
| ETH (ref) | 1.28 | +0.15 | 8/12 (67%) | 0.001 | PASS |
| BTC (ref) | 0.87 | −0.08 | 4/12 | 0.096 | fail |
| XRP | 1.18 | +0.10 | 7/12 (58%) | 0.047 | near-miss |
| LINK | 1.17 | +0.09 | 7/12 (58%) | 0.063 | near-miss |
| AVAX | 0.89 | −0.07 | 8/12 (67%) | 0.136 | fail |
| DOGE | 0.86 | −0.09 | 4/12 | 0.066 | fail |
| ADA | 0.83 | −0.10 | 6/12 | 0.043 | fail |
| LTC | 0.75 | −0.17 | 1/12 | — | fail |

ไม่มีตัวไหนผ่าน gate เต็ม XRP และ LINK เป็น near-miss ที่แท้จริง
(expectancy บวก, PF>1.17) ตกแค่ WFO consistency (58% เทียบ 60%)

### หา BTC-specific edge — 4 สมมติฐานที่ pre-register ไว้ **fail ทั้งหมด**
User เลือกจะหา edge เฉพาะ BTC แทนที่จะบังคับ V0 ลง BTC เทส (sacred holdout
2026-07-01, gate PF>1.10 และ >=60% yearly bucket และ p<0.05):

| hypothesis | PF | exp_r | years+ | gate |
|---|---|---|---|---|
| V0 control | 0.94 | −0.04 | — | fail |
| V0 + high-liq sessions | 0.96 | −0.02 | — | fail |
| CME weekend gap-fill | 0.76 | −0.17 | 1/4 | fail |
| Funding-extreme contrarian | 0.81 | −0.41 | 2/4 | fail |

Pattern: 2023-2024 ติดลบแรงในทุกสมมติฐาน, 2025-2026 บวกอ่อนๆ — ถ้า BTC
กำลังจะมี edge มันเพิ่งเกิดและยังไม่แข็งแรงพอ CME gap-fill fill-rate แค่
41% หลังหักต้นทุน (ความเชื่อ "gap เติมเสมอ" ไม่จริงในช่วง 2023-2026)
**บทสรุป: BTC efficient/ยากที่ horizon M15-daily สำหรับกลไกพวกนี้; ไม่พบ
BTC-specific edge หยุดเทสสมมติฐาน BTC เพิ่ม (ใช้ multiple-comparison
budget ไปแล้ว 4 ตัว)** Script: `research_btc_edge_search.py`,
`research_btc_cme_gap.py`

### XRP vetting เต็มระดับ ETH (`research_xrp_vetting.py`)
XRP ผ่านชุดทดสอบเดียวกับที่ ETH เคยผ่าน:
- **WFO 12 fold:** 7/12 เป็นบวก (58%), std 0.239; 2 fold significant บวก
  (2024Q1 +0.48***, 2026Q1 +0.49***), 1 fold significant ลบ (2025Q4
  −0.26*) โปรไฟล์เหมือน ETH คือ "ไม่กี่ไตรมาสใหญ่พยุงทั้งหมด"
- **Holdout:** PF 1.185, +0.104R, p=0.047, 95% CI [0.001, 0.205] — ผ่าน
  แต่ขอบล่างของ CI แตะศูนย์เกือบสนิท (เปราะ)
- **Slippage sensitivity:** PF 1.19 / 1.13 / 1.07 ที่ 1x/2x/3x (2/4/6 bps)
  **หลุดต่ำกว่า 1.10 ที่ 3x** — ETH ยังอยู่ที่ 1.14 ที่ 3x XRP ทนต่อ
  slippage น้อยกว่า**และ**liquid น้อยกว่า จึงมี risk slippage จริงสูงกว่า
- **Long/short:** LONG PF 1.40 (+0.21R) แข็งแรง; SHORT PF 1.055 (+0.03R)
  เฉียดบวกเท่านั้น — edge อยู่ฝั่ง long เป็นหลัก
- **Overlay เทียบ ETH (เซอร์ไพรส์เชิงบวก):** fold-mean correlation แค่
  +0.19 XRP **ไม่**แชร์จุดอ่อน 2023 H2 ของ ETH (2023Q3: XRP +0.34 เทียบ
  ETH −0.40) ราคาจริงสัมพันธ์กัน ~0.8 รายวัน แต่ *P&L ของกลยุทธ์ V0* บน
  XRP เทียบ ETH แทบไม่สัมพันธ์กัน (setup ยิงคนละ regime) ดังนั้น XRP เพิ่ม
  ทั้งโอกาสเทรด**และ**การกระจายความเสี่ยงของ equity curve จริง

**คำตัดสิน:** XRP เป็น candidate จริงแต่เป็น **TIER-2** — อ่อนกว่าและเปราะ
กว่า ETH (WFO 58%, CI แตะศูนย์, หลุดที่ slippage 3x, edge กระจุกไม่กี่
ไตรมาสและอยู่ฝั่ง long) แต่มี correlation กับ strategy return ของ ETH ต่ำ
จริง ถ้าจะเพิ่มต้องจัดการให้เหมาะสม: paper-trade ก่อน, ลด risk_pct (เช่น
0.25% เทียบ ETH ที่ 0.5%), และแก้ shared slippage model ก่อนใช้งานจริง
ไม่ใช่ตัวเทียบเท่า ETH — เป็น satellite ที่ต้องระวัง ไม่ใช่ co-anchor

**การตัดสินใจ:** พัก BTC ไว้ (ไม่มี edge) XRP เป็น candidate เดียวที่หา
เจอสำหรับ symbol ที่ 2 ที่ conviction ลดลง Engineering prerequisite สำหรับ
การเพิ่ม symbol ที่ 2 ใดๆ: (1) แก้ slippage ให้เป็นสัดส่วนราคาใน costs.py
**[เสร็จแล้ว]**, (2) multi-symbol support ใน run_signal_cycle.py
**[เสร็จแล้ว]** — refactor เป็น `SYMBOLS` config list (config +
base_risk_pct ต่อ symbol), แต่ละ symbol รันแยกใน `run_symbol_cycle()`
isolated กัน (symbol หนึ่งพังไม่บล็อกตัวอื่น), และ rolling-winrate risk
guard อ่านประวัติแยกตาม symbol ผ่าน `recent_closed_r_multiples()` แล้ว
**อัปเดต 2026-08-26: XRP เปิดใช้งานจริงแล้ว** (ไม่ใช่ comment ไว้เฉยๆ) —
paper-trade บน demo คู่กับ ETH ที่ risk 0.25% บน VPS จริง (`134.185.81.78`)
ยืนยันแล้วว่า cycle รันทั้งสอง symbol สำเร็จไม่มี error (ดู
[HANDOFF.md](HANDOFF.md) สำหรับสถานะ deploy ล่าสุด)
