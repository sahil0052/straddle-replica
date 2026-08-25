# Exact-Real StraddleReplica Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a dedicated real-account `StraddleReplica_REAL_EXACT.ex5`
that uses exactly the same strategy engine and `LATEST_30` profile as the demo
build while defaulting the demo-account gate to off.

**Architecture:** Move the existing input declarations and MT5 event-handler
wiring into one shared include. Keep two thin wrappers: the existing demo
wrapper defines the account-gate default as `true`, while the new real wrapper
defines it as `false`. Add a real-exact preset, independent build script, and
reproducible package script; do not deploy or execute any trades.

**Tech Stack:** MQL5, Python 3/pytest, PowerShell, MetaEditor 5.

---

### Task 1: Add real/demo wrapper contract regressions

**Files:**
- Modify: `tests/test_mql5_contract.py`
- Create: `mql5/include/StraddleReplicaApp.mqh`
- Modify: `mql5/StraddleReplica.mq5`
- Create: `mql5/StraddleReplicaReal.mq5`

- [ ] **Step 1: Write failing wrapper tests**

Add paths and a helper near the top of `tests/test_mql5_contract.py`:

```python
APP = ROOT / "mql5" / "include" / "StraddleReplicaApp.mqh"
REAL_MAIN = ROOT / "mql5" / "StraddleReplicaReal.mq5"


def app_source() -> str:
    return APP.read_text(encoding="utf-8")
```

Change tests that inspect inputs and event handlers to use `app_source()`.
Replace the existing demo-account default assertion with:

```python
def test_demo_and_real_wrappers_share_app_with_distinct_account_defaults():
    demo = MAIN.read_text(encoding="utf-8")
    real = REAL_MAIN.read_text(encoding="utf-8")
    app = app_source()

    assert "#define STR_REQUIRE_DEMO_DEFAULT true" in demo
    assert '#include "include/StraddleReplicaApp.mqh"' in demo
    assert "#define STR_REQUIRE_DEMO_DEFAULT false" in real
    assert '#include "include/StraddleReplicaApp.mqh"' in real
    assert "input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT" in app
    assert "runtime.require_demo_account=RequireDemoAccount" in app
```

Keep the engine assertions proving that `RequireDemoAccount=true` still
enforces `ACCOUNT_TRADE_MODE_DEMO`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest `
  tests/test_mql5_contract.py::test_main_ea_exposes_required_inputs_and_event_handlers `
  tests/test_mql5_contract.py::test_demo_and_real_wrappers_share_app_with_distinct_account_defaults `
  -q
```

Expected: failure because `StraddleReplicaApp.mqh` and
`StraddleReplicaReal.mq5` do not exist.

- [ ] **Step 3: Extract the shared application include**

Create `mql5/include/StraddleReplicaApp.mqh` from the current
`StraddleReplica.mq5` implementation, starting with:

```cpp
#ifndef STR_REQUIRE_DEMO_DEFAULT
   #define STR_REQUIRE_DEMO_DEFAULT true
#endif

#include "StraddleTypes.mqh"
#include "StraddleEngine.mqh"
```

Move every existing `input` declaration, `CStraddleEngine g_engine`, and the
five event handlers into this include. Change only:

```cpp
input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT;
```

Do not change any other input default or runtime mapping.

- [ ] **Step 4: Replace the demo wrapper**

Reduce `mql5/StraddleReplica.mq5` to:

```cpp
//+------------------------------------------------------------------+
//|                                            StraddleReplica.mq5    |
//| Structural reconstruction from MT5 account 901018 trade history  |
//+------------------------------------------------------------------+
#property copyright "StraddleReplica"
#property version   "1.00"
#property strict
#property description "Configurable XAUUSD hedging stop-grid replica."

#define STR_REQUIRE_DEMO_DEFAULT true
#include "include/StraddleReplicaApp.mqh"
```

- [ ] **Step 5: Add the real wrapper**

Create `mql5/StraddleReplicaReal.mq5`:

