# Task: Refactor Existing Trading Project into XAU/USD AI 24/7 Architecture

คุณกำลังทำงานกับ **existing trading project/repository** ที่มี code, strategy, backtest, data pipeline และ infrastructure อยู่แล้ว

เป้าหมายคือ **ไม่ใช่การเขียน project ใหม่จากศูนย์** แต่ให้ตรวจสอบ project เดิมก่อน แล้ว refactor/extend ให้กลายเป็นระบบ:
ตั้งชื่อ 24/7 ก็จริงแต่มีเวลาให้ agent ทำงาน จ-ศ ตามเวลาตลาดเปิดและปิด คิดไว้ว่าจะตั้งรัน 8:00-22:00 และไม่เทรดวัน non-farm pay role

> **XAU/USD AI 24/7 Research + Market Monitoring + Signal Analysis + Risk Management + MT5 Execution System**

---

# 1. IMPORTANT RULES

ก่อนแก้ code ใด ๆ:

1. อ่าน repository ทั้งหมดที่เกี่ยวข้อง
2. วิเคราะห์ architecture ปัจจุบัน
3. หา entry points ของ application
4. หา data pipeline
5. หา strategy / signal generation
6. หา backtesting
7. หา configuration
8. หา database
9. หา broker / MT5 integration
10. หา scheduler / cron / worker
11. หา logging / monitoring
12. หา existing AI/LLM integration
13. หา test suite

**ห้าม rewrite project ทั้งหมดทันที**

ต้องรักษา code ที่มีคุณค่าอยู่แล้ว และ refactor เฉพาะส่วนที่จำเป็น

---

# 2. FIRST OUTPUT — EXISTING PROJECT AUDIT

ก่อน implement ให้สร้างเอกสาร:

`docs/XAU_ARCHITECTURE_AUDIT.md`

โดยอธิบาย:

```text
Current Architecture
Current Components
Current Data Flow
Current Strategy Flow
Current Execution Flow
Current AI Integration
Current Database
Current Infrastructure
Current Scheduler
Current Monitoring
Current Tests
Technical Debt
Reusable Components
Components That Should Be Replaced
Components That Should NOT Be Touched
```

ทำ mapping:

```text
CURRENT PROJECT
       ↓
TARGET ARCHITECTURE
       ↓
KEEP / MODIFY / REPLACE / NEW
```

---

# 3. TARGET ARCHITECTURE

เป้าหมายคือ:

```text
                         XAU/USD
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Market Data Engine   │
                 │        24/7          │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Data Validation      │
                 │ Normalization        │
                 │ Time Synchronization │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Feature Engine      │
                 │                     │
                 │ ATR                 │
                 │ ADX                 │
                 │ EMA                 │
                 │ Structure           │
                 │ FVG                 │
                 │ Liquidity Sweep     │
                 │ Session             │
                 │ Volatility          │
                 │ Spread              │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Regime Detection    │
                 │                     │
                 │ TREND               │
                 │ RANGE               │
                 │ EXPANSION           │
                 │ HIGH VOLATILITY     │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ Setup Scanner       │
                 │                     │
                 │ Trend Pullback      │
                 │ Breakout            │
                 │ FVG                 │
                 │ Liquidity Sweep     │
                 │ Mean Reversion      │
                 │ Volatility Expansion│
                 │ Session Strategy    │
                 └──────────┬──────────┘
                            │
                     Setup detected?
                       │           │
                      NO          YES
                       │           │
                      WAIT         ▼
                           ┌─────────────────┐
                           │ Fast AI Agent   │
                           │ Claude or other │
                           │                 │
                           │ Setup Screening │
                           │ Context Check   │
                           └────────┬────────┘
                                    │
                              High Quality?
                               │          │
                              NO         YES
                               │          │
                              WAIT        ▼
                            ┌─────────────────┐
                            │ Strong AI Agent │
                            │ Claude Sonnet   │
                            │                 │
                            │ Deep Analysis   │
                            │ Macro Context   │
                            │ Trade Thesis    │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Risk Engine     │
                            │                 │
                            │ Position Size   │
                            │ Stop Loss       │
                            │ Take Profit     │
                            │ Daily Risk      │
                            │ Drawdown        │
                            │ Kill Switch     │
                            └────────┬────────┘
                                     │
                               APPROVE / REJECT
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Execution Engine │
                            │                 │
                            │ MT5             │
                            │ Order           │
                            │ Position        │
                            │ Stop Management │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Trade Journal   │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Performance     │
                            │ Attribution     │
                            └────────┬────────┘
                                     │
                                     ▼
                            ┌─────────────────┐
                            │ Research Loop   │
                            │                 │
                            │ Hypothesis      │
                            │ Backtest        │
                            │ WFO             │
                            │ OOS             │
                            └─────────────────┘
```

