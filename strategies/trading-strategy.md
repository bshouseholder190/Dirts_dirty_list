---
name: Small-Cap Momentum Breakout
ticker: SOUN
timeframe: 1d
version: 1.0
buy:
  conditions:
  - type: rsi
    period: 20
    signal: above
    value: 41.9
  - type: ema
    period: 10
    signal: above
  - type: vwap
    period: 20
    signal: above
sell:
  conditions:
  - type: rsi
    period: 20
    signal: above
    value: 69.2
  stop_loss_pct: 0.027
  take_profit_pct: 0.208
---

# Small-Cap Momentum Breakout Strategy
### Version 1.0 — Test Environment (Backtesting & Paper Trading)

---

## Overview

**Style:** Discretionary-systematic hybrid  
**Instrument:** U.S. equities, small-cap ($300M–$2B market cap)  
**Timeframe:** Intraday (primary: 5-min, 15-min); Daily for bias  
**Holding Period:** Intraday to 2 days  
**Universe:** NYSE / NASDAQ listed, price $2–$20, avg daily volume > 500K shares  

This strategy captures momentum breakouts from consolidation on stocks exhibiting a clear daily trend bias. Entry is triggered when price breaks a defined intraday level on expanding volume after a period of compression. Risk is defined before entry. Every trade is sized to risk a fixed percentage of account equity.

---

## Theoretical Foundation

| Principle | Source |
|---|---|
| Follow the trend of least resistance | *Reminiscences of a Stock Operator* |
| Define risk before entry; never add to losers | *Trading for a Living* — Elder |
| Multiple timeframe confirmation | *Technical Analysis Using Multiple Timeframes* — Shannon |
| Position size determines survival | *Trade Your Way to Financial Freedom* — Tharp |
| Separate edge from execution | *The Disciplined Trader* — Douglas |
| Randomness exists; edge is statistical | *Fooled by Randomness* — Taleb |

---

## Market Conditions (When to Trade)

**Trade this strategy only when:**

- The broad market (SPY) is not in a confirmed downtrend on the daily chart
- VIX is below 35 (above 35 = erratic intraday behavior, reduces edge)
- The stock has a clear daily trend: higher highs and higher lows (long setups), or lower highs and lower lows (short setups)

**Do not trade:**

- Earnings day or the day before earnings
- FDA/binary event pending
- First 5 minutes of the market open (observation only)
- Last 10 minutes of the session (unless already in a trade)

---

## Setup Criteria

All five conditions must be met before a trade is considered.

### 1. Daily Trend Bias
- **Long:** Stock is above its 20-day EMA and 50-day EMA; both EMAs sloping up
- **Short:** Stock is below its 20-day EMA and 50-day EMA; both EMAs sloping down

### 2. Intraday Consolidation
- Price has been ranging for a minimum of 3 bars (15-min chart) with contracting ATR
- The range is no wider than 3% from low to high of consolidation
- This forms the **base**

### 3. Volume Dry-Up During Base
- Volume during consolidation is below the 20-period average on the 15-min chart
- This confirms institutional supply/demand imbalance is building

### 4. Defined Breakout Level
- Identify the **high of the base** (for longs) or **low of the base** (for shorts)
- This becomes the **trigger price**
- Must be a clean, obvious level — not forced

### 5. Relative Strength / Weakness
- Long setups: stock is outperforming SPY on the day it breaks
- Short setups: stock is underperforming SPY on the day it breaks

---

## Entry Rules

### Long Entry
1. Price closes **above the breakout level** on a 5-min candle
2. Volume on the breakout candle is **at least 1.5x the 20-period average** on the 5-min chart
3. Enter on the **open of the next 5-min candle** after confirmation closes
4. Do not chase: if price has moved more than **1.5x ATR(14)** beyond the breakout level before your entry, skip the trade

### Short Entry
Mirror of long entry rules — price closes below the base low on expanding volume.

### Entry Checklist (complete before placing order)

```
[ ] Daily trend bias confirmed (EMA alignment)
[ ] Base formed: 3+ bars, range < 3%, volume dry-up
[ ] Breakout candle: closes beyond level on 1.5x+ volume
[ ] Entry price within 1.5x ATR of trigger
[ ] Stop loss level identified
[ ] Position size calculated
[ ] No binary events pending
```

---

## Stop Loss Rules

**Initial Stop:** Placed at the **low of the consolidation base** (longs) or **high of the base** (shorts).

- This is non-negotiable — set it as a hard stop at time of entry
- Do not widen stop after entry under any circumstances
- If the base is too wide and the stop requires risking more than the defined R per trade, **do not take the trade**

**Time Stop:** If price does not move in your favor within **3 candles (15 minutes)** of entry, exit at market regardless of stop distance. Stalling after a breakout is a failed breakout signal.

---

## Profit Target Rules

This strategy uses a **tiered exit** approach.

| Target | Action | Rationale |
|---|---|---|
| **1R** (1x risk distance) | Exit 50% of position | Lock in a winner; removes emotional pressure |
| **2R** | Exit remaining 25% | Captures extended move |
| **Trailing stop** | Trail remaining 25% with 2-bar low (5-min) | Allows runners to develop |

