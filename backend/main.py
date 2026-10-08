"""FastAPI backend for the Taiwan + US stock viewer.

Run (from the backend dir, with the conda env active):
    uvicorn main:app --reload --port 8000
"""
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import fetch
import backtest
import taifex
import pair_strategy
import pair_strategy_v2
import pair_strategy_lite
import trade_log
import sinopac_quote
import quote_tracker
import daily_close
import log_rotation
import holdings
import asyncio

app = FastAPI(title="Stock Viewer API")

# The browser only ever talks to the Vite dev server (5173), which proxies
# /api here, so it's the only cross-origin caller that needs to be allowed.
# A wildcard would let any web page open in the same browser read this API
# (including /api/holdings' real account inventory) via fetch to localhost:8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    db.init_schema()
    try:
        log_rotation.rotate_quote_logs()
    except Exception:  # noqa: BLE001 -- housekeeping must never block startup
        pass
    asyncio.create_task(quote_tracker.run_forever())
    asyncio.create_task(daily_close.run_forever())


# range string -> number of days back (None means "everything")
RANGE_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 731,
    "3y": 1096,
    "5y": 1827,
    "10y": 3653,
    "max": None,
}


def _range_start(range_):
    days = RANGE_DAYS.get(range_, 186)  # default ~6 months
    if days is None:
        return None
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


# Intraday range -> calendar days of bars to return (None = all, ~60d cap).
INTRADAY_RANGE_DAYS = {"1d": 1, "5d": 5, "1mo": 30, "max": None}


def _with_quote(sym):
    sym = dict(sym)
    sym["quote"] = db.latest_quote(sym["symbol"])
    sym["is_tracked"] = db.is_tracked(sym["symbol"])
    return sym


def _fetch_daily_rows(sym_row, last):
    """Route a daily fetch to the right source (yahoo vs taifex futures)."""
    if (sym_row.get("source") or "yahoo") == "taifex":
        return taifex.fetch_daily(sym_row["symbol"], start_date=last)
    symbol = sym_row["symbol"]
    return (fetch.fetch_history(symbol, start=last) if last
            else fetch.fetch_history(symbol, period="max"))


# --- models ---------------------------------------------------------------

class HomeIndicesIn(BaseModel):
    symbols: list[str]


class TrackedSymbolIn(BaseModel):
    symbol: str


class TrackedOrderIn(BaseModel):
    symbols: list[str]


class PipHiddenIn(BaseModel):
    hidden: bool


class LiteOverrideIn(BaseModel):
    level: int  # 0/1/2
    side: int   # -1/0/+1, matches diff's sign convention; 0 only valid at level 0


class AddSymbolIn(BaseModel):
    symbol: str
    name: str | None = None
    market: str | None = None
    type: str | None = "stock"


class TradeLogIn(BaseModel):
    name: str
    pair_source: str | None = None
    pair_key: str | None = None
    symbol_a: str
    symbol_b: str
    name_a: str
    name_b: str
    initial_capital: float
    start_date: str
    notes: str | None = None


class TradeEntryIn(BaseModel):
    date: str
    symbol: str
    side: str  # buy | sell
    shares: float
    price: float
    fee: float = 0
    note: str | None = None


class TradeEntryPatch(BaseModel):
    included: bool


class TradeLogPatch(BaseModel):
    initial_capital: float
    start_date: str


class TradeLogPriceIn(BaseModel):
    price_a: float
    price_b: float


class TradeLogStartPriceIn(BaseModel):
    start_price_a: float
    start_price_b: float


class BacktestIn(BaseModel):
    symbols: list[str]
    strategy: str = "sma_cross"
    params: dict = {}
    range: str = "3y"
    benchmark: str | None = "^TWII"
    initial_capital: float = 100000


# --- routes ----------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/symbols")
def get_symbols(market: str | None = None, type: str | None = None,
                q: str | None = None, with_quote: bool = False):
    rows = db.list_symbols(market=market, type_=type, q=q)
    if with_quote:
        rows = [_with_quote(r) for r in rows]
    return rows


@app.get("/api/symbols/{symbol}")
def get_symbol(symbol: str):
    sym = db.get_symbol(symbol)
    if not sym:
        raise HTTPException(404, f"unknown symbol {symbol}")
    sym = _with_quote(sym)
    sym["bars"] = db.price_count(symbol)
    sym["last_date"] = db.last_price_date(symbol)
    return sym


