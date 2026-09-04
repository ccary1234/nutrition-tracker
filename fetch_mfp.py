"""
Pulls daily nutrition data from MyFitnessPal via its own web JSON API,
authenticated with Chrome session cookies.

Outputs (all public, all in data/):
  data/nutrition.json     - daily totals of every nutrient MFP reports
  data/foods.json         - aggregate per-food calories + % of total
  data/foods_detail.json  - full per-entry food log (date, meal, food,
                            brand, servings, macros)
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

import browser_cookie3
from curl_cffi import requests as creq

ROOT = Path(__file__).parent
NUTRITION_PATH = ROOT / "data" / "nutrition.json"
FOODS_AGG_PATH = ROOT / "data" / "foods.json"
DETAIL_PATH = ROOT / "data" / "foods_detail.json"

BACKFILL_DAYS = 365
MAX_DAYS_PER_RUN = 400
PAUSE_SECONDS = 0.6

RENAME = {"energy": "calories", "carbohydrates": "carbs"}


CHROME_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
SESSION_COOKIE = "__Secure-next-auth.session-token"


def chrome_cookies() -> dict:
    """Scan every Chrome profile and return the cookies from the one that is
    actually logged in to MFP (falls back to whichever has the most cookies)."""
    candidates = []
    for prof in sorted(CHROME_DIR.glob("*")):
        if prof.name == "System Profile":
            continue
        for ck in (prof / "Cookies", prof / "Network" / "Cookies"):
            if not ck.exists():
                continue
            try:
                jar = browser_cookie3.chrome(cookie_file=str(ck),
                                             domain_name="myfitnesspal.com")
                cookies = {c.name: c.value for c in jar}
            except Exception as exc:  # noqa: BLE001
                print(f"  (skipping {prof.name}: {exc})")
                continue
            if cookies:
                candidates.append((prof.name, cookies))
            break
    if not candidates:
        return {}
    logged_in = [c for c in candidates if SESSION_COOKIE in c[1]]
    name, cookies = (logged_in or sorted(candidates, key=lambda c: -len(c[1])))[0]
    print(f"Using Chrome profile '{name}' ({len(cookies)} MFP cookies"
          f"{'' if SESSION_COOKIE in cookies else ', NO session token - may not be logged in'})")
    return cookies


def get_token(sess):
    r = sess.get("https://www.myfitnesspal.com/user/auth_token?refresh=true")
    if r.status_code != 200:
        print(f"ERROR: auth token request failed: HTTP {r.status_code}")
        print((r.text or "")[:300])
        sys.exit(1)
    d = r.json()
    return d["access_token"], str(d["user_id"])


def fetch_day(sess, headers, day):
    """Returns (totals_dict_or_None, list_of_food_entries)."""
    params = {
        "types": "food_entry",
        "entry_date": day.isoformat(),
        "fields[]": ["nutritional_contents", "food", "meal_name", "servings"],
    }
    r = sess.get("https://api.myfitnesspal.com/v2/diary",
                 params=params, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {(r.text or '')[:200]}")
    items = r.json().get("items", [])

    totals = {}
    foods = []
    for it in items:
        if it.get("type") != "food_entry":
            continue
        nc = it.get("nutritional_contents") or {}
        clean = {}
        for key, val in nc.items():
            if isinstance(val, dict):
                val = val.get("value")
            if isinstance(val, (int, float)):
                out = RENAME.get(key, key)
                clean[out] = val
                totals[out] = totals.get(out, 0.0) + val
        food = it.get("food") or {}
        foods.append({
            "date": day.isoformat(),
            "meal": it.get("meal_name"),
            "name": (food.get("description") or "Unknown").strip(),
            "brand": (food.get("brand_name") or "").strip() or None,
            "servings": it.get("servings"),
            "calories": round(clean.get("calories", 0.0), 1),
            "protein": round(clean.get("protein", 0.0), 1),
            "carbs": round(clean.get("carbs", 0.0), 1),
            "fat": round(clean.get("fat", 0.0), 1),
        })

    if not foods:
        return None, []
    return {k: round(v, 1) for k, v in totals.items()}, foods


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text())
    return default


def dates_to_fetch(existing):
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


def build_aggregate(detail):
    """Collapse the per-entry log into per-food totals."""
    agg = {}
    total_cal = 0.0
    for e in detail:
        key = e["name"].lower()
        a = agg.setdefault(key, {
            "name": e["name"], "brand": e.get("brand"),
            "calories": 0.0, "protein": 0.0, "times_logged": 0,
        })
        a["calories"] += e.get("calories") or 0.0
        a["protein"] += e.get("protein") or 0.0
        a["times_logged"] += 1
        total_cal += e.get("calories") or 0.0

    foods = sorted(agg.values(), key=lambda a: -a["calories"])
    for f in foods:
        f["calories"] = round(f["calories"])
        f["protein"] = round(f["protein"])
        f["pct_of_calories"] = round(100.0 * f["calories"] / total_cal, 2) if total_cal else 0.0

    dates = sorted({e["date"] for e in detail})
    return {
        "window_start": dates[0] if dates else None,
        "window_end": dates[-1] if dates else None,
        "total_calories": round(total_cal),
        "foods": foods,
    }


def main() -> int:
    try:
        cookies = chrome_cookies()
    except Exception as exc:
        print(f"ERROR: couldn't read Chrome cookies: {exc}")
        return 1
    if not cookies:
        print("ERROR: no MFP cookies in Chrome. Log in at myfitnesspal.com first.")
        return 1

    sess = creq.Session(impersonate="chrome", cookies=cookies)
    token, user_id = get_token(sess)
    print(f"Authenticated as user {user_id}")

    headers = {
        "Authorization": f"Bearer {token}",
        "mfp-client-id": "mfp-main-js",
        "mfp-user-id": user_id,
        "Accept": "application/json",
    }

    existing = load_json(NUTRITION_PATH, [])
    detail = load_json(DETAIL_PATH, [])
    days = dates_to_fetch(existing)

    if days:
        print(f"Fetching {len(days)} day(s): {days[0]} -> {days[-1]}")
        fetched = []
        for day in days:
            totals, foods = fetch_day(sess, headers, day)
            entry = {"date": day.isoformat()}
            if totals:
                entry.update(totals)
            else:
                entry["calories"] = None
            fetched.append(entry)
            detail = [e for e in detail if e["date"] != day.isoformat()] + foods
            cal = entry.get("calories")
            print(f"  {entry['date']}: {cal if cal is not None else 'no entries'}"
                  + (f" ({len(foods)} foods)" if foods else ""))
            time.sleep(PAUSE_SECONDS)

        merged = {e["date"]: e for e in existing}
        merged.update({e["date"]: e for e in fetched})
        existing = sorted(merged.values(), key=lambda e: e["date"])
    else:
        print("Daily totals already up to date; rebuilding aggregates.")

    NUTRITION_PATH.parent.mkdir(parents=True, exist_ok=True)
    NUTRITION_PATH.write_text(json.dumps(existing, indent=1))
    DETAIL_PATH.write_text(json.dumps(sorted(detail, key=lambda e: e["date"]), indent=1))
    FOODS_AGG_PATH.write_text(json.dumps(build_aggregate(detail), indent=1))

    print(f"Wrote {len(existing)} days -> data/nutrition.json")
    print(f"Wrote {len(detail)} food entries -> data/foods_detail.json")
    print(f"Wrote aggregate -> data/foods.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
