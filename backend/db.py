"""SQLite access layer for the stock app.

Plain sqlite3 (stdlib) — no ORM. The schema is tiny:
  symbols       one row per tracked ticker
  prices        daily OHLCV bars, one row per (symbol, date)
  home_indices  the (editable) list of indices shown on the home page
"""
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stock.db")


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL improves concurrent read while the update endpoint writes.
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                symbol   TEXT PRIMARY KEY,
                name     TEXT NOT NULL,
                market   TEXT NOT NULL,      -- TW | US
                type     TEXT NOT NULL,      -- index | stock | etf
                currency TEXT,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS prices (
                symbol    TEXT NOT NULL,
                date      TEXT NOT NULL,      -- YYYY-MM-DD
                open      REAL,
                high      REAL,
                low       REAL,
                close     REAL,
                adj_close REAL,
                volume    INTEGER,
                PRIMARY KEY (symbol, date)
            );
            CREATE INDEX IF NOT EXISTS idx_prices_symbol_date
                ON prices(symbol, date);

            CREATE TABLE IF NOT EXISTS home_indices (
                symbol   TEXT PRIMARY KEY,
                position INTEGER NOT NULL DEFAULT 0
            );

            -- Intraday bars (5m, 15m, ...). ts is epoch seconds with the
            -- exchange wall-clock interpreted as UTC, so charts show local
            -- market time. Yahoo only serves a rolling ~60-day window for 5m.
            CREATE TABLE IF NOT EXISTS intraday_prices (
                symbol   TEXT NOT NULL,
                interval TEXT NOT NULL,          -- e.g. 5m
                ts       INTEGER NOT NULL,        -- epoch seconds
                open     REAL,
                high     REAL,
                low      REAL,
                close    REAL,
                volume   INTEGER,
                PRIMARY KEY (symbol, interval, ts)
            );
            CREATE INDEX IF NOT EXISTS idx_intraday_symbol_interval_ts
                ON intraday_prices(symbol, interval, ts);

            -- Real (not backtested) trading journals: one row per portfolio
            -- ("組"), e.g. a pair-strategy live account. entries are the
            -- actual buy/sell fills; P&L is derived on the fly, not stored.
            CREATE TABLE IF NOT EXISTS trade_logs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                pair_source      TEXT,             -- pair_strategy | pair_strategy_v2 | pair_strategy_lite | NULL
                pair_key         TEXT,
                symbol_a         TEXT NOT NULL,
                symbol_b         TEXT NOT NULL,
                name_a           TEXT NOT NULL,
                name_b           TEXT NOT NULL,
                initial_capital  REAL NOT NULL,
                start_date       TEXT NOT NULL,    -- benchmark (buy&hold) start date
                notes            TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trade_log_entries (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id   INTEGER NOT NULL,
                date     TEXT NOT NULL,
                symbol   TEXT NOT NULL,
                side     TEXT NOT NULL,             -- buy | sell
                shares   REAL NOT NULL,
                price    REAL NOT NULL,
                fee      REAL NOT NULL DEFAULT 0,   -- actual fee+tax paid, entered manually
                note     TEXT,
                included INTEGER NOT NULL DEFAULT 1  -- 0 = excluded from the "what if I hadn't made this trade" replay
            );
            CREATE INDEX IF NOT EXISTS idx_trade_log_entries_log
                ON trade_log_entries(log_id, date);

            -- Unused since pair-strategy-lite's live-alert tracking was
            -- unified onto the global tracked_symbols watchlist below (a
            -- pair now counts as tracked when both its symbols are) --
            -- kept only so old DBs don't error, no code reads/writes it.
            CREATE TABLE IF NOT EXISTS pair_live_tracking (
                pair_key TEXT PRIMARY KEY,
                tracked  INTEGER NOT NULL DEFAULT 1
            );

            -- Global live-quote watchlist (symbol-level, not tied to any
            -- one feature). A background poller (see quote_tracker.py)
            -- keeps every tracked symbol's TODAY row in `prices` fresh
            -- off the Sinopac quote service during market hours, so every
            -- reader in the app (db.latest_quote/get_prices) sees the
            -- live price automatically without calling Sinopac itself.
            CREATE TABLE IF NOT EXISTS tracked_symbols (
                symbol      TEXT PRIMARY KEY,
                added_at    TEXT DEFAULT (datetime('now')),
                last_polled_at TEXT
            );

            -- Manual correction for pair-strategy-lite's displayed position
            -- state (level/side). The computed state is purely a function
            -- of price history, but the user's *real* holdings can drift
            -- from it -- a manual trade outside the app, a partial fill,
            -- etc. -- so this lets them tell the UI "actually I'm here"
            -- without needing to fake the price data. level is 0/1/2, side
            -- is -1/0/+1 matching diff's own sign convention (0 only valid
            -- when level=0). Absence of a row means "trust the computed
            -- value" -- this table only holds pairs currently overridden.
            CREATE TABLE IF NOT EXISTS lite_position_override (
                pair_key   TEXT PRIMARY KEY,
                level      INTEGER NOT NULL,
                side       INTEGER NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        # Migration: tag each symbol with its data source so updates can route
        # to the right fetcher (yahoo = yfinance, taifex = TAIFEX futures).
        cols = [r[1] for r in conn.execute("PRAGMA table_info(symbols)").fetchall()]
        if "source" not in cols:
            conn.execute(
                "ALTER TABLE symbols ADD COLUMN source TEXT NOT NULL DEFAULT 'yahoo'"
            )
        entry_cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_log_entries)").fetchall()]
        if entry_cols and "included" not in entry_cols:
            conn.execute(
                "ALTER TABLE trade_log_entries ADD COLUMN included INTEGER NOT NULL DEFAULT 1"
            )
        # Migration: persisted manual price overrides for the trade-log detail
        # page (current mark + benchmark entry price), NULL = auto-track.
        log_cols = [r[1] for r in conn.execute("PRAGMA table_info(trade_logs)").fetchall()]
        for col in ("custom_price_a", "custom_price_b", "custom_start_price_a", "custom_start_price_b"):
            if log_cols and col not in log_cols:
                conn.execute(f"ALTER TABLE trade_logs ADD COLUMN {col} REAL")
        # Migration: a `prices` row for *today* can come from two genuinely
        # different sources -- quote_tracker's poller (a live snapshot,
        # taken mid-session, subject to change) or a real fetch from
        # yfinance/TAIFEX (the settled close). Before this column existed
        # both were stored identically in `close`, so nothing downstream
        # could tell "today's row is final" from "today's row is still
        # moving" -- that's what caused a tracked pair's displayed close to
        # sit at the poller's last pre-close snapshot instead of the real
        # closing price, and separately made the next-day threshold basis
        # drift onto today's still-live price. All pre-existing rows are
        # real settled closes (the poller never backfills), so they default
        # to final.
        price_cols = [r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()]
        if "is_final" not in price_cols:
            conn.execute("ALTER TABLE prices ADD COLUMN is_final INTEGER NOT NULL DEFAULT 1")
        if "quote_time" not in price_cols:
            conn.execute("ALTER TABLE prices ADD COLUMN quote_time TEXT")