---

# 4. CORE PRINCIPLE

อย่าให้ LLM เป็น trading engine โดยตรง

ใช้:

```text
Python / deterministic code
        ↓
Market calculation
        ↓
Feature generation
        ↓
Regime detection
        ↓
Setup detection
        ↓
LLM analysis
        ↓
Risk engine
        ↓
Execution
```

LLM มีหน้าที่:

* วิเคราะห์ context
* วิเคราะห์ setup
* ประเมิน quality
* วิเคราะห์ macro/news
* สร้าง trade thesis
* ตรวจสอบ conflicting signals

LLM **ไม่มีสิทธิ์ bypass Risk Engine**

---

# 5. 24/7 MARKET MONITOR

ระบบต้องทำงาน 24/7 บน VPS

แต่ **ห้ามเรียก LLM ทุก tick**

Architecture:

```text
Market Tick
   ↓
Python Engine
   ↓
Update State
   ↓
Candle Close
   ↓
Feature Calculation
   ↓
Rule-based Filters
   ↓
Setup?
   │
   ├── NO → WAIT
   │
   └── YES
          ↓
       AI Agent
```

สำหรับเริ่มต้น:

```text
M1  = market monitoring
M5  = setup detection
M15 = primary decision timeframe
H1  = regime/context
H4  = higher-level context
```

อย่าเพิ่ม timeframe หากไม่มี research justification

---

# 6. AI MODEL ARCHITECTURE

ใช้ Multi-Agent / Multi-Model

## Agent 1 — Market Monitor

Model:

**Claude Haiku-class / fastest economical model**

หน้าที่:

```text
Market state
Volatility
Session
Anomaly
Setup screening
Context summarization
```

ต้องไม่ถูกเรียกทุก tick

เรียกเมื่อเกิด:

```text
M5 candle close
setup detected
regime changed
volatility spike
important event
```

---

## Agent 2 — Trade Analyst

Model:

**Claude Sonnet-class**

เรียกเฉพาะเมื่อ setup ผ่าน initial filter

Input:

```text
Market structure
Current price
M5/M15/H1 context
Indicators
Volatility
Session
Spread
Setup
Recent candles
Macro context
News context
Historical statistics
```

Output ต้องเป็น structured JSON เช่น:

```json
{
  "decision": "LONG | SHORT | NO_TRADE",
  "confidence": 0,
  "setup_quality": 0,
  "market_regime": "",
  "thesis": "",
  "invalidation": "",
  "risk_factors": [],
  "reasons": []
}
```

ห้ามให้ model ส่ง order โดยตรง

---

## Agent 3 — Research Agent

Model:

**Claude Opus-class**

ไม่จำเป็นต้อง run continuously

ใช้สำหรับ:

```text
Strategy research
Hypothesis generation
Backtest analysis
Trade review
Failure analysis
Parameter sensitivity
Walk-forward analysis
Research reports
```

---

# 7. REGIME ENGINE

สร้าง module แยก:

```text
src/regime/
```

เริ่มจาก deterministic/rule-based ก่อน

ตัวอย่าง:

```text
TREND
RANGE
VOLATILITY_EXPANSION
HIGH_VOLATILITY
UNKNOWN
```

ห้ามใช้ LLM เป็นตัวคำนวณ regime โดยตรงถ้า deterministic features สามารถทำได้

เก็บ:

