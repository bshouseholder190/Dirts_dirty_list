import pandas as pd
import numpy as np


def calc_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta = closes.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_ema(closes: pd.Series, period: int) -> pd.Series:
    return closes.ewm(span=period, adjust=False).mean()


def calc_vwap(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Rolling VWAP over `period` bars using typical price * volume."""
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    tp_vol = typical * df["Volume"]
    return tp_vol.rolling(period).sum() / df["Volume"].rolling(period).sum()


def calc_sma(closes: pd.Series, period: int) -> pd.Series:
    return closes.rolling(period).mean()


def calc_session_vwap(df: pd.DataFrame) -> pd.Series:
    """
    True intraday VWAP — cumulative from today's session open.
    Falls back to rolling VWAP(20) on daily data.
    """
    try:
        today = pd.Timestamp.now(tz="UTC").normalize()
        if df.index.tzinfo is not None:
            today_mask = df.index.normalize() >= today
        else:
            today_mask = df.index.normalize() >= today.tz_localize(None)
        today_df = df[today_mask]
        if len(today_df) < 2:
            today_df = df.tail(80)
    except Exception:
        today_df = df.tail(80)

    typical = (today_df["High"] + today_df["Low"] + today_df["Close"]) / 3
    cum_tpv = (typical * today_df["Volume"]).cumsum()
    cum_vol  = today_df["Volume"].cumsum().replace(0, float("nan"))
    session_vwap = cum_tpv / cum_vol

    full = session_vwap.reindex(df.index)
    full = full.ffill().bfill()
    return full


def evaluate_condition(cond: dict, df: pd.DataFrame) -> bool:
    """Return True if the condition is satisfied on the latest bar."""
    kind = cond.get("type", "")
    close = df["Close"]
    last = close.iloc[-1]

    if kind == "rsi":
        period = cond.get("period", 14)
        value = cond.get("value", 50)
        signal = cond.get("signal", "above")
        rsi = calc_rsi(close, period)
        if len(rsi.dropna()) == 0:
            return False
        rsi_val = rsi.iloc[-1]
        return rsi_val > value if signal == "above" else rsi_val < value

    if kind == "vwap":
        period = cond.get("period", 20)
        signal = cond.get("signal", "above")
        vwap = calc_vwap(df, period)
        if len(vwap.dropna()) == 0:
            return False
        vwap_val = vwap.iloc[-1]
        return last > vwap_val if signal == "above" else last < vwap_val

    if kind == "session_vwap":
        signal = cond.get("signal", "above")
        vwap = calc_session_vwap(df)
        if len(vwap.dropna()) == 0:
            return False
        vwap_val = float(vwap.iloc[-1])
        return last > vwap_val if signal == "above" else last < vwap_val

    if kind == "ema":
        period = cond.get("period", 20)
        signal = cond.get("signal", "above")
        ema = calc_ema(close, period)
        ema_val = ema.iloc[-1]
        return last > ema_val if signal == "above" else last < ema_val

    if kind == "sma":
        period = cond.get("period", 20)
        signal = cond.get("signal", "above")
        sma = calc_sma(close, period)
        sma_val = sma.iloc[-1]
        return last > sma_val if signal == "above" else last < sma_val

    if kind == "price":
        value = cond.get("value", 0)
        signal = cond.get("signal", "above")
        return last > value if signal == "above" else last < value

    return False


def get_indicator_values(df: pd.DataFrame, strategy_cfg: dict) -> dict:
    """Compute current indicator values for display in the UI."""
    close = df["Close"]
    values = {"price": round(float(close.iloc[-1]), 4)}

    all_conditions = list(strategy_cfg.get("buy", {}).get("conditions", []))
    all_conditions += list(strategy_cfg.get("sell", {}).get("conditions", []))

    seen = set()
    for cond in all_conditions:
        kind = cond.get("type", "")
        period = cond.get("period", "")
        key = f"{kind}_{period}"
        if key in seen:
            continue
        seen.add(key)

        try:
            if kind == "rsi":
                rsi = calc_rsi(close, period)
                values[f"RSI({period})"] = round(float(rsi.iloc[-1]), 2)
            elif kind == "vwap":
                vwap = calc_vwap(df, period)
                values[f"VWAP({period})"] = round(float(vwap.iloc[-1]), 4)
            elif kind == "session_vwap":
                svwap = calc_session_vwap(df)
                values["VWAP(session)"] = round(float(svwap.iloc[-1]), 4)
            elif kind == "ema":
                ema = calc_ema(close, period)
                values[f"EMA({period})"] = round(float(ema.iloc[-1]), 4)
            elif kind == "sma":
                sma = calc_sma(close, period)
                values[f"SMA({period})"] = round(float(sma.iloc[-1]), 4)
        except Exception:
            pass

    return values
