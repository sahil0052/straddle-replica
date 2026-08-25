# Target EA Independent-Fidelity Design

Date: 2026-08-11

## Objective

Build the closest evidence-supported independent reconstruction of the target
MT5 EA. The candidate must calculate and execute its own decisions from its own
account state and market prices. It must not copy target trades, positions, or
order actions after a controlled comparison cycle begins.

The work follows a repeated loop:

`observe -> normalize -> compare -> diagnose -> test -> fix -> replay -> demo`

The goal is to improve measured lifecycle fidelity, not to claim identical
profit across different brokers. Exact profit parity cannot be guaranteed
because spread, fills, slippage, commission, swap, server timing, order limits,
and stop execution are broker-controlled.

## Measured starting point

The live read-only comparison captured on 2026-08-11 at 06:45 UTC showed:

| Account | Realized for the day | Floating P/L | Estimated net for the day |
| --- | ---: | ---: | ---: |
| Target | +$409.67 | -$20.97 | +$388.70 |
| Existing VPS replica | +$2,532.85 | -$12,722.98 | -$10,190.13 |

The existing VPS replica had 37 positions, 6 pending orders, and 3.21 gross
lots. The target had 7 positions, 50 pending orders, and 0.07 gross lots.

The current evidence establishes:

- initial 30-by-30 grid geometry, comments, spacing, and lot tiers are close;
- the existing replica and target were running unrelated cycle anchors;
- the target restarted about seven times while the replica remained in one
  cycle;
- the replica cycle never reached its configured $30 basket target;
- unprotected losing inventory accumulated because stops are added only after
  favorable movement;
- the deployed VPS preset disabled all optional safety controls;
- duplicate processing of two exit deals overstated internal cycle realized
  profit by $8.74;
- the best preserved broad lifecycle comparison matched 663 of 1,200 target
  events, approximately 55%, not 92%.

The 92% figure is retired. Future closeness claims must come from the canonical
paired-cycle score defined in this document.

The supporting root-cause evidence is preserved in
`artifacts/analysis/2026-08-11-target-vs-vps-root-cause.md`.

## Scope and non-goals

### In scope

- restore reliable read-only target evidence capture;
- create a fresh isolated demo candidate;
- build a canonical event stream for target and candidate activity;
- identify deterministic EA mismatches separately from broker differences;
- fix one evidence-proven mismatch at a time using tests first;
- replay every change against preserved evidence;
- forward-test at least 20 complete paired cycles;
- produce separate `FIDELITY` and `REAL_SAFE` presets;
- package the reviewed EX5, presets, hashes, and measured fidelity report.

### Out of scope

- trade copying or mirroring;
- changing, closing, canceling, or resetting the existing VPS replica trades;
- trading through the target investor account;
- modifying unrelated VPS containers or terminals;
- promising identical trades or profit on brokers with different execution;
- automatically deploying or enabling the EA on a real account.

## Selected approach

Use an evidence-driven independent twin on a new demo account.

1. Observe the target through strictly read-only sources.
2. Capture the candidate's requests, accepted transactions, state, and
   account terms.
3. Normalize both streams into the same lifecycle event model.
4. Establish clean paired-cycle boundaries for controlled comparisons.
5. Compare deterministic decisions and broker execution separately.
6. Convert the first proven mismatch into a failing regression test.
7. Make the smallest source correction.
8. Replay all preserved cycles and then restart the live qualification count.

This approach is selected because it can improve the underlying strategy logic
without turning the system into a copier.

Rejected alternatives:

- **Unsynchronized profit comparison:** rejected because unrelated anchors and
  inventory paths make the result non-diagnostic.
- **Continuous target mirroring:** rejected because it copies actions instead
  of reconstructing logic.
- **Guess-based parameter tuning:** rejected because it can overfit one market
  path and worsen unseen cycles.
- **Immediate real-account deployment:** rejected because the current measured
  lifecycle result and drawdown are unacceptable.

## Isolation and account boundaries

### Existing VPS replica

The current VPS container and account are evidence only. This project must not:

- send, modify, cancel, or close any of its orders;
- change its inputs or Algo Trading setting;
- restart its terminal, container, or VPS;
- reuse its mutable data directory for the new candidate.

### Fresh candidate

The candidate runs in a separate terminal or container with:

- a unique terminal data directory or Wine prefix;
- a dedicated demo login;
- a dedicated telemetry directory;
- a loopback-only remote viewing port if remote viewing is enabled;
- an explicit expected account login;
- `XAUUSD`, hedging mode, and magic `901018`;
- no access to target trading credentials.

The target investor login is used only by the read-only observer. It is never
embedded in the candidate preset as the account allowed to trade.

## Evidence architecture

### Target capture

Exactly one Python MetaTrader5 connection may own the target observer terminal
at a time. Other analysis processes read persisted files only.

Every capture session must verify:

- expected target login and server;
- `trade_allowed=false`;
- connected terminal and fresh Python/MQL heartbeats;
- zero dropped transactions;
- monotonic sequence numbers;
- a stable observer session identifier;
- target symbol and account-term manifests.

There are two evidence grades:

- **FORMAL:** a passive same-terminal probe captures originating target
  requests and results, with matching candidate broker/account terms.
- **BEST_EFFORT:** the investor observer captures accepted broker state,
  history, and transactions but cannot see every originating request.

If same-terminal request evidence is unavailable, reports must remain
`BEST_EFFORT`; the project cannot certify literal request-for-request identity.

### Candidate capture

The candidate EA records:

- cycle start, anchor, step, profile, and build fingerprint;
- pending-order requests and results;
- fills and actual position entry prices;
- stop requests and accepted stop changes;
- stop exits and ordinary close fills;
- rearm eligibility and rearm requests;
- basket trigger inputs and decision;
- cancellation and close order;
- cycle completion and restart;
- account, symbol, and runtime terms;
- commission, swap, fee, and realized/floating profit components.

Telemetry writes must be append-safe and must not alter trading decisions.

## Canonical lifecycle model

Both sources are converted into canonical events with these fields:

- source, capture session, cycle ID, source sequence, and event ID;
- UTC time and original server time;
- event kind and cycle state;
- comment, side, grid level, and occurrence number;
- volume, requested price, accepted price, SL, and TP;
- order, position, deal, request, and result identifiers;
- retcode and rejection reason;
- commission, swap, fee, realized profit, and floating profit;
- anchor, step, symbol tick size, and relevant account terms;
- evidence grade and capture-quality flags.

Canonical event kinds include:

- `cycle_start`
- `initial_pending_request`
- `initial_pending_accept`
- `fill`
- `stop_request`
- `stop_accept`
- `stop_exit`
- `rearm_eligible`
- `rearm_request`
- `rearm_accept`
- `basket_trigger`
- `cancel_request`
- `cancel_accept`
- `close_request`
- `close_fill`
- `cycle_complete`
- `cycle_restart`
- `capture_invalid`

### Event identity and deduplication

Every deal must be processed idempotently. Deal accounting and telemetry use
the unique broker deal ticket as the primary identity. Request and order
events use their broker identifiers plus event type.

The EA must maintain a cycle deal ledger that:

- ignores a previously processed deal ticket;
- survives terminal restart;
- rebuilds or verifies cycle realized profit from unique history deals;
- filters by symbol and magic;
- records commission, swap, fee, and profit exactly once;
- does not use capture-row duplication as trading input.

The first implementation change must address this confirmed defect before any
strategy calibration.

## Cycle boundaries and pairing

A target cycle is valid only when capture contains:

1. a completed prior-cycle cancellation/close boundary or an observed flat
   initialization;
2. a fresh complete initial deployment;
3. one unique `STR B1` through `STR B30` and `STR S1` through `STR S30`;
4. a stable derived anchor and step;
5. a complete close and restart boundary.

For a controlled paired experiment, the fresh demo candidate may receive one
cycle-start command containing the observed target anchor and step. This is
permitted only to create the same initial test condition. After start:

- the target stream cannot issue fill, stop, rearm, cancel, or close commands;
- the candidate uses only its own positions, fills, prices, and account state;
- any later target-derived trade command invalidates the cycle;
- a missed or late start is marked `UNPAIRED` and is not scored.

Normal independent mode must derive its own anchor from its own broker price.
The controlled seeded mode is a comparison instrument, not the production
strategy.

## Comparator and mismatch classification

The comparator pairs events by cycle, event kind, comment, side, level, and
occurrence. It produces four outcomes:

- `PASS`: all required deterministic events match and evidence is complete;
- `FAIL`: a deterministic mismatch is proven;
- `INVALID`: capture, account, build, or cycle integrity failed;
- `UNPAIRED`: the cycles did not share a valid start boundary.

### Deterministic EA mismatches

These are candidates for source correction:

- wrong grid count, order, comment, side, level, lot, anchor, or step;
- wrong fill-to-level ownership;
- wrong stop eligibility, ticket selection, formula, order, or cadence;
- wrong rearm eligibility, ordering, or delay;
- wrong basket net components, threshold, check cadence, or trigger state;
- wrong cancellation or residual-close order;
- wrong restart delay or anchor derivation;
- duplicate or missing internal deal accounting.

### Broker and environment differences

These are reported but not automatically treated as logic defects:

- spread and stop/freeze distance;
- slippage and actual fill price;
- commission, swap, fee, and tick value;
- order limits and filling mode;
- network and server timing;
- broker-side serialization of positions sharing a stop;
- downstream path changes caused by an earlier execution difference.

The report must preserve causality. Once a broker execution difference changes
candidate state, later dependent events are marked `EXECUTION_DIVERGED` unless
an independent deterministic defect is also proven.

## Fidelity measurement

No single percentage is reported without its calculation and evidence grade.

For valid paired cycles:

- an exact deterministic event match requires the same event kind, comment,
  side, level, occurrence, lot, normalized requested price, SL, TP, and
  relative decision order;
- `precision = exact matches / candidate deterministic events`;
- `recall = exact matches / target deterministic events`;
- `strict lifecycle fidelity = 2 * precision * recall /
  (precision + recall)`;
- cycle pass rate, field-level accuracy, evidence coverage, and execution
  divergence are reported separately.

The strict score includes all observed lifecycle consequences and is the
user-facing closeness percentage. A second `conditional logic fidelity` score
may be reported only for events whose input state and broker preconditions are
equivalent. Events after a proven broker-caused state divergence are excluded
from the conditional score, identified explicitly, and included in a separate
coverage percentage. This diagnostic score must never replace or inflate the
strict score.

Timing is a separate measurement and is not hidden inside the logic score.
Formal reports may apply a stated request-time tolerance. Best-effort observer
reports identify accepted-event timing only.

The current broad historical baseline is approximately 55% lifecycle event
alignment. It remains the baseline until a reproducible comparator run replaces
it.

## Diagnosis and correction loop

Each iteration is deliberately narrow:

1. Select the earliest causal deterministic mismatch in a valid cycle.
2. State one falsifiable hypothesis.
3. Add a failing unit, contract, replay, or comparator test.
4. Implement the smallest correction.
5. Run the focused test.
6. Run all lifecycle and account-safety regressions.
7. Compile both demo and real-capable binaries with zero errors and warnings.
8. Replay every preserved target cycle.
9. Reject the change if aggregate fidelity regresses or a safety boundary
   breaks.
10. Deploy the new fingerprint only to the fresh demo candidate.

Examples of evidence questions to test, not assume:

- whether the basket threshold is exactly $30 or includes another balance
  component;
- which profit, commission, swap, and fee fields enter the basket;
- the basket evaluation cadence and trigger-to-cancellation latency;
- stop selection when several positions become eligible together;
- rearm order when several levels become valid together;
- exact restart timing and anchor source;
- behavior after rejection, partial fill, disconnect, or terminal restart.

## EA component boundaries

The implementation should separate these responsibilities:

### Cycle state machine

Owns deployment, running, canceling, closing, restarting, and halted states.
It exposes explicit transitions and reasons.

### Level registry

Owns one identity per side and level, current pending/position ticket, target
price, lot, rearm eligibility, and occurrence count. Duplicate active level
identities fail closed.

### Deal ledger

Owns idempotent deal-ticket processing and authoritative cycle realized profit.

### Stop scheduler

Owns stop eligibility, selected ticket, requested stop, cadence, and ordering.
It does not imitate broker-side stop-execution serialization.

### Basket evaluator

Owns included P/L components, threshold, evaluation cadence, trigger snapshot,
and transition into cancellation.

### Telemetry adapter

Records decisions and outcomes without changing state-machine behavior.

These units must be testable independently so one hypothesis can change
without rewriting the entire engine.

## Presets and real-account safety