@app.get("/api/symbols/{symbol}/prices")
def get_symbol_prices(symbol: str, range: str = "6mo", interval: str = "1d"):
    if not db.get_symbol(symbol):
        raise HTTPException(404, f"unknown symbol {symbol}")
    if interval == "1d":
        prices = db.get_prices(symbol, start=_range_start(range))
    else:
        days = INTRADAY_RANGE_DAYS.get(range, 5)
        prices = db.get_intraday(symbol, interval, days=days)
    return {"symbol": symbol, "range": range, "interval": interval, "prices": prices}


@app.post("/api/symbols/{symbol}/update")
def update_symbol(symbol: str, interval: str = "1d"):
    """Crawl fresh data from Yahoo and upsert. Used by the Update button.

    interval=1d updates daily history; interval=5m (etc.) updates the rolling
    intraday window (Yahoo only serves ~60 days for 5m)."""
    sym = db.get_symbol(symbol)
    if not sym:
        raise HTTPException(404, f"unknown symbol {symbol}")

    if interval == "1d":
        last = db.last_price_date(symbol)
        try:
            rows = _fetch_daily_rows(sym, last)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"fetch failed: {e}")
        written = db.upsert_prices(symbol, rows)
        return {
            "symbol": symbol, "interval": interval, "rows_written": written,
            "last_date": db.last_price_date(symbol), "total_bars": db.price_count(symbol),
        }

    # intraday
    last_ts = db.last_intraday_ts(symbol, interval)
    min_date = (datetime.now() - timedelta(days=59)).strftime("%Y-%m-%d")
    try:
        if last_ts:
            start_date = datetime.utcfromtimestamp(last_ts).strftime("%Y-%m-%d")
            if start_date < min_date:
                start_date = min_date
            rows = fetch.fetch_intraday(symbol, interval=interval, start=start_date)
        else:
            rows = fetch.fetch_intraday(symbol, interval=interval, period="60d")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"fetch failed: {e}")
    written = db.upsert_intraday(symbol, interval, rows)
    return {
        "symbol": symbol, "interval": interval, "rows_written": written,
        "total_bars": db.intraday_count(symbol, interval),
    }


@app.post("/api/symbols")
def add_symbol(body: AddSymbolIn):
    """Add a new ticker to track and immediately pull its full history."""
    symbol = body.symbol.strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    market = body.market or ("TW" if symbol.upper().endswith((".TW", ".TWO")) else "US")
    name = body.name or symbol
    currency = fetch.fetch_currency(symbol)
    db.upsert_symbol(symbol, name, market, body.type or "stock", currency)
    try:
        rows = fetch.fetch_history(symbol, period="max")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"fetch failed: {e}")
    written = db.upsert_prices(symbol, rows)
    return {"symbol": symbol, "rows_written": written, "last_date": db.last_price_date(symbol)}


@app.get("/api/holdings")
def get_holdings():
    """Sinopac account inventory (read-only, display only -- see
    holdings.py). 502 if the quote service can't answer, with its own
    message so the page can say why (e.g. key without 帳務 permission)."""
    try:
        return holdings.build_holdings()
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.get("/api/tracked-symbols")
def get_tracked_symbols():
    """The global live-quote watchlist (see quote_tracker.py) -- symbols
    here have their TODAY price kept continuously fresh off Sinopac
    whenever the market's open, so every reader in the app shows the live
    price automatically instead of just the last EOD close."""
    out = []
    hidden = db.pip_hidden_symbols()
    for sym in db.list_tracked_symbols():
        info = db.get_symbol(sym) or {"symbol": sym, "name": sym, "market": None, "type": None}
        info = _with_quote(info)
        info["pip_hidden"] = sym in hidden
        out.append(info)
    return out


@app.post("/api/tracked-symbols")
def add_tracked_symbol(body: TrackedSymbolIn):
    symbol = body.symbol.strip()
    if not symbol:
        raise HTTPException(400, "symbol required")
    if not db.get_symbol(symbol):
        raise HTTPException(404, f"unknown symbol {symbol}（請先透過「新增股票」加入股票清單）")
    db.add_tracked_symbol(symbol)
    return get_tracked_symbols()


@app.put("/api/tracked-symbols/order")
def set_tracked_order(body: TrackedOrderIn):
    db.set_tracked_order(body.symbols)
    return get_tracked_symbols()


