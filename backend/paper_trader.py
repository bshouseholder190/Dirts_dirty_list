"""
Paper trading simulation — runs strategies against today's live intraday data.
Uses 5-minute bars from yfinance, updated every 60 seconds.
Tracks virtual cash, positions, and P&L per strategy.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from data_feed import fetch_ohlcv
from indicators import evaluate_condition, get_indicator_values

log = logging.getLogger(__name__)

STARTING_CAPITAL = 10_000.0  # virtual dollars per strategy


class PaperAccount:
    def __init__(self, strategy: dict, capital: float = STARTING_CAPITAL):
        self.cfg        = strategy
        self.id         = strategy["id"]
        self.name       = strategy["name"]
        self.ticker     = strategy["ticker"]
        self.capital    = capital
        self.start_cap  = capital
        self.position: Optional[dict] = None
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        self.indicators: dict = {}
        self.signal: str = "—"
        self.error: Optional[str] = None
        self.last_price: float = 0.0
        self._prev_buy  = False
        self._prev_sell = False

    @property
    def equity(self) -> float:
        """Current total equity including open position."""
        if self.position:
            unrealized = (self.last_price - self.position["entry_price"]) * self.position["shares"]
            return self.capital + unrealized
        return self.capital

    @property
    def pnl(self) -> float:
        return round(self.equity - self.start_cap, 2)

    @property
    def pnl_pct(self) -> float:
        return round((self.equity - self.start_cap) / self.start_cap * 100, 2)

    async def tick(self) -> list[dict]:
        events = []
        try:
            # Use 5m intraday for live simulation — gives real-time signal updates
            df = await fetch_ohlcv(self.ticker, "5m")
            if df is None or len(df) < 30:
                # Fall back to daily
                df = await fetch_ohlcv(self.ticker, "1d")
            if df is None or len(df) < 20:
                self.error = "no data"
                return events

            self.error = None
            price = float(df["Close"].iloc[-1])
            self.last_price = price
            self.indicators = get_indicator_values(df, self.cfg)
            self.indicators["price"] = round(price, 4)

            buy_cfg  = self.cfg.get("buy", {})
            sell_cfg = self.cfg.get("sell", {})
            stop_pct = sell_cfg.get("stop_loss_pct", 0.05)
            tp_pct   = sell_cfg.get("take_profit_pct", 0.15)

            buy_conds  = buy_cfg.get("conditions", [])
            sell_conds = sell_cfg.get("conditions", [])
            buy_signal  = all(evaluate_condition(c, df) for c in buy_conds) if buy_conds else False
            sell_signal = all(evaluate_condition(c, df) for c in sell_conds) if sell_conds else False

            self.signal = "BUY" if buy_signal else ("SELL" if sell_signal else "—")

            # Check stop-loss / take-profit on open position
            if self.position:
                entry = self.position["entry_price"]
                chg   = (price - entry) / entry
                reason = None
                if chg <= -stop_pct:
                    reason = "stop_loss"
                elif chg >= tp_pct:
                    reason = "take_profit"
                elif sell_signal and not self._prev_sell:
                    reason = "signal"
                if reason:
                    ev = self._close(price, reason)
                    events.append(ev)

            # Open on rising edge of buy signal
            if not self.position and buy_signal and not self._prev_buy:
                ev = self._open(price)
                events.append(ev)

            self._prev_buy  = buy_signal
            self._prev_sell = sell_signal

            # Record equity curve point
            self.equity_curve.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "equity": round(self.equity, 2),
                "price": round(price, 4),
            })
            # Keep last 200 points
            if len(self.equity_curve) > 200:
                self.equity_curve = self.equity_curve[-200:]

        except Exception as e:
            log.exception(f"[paper:{self.id}] tick error")
            self.error = str(e)

        return events

    def _open(self, price: float) -> dict:
        shares = self.capital / price  # buy with all available cash
        cost   = shares * price
        self.capital -= cost
        self.position = {
            "entry_price": round(price, 4),
            "shares": round(shares, 4),
            "cost": round(cost, 2),
            "entry_time": datetime.now(timezone.utc).isoformat(),
        }
        ev = {
            "type": "paper_trade",
            "action": "BUY",
            "strategy_id": self.id,
            "strategy_name": self.name,
            "ticker": self.ticker,
            "price": round(price, 4),
            "shares": round(shares, 4),
            "value": round(cost, 2),
            "capital_remaining": round(self.capital, 2),
            "time": self.position["entry_time"],
        }
        log.info(f"[paper:{self.id}] BUY {shares:.1f} {self.ticker} @ ${price:.2f} (cost ${cost:.0f})")
        return ev

    def _close(self, price: float, reason: str) -> dict:
        shares   = self.position["shares"]
        proceeds = shares * price
        entry    = self.position["entry_price"]
        pnl      = proceeds - self.position["cost"]
        pnl_pct  = (price - entry) / entry * 100
        self.capital += proceeds
        self.trades.append({
            "action": "SELL",
            "entry": entry,
            "exit": round(price, 4),
            "shares": round(shares, 4),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason,
            "time": datetime.now(timezone.utc).isoformat(),
        })
        ev = {
            "type": "paper_trade",
            "action": "SELL",
            "strategy_id": self.id,
            "strategy_name": self.name,
            "ticker": self.ticker,
            "price": round(price, 4),
            "shares": round(shares, 4),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "reason": reason,
            "capital": round(self.capital, 2),
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self.position = None
        log.info(f"[paper:{self.id}] SELL {shares:.1f} {self.ticker} @ ${price:.2f} P&L ${pnl:+.2f} ({pnl_pct:+.1f}%) [{reason}]")
        return ev

    def state(self) -> dict:
        wins   = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] <= 0]
        pos = None
        if self.position:
            entry = self.position["entry_price"]
            unreal_pct = (self.last_price - entry) / entry * 100
            pos = {**self.position, "current_price": self.last_price,
                   "unrealized_pnl": round((self.last_price - entry) * self.position["shares"], 2),
                   "unrealized_pct": round(unreal_pct, 2)}
        return {
            "id": self.id,
            "name": self.name,
            "ticker": self.ticker,
            "capital": round(self.capital, 2),
            "equity": round(self.equity, 2),
            "pnl": self.pnl,
            "pnl_pct": self.pnl_pct,
            "position": pos,
            "signal": self.signal,
            "indicators": self.indicators,
            "trade_count": len(self.trades),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins)/len(self.trades)*100, 1) if self.trades else None,
            "recent_trades": self.trades[-10:],
            "equity_curve": self.equity_curve[-50:],
            "error": self.error,
        }


class PaperTradingSession:
    def __init__(self, strategies: list[dict], capital: float = STARTING_CAPITAL):
        self.accounts  = [PaperAccount(s, capital) for s in strategies]
        self.running   = False
        self.started_at = None
        self._callbacks: list = []

    def on_event(self, cb):
        self._callbacks.append(cb)

    async def _emit(self, payload: dict):
        for cb in self._callbacks:
            await cb(payload)

    async def start(self, poll_interval: int = 60):
        self.running    = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        log.info(f"[paper] session started — {len(self.accounts)} strategies")

        # Initial tick (staggered)
        for i, acc in enumerate(self.accounts):
            await asyncio.sleep(i * 1.5)
            events = await acc.tick()
            for ev in events:
                await self._emit(ev)

        # Push initial state
        await self._emit({"type": "paper_state", "accounts": self.all_states(),
                          "started_at": self.started_at})

        while self.running:
            await asyncio.sleep(poll_interval)
            all_events = []
            for acc in self.accounts:
                events = await acc.tick()
                all_events.extend(events)
            for ev in all_events:
                await self._emit(ev)
            await self._emit({"type": "paper_state", "accounts": self.all_states(),
                              "started_at": self.started_at})

    def stop(self):
        self.running = False

    def reset(self, strategies: list[dict], capital: float = STARTING_CAPITAL):
        self.stop()
        self.accounts = [PaperAccount(s, capital) for s in strategies]
        self.started_at = None

    def all_states(self) -> list[dict]:
        return [a.state() for a in self.accounts]