```text
regime
regime_confidence
regime_features
regime_timestamp
```

---

# 8. FEATURE ENGINE

สร้าง reusable feature pipeline

อย่างน้อย:

```text
Price
ATR
ATR percentile
ADX
EMA 20/50/200
EMA slope
RSI
VWAP
Candle range
Volatility
Spread
Session
Day of week
Swing high
Swing low
BOS
CHoCH
FVG
Liquidity sweep
Displacement
Distance from key levels
```

Macro features:

```text
DXY
US10Y
Real Yield
Economic calendar
CPI
NFP
PCE
FOMC
Fed events
```

Feature calculation ต้องเป็น deterministic และ reproducible

---

# 9. STRATEGY RESEARCH

อย่า hard-code ว่า strategy ไหน profitable

ให้ research framework ทดลอง:

```text
Trend Following
Trend Pullback
Breakout
Liquidity Sweep
FVG
Momentum
Mean Reversion
Volatility Expansion
Session Breakout
```

แต่ละ strategy ต้องมี:

```text
entry
exit
stop
target
filters
session
regime
transaction cost
spread
slippage
```

---

# 10. RESEARCH VALIDATION

ห้ามยอมรับ strategy เพราะ backtest สวย

ทุก strategy ต้องผ่าน:

```text
Train
Validation
Test
Walk Forward
Out-of-Sample
Monte Carlo
Parameter Sensitivity
Transaction Cost Test
Spread Stress Test
Slippage Stress Test
```

และตรวจ:

```text
Look-ahead bias
Data leakage
Overfitting
Survivorship bias
Regime dependency
Parameter instability
```

สร้างสถานะ:

```text
RESEARCH
CANDIDATE
VALIDATED
PAPER
LIVE
REJECTED
```

---

# 11. RISK ENGINE

สร้าง module แยกอย่างชัดเจน

ตัวอย่าง default:

```text
Risk per trade = 0.5%

Max daily loss = 2%

Max drawdown threshold = configurable

Max consecutive losses = 3

Max simultaneous risk = 1%

No martingale

No revenge trading

No averaging down
```

Position sizing:

```text
risk_amount / stop_distance
```

Risk Engine ต้องสามารถ reject signal จาก AI ได้

---

# 12. NEWS / MACRO FILTER

News ไม่ควรเป็น Buy/Sell generator

ใช้เป็น context + risk filter

ตัวอย่าง:

```text
High-impact event < 10 min
        ↓
BLOCK NEW TRADE
```

หรือ:

```text
High-impact event
        ↓
Increase uncertainty
        ↓
Require higher setup quality
```

ต้องเก็บเหตุผลว่าทำไม trade ถูก block

---

# 13. EXECUTION

สร้าง abstraction:

```text
Signal
   ↓
Risk Validation
   ↓
Execution Request
   ↓
MT5 Adapter
   ↓
Order
```

ห้ามให้ AI เรียก MT5 API โดยตรง

Execution Engine ต้องจัดการ:

```text
market order
pending order
SL
TP
trailing stop
partial close
position reconciliation
broker errors
retry
duplicate order protection
```

---

# 14. TRADE JOURNAL

ทุก signal ต้องถูกบันทึก แม้ไม่ได้ trade

ตัวอย่าง:

```text
timestamp
symbol
timeframe
regime
strategy
setup
features
AI score
AI thesis
decision
risk decision
entry
SL
TP
spread
slippage
result
MAE
MFE
exit reason
```

สำคัญมาก:

**บันทึก NO_TRADE ด้วย**

เพราะภายหลังเราต้องวิเคราะห์ว่า AI พลาดอะไรจากการไม่เข้า trade

---

# 15. FEEDBACK LOOP

สร้าง:

```text
Trade
 ↓
Journal
 ↓
Performance
 ↓
Attribution
 ↓
Research
 ↓
Hypothesis
 ↓
Backtest
 ↓
WFO
 ↓
OOS
 ↓
Promotion / Reject
```

ห้ามระบบ self-modify strategy แล้วนำไป live โดยอัตโนมัติ