@app.put("/api/tracked-symbols/{symbol}/pip-hidden")
def set_tracked_pip_hidden(symbol: str, body: PipHiddenIn):
    """Hide/show a tracked symbol in the PiP mini window only -- it stays
    tracked (still live-polled) and still listed on every web page."""
    if not db.is_tracked(symbol):
        raise HTTPException(404, f"{symbol} is not tracked")
    db.set_tracked_pip_hidden(symbol, body.hidden)
    return get_tracked_symbols()


@app.delete("/api/tracked-symbols/{symbol}")
def remove_tracked_symbol(symbol: str):
    db.remove_tracked_symbol(symbol)
    return get_tracked_symbols()


@app.get("/api/home/indices")
def home_indices():
    symbols = db.get_home_indices()
    out = []
    for s in symbols:
        sym = db.get_symbol(s)
        if sym:
            out.append(_with_quote(sym))
    return out


@app.put("/api/home/indices")
def set_home_indices(body: HomeIndicesIn):
    # Validate every symbol exists before saving.
    for s in body.symbols:
        if not db.get_symbol(s):
            raise HTTPException(400, f"unknown symbol {s}")
    db.set_home_indices(body.symbols)
    return {"symbols": db.get_home_indices()}


@app.post("/api/update-all")
def update_all():
    """Incrementally crawl fresh data for every tracked symbol (one-click)."""
    rows_meta = db.list_symbols()
    updated, total, failed = [], 0, []
    for s in rows_meta:
        symbol = s["symbol"]
        last = db.last_price_date(symbol)
        try:
            rows = _fetch_daily_rows(s, last)
            w = db.upsert_prices(symbol, rows)
            total += w
            updated.append({"symbol": symbol, "rows_written": w, "last_date": db.last_price_date(symbol)})
        except Exception as e:  # noqa: BLE001
            failed.append({"symbol": symbol, "error": str(e)})
    return {"symbols": len(rows_meta), "updated": len(updated), "rows_written": total, "failed": failed}


@app.get("/api/pair-strategy/config")
def pair_strategy_config():
    return {"pairs": pair_strategy.PAIR_PARAMS, "excluded": pair_strategy.EXCLUDED}


@app.get("/api/pair-strategy/dates")
def pair_strategy_dates():
    return {"dates": pair_strategy.list_available_dates()}


@app.get("/api/pair-strategy/signals")
def pair_strategy_signals(date: str | None = None):
    return {"date": date, "signals": pair_strategy.all_signals(date)}


# v2: same 4 pairs, same underlying symbols (kept fresh by the /update
# endpoint below already), just a different dev/baseline formula -- see
# pair_strategy_v2.py's docstring. No separate update endpoint needed.
@app.get("/api/pair-strategy-v2/config")
def pair_strategy_v2_config():
    return {"pairs": pair_strategy_v2.PAIR_PARAMS}


@app.get("/api/pair-strategy-v2/dates")
def pair_strategy_v2_dates():
    return {"dates": pair_strategy_v2.list_available_dates()}


@app.get("/api/pair-strategy-v2/signals")
def pair_strategy_v2_signals(date: str | None = None):
    return {"date": date, "signals": pair_strategy_v2.all_signals(date)}


# lite: same 4 pairs/symbols, same rolling-MA formula as v1, just each
# pair's ladder cut to 2 levels (its old 3rd/6th tier, re-tuned) at 50%
# sold per level instead of 6 levels at 30% -- see pair_strategy_lite.py.
@app.get("/api/pair-strategy-lite/config")
def pair_strategy_lite_config():
    return {"pairs": pair_strategy_lite.PAIR_PARAMS}


@app.get("/api/pair-strategy-lite/dates")
def pair_strategy_lite_dates():
    return {"dates": pair_strategy_lite.list_available_dates()}


@app.get("/api/pair-strategy-lite/quotes")
def pair_strategy_lite_quotes(date: str | None = None):
    """Quote (date/close/prev_close/change_pct) per symbol, as of `date`
    if given (browsing a specific historical day) or the true latest
    otherwise -- the "前一天" reference the frontend shows for untracked
    pairs, and the baseline the live poll's price gets compared against
    to compute today's live % change for tracked ones."""
    return {sym: db.latest_quote(sym, as_of=date) for sym in pair_strategy_lite.ALL_SYMBOLS}


