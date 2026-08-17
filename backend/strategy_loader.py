"""Parse trading strategy .md files with YAML frontmatter."""
import os
import re
from pathlib import Path
from typing import Optional

import yaml


_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---", re.DOTALL)


def _extract_frontmatter(text: str) -> Optional[dict]:
    """Return parsed YAML frontmatter dict, or None if not found."""
    m = _FRONTMATTER_RE.search(text)
    if not m:
        return None
    try:
        result = yaml.safe_load(m.group(1))
        return result if isinstance(result, dict) else None
    except yaml.YAMLError:
        return None


def _extract_description(text: str) -> str:
    """Pull the first non-empty paragraph after the frontmatter as a description."""
    # Strip frontmatter
    body = _FRONTMATTER_RE.sub("", text, count=1).strip()
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("|") and not line.startswith("-"):
            return line[:200]
    # Fall back to first heading
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def load_strategy(path: str) -> Optional[dict]:
    """
    Load a strategy from a .md file.
    Returns None if the file has no valid frontmatter with buy/sell config.
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()

    fm = _extract_frontmatter(text)
    if not fm:
        return None

    # Must have buy AND sell sections with conditions
    buy = fm.get("buy", {})
    sell = fm.get("sell", {})
    if not buy or not sell:
        return None
    if not buy.get("conditions") and not sell.get("conditions"):
        return None

    name = fm.get("name") or Path(path).stem
    ticker = fm.get("ticker") or fm.get("symbol") or _infer_ticker(path)

    return {
        "id": Path(path).stem,
        "name": name,
        "ticker": ticker,
        "timeframe": fm.get("timeframe", "1d"),
        "buy": buy,
        "sell": sell,
        "description": _extract_description(text),
        "file": path,
        "last_return_pct": fm.get("last_return_pct"),
        "best_return_pct": fm.get("best_return_pct"),
    }


def _infer_ticker(path: str) -> str:
    """Guess the ticker from the filename."""
    name = Path(path).stem.upper()
    # Common tickers to look for
    for ticker in ["SPY", "QQQ", "NVDA", "TSLA", "SOUN", "AAPL", "MSFT", "BTC", "ETH"]:
        if ticker in name:
            return ticker
    return "SPY"


def load_all_strategies(folder: str) -> list[dict]:
    """Scan folder for .md files and return all valid strategy configs."""
    strategies = []
    for fname in sorted(os.listdir(folder)):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(folder, fname)
        try:
            s = load_strategy(path)
            if s:
                strategies.append(s)
        except Exception as e:
            print(f"[loader] skipped {fname}: {e}")
    return strategies
