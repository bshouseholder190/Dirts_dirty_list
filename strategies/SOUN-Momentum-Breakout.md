---
name: SOUN Momentum Breakout — Evolved
ticker: SOUN
timeframe: 1d
buy:
  conditions:
  - type: rsi
    period: 21
    signal: above
    value: 26.1
  - type: ema
    period: 45
    signal: above
  - type: vwap
    period: 20
    signal: above
sell:
  conditions:
  - type: rsi
    period: 21
    signal: above
    value: 55
  stop_loss_pct: 0.043
  take_profit_pct: 0.217
---

# SOUN Momentum Breakout — Evolved

Buy SOUN when price breaks above EMA(20) with RSI confirming momentum above 50. Exit when RSI drops below 40, stop 7%, TP 17%.

---

## Evolution Run 2026-06-04 17:37 — SOUN · Gen 10

**Winning Genome (Bot #3):**
- RSI Buy: 22.6 → Sell: 53.8 · Period: RSI(14)
- EMA Period: 50 · VWAP: ✓
- Stop Loss: 4.2% · Take Profit: 23.9%
- Fitness: +23.4% · Win Rate: 42.9% · 7 trades

**Population Summary (Gen 10):**
- Best: +23.4% · Avg: +22.9% · Worst: +20.9%
- Survivors analysed: top 5 of 10 bots
- RSI buy zone: 22.6–24.9 (avg 23.5) · Sell zone: 53.8–55.0 (avg 54.3)
- Stop range: 4.1–5.8% · TP range: 20.5–23.9%

**What the bots learned:**
- Deep oversold entries (RSI ~23.5) worked — SOUN rewards patience waiting for real dips
- Early exits at RSI ~54.3 were optimal — SOUN fades quickly at overbought levels
- RSI(14) dominated — standard 14-period balanced noise vs signal SOUN moves
- EMA(45) trend filter was optimal — medium-term trend filter reduced whipsaws on SOUN
- VWAP filter hurt performance (40% of survivors used it) — too restrictive for SOUN's daily swings
- Medium stops (~5.1%) optimal — gives trades room to breathe without excessive loss
- Take profit ~22.1% was the sweet spot — let winners run on SOUN
- Low win rate (38.8%) but positive return (+22.9%) — few big winners offset many small losses (trend-following behavior)