@app.get("/api/pair-strategy-lite/index-quotes")
def pair_strategy_lite_index_quotes(date: str | None = None):
    """Same shape/semantics as /quotes above, for the reference indices
    (^TWII, 0050.TW) shown next to the toolbar -- keyed by INDEX_SYMBOLS'
    short key instead of the raw yahoo symbol so the frontend doesn't have
    to know/encode '^TWII' itself."""
    return {
        key: db.latest_quote(cfg["symbol"], as_of=date)
        for key, cfg in pair_strategy_lite.INDEX_SYMBOLS.items()
    }


@app.get("/api/pair-strategy-lite/signals")
def pair_strategy_lite_signals(date: str | None = None):
    return {"date": date, "signals": pair_strategy_lite.all_signals(date)}


@app.get("/api/pair-strategy-lite/overrides")
def pair_strategy_lite_overrides():
    """Manual corrections to the displayed position state (level/side) --
    the computed state is purely a function of price history, but the
    user's real holdings can drift from it (a manual trade outside the
    app, a partial fill, ...). Keyed by pair_key; a pair with no override
    is omitted (the frontend falls back to the computed value)."""
    return db.list_lite_overrides()


@app.put("/api/pair-strategy-lite/overrides/{pair_key}")
def set_pair_strategy_lite_override(pair_key: str, body: LiteOverrideIn):
    if pair_key not in pair_strategy_lite.PAIR_PARAMS:
        raise HTTPException(404, f"unknown pair {pair_key}")
    if body.level not in (0, 1, 2):
        raise HTTPException(400, "level must be 0, 1, or 2")
    if body.side not in (-1, 0, 1):
        raise HTTPException(400, "side must be -1, 0, or 1")
    if (body.level == 0) != (body.side == 0):
        raise HTTPException(400, "side must be 0 iff level is 0")
    now = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    db.set_lite_override(pair_key, body.level, body.side, updated_at=now)
    return {"ok": True}


@app.delete("/api/pair-strategy-lite/overrides/{pair_key}")
def clear_pair_strategy_lite_override(pair_key: str):
    if pair_key not in pair_strategy_lite.PAIR_PARAMS:
        raise HTTPException(404, f"unknown pair {pair_key}")
    db.clear_lite_override(pair_key)
    return {"ok": True}


def _tse_market_open(now):
    return now.weekday() < 5 and dtime(9, 0) <= now.time() <= dtime(13, 30)


@app.get("/api/pair-strategy-lite/live")
def pair_strategy_lite_live():
    """Intraday "is today about to trigger anything" check, for whichever
    pairs have BOTH symbols in the global tracked-symbols watchlist (see
    /api/tracked-symbols) -- polled every ~15s by the frontend. A tracked
    pair's TODAY row is usually already real by the time this runs
    (quote_tracker's background poller keeps it fresh), so this mostly
    just reads compute_pair_signal's own result; live_check() also copes
    with a not-yet-polled pair by splicing a Sinopac quote on as a
    hypothetical extra day.

    Gated on TSE trading hours (weekdays 09:00-13:30 Taipei) -- outside
    that window quotes don't move, so there's nothing to check (the
    frontend may still poll every 15s if the tab is left open all day)."""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    if not _tse_market_open(now):
        return {"quote_service_ok": True, "market_open": False, "results": []}

    tracked_pairs = [
        (k, cfg) for k, cfg in pair_strategy_lite.PAIR_PARAMS.items()
        if db.is_tracked(cfg["symA"]) and db.is_tracked(cfg["symB"])
    ]
    today_str = now.strftime("%Y-%m-%d")
    if not tracked_pairs:
        return {"quote_service_ok": sinopac_quote.service_available(), "market_open": True, "checked_at": today_str, "results": []}

    symbols = sorted({s for _, cfg in tracked_pairs for s in (cfg["symA"], cfg["symB"])})
    try:
        prices = sinopac_quote.get_prices(symbols)
    except Exception:  # noqa: BLE001
        prices = {}
    # get_prices() itself swallows connection errors per-symbol (returns
    # None rather than raising), so reachability has to be checked
    # separately -- otherwise a genuinely-down quote service silently
    # reports "ok" while quietly finding nothing to alert on.
    ok = sinopac_quote.service_available()

    overrides = db.list_lite_overrides()
    results = []
    for k, cfg in tracked_pairs:
        pa, pb = prices.get(cfg["symA"]), prices.get(cfg["symB"])
        result = pair_strategy_lite.live_check(k, pa, pb, today_str)
        if result:
            override = overrides.get(k)
            if override:
                result = pair_strategy_lite.apply_override(result, override, cfg)
            results.append(result)
    return {"quote_service_ok": ok, "market_open": True, "checked_at": today_str, "results": results}


