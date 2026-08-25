# Recovery Fidelity Gap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove and implement the target's exact side-specific 2x recovery behavior without guessing, then qualify the candidate only from complete eligible paired cycles.

**Architecture:** Keep read-only evidence reconstruction in Python and deterministic trading behavior in MQL5. The analyzer accepts immutable MT5 history/rate exports, segments only exact LATEST_30 cycles, reconstructs state strictly from each cycle boundary, and emits machine-readable recovery episodes. MQL5 changes are allowed only after those episodes identify a trigger and per-level reset rule with negative controls.

**Tech Stack:** Python 3.12, pytest, MetaTrader5 read-only collector, MQL5/MetaEditor, PowerShell deployment scripts.

**Repository note:** This workspace has no `.git` metadata. Preserve user files, use targeted patches, record SHA256 hashes, and review exact changed files instead of committing.

---

### Task 1: Reusable cycle-bounded recovery analyzer

**Files:**
- Create: `straddle_replica/recovery_analysis.py`
- Create: `tools/analyze_target_recovery.py`
- Create: `tests/test_recovery_analysis.py`

- [ ] **Step 1: Write failing cycle-boundary and geometry tests**

Test a deal before `cycle_started_msc`, an exact B1/S1 through B30/S30 base deployment, and a contaminated deployment with one wrong lot. Require the pre-cycle deal to be ignored and the contaminated deployment to be rejected.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
& 'C:\websites\mt5 2\tmp\independent-demo-venv\Scripts\python.exe' -m pytest tests/test_recovery_analysis.py -q
```

Expected: collection/import failure because `straddle_replica.recovery_analysis` does not exist.

- [ ] **Step 3: Implement the minimal analyzer API**

Provide:

```python
def latest_30_base_volume(level: int) -> float: ...
def find_latest_30_cycles(orders: Iterable[Mapping[str, Any]]) -> list[CycleWindow]: ...
def reconstruct_cycle_state(
    deals: Iterable[Mapping[str, Any]],
    *,
    cycle_started_msc: int,
    through_msc: int,
    magic: int,
    symbol: str,
) -> CycleState: ...
def find_recovery_episodes(
    orders: Iterable[Mapping[str, Any]],
    cycles: Sequence[CycleWindow],
) -> list[RecoveryEpisode]: ...
```

The first operation inside deal reconstruction must reject `time_msc < cycle_started_msc` before position or realized-P/L mutation.

- [ ] **Step 4: Add recovery lifecycle tests**

Cover:

- exact same-price base-to-2x pending replacement;
- side-specific activation;
- existing-position next rearm at 2x, followed by base volume;
- activation-pending level retaining 2x on the next rearm;
- no false activation from an isolated doubled rearm.

- [ ] **Step 5: Implement the CLI and verify GREEN**

The CLI reads exported JSONL only, writes JSON only when `--output` is supplied, and reports exact cycle/episode counts plus rejected geometries.

### Task 2: Read-only H1 rate backfill through the sole collector

**Files:**
- Modify: `straddle_replica/live_monitor.py`
- Modify: `straddle_replica/monitor_cli.py`
- Modify: `tests/test_live_monitor.py`

- [ ] **Step 1: Write failing adapter/config/CLI tests**

Require:

```python
LiveMonitorConfig(history_rates_timeframe="H1", history_rates_seed_days=60)
```

to call only `MetaTrader5.copy_rates_range`, normalize OHLC/tick-volume fields, and write `history-rates-H1-*.jsonl`. Reject a rates seed without a timeframe and unknown timeframe constants.

- [ ] **Step 2: Verify RED**

Run the three new focused tests and confirm failures are caused by the missing rates feature.

- [ ] **Step 3: Implement the minimal read-only capture**

Add rate fields:

```python
RATE_FIELDS = (
    "time", "open", "high", "low", "close",
    "tick_volume", "spread", "real_volume",
)
```

Capture once during initialization, after read-only account validation, through the existing collector process. Do not add any trading API.

- [ ] **Step 4: Verify GREEN and collector neighbors**

Run:

```powershell
& 'C:\websites\mt5 2\tmp\independent-demo-venv\Scripts\python.exe' -m pytest tests/test_live_monitor.py -q
```

### Task 3: Prove the recovery trigger and reset model

**Files:**
- Modify: `straddle_replica/recovery_analysis.py`
- Modify: `tools/analyze_target_recovery.py`
- Modify: `tests/test_recovery_analysis.py`
- Create: `artifacts/live/independent-demo-fidelity/target-recovery-backfill-analysis.json`

- [ ] **Step 1: Capture 60 days of target H1 bars**

Stop only `StraddleIndependentTargetCollector`, run the same read-only collector with the rate-backfill options into an isolated directory, and restart the normal collector immediately. Confirm connected/read-only/trade-disabled health and zero archive gaps after restart.

- [ ] **Step 2: Add failing indicator-discrimination tests**

Test standard H1 Parabolic SAR direction/flip calculations and require recovery episodes plus non-recovery drawdown controls to be classified separately.

- [ ] **Step 3: Evaluate candidate trigger families**

Evaluate, without fitting production constants:

- floating loss and cycle net;
- price/anchor and filled-level counts;
- H1 Parabolic SAR direction/flip;
- H1 candle/ATR volatility state;
- combinations supported by all positive episodes and negative controls.

Reject any rule with a deterministic historical contradiction.

- [ ] **Step 4: Persist the evidence verdict**

The JSON assessment must state the earliest causal trigger, selected side, multiplier, per-level persistence/reset, coverage, contradictions, and whether an EA change is authorized.

### Task 4: Minimal MQL5 recovery state machine

**Files:**
- Modify: `mql5/include/StraddleTypes.mqh`
- Modify: `mql5/include/ProfileCatalog.mqh`
- Modify: `mql5/include/StraddleEngine.mqh`
- Modify: `tests/test_mql5_contract.py`

- [ ] **Step 1: Write and verify a failing MQL5 contract regression**

Require only the behavior proven in Task 3: trigger evaluation, one selected side, exact 2.0 multiplier, same pending prices, and the proven per-level reset/persistence semantics.

- [ ] **Step 2: Implement one root-cause fix**

Add the smallest state required to represent recovery mode. Keep the fixed $30 basket, 20-second rearm gate, 20-second deployment cooldown, two-stage trailing, and base 0.01/0.06/0.15 tiers unchanged.

- [ ] **Step 3: Run focused and relevant Python suites**

Run the recovery tests, MQL5 contract tests, collector tests, deployment contract tests, and independent comparator tests.

- [ ] **Step 4: Compile MQL5**

Compile `mql5/StraddleReplica.mq5` with zero errors and zero warnings. Record the source, EX5, and package SHA256 hashes.

### Task 5: Safe deployment and formal qualification

**Files:**
- Modify only generated package/assessment/state artifacts after verification.

- [ ] **Step 1: Wait for the excluded candidate cycle to become naturally flat**

Do not manually close, cancel, modify, or send candidate orders. Do not toggle Algo Trading or EA inputs.

- [ ] **Step 2: Deploy only the exact candidate container**

Recreate only `straddle-fidelity-independent-demo`; prove unrelated container identities are unchanged, the exact VNC binding remains `127.0.0.1:15925`, restart count is zero, OOMKilled is false, `MT5_START=1`, and the loaded EX5 hash matches the package.

- [ ] **Step 3: Start qualification at the first new-cycle event**

Require exactly 60 unique B1/S1 through B30/S30 identities with no missing or duplicate slots. Persist `qualification_started_utc`, `active_cycle_id`, and `active_cycle_eligible=true`.

- [ ] **Step 4: Compare complete cycles ordinally**

Run:

```powershell
& 'C:\websites\mt5 2\tmp\independent-demo-venv\Scripts\python.exe' tools/compare_independent_cycles.py ...
```

Exclude `local-110971967-20260812T113748Z`. Report execution timing separately.

- [ ] **Step 5: Claim 99% only on formal evidence**

Require at least one complete eligible paired cycle, lifecycle fidelity >=99%, conditional logic fidelity >=99%, conditional coverage >=99%, and zero deterministic mismatches.
