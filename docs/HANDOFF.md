# Handoff — AI Trading System (ปรับทิศทางเป็น crypto)

อัปเดตล่าสุด: 2026-08-25 อ่านไฟล์นี้ก่อนเป็นอันดับแรกทุกครั้งที่เริ่ม session ใหม่ ก่อนแตะโค้ด

## โปรเจกต์นี้คืออะไร

เดิมออกแบบไว้สำหรับ XAU/USD ผ่าน MT5 (ดู PIVOT NOTICE ที่หัวไฟล์
PROJECT_PLAN.md) แล้วปรับทิศทางมาเป็น **Binance Futures crypto perpetuals**
เพราะ lot-size ขั้นต่ำของ MT5 ทำให้ risk sizing 1% เป็นไปไม่ได้บนบัญชี 2,000
บาท PROJECT_PLAN.md §0-§21 ยังคงเป็นแผนยุค XAU/MT5 (เก็บไว้อ้างอิง)
รายละเอียดการทำงานจริงของฝั่ง crypto อยู่ในโค้ด + docs/ ของ repo นี้ ไม่ได้อยู่
ใน PROJECT_PLAN.md

**อ่าน `docs/FINDINGS.md` ก่อนรัน backtest/งานวิจัยซ้ำทุกครั้ง — มันบันทึกไว้ว่า
อะไรเคยลองแล้วและถูกปฏิเสธไปแล้วบ้าง เพื่อไม่ให้ทำงานซ้ำ**

## โครงสร้างพื้นฐานปัจจุบัน (รันอยู่จริงทั้งหมด)

- **VPS**: Oracle Cloud Free Tier, Ubuntu 24.04, `134.185.81.78`, user `ubuntu`
  - SSH key: `~/.ssh/oracle_trading_vps.key` (อยู่บน dev Mac, ไม่ commit เข้า git)
  - ผ่านการ harden: UFW (เปิดแค่ port 22), fail2ban, SSH แบบ key-only เท่านั้น,
    ปิด root login, ปิด auto-reboot ของ unattended-upgrades
- **Repo**: `https://github.com/tongeiei/ai_trading_system` (public), clone ไว้
  ที่ `~/ai_trading_system` บน VPS, sync ผ่าน `git pull`
- **systemd units** (`/etc/systemd/system/`, ต้นฉบับอยู่ใน `deploy/`):
  - `signal-cycle.timer` + `.service` — รัน `scripts/run_signal_cycle.py`
    ทุกครั้งที่แท่ง M15 ปิด (`OnCalendar=*:0/15:30`)
  - `dashboard.service` — Streamlit dashboard, รันตลอด, bind แค่
    `127.0.0.1:8501` (ดูผ่าน SSH tunnel: `ssh -i ~/.ssh/oracle_trading_vps.key -N -L 8501:127.0.0.1:8501 ubuntu@134.185.81.78` แล้วเปิด `http://localhost:8501`)
- **Binance**: ใช้ testnet/demo trading เท่านั้น (`enable_demo_trading(True)`
  ผ่าน ccxt) — ยังไม่มีเงินจริงที่ไหนเลย API key อยู่ใน `.env` ทั้งบน dev Mac
  และ VPS (ไม่ commit เข้า git)
- **key ที่ต้องมีใน `.env`**: `BINANCE_TESTNET_API_KEY`, `BINANCE_TESTNET_API_SECRET`,
  และถ้าจะใช้แจ้งเตือน `LINE_CHANNEL_ACCESS_TOKEN` + `LINE_TARGET_ID` (ดูหัวข้อ
  "ขั้นต่อไปที่ต้องทำ" ด้านล่าง)

## สถานะกลยุทธ์ — อะไรพิสูจน์แล้ว อะไรยังไม่

