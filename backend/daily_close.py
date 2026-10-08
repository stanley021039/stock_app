"""Daily close-price sweep for every TW-listed symbol in the DB, run
automatically in the background regardless of whether anyone has the app
open.

Before this existed, a symbol's official close only ever got written when
a user happened to click a page's own "更新" button that day (e.g.
/api/pair-strategy/update, scoped to just the symbols that page cares
about). Skip a day -- app never opened -- and the next visit's %change
silently compares against whatever the last *settled* close still on file
was, which can be several days stale. Caught directly: a Friday the app
was never opened left every pair-strategy symbol's prev_close still
pinned to Thursday's close the following Monday, because quote_tracker's
live snapshot for Friday was written (is_final=False) but nothing ever
promoted it to a real close.

Two-stage source strategy, shared with /api/pair-strategy/update (which
calls the same sinopac_sweep/yfinance_sweep below, just scoped to its own
symbol list instead of every TW symbol): Sinopac's own closing snapshot in
the 13:30(+buffer)-14:00 window (fast, but a handful of names -- an
illiquid stock whose service-side snapshot hasn't refreshed, the service
being briefly unreachable -- can slip through), yfinance as the 14:00+
fallback for whatever's still missing.
"""
import asyncio
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import db
import fetch
import sinopac_quote

logger = logging.getLogger("daily_close")

CLOSE_TIME = dtime(13, 30)
# Give Sinopac's own feed a moment to settle right at the closing bell
# before trusting its snapshot as final -- see sinopac_sweep's docstring.
CLOSE_BUFFER = timedelta(seconds=60)
YFINANCE_FALLBACK_TIME = dtime(14, 0)
CHECK_INTERVAL_SECONDS = 300  # only needs to notice the 13:30/14:00 transitions, not track live prices
MIN_LOOKBACK_DAYS = 120  # matches the old pair_strategy_update's own floor -- insurance against gaps


def sinopac_sweep(symbols, today_str):
    """Fetch+write today's close for whichever of `symbols` are still
    missing it, from Sinopac's snapshot. Returns the list actually
    written.

    Trust is based on *when this is called*, not on the snapshot's own
    last-trade timestamp: an earlier version also required the snapshot's
    own `datetime` to be >= 13:30, which rejected perfectly valid closes
    for any stock that simply stopped trading earlier in the day (that's
    a legitimate final price once the market itself is shut, not a sign
    of stale data). The only thing actually worth guarding against here
    is the quote *service* itself returning something stale/cached from a
    previous day, which the date check below still catches. Callers are
    expected to only call this once it's actually safe to trust a
    snapshot as final (see run_once's CLOSE_BUFFER gate)."""
    missing = [s for s in symbols if db.last_final_price_date(s) != today_str]
    if not missing:
        return []
    try:
        snaps = sinopac_quote.get_snapshots(missing)
    except Exception:  # noqa: BLE001
        logger.exception("daily_close: sinopac snapshot fetch failed")
        return []
    advanced = []
    for symbol in missing:
        snap = snaps.get(symbol)
        if not snap or snap.get("close") is None:
            continue
        snap_date = (snap.get("datetime") or "")[:10]
        if snap_date and snap_date != today_str:
            continue  # stale/cached snapshot from a previous day -- not today's close
        db.upsert_prices(symbol, [{
            "date": today_str,
            "open": snap.get("open"), "high": snap.get("high"), "low": snap.get("low"),
            "close": snap["close"], "adj_close": snap["close"], "volume": snap.get("total_volume"),
            "is_final": True, "quote_time": snap.get("datetime"),
        }])
        advanced.append(symbol)
    return advanced


def yfinance_sweep(symbols, today_str, now=None):
    """Fetch+write today's close for whichever of `symbols` are still
    missing it, via yfinance -- the 14:00+ fallback for anything Sinopac's
    snapshot didn't resolve. Returns (advanced, failed)."""
    now = now or datetime.now(ZoneInfo("Asia/Taipei"))
    missing = [s for s in symbols if db.last_final_price_date(s) != today_str]
    if not missing:
        return [], []
    lookback_floor = (now - timedelta(days=MIN_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    advanced, failed = [], []
    for symbol in missing:
        before = db.last_price_date(symbol)
        try:
            rows = fetch.fetch_history(symbol, start=min(before, lookback_floor)) if before \
                else fetch.fetch_history(symbol, period="max")
            written = db.upsert_prices(symbol, rows)
            if written > 0:
                advanced.append(symbol)
        except Exception as e:  # noqa: BLE001
            failed.append({"symbol": symbol, "error": str(e)})
    return advanced, failed


def run_once(now=None):
    """One check, meant to be called every few minutes -- a no-op outside
    a trading weekday, outside the 13:30(+buffer)-14:00/14:00+ windows, or
    once every TW symbol is already settled for today, so it's safe to
    call as often as you like."""
    now = now or datetime.now(ZoneInfo("Asia/Taipei"))
    if now.weekday() >= 5:
        return
    close_buffered = (datetime.combine(now.date(), CLOSE_TIME) + CLOSE_BUFFER).time()
    if now.time() < close_buffered:
        return

    today_str = now.strftime("%Y-%m-%d")
    symbols = db.list_tw_symbols()

    if now.time() < YFINANCE_FALLBACK_TIME:
        advanced = sinopac_sweep(symbols, today_str)
        if advanced:
            logger.info("daily_close: sinopac closed %d/%d TW symbols", len(advanced), len(symbols))
        return

    advanced, failed = yfinance_sweep(symbols, today_str, now)
    if advanced or failed:
        logger.info(
            "daily_close: yfinance closed %d TW symbols (%d failed)", len(advanced), len(failed)
        )


async def run_forever():
    while True:
        try:
            run_once()
        except Exception:  # noqa: BLE001
            logger.exception("daily_close: sweep failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
