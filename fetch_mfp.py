"""
Pulls daily nutrition totals from MyFitnessPal and appends them to
data/nutrition.json. Runs in GitHub Actions on a daily cron.
Auth comes from the MFP_COOKIES secret (see export_cookies.py).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from http.cookiejar import Cookie, CookieJar
from pathlib import Path

import requests

# --- Disguise as a real browser (MFP 403s obvious scripts) ---
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.myfitnesspal.com/",
}
_orig_session_init = requests.Session.__init__


def _patched_session_init(self, *args, **kwargs):
    _orig_session_init(self, *args, **kwargs)
    self.headers.update(_BROWSER_HEADERS)


requests.Session.__init__ = _patched_session_init
# --------------------------------------------------------------

import myfitnesspal  # noqa: E402  (import after the patch, on purpose)

DATA_PATH = Path("data/nutrition.json")
BACKFILL_DAYS = 60
MAX_DAYS_PER_RUN = 90
REQUEST_PAUSE_SECONDS = 1.0

FIELDS = {
    "calories": "calories",
    "protein": "protein",
    "carbohydrates": "carbs",
    "fat": "fat",
}


def build_cookiejar(raw_json: str) -> CookieJar:
    jar = CookieJar()
    for c in json.loads(raw_json):
        domain = c.get("domain", ".myfitnesspal.com")
        jar.set_cookie(
            Cookie(
                version=0,
                name=c["name"],
                value=c["value"],
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path=c.get("path", "/"),
                path_specified=True,
                secure=bool(c.get("secure", True)),
                expires=None,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
            )
        )
    return jar


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
    raw_cookies = os.environ.get("MFP_COOKIES", "").strip()
    if not raw_cookies:
        print("ERROR: MFP_COOKIES env var is empty. Add it as a repo secret.")
        return 1

    client = myfitnesspal.Client(cookiejar=build_cookiejar(raw_cookies))

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
            print(
                "ERROR: MyFitnessPal rejected the session cookies. They have "
                "likely expired (~30 days). Re-run export_cookies.py locally "
                "and update the MFP_COOKIES secret."
            )
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
