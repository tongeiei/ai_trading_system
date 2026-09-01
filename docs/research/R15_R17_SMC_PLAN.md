# R15–R17 — Smart Money Concepts: CHoCH / Order Block / FVG (Research Plan)

เขียน: 2026-08-30 · track: GOLD (XAU/USD spot) · อ่าน `GOLD_HANDOFF.md` + `XAU_YOUTUBE_PLAYLIST.md` ก่อน

> ที่มา: หมวด "Price action / structure — SMC, order blocks, liquidity" ใน
> `XAU_YOUTUBE_PLAYLIST.md` ที่ทีมทำเครื่องหมายว่า **"ระวัง hype มากสุด"** ยังไม่เคย
> แปลงเป็นกฎ deterministic มาก่อน ร่างนี้ตัดดุลยพินิจ (discretionary "zone เจ๋งๆ ด้วยตา")
> ออกให้หมด ผูก mechanism ตามมาตรฐาน track นี้ **คลิป/คอนเซปต์ SMC ไม่ใช่หลักฐาน —
> verdict มาจาก backtest design ล่าง**
>
> **บริบทสำคัญที่ต้องอ่านก่อนลงมือ:** track นี้ falsified ไปแล้ว 5/5 สมมติฐาน (R1, R2, R8,
> R11, R14) — ทุกตัวเป็น mechanical price-action pattern บน m15 spot gold ที่ตายที่ cost
> model สมจริง (spread+slippage) แม้ mechanism story จะฟังขึ้น. CHoCH/OB/FVG เป็น
> price-action pattern ตระกูลเดียวกัน (อ่านจาก swing/wick/gap ไม่ใช่ indicator) — priors
> ควรตั้งไว้ต่ำ ไม่ใช่เพราะ SMC "ผิด" แต่เพราะ**ทุก pattern ที่มองด้วยตาง่ายบน chart มักถูก
> arb ออกไปจนเหลือ edge ต่ำกว่า cost แล้ว**. ทำตาม pipeline เดียวกันแบบไม่มีข้อยกเว้น
>
> ทุก plan เสียบ `run_gold_backtest(signal_fn, spec, start, end)` — signal_fn คืน df คอลัมน์
> `time_utc, close(=entry), action(LONG/SHORT/NO_TRADE), sl_price, tp_price, sl_distance(>0)`
> Data ที่ยืนยันว่ามี: `XAUUSD_{1m,15m,1h}.parquet` (spot 20y). **ไม่ใช้ DXY/news** ทั้งสามตัว

---

## ลำดับความสำคัญ (ทำตามนี้)
1. **R15 (CHoCH)** — เป็น precondition ของ R16 อยู่แล้ว (ต้องนิยาม structure/CHoCH ก่อนจะ
   นิยาม order block ที่ "ทำให้เกิด" CHoCH ได้) ทำก่อนในฐานะ standalone signal
2. **R16 (Order Block)** — ใช้ CHoCH จาก R15 เป็น trigger, entry ที่ OB retest
3. **R17 (FVG)** — mechanism อิสระที่สุดในสามตัว (ไม่ต้องพึ่ง structure) แต่ที่ทำทีหลังเพราะ
   เป็นตัวที่ overlap กับ R11 (wick-fill/imbalance) มากที่สุด — ถ้า R11 falsified เพราะ
   "การเติมช่องว่างราคาไม่มี edge เหนือ mean-reversion เปล่า" ก็มีโอกาสสูงว่า FVG จะซ้ำรอย

---

# R15 — CHoCH (Change of Character)

## 1. นิยาม deterministic ก่อน (ไม่มีในคลิป SMC ส่วนใหญ่ที่นิยามด้วยตา)

