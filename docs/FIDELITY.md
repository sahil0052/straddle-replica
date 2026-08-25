# Fidelity and calibration status

## Current classification

This build is a structural replica. It is not 100% behaviorally verified and
must not be represented as an exact clone until full lifecycle replay matches
the supplied history.

The `LATEST_30` live-twin instrumentation, shadow coordinator, lifecycle
comparator and fail-closed 20-cycle/48-market-open-hour gate are implemented.
That is validation infrastructure, not certification evidence. The formal gate
has not been started because a term-matched Achiever hedging demo and
same-terminal access to the original target EA are still required.

Qualification requires 20 consecutive complete paired cycles and 48 market-open hours on one unchanged build. Any source, preset, account-term, or code change,
deterministic mismatch, sequence gap, duplicate identity, or dropped
transaction resets the run. Same-terminal request evidence with matching terms
may produce `FORMAL_PASS`; investor-observer evidence can only produce
`BEST_EFFORT_PASS`. Neither result promises identical broker profit.

## Authoritative report counts

Original report:

- 17,632 closed positions and 6 open positions.
- 54,742 historical orders and 51 working orders.
- 35,446 deals and 284 detected grid deployments.
- Profile deployments: 101 `HISTORICAL_50`, 77 `HISTORICAL_60`, 2
  `AGGRESSIVE_30`, 1 `LOW_RISK_30`, and 103 `LATEST_30`.

Recent report:

- 609 closed positions and 4 open positions, or 613 total trades.
- 2,178 historical orders and 54 working orders.
- 1,213 deals and 22 `LATEST_30` deployments.
- No `STR AVB`, `STR AVS`, `STR ORB`, or `STR ORS` orders.

## Deterministic properties confirmed

- Alternating deployment order and comments: `STR B1`, `STR S1`, through the
  selected profile's final level.
- No take-profit values on the reconstructed pending grid.
- All observed lot tiers for the five profile families.
- `LATEST_30` and `LOW_RISK_30` use tick-normalized anchor / 3000 spacing.
- `AGGRESSIVE_30` uses tick-normalized anchor / 6000 spacing.
- Original initial deployments: 25,614 compared grid orders with zero side,
  level, lot, or price mismatches.
- Recent initial deployments: 1,311 compared grid orders with zero mismatches.
- Recent all-order attribution: 1,582 orders match profile lot and price
  geometry; 41 earlier orders belong to a cycle that began before the report.
- Original all-rearm analysis finds 177 old-profile differences: 146 volume
  and 31 price mismatches. Initial deployment geometry still matches.

The tick archive covers 78 half-day segments through August 1, 2026:
7,349,903 ticks, no missing or invalid segments, and no internal gap over five
minutes. The selected report-time offset is UTC+0 and the anchor source is the
bid/ask midpoint. Both training and holdout remain within one tick:

- Original: 282 usable deployments, 197 training and 85 holdout.
- Recent: 21 usable deployments, 14 training and 7 holdout.

## Lifecycle evidence from the recent report

- The earlier report-only inference of a fixed $0.20 initial profit lock is
  superseded by live transaction evidence. The initial stop follows the
  pre-tightening trail at approximately two grid steps behind market once the
  position crosses the activation threshold.
- The fixed-$30 basket model remains the strongest tester baseline. Live
  cancellation was observed at approximately $33.54 and $37.77 cycle net, so
  trigger-to-confirmation latency is analyzed separately.
- Pending orders are canceled first at roughly 100 ms intervals.
- Residual `STR CLOSE` exits are submitted about every 20 seconds.
- A new deployment begins about 20 seconds after the final residual close.
- A stopped level is not eligible to rearm for 20 seconds. Corrected local
  evidence contains 23 genuine rearms, all at least 20.113 seconds after the
  stop exit; two orders previously counted as rearms were actually members of
  complete 60-order deployments. A later VPS-only `STR B12` rearm occurred
  after 59.675 seconds.
- The first complete real cycle stops `STR S3` and then `STR S1`; `STR S2`
  survives to the basket close. A uniform every-position trailing loop does
  not reproduce this selection.

## Real-tick model-selection result

The comparison interval begins with the first complete recent deployment.
The report has 602 fills, 416 stop exits, 182 `STR CLOSE` exits, and 22
deployments. Position-level canonical comparison contains 1,200 lifecycle
events.

