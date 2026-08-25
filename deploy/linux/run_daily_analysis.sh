#!/usr/bin/env bash
set -euo pipefail

python_root=/home/ubuntu/straddle-data/python
mql_root=/home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver
output_root=/home/ubuntu/straddle-analysis/daily
checker=/home/ubuntu/straddle-monitor/bin/check_monitor_health.py
analyzer=/home/ubuntu/straddle-monitor/package/tools/analyze_live_capture.py

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="$output_root/live-analysis-$timestamp.json"
mkdir -p "$output_root"

python3 "$checker" \
  --python-root "$python_root" \
  --mql-root "$mql_root" \
  --max-age-seconds 120

python3 "$analyzer" \
  --mql-root "$mql_root" \
  --python-root "$python_root" \
  --output "$output"

python3 "$checker" \
  --python-root "$python_root" \
  --mql-root "$mql_root" \
  --max-age-seconds 120

printf '%s\n' "$output"