**Swing point (fractal แบบเดียวกับ R14):**
```
swing_high ที่แท่ง i  IFF  high_i > high_{i-w..i-1} AND high_i > high_{i+1..i+w}   (w แท่งซ้าย-ขวา)
swing_low  ที่แท่ง i  IFF  low_i  < low_{i-w..i-1}  AND low_i  < low_{i+1..i+w}
```
ยืนยันได้จริงเมื่อผ่านไปแล้ว w แท่ง (ไม่มี look-ahead — ณ เวลาที่ "รู้ว่าเป็น swing" คือ i+w)

**Market structure (state machine ต่อเนื่อง, อัปเดตทีละ swing ที่ยืนยันแล้ว):**
```
เก็บ last_swing_high, last_swing_low, trend ∈ {UP, DOWN, UNKNOWN}
trend เริ่ม UNKNOWN จนกว่าจะเห็น HH+HL (→UP) หรือ LH+LL (→DOWN) ครั้งแรก

BOS (break of structure, "ต่อเทรนด์"):
  ใน UP trend: close ทะลุขึ้นเหนือ last_swing_high → ต่อ UP, อัปเดต last_swing_high
  ใน DOWN trend: close ทะลุลงใต้ last_swing_low → ต่อ DOWN

CHoCH (change of character, "กลับเทรนด์" — นี่คือสัญญาณ):
  ใน UP trend: close ปิด**ต่ำกว่า** last_swing_low (จุด HL ล่าสุดที่ค้ำ uptrend) → trend เปลี่ยนเป็น DOWN
  ใน DOWN trend: close ปิด**สูงกว่า** last_swing_high (จุด LH ล่าสุดที่ค้ำ downtrend) → trend เปลี่ยนเป็น UP
```
ข้อนี้คือความต่างจาก BOS ที่คนสับสนบ่อย: **CHoCH คือแท่งแรกที่ทะลุไปทางตรงข้ามกับเทรนด์เดิม**
ไม่ใช่แค่ pullback — ต้องปิด (close) ทะลุ swing ที่ค้ำโครงสร้างเดิมไว้จริง

## 2. Mechanism (ใครจ่าย)
CHoCH claim ว่าคือจุดที่ **stop-loss ของฝั่งเทรนด์เดิมที่วางไว้หลัง swing กันชนแตก** — trader
ที่ long ตาม uptrend วาง SL ใต้ HL ล่าสุด (ตำแหน่งมาตรฐาน); เมื่อราคาทะลุลงมาปิดใต้จุดนั้น SL
เหล่านั้น trigger เป็น sell market order ต่อเนื่อง (forced liquidation) → ผู้จ่าย = long ที่โดน
stop + คนที่เข้าตามเทรนด์เดิมช้าเกินไป กลไกนี้เหมือน R12 (stop-run) แต่ trigger จาก **โครงสร้าง
สวิงที่นิยามชัด** แทนที่จะเป็น "แท่งแรง" ดิบๆ

Honesty: นี่คือ momentum-continuation-after-break อีกแบบ (ญาติกับ R12 ที่ falsified) — สิ่งที่
ต่างคือนิยาม trigger level จาก swing structure ไม่ใช่ ATR range ต้องพิสูจน์ว่า **swing-based
level ดีกว่า ATR-based level** ไม่งั้นก็แค่ R12 แต่งตัวใหม่

