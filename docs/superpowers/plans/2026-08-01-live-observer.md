# Live Straddle Observer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a durable, read-only MT5 monitoring system for account `901018` that captures every observable tick, transaction, order, position, deal, and state transition.

**Architecture:** A minimal MQL5 observer captures terminal-native transaction events and ticks while a Python sidecar independently polls and journals account state. Both fail closed unless the expected investor/read-only account is connected, and Windows scripts install, start, supervise, and report status without storing credentials.

**Tech Stack:** MQL5 build 6090, Python 3.11, MetaTrader5 5.0.5735, pytest, PowerShell Scheduled Tasks.

---

### Task 1: Lock the non-trading contract

**Files:**
- Create: `tests/test_observer_contract.py`
- Create: `tests/test_live_monitor.py`

- [ ] Add a source-contract test requiring `OnTradeTransaction`,
  `EventSetMillisecondTimer`, `CopyTicks`, `FILE_COMMON`, and the expected
  account/server/read-only guards in `mql5/StraddleObserver.mq5`.
- [ ] Add a forbidden-token test covering `OrderSend`, `OrderSendAsync`,
  `CTrade`, `TRADE_ACTION_`, `PositionModify`, `PositionClose`, `OrderDelete`,
  and Python `order_send`.
- [ ] Add tests for deterministic tick deduplication, state fingerprints,
  hourly file naming, atomic heartbeat replacement, and read-only validation.
- [ ] Run `python -m pytest tests/test_observer_contract.py tests/test_live_monitor.py -q`
  and verify failure because the observer and collector do not yet exist.

### Task 2: Implement the Python collector

**Files:**
- Create: `straddle_replica/live_monitor.py`
- Modify: `straddle_replica/cli.py`

- [ ] Implement immutable normalization helpers for ticks, positions, orders,
  historical orders, and deals.
- [ ] Implement overlapping tick reads with a bounded deduplication cache keyed
  by millisecond timestamp and complete tick values.
- [ ] Implement state-change snapshots plus periodic full checkpoints.
- [ ] Implement hourly append-only writers and an atomically replaced
  `heartbeat.json`.
- [ ] Implement reconnection, resume metadata, and explicit account/server/
  symbol validation.
- [ ] Refuse startup when `account_info.trade_allowed` is true or the expected
  login/server does not match.
- [ ] Add `monitor-live` and `monitor-status` CLI commands.
- [ ] Run the targeted tests until they pass.

### Task 3: Implement the MQL5 observer

**Files:**
- Create: `mql5/StraddleObserver.mq5`

- [ ] Add inputs for expected login, expected server, monitored symbol, timer
  interval, snapshot interval, heartbeat interval, and output prefix.
- [ ] In `OnInit`, verify investor mode and the expected account/server, open
  `FILE_COMMON` append-only files, write metadata, seed the initial snapshot,
  and start the millisecond timer.
- [ ] In `OnTradeTransaction`, serialize the transaction/request/result fields
  into an in-memory ring queue and return immediately.
- [ ] In `OnTimer`, flush queued transactions, collect overlapping `CopyTicks`
  results, detect account-state changes, write snapshots, and update heartbeat.
- [ ] In `OnDeinit`, flush all pending records, record the stop reason, close
  handles, and stop the timer.
- [ ] Run the contract tests and verify the source contains no forbidden
  operation.

### Task 4: Build and install safely

**Files:**
- Create: `scripts/build_observer.ps1`
- Create: `scripts/install_observer.ps1`
- Create: `scripts/start_live_monitor.ps1`
- Create: `scripts/stop_live_monitor.ps1`
- Create: `scripts/install_monitor_task.ps1`

- [ ] Compile only `StraddleObserver.mq5` and require zero errors and warnings.
- [ ] Install source and binary under
  `MQL5\Experts\StraddleObserver` without modifying `StraddleReplica` or the
  original EA.
- [ ] Start Python with `Start-Process -WindowStyle Hidden`, a PID file, and
  duplicate-process protection.
- [ ] Stop only the PID whose executable and command line match this workspace.
- [ ] Register a startup/logon scheduled task with restart-on-failure and no
  credentials in task arguments.
- [ ] Add tests that verify all scripts retain the read-only guards.

### Task 5: Start and verify local capture

**Files:**
- Create at runtime: `artifacts/live/<session>/...`

- [ ] Start the Python collector against
  `C:\Program Files\MetaTrader 5\terminal64.exe`.
- [ ] Verify the manifest reports the expected server and investor mode.
- [ ] Verify the initial snapshot contains four positions and 54 orders.
- [ ] Verify heartbeat advancement, tick/history persistence, reconnect
  behavior, and zero trade calls.
- [ ] Install and attach the observer to a separate local XAUUSD chart only
  after its binary and static safety audit pass.

### Task 6: Deploy an isolated VPS monitor

**Files:**
- Create: `scripts/package_monitor.ps1`
- Create: `docs/LIVE_MONITORING.md`

- [ ] Package only the observer, collector, requirements, and deployment
  scripts; exclude reports, credentials, caches, and the trading EA.
- [ ] Connect to the supplied Windows VPS and inspect existing terminals without
  changing them.
- [ ] Create a separate portable monitoring terminal and log it into the
  expected account using investor mode.
- [ ] Install the observer and collector into that isolated terminal.
- [ ] Register the watchdog scheduled task and verify it survives collector and
  terminal restarts.
- [ ] Confirm remote heartbeat/data files continue updating after the local RDP
  session disconnects.

### Task 7: Final verification and handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/FIDELITY.md`
- Modify: `docs/LIVE_MONITORING.md`

- [ ] Run the targeted monitor tests, then the full pytest suite.
- [ ] Compile both MQL5 programs with zero errors and warnings.
- [ ] Search all monitor code and scripts for forbidden trading APIs and
  credential strings.
- [ ] Record local/VPS process IDs, session paths, start time, expected review
  time, and exact stop/status commands.
- [ ] Document that deterministic strategy parity may improve to 100%, while
  broker-dependent fill parity remains execution-dependent.

