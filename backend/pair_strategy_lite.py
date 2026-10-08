"""Pair-rebalancing strategy, "lite": a capital-reduced variant of
`pair_strategy.py` (v1) -- same dev/baseline formula (MA-deviation against
a rolling trailing average), but a different capital-movement rule.

v1/v2 use a tiered *ratchet*: each level fires once, moving a fixed
`sell_fraction` of the strong side over; only a sign flip through zero
resets the whole episode back to 50/50 and clears the fired flags. A
position never partially exits.

Lite uses a 3-position state machine instead -- (pos, side), where pos is
0/1/2 (the number below is the WEAK side's -- the one being bought into --
weight) and side is which symbol is currently strong (0 only when pos=0):

    pos 0: 50/50
    pos 1: 75/25 (weak/strong)
    pos 2: 100/0

Unlike a fully reversible band (tested and abandoned -- see
LITE_MECHANISM_SPEC.md section 6, its cost-inclusive backtest lost on all
six pairs), the transition rule is deliberately asymmetric:

  - T2 is entry-only. Breaking back below T2 while at pos 2 does nothing --
    pos stays 2. This kills the edge-of-threshold churn a fully reversible
    band suffers from.
  - A pullback only ever happens once: pos 2 breaking below T1 drops to
    pos 1, and pos 1 is then sticky (breaking below T1 again does nothing).
    Only a sign flip through zero forces pos back to 0 (50/50) -- and if
    the new |diff| already clears a threshold, the same day immediately
    re-enters at the appropriate level (one trade, not two).

See LITE_MECHANISM_SPEC.md for the full transition table, the reference
implementation this loop is transcribed from, and the trading-cost model
used to compare this against the reversible-band and pure-ratchet designs
(this one won on cost-inclusive turnover without giving up the "can
partially de-risk" property the ratchet lacks). `entries_since_reset`/
`tier_index` are the *current* pos (0/1/2), not a cumulative fired count --
same as the abandoned band version, just a different transition rule for
getting there.

Headline metrics are `bh_ratio` (terminal value ÷ buy&hold's, which unlike
pp is not inflated by compounding) and `ir` (the excess return over
buy&hold, risk-adjusted -- it strips out the stock beta both the strategy
and the benchmark carry equally, which plain Sharpe conflates in). All
backtest numbers below include trading costs (LEAK ~0.357% per dollar
moved -- see the spec) -- `turnover` (cumulative moved amount ÷ starting
capital) is the real driver of cost drag, more so than `n_trades`.
"""
import db

