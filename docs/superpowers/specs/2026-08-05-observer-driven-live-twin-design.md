# Observer-Driven Live Twin: 24-Hour Best-Effort Design

## Objective

Use the existing read-only target observer to synchronize Achiever demo account
`901111` with target account `901018` as closely as the available evidence
allows during the next 24 hours.

This mode is explicitly best-effort. It can validate EA decisions and lifecycle
behavior, but it cannot certify literal outgoing-request parity because the
observer is not the terminal that originates the target EA's requests.

## Constraints

- The target account remains read-only and receives no commands.
- Only Achiever demo account `901111` may be traded or reset.
- The target is already mid-cycle, so the demo must not start from the current
  partial lifecycle.
- The demo differs from the target in leverage and swap mode. These broker
  mismatches remain visible in every report and cannot be reported as EA-logic
  matches.
- Existing demo-account, expected-login, stale-command and flat-account guards
  remain mandatory.

## Architecture

### Observer Event Adapter

Add an incremental adapter that reads the current target Python observer
session:

- `snapshots-*.jsonl`
- `history-orders-*.jsonl`
- `history-deals-*.jsonl`
- `heartbeat.json`

The adapter persists its cursor and current-cycle state. It emits normalized
events compatible with `ShadowCoordinator` and the lifecycle comparator.

Events inferred from accepted broker state are marked with
`source=observer_inferred`; they are never represented as original request
events.

The adapter will:

1. Detect a new target cycle from a previously unseen accepted `STR B1/S1`
   pair.
2. Derive the exact anchor and step from their accepted pending prices.
3. Emit accepted pending events for every newly observed `STR` order.
4. Emit fills and exits from target deal history using broker timestamps,
   comments, prices, volume, commission, swap and profit.
5. Detect cancellation/closure transitions from history plus state changes.
6. Deduplicate records across polling, file rotation and service restarts.
7. Fail closed on stale heartbeat, malformed data, sequence regression or an
   ambiguous cycle boundary.

### Coordinator Behavior

The current target cycle is observation-only. Its state seeds the adapter but
cannot produce a `START` command.

At the next clean target cycle:

1. The target must transition through closure/flat evidence.
2. The demo must acknowledge `FLAT`.
3. A fresh accepted `B1/S1` pair must arrive inside the configured freshness
   window.
4. The coordinator writes one expiring `START` command containing the observed
   cycle ID, anchor and step.
5. `StraddleReplica` then runs independently; downstream target events are
   evidence for comparison, not copy-trading instructions.

If any requirement fails, that cycle is skipped rather than started late.

### Comparison and Classification

Use lifecycle pairing by cycle ID, semantic slot and occurrence.

Reports separate:

- `EA_LOGIC`: sequence, lots, prices, stops, rearms, cancellations, closes and
  restart decisions.
- `EXECUTION`: fill price/time, partial fills and retcodes available from the
  observer.
- `BROKER_TERMS`: leverage, swap mode, commission and contract differences.
- `CAPTURE_LIMIT`: values unavailable without the originating target terminal.

An EA-logic match may be reported as best-effort even when broker terms differ,
but the formal 100% certification status remains closed.

## Safety and Recovery

- No mid-cycle demo start.
- No command when the target heartbeat is stale.
- No command unless the demo account is flat and login `901111` is confirmed.
- Atomic command and state-file replacement.
- Persistent deduplication cursor across restarts.
- Observation-only commissioning before active mode.
- Existing target observer services are never restarted by the adapter.
- Coordinator or adapter failure leaves the demo EA waiting without a new
  cycle command.

## Verification

Focused tests must cover:

- Current-cycle seeding produces no `START`.
- A later fresh `B1/S1` pair produces exactly one `START`.
- Duplicate snapshots/history records do not duplicate events.
- File rotation and process restart preserve cursors.
- Stale heartbeat, ambiguous transitions and malformed rows fail closed.
- Fill, stop, cancellation and close inference uses broker timestamps.
- Demo-not-flat and stale-ack conditions skip the cycle.

Deployment sequence:

1. Replay the adapter against captured historical sessions.
2. Run it live in observation-only mode against the current cycle.
3. Confirm freshness, cursor stability and zero target-side writes.
4. Enable demo command output before the next clean cycle.
5. Run continuous paired comparison for the remaining 24-hour window.

## Deliverables

- Observer event adapter and CLI.
- Unit and integration tests.
- Systemd service/environment configuration.
- Persistent observer event archive and state.
- Live paired-cycle comparison reports.
- A final best-effort similarity report with all broker and capture limits
  stated explicitly.
