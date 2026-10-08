"""Yahoo Finance download helpers (via yfinance).

Normalises a yfinance history DataFrame into the row dicts that db.upsert_prices
expects. Keeps network concerns (retries, throttling) in one place.
"""
import time

import pandas as pd
import yfinance as yf


def _normalize(df):
    """Turn a yfinance history DataFrame into a list of price-row dicts."""
    if df is None or df.empty:
        return []
    df = df.reset_index()
    # Date column is "Date" for daily data; normalise to YYYY-MM-DD strings.
    date_col = "Date" if "Date" in df.columns else df.columns[0]

    def col(name):
        return df[name] if name in df.columns else pd.Series([None] * len(df))

    rows = []
    dates = pd.to_datetime(df[date_col])
    o, h, l, c = col("Open"), col("High"), col("Low"), col("Close")
    ac = col("Adj Close") if "Adj Close" in df.columns else c
    v = col("Volume")
    for i in range(len(df)):
        close = c.iloc[i]
        if pd.isna(close):
            continue  # skip non-trading rows
        rows.append(
            {
                "date": dates.iloc[i].strftime("%Y-%m-%d"),
                "open": _f(o.iloc[i]),
                "high": _f(h.iloc[i]),
                "low": _f(l.iloc[i]),
                "close": _f(close),
                "adj_close": _f(ac.iloc[i]),
                "volume": _i(v.iloc[i]),
            }
        )
    return rows


def _f(x):
    return None if pd.isna(x) else float(x)


def _i(x):
    return None if pd.isna(x) else int(x)


def fetch_history(symbol, period="max", start=None, retries=3, pause=1.0):
    """Fetch daily history for a symbol.

    If `start` is given (YYYY-MM-DD), fetches from that date forward;
    otherwise uses `period` (default the full available history).
    """
    last_err = None
    for attempt in range(retries):
        try:
            tk = yf.Ticker(symbol)
            if start:
                df = tk.history(start=start, interval="1d", auto_adjust=False)
            else:
                df = tk.history(period=period, interval="1d", auto_adjust=False)
            return _normalize(df)
        except Exception as e:  # noqa: BLE001 - report and retry
            last_err = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"failed to fetch {symbol}: {last_err}")


def _normalize_intraday(df):
    """Turn an intraday yfinance DataFrame into epoch-keyed row dicts.

    Yahoo returns a tz-aware Datetime index (exchange timezone). We drop the
    tz keeping the wall-clock numbers, then encode as epoch seconds — so charts
    that render in UTC actually display the local market time-of-day.
    """
    if df is None or df.empty:
        return []
    df = df.reset_index()
    dt_col = "Datetime" if "Datetime" in df.columns else df.columns[0]
    dt = pd.to_datetime(df[dt_col])
    if getattr(dt.dt, "tz", None) is not None:
        dt = dt.dt.tz_localize(None)  # keep wall-clock, drop tz
    epochs = (dt.astype("int64") // 10**9).tolist()

    def col(name):
        return df[name] if name in df.columns else pd.Series([None] * len(df))

    o, h, l, c, v = col("Open"), col("High"), col("Low"), col("Close"), col("Volume")
    rows = []
    for i in range(len(df)):
        close = c.iloc[i]
        if pd.isna(close):
            continue
        rows.append({
            "ts": int(epochs[i]),
            "open": _f(o.iloc[i]),
            "high": _f(h.iloc[i]),
            "low": _f(l.iloc[i]),
            "close": _f(close),
            "volume": _i(v.iloc[i]),
        })
    return rows


def fetch_intraday(symbol, interval="5m", period="60d", start=None, retries=3, pause=1.0):
    """Fetch intraday bars. For 5m, Yahoo only serves ~60 days, so `period`
    defaults to 60d; `start` (YYYY-MM-DD) does an incremental pull."""
    last_err = None
    for attempt in range(retries):
        try:
            tk = yf.Ticker(symbol)
            if start:
                df = tk.history(start=start, interval=interval, auto_adjust=False)
            else:
                df = tk.history(period=period, interval=interval, auto_adjust=False)
            return _normalize_intraday(df)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"failed to fetch intraday {symbol}: {last_err}")


def fetch_currency(symbol):
    """Best-effort currency lookup; returns None on any failure."""
    try:
        info = yf.Ticker(symbol).fast_info
        return getattr(info, "currency", None) or info.get("currency")
    except Exception:
        return None