# The pair symbols plus the reference indices shown next to the lite tab's
# toolbar -- both get refreshed by the same /api/pair-strategy/update click
# (indices aren't part of any pair, but they're plain TW-listed instruments
# same as the pairs, so the same Sinopac/yfinance update logic applies).
PAIR_STRATEGY_UPDATE_SYMBOLS = sorted(
    set(pair_strategy.ALL_SYMBOLS) | {v["symbol"] for v in pair_strategy_lite.INDEX_SYMBOLS.values()}
)


@app.post("/api/pair-strategy/update")
def pair_strategy_update():
    """Only fetch symbols that are actually missing today's *settled* close
    -- not a blind refetch of all 14 every click. Still gated on TWSE having
    closed (13:30 Taipei, plus daily_close.CLOSE_BUFFER) so we never treat
    an intraday snapshot as final.

    Checks last_final_price_date() rather than last_price_date(): a tracked
    symbol's "today" row can already exist by the time this runs even
    though it was never actually updated here -- quote_tracker's poller
    writes one throughout the session from live snapshots (is_final=False),
    which isn't necessarily the same price as the official closing
    auction. Only a row the poller itself wrote is ever non-final, so this
    naturally limits the extra fetch to symbols that actually need one,
    instead of unconditionally re-fetching every tracked symbol forever.

    This is now a thin wrapper around daily_close's sinopac_sweep/
    yfinance_sweep -- the same two-stage source strategy daily_close.py's
    background job runs for every TW symbol, just scoped here to this
    button's own PAIR_STRATEGY_UPDATE_SYMBOLS list so a user can force an
    immediate refresh instead of waiting for the next background pass."""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    if now.weekday() >= 5:
        return {"updated": False, "checked": 0, "reason": "weekend"}
    close_buffered = (datetime.combine(now.date(), daily_close.CLOSE_TIME) + daily_close.CLOSE_BUFFER).time()
    if now.time() < close_buffered:
        return {"updated": False, "checked": 0, "reason": "market not closed yet (13:30 Taipei)"}

    today_str = now.strftime("%Y-%m-%d")
    missing = [s for s in PAIR_STRATEGY_UPDATE_SYMBOLS if db.last_final_price_date(s) != today_str]
    if not missing:
        return {"updated": False, "checked": len(PAIR_STRATEGY_UPDATE_SYMBOLS), "reason": "already up to date"}

    if now.time() < daily_close.YFINANCE_FALLBACK_TIME:
        advanced = daily_close.sinopac_sweep(missing, today_str)
        return {
            "updated": True, "attempted": len(missing), "succeeded": len(advanced),
            "symbols_updated": [{"symbol": s, "last_date": today_str} for s in advanced],
            "failed": [], "source": "sinopac_closing_snapshot",
        }

    advanced, failed = daily_close.yfinance_sweep(missing, today_str, now)
    return {
        "updated": True, "attempted": len(missing), "succeeded": len(advanced),
        "symbols_updated": [{"symbol": s, "last_date": db.last_price_date(s)} for s in advanced],
        "failed": failed,
    }


PAIR_SOURCES = [
    ("pair_strategy", "配對策略", pair_strategy.PAIR_PARAMS),
    ("pair_strategy_v2", "配對策略v2", pair_strategy_v2.PAIR_PARAMS),
    ("pair_strategy_lite", "配對策略(縮減版)", pair_strategy_lite.PAIR_PARAMS),
]


@app.get("/api/trade-logs/pair-options")
def trade_log_pair_options():
    """Merged pair choices across all 3 strategy modules, for the 'which
    pair is this journal tracking' dropdown when creating a new log."""
    out = []
    for source_key, source_label, params in PAIR_SOURCES:
        for key, p in params.items():
            out.append({
                "source": source_key, "source_label": source_label, "key": key,
                "label": p["label"], "symA": p["symA"], "symB": p["symB"],
                "nameA": p["nameA"], "nameB": p["nameB"],
            })
    return {"options": out}


