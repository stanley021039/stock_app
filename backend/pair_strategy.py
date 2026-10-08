"""Pair-rebalancing strategy: MA-deviation signal + gated return-flow,
with a per-pair tuned (MA window, trigger threshold) instead of one global
setting for every pair. See the project scratchpad's CLAUDE.md for how
these params were chosen (grid search over MA x trigger, kept only pairs
with End win-rate >= 85% and positive excess return).

Two engine variants, per pair:
  - "single": one flat trigger. Entry re-fires every day |diff| stays past
    it (no cap), reset (full 50/50) only on a diff sign-flip while open.
  - "tiered": an ascending ladder of trigger levels (`tiers`). Each level
    fires AT MOST ONCE per open episode (won't re-enter at a level already
    used, and there's no entry beyond the largest level) -- levels reset
    together with the position on the next sign-flip. Chosen for pairs
    where this outperformed the single-trigger version in backtest (see
    scratchpad's tiered_entry_backtest.py grid search).

This module is pure computation over `db.get_prices()` — no state of its
own. "Today's signal" / "tomorrow's threshold" are derived on the fly from
whatever is in the `prices` table, so refreshing data (via the `/update`
endpoint in main.py) is what makes a new date show up, not anything stored
here.
"""
import db

MA_TYPE = "sma"

