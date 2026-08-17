"""Strategy runner: evaluate signals and track position state."""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from data_feed import fetch_ohlcv
from indicators import evaluate_condition, get_indicator_values

log = logging.getLogger(__name__)


class StrategyRunner:
    def __init__(self, strategy: dict, sim_mode: bool = False):
        self.cfg = strategy
        self.id = strategy["id"]
        self.name = strategy["name"]
        self.ticker = strategy["ticker"]
        # In sim mode use 5m intraday so signals fire on every candle
        self.timeframe = "5m" if sim_mode else strategy.get("timeframe", "1d")
        self.sim_mode = sim_mode
        self.capital = 10_000.0
        self.start_capital = 10_000.0

        self.position: Optional[dict] = None   # None = flat
        self.trades: list[dict] = []
        self.indicators: dict = {}
        self.last_signal: Optional[str] = None
        self.error: Optional[str] = None
        self.last_updated: Optional[str] = None

        self._prev_buy_signal = False
        self._prev_sell_signal = False

    async def tick(self) -> list[dict]:
        """
        Run one evaluation cycle. Returns a list of trade events emitted this tick.
        """
        events = []
        try:
            df = await fetch_ohlcv(self.ticker, self.timeframe)
            min_bars = 15 if self.sim_mode else 30
            if df is None or len(df) < min_bars:
                # Try falling back to daily data
                df = await fetch_ohlcv(self.ticker, "1d")
            if df is None or len(df) < 15:
                self.error = "insufficient data"
                return events

            self.error = None
            self.last_updated = datetime.now(timezone.utc).isoformat()

            buy_cfg = self.cfg.get("buy", {})
            sell_cfg = self.cfg.get("sell", {})
            stop_pct = sell_cfg.get("stop_loss_pct") or buy_cfg.get("stop_loss_pct") or 0.05
            tp_pct = sell_cfg.get("take_profit_pct") or buy_cfg.get("take_profit_pct") or 0.15

            current_price = float(df["Close"].iloc[-1])
            self.indicators = get_indicator_values(df, self.cfg)

            buy_conditions = buy_cfg.get("conditions", [])
            sell_conditions = sell_cfg.get("conditions", [])

            buy_signal = all(evaluate_condition(c, df) for c in buy_conditions) if buy_conditions else False
            sell_signal = all(evaluate_condition(c, df) for c in sell_conditions) if sell_conditions else False

            # Check stop-loss / take-profit on open position
            if self.position:
                entry = self.position["entry_price"]
                change_pct = (current_price - entry) / entry

                if change_pct <= -stop_pct:
                    event = self._close_position(current_price, "stop_loss")
                    events.append(event)
                elif tp_pct and change_pct >= tp_pct:
                    event = self._close_position(current_price, "take_profit")
                    events.append(event)
                elif sell_signal and (self.sim_mode or not self._prev_sell_signal):
                    event = self._close_position(current_price, "signal")
                    events.append(event)

            # In sim mode fire on every true signal; in live mode only on rising edge
            should_buy = buy_signal if self.sim_mode else (buy_signal and not self._prev_buy_signal)
            if not self.position and should_buy:
                event = self._open_position(current_price)
                events.append(event)

            self._prev_buy_signal = buy_signal
            self._prev_sell_signal = sell_signal
            self.last_signal = "BUY" if buy_signal else ("SELL" if sell_signal else "—")

        except Exception as e:
            log.exception(f"[{self.id}] tick error")
            self.error = str(e)

        return events

    def _open_position(self, price: float) -> dict:
        shares = round(self.capital / price, 4) if self.sim_mode else 1.0
        self.position = {
            "entry_price": price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "size": 1.0,
            "shares": shares,
        }
        event = {
            "type": "trade",
            "action": "BUY",
            "strategy_id": self.id,
            "strategy_name": self.name,
            "ticker": self.ticker,
            "price": round(price, 4),
            "shares": shares,
            "capital": round(self.capital, 2),
            "time": self.position["entry_time"],
        }
        log.info(f"[{self.id}] BUY {self.ticker} @ {price:.4f}")
        return event

    def _close_position(self, price: float, reason: str) -> dict:
        entry  = self.position["entry_price"]
        shares = self.position.get("shares", 1.0)
        pnl_pct = (price - entry) / entry * 100
        pnl_dollar = (price - entry) * shares if self.sim_mode else 0
        if self.sim_mode:
            self.capital += shares * price
        event = {
            "type": "trade",
            "action": "SELL",
            "strategy_id": self.id,
            "strategy_name": self.name,
            "ticker": self.ticker,
            "price": round(price, 4),
            "entry_price": round(entry, 4),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_dollar": round(pnl_dollar, 2),
            "capital": round(self.capital, 2),
            "reason": reason,
            "time": datetime.now(timezone.utc).isoformat(),
        }
        self.trades.append(event)
        self.position = None
        log.info(f"[{self.id}] SELL {self.ticker} @ {price:.4f} ({pnl_pct:+.2f}%) ${pnl_dollar:+.2f} [{reason}]")
        return event

    def state(self) -> dict:
        pos = None
        if self.position:
            entry = self.position["entry_price"]
            current = self.indicators.get("price", entry)
            unrealized_pct = (current - entry) / entry * 100
            pos = {
                **self.position,
                "current_price": current,
                "unrealized_pct": round(unrealized_pct, 2),
            }

        wins = [t for t in self.trades if t.get("pnl_pct", 0) > 0]
        total = len(self.trades)

        return {
            "id": self.id,
            "name": self.name,
            "ticker": self.ticker,
            "timeframe": self.timeframe,
            "signal": self.last_signal,
            "position": pos,
            "indicators": self.indicators,
            "trade_count": total,
            "win_rate": round(len(wins) / total * 100, 1) if total else None,
            "recent_trades": self.trades[-10:],
            "error": self.error,
            "last_updated": self.last_updated,
        }


class RunnerManager:
    def __init__(self, strategies: list[dict], poll_interval: int = 60, sim_mode: bool = False):
        self.runners = [StrategyRunner(s, sim_mode=sim_mode) for s in strategies]
        self.poll_interval = poll_interval
        self._running = False
        self._event_callbacks: list = []

    def on_event(self, callback):
        self._event_callbacks.append(callback)

    async def start(self):
        self._running = True
        log.info(f"[manager] starting {len(self.runners)} strategies")
        # Stagger initial fetches to avoid rate limits
        for i, runner in enumerate(self.runners):
            await asyncio.sleep(i * 2)
            await runner.tick()
        # Main loop
        while self._running:
            await asyncio.sleep(self.poll_interval)
            for runner in self.runners:
                events = await runner.tick()
                for ev in events:
                    for cb in self._event_callbacks:
                        await cb(ev)

    def stop(self):
        self._running = False

    def all_states(self) -> list[dict]:
        return [r.state() for r in self.runners]
