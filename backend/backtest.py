"""Extensible backtesting engine.

To add a new strategy, write a function decorated with @strategy(...). It
receives a price DataFrame (DatetimeIndex; columns open/high/low/close/volume)
plus a params dict, and returns a *position* series (0..1 = fraction invested
that day). The engine converts positions -> daily returns -> equity curve and
computes the performance metrics. Positions are shifted one day inside each
strategy so signals are acted on the *next* bar (no look-ahead).

Registered strategies are exposed via list_strategies() and run by key, so the
frontend stays generic — new strategies show up automatically.
"""
import numpy as np
import pandas as pd

import db

TRADING_DAYS = 252

STRATEGIES = {}


def strategy(key, name, params=None):
    def deco(fn):
        STRATEGIES[key] = {"key": key, "name": name, "params": params or [], "fn": fn}
        return fn
    return deco


# --- indicator helpers (also reused by the technical-indicator API) --------

def sma(s, n):
    return s.rolling(int(n), min_periods=1).mean()


def rsi(close, n=14):
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def kd(df, n=9, k_smooth=3, d_smooth=3):
    low_n = df["low"].rolling(n, min_periods=1).min()
    high_n = df["high"].rolling(n, min_periods=1).max()
    denom = (high_n - low_n).replace(0, np.nan)
    rsv = ((df["close"] - low_n) / denom * 100).fillna(50).values
    k = np.empty(len(rsv))
    d = np.empty(len(rsv))
    prev_k = prev_d = 50.0
    ak, ad = 1.0 / k_smooth, 1.0 / d_smooth
    for i, r in enumerate(rsv):
        prev_k = prev_k + ak * (r - prev_k)
        prev_d = prev_d + ad * (prev_k - prev_d)
        k[i] = prev_k
        d[i] = prev_d
    return pd.Series(k, index=df.index), pd.Series(d, index=df.index)


def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig


# --- strategies ------------------------------------------------------------

@strategy("buy_hold", "Buy & Hold 買進持有")
def s_buy_hold(df, p):
    return pd.Series(1.0, index=df.index)


@strategy("sma_cross", "均線交叉 MA Cross", [
    {"name": "fast", "label": "快線", "default": 20},
    {"name": "slow", "label": "慢線", "default": 60},
])
def s_sma_cross(df, p):
    fast = sma(df["close"], p.get("fast", 20))
    slow = sma(df["close"], p.get("slow", 60))
    return (fast > slow).astype(float).shift(1).fillna(0)


@strategy("kd_cross", "KD 黃金交叉", [
    {"name": "n", "label": "RSV 期間", "default": 9},
    {"name": "k", "label": "K 平滑", "default": 3},
    {"name": "d", "label": "D 平滑", "default": 3},
])
def s_kd_cross(df, p):
    k, d = kd(df, int(p.get("n", 9)), int(p.get("k", 3)), int(p.get("d", 3)))
    return (k > d).astype(float).shift(1).fillna(0)


@strategy("rsi_reversion", "RSI 超賣進場", [
    {"name": "n", "label": "RSI 期間", "default": 14},
    {"name": "buy", "label": "買進門檻 (<)", "default": 30},
    {"name": "sell", "label": "出場門檻 (>)", "default": 60},
])
def s_rsi_reversion(df, p):
    r = rsi(df["close"], int(p.get("n", 14)))
    buy, sell = float(p.get("buy", 30)), float(p.get("sell", 60))
    pos = np.zeros(len(r))
    holding = False
    for i, v in enumerate(r.values):
        if not holding and v < buy:
            holding = True
        elif holding and v > sell:
            holding = False
        pos[i] = 1.0 if holding else 0.0
    return pd.Series(pos, index=df.index).shift(1).fillna(0)


@strategy("macd_cross", "MACD 交叉", [
    {"name": "fast", "label": "快 EMA", "default": 12},
    {"name": "slow", "label": "慢 EMA", "default": 26},
    {"name": "signal", "label": "訊號 EMA", "default": 9},
])
def s_macd_cross(df, p):
    line, sig = macd(df["close"], int(p.get("fast", 12)),
                     int(p.get("slow", 26)), int(p.get("signal", 9)))
    return (line > sig).astype(float).shift(1).fillna(0)


