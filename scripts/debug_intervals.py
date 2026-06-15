"""Diagnostic: print raw Intervals.icu API responses.

Run from the project root:
    uv run python scripts/debug_intervals.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, ".")

from t3.integrations.intervals import get_athlete_settings, get_best_efforts, get_events

now = datetime.now(timezone.utc)
history_start = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S")
future_end = (now + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S")
now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

print("=== athlete_settings (all keys) ===")
athlete = get_athlete_settings()
for k, v in athlete.items():
    print(f"  {k!r}: {v!r}")

print(f"\n=== events between {history_start} and {future_end} ===")
events = get_events(history_start, future_end)
print(f"  total events returned: {len(events)}")
for e in events:
    sdl = e.get("start_date_local", "")
    is_upcoming = sdl >= now_str
    print(
        f"  category={e.get('category')!r}  type={e.get('type')!r}  "
        f"name={e.get('name')!r}  start_date_local={sdl!r}  upcoming={is_upcoming}"
    )
    if not e.get("category") and not e.get("type"):
        print(f"    (all keys: {list(e.keys())})")

print("\n=== best_efforts (days=28) ===")
print(json.dumps(get_best_efforts(days=28), indent=2))
