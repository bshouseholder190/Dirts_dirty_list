"""Genetic algorithm: bots trade real market data, winners breed, losers die."""
import asyncio
import copy
import logging
import random
from dataclasses import dataclass, field, asdict
from typing import Optional

import pandas as pd

from data_feed import fetch_ohlcv
from indicators import evaluate_condition, calc_rsi, calc_ema, calc_vwap

log = logging.getLogger(__name__)

# ── Bot genome ────────────────────────────────────────────────────────────────

@dataclass
class Genome:
    ticker: str
    rsi_buy: float        # RSI threshold to enter (e.g. 30 = oversold)
    rsi_sell: float       # RSI threshold to exit (e.g. 70 = overbought)
    rsi_period: int
    ema_period: int
    use_vwap: bool
    stop_loss_pct: float
    take_profit_pct: float

    def to_strategy_cfg(self) -> dict:
        buy_conditions = [
            {"type": "rsi", "period": self.rsi_period, "signal": "above", "value": self.rsi_buy},
            {"type": "ema", "period": self.ema_period, "signal": "above"},
        ]
        if self.use_vwap:
            buy_conditions.append({"type": "vwap", "period": 20, "signal": "above"})

        return {
            "buy": {"conditions": buy_conditions},
            "sell": {
                "conditions": [
                    {"type": "rsi", "period": self.rsi_period, "signal": "above", "value": self.rsi_sell}
                ],
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
            },
        }

    def mutate(self, rate: float = 0.3) -> "Genome":
        g = copy.copy(self)
        if random.random() < rate:
            g.rsi_buy = max(10, min(45, g.rsi_buy + random.gauss(0, 5)))
        if random.random() < rate:
            g.rsi_sell = max(55, min(90, g.rsi_sell + random.gauss(0, 5)))
        if random.random() < rate:
            g.rsi_period = max(5, min(30, g.rsi_period + random.choice([-1, 1, 2, -2])))
        if random.random() < rate:
            g.ema_period = max(5, min(100, g.ema_period + random.choice([-5, 5, 10, -10])))
        if random.random() < rate * 0.5:
            g.use_vwap = not g.use_vwap
        if random.random() < rate:
            g.stop_loss_pct = max(0.02, min(0.20, g.stop_loss_pct + random.gauss(0, 0.01)))
        if random.random() < rate:
            g.take_profit_pct = max(0.05, min(0.50, g.take_profit_pct + random.gauss(0, 0.02)))
        # Ensure sell > buy RSI
        if g.rsi_sell <= g.rsi_buy:
            g.rsi_sell = g.rsi_buy + random.uniform(15, 30)
        return g

    @staticmethod
    def crossover(a: "Genome", b: "Genome") -> "Genome":
        return Genome(
            ticker=a.ticker,
            rsi_buy=random.choice([a.rsi_buy, b.rsi_buy]),
            rsi_sell=random.choice([a.rsi_sell, b.rsi_sell]),
            rsi_period=random.choice([a.rsi_period, b.rsi_period]),
            ema_period=random.choice([a.ema_period, b.ema_period]),
            use_vwap=random.choice([a.use_vwap, b.use_vwap]),
            stop_loss_pct=(a.stop_loss_pct + b.stop_loss_pct) / 2,
            take_profit_pct=(a.take_profit_pct + b.take_profit_pct) / 2,
        )

    @staticmethod
    def random(ticker: str) -> "Genome":
        rsi_buy = random.uniform(20, 45)
        rsi_sell = rsi_buy + random.uniform(20, 40)
        return Genome(
            ticker=ticker,
            rsi_buy=round(rsi_buy, 1),
            rsi_sell=round(min(rsi_sell, 90), 1),
            rsi_period=random.choice([7, 9, 14, 21]),
            ema_period=random.choice([10, 20, 50]),
            use_vwap=random.random() > 0.5,
            stop_loss_pct=round(random.uniform(0.03, 0.12), 3),
            take_profit_pct=round(random.uniform(0.08, 0.30), 3),
        )


@dataclass
class Bot:
    id: int
    genome: Genome
    generation: int = 0
    fitness: float = 0.0      # total return %
    trades: int = 0
    win_rate: float = 0.0
    alive: bool = True


# ── Backtester ────────────────────────────────────────────────────────────────

