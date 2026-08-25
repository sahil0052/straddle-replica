# Exact-Real StraddleReplica Design

## Goal

Produce a dedicated real-account MT5 build that preserves the current
`LATEST_30` target-replica behavior without optional safety interventions.
The deliverable is intended for manual installation only and will not be
deployed or attached to an account automatically.

## Truth Boundary

The build will be named and documented as `REAL_EXACT`, meaning that it keeps
the closest evidence-backed strategy settings unchanged. It will not be
described as a proven 100% clone because:

- the original EA source and outgoing trade-request payloads are unavailable;
- the observer sees accepted broker events rather than every originating
  request;
- zero complete target/replica paired cycles have passed the formal live-twin
  gate;
- fills, slippage, spread, stops level, swap, leverage, and order capacity are
  broker-dependent.

The current evidence-based overall behavioral estimate is approximately 92%.
This is an engineering estimate, not a return or execution guarantee.

## Similarity Evidence

The August 8, 2026 cumulative target analysis provides:

- 46 of 46 historical deployments with exact `B1,S1,...,B30,S30` sequence;
- 46 of 46 deployments with zero grid-geometry error;
- 46 of 46 deployment steps matching tick-rounded `anchor / 3000`;
- exact `0.01 / 0.06 / 0.15` tiers in all 44 fully captured lot deployments;
  the other two capture bursts were incomplete rather than contradictory;
- 14,310 observed stop changes across 1,010 positions;
- 95.36% favorable-move holdout accuracy for the inferred stop phase;
- 97.14% accuracy at the inferred three-step phase boundary;
- 95.96% holdout accuracy from the previous stop-distance band;
- 235 matched rearm observations, including direct evidence for the current
  one-second gate;
- 48 observed restart-delay measurements.

Accordingly:

- deterministic deployment structure: approximately 100% observed match;
- inferred stop-management behavior: approximately 95-97%;
- basket timing, simultaneous rearm ordering, and broker execution: not fully
  resolved;
- combined practical estimate: approximately 92% behavioral similarity.

## Build Architecture

Use the existing strategy engine and profile catalog unchanged.

Create a thin dedicated MQL5 entry point for the real build. Shared inputs and
event-handler wiring will be extracted into one include so the demo and real
executables cannot drift in strategy logic.

The wrappers will differ only in the default account gate:

- `StraddleReplica.mq5`: `RequireDemoAccount=true`;
- `StraddleReplicaReal.mq5`: `RequireDemoAccount=false`.

Both executables will use the same:

- `CStraddleEngine`;
- `LATEST_30` profile;
- lot tiers;
- grid, stop, basket, cancellation, close, rearm, and restart rules;
- telemetry;
- hedging-account validation;
- broker order-limit validation.

## Real-Exact Preset

Create `LATEST_30_REAL_EXACT.set` with:

- `Profile=LATEST_30`;
- `TradeSymbol=XAUUSD`;
- `ReplicaMode=true`;
- `RequireDemoAccount=false`;
- `ExpectedAccountLogin=0`;
- `SafetyEnabled=false`;
- `TelemetryEnabled=true`;
- all target-replica timing and profile values inherited from the compiled
  `LATEST_30` catalog.

No equity-loss, daily-loss, gross-lot, or spread protection will alter the
strategy in this preset.

## Runtime Validation

Initialization will still fail when:

- the account is not MT5 hedging mode;
- the broker reports a pending-order limit below 60;
- the selected symbol cannot be loaded;
- symbol tick size or point configuration is invalid;
- the selected profile is invalid.

These checks are execution prerequisites and do not change target trading
decisions after initialization.

## Deliverables

- `StraddleReplica_REAL_EXACT.ex5`;
- `LATEST_30_REAL_EXACT.set`;
- matching source files;
- installation and risk README;
- SHA-256 checksums;
- a ZIP package for manual installation.

The existing demo-only package remains unchanged.

## Verification

Before handoff:

1. Add tests proving the demo executable defaults to demo-only and the real
   executable defaults to real-account capable.
2. Prove both wrappers use the same engine and profile implementation.
3. Verify the real preset disables the demo gate and optional safety while
   retaining telemetry.
4. Compile both executables with zero errors and zero warnings.
5. Run the focused MQL/profile/package tests.
6. Run all repository tests that do not depend on the unavailable
   `ReportHistory-last2days.xlsx` fixture.
7. Verify packaged source and executable hashes.
8. Scan the package for credentials and secrets.

No real order will be sent as part of implementation or verification.
