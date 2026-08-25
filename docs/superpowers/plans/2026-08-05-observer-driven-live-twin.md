# Observer-Driven Live Twin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start the Achiever demo on the next clean target cycle using accepted target-state evidence, then collect paired best-effort lifecycle comparisons for 24 hours.

**Architecture:** Add an incremental observer adapter that tails the existing target snapshot/order/deal JSONL streams and emits normalized coordinator events. Extend the coordinator CLI to use either the formal same-terminal probe or the observer adapter, preserving the existing atomic command, acknowledgement and demo-only guards.

**Tech Stack:** Python 3.11, CSV/JSONL, existing `ShadowCoordinator`, pytest, Bash/systemd, MT5/Wine.

---

The workspace is not a Git repository. Each task therefore ends with a focused
test and file-hash checkpoint instead of a commit.

### Task 1: Observer adapter state and cycle seeding

**Files:**
- Create: `straddle_replica/observer_adapter.py`
- Create: `tests/test_observer_adapter.py`

- [ ] **Step 1: Write failing tests for current-cycle seeding**

Create fixtures with one active target snapshot containing existing `STR`
orders and positions. Assert that first startup seeds ticket/cycle state and
emits no events:

```python
def test_initial_active_cycle_is_seeded_without_start_events(tmp_path):
    root = build_observer_root(tmp_path, active_cycle=True)
    adapter = ObserverEventAdapter(
        ObserverAdapterConfig(
            observer_root=root,
            state_path=tmp_path / "adapter.json",
        )
    )

    assert adapter.poll() == []
    assert adapter.state["waiting_for_flat"] is True
```

Add a second test where the latest snapshot is flat and assert the adapter is
armed for the next cycle without replaying historical files.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m pytest tests\test_observer_adapter.py -q
```

Expected: collection failure because `observer_adapter.py` does not exist.

- [ ] **Step 3: Implement persisted adapter configuration/state**

Create:

```python
@dataclass(frozen=True)
class ObserverAdapterConfig:
    observer_root: Path
    state_path: Path
    heartbeat_max_age_seconds: float = 5.0


class ObserverEventAdapter:
    def __init__(self, config: ObserverAdapterConfig) -> None: ...
    def poll(self, now: datetime | None = None) -> list[dict[str, Any]]: ...
    @property
    def state(self) -> Mapping[str, Any]: ...