# --- symbols ---------------------------------------------------------------

def upsert_symbol(symbol, name, market, type_, currency=None, source="yahoo"):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO symbols (symbol, name, market, type, currency, source)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
                   name=excluded.name,
                   market=excluded.market,
                   type=excluded.type,
                   currency=COALESCE(excluded.currency, symbols.currency),
                   source=excluded.source""",
            (symbol, name, market, type_, currency, source),
        )


def get_symbol(symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM symbols WHERE symbol = ?", (symbol,)
        ).fetchone()
        return dict(row) if row else None


def list_symbols(market=None, type_=None, q=None):
    sql = "SELECT * FROM symbols WHERE 1=1"
    args = []
    if market:
        sql += " AND market = ?"
        args.append(market)
    if type_:
        sql += " AND type = ?"
        args.append(type_)
    if q:
        sql += " AND (symbol LIKE ? OR name LIKE ?)"
        like = f"%{q}%"
        args += [like, like]
    sql += " ORDER BY type, symbol"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


def list_tw_symbols():
    """Every TW-listed symbol this app knows about that's fetchable via
    Yahoo/Sinopac (plain stocks/ETFs/the index) -- excludes TAIFEX futures
    (source='taifex'), which have their own separate fetch path in
    taifex.py and aren't something Sinopac's equity snapshot API covers.
    Used by daily_close.py's background sweep, which needs "all TW
    symbols" rather than any one page's own curated subset."""
    with get_conn() as conn:
        return [r["symbol"] for r in conn.execute(
            "SELECT symbol FROM symbols WHERE market = 'TW' AND source = 'yahoo' ORDER BY symbol"
        ).fetchall()]


