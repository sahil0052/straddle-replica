#!/usr/bin/env bash
set -euo pipefail

export HOME=/home/ubuntu
export DISPLAY=:99
export WINEPREFIX=/home/ubuntu/.wine-mt5
export WINEDEBUG=-all
runtime_dir="/run/user/$(id -u)"
mkdir -p -m 700 "$runtime_dir"
export XDG_RUNTIME_DIR="$runtime_dir"

terminal_linux=/home/ubuntu/mt5-observer/terminal64.exe
terminal_windows='Z:\home\ubuntu\mt5-observer\terminal64.exe'
startup_windows='Z:\home\ubuntu\straddle-monitor\observer-startup.ini'
runtime_dir=/home/ubuntu/straddle-monitor/runtime
log_dir=/home/ubuntu/straddle-monitor/logs
wineserver=/usr/lib/x86_64-linux-gnu/wine/wineserver

mkdir -p "$runtime_dir" "$log_dir"
cd /home/ubuntu/mt5-observer

find_terminal_pid() {
  local candidate command
  for candidate in /proc/[0-9]*; do
    [[ -r "$candidate/comm" && -r "$candidate/cmdline" ]] || continue
    [[ "$(<"$candidate/comm")" == "main" ]] || continue
    command=$(tr '\0' '\n' < "$candidate/cmdline")
    if grep -Fqx "$terminal_windows" <<<"$command" ||
      grep -Fqx "$terminal_linux" <<<"$command"
    then
      basename "$candidate"
      return 0
    fi
  done
  return 1
}

cleanup() {
  timeout 10s "$wineserver" -k >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

wine "$terminal_linux" /portable "/config:$startup_windows" \
  >>"$log_dir/mt5-launch.log" 2>&1 &

terminal_pid=""
for _ in $(seq 1 120); do
  terminal_pid=$(find_terminal_pid || true)
  [[ -n "$terminal_pid" ]] && break
  sleep 1
done

if [[ -z "$terminal_pid" ]]; then
  echo "MT5 terminal process did not appear within 120 seconds" >&2
  exit 1
fi

printf '%s\n' "$terminal_pid" > "$runtime_dir/mt5.pid"
while kill -0 "$terminal_pid" 2>/dev/null; do
  sleep 5
done

echo "MT5 terminal process exited" >&2
exit 1
