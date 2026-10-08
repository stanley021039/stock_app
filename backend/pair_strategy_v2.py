"""Pair-rebalancing strategy, v2: same tiered entry/reset mechanics as
`pair_strategy.py`, but a different deviation formula.

v1 (pair_strategy.py):
    dev_X(t) = close_X(t) / MA_X(t) − 1
    MA_X(t)  = mean of the trailing `ma` days ENDING at t (includes t itself)
    -> mean-reversion against a smoothed, self-updating trailing average.

v2 (this module):
    dev_X(t) = close_X(t) / baseline_X(t) − 1
    baseline_X(t) = mean of the OLDEST `baseline_days` days within the
    `ma`-day window ending at t, i.e. days [t-ma+1, t-ma+baseline_days]
    -> today's price vs. a fixed reference point from ~`ma` days ago,
    recomputed fresh each day as the window slides forward. Closer to an
    N-day momentum/rate-of-change measure than mean reversion.

Backtested in the scratchpad (tiered_entry_backtest.py, DEV_MODE=
"start_baseline") against the same 4 pairs v1 already uses live; this
formula won on every metric for dram/tw_ossat, and traded more (lower
Sharpe, more entries) but higher excess for tw_passive/tw_power. Kept as a
separate, parallel tab rather than replacing v1 so the two can be watched
side by side before deciding whether to adopt v2 for any pair.

Same engine mechanics as v1 (tiered ladder, each level fires once per open
episode, full 50/50 reset on a diff sign-flip) -- only the dev/baseline
computation and its threshold-inversion math differ. See v1's docstring
for the entry/reset rules themselves.
"""
import db

PAIR_PARAMS = {
    "dram": {
        "label": "記憶體雙雄", "symA": "2408.TW", "symB": "2344.TW",
        "nameA": "南亞科", "nameB": "華邦電", "ma": 60, "baseline_days": 10,
        "tiers": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14], "sell_fraction": 0.30,
        "excess_pp": 787.3, "end_win_rate": 99.4, "one_year_win_rate": 95.3,
        "sharpe": 1.425, "max_dd": -63.2,
        "n_trades": 214, "backtest_start": "2021-10-12", "backtest_end": "2026-07-15",
    },
    "tw_ossat": {
        "label": "封測雙雄", "symA": "3711.TW", "symB": "6239.TW",
        "nameA": "日月光投控", "nameB": "力成", "ma": 60, "baseline_days": 7,
        "tiers": [0.07, 0.105, 0.14, 0.175, 0.21, 0.245], "sell_fraction": 0.30,
        "excess_pp": 193.2, "end_win_rate": 99.9, "one_year_win_rate": 75.5,
        "sharpe": 1.352, "max_dd": -47.4,
        "n_trades": 105, "backtest_start": "2021-10-12", "backtest_end": "2026-07-15",
    },
    "tw_passive": {
        "label": "被動元件雙雄", "symA": "2327.TW", "symB": "2492.TW",
        "nameA": "國巨", "nameB": "華新科", "ma": 15, "baseline_days": 7,
        "tiers": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14], "sell_fraction": 0.30,
        "excess_pp": 140.5, "end_win_rate": 98.9, "one_year_win_rate": 85.7,
        "sharpe": 0.997, "max_dd": -59.5,
        "n_trades": 263, "backtest_start": "2021-08-05", "backtest_end": "2026-07-15",
    },
    "tw_power": {
        "label": "功率元件雙雄", "symA": "2481.TW", "symB": "8261.TW",
        "nameA": "強茂", "nameB": "富鼎", "ma": 15, "baseline_days": 1,
        "tiers": [0.05, 0.075, 0.10, 0.125, 0.15, 0.175], "sell_fraction": 0.30,
        "excess_pp": 131.6, "end_win_rate": 96.7, "one_year_win_rate": 78.1,
        "sharpe": 0.798, "max_dd": -55.1,
        "n_trades": 336, "backtest_start": "2021-08-05", "backtest_end": "2026-07-15",
    },
}

ALL_SYMBOLS = sorted({s for p in PAIR_PARAMS.values() for s in (p["symA"], p["symB"])})


def start_baseline_dev(closes, window, baseline_days):
    n = len(closes)
    out = [None] * n
    for t in range(window - 1, n):
        start_idx = t - window + 1
        baseline = sum(closes[start_idx:start_idx + baseline_days]) / baseline_days
        out[t] = closes[t] / baseline - 1.0
    return out


def _baseline_next(closes, t, window, baseline_days):
    """baseline_X for day t+1 -- entirely determined by days already on the
    books today (the window slides but the oldest slice it lands on for
    tomorrow is still in the past), so this needs no price projection."""
    start_idx = (t + 1) - window + 1
    return sum(closes[start_idx:start_idx + baseline_days]) / baseline_days


