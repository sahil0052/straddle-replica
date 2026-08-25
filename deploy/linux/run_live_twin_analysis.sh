#!/usr/bin/env bash
set -euo pipefail

environment=/home/ubuntu/straddle-live-twin/shadow.env
test -s "$environment"
# shellcheck disable=SC1090
source "$environment"

: "${SHADOW_COMMON_ROOT:?SHADOW_COMMON_ROOT is required}"

TARGET_SOURCE=${TARGET_SOURCE:-probe}
package_root=${PACKAGE_ROOT:-/home/ubuntu/straddle-live-twin/package}
state_root=${STATE_ROOT:-/home/ubuntu/straddle-live-twin/state}
data_root=${DATA_ROOT:-/home/ubuntu/straddle-live-twin/data}
output_root=${OUTPUT_ROOT:-/home/ubuntu/straddle-live-twin/reports}
shadow_ea=${SHADOW_EA_PATH:-/home/ubuntu/mt5-straddle-shadow/MQL5/Experts/StraddleReplica/StraddleReplica.ex5}
shadow_profile=${SHADOW_PROFILE_PATH:-/home/ubuntu/mt5-straddle-shadow/MQL5/Profiles/Presets/latest_30_shadow.set}
shadow_startup=${SHADOW_STARTUP_PATH:-/home/ubuntu/straddle-live-twin/shadow-startup.ini}
target_events="$data_root/target-cycles.jsonl"
demo_telemetry=${DEMO_TELEMETRY_PATH:-"$SHADOW_COMMON_ROOT/StraddleReplicaV2_901018_XAUUSD.csv"}
demo_manifest=${DEMO_MANIFEST_PATH:-"$SHADOW_COMMON_ROOT/StraddleReplicaV2_901018_XAUUSD_manifest.csv"}
state_file="$state_root/certification.state"
coordinator_state="$state_root/coordinator.json"

manifest_value() {
  local manifest=$1
  local key=$2
  awk -F, -v key="$key" '
    $1 == key {
      gsub(/\r/, "", $2)
      gsub(/^"|"$/, "", $2)
      print $2
      exit
    }
  ' "$manifest"
}

mkdir -p "$state_root" "$output_root"

if [[ "$TARGET_SOURCE" == "observer" ]]; then
  : "${OBSERVER_ADAPTER_STATE:?OBSERVER_ADAPTER_STATE is required}"
  account_terms_report=${ACCOUNT_TERMS_REPORT:-"$output_root/commissioning/account-terms-901018-vs-901111.json"}
  commissioning_guard_report=${COMMISSIONING_GUARD_REPORT:-"$state_root/commissioning-guard.json"}
  best_effort_root="$output_root/best-effort"
  best_effort_state="$state_root/best-effort.state"
  status_output="$best_effort_root/status.json"

  mkdir -p "$best_effort_root"
  test -s "$account_terms_report"
  test -s "$OBSERVER_ADAPTER_STATE"
  test -s "$coordinator_state"
  test -s "$demo_manifest"

  tick_size=$(manifest_value "$demo_manifest" symbol_tick_size)
  tick_value=$(manifest_value "$demo_manifest" symbol_tick_value)
  test -n "$tick_size"
  test -n "$tick_value"

  fingerprint_files=(
    "$shadow_ea"
    "$shadow_profile"
    "$shadow_startup"
    "$environment"
    "$account_terms_report"
    "$package_root/straddle_replica/live_twin.py"
    "$package_root/straddle_replica/observer_adapter.py"
    "$package_root/straddle_replica/shadow_coordinator.py"
    "$package_root/tools/compare_live_twin.py"
    "$package_root/tools/report_best_effort_status.py"
  )
  guard_arguments=()
  if [[ -s "$commissioning_guard_report" ]]; then
    fingerprint_files+=("$commissioning_guard_report")
    guard_arguments+=(
      --operational-guard-report "$commissioning_guard_report"
    )
  fi
  for path in "${fingerprint_files[@]}"; do
    test -s "$path"
  done

  build_id=$(
    {
      for path in "${fingerprint_files[@]}"; do
        sha256sum "$path"
      done
    } | sha256sum | cut -d' ' -f1
  )

  stored_build=""
  comparison_started=""
  if [[ -s "$best_effort_state" ]]; then
    read -r stored_build comparison_started <"$best_effort_state" || true
  fi
  if [[ "$stored_build" != "$build_id" || -z "$comparison_started" ]]; then
    comparison_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    temporary_state="$best_effort_state.tmp"
    printf '%s %s\n' "$build_id" "$comparison_started" >"$temporary_state"
    mv -f "$temporary_state" "$best_effort_state"
  fi

  run_token=$(printf '%s' "$comparison_started" | tr -cd '0-9TZ')
  run_root="$best_effort_root/runs/${build_id:0:16}-$run_token"
  cycle_dir="$run_root/cycles"
  mkdir -p "$cycle_dir"

  if [[ -s "$target_events" && -s "$demo_telemetry" ]]; then
    comparison_status=0
    python3 \
      "$package_root/tools/compare_live_twin.py" \
      --target-events "$target_events" \
      --demo-telemetry "$demo_telemetry" \
      --tick-size "$tick_size" \
      --time-tolerance-seconds 1 \
      --tick-value-per-lot "$tick_value" \
      --build-id "$build_id" \
      --certification-started-utc "$comparison_started" \
      --output-dir "$cycle_dir" || comparison_status=$?
    if ((comparison_status > 2)); then
      exit "$comparison_status"
    fi
  fi

  python3 \
    "$package_root/tools/report_best_effort_status.py" \
    --account-terms "$account_terms_report" \
    --adapter-state "$OBSERVER_ADAPTER_STATE" \
    --coordinator-state "$coordinator_state" \
    --comparisons-dir "$cycle_dir" \
    --source-mode observer \
    "${guard_arguments[@]}" \
    --output "$status_output"

  printf '%s\n' "$status_output"
  exit 0