## 3. Rule spec (if/then) — เทรดตาม CHoCH โดยตรง
```
ต่อแท่งปิด i (m15), รัน state machine ด้านบนแบบ online (ไม่ recompute ย้อนหลังทั้งเส้น):

IF CHoCH เกิดที่แท่ง i และเปลี่ยนเป็น trend=UP (นั่นคือ breakout ขึ้นเหนือ last_swing_high เดิม)
  THEN action=LONG ที่ close_i
  sl_price    = min(low ของแท่งที่ทำ CHoCH ทั้งชุด low_{i-m..i})  หรือง่ายกว่า: last_swing_low
                ก่อนหน้า (จุดต่ำสุดที่เพิ่งถูกทะลุขึ้นมา) - buf*atr
  sl_distance = close_i - sl_price
  tp_price    = close_i + tp_r_mult * sl_distance   (grid ตัดสิน r_mult)
mirror สำหรับ SHORT (CHoCH ลง)

filter บังคับ (ตัดสัญญาณรัว/noise):
  min_swing_range: |last_swing_high - last_swing_low| >= k_range * ATR(atr_len)
                   (โครงสร้างต้องมีขนาดพอ ไม่ใช่ noise สวิงเล็กจิ๋ว)
  cooldown: หลัง CHoCH หนึ่งครั้ง ห้าม arm CHoCH ทิศเดิมซ้ำจนกว่าจะมี BOS ยืนยันเทรนด์ใหม่ก่อน
            (กันสัญญาณ whipsaw ตอน state machine แกว่งไปมาในช่วง choppy)
one-trade rule: ไม่ overlap (harness/triple-barrier จัดการ)
session filter: high_liquidity (London/Overlap/NY) เดียวกับ R11
```

## 4. Data
`XAUUSD_15m.parquet` (signal + swing detection) + `1m` (triple-barrier labeling)
ATR จาก `build_features` ถ้ามี ไม่งั้น signal_fn คำนวณ rolling True Range เอง ไม่ต้อง h1/DXY

## 5. Parameter grid (เล็ก, pre-registered)
- `w` (swing confirmation lookback) ∈ {3, 5, 8} — สวิงเล็ก vs ใหญ่ (แกนหลักของนิยาม structure)
- `k_range` ∈ {1.5, 2.5} — กรองสวิง noise ออก
- `tp_r_mult` ∈ {1.0, 1.5, 2.0}
- `direction` ∈ {both, long} — เช็ค long-bias ทองเหมือนทุกตัวก่อนหน้า
- fix: `atr_len=14`, `buf=0.1`, session=high_liquidity, cooldown=on
→ 3×2×3×2 = 36 cells

## 6. Validation design (เหมือนทุก R ก่อนหน้า — ไม่มีข้อยกเว้น)
- Single-config WFO ก่อน (quarterly folds, gate: net PF≥1.10 & ≥60% folds+)
- Sacred holdout: dev 2006–2018, ยืนยัน 2019–2026 (แตะครั้งเดียว, freeze config จากโครงสร้าง)
- Cost stress: base / 2× / 3× spread — ต้องรอด 2× เป็นอย่างน้อย
- Pass = ผ่านทั้ง gate(dev) + plateau + holdout(PF≥1.10, mean_r≥60% ของ dev) + cost 2× + n≥200

## 7. Red flags / kill criteria
- **BASELINE บังคับ (สำคัญที่สุดสำหรับ R15):** เทียบกับ R12 (ATR-range breakout, falsified แล้ว)
  แบบตรงๆ ใช้ WFO fold เดียวกัน — ถ้า CHoCH (swing-based) ไม่ดีกว่า R12 (ATR-based) อย่างมี
  นัยยะ = "นิยาม trigger จาก swing structure" ไม่ได้เพิ่ม edge เหนือ "นิยามจาก ATR" → falsified
  ทั้งคู่เป็นกลไกเดียวกัน (stop-run) แค่วิธี detect level ต่างกัน
- w เล็กสุดชนะเสมอ (สวิงจิ๋วทุกจุด = signal เยอะ) = แค่ noise ไม่ใช่ structure จริง, ตรวจ n/folds
- ถ้า win rate สูงมากแต่ mean_r บาง (TP ใกล้เกิน) = cost กินหมด เหมือน R11 fail mode
- look-ahead check เข้ม: last_swing_high/low ที่ใช้เป็น trigger level ต้องเป็นค่าที่ **ยืนยันแล้ว
  ก่อนแท่ง i** (คือรู้จากแท่ง ≤ i-w) ห้ามใช้ swing ที่เพิ่งเกิดในแท่ง i-1..i-w+1 (ยังไม่ยืนยัน)

