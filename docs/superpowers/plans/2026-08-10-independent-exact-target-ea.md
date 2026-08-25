# Independent Exact-Target EA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the demo exact-twin workflow resilient, add native safe adoption of an existing local cycle, and collect valid paired evidence without continuous trade copying.

**Architecture:** A single supervised Python collector owns the target MT5 API connection. A fail-closed coordinator consumes only persisted observer evidence, performs one clean local reset/start alignment, and then leaves the EA independent. The EA receives a guarded native adoption mode so existing demo trades can enter shadow/wait mode without a fabricated command.

**Tech Stack:** Python 3.11, pytest, PowerShell ScheduledTasks, MQL5/MetaEditor, CSV/JSONL telemetry, MT5 demo and investor terminals.

---

The workspace is not a Git repository. Each task ends with targeted tests and a
SHA-256/file-state checkpoint instead of a commit.

### Task 1: Resilient coordinator loop

**Files:**
- Modify: `tools/run_shadow_coordinator.py`
- Modify: `tests/test_shadow_coordinator.py`

- [ ] **Step 1: Add a failing continuous-mode stale-heartbeat test**

Add a subprocess test that seeds an observer session with a stale heartbeat,
starts the coordinator without `--once`, and asserts that the process remains
alive and writes a waiting health document:

```python
def wait_for_path(path: Path, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {path}")


def build_stale_observer(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "observer"
    session = root / "session"
    session.mkdir(parents=True)
    (root / "current-session.json").write_text(
        json.dumps({"session_id": "session"}),
        encoding="utf-8",
    )
    (session / "manifest.json").write_text(
        json.dumps(
            {"time_domains": {"history_server_offset_seconds": 0}}
        ),
        encoding="utf-8",
    )
    stale = datetime.now(tz=UTC) - timedelta(minutes=1)
    heartbeat = session / "heartbeat.json"
    heartbeat.write_text(
        json.dumps(
            {
                "capture_time_utc": stale.isoformat(),
                "healthy": True,
                "stopped": False,
            }
        ),
        encoding="utf-8",
    )
    (session / "snapshots-20260810-05.jsonl").write_text(
        json.dumps(
            {
                "capture_time_utc": stale.isoformat(),
                "sequence": 1,
                "orders": [{"ticket": 1, "comment": "STR B1"}],
                "positions": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root, heartbeat


def test_continuous_coordinator_waits_on_stale_observer_heartbeat(
    tmp_path: Path,
) -> None:
    observer_root, heartbeat_path = build_stale_observer(tmp_path)
    health_path = tmp_path / "coordinator-health.json"
    process = subprocess.Popen(
        [
            sys.executable,
            str(TOOL),
            "--target-observer-root",
            str(observer_root),
            "--observer-state-path",
            str(tmp_path / "adapter.json"),
            "--command-path",
            str(tmp_path / "command.csv"),
            "--ack-path",
            str(tmp_path / "ack.csv"),
            "--state-path",
            str(tmp_path / "state.json"),
            "--target-archive-path",
            str(tmp_path / "target.jsonl"),
            "--health-path",
            str(health_path),
            "--retry-ms",
            "50",
        ],
        cwd=ROOT,
    )
    try:
        wait_for_path(health_path)
        assert process.poll() is None
        health = json.loads(health_path.read_text(encoding="utf-8"))
        assert health["status"] == "WAITING_FOR_TARGET"
        assert health["error_type"] == "RuntimeError"
    finally:
        process.terminate()
        process.wait(timeout=5)
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest tests\test_shadow_coordinator.py -k stale_observer_heartbeat -q
```

Expected: fail because `--health-path` and retry behavior do not exist.

- [ ] **Step 3: Implement atomic health reporting and transient retry**

Add CLI arguments:

```python
parser.add_argument("--health-path", type=Path)
parser.add_argument("--retry-ms", type=int, default=1_000)
```

Add an atomic helper:

```python
def write_health(path: Path | None, payload: dict[str, object]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)
```

Wrap only observer/file availability failures:

```python
try:
    events = adapter.poll() if adapter is not None else load_probe_events(...)
    result = coordinator.process_events(events)
except (FileNotFoundError, OSError, RuntimeError, json.JSONDecodeError) as exc:
    write_health(
        args.health_path,
        {
            "status": "WAITING_FOR_TARGET",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "updated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        },
    )
    if args.once:
        raise
    time.sleep(args.retry_ms / 1000.0)
    continue
```