async def backtest_genome(
    genome: Genome,
    df: pd.DataFrame,
    volume_factor: float = 1.0,
    sentiment_score: float = 0.0,
) -> dict:
    """
    Backtest genome against df with optional volume + sentiment boosting.
    volume_factor > 1 = this week has above-avg volume (more conviction).
    sentiment_score: -1 to +1 from StockTwits.
    """
    cfg = genome.to_strategy_cfg()
    buy_conds = cfg["buy"]["conditions"]
    stop_pct = cfg["sell"]["stop_loss_pct"]
    tp_pct = cfg["sell"]["take_profit_pct"]

    close = df["Close"]
    volume = df["Volume"] if "Volume" in df.columns else None
    n = len(close)
    if n < 50:
        return {"fitness": 0.0, "trades": 0, "win_rate": 0.0, "sharpe": 0.0}

    # Pre-compute 20-day avg volume for each bar
    vol_avg = volume.rolling(20).mean() if volume is not None else None

    equity = 1.0
    position = None
    wins = 0
    total = 0
    returns = []

    for i in range(50, n):
        window = df.iloc[:i + 1]
        price = float(close.iloc[i])

        if position:
            entry_price, entry_vol_ratio = position
            change = (price - entry_price) / entry_price
            if change <= -stop_pct or change >= tp_pct:
                # Volume bonus: if entry was during high-volume bar, trust the signal more
                vol_multiplier = 1 + (entry_vol_ratio - 1) * 0.1  # up to 10% bonus
                adjusted_change = change * max(0.5, vol_multiplier)
                equity *= (1 + adjusted_change)
                returns.append(adjusted_change)
                if change > 0:
                    wins += 1
                total += 1
                position = None
        else:
            buy_ok = all(_eval_cond(c, window) for c in buy_conds)
            if buy_ok:
                # Check if current bar has above-avg volume (high conviction)
                vol_ratio = 1.0
                if vol_avg is not None and i < len(vol_avg):
                    avg = float(vol_avg.iloc[i])
                    cur = float(volume.iloc[i])
                    vol_ratio = (cur / avg) if avg > 0 else 1.0
                position = (price, vol_ratio)

    # Close open position
    if position:
        entry_price, entry_vol_ratio = position
        change = (float(close.iloc[-1]) - entry_price) / entry_price
        equity *= (1 + change)
        returns.append(change)
        if change > 0:
            wins += 1
        total += 1

    raw_fitness = (equity - 1.0) * 100

    # Sharpe-like score
    import numpy as np
    sharpe = 0.0
    if len(returns) > 1:
        r = np.array(returns)
        sharpe = float(r.mean() / (r.std() + 1e-9) * (252 ** 0.5))
        sharpe = round(sharpe, 2)

    # Final fitness: blend return, volume factor, sentiment, and sharpe
    sentiment_bonus = 1 + sentiment_score * 0.15   # up to ±15% adjustment
    vol_bonus       = 1 + (volume_factor - 1) * 0.2 # up to 20% bonus for high-volume weeks
    sharpe_bonus    = 1 + min(max(sharpe, -1), 2) * 0.1

    fitness = raw_fitness * sentiment_bonus * vol_bonus * sharpe_bonus

    win_rate = (wins / total * 100) if total > 0 else 0.0
    return {
        "fitness": round(fitness, 2),
        "raw_return": round(raw_fitness, 2),
        "trades": total,
        "win_rate": round(win_rate, 1),
        "sharpe": sharpe,
    }


def _eval_cond(cond: dict, df: pd.DataFrame) -> bool:
    close = df["Close"]
    last = float(close.iloc[-1])
    kind = cond.get("type", "")

    if kind == "rsi":
        from indicators import calc_rsi
        period = cond.get("period", 14)
        value = cond.get("value", 50)
        signal = cond.get("signal", "above")
        rsi = calc_rsi(close, period)
        if rsi.dropna().empty:
            return False
        v = float(rsi.iloc[-1])
        return v > value if signal == "above" else v < value

    if kind == "ema":
        from indicators import calc_ema
        period = cond.get("period", 20)
        signal = cond.get("signal", "above")
        ema = calc_ema(close, period)
        v = float(ema.iloc[-1])
        return last > v if signal == "above" else last < v

    if kind == "vwap":
        from indicators import calc_vwap
        period = cond.get("period", 20)
        signal = cond.get("signal", "above")
        vwap = calc_vwap(df, period)
        if vwap.dropna().empty:
            return False
        v = float(vwap.iloc[-1])
        return last > v if signal == "above" else last < v

    return False


# ── Evolution engine ──────────────────────────────────────────────────────────