---

# R16 — Order Block (retest หลัง CHoCH)

## 1. นิยาม deterministic
**Order block (bullish, สำหรับ setup LONG):** แท่ง (หรือกลุ่มแท่งติดกันทิศเดียวกัน) **ล่าสุดที่
เป็นขาลง (close < open)** ก่อนแท่งที่ทำ CHoCH ขึ้น (นิยามจาก R15) จะเกิดขึ้น กล่าวคือ:
```
ให้แท่ง c = แท่งที่เกิด CHoCH-up (จาก R15 state machine)
เดินย้อนจาก c-1 ถอยหลัง หา"แท่งขาลงติดกันตัวสุดท้าย" ก่อน leg ที่พุ่งขึ้นไปทำ CHoCH
  ob_high = high ของแท่ง(กลุ่ม)นั้น
  ob_low  = low ของแท่ง(กลุ่ม)นั้น
zone = [ob_low, ob_high]   ("โซนคำสั่งซื้อสถาบัน" ตามทฤษฎี — ไม่พิสูจน์ ณ ขั้นนี้ แค่นิยามให้ทดสอบได้)
```
mirror bullish OB → bearish OB (แท่งขาขึ้นก่อน CHoCH-down)

## 2. Mechanism (ใครจ่าย)
ทฤษฎี SMC อ้างว่า zone นี้คือที่ที่ "smart money" วาง order ค้างไว้ (unfilled) ก่อนดันราคาขึ้น
เมื่อราคา retest กลับมาโซนนี้ = order ที่เหลือถูก fill ต่อ ราคาเด้งขึ้นต่อ. **นี่คือจุดอ่อนสุดของ
ทฤษฎีทั้งหมด**: ไม่มีกลไกที่พิสูจน์ได้ว่า order จริงกองอยู่ตรงนั้น (retail มองแท่งเดียวกันไม่มีทาง
รู้ order flow จริง) — mechanism ที่ **น่าเชื่อกว่าและ falsifiable** คือ: zone นี้คือระดับที่คน
short ช่วง OB (ก่อนราคาพุ่ง) ยังไม่ปิดสถานะ + คนที่ตกรถขาขึ้นตั้ง limit buy รอไว้แถวนั้น = **แค่
support/resistance ธรรมดาที่เกิดจาก recency (last down-candle before a big up-move)** ไม่ต่างจาก
"แนวรับแนวต้าน" คลาสสิก ต้องพิสูจน์ว่า **OB retest ดีกว่าการเทรด pullback ธรรมดา** (baseline
บังคับ = R2 ที่เคย test ผ่าน DEV/HOLDOUT แต่ตายที่ cost 2× — เกณฑ์ขั้นต่ำสูงอยู่แล้ว)

## 3. Rule spec (if/then)
```
Setup ต้องมี CHoCH-up ก่อน (จาก R15) → ระบุ bullish OB zone [ob_low, ob_high] ตามนิยามข้างบน
รอราคา retest: แท่งถัดไปหลัง CHoCH ที่ low_j <= ob_high (แตะ/ทะลุเข้าโซนจากบน)
  ภายใน N แท่งหลัง CHoCH (timeout — ถ้าไม่ retest ใน N แท่ง = ยกเลิก setup)
entry: close_j ถ้า close_j > ob_low (ยืนยันไม่หลุดโซนไปเลย) มิฉะนั้น NO_TRADE (โซนถูกทำลาย)
  action = LONG
  sl_price    = ob_low - buf*atr   (ใต้โซนทั้งหมด)
  sl_distance = close_j - sl_price
  tp_price    = close_j + tp_r_mult * sl_distance
mirror สำหรับ SHORT (bearish OB, retest จากล่าง)
one setup ต่อ CHoCH เดียว (ห้าม re-arm ซ้ำถ้า retest แรกไม่เข้าเงื่อนไข)
```