- **Symbol**: ETH/USDT:USDT เท่านั้น (BTC/SOL/BNB เทสแล้วถูกปฏิเสธ — ไม่มี
  edge ในรอบแรก; ดู `docs/FINDINGS.md` สำหรับ round สอง — XRP เป็น tier-2
  candidate ที่กำลัง paper-trade อยู่ ส่วน BTC ยัง shelved)
- **Config (locked)**: EMA-pullback V0 rules, `ADX_threshold=35`, `SL=2.5x ATR`,
  `TP=2x SL` ห้าม tune ใหม่โดยไม่มี holdout ใหม่ที่แยกจากเดิมจริงๆ — ดู
  docs/FINDINGS.md ว่าทำไม การ re-tune แบบเฉพาะกิจถึงเผาผลาญ config ไปหลาย
  ชุดแล้วบนข้อมูลชุดเดียวกัน
- **ML (LightGBM)**: เทสแล้วถูก**ปฏิเสธ**ที่ gate P5 — AUC ~0.497 บน holdout
  แยกไม่ออกจาก noise ห้ามเอา "AI probability" display หรือ gate กลับมาใช้อีก
  `src/live/ev_estimate.py` ใช้ base rate จาก backtest ประวัติศาสตร์แทน ไม่ใช่
  ML อย่างชัดเจน และ label ไว้แบบนั้นทุกที่ (dashboard, comment ในโค้ด)
- **ผล walk-forward (สำคัญ)**: edge เป็นของจริงแต่**ไม่เสถียร** 8/12 quarterly
  fold เป็นบวก มีแค่ 2/12 ที่ significant ทางสถิติจริงๆ และ 2023 H2 ติดลบอย่าง
  significant (regime whipsaw/vol สูง) เพราะเหตุนี้จึงลด base risk จากแผนเดิม
  1-2% เหลือ **0.5%** (`base_risk_pct` ต่อ symbol ใน `scripts/run_signal_cycle.py`)
- มี rolling win-rate guard (`rolling_winrate_risk_multiplier` ใน
  `src/live/guards.py`) ที่ลด risk ลงครึ่งหนึ่งอัตโนมัติถ้า win rate ของ 20
  เทรดปิดล่าสุด (ต่อ symbol) ต่ำกว่า 30% — เป็น early warning ที่จำลองจาก
  failure mode ของ 2023 H2 จะ trigger ก่อนที่ threshold DD/daily-loss จะทำงาน

## สิ่งที่ implement แล้ว (เทสครบ, unit test ผ่านทั้งหมด)

```
src/data/           binance_loader, funding_rate_loader, db (SQLite schema)
src/features/        engine.py — 12 features, เทสเรื่อง data leakage แล้ว
src/regime/          rules.py — ตัวจำแนก TREND/RANGE
src/strategy/        v0_rules.py (config ที่ล็อกไว้), breakout.py, mean_reversion.py (ทั้งคู่ถูกปฏิเสธ)
src/labeling/        triple_barrier.py
src/backtest/        costs.py (slippage เป็นสัดส่วนราคาแล้ว), significance.py (bootstrap test)
src/models/          train.py, calibrate.py — LightGBM pipeline เก็บไว้อ้างอิง ไม่ได้ใช้จริง
src/risk/            sizing.py — position sizing, เทส anti-martingale แล้ว
src/live/
  order_executor.py    วางไม้ entry+SL+TP (exchange-native algo order),
                        fetch_open_algo_orders (ccxt มองไม่เห็น order พวกนี้ตรงๆ — มี workaround)
  guards.py            guard: spread/ข้อมูลค้าง/heartbeat/retry-limit/winrate
  reconcile.py         ตรวจจับ position กำพร้า (CRITICAL ถ้า position ไม่มี SL)
  position_timeout.py  บังคับปิดที่ 12 ชม. + ตรวจจับ SL/TP ที่ยิงเองบน exchange
  ev_estimate.py       EV gate จาก historical stats (ไม่ใช่ ML — ดูด้านบน)
  alerting.py          แจ้งเตือนผ่าน LINE Messaging API (ต้องมี LINE_CHANNEL_ACCESS_TOKEN
                        + LINE_TARGET_ID)
  logging_store.py     helper แบบ log-ก่อน-execute ลง signals/orders/trades/risk_decisions,
                        มี recent_closed_r_multiples() แยกตาม symbol
  signal_service.py    ดึง OHLCV สด + สร้าง feature/regime/signal
src/dashboard/app.py  Streamlit — heartbeat, กราฟแท่งเทียนพร้อม marker เทรด,
                       แผง EV, equity curve, ตาราง trades/signals/risk-decision
```