การ promote strategy ต้องมี approval gate

---

# 16. MONITORING

ใช้ Grafana หรือระบบ monitoring ที่มีอยู่แล้ว

Dashboard:

```text
XAUUSD Price
Current Regime
Current Session
Volatility
Spread
AI Status
Last Signal
Current Position
Risk
Daily P&L
Drawdown
Win Rate
Expectancy
System Health
Data Feed Health
MT5 Health
API Health
```

Alert:

```text
Telegram
Discord
Email
```

แจ้ง:

```text
System Down
Data Feed Down
MT5 disconnected
High Spread
High Volatility
New Signal
Trade Executed
Risk Limit
Daily Loss Limit
AI Error
```

---

# 17. SYSTEM HEALTH

ต้องสามารถ run 24/7 บน VPS

ต้องมี:

```text
Docker
Health Check
Restart Policy
Logging
Metrics
Database Backup
Config Backup
API timeout
Retry
Circuit breaker
Kill switch
```

หาก AI API down:

```text
AI unavailable
        ↓
NO NEW TRADE
        ↓
Existing positions remain under Risk/Execution management
```

ระบบต้อง fail-safe

---

# 18. CONFIGURATION

ห้าม hard-code trading parameters

ใช้:

```text
.env
config.yaml
```

แยก:

```text
development
research
paper
live
```

ตัวอย่าง:

```yaml
symbol: XAUUSD

timeframes:
  monitor: M1
  setup: M5
  decision: M15
  regime: H1
  context: H4

risk:
  risk_per_trade: 0.005
  max_daily_loss: 0.02
  max_consecutive_losses: 3

ai:
  fast_model: haiku
  strong_model: sonnet
  research_model: opus
```

---

# 19. IMPLEMENTATION STRATEGY

ห้ามแก้ทั้งหมดในครั้งเดียว

แบ่ง implementation เป็น phases:

### Phase 1

Audit existing project

### Phase 2

XAU/USD data pipeline

### Phase 3

Feature engine

### Phase 4

Regime engine

### Phase 5

Setup scanner

### Phase 6

AI integration

### Phase 7

Risk engine

### Phase 8

MT5 execution

### Phase 9

Trade journal

### Phase 10

Monitoring

### Phase 11

Backtest / WFO

### Phase 12

Paper trading

### Phase 13

Small live

หลังจบแต่ละ phase:

```text
Implement
↓
Test
↓
Run
↓
Verify
↓
Document
↓
Commit
```

---

# 20. DO NOT DO THESE

ห้าม:

```text
❌ Rewrite everything
❌ Add random indicators
❌ Optimize until backtest is perfect
❌ Use LLM for deterministic calculations
❌ Let LLM directly execute trades
❌ Increase leverage because AI confidence is high
❌ Automatically modify live strategy
❌ Automatically promote new strategy to live
❌ Use future data
❌ Use look-ahead information
❌ Trade intrabar unless explicitly researched
```

---

# 21. FINAL DELIVERABLE

หลังจาก audit ให้เสนอ:

```text
1. Current Architecture
2. Target Architecture
3. Gap Analysis
4. Files to Modify
5. Files to Create
6. Files to Delete
7. Migration Plan
8. Dependencies
9. Infrastructure Changes
10. Estimated Complexity
11. Risks
12. Testing Plan
```

**อย่า implement ก่อนส่ง Architecture/GAP Analysis ให้ review**

เมื่อ implementation เริ่มแล้ว ให้ทำทีละ phase และแสดง:

```text
Phase
Goal
Files changed
Why changed
Tests
Result
Next step
```

เป้าหมายสุดท้ายคือ:

> **A robust XAU/USD 24/7 AI-assisted trading and research system, not an LLM-powered gambling bot.**

ระบบต้อง prioritize:

```text
Data Quality
> Risk Management
> Robust Edge
> Execution Quality
> AI Intelligence
> Trading Frequency
```

และหลักสำคัญที่สุด:

> **AI assists. Rules constrain. Risk Engine decides whether trading is allowed. Execution Engine executes. Humans approve strategy promotion.**