## 4. Data
`XAUUSD_15m.parquet` + `1m`. ต้องมี R15's CHoCH detector เป็น dependency โดยตรง (ใช้โค้ดเดียวกัน
ไม่ implement ซ้ำ — กันความคลาดเคลื่อนระหว่างนิยาม CHoCH ของ R15 vs R16)

## 5. Parameter grid
- ใช้ `w`, `k_range` ที่ **ชนะจาก R15** เท่านั้น (ไม่ grid ซ้ำ — ถ้า R15 falsified ทั้ง grid ให้ใช้
  ค่ากลางของ grid R15 หรือข้าม R16 ไปเลย เพราะไม่มี CHoCH definition ที่ผ่านเกณฑ์ให้ยืนต่อ)
- `N` (retest timeout, แท่ง) ∈ {5, 10, 20}
- `ob_group` (รวมแท่งขาลงติดกันเป็นกลุ่มหรือแท่งเดียว) ∈ {single_candle, merged_run}
- `tp_r_mult` ∈ {1.0, 1.5, 2.0}
- fix: `direction=both`, `buf=0.1`
→ 3×2×3 = 18 cells (ตัด direction ออกจาก grid นี้ ใช้ both คงที่ เพราะ n ต่อ setup ต่ำอยู่แล้ว
  จาก precondition CHoCH)

## 6. Validation design
เหมือนทุก R ก่อนหน้า **แต่มีเงื่อนไขเพิ่ม**: ต้องรอ **R15 ผ่าน DEV gate ก่อน** ถึงจะรัน R16
(ถ้า CHoCH เปล่าไม่มี edge ตั้งแต่ DEV แล้ว การ "กรองด้วย OB retest" บนสัญญาณที่ไม่มี edge ไม่มี
ความหมาย — เหมือนที่ R14 เคยเจอปัญหาเดียวกันกับ R8/R11 จนทีมตัดเงื่อนไข "ต้องชนะ R8/R11" ทิ้ง
เพราะฐานมันขาดทุนอยู่แล้ว — ในกรณีนี้ไม่ตัดเงื่อนไข เพราะ R16 **นิยามจาก** R15 โดยตรง ไม่ใช่แค่
"ต้องชนะ" เฉยๆ ถ้า R15 fail แปลว่า CHoCH ที่ใช้ป้อน R16 ไม่มีความหมายทางสถิติ)

## 7. Red flags / kill criteria
- **BASELINE บังคับ:** เทียบกับ R2 (pullback-to-EMA20, ญาติใกล้สุด — ผ่าน DEV/HOLDOUT แต่ตาย
  cost 2×) ถ้า OB retest ไม่ดีกว่า R2 บน fold เดียวกัน = "โซน OB" ไม่ได้ให้อะไรเกิน pullback
  ธรรมดา → falsified (สอดคล้องกับ mechanism concern ใน §2)
- n น้อยมาก (setup ต้องรอทั้ง CHoCH และ retest ภายใน N แท่ง) — เช็ค n≥200 เข้มเป็นพิเศษ ถ้าไม่ถึง
  ให้รายงานว่า "ไม่พอจะสรุป" ไม่ใช่ปัดเป็น pass/fail มั่ว
- ob_group=merged_run ชนะเพราะ curve-fit ขอบเขต "กลุ่มแท่ง" (definition มีทางเลือกเยอะ) —
  ระวัง experimenter degrees of freedom ตรงนี้สุด ถ้า merged_run ชนะ single_candle ขาดลอย
  ให้สงสัยก่อนว่าเป็น artifact ของการนิยาม ไม่ใช่ edge จริง

---

# R17 — FVG (Fair Value Gap)

