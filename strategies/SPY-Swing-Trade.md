---
name: SPY Swing Trade
ticker: SPY
timeframe: 1d
buy:
  conditions:
  - type: rsi
    period: 11
    signal: above
    value: 32.7
  - type: ema
    period: 40
    signal: above
  - type: vwap
    period: 20
    signal: above
sell:
  conditions:
  - type: rsi
    period: 11
    signal: above
    value: 60.5
  stop_loss_pct: 0.058
  take_profit_pct: 0.169
---

# SPY Swing Trade

Buy SPY when price is above rolling VWAP(20) and RSI confirms momentum above 50. Exit when RSI reaches 75 (overbought), stop 5%, TP 25%.

---

## Evolution Run 2026-06-04 17:41 — SPY · Gen 10

**Winning Genome (Bot #19):**
- RSI Buy: 30.0 → Sell: 66.8 · Period: RSI(21)
- EMA Period: 10 · VWAP: ✗
- Stop Loss: 10.7% · Take Profit: 12.0%
- Fitness: +21.1% · Win Rate: 100.0% · 2 trades

**Population Summary (Gen 10):**
- Best: +21.1% · Avg: +21.0% · Worst: +21.0%
- Survivors analysed: top 5 of 10 bots
- RSI buy zone: 27.1–32.0 (avg 29.8) · Sell zone: 60.8–67.8 (avg 63.4)
- Stop range: 9.4–10.7% · TP range: 11.3–12.0%

**What the bots learned:**
- Deep oversold entries (RSI ~29.8) worked — SPY rewards patience waiting for real dips
- Early exits at RSI ~63.4 were optimal — SPY fades quickly at overbought levels
- RSI(21) dominated — longer RSI filtered out false signals SPY moves
- EMA(10) trend filter was optimal — fast trend detection suited SPY
- VWAP filter hurt performance (20% of survivors used it) — too restrictive for SPY's daily swings
- Wide stops (~9.9%) needed — SPY is volatile, tight stops get whipsawed
- Take profit ~11.4% was the sweet spot — quick scalps suited this asset on SPY
- High win rate (100.0%) — strategy found consistent edge, not just lucky outliers