def _trade_log_or_404(log_id: int):
    log = db.get_trade_log(log_id)
    if not log:
        raise HTTPException(404, f"unknown trade log {log_id}")
    return log


@app.get("/api/trade-logs")
def list_trade_logs():
    logs = db.list_trade_logs()
    return [{**log, "summary": trade_log.compute_summary(log)} for log in logs]


@app.post("/api/trade-logs")
def create_trade_log(body: TradeLogIn):
    log_id = db.create_trade_log(
        body.name, body.pair_source, body.pair_key, body.symbol_a, body.symbol_b,
        body.name_a, body.name_b, body.initial_capital, body.start_date, body.notes,
    )
    return _trade_log_or_404(log_id)


def _trade_log_detail(log):
    entries = db.list_trade_entries(log["id"])
    included = [e for e in entries if e["included"]]
    return {
        "log": log,
        "entries": entries,
        "summary": trade_log.compute_summary(log, entries),
        "summary_excluding_off": trade_log.compute_summary(log, included),
    }


@app.get("/api/trade-logs/{log_id}")
def get_trade_log(log_id: int):
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.put("/api/trade-logs/{log_id}/price")
def set_trade_log_price(log_id: int, body: TradeLogPriceIn):
    """Persist a manual mark-to-market price (e.g. an intraday quote the
    user typed in) instead of the latest stored close. Sticks until
    cleared -- unlike a per-request override, this survives navigating
    away and reloading."""
    _trade_log_or_404(log_id)
    db.set_trade_log_price(log_id, body.price_a, body.price_b)
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.delete("/api/trade-logs/{log_id}/price")
def clear_trade_log_price(log_id: int):
    _trade_log_or_404(log_id)
    db.clear_trade_log_price(log_id)
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.put("/api/trade-logs/{log_id}/start-price")
def set_trade_log_start_price(log_id: int, body: TradeLogStartPriceIn):
    """Persist a manual benchmark entry price instead of the auto
    first-close-on-or-after start_date."""
    _trade_log_or_404(log_id)
    db.set_trade_log_start_price(log_id, body.start_price_a, body.start_price_b)
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.delete("/api/trade-logs/{log_id}/start-price")
def clear_trade_log_start_price(log_id: int):
    _trade_log_or_404(log_id)
    db.clear_trade_log_start_price(log_id)
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.delete("/api/trade-logs/{log_id}")
def delete_trade_log(log_id: int):
    _trade_log_or_404(log_id)
    db.delete_trade_log(log_id)
    return {"deleted": True}


@app.patch("/api/trade-logs/{log_id}")
def update_trade_log(log_id: int, body: TradeLogPatch):
    _trade_log_or_404(log_id)
    db.update_trade_log(log_id, body.initial_capital, body.start_date)
    return _trade_log_detail(_trade_log_or_404(log_id))


@app.post("/api/trade-logs/{log_id}/entries")
def add_trade_entry(log_id: int, body: TradeEntryIn):
    log = _trade_log_or_404(log_id)
    if body.side not in ("buy", "sell"):
        raise HTTPException(400, "side must be 'buy' or 'sell'")
    if body.symbol not in (log["symbol_a"], log["symbol_b"]):
        raise HTTPException(400, f"symbol must be {log['symbol_a']} or {log['symbol_b']}")
    db.add_trade_entry(log_id, body.date, body.symbol, body.side, body.shares, body.price, body.fee, body.note)
    return _trade_log_detail(log)


@app.patch("/api/trade-logs/{log_id}/entries/{entry_id}")
def update_trade_entry(log_id: int, entry_id: int, body: TradeEntryPatch):
    log = _trade_log_or_404(log_id)
    db.set_trade_entry_included(log_id, entry_id, body.included)
    return _trade_log_detail(log)


@app.delete("/api/trade-logs/{log_id}/entries/{entry_id}")
def delete_trade_entry(log_id: int, entry_id: int):
    log = _trade_log_or_404(log_id)
    db.delete_trade_entry(log_id, entry_id)
    return _trade_log_detail(log)


@app.get("/api/backtest/strategies")
def backtest_strategies():
    return backtest.list_strategies()


@app.post("/api/backtest")
def run_backtest(body: BacktestIn):
    start = _range_start(body.range)
    try:
        return backtest.run_backtest(
            body.symbols, body.strategy, body.params,
            start, None, body.benchmark, body.initial_capital,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
