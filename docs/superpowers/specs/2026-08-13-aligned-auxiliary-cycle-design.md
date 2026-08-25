# Aligned Auxiliary Cycle Design

## Objective

Create one clean, evidence-eligible demo cycle whose start time and grid anchor are close enough to the target cycle for raw positions, lots, lifecycle transitions, and P/L to be meaningfully compared.

## Root Cause

The screenshots compare independently started cycles. The target cycle began at `2026-08-13T14:36:18.250Z` with anchor `4374.92`; the auxiliary cycle began at `2026-08-13T15:35:57Z` with anchor `4363.02`. The 3,578.75-second and 11.90-price offsets map the same market price to different grid levels. Editing lot or grid logic would not correct this.

## Safety Boundary

The controller must never send, modify, cancel, or close an order. It must not change EA inputs, credentials, or the target terminal. It may act only on `D:\MT5IndependentRegistration\terminal64.exe`, and only after the active auxiliary cycle has emitted `cycle_complete` without a subsequent `cycle_restart`.

## Architecture

`straddle_replica/cycle_alignment.py` contains pure evidence functions:

- determine whether the selected auxiliary cycle is complete and still inside its flat restart window;
- derive recent valid target complete-to-restart delays;
- select the first target completion after the auxiliary was frozen;
- calculate a predicted terminal launch time using the median target restart delay and a configured terminal startup lead.

`tools/align_local_auxiliary_cycle.py` is the guarded runtime controller:

1. Validate the dedicated terminal, startup configuration, active EX5 hash, bound demo account preset, telemetry, target archive, and health destination.
2. Poll auxiliary telemetry until the selected cycle emits `cycle_complete`.
3. Re-read after a short race guard. Abort if `cycle_restart` already occurred.
4. Find exactly one process whose executable path is the dedicated auxiliary terminal and close that process only.
5. Wait for the first target `cycle_complete` observed after the freeze.
6. Launch the dedicated auxiliary terminal shortly before the predicted target restart.
7. Observe the next target and auxiliary cycle starts, record their UTC/anchor deltas, and leave qualification decisions to the existing watcher.

## Failure Handling

- Missing files, hash drift, a non-demo/bound preset, ambiguous terminal processes, or a restart race fail closed before stopping anything.
- If no target completion arrives, the auxiliary stays safely flat and stopped while health remains fresh.
- If the target timing estimate is unavailable, launch immediately after the next observed target cycle start and classify the result as fallback alignment.
- A start delta outside the qualification tolerance is recorded, not hidden or promoted to a score.

## Verification

- Unit tests cover freeze readiness, restart-race rejection, delay filtering, and launch-time calculation.
- A controller contract test rejects order/trade APIs and requires exact executable-path guarding.
- Existing lifecycle/comparator tests remain green.
- The active EA hash remains `0C08884172447BE0C3606EF497DE314CC32DDB4DAAB309DAD3A6D371AF43DAF9`.
- Formal fidelity remains unclaimed until the aligned cycle completes and the existing ordinal comparator reports at least 95% strict lifecycle fidelity, 95% conditional logic fidelity, 95% conditional coverage, and zero deterministic mismatches.
