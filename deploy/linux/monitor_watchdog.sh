#!/usr/bin/env bash
set -euo pipefail

checker=/home/ubuntu/straddle-monitor/bin/check_monitor_health.py
python_root=/home/ubuntu/straddle-data/python
mql_root=/home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver

if /usr/bin/python3 "$checker" \
  --python-root "$python_root" \
  --mql-root "$mql_root" \
  --max-age-seconds 120
then
  exit 0
fi

/usr/bin/systemctl stop straddle-python.service
/usr/bin/systemctl restart straddle-mt5.service
/usr/bin/sleep 20
/usr/bin/systemctl start straddle-python.service
exit 1
