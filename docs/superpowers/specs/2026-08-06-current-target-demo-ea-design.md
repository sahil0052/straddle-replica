# Current Target Demo EA Design

## Goal

Produce a standalone, demo-only `StraddleReplica.ex5` that follows the latest
observed target behavior while preserving the existing grid and stop model.

## Evidence Baseline

The observer archive showed an unchanged deterministic deployment model:

- 30 buy and 30 sell stops in `B1,S1,...,B30,S30` order.
- Tick-rounded `anchor / 3000` spacing.
- Lots `0.01`, `0.06`, and `0.15` in ten-level tiers.
- Approximately 100 ms between initial pending orders.
- A two-stage stop model with activation near two steps and tightening near
  three steps.

Starting with the target cycle at `2026-08-06T10:47:49.119Z`, lifecycle timing
changed:

- Position closes occur approximately every 0.39-0.41 seconds.
- A new cycle begins approximately 1.87-2.26 seconds after the final close.
- Rearms can occur below 20 seconds, with observations consistent with a
  roughly two-second minimum plus market-validity gating.

## Design

Update `LATEST_30` lifecycle defaults to:

- `close_interval_seconds = 0`, allowing one close per 100 ms engine timer pass
  while broker latency controls the observed cadence.
- `restart_delay_ms = 2000`.
- `rearm_delay_seconds = 2`.

Keep all grid, lot, basket-target, cancellation, and stop-model settings
unchanged.

Harden restart handling:

- A normal cycle may not start while any owned order or position remains.
- During `CYCLE_RESTARTING`, remove residual owned orders first and then close
  residual owned positions.
- Preserve the original restart timestamp while cleaning residual exposure.
- Enter `CYCLE_IDLE` only when exposure is flat and the restart delay elapsed.

## Safety

- Preserve `RequireDemoAccount=true` as the compiled default.
- Preserve account-type validation that refuses real accounts.
- Do not add credentials or account-specific identifiers.
- The artifact remains BEST_EFFORT and is not a formally certified clone.

## Verification

- Add contract regressions before production edits and verify they fail.
- Update the Python profile mirror so analysis and MQL behavior agree.
- Run focused profile and MQL contract tests.
- Compile with MetaEditor and require zero errors and zero warnings.
- Copy the verified binary to
  `artifacts/StraddleReplica_LATEST_30_CURRENT_DEMO.ex5`.