@strategy("streak_scale", "連漲分批買 / 連跌分批賣", [
    {"name": "up", "label": "連漲幾日→買", "default": 5},
    {"name": "down", "label": "連跌幾日→賣", "default": 5},
    {"name": "buy_pct", "label": "每次買進 (剩餘現金%)", "default": 50},
    {"name": "sell_pct", "label": "每次賣出 (持股%)", "default": 50},
])
def s_streak_scale(df, p):
    """連續 N 日收盤上漲 → 隔日開盤買進剩餘現金的一部分；連續 N 日收盤下跌
    → 隔日開盤賣出持股的一部分。內部以「現金 + 持股」狀態機模擬，每天收盤
    換算出資產佔比 w，再 shift(1) 讓訊號隔日才生效（無未來函數）。引擎只有
    收盤對收盤報酬，故成交價近似用前一日收盤 ≈ 隔日開盤。"""
    up_n = max(int(p.get("up", 5)), 1)
    down_n = max(int(p.get("down", 5)), 1)
    buy_f = min(max(float(p.get("buy_pct", 50)) / 100.0, 0.0), 1.0)
    sell_f = min(max(float(p.get("sell_pct", 50)) / 100.0, 0.0), 1.0)

    close = df["close"].astype(float)
    chg = close.diff()
    # 連漲/連跌：過去 N 日的日漲跌全部同向（rolling 視窗）
    up_streak = (chg > 0).rolling(up_n).sum().fillna(0).values >= up_n
    down_streak = (chg < 0).rolling(down_n).sum().fillna(0).values >= down_n
    prices = close.values

    n = len(prices)
    cash, shares = 1.0, 0.0          # 正規化起始資金，全為現金
    w = np.zeros(n)                  # 每日收盤後的資產佔比（成交後）
    for i in range(n):
        px = prices[i]
        if up_streak[i]:             # 連漲 → 買進剩餘現金的 buy_f
            spend = cash * buy_f
            shares += spend / px
            cash -= spend
        elif down_streak[i]:         # 連跌 → 賣出持股的 sell_f
            qty = shares * sell_f
            cash += qty * px
            shares -= qty
        asset = shares * px
        total = asset + cash
        w[i] = asset / total if total > 0 else 0.0

    return pd.Series(w, index=df.index).shift(1).fillna(0)


# --- engine ----------------------------------------------------------------

def _load_df(symbol, start, end):
    rows = db.get_prices(symbol, start=start, end=end)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _metrics(daily_ret, equity):
    if equity is None or len(equity) < 2:
        return None
    total = float(equity.iloc[-1] / equity.iloc[0] - 1)
    days = max((equity.index[-1] - equity.index[0]).days, 1)
    years = days / 365.25
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0
    vol = float(daily_ret.std() * np.sqrt(TRADING_DAYS))
    sharpe = float(daily_ret.mean() * TRADING_DAYS / vol) if vol > 0 else 0.0
    max_dd = float((equity / equity.cummax() - 1).min())
    return {
        "total_return": total,
        "cagr": cagr,
        "ann_vol": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "final_value": float(equity.iloc[-1]),
    }


def _curve(equity):
    return [{"date": d.strftime("%Y-%m-%d"), "value": round(float(v), 2)}
            for d, v in equity.items()]


def list_strategies():
    return [{"key": s["key"], "name": s["name"], "params": s["params"]}
            for s in STRATEGIES.values()]


def run_backtest(symbols, strategy_key, params, start, end, benchmark, initial_capital):
    if strategy_key not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy_key}")
    if not symbols:
        raise ValueError("no symbols selected")
    fn = STRATEGIES[strategy_key]["fn"]
    params = params or {}

    per = {}
    used, missing = [], []
    for sym in symbols:
        df = _load_df(sym, start, end)
        if df is None or len(df) < 5:
            missing.append(sym)
            continue
        pos = fn(df, params).clip(0, 1).fillna(0)
        ret = df["close"].pct_change().fillna(0) * pos
        per[sym] = ret
        used.append(sym)

    if not per:
        raise ValueError("no price data for the selected symbols/range")

    # Equal-weight portfolio: average daily strategy return across symbols.
    port_ret = pd.concat(per, axis=1).mean(axis=1).dropna()
    port_eq = (1 + port_ret).cumprod() * initial_capital

    result = {
        "strategy": strategy_key,
        "initial_capital": initial_capital,
        "symbols_used": used,
        "symbols_missing": missing,
        "portfolio": {"metrics": _metrics(port_ret, port_eq), "curve": _curve(port_eq)},
        "benchmark": None,
    }

    if benchmark:
        bdf = _load_df(benchmark, start, end)
        if bdf is not None and len(bdf) >= 2:
            bret = bdf["close"].pct_change().fillna(0)
            beq = (1 + bret).cumprod() * initial_capital
            result["benchmark"] = {
                "symbol": benchmark,
                "metrics": _metrics(bret, beq),
                "curve": _curve(beq),
            }
    return result