| Stop model | Fills | Stop exits | Basket exits | Cycles | Aligned fills |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current default, every tick | 655 | 514 | 138 | 18 | 370 / 602 |
| All positions every 10 s | 584 | 401 | 162 | 20 | 339 / 602 |
| All positions every 20 s | 556 | 366 | 177 | 20 | 339 / 602 |
| One oldest every 20 s | 412 | 279 | 120 | 11 | 247 / 602 |
| One newest every 20 s | 538 | 360 | 165 | 16 | 292 / 602 |

The prior every-tick baseline aligns 604 of 1,200 full lifecycle events. The
10-second model aligns 553 events. These results predate the live stop-phase
capture described below.

Live stop transactions now support a two-stage trailing candidate:

- activate the initial lock near two favorable grid steps;
- set the initial stop about two grid steps behind the current market;
- trail about two steps behind before tightening;
- after roughly three favorable steps, trail about one step behind.

Across three non-overlapping preserved sessions, 2,483 stop changes over 144
positions were captured with 170,482 contiguous heartbeats, 207,142 ticks,
5,793 transactions, zero sequence gaps, and zero dropped transactions. Median
activation was 2.1185 grid steps. A chronological 70/30 threshold fit selected
3.0553 favorable steps and classified the two phases with 97.72% holdout
accuracy. Level gap achieved only 66.24%, rejecting the earlier simple
gap-threshold hypothesis.

There were 84 clean two-step-to-one-step transitions. Every immediately
preceding two-step stop implied a decision below three steps, with a maximum of
2.9926. The first one-step stop began at the three-step rounding boundary, with
a minimum implied value of 2.9852. No genuine one-step-to-two-step reversal was
found.

Only 2 of 144 captured initial locks were exactly $0.20 from entry, and the
median initial lock was $0.09. This rejects a fixed-$0.20 activation rule for
`LATEST_30`; the fixed offset remains available only as a calibration fallback
for other profiles.

Tight stop-update groups establish descending/newest-ticket-first ordering.
At a 100 ms grouping boundary, 170 multi-ticket groups were descending and 17
were ascending. Global stop-update p10 was approximately 99-103 ms in every
preserved session. `LATEST_30` therefore updates one newest eligible stop per
100 ms timer pass.

### Broker stop-exit serialization

Stop modification cadence and stop execution cadence are separate. Across the
preserved live evidence, 16 runs covering 41 positions exited at an identical
SL approximately one position every 20 seconds:

- median inter-exit gap: 20.114 seconds;
- minimum/maximum gap: 19.815/21.127 seconds;
- all 16 runs exited in ascending position-ticket order;
- in 15 runs, every position already had the identical broker-side SL before
  the first exit; the remaining run lacks complete stop-change evidence.

The recent historical report independently contains 62 same-SL serialized runs
covering 137 positions with the same 20.114-second median inter-exit gap. This
matches the live account behavior and is not a Strategy Tester timing artifact.

This proves the 20-second stagger is produced after the EA has submitted its
stop decisions. It must be classified as broker/server execution behavior, not
imitated by slowing the EA's 100 ms stop-update scheduler. MT5 Strategy Tester
can therefore close same-SL positions differently from the target broker even
when the EA's deterministic stop requests match.

### Same-start August live replay

A clean live deployment beginning August 3, 2026 at 14:28:48 UTC was replayed
from the same second with fresh magic `901039` and real broker ticks. The
deterministic deployment matched exactly:

- anchor `4051.51`;
- step `1.35`;
- all 60 comments in alternating `B1, S1 ... B30, S30` order;
- all lot tiers and pending prices.

Lifecycle execution then diverged. The live cycle produced 18 fills, 12
stop exits, and 6 residual closes; Strategy Tester produced 12 fills, 5 stop
exits, and 7 residual closes before restarting 976 seconds early. The first
material cause is execution price: live `STR S1` filled at `4050.13`, while
Strategy Tester filled it at `4049.78`. That $0.35 difference delayed the
three-step tightening switch and changed downstream stop exits even though the
deployment and stop formulas were unchanged.

Across 114 activations with captured pending-order history, measuring favorable
movement from the actual broker fill was closer to the observed two-step
trigger in 94 cases; using the pending grid price was closer in only 7 cases
(13 ties). The EA must therefore retain `POSITION_PRICE_OPEN` as its activation
reference rather than compensating for Strategy Tester fills with the grid
target.

The replay comparison is preserved in
`artifacts/vps/live-cycle-replay-20260803T142848.json`.