class EvolutionEngine:
    def __init__(self):
        self.bots: list[Bot] = []
        self.generation = 0
        self.history: list[dict] = []   # per-generation stats
        self._next_id = 1
        self._running = False
        self._callbacks: list = []

    def on_update(self, cb):
        self._callbacks.append(cb)

    async def _emit(self, payload: dict):
        for cb in self._callbacks:
            await cb(payload)

    def seed(self, ticker: str, population_size: int = 10,
             volume_factor: float = 1.0, sentiment_score: float = 0.0):
        self.bots = []
        self.generation = 0
        self.history = []
        self._next_id = 1
        self._volume_factor = volume_factor
        self._sentiment_score = sentiment_score
        for _ in range(population_size):
            bot = Bot(id=self._next_id, genome=Genome.random(ticker))
            self._next_id += 1
            self.bots.append(bot)
        log.info(f"[evo] seeded {population_size} bots for {ticker} (vol={volume_factor:.2f} sentiment={sentiment_score:.2f})")

    async def run_generation(self) -> dict:
        if not self.bots:
            return {"error": "no population — seed first"}

        ticker = self.bots[0].genome.ticker
        df = await fetch_ohlcv(ticker, "1d")
        if df is None or len(df) < 60:
            return {"error": f"insufficient data for {ticker}"}

        self.generation += 1
        log.info(f"[evo] generation {self.generation} — {len(self.bots)} bots")

        # Evaluate each bot (use stored volume/sentiment if available)
        vf = getattr(self, '_volume_factor', 1.0)
        ss = getattr(self, '_sentiment_score', 0.0)
        tasks = [backtest_genome(b.genome, df, vf, ss) for b in self.bots]
        results = await asyncio.gather(*tasks)

        for bot, result in zip(self.bots, results):
            bot.fitness = result["fitness"]
            bot.trades = result["trades"]
            bot.win_rate = result["win_rate"]
            bot.generation = self.generation

        # Sort by fitness
        self.bots.sort(key=lambda b: b.fitness, reverse=True)

        # Kill bottom half
        keep = max(2, len(self.bots) // 2)
        survivors = self.bots[:keep]
        for b in self.bots[keep:]:
            b.alive = False

        # Breed new population from survivors
        new_bots = list(survivors)
        target = len(self.bots)
        while len(new_bots) < target:
            parents = random.sample(survivors, min(2, len(survivors)))
            if len(parents) == 2:
                child_genome = Genome.crossover(parents[0].genome, parents[1].genome).mutate()
            else:
                child_genome = parents[0].genome.mutate()
            child = Bot(id=self._next_id, genome=child_genome, generation=self.generation)
            self._next_id += 1
            new_bots.append(child)

        self.bots = new_bots

        # Record stats
        fitnesses = [b.fitness for b in survivors]
        gen_stats = {
            "generation": self.generation,
            "best": round(max(fitnesses), 2),
            "avg": round(sum(fitnesses) / len(fitnesses), 2),
            "worst": round(min(fitnesses), 2),
            "population": len(self.bots),
        }
        self.history.append(gen_stats)

        payload = {
            "type": "evolution",
            "generation": self.generation,
            "stats": gen_stats,
            "bots": self._bots_state(),
            "history": self.history[-20:],
            "running": self._running,
        }
        await self._emit(payload)
        return payload

    async def auto_evolve(self, generations: int = 10):
        from lessons_writer import append_lessons
        self._running = True
        for _ in range(generations):
            if not self._running:
                break
            await self.run_generation()
            await asyncio.sleep(0.5)
        self._running = False

        # Write lessons after full auto-evolve run
        if self.bots and self.history:
            ticker = self.bots[0].genome.ticker
            try:
                path = append_lessons(ticker, self.generation, self._bots_state(), self.history)
                log.info(f"[evo] lessons written to {path}")
                await self._emit({
                    "type": "evolution_lessons",
                    "message": f"Lessons saved to {path}",
                    "ticker": ticker,
                    "generation": self.generation,
                })
            except Exception as e:
                log.error(f"[evo] failed to write lessons: {e}")

    def stop(self):
        self._running = False

    def reset(self):
        self.stop()
        self.bots = []
        self.generation = 0
        self.history = []

    def _bots_state(self) -> list[dict]:
        return [
            {
                "id": b.id,
                "generation": b.generation,
                "fitness": b.fitness,
                "trades": b.trades,
                "win_rate": b.win_rate,
                "alive": b.alive,
                "genome": {
                    "ticker": b.genome.ticker,
                    "rsi_buy": round(b.genome.rsi_buy, 1),
                    "rsi_sell": round(b.genome.rsi_sell, 1),
                    "rsi_period": b.genome.rsi_period,
                    "ema_period": b.genome.ema_period,
                    "use_vwap": b.genome.use_vwap,
                    "stop_loss_pct": round(b.genome.stop_loss_pct * 100, 1),
                    "take_profit_pct": round(b.genome.take_profit_pct * 100, 1),
                },
            }
            for b in self.bots
        ]

    def state(self) -> dict:
        return {
            "generation": self.generation,
            "population": len(self.bots),
            "running": self._running,
            "history": self.history[-20:],
            "bots": self._bots_state(),
        }
