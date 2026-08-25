#!/usr/bin/env bash
set -euo pipefail

environment=/home/ubuntu/straddle-live-twin/shadow.env
test -s "$environment"
# shellcheck disable=SC1090
source "$environment"

: "${SHADOW_COMMON_ROOT:?SHADOW_COMMON_ROOT is required}"

state_root=${STATE_ROOT:-/home/ubuntu/straddle-live-twin/state}
data_root=${DATA_ROOT:-/home/ubuntu/straddle-live-twin/data}
SHADOW_ACTIVE=${SHADOW_ACTIVE:-0}
TARGET_SOURCE=${TARGET_SOURCE:-probe}
mkdir -p "$state_root" "$data_root" "$SHADOW_COMMON_ROOT/StraddleShadow"

arguments=(
  --command-path "$SHADOW_COMMON_ROOT/StraddleShadow/command.csv"
  --ack-path "$SHADOW_COMMON_ROOT/StraddleShadow/ack.csv"
  --state-path "$state_root/coordinator.json"
  --target-archive-path "$data_root/target-cycles.jsonl"
  --command-ttl-ms 2000
  --pair-window-ms 1000
  --poll-ms 100
)
case "$TARGET_SOURCE" in
  observer)
    : "${TARGET_OBSERVER_ROOT:?TARGET_OBSERVER_ROOT is required}"
    : "${OBSERVER_ADAPTER_STATE:?OBSERVER_ADAPTER_STATE is required}"
    arguments+=(
      --target-observer-root "$TARGET_OBSERVER_ROOT"
      --observer-state-path "$OBSERVER_ADAPTER_STATE"
      --heartbeat-max-age-seconds 5
    )
    ;;
  probe)
    : "${TARGET_PROBE_ROOT:?TARGET_PROBE_ROOT is required}"
    arguments+=(--target-probe-root "$TARGET_PROBE_ROOT")
    ;;
  *)
    echo "Unsupported TARGET_SOURCE: $TARGET_SOURCE" >&2
    exit 2
    ;;
esac
if [[ "$SHADOW_ACTIVE" == "1" ]]; then
  arguments+=(--active)
fi

exec python3 \
  /home/ubuntu/straddle-live-twin/package/tools/run_shadow_coordinator.py \
  "${arguments[@]}"