fi

: "${TARGET_PROBE_ROOT:?TARGET_PROBE_ROOT is required}"
test -s "$target_events"
test -s "$demo_telemetry"
test -s "$demo_manifest"
test -s "$coordinator_state"

read -r current_skipped current_sequence_gaps current_session_restarts < <(
  python3 -c \
    'import json,sys; state=json.load(open(sys.argv[1], encoding="utf-8")); print(int(state.get("skipped_cycles", 0)), int(state.get("sequence_gaps", 0)), int(state.get("session_restarts", 0)))' \
    "$coordinator_state"
)

fingerprint_files=(
  "$shadow_ea"
  "$shadow_profile"
  "$shadow_startup"
  "$environment"
  "$demo_manifest"
  "$package_root/mql5/StraddleTargetProbe.ex5"
  "$package_root/straddle_replica/account_terms.py"
  "$package_root/straddle_replica/live_twin.py"
  "$package_root/straddle_replica/live_twin_gate.py"
  "$package_root/straddle_replica/probe_health.py"
  "$package_root/straddle_replica/shadow_coordinator.py"
  "$package_root/tools/analyze_probe_health.py"
  "$package_root/tools/compare_account_terms.py"
  "$package_root/tools/compare_live_twin.py"
  "$package_root/tools/evaluate_live_twin_gate.py"
)
for path in "${fingerprint_files[@]}"; do
  test -s "$path"
done

build_id=$(
  {
    printf 'SHADOW_ACTIVE=%s\n' "${SHADOW_ACTIVE:-0}"
    for path in "${fingerprint_files[@]}"; do
      sha256sum "$path"
    done
  } | sha256sum | cut -d' ' -f1
)

stored_build=""
certification_started=""
baseline_skipped=$current_skipped
baseline_sequence_gaps=$current_sequence_gaps
baseline_session_restarts=$current_session_restarts
if [[ -s "$state_file" ]]; then
  read -r \
    stored_build \
    certification_started \
    baseline_skipped \
    baseline_sequence_gaps \
    baseline_session_restarts <"$state_file" || true
fi
baseline_skipped=${baseline_skipped:-$current_skipped}
baseline_sequence_gaps=${baseline_sequence_gaps:-$current_sequence_gaps}
baseline_session_restarts=${baseline_session_restarts:-$current_session_restarts}
if [[ "$stored_build" != "$build_id" || -z "$certification_started" ]]; then
  certification_started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  baseline_skipped=$current_skipped
  baseline_sequence_gaps=$current_sequence_gaps
  baseline_session_restarts=$current_session_restarts
  temporary_state="$state_file.tmp"
  printf '%s %s %s %s %s\n' \
    "$build_id" \
    "$certification_started" \
    "$baseline_skipped" \
    "$baseline_sequence_gaps" \
    "$baseline_session_restarts" >"$temporary_state"
  mv -f "$temporary_state" "$state_file"