**Maximum holding time:** Close all positions before the market close. No overnight holds unless the 2R target has been hit and the trailing stop is active.

---

## Position Sizing

This strategy risks **1% of account equity per trade**. No exceptions.

```
Risk Amount ($)   = Account Equity × 0.01
Stop Distance ($) = Entry Price − Stop Price (per share)
Share Size        = Risk Amount ÷ Stop Distance
```

**Example:**
- Account: $25,000
- Entry: $8.50
- Stop: $8.10
- Stop distance: $0.40
- Risk amount: $250
- Share size: 250 ÷ 0.40 = **625 shares**

**Hard limits:**
- Never risk more than 2% of equity on any single trade
- Never hold more than 3 open positions simultaneously
- Maximum total portfolio risk at any time: 4% of equity

---

## Trade Management Rules

1. **Move stop to breakeven** once price reaches 1R profit
2. **Never add to a losing position** — ever
3. Adding to a winner is permitted only after 1R is achieved and only up to 50% of original size
4. If stopped out, do not re-enter the same setup on the same day
5. Log every trade immediately after exit (see Trade Log section)

---

## Backtesting Protocol

### Setup
- Platform: TradingView (replay mode) or ThinkOrSwim OnDemand
- Data: Minimum 2 years of daily + intraday data
- Sample size: Minimum **100 trades** before drawing conclusions

### Process
1. Start with daily chart — identify candidate setups meeting trend bias criteria
2. Drop to 15-min chart — confirm base formation and volume dry-up
3. Drop to 5-min chart — simulate entry, stop, and exits as written
4. Record every trade in the log — **including trades you would have skipped**
5. Do not skip a valid setup in backtesting because "it felt wrong" — apply rules mechanically

### What to Measure

| Metric | Target |
|---|---|
| Win Rate | > 40% |
| Average R:R (winners) | > 2:1 |
| Expectancy | > 0.4R per trade |
| Max Drawdown | < 15% of starting equity |
| Profit Factor | > 1.5 |
| Consecutive losses (max observed) | Track for psychology prep |

**Expectancy formula:**
```
Expectancy = (Win Rate × Avg Win) − (Loss Rate × Avg Loss)
```
A positive expectancy means the strategy makes money over a large sample. A single trade result means nothing.

---

## Paper Trading Protocol

### Rules
- Use **real-time data only** — no delayed feeds
- Execute every entry and exit at **the price you would have gotten**, not the ideal price
- Include **$0.005/share slippage** in all calculations (simulates real fills)
- Run for minimum **30 trades or 60 calendar days** before evaluating
- Do not increase size or deviate from rules during paper trading phase

### Graduation Criteria (move to live trading when)
- Expectancy is positive over 30+ trades
- You have not violated a single rule (stop, sizing, no-trade conditions)
- You can explain every loss without blaming the market
- Maximum drawdown stayed under 15%

---

## Trade Log

Record every trade. No exceptions.

| Field | Notes |
|---|---|
| Date | |
| Ticker | |
| Direction | Long / Short |
| Setup Quality | A / B / C (grade before entry) |
| Entry Price | |
| Stop Price | |
| Target 1 (1R) | |
| Target 2 (2R) | |
| Exit Price(s) | |
| Shares | |
| P&L ($) | |
| P&L (R) | |
| Rule Violations | None / describe |
| Notes | What did you see? What did you feel? |

---

## Psychological Rules

Drawn from *The Disciplined Trader* (Douglas) and *Best Loser Wins* (Hougaard):

1. **Before the session:** Write down the market conditions and your bias. Commit to it.
2. **During the session:** If you feel urgency to enter a trade that doesn't meet criteria, do not trade. Log the feeling instead.
3. **After a loss:** Do not increase size on the next trade. Losses are the cost of doing business.
4. **After a win:** Do not loosen rules on the next trade. Overconfidence kills accounts.
5. **End of day review:** Grade your execution, not your P&L. A losing trade executed perfectly is a success. A winning trade taken outside the rules is a failure.

---

## Strategy Limitations

Be honest about what this strategy cannot do:

- It **underperforms in choppy, low-volatility markets** — consolidation breakouts fail more often
- It **requires active monitoring** during the trading session — not suitable for set-and-forget
- It has **higher transaction costs** than swing or position trading — slippage matters
- Small-cap stocks carry **liquidity risk** — large size can move the stock against you
- **Not all breakouts work.** A 40–50% win rate is expected and acceptable if R:R is maintained

---

## Suggested Assignment (Classroom Use)

Students complete four deliverables:

1. **Backtest Report** — 100 trade sample with full log, metrics table, and equity curve chart
2. **Setup Gallery** — Screenshot library of 20 valid setups (10 winners, 10 losers) with annotations
3. **Rule Violation Audit** — Identify any trades where rules were bent; explain the bias that caused it
4. **Risk Plan** — Written document: max daily loss limit, max drawdown before strategy pause, re-evaluation criteria

---

*Strategy version 1.0. Review and revise after every 100-trade sample.*
