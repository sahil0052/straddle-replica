#!/usr/bin/env bash
set -euo pipefail

export HOME=/home/ubuntu
export DISPLAY=:99
export WINEPREFIX=/home/ubuntu/.wine-straddle-demo
export WINEDEBUG=-all
runtime_base="/run/user/$(id -u)"
mkdir -p -m 700 "$runtime_base"
export XDG_RUNTIME_DIR="$runtime_base"

terminal_linux=/home/ubuntu/mt5-straddle-demo/terminal64.exe
terminal_windows='Z:\home\ubuntu\mt5-straddle-demo\terminal64.exe'
terminal_directory_windows='Z:\home\ubuntu\mt5-straddle-demo'
startup_windows='Z:\home\ubuntu\straddle-demo\demo-startup.ini'
runtime_dir=/home/ubuntu/straddle-demo/runtime
log_dir=/home/ubuntu/straddle-demo/logs
wineserver=/usr/lib/x86_64-linux-gnu/wine/wineserver
transition_grace_seconds=30

mkdir -p "$runtime_dir" "$log_dir"
test -f "$terminal_linux"
test -f /home/ubuntu/straddle-demo/demo-startup.ini
cd /home/ubuntu/mt5-straddle-demo

find_related_mt5_pid() {
  local candidate command
  for candidate in /proc/[0-9]*; do
    [[ -r "$candidate/comm" && -r "$candidate/cmdline" ]] || continue
    [[ "$(<"$candidate/comm")" == "main" ]] || continue
    command=$(tr '\0' '\n' < "$candidate/cmdline")
    if grep -Fqx "$terminal_windows" <<<"$command" ||
      grep -Fqx "$terminal_linux" <<<"$command" ||
      {
        grep -Fqx "/update" <<<"$command" &&
          grep -Fqx "/path:$terminal_directory_windows" <<<"$command"
      }
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

related_pid=""
for _ in $(seq 1 120); do
  related_pid=$(find_related_mt5_pid || true)
  [[ -n "$related_pid" ]] && break
  sleep 1
done

if [[ -z "$related_pid" ]]; then
  echo "Demo MT5 terminal process did not appear within 120 seconds" >&2
  exit 1
fi

printf '%s\n' "$related_pid" >"$runtime_dir/mt5.pid"
last_seen=$(date +%s)
while true; do
  related_pid=$(find_related_mt5_pid || true)
  now=$(date +%s)
  if [[ -n "$related_pid" ]]; then
    printf '%s\n' "$related_pid" >"$runtime_dir/mt5.pid"
    last_seen=$now
  elif ((now - last_seen >= transition_grace_seconds)); then
    break
  fi
  sleep 1
done

echo "No related demo MT5 process remained after the transition grace period" >&2
exit 1