After a successful poll, write `status="RUNNING"` with the result counters.
Do not catch programming errors such as `AssertionError` or `TypeError`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: pass.

- [ ] **Step 5: Run coordinator regressions**

Run:

```powershell
python -m pytest tests\test_shadow_coordinator.py tests\test_observer_adapter.py -q
```

Expected: all tests pass.

### Task 1A: Retry Windows atomic heartbeat replacement

**Files:**
- Modify: `straddle_replica/live_monitor.py`
- Modify: `tests/test_live_monitor.py`

- [ ] **Step 1: Reproduce the Windows sharing violation**

Monkeypatch `os.replace` to raise `PermissionError` twice and require
`atomic_write_json` to succeed on the third attempt.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m pytest tests\test_live_monitor.py -k sharing_violation -q
```

Expected: the first `PermissionError` escapes.

- [ ] **Step 3: Add bounded replacement retry**

Retry `os.replace` up to 20 times with a 10 ms delay, re-raising the final
`PermissionError`. Do not retry serialization or other programming failures.

- [ ] **Step 4: Verify GREEN**

Run the focused test and then all `tests\test_live_monitor.py` tests.

### Task 2: Seed coordinator command sequence from EA acknowledgement

**Files:**
- Modify: `straddle_replica/shadow_coordinator.py`
- Modify: `tests/test_shadow_coordinator.py`

- [ ] **Step 1: Add a failing acknowledgement-seeding test**

```python
def test_new_coordinator_continues_after_existing_ea_ack_sequence(
    tmp_path: Path,
) -> None:
    ack = tmp_path / "ack.csv"
    write_ack(ack, status="ADOPTED", command_seq=41)
    service = ShadowCoordinator(
        ShadowCoordinatorConfig(
            command_path=tmp_path / "command.csv",
            ack_path=ack,
            state_path=tmp_path / "missing-state.json",
        )
    )
    now = datetime(2026, 8, 10, 5, 0, tzinfo=UTC)
    service.process_events(
        [request_event(sequence=1, time=now, action="cancel_request")],
        now=now,
    )
    assert read_shadow_command(tmp_path / "command.csv").command_seq == 42
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests\test_shadow_coordinator.py -k existing_ea_ack_sequence -q
```

Expected: command sequence is `1`, not `42`.

- [ ] **Step 3: Seed only a missing coordinator state**

In `_default_state`, read the acknowledgement and initialize
`last_command_seq` from its validated nonnegative `command_seq`. Existing
persisted state always remains authoritative:

```python
ack = _read_ack(self.config.ack_path)
ack_sequence = max(0, int(ack["command_seq"]))
return {
    "schema_version": 1,
    "last_command_seq": ack_sequence,
    ...
}
```

- [ ] **Step 4: Verify GREEN and run coordinator regressions**

Run:

```powershell
python -m pytest tests\test_shadow_coordinator.py -q
```

Expected: all tests pass.

### Task 3: Native guarded adoption of an existing demo cycle

**Files:**
- Modify: `mql5/include/StraddleTypes.mqh`
- Modify: `mql5/include/StraddleReplicaApp.mqh`
- Modify: `mql5/include/StraddleEngine.mqh`
- Modify: `profiles/latest_30_shadow.set`
- Modify: `tests/test_mql5_contract.py`
- Modify: `tests/test_live_twin_deployment_contract.py`

- [ ] **Step 1: Add failing MQL contract tests**

Add assertions:

```python
def test_shadow_mode_can_guardedly_adopt_existing_demo_cycle():
    app = APP.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    assert "input bool AllowShadowAdoptExistingCycle = false" in app
    assert "runtime.allow_shadow_adopt_existing_cycle" in app
    assert "bool              allow_shadow_adopt_existing_cycle;" in types
    assert "AdoptExistingShadowCycle" in engine
    assert 'WriteShadowAck("ADOPTED"' in engine
    assert "existing_cycle_adoption_disabled" in engine
    assert '"runtime_shadow_adopt_existing_cycle"' in engine