```

On first initialization:

- locate the session referenced by `current-session.json`, or the newest
  session containing `manifest.json`;
- parse only the latest complete snapshot row;
- seed current order/position tickets;
- set all existing JSONL cursors to EOF;
- set `waiting_for_flat=True` when any `STR` state exists;
- set `armed_for_next_cycle=True` only when the target is already flat;
- persist state atomically.

- [ ] **Step 4: Run tests and verify pass**

Run the Task 1 test command. Expected: all Task 1 tests pass.

### Task 2: Incremental accepted-order and cycle-boundary events

**Files:**
- Modify: `straddle_replica/observer_adapter.py`
- Modify: `tests/test_observer_adapter.py`

- [ ] **Step 1: Add failing tests for flat transition and next B1/S1 pair**

Append snapshots that transition:

1. active target state;
2. flat target state;
3. new `STR B1`;
4. new `STR B1/S1`.

Assert:

```python
assert [event["kind"] for event in flat_events] == ["cancel_request"]
assert [event["comment"] for event in next_events] == ["STR B1", "STR S1"]
assert all(event["kind"] == "pending_request" for event in next_events)
assert next_events[0]["source"] == "observer_inferred"
```

Add duplicate-poll and restart tests proving each ticket is emitted once.

- [ ] **Step 2: Run tests and verify the new assertions fail**

Run the Task 1 test command. Expected: the new transition tests fail.

- [ ] **Step 3: Implement incremental snapshot tailing**

Implement complete-line JSONL reads from persisted byte offsets. For each new
snapshot:

- reject stale `heartbeat.json`;
- filter comments matching `^STR ([BS])(\d+)$`;
- emit one inferred `cancel_request` when an observed active cycle first
  becomes flat;
- while armed, emit accepted `pending_request` events for unseen tickets using
  `time_setup_msc`, `price_open`, `volume_initial`, comment-derived side and
  retcode `10008`;
- assign a persisted monotonic adapter sequence;
- disarm only after a fresh B1/S1 pair establishes the new cycle;
- continue emitting later accepted pending levels for comparison;
- atomically persist offsets, tickets, sequence and cycle state.

- [ ] **Step 4: Run tests and verify pass**

Run the Task 1 test command. Expected: all transition, deduplication and restart
tests pass.

### Task 3: Deal, stop, close and cancellation inference

**Files:**
- Modify: `straddle_replica/observer_adapter.py`
- Modify: `tests/test_observer_adapter.py`

- [ ] **Step 1: Add failing history tests**

Create incremental order/deal rows and assert:

```python
assert fill["kind"] == "fill"
assert fill["comment"] == "STR B1"
assert stop["kind"] == "stop_exit"
assert stop["comment"] == "STR B1"
assert close["kind"] == "close_fill"
assert cancel["kind"] == "cancel_request"
```

Verify broker timestamps, volume, price, commission, swap and profit are
preserved. Add malformed/partial-line tests.

- [ ] **Step 2: Run tests and verify failure**

Run the Task 1 test command. Expected: history assertions fail.

- [ ] **Step 3: Implement history tailing and position mapping**

Tail `history-orders-*.jsonl` and `history-deals-*.jsonl` with independent
cursors. Persist `position_id -> STR comment` mappings from current positions
and entry deals.

Normalize:

- deal entry `0` to `fill`;
- exit deals with stop-loss reason/comment to `stop_exit`;
- other exit deals to `close_fill`;
- canceled/expired historical pending orders to `cancel_request`.

Every event includes `source="observer_inferred"` and
`capture_limit="no_originating_request_payload"`.

- [ ] **Step 4: Run tests and verify pass**

Run the Task 1 test command. Expected: all adapter tests pass.

### Task 4: Coordinator CLI observer source

**Files:**
- Modify: `tools/run_shadow_coordinator.py`
- Modify: `deploy/linux/run_shadow_coordinator.sh`
- Modify: `deploy/linux/shadow.env.example`
- Modify: `tests/test_shadow_coordinator.py`
- Modify: `tests/test_live_twin_deployment_contract.py`

- [ ] **Step 1: Add failing CLI and deployment tests**

Add a CLI integration test using `--target-observer-root` and
`--observer-state-path`. Seed the current cycle, append flat plus B1/S1
snapshots, run `--once`, and assert one `START` command.

Add deployment assertions for:

```text
TARGET_SOURCE=observer
TARGET_OBSERVER_ROOT=/home/ubuntu/straddle-data/python
OBSERVER_ADAPTER_STATE=/home/ubuntu/straddle-live-twin/state/observer-adapter.json
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
python -m pytest tests\test_observer_adapter.py tests\test_shadow_coordinator.py tests\test_live_twin_deployment_contract.py -q
```

Expected: observer CLI/deployment tests fail.

- [ ] **Step 3: Implement mutually exclusive target sources**

Extend CLI arguments with:

```python
source = parser.add_mutually_exclusive_group(required=True)
source.add_argument("--target-probe-root", type=Path)
source.add_argument("--target-observer-root", type=Path)
parser.add_argument("--observer-state-path", type=Path)
parser.add_argument("--heartbeat-max-age-seconds", type=float, default=5.0)
```

When observer mode is selected, instantiate `ObserverEventAdapter` and pass
`adapter.poll()` into the existing coordinator loop. Preserve probe mode
unchanged.

Update the Bash runner to select arguments from `TARGET_SOURCE`, while keeping
`SHADOW_ACTIVE=0` observation mode as the default.

- [ ] **Step 4: Run focused tests and verify pass**

Run the Task 4 test command. Expected: all focused tests pass.

### Task 5: Best-effort report classification

**Files:**
- Create: `tools/report_best_effort_status.py`
- Create: `tests/test_best_effort_status.py`
- Modify: `docs/LIVE_TWIN.md`

- [ ] **Step 1: Add failing classification tests**

Given account-term mismatches and observer-derived target events, assert:

```python
assert report["mode"] == "BEST_EFFORT"
assert report["formal_certification_eligible"] is False
assert report["broker_terms"] == ["account_leverage", "symbol_swap_mode"]
assert "originating_request_payload" in report["capture_limits"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest tests\test_best_effort_status.py -q
```

Expected: tool/module is missing.

- [ ] **Step 3: Implement concise status report**

Read the account-term JSON, adapter state, coordinator state and latest paired
cycle reports. Write a JSON status that never reports formal `PASS` when using
observer inference or mismatched broker terms.

- [ ] **Step 4: Run test and verify pass**

Run the Task 5 test command. Expected: pass.

### Task 6: Package, deploy and commission

**Files:**
- Modify: `scripts/package_live_twin.ps1` only if new required files are not
  already included by its Python-module copy logic.
- Deploy: VPS package, runner, environment and systemd services.

- [ ] **Step 1: Run the complete focused regression suite**

Run:

```powershell
python -m pytest tests\test_observer_adapter.py tests\test_shadow_coordinator.py tests\test_live_twin.py tests\test_live_twin_gate.py tests\test_live_twin_deployment_contract.py tests\test_best_effort_status.py -q
```

Expected: zero failures.

- [ ] **Step 2: Build and checksum the package**

Run:

```powershell
& .\scripts\package_live_twin.ps1
Get-FileHash .\artifacts\StraddleLiveTwin.zip -Algorithm SHA256
```

- [ ] **Step 3: Deploy in observation-only mode**

Install the adapter, CLI, runner and environment on the VPS. Keep:

```text
SHADOW_ACTIVE=0
TARGET_SOURCE=observer
```

Start the coordinator and verify for at least five live polling intervals:

- healthy target heartbeat;
- no target-side writes;
- persisted adapter cursor advances;
- no command file is written;
- the current active cycle is seeded and skipped.

- [ ] **Step 4: Enable the demo for the next clean cycle**

Confirm account `901111` is flat, expected-login guard is active, and MT5 Algo
Trading is enabled only in the isolated shadow terminal. Set
`SHADOW_ACTIVE=1`, restart only the coordinator, and verify it remains waiting
for a target flat transition followed by a fresh B1/S1 pair.

- [ ] **Step 5: Start continuous comparison**

Enable a best-effort status timer. Confirm reports explicitly retain:

- leverage mismatch;
- swap-mode mismatch;
- observer-inference capture limit;
- formal certification ineligible.

Record service states, report paths and package checksum for handoff.