## สถานะปัจจุบัน (อัปเดต 2026-08-26)

**Multi-symbol เปิดใช้งานแล้ว**: `scripts/run_signal_cycle.py` refactor เป็น
`SYMBOLS` config list — แต่ละ symbol รันแยก cycle isolated กัน (symbol หนึ่งพัง
ไม่กระทบตัวอื่น) ตอนนี้รัน **ETH (risk 0.5%) + XRP (risk 0.25%, paper-trade,
tier-2 candidate)** พร้อมกัน ดู `docs/FINDINGS.md` ส่วน "2nd-symbol search"
สำหรับหลักฐานเบื้องหลังการเลือก XRP และเหตุผลที่ BTC ถูกพักไว้

**แจ้งเตือน**: LINE Messaging API ตั้งค่าและใช้งานได้แล้ว (Discord ถูกเลิกใช้
เพราะ LINE Notify ถูกปิดบริการปลายเดือนมีนาคม 2025) `alert_trade_opened` /
`alert_trade_closed` / `alert_critical` / `alert_error` ยิงแบบ real-time ทันที
ที่มีเหตุการณ์ — เป็นช่องทางเดียวที่ real-time จริงๆ, dashboard ต้องกด
refresh เอง (cache 30 วินาที ไม่มี auto-refresh loop)

## ช่องว่างที่ยังมี / to-do แบบตรงไปตรงมา

- ยังไม่มีเทรดเกิดขึ้นจริงบน demo — ETH อยู่ใน regime RANGE ต่อเนื่องมาตั้งแต่
  ระบบอัตโนมัติเริ่มทำงาน (~2026-08-24) ซึ่งทางสถิติไม่ใช่เรื่องผิดปกติ (ดูบท
  สนทนา: P(ไม่มีเทรดใน 71 แท่ง) ≈ 6-19% แล้วแต่ window ไม่ใช่ bug)
- Mainnet shadow (Phase B ตัวจริง ตาม 5-layer testing framework ที่เคยคุยไว้)
  ยังไม่เกิดขึ้น — ทุกอย่างตอนนี้รันบน demo trading ไม่ใช่กับความลึกของ
  orderbook จริงบน mainnet ต้นทุน execution จริง (spread/slippage) ยังเป็น
  สมมติฐานจาก cost model ของ backtest ไม่ได้วัดจากของจริง
- ยังไม่มีการเช็ค robustness จากการตัด 2 เดือนที่ผลดีผิดปกติ (ส.ค. 2025,
  ส.ค. 2026) ออกจาก walk-forward — เคย flag ไว้เป็นขั้นต่อไป แต่ยังไม่ได้ทำ
- `docs/TASKS.md` ยังสะท้อนโครงสร้าง phase ของยุค MT5/XAU เดิมอยู่ — ยังไม่ได้
  เขียนใหม่สำหรับการปรับทิศทางมา crypto นอกเหนือจากส่วน P0
- Slippage bug ที่แก้ไปแล้ว (`src/backtest/costs.py` เดิมใช้ 0.5 USD/side คงที่
  ผิดกับ coin ราคาต่ำ) ตอนนี้เป็นสัดส่วนราคาแล้ว (`SLIPPAGE_BPS`) และ ETH edge
  ถูก re-confirm แล้วว่าไม่เปลี่ยน — ดู FINDINGS.md
