---
name: VWAP Reclaim — NIO Intraday
ticker: NIO
timeframe: 5m
buy:
  conditions:
    - type: session_vwap
      signal: above
    - type: rsi
      period: 14
      signal: above
      value: 45
sell:
  conditions:
    - type: session_vwap
      signal: below
  stop_loss_pct: 0.015
  take_profit_pct: 0.035
---

# VWAP Reclaim — NIO Intraday

Intraday VWAP reclaim strategy — built from live market observations on June 5, 2026.

## Rules
- **Entry:** Price crosses ABOVE session VWAP + RSI(14) > 45 (momentum confirming)
- **Exit signal:** Price crosses BELOW session VWAP (reclaim failed)
- **Stop loss:** 1.5% — tight intraday, no mercy
- **Take profit:** 3.5% — 2.3:1 R:R minimum

## What we learned watching FOXX, MU, STI, NIO today
- VWAP is the line in the sand — above = bulls in control, below = bears
- Price below VWAP after a gap = short, not long
- RSI > 45 at VWAP reclaim = institutional buying confirming the move
- Tight stops (1.5%) are correct intraday — losers don't recover same day
- 3.5% target captures the average intraday VWAP reclaim move

## Lessons from today
- STI +379% → faded below VWAP by 9:24 AM → short
- MU VWAP rejection at 60 → confirmed short to 37
- FOXX reclaimed VWAP at .07 → ran to .30 (VWAP target)
- NIO bounced off VWAP lower band at .54