## 1. นิยาม deterministic
**Bullish FVG ที่แท่ง i (3-candle pattern มาตรฐาน):**
```
IF low_i > high_{i-2}      (แท่ง i ไม่แตะ high ของแท่ง i-2 เลย — ทิ้งช่องว่างราคาที่ไม่มีใครเทรด)
THEN FVG zone = [high_{i-2}, low_i],  ยืนยันเมื่อแท่ง i ปิด (รู้ทันทีที่ i ปิด ไม่มี look-ahead)
```
mirror bearish FVG: `high_i < low_{i-2}` → zone = `[high_i, low_{i-2}]`

**ข้อแตกต่างจาก R11 (wick-fill) ที่ต้องระบุชัด:** R11 มองไส้ของ**แท่งเดียว** (intra-candle
rejection); FVG มองช่องว่างระหว่าง**สามแท่ง** (inter-candle gap ที่ไม่มี overlap เลย) — คนละกลไก
คนละนิยาม แม้ทั้งคู่จะจบด้วย "ราคาย้อนมาเติมช่องว่าง" เหมือนกัน

## 2. Mechanism (ใครจ่าย)
อ้างว่าช่วงที่ราคาพุ่งเร็วจนข้าม price level บางช่วงไปโดยไม่มีใคร trade ที่นั่น (thin two-way
volume) = **inefficiency ที่ตลาดมักย้อนมาปิด** เพราะ (a) ไม่มี resting liquidity ที่ level นั้น
ทำให้เมื่อราคาย้อนมาถึงมันไหลผ่านไว (ไม่มีแรงต้าน) และ (b) หลายฝ่ายในตลาด (algo + retail SMC
crowd) ต่างรู้จัก pattern นี้และตั้ง limit order รอ "เติมช่องว่าง" ไว้ล่วงหน้า → **self-fulfilling
ระดับหนึ่ง** ผู้จ่าย = ไม่ชัดเจนเท่า CHoCH/OB (ไม่มี stop-run บังคับ) — เป็น mechanism ที่**อ่อน
ที่สุดในสามตัว** เพราะพึ่ง "ตลาดเชื่อ pattern เดียวกัน" มากกว่ากลไกบังคับจาก stop-loss

## 3. Rule spec (if/then)
```
ตรวจ FVG ทุกแท่งปิด i ตามนิยาม §1
เมื่อเจอ bullish FVG (zone [high_{i-2}, low_i]):
  รอราคา retest: แท่ง j > i ที่ low_j <= low_i (แตะขอบบนของ gap จากบนลงมา)
                 ภายใน N แท่ง (timeout)
  entry: close_j ถ้า close_j > high_{i-2} (ยังไม่ทะลุปิด gap เต็ม — ถ้าปิดต่ำกว่านั้นคือ gap
         โดนกลืนหมดแล้ว ไม่ fade)
  action = LONG at close_j
  sl_price    = high_{i-2} - buf*atr   (ใต้ gap ทั้งโซน)
  sl_distance = close_j - sl_price
  tp_price    = close_j + tp_r_mult * sl_distance
mirror สำหรับ SHORT (bearish FVG, retest จากล่างขึ้นบน)
gap_size filter: (low_i - high_{i-2}) >= k_gap * ATR(atr_len)  (gap เล็กจิ๋วเกิน = noise ปกติ
  ของราคา ไม่ใช่ imbalance จริง — mirror เงื่อนไข k_wick ของ R11)
one setup ต่อ gap เดียว, ไม่ arm ซ้ำถ้า retest แรกพลาด (gap ถูกกลืนแล้ว = จบ)
session filter: high_liquidity เดียวกับ R11/R15
```

## 4. Data
`XAUUSD_15m.parquet` + `1m`. ATR จาก `build_features` ถ้ามี ไม่งั้น signal_fn คำนวณเอง

