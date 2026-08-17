"""Real-time data via yfinance (polling). Free, no API key required."""
import asyncio
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

# Cache: ticker -> (df, fetched_at)
_cache: dict[str, tuple[pd.DataFrame, datetime]] = {}
_CACHE_TTL = 60  # seconds


def _interval_for_timeframe(timeframe: str) -> tuple[str, str]:
    """Map strategy timeframe to yfinance period/interval."""
    tf = timeframe.lower()
    if tf in ("1m", "2m", "5m"):
        return "1d", tf
    if tf in ("15m", "30m"):
        return "5d", tf
    if tf in ("1h", "60m"):
        return "60d", "1h"
    # Default: daily
    return "1y", "1d"


async def fetch_ohlcv(ticker: str, timeframe: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data for ticker.
    Returns a DataFrame with columns [Open, High, Low, Close, Volume].
    Uses a 60-second cache to avoid hammering yfinance.
    """
    now = datetime.now(timezone.utc)
    cached = _cache.get(ticker)
    if cached:
        df, fetched_at = cached
        age = (now - fetched_at).total_seconds()
        if age < _CACHE_TTL:
            return df

    loop = asyncio.get_event_loop()
    period, interval = _interval_for_timeframe(timeframe)

    try:
        df = await loop.run_in_executor(
            None,
            lambda: yf.download(ticker, period=period, interval=interval,
                                 auto_adjust=True, progress=False, threads=False)
        )
    except Exception as e:
        print(f"[data_feed] yfinance error for {ticker}: {e}")
        return cached[0] if cached else None

    if df is None or df.empty:
        return cached[0] if cached else None

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"])
    _cache[ticker] = (df, now)
    return df


def get_last_price(ticker: str) -> Optional[float]:
    cached = _cache.get(ticker)
    if cached:
        df, _ = cached
        if not df.empty:
            return float(df["Close"].iloc[-1])
    return None