### Basket-trigger timing

State-snapshot reconstruction found three live cycles crossing the current
$30 candidate before cancellation. Their observed peak nets were $36.70,
$37.77, and $36.94. In the third cycle, `STR S12` filled after the crossing
and reduced basket net to approximately $19.54 before cancellation began
22.411 seconds after the observed crossing. This proves that cancellation
timestamp net alone cannot identify the trigger threshold.

A controlled same-start 0.18%-of-balance replay restarted 994 seconds early,
versus 976 seconds early for fixed $30, and did not improve lifecycle parity.
Fixed $30 therefore remains the promoted baseline while the original
trigger/check cadence remains unresolved. The evidence is preserved in
`artifacts/vps/basket-trigger-analysis-20260804.json`.

Clean tester runs use a fresh magic number per run so telemetry cannot append
across experiments:

| Calibration | Cycles | Fills | Stops | Closes | Events | Matched / 1,200 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Expected report | 22 | 602 | 416 | 182 | 1,200 | 1,200 |
| Prior every-tick baseline | 18 | 655 | 514 | 138 | 1,307 | 604 |
| Two-stage, newest, one per 100 ms | 21 | 646 | 477 | 166 | 1,289 | 663 |
| Two-step initial activation, newest, one per 100 ms | 21 | 644 | 475 | 166 | 1,285 | 662 |
| Earlier 20-second rearm calibration | 20 | 621 | 458 | 150 | 1,229 | 625 |
| Two-stage, newest, max two per tick | 10 | 513 | 418 | 81 | 1,012 | 441 |
| Two-stage, 0.18% basket | 11 | 496 | 404 | 79 | 979 | 453 |

The timer-based model remains the strongest broad full-lifecycle result so
far. The August 6-7 capture contained sub-two-second same-level stop/order
pairs, but that evidence predates the currently observed `Straddle v1.1.36`
identity. On August 12, 2026, the current version produced 51 correctly paired
rearms with a 19.817-second minimum and no event below 19.5 seconds. Two
replacement prices remained broker-valid throughout their complete waiting
windows and were still accepted only after 20.119 and 20.120 seconds.
`LATEST_30` therefore uses a 20-second rearm gate for the current target.
The evidence is preserved in
`artifacts/live/independent-demo-fidelity/current-target-rearm-delay-assessment.json`.

The supplied `scalpingrobotpromytradingset.set` file is not compatible with
the observed target. Its `SRP` comments, magic `77789`, 20-order limit,
fixed entry-distance/recovery model, and trailing values conflict with the
target's 60 `STR B/S` identities, magic `26011001`, anchor-derived spacing,
fixed lot tiers, and two-stage trailing behavior. It remains unapplied and
reference-only.

The candidate level registry now treats MT5's brief same-ticket
order-to-position fill transition as one logical entity. This removes a
confirmed false `duplicate_level_identity` report while preserving fail-closed
behavior for genuinely different tickets. The final demo build produced
multiple same-ticket fills without a false duplicate report; inherited `STR S2` and
`STR S8` reports remain genuine two-ticket duplicates in the excluded
commissioning cycle. Evidence is in
`artifacts/live/independent-demo-fidelity/same-ticket-overlap-assessment.json`.

Current target cycle `20260812T130157173Z-target-783` supplied a complete
`Straddle v1.1.36` transition check. It cancelled 43 pending orders in 4.816
seconds at a 0.113-second median cadence, then completed ten residual exits
with 19.910-20.223-second gaps. The next cycle began 21.869 seconds after
flat and deployed all 60 orders in 6.473 seconds with the exact alternating
comments, lot tiers, and zero geometry errors. These observations support the
active 100 ms cancellation/deployment cadence, 20-second close cadence, and
20-second restart gate; no source change was required. Evidence is in
`artifacts/live/independent-demo-fidelity/current-target-cycle-transition-assessment.json`.

For the first cycle, the real next deployment is July 30, 2026 at 01:08:04.192
UTC. The canonical tester restarts at 01:06:26 UTC, 98 seconds early.

## Historical spacing proxies

- `HISTORICAL_50`: live M15 ATR(17) × 0.10422410545583288.
- `HISTORICAL_60`: live M5 ATR(44) × 0.09188197447190301.

The proxies pass the chronological holdout gate but are not the original
private formula. `HISTORICAL_50` holdout mean error is 8.52 ticks and
`HISTORICAL_60` is 4.92 ticks.

