"""Real (not backtested) trading-journal P&L.

A trade log is one live portfolio ("組"): an initial cash amount plus a
sequence of manually-entered actual buy/sell fills on a fixed pair of
symbols (symbol_a / symbol_b). Everything here is derived on the fly from
the entries + current prices -- no P&L numbers are stored.

Two comparisons are reported, per the pair-strategy convention already used
in backtest.py: vs the initial capital (simple total return), and vs a
50/50 buy&hold benchmark that puts the same initial capital into symbol_a /
symbol_b on start_date and never touches it again (fee-free, since it's a
hypothetical baseline, not an actual trade).
"""
import db


def _price_on_or_after(symbol, date):
    rows = db.get_prices(symbol, start=date)
    return rows[0]["close"] if rows else None


def compute_summary(log, entries=None):
    """entries defaults to the log's full ledger. Pass a filtered subset
    (e.g. only entries with included=1) to replay a "what if I hadn't made
    these trades" counterfactual instead.

    log.custom_price_a/b and log.custom_start_price_a/b (persisted columns,
    NULL by default) override the latest-close mark and the benchmark's
    entry price respectively -- set via the /price and /start-price
    endpoints, e.g. when the user typed in an intraday quote instead of
    waiting for the stored latest close.

    When price_a/b isn't custom, it's just the latest stored close --
    which is a *live*, continuously-refreshed price when that symbol is
    in the global tracked-symbols watchlist (see quote_tracker.py; a
    background poller keeps tracked symbols' TODAY row fresh off Sinopac
    directly in the DB), or the last EOD close otherwise. Either way this
    function only ever reads the DB, no Sinopac call of its own."""
    if entries is None:
        entries = db.list_trade_entries(log["id"])
    sym_a, sym_b = log["symbol_a"], log["symbol_b"]

    cash = log["initial_capital"]
    holdings = {sym_a: 0.0, sym_b: 0.0}
    total_fees = 0.0
    for e in entries:
        gross = e["shares"] * e["price"]
        if e["side"] == "buy":
            cash -= gross + e["fee"]
            holdings[e["symbol"]] += e["shares"]
        else:
            cash += gross - e["fee"]
            holdings[e["symbol"]] -= e["shares"]
        total_fees += e["fee"]

    price_a = log["custom_price_a"]
    price_b = log["custom_price_b"]
    price_is_custom = price_a is not None
    price_a_is_live = False
    price_b_is_live = False
    if price_a is None:
        quote_a = db.latest_quote(sym_a)
        price_a = quote_a["price"] if quote_a else None
        price_a_is_live = bool(quote_a) and not quote_a["is_final"]
    if price_b is None:
        quote_b = db.latest_quote(sym_b)
        price_b = quote_b["price"] if quote_b else None
        price_b_is_live = bool(quote_b) and not quote_b["is_final"]

    market_value = None
    if price_a is not None and price_b is not None:
        market_value = cash + holdings[sym_a] * price_a + holdings[sym_b] * price_b

    pnl_vs_initial = market_value - log["initial_capital"] if market_value is not None else None
    pnl_vs_initial_pct = (
        pnl_vs_initial / log["initial_capital"] * 100
        if pnl_vs_initial is not None and log["initial_capital"] else None
    )

    start_price_a = log["custom_start_price_a"]
    start_price_is_custom = start_price_a is not None
    if start_price_a is None:
        start_price_a = _price_on_or_after(sym_a, log["start_date"])
    start_price_b = log["custom_start_price_b"]
    if start_price_b is None:
        start_price_b = _price_on_or_after(sym_b, log["start_date"])
    benchmark_value = None
    if start_price_a and start_price_b and price_a is not None and price_b is not None:
        half = log["initial_capital"] / 2
        benchmark_value = (half / start_price_a) * price_a + (half / start_price_b) * price_b

    pnl_vs_benchmark = (
        market_value - benchmark_value
        if market_value is not None and benchmark_value is not None else None
    )
    pnl_vs_benchmark_pct = (
        pnl_vs_benchmark / benchmark_value * 100
        if pnl_vs_benchmark is not None and benchmark_value else None
    )
    benchmark_return_pct = (
        (benchmark_value / log["initial_capital"] - 1) * 100
        if benchmark_value is not None and log["initial_capital"] else None
    )

    return {
        "cash": cash,
        "holdings": holdings,
        "price_a": price_a,
        "price_b": price_b,
        "price_is_custom": price_is_custom,
        "price_a_is_live": price_a_is_live,
        "price_b_is_live": price_b_is_live,
        "start_price_a": start_price_a,
        "start_price_b": start_price_b,
        "start_price_is_custom": start_price_is_custom,
        "market_value": market_value,
        "benchmark_value": benchmark_value,
        "total_fees": total_fees,
        "n_trades": len(entries),
        "pnl_vs_initial": pnl_vs_initial,
        "pnl_vs_initial_pct": pnl_vs_initial_pct,
        "pnl_vs_benchmark": pnl_vs_benchmark,
        "pnl_vs_benchmark_pct": pnl_vs_benchmark_pct,
        "benchmark_return_pct": benchmark_return_pct,
    }
