#!/bin/zsh
cd ~/nutrition-tracker
echo "=== Run started: $(date) ==="
/usr/local/bin/python3 fetch_mfp.py 2>&1 || /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 fetch_mfp.py 2>&1
/usr/local/bin/python3 fetch_prices.py 2>&1 || /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 fetch_prices.py 2>&1
git add data/
if ! git diff --cached --quiet; then
  git commit -m "Daily data update $(date +%F)"
  git push
  echo "Pushed."
else
  echo "No changes."
fi
echo "=== Run finished: $(date) ==="
