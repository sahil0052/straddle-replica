# LATEST_30 live twin

The live-twin system validates `StraddleReplica` against the original target
EA without controlling the target account. Implementation alone is not a
certification result: promotion requires the measured gate described below.

## Hard prerequisites

- Obtain an Achiever hedging demo on the same server with matching XAUUSD
  contract, leverage, order limit, volume, filling, stop/freeze, tick-value and
  swap terms.
- Attach `StraddleTargetProbe` in the same terminal as the original target EA.
  The probe is passive and contains no trade-send, modification, cancellation
  or close operation.
- Keep the coordinator in observation-only mode until request events, zero
  dropped transactions, UTC timing and account-term parity are verified.
- Never use the shadow preset on a real account.

If the passive probe cannot observe `TRADE_TRANSACTION_REQUEST` request/result
events from the original EA, literal request parity cannot be certified and
the highest available qualification is `BEST_EFFORT_PASS`.

## Installation layout

Extract `StraddleLiveTwin.zip` to
`/home/ubuntu/straddle-live-twin/package`, then install:

- `mql5/StraddleReplica.ex5` into the isolated shadow terminal at
  `MQL5/Experts/StraddleReplica/StraddleReplica.ex5`.
- `profiles/latest_30_shadow.set` as
  `/home/ubuntu/straddle-live-twin/latest_30_shadow.set`, beside the startup
  configuration. MT5 resolves the relative `ExpertParameters` value from that
  directory during command-line startup.
- `monitor/shadow-startup.ini` as
  `/home/ubuntu/straddle-live-twin/shadow-startup.ini`.
- The three `deploy/linux/run_*shadow*.sh`/analysis scripts as executable files
  under `/home/ubuntu/straddle-live-twin/`.
- The three shadow systemd units and analysis timer under `/etc/systemd/system`.

Install `StraddleTargetProbe.ex5` separately in the original target terminal.
Do not copy target credentials or terminal configuration into the shadow
terminal or package.

Copy `deploy/linux/shadow.env.example` to
`/home/ubuntu/straddle-live-twin/shadow.env` and verify every path. Keep
`SHADOW_ACTIVE=0` for commissioning.

## Observer-driven best-effort mode

When the passive probe cannot be installed in the originating target terminal,
set `TARGET_SOURCE=observer` and point `TARGET_OBSERVER_ROOT` at the existing
read-only Python observer output. This mode infers accepted pending orders,
fills and lifecycle transitions from snapshots and broker history.

Observer mode may start the demo only after the currently observed target cycle
becomes flat and a fresh accepted `STR B1/S1` pair appears. It never starts
from a partial target cycle. Reports must remain `BEST_EFFORT`, retain all
broker-term mismatches, and state that originating request payloads and exact
request timestamps are unavailable.

Set `TARGET_SOURCE=probe` only when `StraddleTargetProbe` is running in the same
terminal as the original target EA. Only probe mode with matching account terms
can enter the formal certification gate.

## Fresh isolated fidelity candidate

The fidelity candidate is packaged with
`scripts\package_fidelity_candidate.ps1` and deployed only through
`scripts\deploy_fidelity_candidate_vps.ps1`. It uses the dedicated root
`/opt/straddle-fidelity-candidate`, container
`straddle-fidelity-candidate-demo`, and loopback VNC port `15915`.

The package contains the compiled EX5, bound shadow preset, unbound
`FIDELITY` and `REAL_SAFE` templates, startup configuration, installer,
Docker runtime files, documentation, and SHA-256 manifest. It excludes MQL
source and account secrets. The first boot keeps `MT5_START=0`; account terms
and the fresh demo login must be checked manually before commissioning.

The deployment script records the existing replica container identity, state,
and restart count before and after candidate startup and fails if any of them
change. The monitoring installer registers new fidelity-only tasks, starts
only the read-only collector, and leaves candidate cycle synchronization
stopped until commissioning is complete.

## Local Windows exact-twin supervision

Run `scripts/install_local_exact_twin_tasks.ps1` to register the local
`StraddleTargetCollector` and `StraddleNextCycleSync` tasks. The collector is
the sole Python process permitted to initialize the MetaTrader5 module against
`D:\MT5ObserverTerminal\terminal64.exe`.

Status checks and recurring monitors must read the collector heartbeat,
manifest, snapshots, history, and MQL observer files. Do not run an ad-hoc
`MetaTrader5.initialize` call against the target observer terminal while
`StraddleTargetCollector` is running; the Windows MT5 Python bridge is treated
as a single-owner connection.

