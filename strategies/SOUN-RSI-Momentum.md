---
name: SOUN RSI Momentum — Evolved
ticker: SOUN
timeframe: 1d
buy:
  conditions:
  - type: rsi
    period: 14
    signal: above
    value: 27.8
  - type: ema
    period: 35
    signal: above
  - type: vwap
    period: 20
    signal: above
sell:
  conditions:
  - type: rsi
    period: 14
    signal: above
    value: 70.0
  stop_loss_pct: 0.021
  take_profit_pct: 0.219
---

# SOUN RSI Momentum — Evolved

Buy SOUN when RSI recovers above 30 (oversold bounce) with price above EMA(20). Exit when RSI hits 70, stop 8%, TP 18%.