```cpp
//+------------------------------------------------------------------+
//|                                        StraddleReplicaReal.mq5    |
//| Real-account exact-pattern candidate; use at the user's risk      |
//+------------------------------------------------------------------+
#property copyright "StraddleReplica"
#property version   "1.00"
#property strict
#property description "Real-account LATEST_30 target-pattern candidate."

#define STR_REQUIRE_DEMO_DEFAULT false
#include "include/StraddleReplicaApp.mqh"
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_mql5_contract.py -q
```

Expected: all MQL contract tests pass.

### Task 2: Add the real-exact preset and reproducible build/package flow

**Files:**
- Create: `tests/test_real_exact_contract.py`
- Create: `profiles/latest_30_real_exact.set`
- Create: `scripts/build_real.ps1`
- Create: `scripts/package_real_exact.ps1`
- Create: `docs/REAL_EXACT.md`
- Modify: `README.md`

- [ ] **Step 1: Write failing real-package contract tests**

Create `tests/test_real_exact_contract.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REAL_MAIN = ROOT / "mql5" / "StraddleReplicaReal.mq5"
APP = ROOT / "mql5" / "include" / "StraddleReplicaApp.mqh"
PRESET = ROOT / "profiles" / "latest_30_real_exact.set"
BUILD = ROOT / "scripts" / "build_real.ps1"
PACKAGE = ROOT / "scripts" / "package_real_exact.ps1"
DOC = ROOT / "docs" / "REAL_EXACT.md"


def test_real_entrypoint_changes_only_the_account_gate_default():
    real = REAL_MAIN.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    assert "#define STR_REQUIRE_DEMO_DEFAULT false" in real
    assert '#include "include/StraddleReplicaApp.mqh"' in real
    assert "input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT" in app


def test_real_exact_preset_preserves_replica_behavior_without_optional_safety():
    preset = PRESET.read_text(encoding="utf-8")

    for required in (
        "Profile=4",
        "TradeSymbol=XAUUSD",
        "ReplicaMode=true",
        "InterOrderDelayMs=100",
        "TelemetryEnabled=true",
        "RequireDemoAccount=false",
        "ExpectedAccountLogin=0",
        "SafetyEnabled=false",
    ):
        assert required in preset


def test_real_build_and_package_are_separate_from_demo_artifacts():
    build = BUILD.read_text(encoding="utf-8")
    package = PACKAGE.read_text(encoding="utf-8")
    documentation = DOC.read_text(encoding="utf-8")

    assert "StraddleReplicaReal.mq5" in build
    assert "StraddleReplicaReal.ex5" in build
    assert "compile-real.log" in build
    assert "StraddleReplica_REAL_EXACT.ex5" in package
    assert "latest_30_real_exact.set" in package
    assert "StraddleReplica-REAL-EXACT-20260808.zip" in package
    assert "approximately 92%" in documentation
    assert "proven 100%" in documentation
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_real_exact_contract.py -q
```

Expected: failures because the preset, scripts, and real documentation are
missing.

- [ ] **Step 3: Add the exact-real preset**

Create `profiles/latest_30_real_exact.set`:

```ini
Profile=4
TradeSymbol=XAUUSD
MagicNumber=901018
ReplicaMode=true
ReplicaStartTime=0
InterOrderDelayMs=100
DeviationPoints=100
TelemetryEnabled=true
RuntimeMode=0
RequireDemoAccount=false
ExpectedAccountLogin=0
SafetyEnabled=false
```

- [ ] **Step 4: Add the real build script**

Create `scripts/build_real.ps1` using the existing `build.ps1` structure with:

```powershell
$sourcePath = Join-Path $Workspace "mql5\StraddleReplicaReal.mq5"
$outputPath = Join-Path $Workspace "mql5\StraddleReplicaReal.ex5"
$logPath = Join-Path $Workspace "artifacts\compile-real.log"
```

Require `Result: 0 errors, 0 warnings` and fail if the real EX5 is absent.

- [ ] **Step 5: Add the real-account handoff documentation**

Create `docs/REAL_EXACT.md` containing:

