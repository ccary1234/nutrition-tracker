"""
Pulls daily nutrition totals from MyFitnessPal into data/nutrition.json.
Runs locally on a Mac; reads MFP session cookies straight from Chrome.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

import browser_cookie3
import myfitnesspal

DATA_PATH = Path(__file__).parent / "data" / "nutrition.json"
BACKFILL_DAYS = 60
MAX_DAYS_PER_RUN = 90
REQUEST_PAUSE_SECONDS = 1.0

FIELDS = {
    "calories": "calories",
    "protein": "protein",
    "carbohydrates": "carbs",
    "fat": "fat",
}


def load_existing() -> list[dict]:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text())
    return []


def dates_to_fetch(existing: list[dict]) -> list[dt.date]:
    yesterday = dt.date.today() - dt.timedelta(days=1)
    if existing:
        last = dt.date.fromisoformat(max(e["date"] for e in existing))
        start = last + dt.timedelta(days=1)
    else:
        start = yesterday - dt.timedelta(days=BACKFILL_DAYS - 1)

    days = []
    d = start
    while d <= yesterday and len(days) < MAX_DAYS_PER_RUN:
        days.append(d)
        d += dt.timedelta(days=1)
    return days


def fetch_day(client: myfitnesspal.Client, day: dt.date) -> dict:
    entry: dict = {"date": day.isoformat()}
    diary = client.get_date(day.year, day.month, day.day)
    totals = diary.totals or {}
    for mfp_key, out_key in FIELDS.items():
        value = totals.get(mfp_key)
        entry[out_key] = round(value) if isinstance(value, (int, float)) else None
    return entry


def main() -> int:
    try:
        jar = browser_cookie3.chrome(domain_name="myfitnesspal.com")
    except Exception as exc:
        print(f"ERROR: couldn't read Chrome cookies: {exc}")
        print("Open Chrome, confirm you're logged in to myfitnesspal.com, retry.")
        return 1

    client = myfitnesspal.Client(cookiejar=jar)

    existing = load_existing()
    days = dates_to_fetch(existing)
    if not days:
        print("Already up to date; nothing to fetch.")
        return 0

    print(f"Fetching {len(days)} day(s): {days[0]} -> {days[-1]}")
    fetched = []
    for day in days:
        try:
            entry = fetch_day(client, day)
        except myfitnesspal.exceptions.MyfitnesspalLoginError:
            print("ERROR: MFP rejected the session. Log in to myfitnesspal.com in Chrome and rerun.")
            return 1
        fetched.append(entry)
        logged = entry.get("calories")
        print(f"  {entry['date']}: {logged if logged is not None else 'no entries'}")
        time.sleep(REQUEST_PAUSE_SECONDS)

    merged = {e["date"]: e for e in existing}
    merged.update({e["date"]: e for e in fetched})
    combined = sorted(merged.values(), key=lambda e: e["date"])

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(combined, indent=1))
    print(f"Wrote {len(combined)} total days to {DATA_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