```

Update the shadow preset contract to require:

```text
AllowShadowAdoptExistingCycle=true
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py tests\test_live_twin_deployment_contract.py -q
```

Expected: fail because the input and adoption path are absent.

- [ ] **Step 3: Add the runtime configuration**

Add to `SRuntimeConfig`:

```cpp
bool              allow_shadow_adopt_existing_cycle;
```

Add to `StraddleReplicaApp.mqh`:

```cpp
input bool AllowShadowAdoptExistingCycle = false;
```

Map it during `OnInit`:

```cpp
runtime.allow_shadow_adopt_existing_cycle=
   AllowShadowAdoptExistingCycle;
```

Write the effective value into the runtime manifest as
`runtime_shadow_adopt_existing_cycle`.

- [ ] **Step 4: Implement fail-closed adoption**

Add an engine helper:

```cpp
bool AdoptExistingShadowCycle(void)
  {
   if(m_runtime.runtime_mode!=STR_RUNTIME_SHADOW ||
      !m_runtime.allow_shadow_adopt_existing_cycle ||
      (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
         ACCOUNT_TRADE_MODE_DEMO ||
      m_runtime.expected_account_login==0 ||
      OwnedOrderCount()+OwnedPositionCount()==0)
      return false;
   m_cycle_id=StringFormat(
      "local-adopt-%I64u-%I64d",
      (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
      (long)TimeGMT()
   );
   if(!RestoreCycle())
      return false;
   PersistShadowSequence();
   LogEvent("shadow_adopt","",0,0.0,0.0,"existing_cycle");
   WriteShadowAck(
      "ADOPTED",
      m_shadow_last_command_seq,
      "existing_cycle"
   );
   return true;
  }
```

In initialization, when owned trades exist and no safe restored shadow cycle
identity exists, call this helper. If adoption is disabled or fails, print
`existing_cycle_adoption_disabled` and return `false`. Do not send, modify,
cancel, or close anything during adoption.

- [ ] **Step 5: Enable adoption only in the shadow preset**

Add:

```text
AllowShadowAdoptExistingCycle=true
```

Do not add it to normal demo or real presets.

- [ ] **Step 6: Run tests and verify GREEN**

Run the Step 2 command. Expected: all tests pass.

- [ ] **Step 7: Compile both account-mode builds**

Run:

```powershell
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: both logs report `0 errors, 0 warnings`.

### Task 4: Reproducible Windows supervision and single target API owner

**Files:**
- Create: `scripts/install_local_exact_twin_tasks.ps1`
- Create: `tests/test_local_exact_twin_task_contract.py`
- Modify: `docs/LIVE_TWIN.md`

- [ ] **Step 1: Add a failing task-contract test**

```python
def test_local_exact_twin_tasks_are_supervised_and_read_only():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "StraddleTargetCollector" in source
    assert "StraddleNextCycleSync" in source
    assert "--require-read-only" in source
    assert "--exit-on-connection-error" in source
    assert "--health-path" in source
    assert "--active" in source
    assert "New-ScheduledTaskSettingsSet" in source
    assert "-RestartCount 999" in source
    assert "ExecutionTimeLimit ([TimeSpan]::Zero)" in source
    assert "order_send" not in source
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests\test_local_exact_twin_task_contract.py -q
```

Expected: fail because the installer is missing.

- [ ] **Step 3: Implement the task installer**

The script validates the two terminal paths, Python executable, workspace, and
demo/common file paths. It registers:

- `StraddleTargetCollector`, directly running:

```text
python -m straddle_replica.monitor_cli monitor-live
  --terminal D:\MT5ObserverTerminal\terminal64.exe
  --output D:\MT5ObserverData\isolated-live
  --account 901018
  --server AchieverGlobalMarkets-Server
  --symbol XAUUSD
  --poll-ms 50
  --checkpoint-seconds 30
  --exit-on-connection-error
  --require-read-only
```

- `StraddleNextCycleSync`, directly running the resilient coordinator with
  `--active`, `--health-path`, and the persisted state paths.

Both tasks use interactive-token, limited privileges, no stored password,
unlimited execution time, ignored duplicate instances, and restart-on-failure.
The installer starts the collector, waits for a fresh read-only heartbeat, then
starts the coordinator.

- [ ] **Step 4: Update operational documentation**

Document that:

- the collector is the only Python MT5 client for the target terminal;
- status checks read persisted files;
- direct ad-hoc `MetaTrader5.initialize` calls against the observer terminal
  are forbidden while the collector runs;
- the coordinator never copies trades after `STARTED`.

- [ ] **Step 5: Verify GREEN**

Run the Step 2 test. Expected: pass.

### Task 5: File-only heartbeat monitoring

**Files:**
- Modify the existing Codex heartbeat automation after code verification.
- Modify: `docs/LIVE_TWIN.md`

- [ ] **Step 1: Update the heartbeat instructions**

Remove target-terminal `MetaTrader5.initialize` queries. Require file-only
checks of:

- Python collector heartbeat and manifest;
- MQL observer heartbeat/transactions;
- scheduled-task states and command lines;
- coordinator health/state;
- local EA telemetry and local MT5 API only when needed.

The heartbeat remains strictly read-only and never restarts processes or writes
commands.

- [ ] **Step 2: Verify the automation text**

View the saved automation and assert it contains:

```text
Never initialize the MetaTrader5 Python module against the target observer terminal while StraddleTargetCollector is running.
```

and still contains the target read-only, zero-drop, and no-trade-write rules.

### Task 6: Full regression, build, and demo deployment

**Files:**
- Runtime install under the existing local demo terminal only.
- Runtime state under `artifacts/live/next-cycle-sync`.

- [ ] **Step 1: Run the focused regression suite**

Run:

```powershell
python -m pytest `
  tests\test_live_monitor.py `
  tests\test_observer_adapter.py `
  tests\test_shadow_coordinator.py `
  tests\test_mql5_contract.py `
  tests\test_live_twin_deployment_contract.py `
  tests\test_local_exact_twin_task_contract.py -q
```

Expected: zero failures.

- [ ] **Step 2: Compile and fingerprint**

Run both build scripts and record:

```powershell
Get-FileHash `
  .\mql5\StraddleReplica.ex5,`
  .\mql5\StraddleReplicaReal.ex5 `
  -Algorithm SHA256
```

- [ ] **Step 3: Install only the demo build**

Copy the verified demo-capable binary and shadow preset into the existing
MetaQuotes demo terminal. Keep:

```text
RequireDemoAccount=true
ExpectedAccountLogin=5054170246
AllowShadowAdoptExistingCycle=true
```

Do not copy or attach the real build.

- [ ] **Step 4: Restart the demo terminal safely**

Before restart, record all local magic `901018` order and position tickets.
After restart, require:

- same ticket sets;
- `shadow_adopt` telemetry;
- `ADOPTED` acknowledgement;
- no cancel, close, or new deployment caused by adoption.

Rollback to the preserved binary/profile if any condition fails.

- [ ] **Step 5: Install and start supervised tasks**

Run the Task 4 installer. Verify:

- target collector task is running;
- collector heartbeat age is under five seconds;
- `trade_allowed=false`;
- coordinator task is running;
- coordinator health is `RUNNING`;
- command sequence has not advanced before a target cancellation.

### Task 7: Clean-cycle pairing and evidence gate

**Files:**
- Persisted evidence under `artifacts/live/next-cycle-sync`
- Comparison cursor under `artifacts/live/local-target-monitor-state.json`

- [ ] **Step 1: Wait for the next target basket close**

No manual order action is permitted. Verify the first target cancellation
produces exactly one local `RESET`.

- [ ] **Step 2: Verify reset scope**

Confirm every affected local ticket had:

```text
magic=901018
symbol=XAUUSD
```

and no other order or position changed due to reset.

- [ ] **Step 3: Verify clean start**

Require a sequence-matched `FLAT`, fresh target `STR B1/S1`, derived anchor and
step, `STARTED`, and a complete local alternating 60-order deployment.

- [ ] **Step 4: Compare the independent cycle**

Run the lifecycle comparator. Classify:

- exact deterministic matches;
- proven deterministic mismatches;
- broker execution differences;
- missing evidence.

- [ ] **Step 5: Enforce the promotion gate**

Continue until ten paired cycles and 48 market-open hours pass with zero
operational errors. Any deterministic code change restarts both counters.

Only after the gate passes may `StraddleReplicaReal.ex5` be packaged as the
real-account candidate. It is not installed or activated automatically.