The scheduled collector remains read-only and exits if the expected investor
login, server, or `trade_allowed=false` condition is lost. Task Scheduler
restarts process failures. The coordinator waits without writing a command
while target evidence is missing or stale.

The coordinator is not a trade copier. It may issue one demo `RESET` and one
demo `START` to establish a clean paired comparison cycle. After `STARTED`, the
local EA makes all trading decisions independently from its own account state
and broker prices.

## Commissioning

1. Set `ExpectedLogin` and `ExpectedServer` on `StraddleTargetProbe`.
2. Set the exact dedicated demo login in
   `/home/ubuntu/straddle-live-twin/latest_30_shadow.set`. The EA intentionally
   refuses shadow mode while `ExpectedAccountLogin=0`.
3. Confirm `shadow-startup.ini` has `[Experts]`, `Enabled=1` and
   `AllowLiveTrading=1`; the toolbar alone does not grant a startup-loaded EA
   permission to send orders.
4. Start the isolated shadow terminal and coordinator with
   `SHADOW_ACTIVE=0`.
5. Confirm probe request rows, UTC timestamps, no dropped/duplicate/sequence
   gaps, command observations, and exact account terms.
6. Confirm the target probe receives request/result events from the original
   EA in that same terminal.
7. Confirm its manifest reports
   `probe_build_id=latest30-live-twin-v1`.
8. Set `SHADOW_ACTIVE=1` and restart only the shadow coordinator.

The coordinator resets only the dedicated demo. It detects target closure,
waits for a sequence-matched `FLAT` acknowledgement, derives the next anchor
and step from `STR B1/S1`, and issues an expiring atomic start command. The
replica trades independently after deployment.

## Automated analysis

`straddle-live-twin-analysis.timer` runs every minute. In observer mode it
compares any available paired target/demo cycles and always refreshes
`reports/best-effort/status.json`. The status remains `BEST_EFFORT`, explicitly
lists broker-term and capture limitations, and reports `WAITING` before the
first paired cycle. Observer comparison reports are stored below
`reports/best-effort/runs/<fingerprint>-<start>/cycles/`.

Commissioning failures are fail-closed. When
`state/commissioning-guard.json` contains active failures, the best-effort
status reports `INVALID` and lists the guard codes. A demonstrated broker slot
limit below the required 60 orders must remain active until a clean 60-slot
deployment and reset smoke test passes.

In formal probe mode, the read-only analysis pipeline:

1. Fingerprints the active EA, effective runtime manifest, preset, startup
   file, environment, probe binary, coordinator, comparator and gate code.
2. Compares target/demo account and XAUUSD terms.
3. Measures request visibility, market-open hours, sequence continuity,
   duplicate rows, queue drops and probe-session restarts.
4. Refreshes every paired cycle in the active certification run.
5. Evaluates the formal gate and writes `gate.json`.

Reports are stored below `reports/runs/<fingerprint>-<start>/`. A code,
parameter, account-term, completed-cycle or operational mismatch writes a new
certification start for the next timer run. An incomplete active cycle is
`INVALID` but does not continually reset the clock.

Numeric mismatch candidates in comparison reports are advisory only. They do
not modify, compile, install or restart the EA; any accepted calibration still
requires code review, compilation and the complete gate from zero.

## Promotion gate

Each completed cycle must contain all 60 initial slots in exact alternating
order. Later pending requests are treated as rearms only when a prior stop exit
makes that level eligible. The comparator then checks stop requests, rearm
order, cancellations, closes, lifecycle completion and execution.

- Deterministic request values and retcodes must match exactly.
- Request and fill timestamps must be within one second.
- Fill prices must be within one symbol tick.
- Commission and swap must match exactly.
- P/L tolerance is limited to the account tick value implied by the permitted
  one-tick execution difference.
- Missing, duplicate, stale, rejected, invalid or unpaired cycles cannot pass.

The execution tolerance is therefore one tick and one second.

Promotion requires 20 consecutive complete paired cycles, all with distinct
cycle IDs, and 48 market-open hours. Any source, preset, account-term, or code
change, deterministic mismatch, sequence gap, duplicate capture identity, or
dropped transaction resets the qualification run.

Same-terminal request evidence with matching account terms can produce
`FORMAL_PASS`. Investor-observer evidence can only produce
`BEST_EFFORT_PASS`. Neither status promises identical broker profit because
spread, fills, slippage, commission, swap, and server timing remain
broker-controlled.