PAIR_PARAMS = {
    "dram": {
        "label": "記憶體雙雄", "symA": "2408.TW", "symB": "2344.TW",
        "nameA": "南亞科", "nameB": "華邦電", "ma": 60,
        "tiers": [0.04, 0.07], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 790.7, "bh_ratio": 2.07, "ir": 1.14,
        "end_win_rate": 95.0, "one_year_win_rate": 96.7,
        "sharpe": 1.35, "max_dd": -63.1,
        "n_trades": 142, "turnover": 147.8,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
    "tw_ossat": {
        "label": "封測雙雄", "symA": "3711.TW", "symB": "6239.TW",
        "nameA": "日月光投控", "nameB": "力成", "ma": 60,
        "tiers": [0.1, 0.175], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 161.4, "bh_ratio": 1.35, "ir": 0.51,
        "end_win_rate": 97.6, "one_year_win_rate": 91.3,
        "sharpe": 1.23, "max_dd": -46.7,
        "n_trades": 51, "turnover": 43.9,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
    "tw_passive": {
        "label": "被動元件雙雄", "symA": "2327.TW", "symB": "2492.TW",
        "nameA": "國巨", "nameB": "華新科", "ma": 60,
        "tiers": [0.04, 0.07], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 131.4, "bh_ratio": 1.39, "ir": 0.55,
        "end_win_rate": 98.7, "one_year_win_rate": 76.9,
        "sharpe": 0.92, "max_dd": -64.0,
        "n_trades": 138, "turnover": 73.7,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
    "tw_power": {
        "label": "功率元件雙雄", "symA": "2481.TW", "symB": "8261.TW",
        "nameA": "強茂", "nameB": "富鼎", "ma": 60,
        "tiers": [0.1, 0.175], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 83.8, "bh_ratio": 1.45, "ir": 0.59,
        "end_win_rate": 95.0, "one_year_win_rate": 78.1,
        "sharpe": 0.70, "max_dd": -55.3,
        "n_trades": 62, "turnover": 25.3,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
    # Both MA90 pairs keep v1's MA (the lite tab is the same strategy on less
    # capital, so the timescale must match); only T was re-searched here.
    "aiserver": {
        "label": "AI伺服器雙雄", "symA": "3231.TW", "symB": "6669.TW",
        "nameA": "緯創", "nameB": "緯穎", "ma": 90,
        "tiers": [0.06, 0.105], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 469.1, "bh_ratio": 1.60, "ir": 0.55,
        "end_win_rate": 97.4, "one_year_win_rate": 61.6,
        "sharpe": 1.42, "max_dd": -35.9,
        "n_trades": 117, "turnover": 139.4,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
    "shipping": {
        "label": "航運雙雄", "symA": "2603.TW", "symB": "2609.TW",
        "nameA": "長榮", "nameB": "陽明", "ma": 90,
        "tiers": [0.04, 0.07], "band_weights": [0.50, 0.75, 1.00],
        "excess_pp": 69.2, "bh_ratio": 1.80, "ir": 0.79,
        "end_win_rate": 97.2, "one_year_win_rate": 82.0,
        "sharpe": 0.43, "max_dd": -54.6,
        "n_trades": 70, "turnover": 26.3,
        "backtest_start": "2021-10-12", "backtest_end": "2026-09-03",
        "costs_included": True,
    },
}

ALL_SYMBOLS = sorted({s for p in PAIR_PARAMS.values() for s in (p["symA"], p["symB"])})

# Reference indices shown alongside the pairs -- not part of any pair, just
# a "how's the market doing overall" quote next to the toolbar. Live via the
# same tracked-symbols/Sinopac path as everything else on this page (see
# sinopac_quote._INDEX_CONTRACTS for ^TWII's index contract mapping), and
# kept fresh by the same /api/pair-strategy/update button as the pairs.
INDEX_SYMBOLS = {
    "twii": {"symbol": "^TWII", "label": "台股加權指數"},
    "yuanta50": {"symbol": "0050.TW", "label": "元大台灣50"},
}


def ma_dev(closes, window):
    n = len(closes)
    out = [None] * n
    for i in range(window - 1, n):
        window_slice = closes[i - window + 1:i + 1]
        ma = sum(window_slice) / window
        out[i] = closes[i] / ma - 1.0
    return out


def _merged_history(symA, symB, through_date=None, extra=None):
    """extra, if given, is (date_str, price_a, price_b) -- a synthetic
    "today" row spliced onto the end (only if that date isn't already the
    last stored one), used by live_check() to try today's live price
    against the same tier/reset math without writing anything to the DB."""
    rowsA = db.get_prices(symA, end=through_date)
    rowsB = db.get_prices(symB, end=through_date)
    mapB = {r["date"]: r["close"] for r in rowsB if r["close"] is not None}
    dates, closeA, closeB = [], [], []
    for r in rowsA:
        if r["close"] is None or r["date"] not in mapB:
            continue
        dates.append(r["date"])
        closeA.append(r["close"])
        closeB.append(mapB[r["date"]])
    if extra is not None:
        date_str, price_a, price_b = extra
        if price_a is not None and price_b is not None and (not dates or dates[-1] != date_str):
            dates.append(date_str)
            closeA.append(price_a)
            closeB.append(price_b)
    return dates, closeA, closeB


def _dev_at_price(sumN_1, price, N):
    return N * price / (sumN_1 + price) - 1


def _price_for_dev(sumN_1, d, N):
    return (d + 1) * sumN_1 / (N - 1 - d)


def _transition(pos, side, d, T1, T2):
    """One state-machine step of the asymmetric band mechanism: given the
    current (pos, side) and a new diff value d, return the (pos, side) it
    transitions to. See LITE_MECHANISM_SPEC.md section 1 for the full
    transition table -- T2 is entry-only, a pullback (2->1) only ever
    happens via T1, and a sign flip resets to 0 with same-day re-entry if
    the new |diff| already clears a threshold.

    Shared by compute_pair_signal's own history walk and apply_override
    (which runs this same single step against the user's manually-tracked
    position instead of the position compute_pair_signal itself arrived
    at from price history alone)."""
    ad = abs(d)
    sgn = 1 if d > 0 else -1
    new_pos, new_side = pos, side
    if pos != 0 and side != 0 and sgn != side:
        new_pos, new_side = 0, 0
        if ad > T2:
            new_pos, new_side = 2, sgn
        elif ad > T1:
            new_pos, new_side = 1, sgn
    elif pos == 0:
        if ad > T2:
            new_pos, new_side = 2, sgn
        elif ad > T1:
            new_pos, new_side = 1, sgn
    elif pos == 1:
        if ad > T2:
            new_pos = 2
    elif pos == 2:
        if ad <= T1:
            new_pos = 1
    return new_pos, new_side


def compute_pair_signal(pair_key, through_date=None, extra=None):
    cfg = PAIR_PARAMS[pair_key]
    N, tiers = cfg["ma"], cfg["tiers"]
    T1, T2 = tiers[0], tiers[1]
    dates, closeA, closeB = _merged_history(cfg["symA"], cfg["symB"], through_date, extra)
    n = len(dates)
    if n < N:
        return {"key": pair_key, **cfg, "error": "not enough price history"}

    devA = ma_dev(closeA, N)
    devB = ma_dev(closeB, N)
    diff = [None if (a is None or b is None) else a - b for a, b in zip(devA, devB)]
    i0 = N - 1

    # Transition table (see LITE_MECHANISM_SPEC.md section 1 -- transcribed
    # from its verified reference implementation, factored out as
    # _transition() so the override-aware live check below can run the
    # exact same rule): T2 is entry-only (pos 2 breaking back below T2
    # does nothing, stays at 2); a pullback only ever happens once (pos 2
    # breaking below T1 drops to pos 1, which is then sticky); only a
    # sign flip forces pos back to 0, and if the new |diff| already
    # clears a threshold that same day, it re-enters immediately at the
    # appropriate level (one trade, not "reset then re-enter" as two
    # separate events).
    pos, side = 0, 0
    entered_today = False
    reset_today = False
    t_last = n - 1
    for t in range(i0 + 1, n):
        d = diff[t]
        entered_today = False
        reset_today = False
        new_pos, new_side = _transition(pos, side, d, T1, T2)
        if (new_pos, new_side) != (pos, side):
            pos, side = new_pos, new_side
            if t == t_last:
                if pos == 0:
                    reset_today = True
                else:
                    entered_today = True

    is_open = pos > 0
    entries_since_reset = pos
    cur_diff = diff[t_last]
    basis_date = dates[t_last]

    sumN_1_a = sum(closeA[t_last - (N - 2):t_last + 1])
    sumN_1_b = sum(closeB[t_last - (N - 2):t_last + 1])
    lastA, lastB = closeA[t_last], closeB[t_last]

    devB_flat = _dev_at_price(sumN_1_b, lastB, N)
    devA_flat = _dev_at_price(sumN_1_a, lastA, N)
    flat_diff = devA_flat - devB_flat

    def entry_high_for(trig):
        pa_sell_a = _price_for_dev(sumN_1_a, devB_flat + trig, N)
        pct_a_sell_a = pa_sell_a / lastA - 1
        pb_down = _price_for_dev(sumN_1_b, devA_flat - trig, N)
        pct_b_down = pb_down / lastB - 1
        return (pct_a_sell_a + (-pct_b_down)) / 2

    def entry_low_for(trig):
        pa_sell_b = _price_for_dev(sumN_1_a, devB_flat - trig, N)
        pct_a_sell_b = pa_sell_b / lastA - 1
        pb_up = _price_for_dev(sumN_1_b, devA_flat + trig, N)
        pct_b_up = pb_up / lastB - 1
        return (pct_a_sell_b + (-pct_b_up)) / 2

    fired_count = pos
    maxed_out = fired_count >= len(tiers)
    tier_marks = [
        {"tier": tv, "entry_high": entry_high_for(tv), "entry_low": entry_low_for(tv), "fired": i < fired_count}
        for i, tv in enumerate(tiers)
    ]

    continue_trigger = tiers[-1] if maxed_out else tiers[fired_count]
    reverse_trigger = tiers[0]
    if cur_diff is not None and cur_diff > 0:
        trig_high, trig_low = continue_trigger, reverse_trigger
        high_maxed, low_maxed = maxed_out, False
    elif cur_diff is not None and cur_diff < 0:
        trig_high, trig_low = reverse_trigger, continue_trigger
        high_maxed, low_maxed = False, maxed_out
    else:
        trig_high = trig_low = continue_trigger
        high_maxed = low_maxed = maxed_out

    entry_high = entry_high_for(trig_high)
    entry_low = entry_low_for(trig_low)

    # Computed regardless of is_open -- the frontend shows this as a
    # "where's the middle" reference even when flat, not just as the
    # actual reset target for an open position.
    pa_zero = _price_for_dev(sumN_1_a, devB_flat, N)
    pct_a_zero = pa_zero / lastA - 1
    pb_zero = _price_for_dev(sumN_1_b, devA_flat, N)
    pct_b_zero = pb_zero / lastB - 1
    reset_ab = (pct_a_zero + (-pct_b_zero)) / 2

    return {
        "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
        "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": N, "engine": "band",
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "turnover": cfg["turnover"], "costs_included": cfg["costs_included"],
        "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
        "bh_ratio": cfg["bh_ratio"], "ir": cfg["ir"],
        "basis_date": basis_date, "diff": cur_diff, "flat_diff": flat_diff, "is_open": is_open,
        "entry_high": entry_high, "entry_low": entry_low, "reset_ab": reset_ab,
        "high_maxed": high_maxed, "low_maxed": low_maxed,
        "entered_today": entered_today, "reset_today": reset_today,
        "entries_since_reset": entries_since_reset,
        "tiers": tiers, "band_weights": cfg["band_weights"],
        "tier_index": fired_count, "tier_count": len(tiers), "maxed_out": maxed_out,
        "tier_marks": tier_marks,
    }


def _prev_trading_date(pair_key, target_date):
    cfg = PAIR_PARAMS[pair_key]
    dates, _, _ = _merged_history(cfg["symA"], cfg["symB"], target_date)
    return dates[-2] if len(dates) >= 2 else None


def signal_for_target(pair_key, target_date=None):
    cfg = PAIR_PARAMS[pair_key]
    static_keys = ("engine", "tiers", "band_weights")
    state_keys = ("tier_index", "tier_count", "maxed_out", "tier_marks", "high_maxed", "low_maxed")
    meta_keys = ("n_trades", "turnover", "costs_included", "backtest_start", "backtest_end", "bh_ratio", "ir")

    if target_date is None:
        # A tracked symbol's latest row can be a live, not-yet-final
        # snapshot from quote_tracker's poller. Treating that as a real
        # close here would drag the static/blue basis onto today's live
        # price too, converging it with live_check's own yellow marker
        # instead of staying anchored to the last settled close -- which
        # is what the tier thresholds (and the user's own mental model of
        # this bar) assume. Checking is_final directly (rather than
        # guessing from tracked-status + market hours) means this is
        # correct regardless of clock/timezone issues or a symbol being
        # tracked without actually having live data yet.
        through_date = None
        latest_dates, _, _ = _merged_history(cfg["symA"], cfg["symB"], None)
        if latest_dates:
            latest = latest_dates[-1]
            if db.last_final_price_date(cfg["symA"]) != latest or db.last_final_price_date(cfg["symB"]) != latest:
                through_date = latest_dates[-2] if len(latest_dates) >= 2 else None
        proj = compute_pair_signal(pair_key, through_date)
        if "error" in proj:
            return proj
        return {
            "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
            "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": proj["ma"],
            **{k: proj[k] for k in static_keys + state_keys + meta_keys if k in proj},
            "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
            "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
            "target_date": None, "outcome_known": False,
            "basis_date": proj["basis_date"], "is_open_before": proj["is_open"], "basis_diff": proj["diff"],
            "entry_high": proj["entry_high"], "entry_low": proj["entry_low"], "reset_ab": proj["reset_ab"],
            "entries_since_reset": proj["entries_since_reset"],
            "actual_diff": None, "is_open_after": None, "entered_today": None, "reset_today": None,
        }

    basis_date = _prev_trading_date(pair_key, target_date)
    threshold = compute_pair_signal(pair_key, basis_date) if basis_date else None
    actual = compute_pair_signal(pair_key, target_date)
    if "error" in actual:
        return actual
    if actual["basis_date"] != target_date:
        return {"key": pair_key, "label": cfg["label"], "error": f"{target_date} 無資料（非交易日或超出可計算範圍）"}

    if threshold is not None and "error" not in threshold:
        basis_date_out = threshold["basis_date"]
        is_open_before = threshold["is_open"]
        basis_diff = threshold["diff"]
        entry_high, entry_low, reset_ab = threshold["entry_high"], threshold["entry_low"], threshold["reset_ab"]
        entries_before = threshold["entries_since_reset"]
        state_fields = {k: threshold[k] for k in state_keys if k in threshold}
    else:
        basis_date_out, is_open_before, basis_diff = None, False, None
        entry_high = entry_low = reset_ab = None
        entries_before = 0
        state_fields = {}

    return {
        "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
        "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": actual["ma"],
        **{k: actual[k] for k in static_keys + meta_keys if k in actual},
        **state_fields,
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "target_date": target_date, "outcome_known": True,
        "basis_date": basis_date_out, "is_open_before": is_open_before, "basis_diff": basis_diff,
        "entry_high": entry_high, "entry_low": entry_low, "reset_ab": reset_ab,
        "entries_since_reset": entries_before,
        "entries_since_reset_after": actual["entries_since_reset"],
        "actual_diff": actual["diff"], "is_open_after": actual["is_open"],
        "entered_today": actual["entered_today"], "reset_today": actual["reset_today"],
    }


def list_available_dates(limit=120):
    sets = None
    for sym in ALL_SYMBOLS:
        d = {r["date"] for r in db.get_prices(sym)}
        sets = d if sets is None else (sets & d)
    return sorted(sets, reverse=True)[:limit] if sets else []


def all_signals(target_date=None):
    return [signal_for_target(k, target_date) for k in PAIR_PARAMS]


def _last_trading_date_before(pair_key, date_str):
    """Most recent trading date strictly before date_str, for this pair's
    merged history -- correct whether or not date_str itself has data yet
    (unlike _prev_trading_date, which assumes it already does)."""
    cfg = PAIR_PARAMS[pair_key]
    dates, _, _ = _merged_history(cfg["symA"], cfg["symB"], date_str)
    if not dates:
        return None
    if dates[-1] == date_str:
        return dates[-2] if len(dates) >= 2 else None
    return dates[-1]


def _prev_close_pair(pair_key, through_date):
    """The close as of through_date -- e.g. yesterday's actual close, the
    correct denominator for a live %-change."""
    cfg = PAIR_PARAMS[pair_key]
    dates, closeA, closeB = _merged_history(cfg["symA"], cfg["symB"], through_date)
    if not dates:
        return None, None
    return closeA[-1], closeB[-1]


def live_check(pair_key, live_price_a, live_price_b, today_str):
    """Whether *today* would already fire a new entry tier or a reset --
    the live-alert poller's core check.

    Always pins the reference basis to the trading day BEFORE today_str,
    then splices today's price on top of that fixed series as an extra
    day -- regardless of whether today already has a real row in the DB
    (quote_tracker's background poller writes one once a symbol is
    tracked) or is still just a freshly-fetched Sinopac quote. Without
    this, once a pair is tracked, a plain "latest stored row" basis
    silently drifts to be today itself once the poller writes it,
    comparing today's price against a basis of today's price -- which
    collapses live_diff to ~0 regardless of how much has actually moved
    since yesterday's close.

    Returns None if there isn't enough history, or no price is available
    for today from either source.
    """
    yesterday = _last_trading_date_before(pair_key, today_str)
    if yesterday is None:
        return None
    baseline = compute_pair_signal(pair_key, through_date=yesterday)
    if "error" in baseline:
        return None

    cfg = PAIR_PARAMS[pair_key]
    # Prefer today's actual stored price (the poller already wrote it)
    # over the freshly-fetched live_price_a/b passed in, so this reflects
    # the DB's real state when available.
    today_a = db.latest_quote(cfg["symA"])
    today_b = db.latest_quote(cfg["symB"])
    price_a = today_a["price"] if today_a and today_a["date"] == today_str else live_price_a
    price_b = today_b["price"] if today_b and today_b["date"] == today_str else live_price_b
    if price_a is None or price_b is None:
        return None

    live = compute_pair_signal(pair_key, through_date=yesterday, extra=(today_str, price_a, price_b))
    if "error" in live or live["basis_date"] != today_str:
        return None

    prev_close_a, prev_close_b = _prev_close_pair(pair_key, yesterday)
    return {
        "key": pair_key, "label": cfg["label"], "nameA": cfg["nameA"], "nameB": cfg["nameB"],
        "baseline_date": yesterday,
        "live_diff": live["diff"], "live_price_a": price_a, "live_price_b": price_b,
        "prev_close_a": prev_close_a, "prev_close_b": prev_close_b,
        "is_open": live["is_open"], "entered_today": live["entered_today"], "reset_today": live["reset_today"],
        "tier_index": live["tier_index"], "tier_index_before": baseline["tier_index"],
        "tier_count": live["tier_count"], "maxed_out": live["maxed_out"],
    }


def apply_override(result, override, cfg):
    """Whether the user's manually-tracked position (see
    lite_position_override) should itself transition given today's live
    diff -- using the mechanism's own asymmetric transition rule
    (_transition, the same one compute_pair_signal's history walk uses),
    not "did the raw signal cross a threshold somewhere in its own price
    history". The override represents what the user's real holdings
    actually are (which can differ from the auto-computed signal -- a
    manual trade outside the app, a partial fill, deciding not to follow
    a signal, ...), so the right question is "given where I'm actually
    tracked right now, does today's diff say I should move" -- a pair
    already at level 2 with the diff still only in the T1-T2 band
    correctly produces no notification (T2 is entry-only), even though
    the raw diff itself has been past a threshold for a while.

    Re-evaluated fresh on every poll -- this isn't "did I adjust the
    override today"; an override persists across days until changed, so
    a suggested move the user hasn't applied yet keeps surfacing until
    their tracked position actually catches up to it."""
    T1, T2 = cfg["tiers"]
    pos, side = override["level"], override["side"]
    new_pos, new_side = _transition(pos, side, result["live_diff"], T1, T2)
    changed = (new_pos, new_side) != (pos, side)
    out = dict(result)
    out["is_open"] = pos > 0
    out["maxed_out"] = pos >= result["tier_count"]
    out["tier_index_before"] = pos
    out["tier_index"] = new_pos if changed else pos
    out["entered_today"] = changed and new_pos > 0
    out["reset_today"] = changed and new_pos == 0
    out["override_active"] = True
    return out
