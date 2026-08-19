"""
Run this ON YOUR OWN COMPUTER (not in GitHub) to export your MyFitnessPal
session cookies. The output gets pasted into a GitHub Actions secret.

Setup (one time):
    pip install browser-cookie3

Usage:
    1. Log in to https://www.myfitnesspal.com in your normal browser.
    2. Run:  python export_cookies.py
    3. Copy the JSON it prints (the whole line) into the MFP_COOKIES
       secret on GitHub (repo Settings > Secrets and variables > Actions).

Cookies expire after roughly 30 days. When the GitHub Action starts
failing with a login error, just repeat steps 1-3.
"""

import json

import browser_cookie3

DOMAIN = "myfitnesspal.com"


def main() -> None:
    try:
        jar = browser_cookie3.load(domain_name=DOMAIN)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Couldn't read browser cookies: {exc}\n"
            "Make sure you're logged in to myfitnesspal.com in Chrome, "
            "Firefox, Edge, or Safari on this machine."
        )

    cookies = [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": bool(c.secure),
        }
        for c in jar
        if DOMAIN in (c.domain or "")
    ]

    if not cookies:
        raise SystemExit(
            "No MyFitnessPal cookies found. Log in to myfitnesspal.com "
            "in your browser first, then run this again."
        )

    print("\n=== Copy everything between the lines into the MFP_COOKIES secret ===\n")
    print(json.dumps(cookies, separators=(",", ":")))
    print(f"\n=== {len(cookies)} cookies exported ===")


if __name__ == "__main__":
    main()