## Remaining gaps

- The current target uses a 20-second per-level rearm gate. Exact ordering when
  several stopped levels become broker-valid together, and remaining
  cycle-transition differences, are unresolved.
- The 14 `STR AVB` and 14 `STR AVS` triggers in the original report remain
  unidentified.
- Historical crossed-level recovery ordering and the 177 rearm differences
  remain unresolved.
- Historical tick playback does not reproduce every live fill delay or
  slippage. It also does not reproduce the target broker's ascending-ticket,
  approximately 20-second serialization of positions that already share the
  same SL. Those broker-dependent outcomes cannot be guaranteed by EA source.
- Exact rejection, partial-fill, network-loss, and restart parity still need
  demo validation.

## Live observer status

The Ubuntu/Wine VPS is configured as the sole live monitor. The laptop
scheduled task, collector, and isolated observer terminal were stopped on
August 3, 2026; their captured data was preserved. On August 8, 2026 at
08:57 UTC, the MQL observer and Python collector were active with zero service
restarts. Both collectors reported 46 orders, 14 positions, read-only status,
and zero dropped transactions. The isolated shadow MT5 and coordinator were
also active. No local fallback was started.

The main VPS evidence session ran for 16.10 hours with 57,094 contiguous
heartbeats, 148,549 ticks, 3,587 transactions, 4,307 snapshots, and zero
dropped MQL transactions. It captured two completed cycles and 1,782 stop
changes across 100 positions.

New deterministic evidence:

- pending orders are canceled by descending ticket at roughly 110 ms each;
- residual positions are closed by descending position ticket at roughly
  20-second intervals;
- two observed basket exits began at approximately $37.77 and $33.54 cycle
  net;
- stop activation has a 2.87 median favorable move and two dominant trailing
  distances near 2.78 and 1.43;
- normalized preserved evidence maps those values to approximately 2-step
  activation, 2-step pre-tightening distance, a 3-step tightening threshold,
  and 1-step post-tightening distance;
- active stop modifications are serialized at about 100 ms in descending
  position-ticket order;
- the old fixed-$0.20-only stop model is incomplete.

The Python collector now accounts for the broker's UTC+2 history timestamps,
and both Wine services share one runtime so collector restarts do not create a
duplicate terminal. The formal uninterrupted validation window restarted with
MQL session `20260803T202948Z_901018_XAUUSD` after this service correction.
At the latest local evidence pull on August 3, 2026 at 23:50:33 UTC, that
formal session had 11,873 contiguous heartbeats over 3.345 hours, 8,143 MQL
ticks, 165 transactions, zero sequence gaps, zero dropped transactions, and
read-only trading permission.

Detailed evidence is in
`artifacts/vps/live-comparison-20260804.md`.
The broker serialization audit is in
`artifacts/vps/broker-stop-serialization-20260804.json`.
The corrected rearm audit is in
`artifacts/vps/rearm-gate-analysis-20260804.json`.

The transaction analyzer now preserves all MQL request and result fields when
they are present. An audit of all 5,793 preserved transaction rows across 58
local MQL CSV files found zero `TRADE_TRANSACTION_REQUEST` rows and zero
request/result payloads. This confirms that the separate read-only terminal
captures accepted broker transactions and state changes, not the originating
EA terminal's outgoing request stream. Direct requested-SL/action comparison
therefore requires same-terminal telemetry; the current topology continues to
infer those decisions from accepted position updates and snapshots. The audit
is in `artifacts/vps/request-capture-audit-20260804.json`.

## Exactness gate

Promotion beyond “structural replica” requires:

1. Exact direction, comment, volume, geometry, rearm, and cycle-transition
   agreement in the canonical comparator.
2. Stop-ticket selection and reset conditions matching both training and
   holdout cycles.
3. Execution-dependent timing, fill price, slippage, profit, and swap reported
   separately.
4. A minimum 48-hour demo forward test without operational errors.
5. At least 48 non-overlapping market-open capture hours and ten complete live
   deploy/close/restart cycles with zero sequence gaps or dropped transactions.

`tools/evaluate_exactness_gate.py` enforces these thresholds and requires ten
matching deployment replays plus ten matching lifecycle comparisons. It
reports deterministic EA-decision parity separately from broker execution
parity. The current result is preserved in
`artifacts/vps/exactness-gate-20260804.json` and fails closed.
