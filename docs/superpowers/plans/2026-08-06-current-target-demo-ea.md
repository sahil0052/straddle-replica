# Current Target Demo EA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a generic demo-only EX5 matching the target's latest observed lifecycle timing and safely cleaning residual exposure before restart.

**Architecture:** Keep the existing `LATEST_30` grid and stop engine. Change only its lifecycle timing defaults, mirror those values in Python, and extract small owned-order/position operations so `CYCLE_RESTARTING` can clean residual exposure without resetting the original restart timer.

**Tech Stack:** MQL5, Python 3, pytest, PowerShell, MetaEditor 5.

---

### Task 1: Add failing lifecycle regressions

**Files:**
- Modify: `tests/test_profiles.py`
- Modify: `tests/test_mql5_contract.py`

- [ ] **Step 1: Change the Python profile expectations**

Assert the latest profile uses:

```python
assert profile.close_interval_seconds == 0
assert profile.restart_delay_seconds == 2
assert profile.rearm_delay_seconds == 2
```

- [ ] **Step 2: Change MQL profile expectations**

Assert `ProfileCatalog.mqh` contains:

```python
assert "config.close_interval_seconds=0" in profile
assert "config.restart_delay_ms=2000" in profile
assert "config.rearm_delay_seconds=2" in profile
```

- [ ] **Step 3: Add restart safety contract assertions**

Extract `StartCycle` and `CYCLE_RESTARTING` source sections and assert:

```python
assert "OwnedOrderCount()>0 || OwnedPositionCount()>0" in start_cycle
assert "TryCancelOneOwnedOrder()" in restarting
assert "TryCloseOneOwnedPosition()" in restarting
assert restarting.index("TryCancelOneOwnedOrder()") < restarting.index(
    "TryCloseOneOwnedPosition()"
)
assert restarting.index("OwnedPositionCount()>0") < restarting.index(
    "TimeCurrent()-m_restart_started_at"
)
```

- [ ] **Step 4: Run the regressions and confirm RED**

Run:

```powershell
python -m pytest tests/test_profiles.py::test_latest_profile_uses_recent_absolute_basket_and_close_cadence tests/test_mql5_contract.py::test_latest_profile_uses_recent_cancel_close_restart_lifecycle tests/test_mql5_contract.py::test_restart_state_cleans_residual_exposure_before_becoming_idle -q
```

Expected: failures showing the old `20`, `20000`, and missing restart cleanup.

### Task 2: Update current target lifecycle defaults

**Files:**
- Modify: `mql5/include/ProfileCatalog.mqh`
- Modify: `straddle_replica/profiles.py`

- [ ] **Step 1: Update MQL defaults**

Set:

```cpp
config.close_interval_seconds=0;
config.restart_delay_ms=2000;
config.rearm_delay_seconds=2;
```

- [ ] **Step 2: Update Python mirror**

Set:

```python
close_interval_seconds=0,
restart_delay_seconds=2,
rearm_delay_seconds=2,
```

- [ ] **Step 3: Run focused profile tests**

Run:

```powershell
python -m pytest tests/test_profiles.py -q
```

Expected: all profile tests pass.

### Task 3: Harden restart cleanup

**Files:**
- Modify: `mql5/include/StraddleEngine.mqh`

- [ ] **Step 1: Extract one-order cancellation**

Add a helper that selects the newest owned order, deletes it, logs the cancel,
and returns `true` whenever an owned order was found:

```cpp
bool TryCancelOneOwnedOrder(void)
  {
   for(int index=OrdersTotal()-1;index>=0;index--)
     {
      ulong ticket=OrderGetTicket(index);
      if(ticket==0 || !IsOwnedOrderSelected())
         continue;
      string comment=OrderGetString(ORDER_COMMENT);
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
      double price=OrderGetDouble(ORDER_PRICE_OPEN);
      if(m_gateway.DeleteOrder(ticket))
         LogEvent("cancel",comment,ticket,volume,price,comment);
      return true;
     }
   return false;
  }
```

- [ ] **Step 2: Extract one-position close**

Add a helper that selects the newest owned position, closes it with
`STR CLOSE`, records `m_last_close_at`, logs the close, and returns `true`
whenever an owned position was found.

- [ ] **Step 3: Reuse helpers in existing lifecycle methods**

Replace duplicated loops in `CancelOneOrder` and `CloseOnePosition` with the
helpers while preserving their existing state transitions.

- [ ] **Step 4: Add the normal start flat guard**

At the beginning of `StartCycle`, after the halted check:

```cpp
if(OwnedOrderCount()>0 || OwnedPositionCount()>0)
   return false;
```

- [ ] **Step 5: Clean residual exposure during restart**

Before checking elapsed restart time:

```cpp
if(OwnedOrderCount()>0)
  {
   TryCancelOneOwnedOrder();
   break;
  }
if(OwnedPositionCount()>0)
  {
   TryCloseOneOwnedPosition();
   break;
  }
```

Do not modify `m_restart_started_at` in this branch.

- [ ] **Step 6: Run focused contract tests**

Run:

```powershell
python -m pytest tests/test_mql5_contract.py tests/test_profiles.py -q
```

Expected: all tests pass.

### Task 4: Compile and produce the demo artifact

**Files:**
- Regenerate: `mql5/StraddleReplica.ex5`
- Regenerate: `artifacts/compile.log`
- Create: `artifacts/StraddleReplica_LATEST_30_CURRENT_DEMO.ex5`

- [ ] **Step 1: Compile**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 2: Run affected tests**

Run:

```powershell
python -m pytest tests/test_profiles.py tests/test_mql5_contract.py tests/test_demo_vps_contract.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Copy and hash the artifact**

Copy `mql5/StraddleReplica.ex5` to
`artifacts/StraddleReplica_LATEST_30_CURRENT_DEMO.ex5`, then calculate its
SHA-256 hash.

- [ ] **Step 4: Review changed files**

Confirm only the profile mirror, MQL engine, focused tests, compile output, and
final artifact changed.