fi

operational_guard_failures=$(( \
  current_skipped - baseline_skipped + \
  current_sequence_gaps - baseline_sequence_gaps + \
  current_session_restarts - baseline_session_restarts \
))
if ((operational_guard_failures < 0)); then
  operational_guard_failures=1
fi

run_token=$(printf '%s' "$certification_started" | tr -cd '0-9TZ')
run_root="$output_root/runs/${build_id:0:16}-$run_token"
cycle_dir="$run_root/cycles"
mkdir -p "$cycle_dir"

target_manifest=$(
  find "$TARGET_PROBE_ROOT" -type f -name manifest.csv \
    -printf '%T@ %p\n' |
    sort -n |
    tail -1 |
    cut -d' ' -f2-
)
test -n "$target_manifest"
test -s "$target_manifest"

tick_size=$(manifest_value "$demo_manifest" symbol_tick_size)
tick_value=$(manifest_value "$demo_manifest" symbol_tick_value)
expected_probe_build_id=${EXPECTED_PROBE_BUILD_ID:-latest30-live-twin-v1}
actual_probe_build_id=$(manifest_value "$target_manifest" probe_build_id)
test -n "$tick_size"
test -n "$tick_value"
if [[ "$actual_probe_build_id" != "$expected_probe_build_id" ]]; then
  echo "Target probe build mismatch: expected=$expected_probe_build_id actual=$actual_probe_build_id" >&2
  exit 1
fi

terms_output="$run_root/account-terms.json"
terms_status=0
python3 \
  "$package_root/tools/compare_account_terms.py" \
  --target "$target_manifest" \
  --demo "$demo_manifest" \
  --output "$terms_output" || terms_status=$?
if ((terms_status > 1)); then
  exit "$terms_status"
fi

comparison_status=0
python3 \
  "$package_root/tools/compare_live_twin.py" \
  --target-events "$target_events" \
  --demo-telemetry "$demo_telemetry" \
  --tick-size "$tick_size" \
  --time-tolerance-seconds 1 \
  --tick-value-per-lot "$tick_value" \
  --build-id "$build_id" \
  --certification-started-utc "$certification_started" \
  --output-dir "$cycle_dir" || comparison_status=$?
if ((comparison_status > 2)); then
  exit "$comparison_status"
fi

health_output="$run_root/probe-health.json"
health_status=0
python3 \
  "$package_root/tools/analyze_probe_health.py" \
  --probe-root "$TARGET_PROBE_ROOT" \
  --certification-started-utc "$certification_started" \
  --output "$health_output" || health_status=$?
if ((health_status > 1)); then
  exit "$health_status"
fi

comparison_arguments=()
while IFS= read -r comparison; do
  comparison_arguments+=(--comparison "$comparison")
done < <(find "$cycle_dir" -maxdepth 1 -type f -name '*.json' | sort)

gate_output="$run_root/gate.json"
gate_status=0
python3 \
  "$package_root/tools/evaluate_live_twin_gate.py" \
  "${comparison_arguments[@]}" \
  --probe-health "$health_output" \
  --account-terms-report "$terms_output" \
  --operational-guard-failures "$operational_guard_failures" \
  --certification-started-utc "$certification_started" \
  --output "$gate_output" || gate_status=$?
if ((gate_status > 1)); then
  exit "$gate_status"
fi

reset_required=$(
  python3 -c \
    'import json,sys; print("1" if json.load(open(sys.argv[1], encoding="utf-8"))["reset_required"] else "0")' \
    "$gate_output"
)
if [[ "$reset_required" == "1" ]]; then
  next_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  temporary_state="$state_file.tmp"
  printf '%s %s %s %s %s\n' \
    "$build_id" \
    "$next_start" \
    "$current_skipped" \
    "$current_sequence_gaps" \
    "$current_session_restarts" >"$temporary_state"
  mv -f "$temporary_state" "$state_file"
fi

printf '%s\n' "$gate_output"
