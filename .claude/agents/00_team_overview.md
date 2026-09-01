# Trading Agent Team — ภาพรวมทีม

## หลักปรัชญาของทั้งทีม
> "อย่าหา Edge เพราะอยากหา Edge — ให้หาว่าอะไรคือ bottleneck ของระบบ
> แล้วใช้ Agent ที่เหมาะสมไปแก้มัน"

หลักนี้ฝังอยู่ใน Research Lead และ Trading Lead โดยเฉพาะ เพราะทั้งคู่เป็นจุดตัดสินใจ
ว่าจะ deploy agent ตัวไหน และจะอนุมัติ strategy ไหนให้ไปต่อ

## Flow การทำงานเต็มระบบ

```
1. Research Lead      → วินิจฉัย bottleneck ก่อนแจกงาน (ไม่แจกทุก agent อัตโนมัติ)
2. Strategy Research   → (ถ้าถูกเรียก) หา edge ที่ตอบ bottleneck โดยเฉพาะ
3. Risk Research       → (ถ้าถูกเรียก) ประเมินความเสี่ยงเชิงปริมาณ มีอำนาจ veto
4. Systems Audit       → (ถ้าถูกเรียก) ตรวจ data/infrastructure ก่อน backtest เสมอ
5. Research Lead       → สังเคราะห์เป็น Research Brief
6. Skeptic (จุดที่ 1)  → ตรวจ Research Brief เชิงญาณวิทยา ก่อนถึง Trading Lead
7. Trading Lead        → Decision Gate: strategy นี้แก้ bottleneck จริงหรือไม่ → approve/reject
8. BACKTEST agent      → รัน backtest, แยก in-sample/out-of-sample อย่างเคร่งครัด
9. Skeptic (จุดที่ 2)  → ตรวจผล backtest หา overfitting/too-good-to-be-true
10. Trading Lead       → ตัดสินใจสุดท้ายก่อนส่งต่อ paper trading/live (นอก scope ทีมนี้)
```

## บทบาทโดยสรุป

| Agent | บทบาทหลัก | มีอำนาจ veto? |
|---|---|---|
| Research Lead | วินิจฉัย bottleneck + แจกงาน + สังเคราะห์ | ไม่โดยตรง (แต่คุมทิศทาง) |
| Strategy Research | หา edge ที่ตอบ bottleneck | ไม่มี |
| Risk Research | ประเมินความเสี่ยงเชิงปริมาณ | **มี** (reject = ห้ามไปต่อ) |
| Systems Audit | ตรวจ data/infrastructure | ไม่มีโดยตรง (แต่ blocked = ต้องแก้ก่อน) |
| Skeptic | ท้าทายเชิงญาณวิทยา 2 จุด | **มี** (severity=block = ห้ามไปต่อ) |
| Trading Lead | Gatekeeper อนุมัติ/ปฏิเสธ | **มี** (decision gate สุดท้าย) |
| BACKTEST agent | รัน backtest อย่างเข้มงวด | ไม่มี (แต่รายงาน overfitting risk บังคับ) |

## กฎร่วมของทั้งทีม
1. **ห้าม default ไปที่ Strategy Research** — ทุกการเรียกใช้ agent ต้องมีเหตุผลจาก bottleneck diagnosis
2. **Risk Research และ Skeptic มีอำนาจ veto จริง** — ไม่ใช่แค่ให้ความเห็นประกอบ
3. **Systems Audit ต้องรันก่อน backtest เสมอ** เมื่อยังไม่มั่นใจในคุณภาพข้อมูล
4. **แยก in-sample/out-of-sample** อย่างเคร่งครัดใน BACKTEST agent
5. **ทุก decision ต้อง log พร้อมเหตุผล** (audit trail) โดยเฉพาะ Trading Lead
6. **Human checkpoint บังคับก่อนขึ้น live** — ระบบอัตโนมัติหยุดที่ backtest/paper trading เท่านั้น

## ไฟล์ในชุดนี้
- `01_research_lead.md`
- `02_strategy_research.md`
- `03_risk_research.md`
- `04_systems_audit.md`
- `05_skeptic.md`
- `06_trading_lead.md`
- `07_backtest_agent.md`
