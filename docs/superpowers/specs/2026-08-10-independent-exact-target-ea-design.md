# Independent Exact-Target EA Design

## Objective

Build one independent MT5 EA whose deterministic trading decisions match the
observed target EA as closely as evidence permits. The same source and strategy
profile will be validated on the dedicated MetaQuotes demo before a
real-account candidate is produced.

This is not a trade copier. After a clean comparison-cycle start, the local EA
must make every grid, fill-handling, stop, rearm, basket-close, and restart
decision from its own account state and broker prices.

## Selected approach

Use an evidence-first independent twin:

1. Observe the target through an investor/read-only terminal.
2. Align one fresh demo cycle to the target anchor and step solely to create a
   valid comparison boundary.
3. Let both EAs trade independently after deployment.
4. Compare deterministic decisions separately from broker execution.
5. Change the EA only when paired evidence proves a deterministic mismatch.

Rejected approaches:

- Continuous trade copying, because it would not reproduce the target logic.
- Guess-based tuning from unsynchronized cycles, because independent anchors
  make those profits and lifecycle events unpairable.
- Deploying to real before the demo gate, because it would expose money to
  unverified behavior.

## Safety boundary

- The target account remains investor/read-only at all times.
- The target collector contains no trading operation.
- All development deployment and cycle reset actions are limited to demo login
  `5054170246`, server `MetaQuotes-Demo`, symbol `XAUUSD`, and magic `901018`.
- The reset path may cancel or close only positions and orders matching both
  `XAUUSD` and magic `901018`.
- Any stale heartbeat, changed target session, account mismatch, rejected
  command, sequence gap, or nonzero dropped-event count fails closed.
- No code is installed on a real account until the validation gate passes.

## Components

### Target evidence collector

Exactly one Python process owns the MetaTrader5 API connection to the target
observer terminal. Other monitors read the collector and MQL observer files;
they do not initialize another Python MT5 connection to that terminal.

The collector verifies:

- login `901018`;
- server `AchieverGlobalMarkets-Server`;
- `trade_allowed=false`;
- connected terminal;
- fresh heartbeat;
- zero dropped transactions.

It persists snapshots, orders, deals, ticks, and health state. A Windows
scheduled task supervises it and restarts it after process failure.

### Independent local EA

The EA retains the confirmed `LATEST_30` behavior:

- 30 buy-stop and 30 sell-stop levels;
- alternating `STR B1`, `STR S1` through level 30 deployment;
- anchor-derived spacing;
- confirmed lot tiers;
- no take profit;
- two-stage trailing behavior;
- newest-first, one-stop-update-per-100-ms scheduling;
- one-second rearm eligibility;
- fixed `$30` basket baseline;
- pending cancellation before residual closes;
- independent cycle restart.

The EA gains a native, guarded way to adopt an already-running local cycle into
shadow/wait mode. This replaces the temporary seeded `START` workaround.
Adoption does not change existing orders or positions.

### One-time cycle synchronizer

The synchronizer exists only to establish a valid paired comparison cycle. It
does not mirror target trades after the cycle begins.

Flow:

1. Seed the currently active target cycle without emitting commands.
2. Detect the target's first basket-cancellation event.
3. Send one expiring `RESET` command to the local demo.
4. Wait for a sequence-matched `FLAT` acknowledgement.
5. Observe a fresh accepted target `STR B1` and `STR S1`.
6. Derive target anchor and step from those two prices.
7. Send one expiring `START` command.
8. Confirm local `STARTED`, anchor, step, profile, and full 60-order deployment.
9. Issue no trade-control commands during the paired cycle.

If local reset is not complete before the fresh target start pair, the cycle is
marked missed. The synchronizer waits for the following target cycle rather
than starting late.

### Lifecycle comparator

The comparator pairs events by cycle, comment, side, level, volume, and order.
It checks:

- initial order sequence and price geometry;
- fills and actual entry prices;
- stop-selection order and requested stop values;
- stop exits;
- rearm eligibility, order, and timing;
- pending cancellation order;
- residual close order;
- basket result and restart boundary.

Deterministic EA decisions must match exactly. Broker fill price, slippage,
spread, commission, swap, server execution serialization, and resulting P/L
are reported separately and cannot be guaranteed identical across Achiever and
MetaQuotes.

## Failure handling

- Collector connection loss: record unhealthy state, stop advancing evidence,
  and restart the collector without writing a trade command.
- Stale target heartbeat: synchronizer waits and retries; it does not exit
  permanently or reuse stale events.
- Target observer session change: discard the partial pairing and wait for a
  new clean cycle.
- Local command rejection or stale acknowledgement: stop synchronization and
  require a new target cycle.
- Coordinator process failure: scheduled-task supervision restarts it from
  persisted cursors without replaying an already consumed event.
- Missing exact evidence: retain the current rule and classify it as unresolved
  instead of guessing.

## Validation gate

The demo candidate is not promoted until all of the following hold:

- at least ten complete, non-overlapping paired cycles;
- at least 48 market-open hours;
- exact deterministic deployment and lifecycle decisions;
- zero sequence gaps, duplicate events, dropped events, stale command use, or
  observer session corruption;
- no account, symbol, profile, magic, or code fingerprint change during the
  run.

Any deterministic mismatch resets the paired-cycle count after the corrected
build is deployed.

## Real-account candidate

After the gate passes, build the real candidate from the same reviewed source
and `LATEST_30` profile. Only account-mode and expected-login configuration may
change. Trading formulas, cadence, comments, lot tiers, basket logic, and
lifecycle behavior must remain identical to the validated demo build.

The real candidate can reproduce EA decisions, but no software can force two
different brokers to produce identical fills, execution timing, or profit.
