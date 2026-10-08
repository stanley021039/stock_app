"""Keep the Sinopac quote service's archived logs under logs/quote-service/
and cap how many are retained.

The StockAppQuote NSSM service writes quote-service.log straight into
logs/quote-service/ and NSSM renames the previous run's file to
quote-service-<timestamp>.log on every (re)start, so they accumulate with
each restart (a failing login loop can add several in a minute). Nothing
trims them on its own -- this runs at backend startup (see main.py) and is
also callable by hand via scripts/rotate_quote_logs.py.

Only archived quote-service-*.log files are touched, never the live
quote-service.log that the service still has open. Any strays left in the
project root (from before the NSSM output path was moved) get swept in too.
"""
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs" / "quote-service"
KEEP_COUNT = 10


def rotate_quote_logs(keep=KEEP_COUNT):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    moved = 0
    for f in PROJECT_ROOT.glob("quote-service-*.log"):
        shutil.move(str(f), str(LOG_DIR / f.name))
        moved += 1

    archived = sorted(LOG_DIR.glob("quote-service-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = 0
    for f in archived[keep:]:
        f.unlink()
        removed += 1
    return moved, removed