Two presets are required because target fidelity and additional risk controls
are different objectives.

### `FIDELITY`

- uses only evidence-supported target behavior;
- contains no extra stop, lot, equity, spread, or daily-loss rule unless the
  same rule is observed in the target;
- is used for paired demo measurement;
- remains demo-only until the full gate passes;
- must never be described as safe merely because it resembles the target.

### `REAL_SAFE`

- uses the same strategy geometry and lifecycle baseline;
- enables explicit gross-lot, equity-loss, spread, and daily-loss limits;
- checks exposure before creating or rearming an order where possible;
- fails closed on account, symbol, hedging-mode, or term mismatch;
- is reported as intentionally divergent from the target whenever a safety
  rule acts.

The user chooses the real-account preset after reviewing measured drawdown and
the fidelity report. Enabling safety can prevent the target's behavior and
therefore reduces literal fidelity during stressed conditions.

## Test strategy

### Unit and contract tests

Required coverage includes:

- duplicate deal callback does not change telemetry or cycle realized profit;
- deal ledger restoration after terminal restart;
- exact P/L component accounting;
- level identity and occurrence handling;
- anchor/step and lot-tier calculations;
- stop eligibility and ordering;
- rearm eligibility and ordering;
- basket trigger and cancellation transition;
- cycle restore and restart;
- account-login, demo/real mode, symbol, magic, and hedging guards;
- separate `FIDELITY` and `REAL_SAFE` preset contracts.

### Offline replay

Every build is replayed against:

- the canonical 1,200-event lifecycle dataset;
- all preserved target observer sessions;
- the latest target-versus-VPS evidence;
- synthetic duplicate, rejection, partial-fill, restart, and sequence-gap
  cases.

The replay output must show the earliest causal mismatch and the before/after
fidelity score.

### Live demo qualification

Promotion requires:

- at least 20 consecutive complete valid paired cycles;
- at least 48 market-open hours in the same unmodified qualification run;
- distinct cycle IDs and stable binary/preset fingerprints;
- zero target read-only violations;
- zero dropped events, sequence gaps, unresolved duplicate source identities,
  or stale commands;
- zero unexplained duplicate or missing level identities;
- no deterministic mismatch in any qualifying cycle;
- documented broker/execution differences;
- a successful terminal-restart recovery test on the candidate demo;
- an explicit maximum observed floating drawdown and gross exposure report.

Any source, preset, account-term, or deterministic behavior change resets the
20-cycle and 48-hour qualification counters.

If only `BEST_EFFORT` target evidence is available, the result may qualify as
the closest measured reconstruction but not as proven 100% request parity.

## Failure handling

- Stale or disconnected target capture pauses pairing and invalidates the
  affected cycle.
- Loss of target read-only status stops capture immediately.
- Nonzero dropped transactions or sequence gaps invalidate the session.
- Candidate account or symbol mismatch prevents EA initialization.
- Duplicate active level identity halts new placement for that level and emits
  an error event.
- Candidate telemetry failure is visible and invalidates certification; it
  does not authorize target access or copying.
- A failed candidate deployment rolls back only the fresh demo candidate.
- No failure path may modify the existing VPS replica or target account.

## Deliverables

After the gate, produce:

- reviewed MQL5 source retained privately in the workspace;
- compiled EX5 candidate for distribution;
- `latest_30_fidelity.set`;
- `latest_30_real_safe.set`;
- SHA-256 hashes for the EX5 and presets;
- machine-readable and human-readable fidelity reports;
- a mismatch register showing fixed, unresolved, broker-dependent, and
  unobservable behavior;
- demo and VPS installation instructions that contain no passwords;
- a clear real-account risk statement.

The EX5 and selected `.set` file are the user-facing deployment files. The
source is not required for normal MT5 operation.

## Completion criteria

This project is complete only when:

1. the confirmed duplicate-deal defect is fixed and regression-tested;
2. target and candidate evidence are normalized reproducibly;
3. every retained strategy change is supported by paired evidence;
4. the canonical replay does not regress;
5. the fresh demo candidate completes the qualification gate;
6. the final fidelity percentage and evidence grade are generated from saved
   reports;
7. `FIDELITY` and `REAL_SAFE` artifacts are clearly separated;
8. no claim of identical broker profit or unproven 100% parity is made.
