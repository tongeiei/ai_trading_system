# Handoff — XAU/USD live track (เตรียมเครื่อง/บัญชี ก่อน refactor)

อัปเดตล่าสุด: 2026-09-03 · อ่านไฟล์นี้ก่อนเริ่มงาน XAU live-prep ทุกครั้ง

แยกจาก:
- `docs/research/GOLD_HANDOFF.md` — เรื่อง backtest hypothesis testing ล้วนๆ (R1-R17, 8/8 falsified แล้ว) ยังไม่แตะ live/paper/เครื่องจริง
- `docs/HANDOFF.md` — ETH/XRP live track ที่รันอยู่บน Oracle VPS แยกกันคนละ track

## เป้าหมายของ track นี้

เตรียมโครงสร้างพื้นฐาน (broker, บัญชี, เครื่อง, MT5 connectivity) ให้พร้อมสำหรับเทรด
XAU/USD live ตามลำดับ phase ใน `docs/XAU_ARCHITECTURE_AUDIT.md` §10 (P0-P13) — **ตอนนี้
อยู่ในขั้น "เตรียมของก่อน" ตามคำสั่งผู้ใช้ 2026-09-02 (ยังไม่เริ่มแก้/เขียนโค้ด P2)**

## การตัดสินใจที่ล็อกแล้ว (2026-09-02, แก้ไข 2026-09-03)

| หัวข้อ | ค่าที่เลือก |
|---|---|
| Broker / ประเภทบัญชีจริง (live) | Exness — **Standard Cent** (ไม่เปลี่ยนจากเดิม) |
| บัญชี demo ที่ใช้เทสตอนนี้ | Exness — **Standard** (ไม่ใช่ Cent) เพราะ **Exness ไม่มี Cent account แบบ demo ให้เปิด** — ใช้ Standard demo แทนเพื่อเทส connectivity/order flow เท่านั้น, max leverage **1:2000** |
| ทุนเริ่มทดลอง | $10 USD (บนบัญชี live/Cent จริง) |
| LLM สำหรับ P6 (Setup Quality Scorecard) | DeepSeek, งบ **$10/เดือน** |
| Deploy target | **PC Windows เครื่องนี้** (ไม่ใช่ Oracle VPS) — ETH/XRP ยังรันแยกบน VPS ต่อไปตามเดิม |

⚠️ **สลับ demo account เป็น Exness Standard เมื่อ 2026-09-03** (Exness ไม่มี Cent demo) —
เช็ค spec จริงแล้ว (ดูหัวข้อ "สถานะเครื่อง" ด้านล่าง): `XAUUSDm` บน Standard demo มี
`contract_size=100`, `volume_min=0.01` lot — เหมือนปัญหา lot-size เดิมจาก PROJECT_PLAN.md
§0.1 เป๊ะ **แต่นี่คือ spec ของ Standard ไม่ใช่ Cent** บัญชีจริงที่จะใช้เทรดยังคงเป็น
**Standard Cent** ตามแผนเดิม ซึ่งควรมี `volume_min`/`contract_size` เล็กกว่านี้ ~100 เท่า
(หน่วยเป็นเซนต์) — **ยังไม่มีทางเช็ค spec ของ Cent account จริงได้จนกว่าจะเปิดบัญชี Cent จริง**
เพราะไม่มี Cent demo ให้ทดสอบ ต้องรับความเสี่ยงนี้ไว้จนกว่าจะเปิดบัญชีจริงแล้วเช็คหน้างาน

## สถานะเครื่อง — เสร็จแล้ว (2026-09-02)

- ติดตั้ง **Python 3.13.7** ผ่าน `winget install --id Python.Python.3.13 --version 3.13.7`
  (ตรงกับที่ระบุใน `requirements.txt`/audit doc)
- สร้าง `.venv` ที่ root ของ repo, ติดตั้ง `requirements.txt` ครบ **ยกเว้น `uvloop`**
  (ไม่รองรับ Windows, grep แล้วไม่มีที่ไหน import ใช้จริง — เป็น transitive dep จาก
  `pip freeze` บน Mac/VPS เดิม) `ccxt` ดึง `winloop` มาแทนเองอัตโนมัติบน Windows
- `pytest tests -q` ผ่าน **52/52** บน Windows/Python 3.13.7
  ⚠️ bare `pytest` (ไม่ระบุ path) จะไปเก็บ `scripts/test_*.py` มาด้วย (ต้องมี `.env`/network,
  ทำให้ collection พังทันที) — ต้องรัน `pytest tests` เจาะจงเสมอ
- เจอ **Windows Application Control / Smart App Control บล็อกการโหลด `.pyd` ของ pandas**
  ("An Application Control policy has blocked this file") — ผู้ใช้ปิด policy นี้แล้ว แก้ได้
- ติดตั้ง `MetaTrader5` pip package แล้วทดสอบครบวงจรบนบัญชี `MetaQuotes-Demo`:
  - `mt5.initialize()` / `symbol_info()` / `symbol_info_tick()` — ผ่าน
  - `copy_rates_from()` ดึง M15 OHLCV ย้อนหลัง — ผ่าน
  - `order_send()` เปิด + ปิด position (BUY 0.01 lot `XAUUSD` พร้อม SL/TP) — ผ่าน
    (ต้องเปิด **AutoTrading** ปุ่ม toolbar + **Tools→Options→Expert Advisors→Allow
    algorithmic trading** ใน terminal ก่อน ไม่งั้นได้ retcode 10027 CLIENT_DISABLED)
