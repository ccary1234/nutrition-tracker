"""
Pulls 10 everyday consumer prices (BLS national averages) from the
St. Louis Fed's FRED API into data/prices.json.
API key is read from ~/.fred_api_key (never committed).
"""

import json
import sys
from datetime import date
from pathlib import Path

from curl_cffi import requests as creq

OUT = Path(__file__).parent / "data" / "prices.json"
KEY_FILE = Path.home() / ".fred_api_key"
START = "2015-01-01"

BASKET = [
    ("APU0000708111", "Eggs",        "dozen"),
    ("APU0000709112", "Milk",        "gallon"),
    ("APU0000702111", "White Bread", "lb loaf"),
    ("APU0000703112", "Ground Beef", "lb"),
    ("APU0000704111", "Bacon",       "lb"),
    ("APU0000706111", "Chicken",     "lb"),
    ("APU0000717311", "Coffee",      "lb"),
    ("APU0000711211", "Bananas",     "lb"),
    ("APU000074714",  "Gasoline",    "gallon"),
    ("APU000072610",  "Electricity", "kWh"),
]


def fetch_series(series_id: str, key: str):
    r = creq.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={
            "series_id": series_id,
            "api_key": key,
            "file_type": "json",
            "observation_start": START,
        },
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {(r.text or '')[:150]}")
    points = []
    for obs in r.json().get("observations", []):
        v = obs.get("value")
        if v in (None, "", "."):
            continue
        points.append({"date": obs["date"], "value": round(float(v), 3)})
    return points


def main() -> int:
    if not KEY_FILE.exists():
        print("ERROR: ~/.fred_api_key not found.")
        return 1
    key = KEY_FILE.read_text().strip()

    series_out = []
    for sid, name, unit in BASKET:
        try:
            pts = fetch_series(sid, key)
        except Exception as exc:
            print(f"  {name}: FAILED ({exc})")
            continue
        if pts:
            series_out.append({"id": sid, "name": name, "unit": unit, "points": pts})
            print(f"  {name}: {len(pts)} months, latest {pts[-1]['date']} = ${pts[-1]['value']}")

    if len(series_out) < 5:
        print("ERROR: too few series fetched; not writing output.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated": date.today().isoformat(),
        "source": "FRED, Federal Reserve Bank of St. Louis (BLS average prices)",
        "series": series_out,
    }, indent=1))
    print(f"Wrote {len(series_out)} series -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
