"""Backfill TAIFEX index-futures daily history into the DB.

Adds the front-month continuous series for a TAIFEX product (default TX =
臺股期貨 / 台指期). Resumable: by default it resumes from the last stored date.

Usage (env python):
    python init_taifex.py                       # TX, resume from last stored
    python init_taifex.py --start 2015-01-01    # TX from a given date
    python init_taifex.py --full                # TX from inception (1998)
    python init_taifex.py --commodity MTX       # 小台
"""
import argparse

import db
import taifex

PRODUCTS = {
    "TX": "臺股期貨 台指期(近月連續)",
    "MTX": "小型臺指期貨 小台(近月連續)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commodity", default="TX")
    ap.add_argument("--name", default=None)
    ap.add_argument("--start", default=None,
                    help="YYYY-MM-DD (default: resume from last stored)")
    ap.add_argument("--full", action="store_true", help="force from inception")
    args = ap.parse_args()

    db.init_schema()
    sym = args.commodity
    name = args.name or PRODUCTS.get(sym, sym)
    db.upsert_symbol(sym, name, "TW", "future", currency="TWD", source="taifex")

    start = args.start
    if not start and not args.full:
        start = db.last_price_date(sym)  # resume; None => inception

    print(f"Fetching {sym} ({name}) from {start or taifex.INCEPTION} to today ...")
    rows = taifex.fetch_daily(sym, start_date=start)
    written = db.upsert_prices(sym, rows)
    print(f"{sym}: wrote {written} bars | total {db.price_count(sym)} | "
          f"latest {db.last_price_date(sym)}")


if __name__ == "__main__":
    main()