- บน `MetaQuotes-Demo`, symbol `XAUUSD` เป็น **standard spec**: `contract_size=100`,
  `volume_min=0.01` lot (=1 oz), `tick_value=0.1` — คือปัญหา lot-size เดิมจาก
  PROJECT_PLAN.md §0.1 เป๊ะๆ ยืนยันว่าต้องรอ Exness cent account จริงถึงจะได้ spec
  ที่ risk sizing ทำงานได้บนทุน $10
- **(2026-09-03)** เช็คบน Exness Standard demo จริงแล้ว (`mt5.account_info()` /
  `mt5.symbol_info()`): login `463906588`, server `Exness-MT5Trial17`, balance $500,
  leverage 1:2000. Symbol ที่มีคำว่า XAU ทั้งหมด: `BTCXAUm`, `XAUAUDm`, `XAUEURm`,
  `XAUGBPm`, `XAUUSDm`, `XAUUSD247m` — **`XAUUSDm`**: `contract_size=100`,
  `volume_min=0.01` lot, `tick_value=0.1`, spread ~260 points (~$0.26) ณ ตอนเช็ค —
  **เหมือน `MetaQuotes-Demo` เป๊ะ ยืนยันปัญหา lot-size เดิมของบัญชี Standard**
  (0.01 lot ขั้นต่ำ = risk ~$10-20/ไม้ที่ SL ทั่วไปของทอง M15 ⇒ เกินทุน $10 ทั้งก้อน)
  **แต่นี่คือ spec ของบัญชี Standard demo เท่านั้น** ไม่ใช่บัญชี Cent ที่จะใช้เทรดจริง —
  Exness ไม่มี Cent demo ให้เปิด จึงยังไม่มีทางยืนยัน spec ของ Cent account จริงได้
  ก่อนเปิดบัญชีจริง (ดู "การตัดสินใจที่ล็อกแล้ว" ด้านบน)

## ยังไม่ทำ / ต้องทำต่อ

- [x] เปิดบัญชี **Exness demo (Standard, 1:2000)** แล้ว login MT5 terminal เข้าบัญชีนั้นแทน
      `MetaQuotes-Demo` (2026-09-03) — ใช้ Standard เพราะ Exness ไม่มี Cent demo
- [x] เช็ค symbol spec ของทองบน Exness Standard แล้ว (2026-09-03) — ผลอยู่ในหัวข้อ
      "สถานะเครื่อง" ด้านบน: ยืนยันปัญหา lot-size เดิมบน **Standard** account
      **ยังค้างอยู่**: เช็ค spec ของ **Cent account จริง** (ต้องรอเปิดบัญชี live ก่อน
      เพราะไม่มี Cent demo) ก่อนเชื่อว่า risk sizing บนทุน $10 ทำงานได้จริง
- [x] **ETH/XRP บน VPS — freeze แล้ว** (ตัดสินใจ 2026-09-03, ผู้ใช้ยืนยันว่า freeze จริงบน VPS
      เรียบร้อยแล้ว — ทำเองผ่าน SSH เพราะ Claude ไม่มี SSH key ของ VPS นี้ในเครื่อง Windows)
      ⚠️ ยังไม่ได้ตรวจสอบผ่าน tool ว่า `signal-cycle.timer` หยุดจริงบน VPS (เชื่อคำยืนยันของ
      ผู้ใช้) — ถ้าต้องการ verify ทีหลัง เช็คด้วย
      `ssh -i ~/.ssh/oracle_trading_vps.key ubuntu@134.185.81.78 "systemctl status signal-cycle.timer"`
- [x] ~~เลือก economic calendar data source~~ — **ตัดออกจาก scope ทั้งหมดแล้ว (2026-09-03)**
      ผู้ใช้ตัดสินใจไม่ทำ NFP/news blackout ในระบบนี้เลย (ดู
      `docs/XAU_ARCHITECTURE_AUDIT.md` §15 ข้อ 10) — ⚠️ trading window เดิม
      (01:00–15:00 UTC) ยังคาบเกี่ยว NFP release (12:30–13:30 UTC) โดยไม่มีการป้องกันใด ๆ
      อีกต่อไป เป็น trade-off ที่รับทราบแล้ว ไม่ใช่ของตกหล่น
- [ ] ยังไม่เริ่ม **P2** (XAU data pipeline refactor: เพิ่ม M5/H4 + validation layer) — รอ
      symbol-spec check บน Exness Standard ให้เสร็จก่อน ตาม §15 ของ audit doc
      (broker/บัญชี audit ผูกไว้กับ P8 แต่ในทางปฏิบัติควรปิดก่อน เพราะกระทบ
      position-sizing math ตั้งแต่ P2)

## อ้างอิง

- `docs/XAU_ARCHITECTURE_AUDIT.md` §10 (migration plan 13 phases), §13 (risks), §15
  (คำตอบ/open items), §17 (สถานะเอกสาร)
- `docs/research/GOLD_HANDOFF.md` — ผล backtest 8/8 falsified (คนละเรื่องกับ track นี้)
- `PROJECT_PLAN.md` §0.1-0.2 — ที่มาของปัญหา lot size / เหตุผลที่เคยเลือก cent account
  (ตอนนี้เปลี่ยนมาใช้ Exness Standard แทนแล้ว — ต้องเช็ค spec ซ้ำว่าปัญหานี้ยังอยู่หรือไม่)
