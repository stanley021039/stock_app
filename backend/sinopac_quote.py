"""Thin client for the local Sinopac/Shioaji quote service.

That service is a *separate* process (`shioaji.exe server`, run as its own
Windows service -- see start_quote_service.bat) wrapping the real Shioaji
SDK connection. The main backend never talks to Sinopac directly; it just
calls this local HTTP API, so there's only ever one persistent
login/session regardless of how many backend workers or browser tabs are
polling.

Snapshots are cached for CACHE_TTL_SECONDS so that several callers within
the same short window (multiple open tabs, quote_tracker's poller and an
on-demand read landing close together, etc.) collapse into one upstream
call -- keeps us far under Sinopac's rate limit (50 combined market-data
queries per 10s) no matter how often anything polls.
"""
import time
import requests

QUOTE_SERVICE_URL = "http://127.0.0.1:8090"
CACHE_TTL_SECONDS = 10
REQUEST_TIMEOUT = 5

_cache = {}  # yahoo_symbol -> (fetched_at_monotonic, snapshot dict or None)



# Indices aren't tradable securities -- Shioaji quotes them as their own
# security_type ("IND") under a market-assigned code, not a stock ticker.
# ^TWII (加權指數) is TSE's "001".
_INDEX_CONTRACTS = {
    "^TWII": ("001", "TSE", "IND"),
}


def _to_contract(yahoo_symbol):
    """'2408.TW' -> ('2408', 'TSE', 'STK'); '5483.TWO' -> ('5483', 'OTC', 'STK');
    '^TWII' -> ('001', 'TSE', 'IND'). Only plain TW/TWO-suffixed equities and
    the indices in _INDEX_CONTRACTS are supported -- this quote source
    doesn't cover US symbols or TAIFEX futures codes."""
    if yahoo_symbol in _INDEX_CONTRACTS:
        return _INDEX_CONTRACTS[yahoo_symbol]
    if yahoo_symbol.endswith(".TWO"):
        return yahoo_symbol[:-4], "OTC", "STK"
    if yahoo_symbol.endswith(".TW"):
        return yahoo_symbol[:-3], "TSE", "STK"
    raise ValueError(f"unsupported symbol for Sinopac quotes: {yahoo_symbol}")


def service_available():
    try:
        r = requests.get(f"{QUOTE_SERVICE_URL}/api/v1/health", timeout=2)
        return r.ok
    except Exception:  # noqa: BLE001
        return False


def get_snapshots(yahoo_symbols):
    """Return {yahoo_symbol: snapshot_dict_or_None}, where snapshot_dict has
    open/high/low/close/volume -- enough to upsert a proper daily bar, not
    just a price. Batches every symbol not already cached into a single
    POST to the quote service."""
    now = time.monotonic()
    out = {}
    missing = []
    for sym in yahoo_symbols:
        hit = _cache.get(sym)
        if hit is not None and now - hit[0] < CACHE_TTL_SECONDS:
            out[sym] = hit[1]
        else:
            missing.append(sym)

    if not missing:
        return out

    contracts = []
    convertible = []
    for sym in missing:
        try:
            code, exchange, security_type = _to_contract(sym)
        except ValueError:
            # not a plain TW/TWO equity or known index (US symbol, TAIFEX
            # code, etc.) -- no live source for it, just report unavailable
            # rather than failing the whole batch.
            out[sym] = None
            continue
        contracts.append({"security_type": security_type, "exchange": exchange, "code": code})
        convertible.append((sym, code))

    if not contracts:
        return out

    snaps = []
    try:
        resp = requests.post(
            f"{QUOTE_SERVICE_URL}/api/v1/data/snapshots",
            json={"contracts": contracts},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        snaps = resp.json()
    except Exception:  # noqa: BLE001
        snaps = []

    by_code = {s["code"]: s for s in snaps}
    for sym, code in convertible:
        snap = by_code.get(code)
        _cache[sym] = (now, snap)
        out[sym] = snap
    return out


def get_prices(yahoo_symbols):
    """Return {yahoo_symbol: last_price_or_None} -- convenience wrapper
    over get_snapshots for callers that only need the last-traded price."""
    snaps = get_snapshots(yahoo_symbols)
    return {sym: (snap.get("close") if snap else None) for sym, snap in snaps.items()}


def get_positions(unit="Share"):
    """The stock account's current inventory (read-only), one dict per
    holding: code, quantity, price (average cost), last_price, pnl, ...
    `unit` "Share" counts in shares -- "Common" counts in whole lots, which
    reads as 0 for odd-lot holdings. Needs the API key's 帳務 permission and
    a production-mode service; raises RuntimeError with the service's own
    message otherwise.

    Careful when probing this with a key that lacks the permission: the
    service answers 401 and then drops its whole Solace session on purpose
    (quotes fail until it's restarted), so don't call it speculatively."""
    try:
        resp = requests.post(
            f"{QUOTE_SERVICE_URL}/api/v1/portfolio/position_unit",
            json={"account_type": "S", "unit": unit},
            timeout=REQUEST_TIMEOUT * 3,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"報價服務連不上：{e}") from e
    if not resp.ok:
        try:
            msg = resp.json().get("message") or resp.text
        except ValueError:
            msg = resp.text
        raise RuntimeError(f"{resp.status_code}: {msg}")
    return resp.json()