# --- prices ----------------------------------------------------------------

def upsert_prices(symbol, rows):
    """rows: iterable of dicts with keys date, open, high, low, close,
    adj_close, volume, and optionally is_final (default True) and
    quote_time (default None). is_final=False marks a row as a live
    snapshot rather than a settled close -- only quote_tracker's poller
    should ever pass that; every other writer (yfinance/TAIFEX fetches,
    the initial bulk loader) is writing real closes and gets the default.
    Returns number of rows written."""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO prices
                   (symbol, date, open, high, low, close, adj_close, volume, is_final, quote_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, date) DO UPDATE SET
                   open=excluded.open, high=excluded.high, low=excluded.low,
                   close=excluded.close, adj_close=excluded.adj_close,
                   volume=excluded.volume, is_final=excluded.is_final,
                   quote_time=excluded.quote_time""",
            [
                (
                    symbol,
                    r["date"],
                    r.get("open"),
                    r.get("high"),
                    r.get("low"),
                    r.get("close"),
                    r.get("adj_close"),
                    r.get("volume"),
                    int(r.get("is_final", True)),
                    r.get("quote_time"),
                )
                for r in rows
            ],
        )
    _price_cache.pop(symbol, None)
    return len(rows)


# get_prices() is hit hard by the pair-strategy pages: a single /signals or
# /live request recomputes several pairs, and each pair re-fetches its two
# symbols' full history multiple times (baseline, live-injected, prev-close,
# last-trading-date lookups all call it independently). Every call used to
# open its own sqlite3 connection -- fine in isolation (a few ms), but a
# single page load fires ~5-6 endpoints at once (React mounts them in
# parallel, doubled again under StrictMode in dev), so dozens of connections
# end up competing for the same WAL file at once and per-request latency
# balloons from ~1s to 5-10s. Caching each symbol's *full* unfiltered history
# for a few seconds and slicing start/end in Python collapses that back down
# to one real query per symbol per cache window, regardless of how many
# functions ask for it. A few seconds of staleness is a non-issue here: the
# only writer is upsert_prices (which invalidates immediately above), and
# the live-quote poller's own 15s cadence already tolerates that much lag.
_price_cache = {}
_PRICE_CACHE_TTL = 5


def get_prices(symbol, start=None, end=None):
    cached = _price_cache.get(symbol)
    now = time.monotonic()
    if cached is None or now - cached[0] > _PRICE_CACHE_TTL:
        with get_conn() as conn:
            rows = [
                dict(r) for r in conn.execute(
                    "SELECT date, open, high, low, close, adj_close, volume, is_final, quote_time "
                    "FROM prices WHERE symbol = ? ORDER BY date ASC",
                    (symbol,),
                ).fetchall()
            ]
        _price_cache[symbol] = (now, rows)
    else:
        rows = cached[1]
    if start:
        rows = [r for r in rows if r["date"] >= start]
    if end:
        rows = [r for r in rows if r["date"] <= end]
    return rows


def last_price_date(symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM prices WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row["d"] if row and row["d"] else None


def last_final_price_date(symbol):
    """Latest date with a *settled* close on file -- unlike last_price_date,
    ignores a trailing live/non-final row from quote_tracker's poller. This
    is the right check for "does this symbol still need a real fetch": a
    tracked symbol's today-row existing at all doesn't mean it's final."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(date) AS d FROM prices WHERE symbol = ? AND is_final = 1", (symbol,)
        ).fetchone()
        return row["d"] if row and row["d"] else None