PAIR_PARAMS = {
    "dram": {
        "label": "記憶體雙雄", "symA": "2408.TW", "symB": "2344.TW",
        "nameA": "南亞科", "nameB": "華邦電", "ma": 60,
        "engine": "tiered", "tiers": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14], "sell_fraction": 0.30,
        "excess_pp": 876.1, "bh_ratio": 2.11, "ir": 1.32,
        "end_win_rate": 94.7, "one_year_win_rate": 94.3,
        "sharpe": 1.40, "max_dd": -63.8,
        "n_trades": 202, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
    "tw_ossat": {
        "label": "封測雙雄", "symA": "3711.TW", "symB": "6239.TW",
        "nameA": "日月光投控", "nameB": "力成", "ma": 60,
        "engine": "tiered", "tiers": [0.07, 0.105, 0.14, 0.175, 0.21, 0.245], "sell_fraction": 0.30,
        "excess_pp": 207.6, "bh_ratio": 1.46, "ir": 0.63,
        "end_win_rate": 99.6, "one_year_win_rate": 86.2,
        "sharpe": 1.26, "max_dd": -47.9,
        "n_trades": 102, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
    "tw_passive": {
        "label": "被動元件雙雄", "symA": "2327.TW", "symB": "2492.TW",
        "nameA": "國巨", "nameB": "華新科", "ma": 60,
        "engine": "tiered", "tiers": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14], "sell_fraction": 0.30,
        "excess_pp": 129.0, "bh_ratio": 1.37, "ir": 0.56,
        "end_win_rate": 99.2, "one_year_win_rate": 77.3,
        "sharpe": 0.94, "max_dd": -63.6,
        "n_trades": 170, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
    "tw_power": {
        "label": "功率元件雙雄", "symA": "2481.TW", "symB": "8261.TW",
        "nameA": "強茂", "nameB": "富鼎", "ma": 60,
        "engine": "tiered", "tiers": [0.05, 0.075, 0.10, 0.125, 0.15, 0.175], "sell_fraction": 0.30,
        "excess_pp": 126.1, "bh_ratio": 1.72, "ir": 0.82,
        "end_win_rate": 99.6, "one_year_win_rate": 92.0,
        "sharpe": 0.75, "max_dd": -53.1,
        "n_trades": 166, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
    "aiserver": {
        "label": "AI伺服器雙雄", "symA": "3231.TW", "symB": "6669.TW",
        "nameA": "緯創", "nameB": "緯穎", "ma": 90,
        "engine": "tiered", "tiers": [0.08, 0.12, 0.16, 0.20, 0.24, 0.28], "sell_fraction": 0.30,
        "excess_pp": 485.6, "bh_ratio": 1.71, "ir": 0.76,
        "end_win_rate": 97.8, "one_year_win_rate": 70.0,
        "sharpe": 1.43, "max_dd": -35.7,
        "n_trades": 112, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
    "shipping": {
        "label": "航運雙雄", "symA": "2603.TW", "symB": "2609.TW",
        "nameA": "長榮", "nameB": "陽明", "ma": 90,
        "engine": "tiered", "tiers": [0.04, 0.06, 0.08, 0.10, 0.12, 0.14], "sell_fraction": 0.30,
        "excess_pp": 67.8, "bh_ratio": 1.74, "ir": 0.87,
        "end_win_rate": 99.7, "one_year_win_rate": 82.7,
        "sharpe": 0.45, "max_dd": -54.7,
        "n_trades": 97, "backtest_start": "2021-10-12", "backtest_end": "2026-08-21",
    },
}

# Symbols evaluated but excluded from live trading (kept for the record).
EXCLUDED = {
    "tw_wafer": {"label": "矽晶圓雙雄", "nameA": "環球晶", "nameB": "合晶",
                 "reason": "最佳格(MA90+4%) End勝率80.8%，未達85%門檻"},
    "tw_probecard": {"label": "探針卡雙雄", "nameA": "中華精測", "nameB": "旺矽",
                      "reason": "所有(MA,門檻)組合超額報酬皆為負值，判定為結構性壞掉的股對"},
    "panel": {"label": "面板雙虎", "nameA": "友達", "nameB": "群創",
              "reason": "backtest本身達標(單一門檻8%，End勝率97.7%)，但依指示自本次分級策略更新起移出即時追蹤"},
    "tw_substrate": {"label": "載板雙雄", "nameA": "欣興", "nameB": "南電",
                     "reason": "backtest本身達標(單一門檻4%，End勝率88.7%)，但依指示自本次分級策略更新起移出即時追蹤"},
    "tw_cclcopper": {"label": "PCB/CCL雙雄", "nameA": "台燿", "nameB": "聯茂",
                     "reason": "全部(MA,門檻)組合超額報酬與IR皆為負值，判定為結構性壞掉的股對"},
    "tw_mobo": {"label": "主機板/伺服器雙雄", "nameA": "技嘉", "nameB": "神達",
                "reason": "最佳格(MA30+4%) End勝率81.4%，未達85%門檻"},
}

ALL_SYMBOLS = sorted({s for p in PAIR_PARAMS.values() for s in (p["symA"], p["symB"])})


def ma_dev(closes, window):
    n = len(closes)
    out = [None] * n
    for i in range(window - 1, n):
        window_slice = closes[i - window + 1:i + 1]
        ma = sum(window_slice) / window
        out[i] = closes[i] / ma - 1.0
    return out


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


def _dev_at_price(sumN_1, price, N):
    return N * price / (sumN_1 + price) - 1


def _price_for_dev(sumN_1, d, N):
    return (d + 1) * sumN_1 / (N - 1 - d)


def compute_pair_signal(pair_key, through_date=None):
    """Signal state + next-trading-day thresholds, using price data up to
    (and including) through_date -- or the latest available if None.
    Also reports whether an entry/reset fired ON through_date itself
    (entered_today / reset_today), so callers can tell "this is what
    actually happened on this date" apart from "this is the threshold
    for the day after".

    Branches on cfg["engine"]:
      "single" -- one flat trigger, re-fires every day it's exceeded.
      "tiered" -- ascending `tiers` ladder, each level fires at most once
        per open episode (mirrors tiered_entry_backtest.py's mechanics).
    """
    cfg = PAIR_PARAMS[pair_key]
    N = cfg["ma"]
    tiered = cfg["engine"] == "tiered"
    tiers = cfg["tiers"] if tiered else [cfg["trigger"]]
    dates, closeA, closeB = _merged_history(cfg["symA"], cfg["symB"], through_date)
    n = len(dates)
    if n < N:
        return {"key": pair_key, **cfg, "error": "not enough price history"}

    devA = ma_dev(closeA, N)
    devB = ma_dev(closeB, N)
    diff = [None if (a is None or b is None) else a - b for a, b in zip(devA, devB)]
    i0 = N - 1

    prev_diff = None
    is_open = False
    entered_today = False
    reset_today = False
    entries_since_reset = 0  # how many entries have stacked up since the position was last flat
    tier_fired = [False] * len(tiers)  # only meaningfully bounded when tiered=True
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
        if tiered:
            for k, thr in enumerate(tiers):
                if abs(d) > thr and not tier_fired[k]:
                    is_open = True
                    tier_fired[k] = True
                    entries_since_reset += 1
                    if t == t_last:
                        entered_today = True
        else:
            if abs(d) > tiers[0]:
                is_open = True
                entered_today = (t == t_last)
                entries_since_reset += 1
        prev_diff = d

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
        return (pct_a_sell_a + (-pct_b_down)) / 2  # A-B threshold: cross above -> sell A buy B

    def entry_low_for(trig):
        pa_sell_b = _price_for_dev(sumN_1_a, devB_flat - trig, N)
        pct_a_sell_b = pa_sell_b / lastA - 1
        pb_up = _price_for_dev(sumN_1_b, devA_flat + trig, N)
        pct_b_up = pb_up / lastB - 1
        return (pct_a_sell_b + (-pct_b_up)) / 2  # A-B threshold: cross below -> sell B buy A

    # Every tier's threshold, for the "mark every level" bar -- not just the
    # next one. A sign-flip always resets tier_fired before any entry check,
    # so within one open episode only ONE direction ever advances through
    # the ladder; the opposite direction (a hypothetical reversal) is always
    # fresh at tiers[0] until that happens.
    fired_count = sum(tier_fired) if tiered else 0
    maxed_out = tiered and fired_count >= len(tiers)
    tier_marks = None
    if tiered:
        tier_marks = [
            {"tier": tv, "entry_high": entry_high_for(tv), "entry_low": entry_low_for(tv), "fired": i < fired_count}
            for i, tv in enumerate(tiers)
        ]

    continue_trigger = (tiers[-1] if maxed_out else tiers[fired_count]) if tiered else tiers[0]
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

    result = {
        "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
        "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": N, "engine": cfg["engine"],
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
        "bh_ratio": cfg["bh_ratio"], "ir": cfg["ir"],
        "basis_date": basis_date, "diff": cur_diff, "flat_diff": flat_diff, "is_open": is_open,
        "entry_high": entry_high, "entry_low": entry_low, "reset_ab": reset_ab,
        "high_maxed": high_maxed, "low_maxed": low_maxed,
        "entered_today": entered_today, "reset_today": reset_today,
        "entries_since_reset": entries_since_reset,
    }
    if tiered:
        result.update({
            "tiers": tiers, "sell_fraction": cfg["sell_fraction"],
            "tier_index": fired_count, "tier_count": len(tiers), "maxed_out": maxed_out,
            "tier_marks": tier_marks,
        })
    else:
        result["trigger"] = cfg["trigger"]
    return result


def _prev_trading_date(pair_key, target_date):
    """The trading date immediately before target_date, for this pair's
    two symbols. None if target_date is the earliest date on record."""
    cfg = PAIR_PARAMS[pair_key]
    dates, _, _ = _merged_history(cfg["symA"], cfg["symB"], target_date)
    return dates[-2] if len(dates) >= 2 else None


def signal_for_target(pair_key, target_date=None):
    """The view a date-picker wants.

    target_date=None -- "predict the next trading day": basis = latest
    available close, entry/reset thresholds are for the day after it,
    outcome_known=False (it hasn't happened yet).

    target_date=<a real date D> -- "what actually happened on D": the
    entry/reset thresholds shown are the ones that were IN FORCE entering
    D (computed from D's previous close), paired with what D's own close
    actually did (actual_diff / is_open_after / entered_today / reset_today).
    outcome_known=True.
    """
    cfg = PAIR_PARAMS[pair_key]
    static_engine_keys = ("engine", "trigger", "tiers", "sell_fraction")
    state_engine_keys = ("tier_index", "tier_count", "maxed_out", "tier_marks", "high_maxed", "low_maxed")

    if target_date is None:
        proj = compute_pair_signal(pair_key, None)
        if "error" in proj:
            return proj
        return {
            "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
            "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": proj["ma"],
            **{k: proj[k] for k in static_engine_keys + state_engine_keys if k in proj},
            "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
            "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
            "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
            "bh_ratio": cfg["bh_ratio"], "ir": cfg["ir"],
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
        # target_date has no price row of its own for this pair (weekend,
        # holiday, future date, or before this pair's history starts) --
        # `_merged_history` silently fell back to the closest earlier date.
        return {"key": pair_key, "label": cfg["label"], "error": f"{target_date} 無資料（非交易日或超出可計算範圍）"}

    if threshold is not None and "error" not in threshold:
        basis_date_out = threshold["basis_date"]
        is_open_before = threshold["is_open"]
        basis_diff = threshold["diff"]
        entry_high, entry_low, reset_ab = threshold["entry_high"], threshold["entry_low"], threshold["reset_ab"]
        entries_before = threshold["entries_since_reset"]
        state_fields = {k: threshold[k] for k in state_engine_keys if k in threshold}
    else:
        # target_date is the earliest date on record for this pair -- no
        # prior close to compute a threshold from.
        basis_date_out, is_open_before, basis_diff = None, False, None
        entry_high = entry_low = reset_ab = None
        entries_before = 0
        state_fields = {}

    return {
        "key": pair_key, "label": cfg["label"], "symA": cfg["symA"], "symB": cfg["symB"],
        "nameA": cfg["nameA"], "nameB": cfg["nameB"], "ma": actual["ma"],
        **{k: actual[k] for k in static_engine_keys if k in actual},
        **state_fields,
        "excess_pp": cfg["excess_pp"], "end_win_rate": cfg["end_win_rate"],
        "one_year_win_rate": cfg["one_year_win_rate"], "sharpe": cfg["sharpe"], "max_dd": cfg["max_dd"],
        "n_trades": cfg["n_trades"], "backtest_start": cfg["backtest_start"], "backtest_end": cfg["backtest_end"],
        "bh_ratio": cfg["bh_ratio"], "ir": cfg["ir"],
        "target_date": target_date, "outcome_known": True,
        "basis_date": basis_date_out, "is_open_before": is_open_before, "basis_diff": basis_diff,
        "entry_high": entry_high, "entry_low": entry_low, "reset_ab": reset_ab,
        "entries_since_reset": entries_before,
        "entries_since_reset_after": actual["entries_since_reset"],
        "actual_diff": actual["diff"], "is_open_after": actual["is_open"],
        "entered_today": actual["entered_today"], "reset_today": actual["reset_today"],
    }


def list_available_dates(limit=120):
    """Most recent trading dates common to all pairs' symbols (drives the
    date picker) -- capped since users only care about recent history."""
    sets = None
    for sym in ALL_SYMBOLS:
        d = {r["date"] for r in db.get_prices(sym)}
        sets = d if sets is None else (sets & d)
    return sorted(sets, reverse=True)[:limit] if sets else []


def all_signals(target_date=None):
    return [signal_for_target(k, target_date) for k in PAIR_PARAMS]