- the approximate 92% behavioral estimate;
- 100% observed deployment sequence/geometry evidence;
- 95-97% stop-rule evidence;
- unresolved basket, simultaneous rearm, and broker-execution differences;
- explicit notice that the build is not a proven 100% clone;
- installation steps;
- hedging and 60-pending-order requirements;
- notice that optional safety is disabled;
- instruction to keep Experts, Journal, and telemetry logs.

- [ ] **Step 6: Add the packaging script**

Create `scripts/package_real_exact.ps1` that:

1. Calls `scripts/build_real.ps1`.
2. Recreates only
   `artifacts/real/StraddleReplica-REAL-EXACT-20260808`.
3. Copies and renames `mql5/StraddleReplicaReal.ex5` to
   `StraddleReplica_REAL_EXACT.ex5`.
4. Copies `profiles/latest_30_real_exact.set` as
   `LATEST_30_REAL_EXACT.set`.
5. Copies the real wrapper, shared app include, engine includes, and
   `docs/REAL_EXACT.md`.
6. Generates `SHA256SUMS.txt`.
7. Creates
   `artifacts/StraddleReplica-REAL-EXACT-20260808.zip`.

The script must use native PowerShell file operations and must not access the
VPS, MT5 terminal configuration, or account credentials.

- [ ] **Step 7: Update the root README**

Add the real package to the contents list and state that it is a manual,
risk-accepted build with optional safety disabled and an approximately 92%
behavioral estimate.

- [ ] **Step 8: Run contract tests and verify GREEN**

Run:

```powershell
python -m pytest `
  tests/test_real_exact_contract.py `
  tests/test_mql5_contract.py `
  tests/test_docs_contract.py `
  -q
```

Expected: all selected tests pass.

### Task 3: Compile, package, and verify the exact-real artifact

**Files:**
- Generate: `mql5/StraddleReplica.ex5`
- Generate: `mql5/StraddleReplicaReal.ex5`
- Generate: `artifacts/compile.log`
- Generate: `artifacts/compile-real.log`
- Generate: `artifacts/real/StraddleReplica-REAL-EXACT-20260808/*`
- Generate: `artifacts/StraddleReplica-REAL-EXACT-20260808.zip`

- [ ] **Step 1: Compile the demo build**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
```

Expected: `0 errors, 0 warnings`.

- [ ] **Step 2: Compile and package the real build**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package_real_exact.ps1
```

Expected: real compilation reports `0 errors, 0 warnings` and the ZIP exists.

- [ ] **Step 3: Run focused verification**

Run:

```powershell
python -m pytest `
  tests/test_profiles.py `
  tests/test_mql5_contract.py `
  tests/test_real_exact_contract.py `
  tests/test_demo_vps_contract.py `
  tests/test_docs_contract.py `
  -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run the non-fixture repository suite**

Run:

```powershell
python -m pytest -q -k "not test_recent_anchor_selection_excludes_partial_30_level_deployment and not test_compare_geometry_cli_can_include_rearmed_orders and not test_compare_tester_cli_writes_aligned_lifecycle_summary and not test_compare_telemetry_cli_writes_position_level_alignment and not test_recent_report_rearms_and_working_orders_match_cycle_geometry and not test_detects_deployment_spanning_history_and_working_orders and not test_partial_latest_deployment_keeps_expected_30_level_profile"
```

Expected: all collected non-fixture tests pass.

- [ ] **Step 5: Verify artifact integrity**

Confirm:

- both compile logs contain `0 errors, 0 warnings`;
- packaged source hashes match workspace source hashes;
- `StraddleReplica_REAL_EXACT.ex5` matches
  `mql5/StraddleReplicaReal.ex5`;
- `LATEST_30_REAL_EXACT.set` contains `RequireDemoAccount=false` and
  `SafetyEnabled=false`;
- the ZIP contains no private key, password, token, account credential, or
  environment file.

- [ ] **Step 6: Final production review**

Review only the changed wrappers, shared app include, preset, scripts, tests,
documentation, and generated package. Approve only for manual real-account use;
do not claim formal 100% parity and do not deploy or run the EA.

No commit step is included because this workspace is not a Git repository and
the user did not request repository history changes.
