"""Bulk-download intraday (default 5m) bars for the seed universe.

Yahoo only serves a rolling ~60-day window for 5m, so this grabs period=60d
per symbol. Resumable: symbols that already have intraday data are skipped
unless --force.

Usage:
    python init_intraday.py                 # all seed symbols, 5m
    python init_intraday.py --interval 15m
    python init_intraday.py --only AAPL --force
"""
import argparse
import sys
import time

import db
import fetch
from tickers import all_seed_symbols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="5m", help="intraday interval (5m, 15m, ...)")
    ap.add_argument("--period", default="60d", help="how far back to pull (5m max 60d)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--pause", type=float, default=0.8)
    args = ap.parse_args()

    db.init_schema()
    seeds = all_seed_symbols()
    for s in seeds:
        db.upsert_symbol(s["symbol"], s["name"], s["market"], s["type"])

    targets = seeds
    if args.only:
        wanted = set(args.only)
        targets = [s for s in seeds if s["symbol"] in wanted]

    total = len(targets)
    ok = skipped = failed = 0
    print(f"Downloading {args.interval} bars for {total} symbols (period={args.period})...")
    for i, s in enumerate(targets, 1):
        symbol = s["symbol"]
        existing = db.intraday_count(symbol, args.interval)
        if existing and not args.force:
            print(f"[{i}/{total}] {symbol:<10} skip ({existing} bars)")
            skipped += 1
            continue
        try:
            rows = fetch.fetch_intraday(symbol, interval=args.interval, period=args.period)
            written = db.upsert_intraday(symbol, args.interval, rows)
            print(f"[{i}/{total}] {symbol:<10} ok  {written} bars")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{total}] {symbol:<10} FAIL  {e}", file=sys.stderr)
            failed += 1
        time.sleep(args.pause)

    print(f"\nDone. ok={ok} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
