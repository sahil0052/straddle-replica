#!/usr/bin/env bash
set -euo pipefail

export HOME=/home/ubuntu
export DISPLAY=:99
export WINEPREFIX=/home/ubuntu/.wine-mt5
export WINEDEBUG=-all
runtime_dir="/run/user/$(id -u)"
mkdir -p -m 700 "$runtime_dir"
export XDG_RUNTIME_DIR="$runtime_dir"

mql_root=/home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver
monitor_started_epoch=$(date +%s)

mql_ready() {
  python3 - "$mql_root" "$monitor_started_epoch" <<'PY'
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

root = Path(sys.argv[1])
started_epoch = float(sys.argv[2])
heartbeats = list(root.rglob("heartbeat-*.csv"))
if not heartbeats:
    raise SystemExit(1)
heartbeat = max(heartbeats, key=lambda path: path.stat().st_mtime)
if heartbeat.stat().st_mtime < started_epoch:
    raise SystemExit(1)
if time.time() - heartbeat.stat().st_mtime > 10:
    raise SystemExit(1)
lines = [line for line in heartbeat.read_text().splitlines() if line]
if len(lines) < 2:
    raise SystemExit(1)
row = next(csv.DictReader([lines[0], lines[-1]]))
raise SystemExit(
    0
    if row.get("connected") == "1" and row.get("trade_allowed") == "0"
    else 1
)
PY
}

for _ in $(seq 1 180); do
  if [[ "$(pgrep -u "$(id -u)" -x main 2>/dev/null | wc -l)" -eq 1 ]] &&
    mql_ready
  then
    break
  fi
  sleep 1
done

if [[ "$(pgrep -u "$(id -u)" -x main 2>/dev/null | wc -l)" -ne 1 ]] ||
  ! mql_ready
then
  echo "MT5 observer did not become ready within 180 seconds" >&2
  exit 1
fi

cd /home/ubuntu/straddle-monitor/package

exec wine 'C:\Python311\python.exe' \
  -m straddle_replica.monitor_cli monitor-live \
  --terminal 'Z:\home\ubuntu\mt5-observer\terminal64.exe' \
  --output 'Z:\home\ubuntu\straddle-data\python' \
  --account 901018 \
  --server AchieverGlobalMarkets-Server \
  --symbol XAUUSD \
  --poll-ms 50 \
  --checkpoint-seconds 30 \
  --history-poll-seconds 0.25 \
  --heartbeat-seconds 1 \
  --exit-on-connection-error \
  --require-read-only
