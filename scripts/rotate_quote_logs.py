"""Manual entry point for backend/log_rotation.py (the backend also runs it
at startup) -- sweeps archived quote-service logs into logs/quote-service/
and keeps only the newest few."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from log_rotation import rotate_quote_logs  # noqa: E402

if __name__ == "__main__":
    moved, removed = rotate_quote_logs()
    print(f"rotate_quote_logs: moved {moved}, removed {removed}")
