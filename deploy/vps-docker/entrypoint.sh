#!/usr/bin/env bash
set -euo pipefail

umask 077

data_root=/data
terminal_root="$data_root/terminal"
runtime_root="$data_root/runtime"
log_root="$data_root/logs"

mkdir -p "$WINEPREFIX" "$runtime_root" "$log_root"

xvfb_pid=""
fluxbox_pid=""
vnc_pid=""
terminal_pid=""

cleanup() {
  if [[ -n "$terminal_pid" ]]; then
    kill "$terminal_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$vnc_pid" ]]; then
    kill "$vnc_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$fluxbox_pid" ]]; then
    kill "$fluxbox_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$xvfb_pid" ]]; then
    kill "$xvfb_pid" >/dev/null 2>&1 || true
  fi
  wineserver -k >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

Xvfb "$DISPLAY" -screen 0 1440x900x24 -nolisten tcp \
  >"$log_root/xvfb.log" 2>&1 &
xvfb_pid=$!

for _ in $(seq 1 100); do
  [[ -S /tmp/.X11-unix/X99 ]] && break
  sleep 0.1
done
[[ -S /tmp/.X11-unix/X99 ]]

fluxbox >"$log_root/fluxbox.log" 2>&1 &
fluxbox_pid=$!

# VNC is intentionally unauthenticated inside the isolated container network.
# Docker must publish it only on the VPS loopback interface for SSH tunneling.
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 \
  >"$log_root/x11vnc.log" 2>&1 &
vnc_pid=$!

if [[ ! -f "$WINEPREFIX/system.reg" ]]; then
  wineboot --init >"$log_root/wineboot.log" 2>&1
  wineserver -w
fi

if [[ "${MT5_START:-0}" != "1" ]]; then
  printf '%s\n' "prepared" >"$runtime_root/state"
  exec sleep infinity
fi

terminal="$terminal_root/terminal64.exe"
if [[ ! -f "$terminal" ]]; then
  echo "Missing terminal executable: $terminal" >&2
  exit 1
fi

args=("$terminal" "/portable")
if [[ -n "${MT5_CONFIG_WINDOWS:-}" ]]; then
  args+=("/config:${MT5_CONFIG_WINDOWS}")
fi

cd "$terminal_root"
while true; do
  wine "${args[@]}" >>"$log_root/terminal-launch.log" 2>&1 &
  terminal_pid=$!
  printf '%s\n' "$terminal_pid" >"$runtime_root/terminal-launcher.pid"
  printf '%s\n' "terminal-starting" >"$runtime_root/state"

  for _ in $(seq 1 120); do
    if pgrep -x main >/dev/null; then
      printf '%s\n' "terminal-running" >"$runtime_root/state"
      break
    fi
    if ! kill -0 "$terminal_pid" 2>/dev/null; then
      break
    fi
    sleep 1
  done

  set +e
  wait "$terminal_pid"
  terminal_status=$?
  set -e
  terminal_pid=""
  printf '%s\n' "terminal-exited-${terminal_status}" >"$runtime_root/state"

  # MT5 exits cleanly before spawning its updater. Keep Wine alive until the
  # updater finishes, then relaunch the portable terminal from the same data
  # directory. The service therefore survives both updates and normal exits.
  timeout 300s wineserver -w >>"$log_root/terminal-launch.log" 2>&1 || true
  sleep 2
done
