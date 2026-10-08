"""TAIFEX (台灣期貨交易所) daily futures data.

Yahoo Finance doesn't carry Taiwan index futures, so we pull directly from
TAIFEX's public daily-data CSV download. We build a **front-month continuous**
series: for each trading day we keep the most-traded *regular-session* (一般)
contract month, which naturally rolls to the next month around each monthly
settlement. The series is NOT back-adjusted, so expect small gaps at rollovers.

Source: https://www.taifex.com.tw/cht/3/futDataDown
  - POST form: down_type=1, commodity_id=TX, queryStartDate, queryEndDate
  - Response: CSV, MS950/cp950 encoded, **<= 1 calendar month per request**.

CSV columns (0-indexed):
  0 交易日期  1 契約  2 到期月份(週別)  3 開盤  4 最高  5 最低  6 收盤
  7 漲跌  8 漲跌%  9 成交量  10 結算價  11 未沖銷契約數 ... 17 交易時段(一般/盤後)
"""
import csv
import io
import time
from datetime import date, datetime, timedelta

import requests

URL = "https://www.taifex.com.tw/cht/3/futDataDown"
HEADERS = {"User-Agent": "Mozilla/5.0", "Referer": URL}

COL_DATE, COL_CONTRACT, COL_MONTH = 0, 1, 2
COL_OPEN, COL_HIGH, COL_LOW, COL_CLOSE = 3, 4, 5, 6
COL_VOLUME, COL_SETTLE, COL_SESSION = 9, 10, 17

DAY_SESSION = "一般"      # regular session (vs 盤後 night session)
INCEPTION = "1998-07-21"  # TX (臺股期貨) launch date


def _num(x):
    x = (x or "").replace(",", "").strip()
    if x in ("", "-"):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def _int(x):
    v = _num(x)
    return int(v) if v is not None else None


def _fetch_window(commodity, start, end, retries=3, pause=0.6):
    """Fetch one <=1-month window; returns parsed CSV rows (or [] if none)."""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(
                URL,
                data={"down_type": "1", "commodity_id": commodity,
                      "queryStartDate": start, "queryEndDate": end},
                headers=HEADERS, timeout=60,
            )
            txt = r.content.decode("cp950", "replace")
            if "交易日期" not in txt[:60]:   # HTML error page, not a CSV
                return []
            return [row for row in csv.reader(io.StringIO(txt)) if len(row) > COL_SESSION]
        except Exception as e:  # noqa: BLE001 - report and retry
            last_err = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"TAIFEX fetch {commodity} {start}~{end} failed: {last_err}")


def _month_windows(start_d, end_d):
    """Yield (start, end) strings, each within a single calendar month."""
    cur = start_d
    while cur <= end_d:
        if cur.month == 12:
            month_first_next = date(cur.year + 1, 1, 1)
        else:
            month_first_next = date(cur.year, cur.month + 1, 1)
        win_end = min(month_first_next - timedelta(days=1), end_d)
        yield cur.strftime("%Y/%m/%d"), win_end.strftime("%Y/%m/%d")
        cur = month_first_next


def fetch_daily(commodity="TX", start_date=None, end_date=None, pause=0.5):
    """Front-month continuous daily bars for a TAIFEX futures product.

    start_date/end_date are 'YYYY-MM-DD' (start defaults to product inception,
    end to today). Returns price-row dicts compatible with db.upsert_prices.
    """
    end_d = (datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today())
    start_d = datetime.strptime(start_date or INCEPTION, "%Y-%m-%d").date()

    best = {}  # date 'YYYY-MM-DD' -> (volume, row dict); keep the most-traded
    for s, e in _month_windows(start_d, end_d):
        for r in _fetch_window(commodity, s, e):
            if r[COL_SESSION].strip() != DAY_SESSION:
                continue
            if r[COL_CONTRACT].strip() != commodity:
                continue
            close = _num(r[COL_CLOSE])
            if close is None:
                continue
            vol = _int(r[COL_VOLUME]) or 0
            d = r[COL_DATE].strip().replace("/", "-")
            if d not in best or vol > best[d][0]:
                best[d] = (vol, {
                    "date": d,
                    "open": _num(r[COL_OPEN]),
                    "high": _num(r[COL_HIGH]),
                    "low": _num(r[COL_LOW]),
                    "close": close,
                    "adj_close": close,   # futures: no dividend adjustment
                    "volume": vol,
                })
        time.sleep(pause)
    return [best[d][1] for d in sorted(best)]
