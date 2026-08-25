# Aligned Auxiliary Cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Safely start the dedicated auxiliary demo from a flat account at the target's next cycle boundary so a complete live pair can support a legitimate 95% fidelity decision.

**Architecture:** Pure Python evidence functions calculate freeze readiness and the predicted launch instant. A guarded CLI performs only exact-path terminal stop/start operations after the EA proves the auxiliary cycle is complete, while the existing telemetry collector and fidelity watcher remain authoritative.

**Tech Stack:** Python 3, pytest, Windows PowerShell process discovery, MT5 CSV telemetry, JSONL target archive.

---

### Task 1: Alignment Evidence Core

**Files:**
- Create: `straddle_replica/cycle_alignment.py`
- Create: `tests/test_cycle_alignment.py`

- [ ] **Step 1: Write failing readiness and timing tests**

```python
def test_freeze_requires_complete_without_restart():
    assert candidate_freeze_ready(
        [{"cycle_id": "c1", "kind": "cycle_complete"}],
        cycle_id="c1",
    )
    assert not candidate_freeze_ready(
        [
            {"cycle_id": "c1", "kind": "cycle_complete"},
            {"cycle_id": "c1", "kind": "cycle_restart"},
        ],
        cycle_id="c1",
    )


def test_launch_time_uses_recent_valid_restart_delay():
    events = target_boundary_events(
        delays=(20.5, 20.9, 130.0),
        next_complete="2026-08-13T18:00:00Z",
    )
    plan = plan_target_aligned_launch(
        events,
        frozen_at_utc=parse_utc("2026-08-13T17:45:00Z"),
        startup_lead_seconds=3.0,
    )
    assert plan.restart_delay_seconds == 20.7
    assert plan.launch_at_utc == parse_utc(
        "2026-08-13T18:00:17.700000Z"
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
tmp\independent-demo-venv\Scripts\python.exe -m pytest -q tests\test_cycle_alignment.py
```

Expected: collection failure because `straddle_replica.cycle_alignment` does not exist.

- [ ] **Step 3: Implement minimal pure functions**

Implement:

```python
def candidate_freeze_ready(events, *, cycle_id): ...
def target_restart_delays(events, *, minimum=10.0, maximum=60.0): ...
def plan_target_aligned_launch(
    events,
    *,
    frozen_at_utc,
    startup_lead_seconds,
): ...
```

The target plan must use the first `cycle_complete` after `frozen_at_utc`, median only valid complete-to-restart samples, and timezone-aware UTC values.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: all tests pass.

### Task 2: Guarded Local Alignment Controller

**Files:**
- Create: `tools/align_local_auxiliary_cycle.py`
- Modify: `tests/test_cycle_alignment.py`

- [ ] **Step 1: Write failing controller contract tests**

```python
def test_controller_is_terminal_only():
    source = TOOL.read_text(encoding="utf-8")
    assert "order_send" not in source.lower()
    assert "positions_get" not in source.lower()
    assert "orders_get" not in source.lower()
    assert "ExecutablePath" in source
    assert "--expected-active-ex5-sha256" in source


def test_controller_help_is_runnable():
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--candidate-cycle-id" in completed.stdout
```

- [ ] **Step 2: Run tests and verify RED**

Run the Task 1 command. Expected: failures because the CLI is absent.

- [ ] **Step 3: Implement the guarded CLI**

The CLI must:

```text
validate paths/hash/preset
wait for cycle_complete
abort on cycle_restart race
find exactly one exact-path terminal process
close only that process
wait for target completion after freeze
launch at predicted target restart minus startup lead
write atomic health updates
observe and record target/candidate start deltas
```

It must not import MetaTrader5 or expose account credentials.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: all alignment tests pass.

### Task 3: Regression and Build Verification

**Files:**
- Verify: `straddle_replica/live_twin.py`
- Verify: `straddle_replica/independent_fidelity.py`
- Verify: `mql5/include/StraddleEngine.mqh`

- [ ] **Step 1: Run focused regression tests**

```powershell
tmp\independent-demo-venv\Scripts\python.exe -m pytest -q tests\test_cycle_alignment.py tests\test_live_twin.py tests\test_independent_fidelity.py tests\test_independent_fidelity_watch.py tests\test_mql5_contract.py
```

Expected: zero failures.

- [ ] **Step 2: Compile MQL5**

```powershell
.\scripts\build.ps1
```

Expected: `Result: 0 errors, 0 warnings`.

- [ ] **Step 3: Verify active binary identity**

```powershell
Get-FileHash -Algorithm SHA256 D:\MT5IndependentRegistration\MQL5\Experts\StraddleReplica\StraddleReplica.ex5
```

Expected: `0C08884172447BE0C3606EF497DE314CC32DDB4DAAB309DAD3A6D371AF43DAF9`.

### Task 4: Arm and Observe the Aligned Cycle

**Files:**
- Create at runtime: `artifacts/live/independent-demo-fidelity/auxiliary-cycle-alignment-health.json`
- Update automatically: `artifacts/live/independent-demo-fidelity/auxiliary-qualification-state.json`

- [ ] **Step 1: Start the controller hidden**

Run with the current excluded cycle, exact dedicated terminal/config paths, active binary hash, target archive, auxiliary telemetry, and a 3-second startup lead.

- [ ] **Step 2: Confirm waiting safety**

Health must say `WAITING_FOR_AUXILIARY_FLAT`; terminal PID and open positions/orders remain untouched.

- [ ] **Step 3: Confirm flat freeze**

After natural `cycle_complete`, health must say `FROZEN_WAITING_FOR_TARGET_COMPLETE`; the dedicated terminal alone is stopped.

- [ ] **Step 4: Confirm aligned restart**

Health must record target/candidate cycle IDs, UTC start delta, anchor delta, and active EX5 hash. The new cycle must have exactly 60 unique B1/S1 through B30/S30 identities.

### Task 5: Formal 95% Gate and Delivery

**Files:**
- Read: `artifacts/live/independent-demo-fidelity/auxiliary-fidelity-watch-health.json`
- Read: `artifacts/live/independent-demo-fidelity/formal-comparison-reports/auxiliary-continuous/*.json`
- Deliver: `artifacts/StraddleReplica-TARGET-FIDELITY-DEMO-901111-RESTORE-FIX-20260813T164714Z.ex5`

- [ ] **Step 1: Wait for one complete eligible aligned pair**

Do not score or claim fidelity while pair count is zero or either cycle is incomplete.

- [ ] **Step 2: Apply the formal gate**

Require:

```text
strict lifecycle fidelity >= 95%
conditional logic fidelity >= 95%
conditional coverage >= 95%
deterministic mismatch count == 0
```

- [ ] **Step 3: Deliver only after evidence passes**

Report the report path, all three percentages, mismatch count, EX5 path, and SHA256. If the pair fails, identify the earliest causal deterministic mismatch and return to RED-GREEN source correction.
