"""One-shot initial data load.

Creates the schema, seeds the curated ticker universe, sets the default home
indices, then downloads full daily history for every seed symbol.

Resumable: symbols that already have data are skipped unless --force is given.

Usage (with the conda env active or via the env python):
    python init_db.py
    python init_db.py --force          # re-download everything
    python init_db.py --only 2330.TW   # just one (repeatable)
"""
import argparse
import sys
import time

import db
import fetch
from tickers import DEFAULT_HOME_INDICES, all_seed_symbols


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="re-download even if data already exists")
    ap.add_argument("--only", action="append", default=[],
                    help="restrict to specific symbol(s)")
    ap.add_argument("--pause", type=float, default=0.6,
                    help="seconds to sleep between symbols (throttle)")
    args = ap.parse_args()

    db.init_schema()

    seeds = all_seed_symbols()
    for s in seeds:
        db.upsert_symbol(s["symbol"], s["name"], s["market"], s["type"])

    # Only set default home indices if not configured yet.
    if not db.get_home_indices():
        db.set_home_indices(DEFAULT_HOME_INDICES)

    targets = seeds
    if args.only:
        wanted = set(args.only)
        targets = [s for s in seeds if s["symbol"] in wanted]

    total = len(targets)
    ok = skipped = failed = 0
    print(f"Downloading history for {total} symbols (pause={args.pause}s)...")
    for i, s in enumerate(targets, 1):
        symbol = s["symbol"]
        existing = db.price_count(symbol)
        if existing and not args.force:
            print(f"[{i}/{total}] {symbol:<10} skip ({existing} bars)")
            skipped += 1
            continue
        try:
            rows = fetch.fetch_history(symbol, period="max")
            written = db.upsert_prices(symbol, rows)
            last = db.last_price_date(symbol)
            print(f"[{i}/{total}] {symbol:<10} ok  {written} bars (latest {last})")
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{total}] {symbol:<10} FAIL  {e}", file=sys.stderr)
            failed += 1
        time.sleep(args.pause)

    print(f"\nDone. ok={ok} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