def latest_quote(symbol, as_of=None):
    """Return the latest known price for `symbol`, split by settled vs
    live the way the `prices` row itself distinguishes them, or None.
    as_of, if given, bounds the lookup to dates <= as_of -- for browsing a
    specific historical date instead of the true latest.

    - close/live_price are mutually exclusive: exactly one is non-null,
      matching is_final. `price` coalesces the two for callers that just
      want "whatever the best known number is" without caring which.
    - prev_close is the last *settled* close before this row (skipping a
      live row rather than pairing "live vs live", which wouldn't have a
      real previous-close to diff against) -- change/change_pct are
      computed off of it.
    """
    with get_conn() as conn:
        sql = "SELECT date, close, is_final, quote_time FROM prices WHERE symbol = ?"
        args = [symbol]
        if as_of:
            sql += " AND date <= ?"
            args.append(as_of)
        sql += " ORDER BY date DESC LIMIT 1"
        last = conn.execute(sql, args).fetchone()
        if not last:
            return None
        prev_sql = "SELECT close FROM prices WHERE symbol = ? AND is_final = 1 AND date < ?"
        prev_args = [symbol, last["date"]]
        prev = conn.execute(prev_sql + " ORDER BY date DESC LIMIT 1", prev_args).fetchone()
    is_final = bool(last["is_final"])
    price = last["close"]
    prev_close = prev["close"] if prev else None
    change = (price - prev_close) if (price is not None and prev_close) else None
    change_pct = (change / prev_close * 100) if (change is not None and prev_close) else None
    return {
        "date": last["date"],
        "is_final": is_final,
        "quote_time": last["quote_time"],
        "close": price if is_final else None,
        "live_price": None if is_final else price,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
    }


def price_count(symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM prices WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row["c"]


# --- home indices ----------------------------------------------------------

def get_home_indices():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol FROM home_indices ORDER BY position ASC"
        ).fetchall()
        return [r["symbol"] for r in rows]


def set_home_indices(symbols):
    with get_conn() as conn:
        conn.execute("DELETE FROM home_indices")
        conn.executemany(
            "INSERT INTO home_indices (symbol, position) VALUES (?, ?)",
            [(s, i) for i, s in enumerate(symbols)],
        )


# --- intraday prices -------------------------------------------------------

def upsert_intraday(symbol, interval, rows):
    """rows: iterable of dicts with keys ts, open, high, low, close, volume."""
    rows = list(rows)
    if not rows:
        return 0
    with get_conn() as conn:
        conn.executemany(
            """INSERT INTO intraday_prices
                   (symbol, interval, ts, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, interval, ts) DO UPDATE SET
                   open=excluded.open, high=excluded.high, low=excluded.low,
                   close=excluded.close, volume=excluded.volume""",
            [
                (
                    symbol, interval, r["ts"],
                    r.get("open"), r.get("high"), r.get("low"),
                    r.get("close"), r.get("volume"),
                )
                for r in rows
            ],
        )
    return len(rows)