def _merged_history(symA, symB, through_date=None):
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
    return dates, closeA, closeB


def compute_pair_signal(pair_key, through_date=None):
    cfg = PAIR_PARAMS[pair_key]
    N, bdays, tiers = cfg["ma"], cfg["baseline_days"], cfg["tiers"]
    dates, closeA, closeB = _merged_history(cfg["symA"], cfg["symB"], through_date)
    n = len(dates)
    if n < N:
        return {"key": pair_key, **cfg, "error": "not enough price history"}

    devA = start_baseline_dev(closeA, N, bdays)
    devB = start_baseline_dev(closeB, N, bdays)
    diff = [None if (a is None or b is None) else a - b for a, b in zip(devA, devB)]
    i0 = N - 1

    prev_diff = None
    is_open = False
    entered_today = False
    reset_today = False
    entries_since_reset = 0
    tier_fired = [False] * len(tiers)
    t_last = n - 1
    for t in range(i0 + 1, n):
        d = diff[t]
        entered_today = False
        reset_today = False
        if is_open and prev_diff is not None and prev_diff * d < 0:
            is_open = False
            reset_today = (t == t_last)
            entries_since_reset = 0
            tier_fired = [False] * len(tiers)
        for k, thr in enumerate(tiers):
            if abs(d) > thr and not tier_fired[k]:
                is_open = True
                tier_fired[k] = True
                entries_since_reset += 1
                if t == t_last:
                    entered_today = True
        prev_diff = d

    cur_diff = diff[t_last]
    basis_date = dates[t_last]
    lastA, lastB = closeA[t_last], closeB[t_last]

    # tomorrow's baseline is fully known today (see _baseline_next) -- so
    # "flat" dev (price unchanged overnight) is just today's close against
    # THAT baseline, and inverting for a target dev is a straight solve
    # with no recursive algebra needed (unlike v1's rolling-MA case).
    baseline_a_next = _baseline_next(closeA, t_last, N, bdays)
    baseline_b_next = _baseline_next(closeB, t_last, N, bdays)
    devA_flat = lastA / baseline_a_next - 1
    devB_flat = lastB / baseline_b_next - 1
    flat_diff = devA_flat - devB_flat

    def entry_high_for(trig):
        pa_sell_a = baseline_a_next * (1 + devB_flat + trig)
        pct_a_sell_a = pa_sell_a / lastA - 1
        pb_down = baseline_b_next * (1 + devA_flat - trig)
        pct_b_down = pb_down / lastB - 1
        return (pct_a_sell_a + (-pct_b_down)) / 2

    def entry_low_for(trig):
        pa_sell_b = baseline_a_next * (1 + devB_flat - trig)
        pct_a_sell_b = pa_sell_b / lastA - 1
        pb_up = baseline_b_next * (1 + devA_flat + trig)
        pct_b_up = pb_up / lastB - 1
        return (pct_a_sell_b + (-pct_b_up)) / 2

    fired_count = sum(tier_fired)
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
    pct_a_zero = baseline_a_next * (1 + devB_flat) / lastA - 1
    pct_b_zero = baseline_b_next * (1 + devA_flat) / lastB - 1
    reset_ab = (pct_a_zero + (-pct_b_zero)) / 2

    return {
        "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
        "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": N, "engine": "tiered",
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
        "basis_date": basis_date, "diff": cur_diff, "flat_diff": flat_diff, "is_open": is_open,
        "entry_high": entry_high, "entry_low": entry_low, "reset_ab": reset_ab,
        "high_maxed": high_maxed, "low_maxed": low_maxed,
        "entered_today": entered_today, "reset_today": reset_today,
        "entries_since_reset": entries_since_reset,
        "tiers": tiers, "sell_fraction": cfg["sell_fraction"], "baseline_days": bdays,
        "tier_index": fired_count, "tier_count": len(tiers), "maxed_out": maxed_out,
        "tier_marks": tier_marks,
    }


def _prev_trading_date(pair_key, target_date):
    cfg = PAIR_PARAMS[pair_key]
    dates, _, _ = _merged_history(cfg["symA"], cfg["symB"], target_date)
    return dates[-2] if len(dates) >= 2 else None


def signal_for_target(pair_key, target_date=None):
    cfg = PAIR_PARAMS[pair_key]
    static_keys = ("engine", "tiers", "sell_fraction", "baseline_days")
    state_keys = ("tier_index", "tier_count", "maxed_out", "tier_marks", "high_maxed", "low_maxed")

    if target_date is None:
        proj = compute_pair_signal(pair_key, None)
        if "error" in proj:
            return proj
        return {
            "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
            "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": proj["ma"],
            **{k: proj[k] for k in static_keys + state_keys if k in proj},
            "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
            "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
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
        **{k: actual[k] for k in static_keys if k in actual},
        **state_fields,
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
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
