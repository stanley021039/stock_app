"""Background poller for the global tracked-symbols watchlist.

Runs as an asyncio task inside the FastAPI process (started from main.py's
startup hook). While the TSE is open, it periodically batches a live
snapshot for every tracked symbol and upserts each one's TODAY row into
`prices` -- so every reader in the app (db.latest_quote, db.get_prices)
sees a live, continuously-refreshed price for tracked symbols with no
per-feature Sinopac calls of its own. Untracked symbols are untouched and
simply keep showing whatever the last regular EOD /update wrote.

Every row this writes is marked is_final=False -- it's a live snapshot,
not a settled close, and callers that need to tell the two apart (the
daily update endpoints, the pair-strategy pages' next-day threshold basis)
rely on that flag rather than guessing from the clock or tracked-status.
The real close still has to come from a real EOD fetch afterward.
"""
import asyncio
import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import db
import sinopac_quote

POLL_INTERVAL_SECONDS = 15
POLL_INTERVAL_CLOSED_SECONDS = 300  # market closed: check back much less often

logger = logging.getLogger("quote_tracker")


def _tse_market_open(now):
    return now.weekday() < 5 and dtime(9, 0) <= now.time() <= dtime(13, 30)


def poll_once():
    """One pass: fetch+upsert every tracked symbol's live snapshot. Returns
    the list of symbols actually updated (for logging/testing)."""
    symbols = db.list_tracked_symbols()
    if not symbols:
        return []

    now = datetime.now(ZoneInfo("Asia/Taipei"))
    today_str = now.strftime("%Y-%m-%d")

    try:
        snaps = sinopac_quote.get_snapshots(symbols)
    except Exception:  # noqa: BLE001
        logger.exception("quote_tracker: snapshot fetch failed")
        return []

    updated = []
    for sym, snap in snaps.items():
        if not snap or snap.get("close") is None:
            continue
        db.upsert_prices(sym, [{
            "date": today_str,
            "open": snap.get("open"),
            "high": snap.get("high"),
            "low": snap.get("low"),
            "close": snap.get("close"),
            "adj_close": snap.get("close"),
            "volume": snap.get("volume"),
            "is_final": False,
            "quote_time": now.isoformat(timespec="seconds"),
        }])
        updated.append(sym)
    db.mark_symbols_polled(updated)
    return updated


async def run_forever():
    while True:
        try:
            now = datetime.now(ZoneInfo("Asia/Taipei"))
            if _tse_market_open(now):
                poll_once()
                delay = POLL_INTERVAL_SECONDS
            else:
                delay = POLL_INTERVAL_CLOSED_SECONDS
        except Exception:  # noqa: BLE001
            logger.exception("quote_tracker: poll loop error")
            delay = POLL_INTERVAL_CLOSED_SECONDS
        await asyncio.sleep(delay)