def get_intraday(symbol, interval, days=None):
    """Return intraday bars. If `days` is given, only the most recent `days`
    calendar days (relative to the latest stored bar) are returned."""
    with get_conn() as conn:
        if days:
            row = conn.execute(
                "SELECT MAX(ts) AS m FROM intraday_prices WHERE symbol=? AND interval=?",
                (symbol, interval),
            ).fetchone()
            if not row or row["m"] is None:
                return []
            cutoff = row["m"] - int(days) * 86400
            rows = conn.execute(
                """SELECT ts AS time, open, high, low, close, volume
                   FROM intraday_prices
                   WHERE symbol=? AND interval=? AND ts >= ?
                   ORDER BY ts ASC""",
                (symbol, interval, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT ts AS time, open, high, low, close, volume
                   FROM intraday_prices
                   WHERE symbol=? AND interval=?
                   ORDER BY ts ASC""",
                (symbol, interval),
            ).fetchall()
        return [dict(r) for r in rows]


def last_intraday_ts(symbol, interval):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(ts) AS m FROM intraday_prices WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None


def intraday_count(symbol, interval):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM intraday_prices WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
        return row["c"]


# --- trade logs (real trading journals) -------------------------------------

def create_trade_log(name, pair_source, pair_key, symbol_a, symbol_b, name_a, name_b,
                      initial_capital, start_date, notes=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO trade_logs
                   (name, pair_source, pair_key, symbol_a, symbol_b, name_a, name_b,
                    initial_capital, start_date, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, pair_source, pair_key, symbol_a, symbol_b, name_a, name_b,
             initial_capital, start_date, notes),
        )
        return cur.lastrowid


def list_trade_logs():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM trade_logs ORDER BY created_at DESC, id DESC"
        ).fetchall()]


def get_trade_log(log_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM trade_logs WHERE id = ?", (log_id,)).fetchone()
        return dict(row) if row else None


def delete_trade_log(log_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM trade_log_entries WHERE log_id = ?", (log_id,))
        conn.execute("DELETE FROM trade_logs WHERE id = ?", (log_id,))


def update_trade_log(log_id, initial_capital, start_date):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_logs SET initial_capital = ?, start_date = ? WHERE id = ?",
            (initial_capital, start_date, log_id),
        )


def set_trade_log_price(log_id, price_a, price_b):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_logs SET custom_price_a = ?, custom_price_b = ? WHERE id = ?",
            (price_a, price_b, log_id),
        )


def clear_trade_log_price(log_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_logs SET custom_price_a = NULL, custom_price_b = NULL WHERE id = ?",
            (log_id,),
        )


def set_trade_log_start_price(log_id, start_price_a, start_price_b):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_logs SET custom_start_price_a = ?, custom_start_price_b = ? WHERE id = ?",
            (start_price_a, start_price_b, log_id),
        )


def clear_trade_log_start_price(log_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_logs SET custom_start_price_a = NULL, custom_start_price_b = NULL WHERE id = ?",
            (log_id,),
        )


def add_trade_entry(log_id, date, symbol, side, shares, price, fee=0.0, note=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO trade_log_entries (log_id, date, symbol, side, shares, price, fee, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (log_id, date, symbol, side, shares, price, fee, note),
        )
        return cur.lastrowid


def list_trade_entries(log_id):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM trade_log_entries WHERE log_id = ? ORDER BY date ASC, id ASC",
            (log_id,),
        ).fetchall()]


def delete_trade_entry(log_id, entry_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM trade_log_entries WHERE id = ? AND log_id = ?", (entry_id, log_id)
        )


def set_trade_entry_included(log_id, entry_id, included):
    with get_conn() as conn:
        conn.execute(
            "UPDATE trade_log_entries SET included = ? WHERE id = ? AND log_id = ?",
            (1 if included else 0, entry_id, log_id),
        )


# --- global tracked-symbols watchlist ---------------------------------------

def list_tracked_symbols():
    with get_conn() as conn:
        return [r["symbol"] for r in conn.execute(
            "SELECT symbol FROM tracked_symbols ORDER BY added_at"
        ).fetchall()]


def is_tracked(symbol):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM tracked_symbols WHERE symbol = ?", (symbol,)
        ).fetchone()
        return row is not None


def add_tracked_symbol(symbol):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tracked_symbols (symbol) VALUES (?)", (symbol,)
        )


def remove_tracked_symbol(symbol):
    with get_conn() as conn:
        conn.execute("DELETE FROM tracked_symbols WHERE symbol = ?", (symbol,))


def mark_symbols_polled(symbols):
    if not symbols:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE tracked_symbols SET last_polled_at = datetime('now') WHERE symbol = ?",
            [(s,) for s in symbols],
        )


def list_lite_overrides():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT pair_key, level, side, updated_at FROM lite_position_override"
        ).fetchall()
        return {r["pair_key"]: dict(r) for r in rows}


def set_lite_override(pair_key, level, side, updated_at=None):
    """updated_at, if given, should be a Taipei-local ISO timestamp (see
    main.py's caller) -- SQLite's own datetime('now') is UTC, which would
    make a same-day check against Taipei-local "today" wrong for roughly
    the first 8 hours of the Taipei calendar day."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO lite_position_override (pair_key, level, side, updated_at)
               VALUES (?, ?, ?, COALESCE(?, datetime('now')))
               ON CONFLICT(pair_key) DO UPDATE SET
                   level=excluded.level, side=excluded.side, updated_at=excluded.updated_at""",
            (pair_key, level, side, updated_at),
        )


def clear_lite_override(pair_key):
    with get_conn() as conn:
        conn.execute("DELETE FROM lite_position_override WHERE pair_key = ?", (pair_key,))