## 5. Parameter grid
- `k_gap` ∈ {0.3, 0.5, 0.8} — ขนาด gap ขั้นต่ำเทียบ ATR (แกนหลัก)
- `N` (retest timeout, แท่ง) ∈ {5, 10, 20}
- `tp_r_mult` ∈ {1.0, 1.5, 2.0}
- `direction` ∈ {both, long}
- fix: `atr_len=14`, `buf=0.1`, session=high_liquidity
→ 3×3×3×2 = 54 cells (ตัดเหลือ 27 โดย fix tp_r_mult=1.5 ตอน dev-explore ก่อน ถ้าจำเป็นต้อง
  ประหยัดเวลา compute — แต่ตัวสุดท้ายที่ใช้ยืนยัน holdout ต้องรัน grid เต็ม)

## 6. Validation design (เหมือนทุก R ก่อนหน้า — ไม่มีข้อยกเว้น)
- Single-config WFO ก่อน (quarterly folds, gate: net PF≥1.10 & ≥60% folds+)
- Sacred holdout: dev 2006–2018, ยืนยัน 2019–2026
- Cost stress: base / 2× / 3× — ต้องรอด 2× เป็นอย่างน้อย
- Pass = gate(dev) + plateau + holdout(PF≥1.10, mean_r≥60% ของ dev) + cost 2× + n≥200

## 7. Red flags / kill criteria
- **BASELINE บังคับ (สำคัญที่สุดสำหรับ R17):** เทียบกับ R11 (wick-fill, falsified แล้ว) บน
  fold เดียวกัน — ทั้งคู่คือ "fade การเคลื่อนไหวเร็วที่ทิ้ง imbalance ไว้" ถ้า FVG ไม่ดีกว่า R11
  อย่างมีนัยยะ = ยืนยันซ้ำว่า "การเติม imbalance" ไม่มี edge เหนือ mean-reversion เปล่า
  (R11 เคยเจอผลนี้แล้ว: baseline mean-rev เปล่าก็ PF ใกล้เคียงกัน — ต้องเช็คแบบเดียวกันที่นี่)
- **เทียบ mean-reversion baseline เปล่าด้วย** (เหมือน R11 §6) ไม่ใช่แค่เทียบ R11 — เผื่อทั้งคู่
  แพ้ baseline พร้อมกัน (คือกลไกร่วม "การเทรดสวนหลังพุ่งแรง" ไม่มี edge เลยบนทองที่ timeframe นี้)
- k_gap เล็กสุดชนะเสมอ (นับ gap จิ๋วทุกจุดเป็นสัญญาณ) = noise, ไม่ใช่ edge — เช็ค n/folds
- ถ้า pass แต่ **overlap สูงกับ R11 ในเชิงเวลาเข้า** (เช็คว่า FVG setup กับ wick-fill setup ชน
  เวลาเดียวกันบ่อยแค่ไหน) = อาจเป็นสัญญาณเดียวกันที่นิยามคนละแบบ ไม่ใช่ edge อิสระใหม่

---

## สรุปก่อนเริ่ม backtest จริง

ลำดับการรัน: **R15 ก่อน (standalone, ไม่ต้องพึ่งอะไร) → ถ้าผ่าน DEV gate ค่อยทำ R16 (ต่อยอด R15)
→ R17 ทำคู่ขนานได้เลยเพราะไม่ dependency กับ R15/R16** (แต่ priority ต่ำสุดเพราะ mechanism อ่อน
สุดและ overlap กับ R11 ที่ตายไปแล้วมากสุด)

**ข้อควรระวังภาพรวม (ย้ำจาก header):** ทั้งสามตัวอยู่ในตระกูล "pattern ที่มองด้วยตาบน chart"
เดียวกับ R1/R11/R12/R14 ที่ falsified มาแล้ว 4/5 ของ track นี้ ถ้าผล R15–R17 ออกมาเป็น falsified
เพิ่มอีก ก็ **สอดคล้องกับ pattern ที่เห็นมาตลอด** ไม่ใช่เรื่องแปลก — คุ้มที่จะทดสอบเพราะยังไม่เคย
ทำ (unknown ≠ ควร skip) แต่ไม่ควรตั้งความหวังสูงกว่า R1–R14 ที่ผ่านมา
