#!/bin/zsh
cd ~/nutrition-tracker || exit 1

# Log every run (scheduled or manual) to tracker.log, while still showing output in Terminal.
exec > >(tee -a tracker.log) 2>&1

echo "=== Run started: $(date) ==="

PY=/usr/local/bin/python3
[ -x "$PY" ] || PY=/Library/Frameworks/Python.framework/Versions/3.10/bin/python3

rc=0

echo "--- MyFitnessPal ---"
if ! "$PY" fetch_mfp.py; then
  rc=1
  echo "!!! MFP fetch FAILED. Nutrition data was NOT updated."
  echo "!!! Most common cause: MyFitnessPal login expired in Chrome."
  echo "!!! Fix: log in at https://www.myfitnesspal.com in Chrome, then re-run ./run_tracker.sh"
fi

if ! git add data/; then
  echo "!!! git add FAILED (stale .git/index.lock? run: rm .git/index.lock)"
  echo "=== Run finished: $(date) (exit 1) ==="
  exit 1
fi
if ! git diff --cached --quiet; then
  git commit -q -m "Daily data update $(date +%F)"
  git push -q && echo "Pushed." || { rc=1; echo "!!! git push FAILED."; }
else
  echo "No changes."
fi

echo "=== Run finished: $(date) (exit $rc) ==="
exit $rc
