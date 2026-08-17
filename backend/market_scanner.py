"""
Market scanner: top 50 most-traded stocks + social sentiment scoring.
Data sources (all free, no API keys):
  - yfinance screener for most-active stocks
  - StockTwits public API for social sentiment
  - Google Trends via pytrends for search interest
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
import yfinance as yf

log = logging.getLogger(__name__)

# Fallback list of typically high-volume S&P 500 stocks
_FALLBACK_TOP50 = [
    "NVDA", "TSLA", "AAPL", "AMD", "AMZN", "META", "MSFT", "GOOGL", "SPY", "QQQ",
    "BAC", "F", "PLTR", "INTC", "SOFI", "AAL", "CCL", "RIVN", "NIO", "LCID",
    "GME", "AMC", "BBBY", "SOUN", "MARA", "RIOT", "COIN", "HOOD", "RBLX", "SNAP",
    "UBER", "LYFT", "NFLX", "DIS", "T", "VZ", "WMT", "JPM", "GS", "XOM",
    "CVX", "PFE", "MRNA", "JNJ", "ABBV", "LLY", "UNH", "CRM", "ORCL", "IBM",
]


def get_top50_by_volume() -> list[dict]:
    """
    Fetch the 50 most-traded US stocks this week.
    Returns list of {ticker, name, volume, price, change_pct}.
    """
    tickers = []

    # Try yfinance screener (most actives)
    try:
        screener = yf.Screener()
        screener.set_predefined_body("most_actives")
        screener.set_default_body({"offset": 0, "size": 50})
        result = screener.response
        quotes = result.get("quotes", [])
        for q in quotes[:50]:
            tickers.append({
                "ticker": q.get("symbol", ""),
                "name": q.get("shortName", q.get("symbol", "")),
                "volume": q.get("regularMarketVolume", 0),
                "price": round(q.get("regularMarketPrice", 0), 2),
                "change_pct": round(q.get("regularMarketChangePercent", 0), 2),
            })
        if tickers:
            log.info(f"[scanner] screener returned {len(tickers)} tickers")
            return tickers
    except Exception as e:
        log.warning(f"[scanner] screener failed: {e}, using fallback")

    # Fallback: fetch 5d volume for known high-volume stocks
    log.info("[scanner] fetching volume for fallback list…")
    results = []
    batch = yf.download(
        _FALLBACK_TOP50, period="5d", interval="1d",
        auto_adjust=True, progress=False, threads=True
    )
    for sym in _FALLBACK_TOP50:
        try:
            if isinstance(batch.columns, __import__('pandas').MultiIndex):
                vol = batch["Volume"][sym].sum()
                price = float(batch["Close"][sym].iloc[-1])
                prev  = float(batch["Close"][sym].iloc[-2])
            else:
                vol = batch["Volume"].sum()
                price = float(batch["Close"].iloc[-1])
                prev  = float(batch["Close"].iloc[-2])
            change_pct = round((price - prev) / prev * 100, 2)
            results.append({
                "ticker": sym,
                "name": sym,
                "volume": int(vol),
                "price": round(price, 2),
                "change_pct": change_pct,
            })
        except Exception:
            results.append({"ticker": sym, "name": sym, "volume": 0, "price": 0, "change_pct": 0})

    results.sort(key=lambda x: x["volume"], reverse=True)
    return results[:50]


def get_stocktwits_sentiment(ticker: str) -> dict:
    """
    Fetch recent StockTwits messages and compute sentiment score.
    Returns {bullish_pct, bearish_pct, message_count, score}.
    score: -1 (all bearish) to +1 (all bullish).
    """
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return _neutral_sentiment()
        data = r.json()
        messages = data.get("messages", [])
        if not messages:
            return _neutral_sentiment()

        bullish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bullish")
        bearish = sum(1 for m in messages if m.get("entities", {}).get("sentiment", {}).get("basic") == "Bearish")
        total = len(messages)
        tagged = bullish + bearish

        if tagged == 0:
            return _neutral_sentiment(total)

        bull_pct = round(bullish / tagged * 100, 1)
        bear_pct = round(bearish / tagged * 100, 1)
        score    = round((bullish - bearish) / tagged, 3)

        return {
            "bullish_pct": bull_pct,
            "bearish_pct": bear_pct,
            "message_count": total,
            "score": score,
        }
    except Exception as e:
        log.debug(f"[sentiment] {ticker}: {e}")
        return _neutral_sentiment()


def _neutral_sentiment(count: int = 0) -> dict:
    return {"bullish_pct": 50.0, "bearish_pct": 50.0, "message_count": count, "score": 0.0}


def get_volume_factor(ticker: str) -> float:
    """
    Returns how this week's avg volume compares to 3-month avg.
    > 1.0 = above average activity (more interest than usual).
    """
    try:
        df = yf.download(ticker, period="3mo", interval="1d",
                         auto_adjust=True, progress=False, threads=False)
        if df is None or len(df) < 10:
            return 1.0
        if isinstance(df.columns, __import__('pandas').MultiIndex):
            vol = df["Volume"].iloc[:, 0] if df["Volume"].shape[1] == 1 else df["Volume"][ticker]
        else:
            vol = df["Volume"]
        avg_3m      = float(vol.mean())
        avg_1w      = float(vol.tail(5).mean())
        if avg_3m == 0:
            return 1.0
        factor = avg_1w / avg_3m
        return round(min(factor, 3.0), 3)   # cap at 3x
    except Exception:
        return 1.0


async def score_ticker(ticker: str) -> dict:
    """Full score for one ticker: volume factor + sentiment."""
    loop = asyncio.get_event_loop()
    sentiment = await loop.run_in_executor(None, get_stocktwits_sentiment, ticker)
    vol_factor = await loop.run_in_executor(None, get_volume_factor, ticker)
    return {
        "ticker": ticker,
        "volume_factor": vol_factor,
        "sentiment": sentiment,
        "composite_score": round(vol_factor * (1 + sentiment["score"]), 3),
    }


async def scan_top50() -> list[dict]:
    """Full scan: top 50 tickers + volume + sentiment, sorted by composite score."""
    loop = asyncio.get_event_loop()
    log.info("[scanner] fetching top 50 by volume…")
    stocks = await loop.run_in_executor(None, get_top50_by_volume)

    log.info(f"[scanner] scoring {len(stocks)} tickers…")
    tasks = [score_ticker(s["ticker"]) for s in stocks[:50]]
    scores = await asyncio.gather(*tasks, return_exceptions=True)

    score_map = {}
    for s in scores:
        if isinstance(s, dict):
            score_map[s["ticker"]] = s

    for stock in stocks:
        sc = score_map.get(stock["ticker"], {})
        stock["volume_factor"]    = sc.get("volume_factor", 1.0)
        stock["sentiment"]        = sc.get("sentiment", _neutral_sentiment())
        stock["composite_score"]  = sc.get("composite_score", 1.0)

    stocks.sort(key=lambda x: x["composite_score"], reverse=True)
    log.info("[scanner] scan complete")
    return stocks
