"""Analyze evolution survivors and append lessons learned to Obsidian .md files."""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


VAULT_DIR = r"C:\Users\bshou\OneDrive\Documents\house's second Brain\skills n thoughts\Strategies"


def analyze_survivors(bots: list[dict]) -> dict:
    """Extract patterns from the top 50% of bots."""
    if not bots:
        return {}

    top = bots[:max(1, len(bots) // 2)]

    rsi_buys  = [b["genome"]["rsi_buy"]        for b in top]
    rsi_sells = [b["genome"]["rsi_sell"]       for b in top]
    rsi_periods = [b["genome"]["rsi_period"]   for b in top]
    ema_periods = [b["genome"]["ema_period"]   for b in top]
    stops       = [b["genome"]["stop_loss_pct"] for b in top]
    tps         = [b["genome"]["take_profit_pct"] for b in top]
    vwap_count  = sum(1 for b in top if b["genome"]["use_vwap"])
    fitnesses   = [b["fitness"] for b in top]
    win_rates   = [b["win_rate"] for b in top]
    trades_list = [b["trades"]  for b in top]

    def avg(lst): return round(sum(lst) / len(lst), 1)
    def rng(lst): return f"{min(lst):.1f}–{max(lst):.1f}"

    vwap_pct = round(vwap_count / len(top) * 100)
    vwap_helped = vwap_pct >= 60

    # Find dominant RSI period
    from collections import Counter
    rsi_period_counts = Counter(rsi_periods)
    dominant_rsi = rsi_period_counts.most_common(1)[0][0]
    ema_period_counts = Counter(ema_periods)
    dominant_ema = ema_period_counts.most_common(1)[0][0]

    return {
        "top_count": len(top),
        "avg_rsi_buy": avg(rsi_buys),
        "avg_rsi_sell": avg(rsi_sells),
        "rsi_buy_range": rng(rsi_buys),
        "rsi_sell_range": rng(rsi_sells),
        "dominant_rsi_period": dominant_rsi,
        "dominant_ema_period": dominant_ema,
        "avg_stop": avg(stops),
        "avg_tp": avg(tps),
        "stop_range": rng(stops),
        "tp_range": rng(tps),
        "vwap_pct": vwap_pct,
        "vwap_helped": vwap_helped,
        "avg_fitness": avg(fitnesses),
        "avg_win_rate": avg(win_rates),
        "avg_trades": avg(trades_list),
    }


def _plain_english(a: dict, ticker: str, generation: int) -> str:
    """Turn analysis dict into bullet-point insights."""
    lines = []

    # RSI buy zone
    buy = a["avg_rsi_buy"]
    if buy < 30:
        lines.append(f"- Deep oversold entries (RSI ~{buy}) worked — {ticker} rewards patience waiting for real dips")
    elif buy < 40:
        lines.append(f"- Mid-oversold entries (RSI ~{buy}) dominated — don't wait for extreme lows, momentum resets faster")
    else:
        lines.append(f"- Momentum entries (RSI ~{buy}) won — buying strength outperformed buying weakness on {ticker}")

    # RSI sell zone
    sell = a["avg_rsi_sell"]
    if sell > 72:
        lines.append(f"- Letting winners run to RSI ~{sell} paid off — {ticker} has strong trend continuation")
    else:
        lines.append(f"- Early exits at RSI ~{sell} were optimal — {ticker} fades quickly at overbought levels")

    # RSI period
    rp = a["dominant_rsi_period"]
    lines.append(f"- RSI({rp}) dominated — {'shorter period = more signals, better for volatile' if rp <= 9 else 'standard 14-period balanced noise vs signal' if rp == 14 else 'longer RSI filtered out false signals'} {ticker} moves")

    # EMA period
    ep = a["dominant_ema_period"]
    lines.append(f"- EMA({ep}) trend filter was optimal — {'fast trend detection suited' if ep <= 20 else 'medium-term trend filter reduced whipsaws on'} {ticker}")

    # VWAP
    if a["vwap_helped"]:
        lines.append(f"- VWAP filter helped ({a['vwap_pct']}% of survivors used it) — adds useful institutional price context")
    else:
        lines.append(f"- VWAP filter hurt performance ({a['vwap_pct']}% of survivors used it) — too restrictive for {ticker}'s daily swings")

    # Stop loss
    sl = a["avg_stop"]
    if sl < 5:
        lines.append(f"- Tight stops (~{sl}%) worked — {ticker} is mean-reverting, losers don't recover")
    elif sl < 9:
        lines.append(f"- Medium stops (~{sl}%) optimal — gives trades room to breathe without excessive loss")
    else:
        lines.append(f"- Wide stops (~{sl}%) needed — {ticker} is volatile, tight stops get whipsawed")

    # Take profit
    tp = a["avg_tp"]
    lines.append(f"- Take profit ~{tp}% was the sweet spot — {'let winners run' if tp > 20 else 'quick scalps suited this asset'} on {ticker}")

    # Win rate vs return tradeoff
    wr = a["avg_win_rate"]
    fitness = a["avg_fitness"]
    if wr < 40:
        lines.append(f"- Low win rate ({wr}%) but positive return (+{fitness}%) — few big winners offset many small losses (trend-following behavior)")
    elif wr > 60:
        lines.append(f"- High win rate ({wr}%) — strategy found consistent edge, not just lucky outliers")
    else:
        lines.append(f"- Balanced win rate ({wr}%) with {fitness:+.1f}% avg return — solid risk/reward ratio")

    return "\n".join(lines)


def build_lesson_block(
    ticker: str,
    generation: int,
    bots: list[dict],
    history: list[dict],
) -> str:
    """Build the full markdown block to append."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    a = analyze_survivors(bots)
    if not a:
        return ""

    best_bot = bots[0] if bots else None
    best_genome = best_bot["genome"] if best_bot else {}

    gen_stats = history[-1] if history else {}
    best_fit  = gen_stats.get("best", 0)
    avg_fit   = gen_stats.get("avg", 0)
    worst_fit = gen_stats.get("worst", 0)

    insights = _plain_english(a, ticker, generation)

    block = f"""
---

## Evolution Run {now} — {ticker} · Gen {generation}

**Winning Genome (Bot #{best_bot['id'] if best_bot else '?'}):**
- RSI Buy: {best_genome.get('rsi_buy', '?')} → Sell: {best_genome.get('rsi_sell', '?')} · Period: RSI({best_genome.get('rsi_period', '?')})
- EMA Period: {best_genome.get('ema_period', '?')} · VWAP: {'✓' if best_genome.get('use_vwap') else '✗'}
- Stop Loss: {best_genome.get('stop_loss_pct', '?')}% · Take Profit: {best_genome.get('take_profit_pct', '?')}%
- Fitness: {best_bot['fitness'] if best_bot else 0:+.1f}% · Win Rate: {best_bot['win_rate'] if best_bot else 0}% · {best_bot['trades'] if best_bot else 0} trades

**Population Summary (Gen {generation}):**
- Best: {best_fit:+.1f}% · Avg: {avg_fit:+.1f}% · Worst: {worst_fit:+.1f}%
- Survivors analysed: top {a['top_count']} of {len(bots)} bots
- RSI buy zone: {a['rsi_buy_range']} (avg {a['avg_rsi_buy']}) · Sell zone: {a['rsi_sell_range']} (avg {a['avg_rsi_sell']})
- Stop range: {a['stop_range']}% · TP range: {a['tp_range']}%

**What the bots learned:**
{insights}
"""
    return block


def find_strategy_file(ticker: str) -> Optional[str]:
    """Find the best matching .md file in the vault for this ticker."""
    ticker_upper = ticker.replace("-", "").upper()

    # Direct match in app strategies folder
    app_strategies = r"C:\Users\bshou\projects\trading-app\strategies"
    for fname in os.listdir(app_strategies):
        if ticker_upper.replace("USD", "") in fname.upper() and fname.endswith(".md"):
            return os.path.join(app_strategies, fname)

    # Search Obsidian vault
    for fname in os.listdir(VAULT_DIR):
        if not fname.endswith(".md"):
            continue
        if ticker_upper.replace("USD", "") in fname.upper():
            return os.path.join(VAULT_DIR, fname)

    return None


def update_strategy_params(path: str, winning_genome: dict) -> None:
    """Rewrite the YAML frontmatter of a strategy file with the winning genome's params."""
    import re, yaml

    with open(path, encoding="utf-8") as f:
        text = f.read()

    FM_RE = re.compile(r"^\s*---\s*\n(.*?)\n---", re.DOTALL)
    m = FM_RE.search(text)
    if not m:
        return

    try:
        fm = yaml.safe_load(m.group(1))
        if not isinstance(fm, dict):
            return
    except Exception:
        return

    rsi_period = winning_genome.get("rsi_period", 14)
    rsi_buy    = round(winning_genome.get("rsi_buy", 30), 1)
    rsi_sell   = round(winning_genome.get("rsi_sell", 70), 1)
    ema_period = winning_genome.get("ema_period", 20)
    use_vwap   = winning_genome.get("use_vwap", False)
    stop_pct   = round(winning_genome.get("stop_loss_pct", 7) / 100, 3)
    tp_pct     = round(winning_genome.get("take_profit_pct", 15) / 100, 3)

    buy_conditions = [
        {"type": "rsi", "period": rsi_period, "signal": "above", "value": rsi_buy},
        {"type": "ema", "period": ema_period, "signal": "above"},
    ]
    if use_vwap:
        buy_conditions.append({"type": "vwap", "period": 20, "signal": "above"})

    fm["buy"] = {"conditions": buy_conditions}
    fm["sell"] = {
        "conditions": [{"type": "rsi", "period": rsi_period, "signal": "above", "value": rsi_sell}],
        "stop_loss_pct": stop_pct,
        "take_profit_pct": tp_pct,
    }

    new_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_text = text[:m.start()] + "---\n" + new_yaml + "---" + text[m.end():]

    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)


def append_lessons(ticker: str, generation: int, bots: list[dict], history: list[dict]) -> str:
    """
    Build lesson block and append to the matching strategy .md file.
    Returns the path written to, or an error message.
    """
    block = build_lesson_block(ticker, generation, bots, history)
    if not block:
        return "no data to write"

    path = find_strategy_file(ticker)

    # If no existing file found, create one in app strategies folder
    if not path:
        clean = ticker.replace("-", "-").upper()
        path = os.path.join(
            r"C:\Users\bshou\projects\trading-app\strategies",
            f"{clean}-Evolution-Lessons.md"
        )
        # Write header
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"---\nname: {ticker} Evolution Lessons\nticker: {ticker}\n---\n\n# {ticker} — Evolution Lessons\n\nAuto-generated lessons from genetic algorithm simulations.\n")

    with open(path, "a", encoding="utf-8") as f:
        f.write(block)

    return path
