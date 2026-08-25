#!/usr/bin/env bash
set -euo pipefail

target_python_root=/home/ubuntu/straddle-data/python
target_mql_root=/home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver
demo_telemetry=/home/ubuntu/.wine-straddle-demo/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleReplica_901018_XAUUSD.csv
output_root=/home/ubuntu/straddle-analysis/demo-daily
checker=/home/ubuntu/straddle-monitor/bin/check_monitor_health.py
comparator=/home/ubuntu/straddle-monitor/package/tools/compare_live_target_demo.py

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output="$output_root/target-demo-comparison-$timestamp.json"
mkdir -p "$output_root"

systemctl is-active --quiet straddle-demo-mt5.service
test -s "$demo_telemetry"

python3 "$checker" \
  --python-root "$target_python_root" \
  --mql-root "$target_mql_root" \
  --max-age-seconds 120

python3 "$comparator" \
  --target-python-root "$target_python_root" \
  --demo-telemetry "$demo_telemetry" \
  --output "$output"

python3 "$checker" \
  --python-root "$target_python_root" \
  --mql-root "$target_mql_root" \
  --max-age-seconds 120

printf '%s\n' "$output"
