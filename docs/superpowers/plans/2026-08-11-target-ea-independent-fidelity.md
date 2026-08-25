# Target EA Independent-Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, measure, and demo-qualify the closest evidence-supported independent reconstruction of the target EA while leaving the existing losing VPS account untouched.

**Architecture:** Preserve the existing MQL5 strategy engine, but add idempotent cycle accounting, explicit lifecycle telemetry, canonical event normalization, causal comparison, and reproducible fidelity scoring. Run the corrected build in a new isolated VPS demo container, synchronize only clean cycle starts, and require 20 paired cycles plus 48 market-open hours before producing real-account candidate artifacts.

**Tech Stack:** MQL5/MetaEditor, Python 3.11, pytest, CSV/JSONL telemetry, PowerShell, OpenSSH, Docker/Wine/MT5, SHA-256 artifact fingerprints.

---

The workspace is not a Git repository. Do not initialize Git and do not commit.
At the end of each task, write a SHA-256 checkpoint under
`artifacts/checkpoints/2026-08-11-independent-fidelity/`.

The implementation must never send, modify, cancel, or close an order on:

- target investor account `901018`;
- existing VPS demo account `5054216668`;
- existing container `straddle-replica-demo-vps`.

Only the newly created isolated demo candidate may be reset or started by the
cycle coordinator.

## File map

New focused files:

- `straddle_replica/cycle_accounting.py`: Python reference implementation for
  unique-deal cycle P/L.
- `mql5/include/CycleDealLedger.mqh`: authoritative MQL5 cycle P/L calculator.
- `mql5/include/BasketEvaluator.mqh`: pure basket trigger evaluation.
- `mql5/include/StopScheduler.mqh`: pure stop-formula calculation.
- `straddle_replica/canonical_events.py`: canonical lifecycle schema,
  normalization, identity, and deduplication.
- `straddle_replica/fidelity_score.py`: strict and conditional lifecycle
  scoring.
- `straddle_replica/observer_health.py`: observer JSONL capture and
  market-open-hour health measurement.
- `straddle_replica/shadow_transport.py`: local-file and candidate-scoped SSH
  command/ack transports.
- `tools/build_fidelity_report.py`: aggregate JSON, Markdown, and mismatch
  register generator.
- `profiles/latest_30_fidelity.set`: target-behavior preset.
- `profiles/latest_30_real_safe.set`: intentionally safer real preset.
- `monitor/fidelity-candidate-startup.ini`: fresh candidate startup file.
- `deploy/vps-docker-candidate/compose.yaml`: isolated candidate container.
- `scripts/package_fidelity_candidate.ps1`: credential-free EX5 package.
- `scripts/package_fidelity_release.ps1`: bound real release package with no
  MQL source.
- `scripts/deploy_fidelity_candidate_vps.ps1`: candidate-only VPS deployment.
- `scripts/install_fidelity_monitor_tasks.ps1`: new read-only collector and
  candidate-scoped coordinator tasks.

Existing files modified:

- `mql5/include/StraddleTypes.mqh`
- `mql5/include/StraddleReplicaApp.mqh`
- `mql5/include/StraddleEngine.mqh`
- `mql5/include/ProfileCatalog.mqh`
- `straddle_replica/observer_adapter.py`
- `straddle_replica/shadow_coordinator.py`
- `straddle_replica/live_twin.py`
- `straddle_replica/live_twin_gate.py`
- `straddle_replica/best_effort_status.py`
- `tools/compare_live_twin.py`
- `tools/evaluate_live_twin_gate.py`
- `tools/run_shadow_coordinator.py`
- `docs/FIDELITY.md`
- `docs/LIVE_TWIN.md`
- `docs/REAL_EXACT.md`
- `README.md`

## Task 1: Make cycle realized profit idempotent

**Files:**

- Create: `straddle_replica/cycle_accounting.py`
- Create: `mql5/include/CycleDealLedger.mqh`
- Create: `tests/test_cycle_accounting.py`
- Modify: `tests/test_mql5_contract.py`
- Modify: `mql5/include/StraddleEngine.mqh`

- [ ] **Step 1: Write the failing Python duplicate-deal tests**

Create `tests/test_cycle_accounting.py`:

```python
from straddle_replica.cycle_accounting import calculate_cycle_realized


def test_cycle_realized_counts_each_owned_exit_deal_once() -> None:
    deals = [
        {
            "ticket": 1001,
            "time_msc": 1_700_000_000_100,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 1,
            "profit": 5.00,
            "swap": -0.10,
            "commission": -0.20,
            "fee": 0.0,
        },
        {
            "ticket": 1001,
            "time_msc": 1_700_000_000_100,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 1,
            "profit": 5.00,
            "swap": -0.10,
            "commission": -0.20,
            "fee": 0.0,
        },
        {
            "ticket": 1002,
            "time_msc": 1_700_000_000_200,
            "magic": 901018,
            "symbol": "XAUUSD",
            "entry": 2,
            "profit": -1.00,
            "swap": 0.0,
            "commission": -0.05,
            "fee": -0.01,
        },
    ]

    result = calculate_cycle_realized(
        deals,
        cycle_started_msc=1_700_000_000_000,
        magic=901018,
        symbol="XAUUSD",
    )

    assert result.unique_exit_deals == 2
    assert result.duplicate_deal_tickets == (1001,)
    assert result.net == 3.64


def test_cycle_realized_filters_time_magic_symbol_and_entry() -> None:
    base = {
        "time_msc": 1_700_000_000_100,
        "magic": 901018,
        "symbol": "XAUUSD",
        "entry": 1,
        "profit": 1.0,
        "swap": 0.0,
        "commission": 0.0,
        "fee": 0.0,
    }
    deals = [
        {"ticket": 1, **base},
        {"ticket": 2, **base, "time_msc": 1_699_999_999_999},
        {"ticket": 3, **base, "magic": 7},
        {"ticket": 4, **base, "symbol": "EURUSD"},
        {"ticket": 5, **base, "entry": 0},
    ]

    result = calculate_cycle_realized(
        deals,
        cycle_started_msc=1_700_000_000_000,
        magic=901018,
        symbol="XAUUSD",
    )

    assert result.net == 1.0
    assert result.unique_exit_deals == 1
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest tests\test_cycle_accounting.py -q
```

Expected: collection fails because `straddle_replica.cycle_accounting` does
not exist.

- [ ] **Step 3: Implement the Python reference calculator**

Create `straddle_replica/cycle_accounting.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any


EXIT_ENTRIES = {1, 2, 3}


@dataclass(frozen=True)
class CycleRealized:
    net: float
    unique_exit_deals: int
    duplicate_deal_tickets: tuple[int, ...]


def calculate_cycle_realized(
    deals: Iterable[Mapping[str, Any]],
    *,
    cycle_started_msc: int,
    magic: int,
    symbol: str,
) -> CycleRealized:
    rows = list(deals)
    seen: set[int] = set()
    duplicates: set[int] = set()
    total = 0.0
    accepted = 0
    for deal in rows:
        ticket = int(deal.get("ticket") or 0)
        if ticket <= 0:
            continue
        if ticket in seen:
            duplicates.add(ticket)
            continue
        seen.add(ticket)
        if int(deal.get("time_msc") or 0) < cycle_started_msc:
            continue
        if int(deal.get("magic") or 0) != magic:
            continue
        if str(deal.get("symbol") or "") != symbol:
            continue
        if int(deal.get("entry") or -1) not in EXIT_ENTRIES:
            continue
        accepted += 1
        total += sum(
            float(deal.get(field) or 0.0)
            for field in ("profit", "swap", "commission", "fee")
        )
    return CycleRealized(
        net=round(total, 10),
        unique_exit_deals=accepted,
        duplicate_deal_tickets=tuple(sorted(duplicates)),
    )
```

- [ ] **Step 4: Run the Python tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_cycle_accounting.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Add a failing MQL contract test**

Append to `tests/test_mql5_contract.py`:

```python
def test_cycle_realized_is_rebuilt_from_unique_history_deals():
    engine = ENGINE.read_text(encoding="utf-8")
    ledger = (
        ROOT / "mql5" / "include" / "CycleDealLedger.mqh"
    )
    assert ledger.exists()
    ledger_source = ledger.read_text(encoding="utf-8")

    assert '#include "CycleDealLedger.mqh"' in engine
    assert "long              m_cycle_started_msc;" in engine
    assert 'GlobalKey("start_msc")' in engine
    assert "m_deal_ledger.Recalculate(" in engine
    assert "m_cycle_realized+=" not in engine
    assert "DEAL_TIME_MSC" in ledger_source
    assert "DEAL_ENTRY_OUT" in ledger_source
    assert "DEAL_ENTRY_OUT_BY" in ledger_source
    assert "DEAL_ENTRY_INOUT" in ledger_source
    assert "DEAL_FEE" in ledger_source
```

- [ ] **Step 6: Run the MQL contract test and verify RED**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py `
  -k cycle_realized_is_rebuilt_from_unique_history_deals -q
```

Expected: fail because the ledger include and start-millisecond state do not
exist.

- [ ] **Step 7: Implement the MQL cycle ledger**

Create `mql5/include/CycleDealLedger.mqh`:

```cpp
#ifndef STRADDLE_CYCLE_DEAL_LEDGER_MQH
#define STRADDLE_CYCLE_DEAL_LEDGER_MQH

class CCycleDealLedger
  {
private:
   ulong  m_magic;
   string m_symbol;

public:
   void Configure(const ulong magic,const string symbol)
     {
      m_magic=magic;
      m_symbol=symbol;
     }

   double Recalculate(const long cycle_started_msc) const
     {
      if(cycle_started_msc<=0)
         return 0.0;
      datetime from=(datetime)(cycle_started_msc/1000);
      if(!HistorySelect(from,TimeCurrent()))
         return 0.0;
      double total=0.0;
      for(int index=0;index<HistoryDealsTotal();index++)
        {
         ulong ticket=HistoryDealGetTicket(index);
         if(ticket==0)
            continue;
         if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=m_magic ||
            HistoryDealGetString(ticket,DEAL_SYMBOL)!=m_symbol ||
            (long)HistoryDealGetInteger(ticket,DEAL_TIME_MSC)<
               cycle_started_msc)
            continue;
         ENUM_DEAL_ENTRY entry=
            (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
         if(entry!=DEAL_ENTRY_OUT &&
            entry!=DEAL_ENTRY_OUT_BY &&
            entry!=DEAL_ENTRY_INOUT)
            continue;
         total+=HistoryDealGetDouble(ticket,DEAL_PROFIT)
               +HistoryDealGetDouble(ticket,DEAL_SWAP)
               +HistoryDealGetDouble(ticket,DEAL_COMMISSION)
               +HistoryDealGetDouble(ticket,DEAL_FEE);
        }
      return total;
     }
  };

#endif
```

Modify `mql5/include/StraddleEngine.mqh`:

```cpp
#include "CycleDealLedger.mqh"
```

Add members:

```cpp
CCycleDealLedger  m_deal_ledger;
long              m_cycle_started_msc;
```

Configure the ledger after the symbol is selected:

```cpp
m_deal_ledger.Configure(m_runtime.magic,m_runtime.symbol);
```

At every new cycle start:

```cpp
m_cycle_started_at=TimeCurrent();
m_cycle_started_msc=(long)m_cycle_started_at*1000;
m_cycle_realized=0.0;
```

Persist and restore the start time:

```cpp
GlobalVariableSet(GlobalKey("start_msc"),(double)m_cycle_started_msc);
```

```cpp
m_cycle_started_msc=(
   GlobalVariableCheck(GlobalKey("start_msc"))
   ? (long)GlobalVariableGet(GlobalKey("start_msc"))
   : (long)TimeCurrent()*1000
);
m_cycle_started_at=(datetime)(m_cycle_started_msc/1000);
m_cycle_realized=m_deal_ledger.Recalculate(m_cycle_started_msc);
```

Delete the key in `ClearPersistence`:

```cpp
GlobalVariableDel(GlobalKey("start_msc"));
```

Replace callback increments with:

```cpp
m_cycle_realized=m_deal_ledger.Recalculate(m_cycle_started_msc);
PersistCycle();
```

Do not scan account history on every tick. Recalculate only during restore and
after an owned exit transaction; `OnTick` uses the latest persisted value.

- [ ] **Step 8: Verify the contract and compile**

Run:

```powershell
python -m pytest tests\test_cycle_accounting.py `
  tests\test_mql5_contract.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: tests pass and both compiler logs contain
`Result: 0 errors, 0 warnings`.

- [ ] **Step 9: Write the Task 1 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
New-Item -ItemType Directory -Force $root | Out-Null
Get-FileHash `
  straddle_replica\cycle_accounting.py,`
  mql5\include\CycleDealLedger.mqh,`
  mql5\include\StraddleEngine.mqh,`
  mql5\StraddleReplica.ex5,`
  mql5\StraddleReplicaReal.ex5 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-01-cycle-accounting.json"
```

## Task 2: Add stable cycle IDs and complete lifecycle telemetry

**Files:**

- Modify: `mql5/include/StraddleEngine.mqh`
- Modify: `tests/test_mql5_contract.py`
- Modify: `tests/test_live_twin_deployment_contract.py`

- [ ] **Step 1: Add failing telemetry contract tests**

Append to `tests/test_mql5_contract.py`:

```python
def test_normal_cycles_have_identity_sequence_and_basket_snapshot():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "ulong             m_event_sequence;" in engine
    assert "string NewCycleId(" in engine
    assert 'GlobalKey("event_seq")' in engine
    assert '"schema_version","event_sequence","event_id"' in engine
    assert '"deal_ticket","order_ticket","position_ticket"' in engine
    assert '"cycle_realized","floating_profit","cycle_net"' in engine
    assert '"basket_target","evidence_grade"' in engine
    assert 'LogLifecycleEvent("rearm_eligible"' in engine
    assert 'LogLifecycleEvent("basket_trigger"' in engine
    assert 'LogLifecycleEvent("cycle_complete"' in engine
    assert 'LogLifecycleEvent("cycle_restart"' in engine
```

- [ ] **Step 2: Run the new contract test and verify RED**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py `
  -k normal_cycles_have_identity_sequence_and_basket_snapshot -q
```

Expected: fail because telemetry schema version 4 is absent.

- [ ] **Step 3: Add cycle and event identity helpers**

Add to `CStraddleEngine`:

```cpp
string NewCycleId(const string prefix) const
  {
   MqlDateTime utc={};
   TimeToStruct(TimeGMT(),utc);
   return StringFormat(
      "%s-%I64u-%04d%02d%02dT%02d%02d%02dZ",
      prefix,
      (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
      utc.year,utc.mon,utc.day,utc.hour,utc.min,utc.sec
   );
  }

ulong NextEventSequence(void)
  {
   m_event_sequence++;
   GlobalVariableSet(GlobalKey("event_seq"),(double)m_event_sequence);
   return m_event_sequence;
  }

string EventId(const string kind,
               const ulong sequence,
               const ulong deal_ticket) const
  {
   if(deal_ticket>0)
      return StringFormat(
         "%s:deal:%I64u:%s",
         m_cycle_id,deal_ticket,kind
      );
   return StringFormat("%s:event:%I64u",m_cycle_id,sequence);
  }
```

Add and initialize:

```cpp
ulong m_event_sequence;
```

```cpp
m_event_sequence=0;
```

For normal cycle starts:

```cpp
m_cycle_id=NewCycleId("local");
m_event_sequence=0;
GlobalVariableSet(GlobalKey("event_seq"),0.0);
```

For restored cycles:

```cpp
m_event_sequence=(
   GlobalVariableCheck(GlobalKey("event_seq"))
   ? (ulong)GlobalVariableGet(GlobalKey("event_seq"))
   : 0
);
```

- [ ] **Step 4: Extend telemetry without removing legacy columns**

Keep the current columns, then append:

```cpp
"schema_version","event_sequence","event_id",
"deal_ticket","order_ticket","position_ticket",
"cycle_realized","floating_profit","cycle_net",
"basket_target","evidence_grade"
```

Extend the `WriteTelemetry` signature by appending:

```cpp
const ulong deal_ticket,
const ulong order_ticket,
const ulong position_ticket
```

Generate the appended values:

```cpp
ulong event_sequence=NextEventSequence();
string event_id=EventId(kind,event_sequence,deal_ticket);
double floating=OwnedFloatingProfit();
double basket_target=(
   m_profile.cycle_target_money>0.0
   ? m_profile.cycle_target_money
   : m_cycle_start_balance*
      m_profile.cycle_target_balance_pct/100.0
);
double cycle_net=m_cycle_realized+floating;
```

Use `FORMAL_CANDIDATE` as the candidate evidence grade. Because event
sequencing mutates state, remove `const` from `WriteTelemetry`, `LogEvent`,
`LogTradeRequest`, and any wrapper that calls `NextEventSequence`.

Append these arguments to the existing telemetry row's `FileWrite` call; do
not create a second CSV row:

```cpp
4,event_sequence,event_id,
deal_ticket,order_ticket,position_ticket,
DoubleToString(m_cycle_realized,8),
DoubleToString(floating,8),
DoubleToString(cycle_net,8),
DoubleToString(basket_target,8),
"FORMAL_CANDIDATE"
```

Update the telemetry call sites so deal events pass the broker deal ticket,
request events pass their order/position identity, and ordinary state events
pass zeroes.

- [ ] **Step 5: Emit explicit lifecycle events**

Add:

```cpp
void LogLifecycleEvent(const string kind,
                       const string level_key,
                       const string reason)
  {
   WriteTelemetry(
      kind,level_key,0,0.0,0.0,0.0,0.0,
      reason,0,0,0.0,0.0,0.0,
      0,0,0
   );
  }
```

When a stop exit schedules a level:

```cpp
ScheduleLevelRearm(level_comment);
LogLifecycleEvent("rearm_eligible",level_comment,"stop_exit");
```

Immediately before basket close:

```cpp
if(m_has_traded && target>0.0 && cycle_net>=target)
  {
   LogLifecycleEvent("basket_trigger","","threshold_reached");
   BeginClose("basket_target",false);
  }
```

When the cycle first becomes flat and transitions out of
cancellation/closing:

```cpp
LogLifecycleEvent("cycle_complete","","flat");
```

When `CYCLE_RESTARTING` finishes its delay and transitions to `CYCLE_IDLE`:

```cpp
LogLifecycleEvent("cycle_restart","","new_cycle");
```

Delete `GlobalKey("event_seq")` in `ClearPersistence` after the final
`cycle_complete` or `cycle_restart` event has been written.

- [ ] **Step 6: Run contract tests and compile**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py `
  tests\test_live_twin_deployment_contract.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: all focused tests pass and both builds compile with zero warnings.

- [ ] **Step 7: Write the Task 2 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  mql5\include\StraddleEngine.mqh,`
  mql5\StraddleReplica.ex5,`
  mql5\StraddleReplicaReal.ex5 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-02-lifecycle-telemetry.json"
```

## Task 3: Normalize and deduplicate target and candidate events

**Files:**

- Create: `straddle_replica/canonical_events.py`
- Create: `tests/test_canonical_events.py`
- Modify: `straddle_replica/observer_adapter.py`
- Modify: `straddle_replica/shadow_coordinator.py`
- Modify: `straddle_replica/live_twin.py`
- Modify: `tests/test_observer_adapter.py`
- Modify: `tests/test_shadow_coordinator.py`
- Modify: `tests/test_live_twin.py`

- [ ] **Step 1: Write failing canonicalization tests**

Create `tests/test_canonical_events.py`:

```python
from straddle_replica.canonical_events import canonicalize_events


def test_deal_ticket_is_the_primary_execution_identity() -> None:
    raw = [
        {
            "cycle_id": "cycle-1",
            "sequence": 1,
            "time_utc": "2026-08-11T00:00:00Z",
            "kind": "stop_exit",
            "comment": "STR B1",
            "deal_ticket": 7001,
            "position_ticket": 9001,
            "volume": 0.01,
            "accepted_price": 4400.0,
        },
        {
            "cycle_id": "cycle-1",
            "sequence": 2,
            "time_utc": "2026-08-11T00:00:00Z",
            "kind": "stop_exit",
            "comment": "STR B1",
            "deal_ticket": 7001,
            "position_ticket": 9001,
            "volume": 0.01,
            "accepted_price": 4400.0,
        },
    ]

    result = canonicalize_events(
        raw,
        source="candidate",
        evidence_grade="FORMAL_CANDIDATE",
        session_id="candidate-session",
    )

    assert len(result.events) == 1
    assert result.duplicate_event_ids == (
        "candidate:candidate-session:cycle-1:deal:7001:stop_exit",
    )
    assert result.events[0]["side"] == "buy"
    assert result.events[0]["level"] == 1


def test_legacy_price_and_ticket_fields_remain_supported() -> None:
    result = canonicalize_events(
        [
            {
                "cycle_id": "cycle-1",
                "sequence": 3,
                "time_utc": "2026-08-11T00:00:01Z",
                "kind": "fill",
                "comment": "STR S2",
                "deal": 8001,
                "ticket": 9002,
                "price": 4398.0,
                "volume": 0.01,
            }
        ],
        source="observer",
        evidence_grade="BEST_EFFORT",
        session_id="observer-session",
    )

    event = result.events[0]
    assert event["deal_ticket"] == 8001
    assert event["position_ticket"] == 9002
    assert event["accepted_price"] == 4398.0
    assert event["side"] == "sell"
    assert event["level"] == 2
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests\test_canonical_events.py -q
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement the canonical event module**

Create `straddle_replica/canonical_events.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


UTC = timezone.utc
COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")
EXECUTION_KINDS = {"fill", "stop_exit", "close_fill"}


@dataclass(frozen=True)
class CanonicalizationResult:
    events: tuple[dict[str, Any], ...]
    duplicate_event_ids: tuple[str, ...]
    invalid_rows: int


def _number(row: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _integer(row: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return int(value)
    return 0


def _level(row: Mapping[str, Any], parsed: int | None) -> int:
    value = row.get("level")
    if value in (None, ""):
        return int(parsed or 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(parsed or 0)


def _parse_comment(comment: str) -> tuple[str, int | None]:
    match = COMMENT_RE.fullmatch(comment)
    if match is None:
        return "", None
    return ("buy" if match.group(1) == "B" else "sell", int(match.group(2)))


def _time(value: object) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _fallback_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def canonicalize_event(
    row: Mapping[str, Any],
    *,
    source: str,
    evidence_grade: str,
    session_id: str,
) -> dict[str, Any]:
    kind = str(row.get("kind") or row.get("event_kind") or "")
    comment = str(row.get("comment") or row.get("entity_comment") or "")
    side, level = _parse_comment(comment)
    deal_ticket = _integer(row, "deal_ticket", "deal")
    legacy_ticket = _integer(row, "ticket")
    order_ticket = _integer(row, "order_ticket", "order")
    position_ticket = _integer(row, "position_ticket", "position")
    if kind in {"pending_request", "cancel_request"} and order_ticket == 0:
        order_ticket = legacy_ticket
    if kind in EXECUTION_KINDS and position_ticket == 0:
        position_ticket = legacy_ticket
    request_id = _integer(row, "request_id")
    sequence = _integer(row, "event_sequence", "sequence")
    cycle_id = str(row.get("cycle_id") or "")
    effective_session = str(row.get("session_id") or session_id)
    accepted_price = _number(
        row,
        "accepted_price",
        "price" if kind in EXECUTION_KINDS else "__missing__",
    )
    requested_price = _number(
        row,
        "requested_price",
        "price" if kind not in EXECUTION_KINDS else "__missing__",
    )
    if deal_ticket:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"deal:{deal_ticket}:{kind}"
        )
    elif request_id:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"request:{request_id}:{kind}"
        )
    elif order_ticket:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"order:{order_ticket}:{kind}"
        )
    elif sequence:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"sequence:{sequence}:{kind}"
        )
    else:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"hash:{_fallback_id(row)}"
        )
    return {
        "schema_version": 1,
        "event_id": identity,
        "source": source,
        "evidence_grade": evidence_grade,
        "session_id": effective_session,
        "cycle_id": cycle_id,
        "sequence": sequence,
        "time_utc": _time(row.get("time_utc") or row.get("utc_time")),
        "server_time": str(row.get("server_time") or ""),
        "kind": kind,
        "comment": comment,
        "side": str(row.get("side") or side),
        "level": _level(row, level),
        "volume": _number(row, "volume"),
        "requested_price": requested_price,
        "accepted_price": accepted_price,
        "sl": _number(row, "sl"),
        "tp": _number(row, "tp"),
        "order_ticket": order_ticket,
        "position_ticket": position_ticket,
        "deal_ticket": deal_ticket,
        "request_id": request_id,
        "retcode": _integer(row, "retcode"),
        "commission": _number(row, "commission"),
        "swap": _number(row, "swap"),
        "fee": _number(row, "fee"),
        "profit": _number(row, "profit"),
        "cycle_realized": _number(row, "cycle_realized"),
        "floating_profit": _number(row, "floating_profit"),
        "cycle_net": _number(row, "cycle_net"),
        "basket_target": _number(row, "basket_target"),
    }


def canonicalize_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str,
    evidence_grade: str,
    session_id: str,
) -> CanonicalizationResult:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    invalid = 0
    for row in rows:
        try:
            event = canonicalize_event(
                row,
                source=source,
                evidence_grade=evidence_grade,
                session_id=session_id,
            )
        except (TypeError, ValueError):
            invalid += 1
            continue
        if event["event_id"] in seen:
            duplicates.add(event["event_id"])
            continue
        seen.add(event["event_id"])
        events.append(event)
    events.sort(key=lambda event: (event["time_utc"], event["sequence"]))
    return CanonicalizationResult(
        events=tuple(events),
        duplicate_event_ids=tuple(sorted(duplicates)),
        invalid_rows=invalid,
    )
```

- [ ] **Step 4: Run canonicalization tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_canonical_events.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Route observer, probe, and candidate loaders through the schema**

In `observer_adapter.py`, add these fields to `_base_event`:

```python
"evidence_grade": "BEST_EFFORT",
"deal_ticket": 0,
"order_ticket": 0,
"position_ticket": 0,
```

Map accepted entities explicitly:

```python
event["order_ticket"] = ticket
event["position_ticket"] = position_id
event["deal_ticket"] = deal_ticket
```

In `shadow_coordinator.load_probe_events`, emit:

```python
"evidence_grade": "FORMAL",
"order_ticket": int(row.get("trans_order") or 0),
"position_ticket": int(
    row.get("trans_position")
    or row.get("request_position")
    or 0
),
"deal_ticket": int(row.get("trans_deal") or 0),
```

Add stream loaders:

```python
def load_jsonl_event_stream(path: Path) -> CanonicalizationResult: ...
def load_demo_telemetry_stream(path: Path) -> CanonicalizationResult: ...
```

These functions collect raw rows and call `canonicalize_events`. Keep the
existing compatibility wrappers:

```python
def load_jsonl_events(path: Path) -> list[dict[str, Any]]:
    return list(load_jsonl_event_stream(path).events)


def load_demo_telemetry_events(path: Path) -> list[dict[str, Any]]:
    return list(load_demo_telemetry_stream(path).events)
```

`tools/compare_live_twin.py` must use the stream functions and pass duplicate
and invalid-row metadata into `compare_paired_cycles`. A nonempty duplicate
identity list or nonzero invalid-row count makes the affected cycle
`INVALID`.

Extend the comparator signature with:

```python
target_capture: CanonicalizationResult | None = None,
demo_capture: CanonicalizationResult | None = None,
```

and inspect those fields before lifecycle comparison.

- [ ] **Step 6: Update loader and adapter tests**

Add assertions:

```python
assert stop["deal_ticket"] == 502
assert stop["position_ticket"] == 1001
assert stop["evidence_grade"] == "BEST_EFFORT"
```

Add a duplicate candidate CSV row test that asserts one canonical execution
event and one duplicate identity.

- [ ] **Step 7: Run the complete normalization regression set**

Run:

```powershell
python -m pytest `
  tests\test_canonical_events.py `
  tests\test_observer_adapter.py `
  tests\test_shadow_coordinator.py `
  tests\test_live_twin.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Write the Task 3 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  straddle_replica\canonical_events.py,`
  straddle_replica\observer_adapter.py,`
  straddle_replica\shadow_coordinator.py,`
  straddle_replica\live_twin.py `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-03-canonical-events.json"
```

## Task 4: Add strict fidelity scoring and execution causality

**Files:**

- Create: `straddle_replica/fidelity_score.py`
- Create: `tests/test_fidelity_score.py`
- Modify: `straddle_replica/live_twin.py`
- Modify: `tests/test_live_twin.py`
- Modify: `tools/compare_live_twin.py`
- Modify: `straddle_replica/best_effort_status.py`
- Modify: `tests/test_best_effort_status.py`

- [ ] **Step 1: Write failing fidelity-score tests**

Create `tests/test_fidelity_score.py`:

```python
import pytest

from straddle_replica.fidelity_score import score_lifecycle


def event(kind: str, comment: str, *, classification: str = "") -> dict:
    side = "buy" if " B" in comment else "sell"
    level = int(comment[5:]) if comment else 0
    return {
        "kind": kind,
        "comment": comment,
        "side": side if comment else "",
        "level": level,
        "volume": 0.01 if comment else 0.0,
        "requested_price": 4400.0 if "request" in kind else 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "comparison_class": classification,
    }


def test_exact_lifecycle_scores_one_hundred_percent() -> None:
    target = [event("initial_pending_request", "STR B1")]
    candidate = [dict(target[0])]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] == 100.0
    assert score["conditional"]["f1_percent"] == 100.0
    assert score["conditional"]["coverage_percent"] == 100.0


def test_extra_and_missing_events_reduce_strict_f1() -> None:
    target = [
        event("initial_pending_request", "STR B1"),
        event("initial_pending_request", "STR S1"),
    ]
    candidate = [
        event("initial_pending_request", "STR B1"),
        event("rearm_request", "STR B2"),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["matched"] == 1
    assert score["strict"]["precision_percent"] == 50.0
    assert score["strict"]["recall_percent"] == 50.0
    assert score["strict"]["f1_percent"] == 50.0


def test_execution_diverged_events_remain_in_strict_score_only() -> None:
    target = [
        event("stop_request", "STR B1"),
        event(
            "rearm_request",
            "STR B1",
            classification="EXECUTION_DIVERGED",
        ),
    ]
    candidate = [
        event("stop_request", "STR B1"),
        event(
            "rearm_request",
            "STR B2",
            classification="EXECUTION_DIVERGED",
        ),
    ]

    score = score_lifecycle(target, candidate)

    assert score["strict"]["f1_percent"] == 50.0
    assert score["conditional"]["f1_percent"] == 100.0
    assert score["conditional"]["coverage_percent"] == 50.0
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests\test_fidelity_score.py -q
```

Expected: import failure because `fidelity_score.py` does not exist.

- [ ] **Step 3: Implement deterministic sequence scoring**

Create `straddle_replica/fidelity_score.py`:

```python
from __future__ import annotations

from typing import Any, Iterable


SCORABLE_KINDS = {
    "cycle_start",
    "initial_pending_request",
    "fill",
    "stop_request",
    "stop_exit",
    "rearm_eligible",
    "rearm_request",
    "basket_trigger",
    "cancel_request",
    "close_request",
    "close_fill",
    "cycle_complete",
    "cycle_restart",
}


def _signature(event: dict[str, Any]) -> tuple[Any, ...]:
    decision = str(event.get("kind") or "").endswith("request")
    return (
        str(event.get("kind") or ""),
        str(event.get("comment") or ""),
        str(event.get("side") or ""),
        int(event.get("level") or 0),
        round(float(event.get("volume") or 0.0), 8),
        round(float(event.get("requested_price") or 0.0), 8)
        if decision
        else 0.0,
        round(float(event.get("sl") or 0.0), 8)
        if str(event.get("kind") or "") == "stop_request"
        else 0.0,
        round(float(event.get("tp") or 0.0), 8),
    )


def _sequence(events: Iterable[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        _signature(event)
        for event in events
        if str(event.get("kind") or "") in SCORABLE_KINDS
    ]


def _lcs_count(
    left: list[tuple[Any, ...]],
    right: list[tuple[Any, ...]],
) -> int:
    previous = [0] * (len(right) + 1)
    for left_item in left:
        current = [0]
        for index, right_item in enumerate(right, start=1):
            if left_item == right_item:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _score(
    target: list[tuple[Any, ...]],
    candidate: list[tuple[Any, ...]],
) -> dict[str, float | int]:
    matched = _lcs_count(target, candidate)
    precision = matched / len(candidate) if candidate else 0.0
    recall = matched / len(target) if target else 0.0
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "target_events": len(target),
        "candidate_events": len(candidate),
        "matched": matched,
        "precision_percent": round(precision * 100.0, 4),
        "recall_percent": round(recall * 100.0, 4),
        "f1_percent": round(f1 * 100.0, 4),
    }


def score_lifecycle(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
) -> dict[str, Any]:
    strict_target = _sequence(target_events)
    strict_candidate = _sequence(candidate_events)
    conditional_target = _sequence(
        event
        for event in target_events
        if event.get("comparison_class") != "EXECUTION_DIVERGED"
    )
    conditional_candidate = _sequence(
        event
        for event in candidate_events
        if event.get("comparison_class") != "EXECUTION_DIVERGED"
    )
    conditional = _score(conditional_target, conditional_candidate)
    denominator = max(len(strict_target), len(strict_candidate), 1)
    conditional["coverage_percent"] = round(
        max(len(conditional_target), len(conditional_candidate))
        / denominator
        * 100.0,
        4,
    )
    return {
        "strict": _score(strict_target, strict_candidate),
        "conditional": conditional,
    }
```

- [ ] **Step 4: Run score tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_fidelity_score.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Separate logic status from execution status**

In `compare_paired_cycles`:

```python
logic_status = "FAIL" if deterministic_mismatches else "PASS"
execution_status = "DIFFERENT" if execution_mismatches else "PASS"
```

Keep `INVALID` and `UNPAIRED` behavior. For complete cycles:

```python
status = logic_status
```

Find the first execution mismatch time. Mark later target and candidate
lifecycle events:

```python
event["comparison_class"] = "EXECUTION_DIVERGED"
```

only after a paired fill/exit differs in count, side, volume, accepted price,
or time. Earlier deterministic mismatches remain `DETERMINISTIC`.

Collect the paired event times while building execution mismatches, then use:

```python
def _mark_execution_divergence(
    target_events: list[dict[str, Any]],
    candidate_events: list[dict[str, Any]],
    divergence_at: datetime | None,
) -> None:
    if divergence_at is None:
        return
    for event in [*target_events, *candidate_events]:
        if _parse_time(event["time_utc"]) >= divergence_at:
            event["comparison_class"] = "EXECUTION_DIVERGED"
```

`divergence_at` is the earliest target or candidate time from the first paired
execution mismatch.

Before scoring, change `_classify_decisions` so the first request for a level
is copied with:

```python
canonical["kind"] = "initial_pending_request"
```

and later eligible requests remain `rearm_request`. Score those classified
decision copies together with fills, exits, and cycle-boundary events.

Add to the report:

```python
"logic_status": logic_status,
"execution_status": execution_status,
"fidelity": score_lifecycle(target_events, demo_events),
"evidence_grade": (
    "FORMAL"
    if all(event.get("evidence_grade") == "FORMAL" for event in target_events)
    else "BEST_EFFORT"
),
```

- [ ] **Step 6: Update comparator tests**

Change the fill-tolerance test to assert:

```python
assert report["status"] == "PASS"
assert report["logic_status"] == "PASS"
assert report["execution_status"] == "DIFFERENT"
assert report["execution_mismatch_count"] == 1
```

Add an extra/missing lifecycle test that asserts strict fidelity is below
100%, while a pure accepted-price mismatch does not create a deterministic
failure.

- [ ] **Step 7: Expose the score in tools and status**

`tools/compare_live_twin.py` must include aggregate strict and conditional
scores in its stdout summary.

`best_effort_status.py` must include:

```python
latest = comparisons[-1] if comparisons else {}
fidelity = dict(latest.get("fidelity") or {})
strict = dict(fidelity.get("strict") or {})
conditional = dict(fidelity.get("conditional") or {})
```

and:

```python
"strict_lifecycle_fidelity_percent": float(
    strict.get("f1_percent") or 0.0
),
"conditional_logic_fidelity_percent": float(
    conditional.get("f1_percent") or 0.0
),
"conditional_coverage_percent": float(
    conditional.get("coverage_percent") or 0.0
),
```

and retain `mode="BEST_EFFORT"` when the target source is the investor
observer.

- [ ] **Step 8: Run comparator regressions**

Run:

```powershell
python -m pytest `
  tests\test_fidelity_score.py `
  tests\test_live_twin.py `
  tests\test_best_effort_status.py `
  tests\test_live_twin_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 9: Write the Task 4 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  straddle_replica\fidelity_score.py,`
  straddle_replica\live_twin.py,`
  straddle_replica\best_effort_status.py,`
  tools\compare_live_twin.py `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-04-fidelity-score.json"
```

## Task 5: Fail closed on duplicate level identities

**Files:**

- Modify: `mql5/include/StraddleTypes.mqh`
- Modify: `mql5/include/StraddleEngine.mqh`
- Modify: `tests/test_mql5_contract.py`
- Modify: `tests/test_live_twin.py`

- [ ] **Step 1: Add a failing MQL contract test**

Append:

```python
def test_duplicate_active_level_identity_blocks_new_placement():
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")

    assert "int               active_order_count;" in types
    assert "int               active_position_count;" in types
    assert "bool              duplicate_identity;" in types
    assert "DetectDuplicateLevelIdentity" in engine
    assert '"duplicate_level_identity"' in engine
    assert "if(level_state.duplicate_identity)" in engine
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py `
  -k duplicate_active_level_identity_blocks_new_placement -q
```

Expected: fail because the level-state counters do not exist.

- [ ] **Step 3: Extend level state**

Add to `SLevelState`:

```cpp
int               active_order_count;
int               active_position_count;
bool              duplicate_identity;
```

Reset the fields in `ResetLevelState` and `ClearLiveFlags`.

- [ ] **Step 4: Count identities during reconciliation**

When an order or position maps to a level:

```cpp
level_state.active_order_count++;
level_state.active_position_count++;
```

`ClearLiveFlags` resets the two counters but preserves
`duplicate_identity`; only `ResetLevelState` initializes it to `false`.

After reconciliation:

```cpp
void DetectDuplicateLevelIdentity(SLevelState &level_state)
  {
   bool duplicate=(
      level_state.active_order_count+
      level_state.active_position_count>1
   );
   if(duplicate && !level_state.duplicate_identity)
      LogLifecycleEvent(
         "duplicate_level_identity",
         StringFormat(
            "STR %s%d",
            level_state.is_buy ? "B" : "S",
            level_state.level
         ),
         "multiple_active_entities"
      );
   level_state.duplicate_identity=duplicate;
  }
```

Call it for every configured buy and sell level after scanning.

- [ ] **Step 5: Block only new placement for the affected level**

At the top of `PlaceLevel`:

```cpp
if(level_state.duplicate_identity)
   return false;
```

Do not close or cancel the duplicate entities automatically.

- [ ] **Step 6: Add comparator coverage**

Add a cycle containing two active candidate order identities for `STR B1`.
Assert:

```python
assert report["status"] == "FAIL"
assert any(
    mismatch["category"] == "duplicate_level_identity"
    for mismatch in report["deterministic_mismatches"]
)
```

In `compare_paired_cycles`, detect canonical events whose kind is
`duplicate_level_identity` and append:

```python
{
    "category": "duplicate_level_identity",
    "comment": event["comment"],
    "source": event["source"],
}
```

to `deterministic_mismatches`.

- [ ] **Step 7: Run tests and compile**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py tests\test_live_twin.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: tests pass and builds have zero errors and warnings.

- [ ] **Step 8: Write the Task 5 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  mql5\include\StraddleTypes.mqh,`
  mql5\include\StraddleEngine.mqh `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-05-level-identity.json"
```

## Task 6: Isolate and observe basket and stop decisions

**Files:**

- Create: `mql5/include/BasketEvaluator.mqh`
- Create: `mql5/include/StopScheduler.mqh`
- Create: `straddle_replica/basket_analysis.py`
- Create: `tests/test_basket_analysis.py`
- Modify: `mql5/include/StraddleEngine.mqh`
- Modify: `tests/test_mql5_contract.py`

- [ ] **Step 1: Write failing basket-analysis tests**

Create `tests/test_basket_analysis.py`:

```python
from straddle_replica.basket_analysis import basket_candidates


def test_basket_candidates_report_first_crossing_and_trigger_delay() -> None:
    snapshots = [
        {"time_msc": 1_000, "realized": 10.0, "floating": 15.0},
        {"time_msc": 2_000, "realized": 12.0, "floating": 19.0},
        {"time_msc": 3_000, "realized": 14.0, "floating": 18.0},
    ]

    result = basket_candidates(
        snapshots,
        trigger_time_msc=3_500,
        fixed_targets=(30.0, 35.0),
    )

    assert result["fixed_30"]["first_crossing_msc"] == 2_000
    assert result["fixed_30"]["trigger_delay_ms"] == 1_500
    assert result["fixed_35"]["first_crossing_msc"] is None
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests\test_basket_analysis.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement the basket candidate analyzer**

Create `straddle_replica/basket_analysis.py`:

```python
from __future__ import annotations

from typing import Iterable, Mapping, Any


def basket_candidates(
    snapshots: Iterable[Mapping[str, Any]],
    *,
    trigger_time_msc: int,
    fixed_targets: tuple[float, ...],
) -> dict[str, dict[str, float | int | None]]:
    ordered = sorted(snapshots, key=lambda row: int(row["time_msc"]))
    result: dict[str, dict[str, float | int | None]] = {}
    for target in fixed_targets:
        crossing = next(
            (
                int(row["time_msc"])
                for row in ordered
                if float(row.get("realized") or 0.0)
                + float(row.get("floating") or 0.0)
                >= target
            ),
            None,
        )
        key = f"fixed_{target:g}"
        result[key] = {
            "target": target,
            "first_crossing_msc": crossing,
            "trigger_delay_ms": (
                trigger_time_msc - crossing
                if crossing is not None
                else None
            ),
        }
    return result
```

- [ ] **Step 4: Add a pure MQL basket evaluator**

Create `mql5/include/BasketEvaluator.mqh`:

```cpp
#ifndef STRADDLE_BASKET_EVALUATOR_MQH
#define STRADDLE_BASKET_EVALUATOR_MQH

struct SBasketSnapshot
  {
   double realized;
   double floating;
   double net;
   double target;
   bool   triggered;
  };

class CBasketEvaluator
  {
public:
   SBasketSnapshot Evaluate(const double realized,
                            const double floating,
                            const double target,
                            const bool has_traded) const
     {
      SBasketSnapshot snapshot={};
      snapshot.realized=realized;
      snapshot.floating=floating;
      snapshot.net=realized+floating;
      snapshot.target=target;
      snapshot.triggered=(
         has_traded &&
         target>0.0 &&
         snapshot.net>=target
      );
      return snapshot;
     }
  };

#endif
```

Include and add:

```cpp
CBasketEvaluator m_basket_evaluator;
```

Replace the inline condition:

```cpp
SBasketSnapshot basket=m_basket_evaluator.Evaluate(
   m_cycle_realized,
   OwnedFloatingProfit(),
   target,
   m_has_traded
);
if(basket.triggered)
  {
   LogLifecycleEvent("basket_trigger","","threshold_reached");
   BeginClose("basket_target",false);
  }
```

- [ ] **Step 5: Add the MQL contract**

Assert:

```python
assert '#include "BasketEvaluator.mqh"' in engine
assert "CBasketEvaluator m_basket_evaluator;" in engine
assert "SBasketSnapshot basket=" in engine
assert "if(basket.triggered)" in engine
```

- [ ] **Step 6: Verify without changing the $30 hypothesis**

Run:

```powershell
python -m pytest tests\test_basket_analysis.py `
  tests\test_mql5_contract.py tests\test_profiles.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: tests pass. `LATEST_30` remains fixed at `$30`; later evidence may
change it only through a new failing test.

- [ ] **Step 7: Add a failing stop-scheduler contract**

Append:

```python
def test_stop_formula_is_isolated_from_position_iteration():
    engine = ENGINE.read_text(encoding="utf-8")
    scheduler = (
        ROOT / "mql5" / "include" / "StopScheduler.mqh"
    )
    assert scheduler.exists()
    source = scheduler.read_text(encoding="utf-8")

    assert '#include "StopScheduler.mqh"' in engine
    assert "CStopScheduler m_stop_scheduler;" in engine
    assert "m_stop_scheduler.Calculate(" in engine
    assert "bool Calculate(" in source
    assert "tighten_trigger_steps" in source
    assert "pre_tighten_trail_distance_steps" in source
```

- [ ] **Step 8: Run the stop-scheduler contract and verify RED**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py `
  -k stop_formula_is_isolated_from_position_iteration -q
```

- [ ] **Step 9: Implement the pure stop scheduler**

Create `mql5/include/StopScheduler.mqh`:

```cpp
#ifndef STRADDLE_STOP_SCHEDULER_MQH
#define STRADDLE_STOP_SCHEDULER_MQH

#include "StraddleTypes.mqh"

class CStopScheduler
  {
public:
   bool Calculate(const ENUM_POSITION_TYPE type,
                  const double entry,
                  const double current_sl,
                  const double bid,
                  const double ask,
                  const double step,
                  const double tick_size,
                  const int digits,
                  const double point,
                  const long stops_level,
                  const SProfileConfig &profile,
                  double &desired) const
     {
      if(step<=0.0 || tick_size<=0.0 || digits<0 || point<=0.0)
         return false;
      double market=(type==POSITION_TYPE_BUY ? bid : ask);
      double direction=(type==POSITION_TYPE_BUY ? 1.0 : -1.0);
      double favorable_steps=direction*(market-entry)/step;
      if(favorable_steps<profile.lock_trigger_steps)
         return false;
      if(current_sl<=0.0)
        {
         desired=(
            profile.activation_uses_trailing_distance
            ? market-direction*
              profile.pre_tighten_trail_distance_steps*step
            : entry+direction*profile.lock_offset_price
         );
        }
      else
        {
         double distance=(
            favorable_steps>=profile.tighten_trigger_steps
            ? profile.trail_distance_steps
            : profile.pre_tighten_trail_distance_steps
         );
         desired=market-direction*distance*step;
        }
      desired=NormalizeDouble(
         MathRound(desired/tick_size)*tick_size,
         digits
      );
      double minimum_distance=(double)stops_level*point;
      if(type==POSITION_TYPE_BUY)
        {
         desired=MathMin(desired,bid-minimum_distance);
         return desired>entry &&
                (current_sl<=0.0 || desired>current_sl);
        }
      desired=MathMax(desired,ask+minimum_distance);
      return desired<entry &&
             (current_sl<=0.0 || desired<current_sl);
     }
  };

#endif
```

In `UpdatePositionStops`, keep newest-first ticket iteration and the
one-update-per-pass limit in the engine, but replace the inline stop formula:

```cpp
double desired=0.0;
if(!m_stop_scheduler.Calculate(
      type,
      entry,
      current_sl,
      tick.bid,
      tick.ask,
      m_step,
      m_tick_size,
      (int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS),
      m_point,
      SymbolInfoInteger(
         m_runtime.symbol,
         SYMBOL_TRADE_STOPS_LEVEL
      ),
      m_profile,
      desired))
   continue;
```

- [ ] **Step 10: Verify the stop scheduler and compile**

Run:

```powershell
python -m pytest tests\test_mql5_contract.py tests\test_profiles.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: tests pass and both builds compile cleanly.

- [ ] **Step 11: Write the Task 6 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  mql5\include\BasketEvaluator.mqh,`
  mql5\include\StopScheduler.mqh,`
  straddle_replica\basket_analysis.py,`
  mql5\include\StraddleEngine.mqh `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-06-basket-observability.json"
```

## Task 7: Separate fidelity and real-safe presets

**Files:**

- Modify: `mql5/include/StraddleTypes.mqh`
- Modify: `mql5/include/StraddleReplicaApp.mqh`
- Modify: `mql5/include/StraddleEngine.mqh`
- Create: `profiles/latest_30_fidelity.set`
- Create: `profiles/latest_30_real_safe.set`
- Modify: `tests/test_mql5_contract.py`
- Create: `tests/test_fidelity_presets.py`

- [ ] **Step 1: Write failing preset and account-binding tests**

Create `tests/test_fidelity_presets.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIDELITY = ROOT / "profiles" / "latest_30_fidelity.set"
REAL_SAFE = ROOT / "profiles" / "latest_30_real_safe.set"


def test_fidelity_and_real_safe_presets_are_explicitly_different() -> None:
    fidelity = FIDELITY.read_text(encoding="utf-8")
    safe = REAL_SAFE.read_text(encoding="utf-8")

    assert "Profile=4" in fidelity
    assert "RequireBoundAccount=true" in fidelity
    assert "SafetyEnabled=false" in fidelity

    assert "Profile=4" in safe
    assert "RequireBoundAccount=true" in safe
    assert "SafetyEnabled=true" in safe
    assert "MaxEquityLossPercent=10.0" in safe
    assert "MaxGrossLots=2.20" in safe
    assert "MaxSpreadPoints=1000.0" in safe
    assert "DailyLossLimit=500.0" in safe
```

Append an engine contract:

```python
def test_bound_account_and_safe_rearm_guards_exist():
    app = APP.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")

    assert "input bool RequireBoundAccount = false" in app
    assert "bool              require_bound_account;" in types
    assert "runtime.require_bound_account=RequireBoundAccount" in app
    assert "m_runtime.require_bound_account" in engine
    assert "ExposureAllowsRearm" in engine
    assert '"safety_rearm_blocked"' in engine
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests\test_fidelity_presets.py `
  tests\test_mql5_contract.py `
  -k "fidelity_and_real_safe or bound_account" -q
```

Expected: failures because the presets and account-binding input do not exist.

- [ ] **Step 3: Add fail-closed account binding**

Add to `SRuntimeConfig`:

```cpp
bool require_bound_account;
```

Add to the app:

```cpp
input bool RequireBoundAccount = false;
```

Map it:

```cpp
runtime.require_bound_account=RequireBoundAccount;
```

Before the existing login comparison:

```cpp
if(m_runtime.require_bound_account &&
   m_runtime.expected_account_login==0)
  {
   Print("[STR] Initialization refused: bound account login is required.");
   return false;
  }
```

- [ ] **Step 4: Block unsafe rearms without changing the fidelity preset**

Add:

```cpp
bool ExposureAllowsRearm(const double volume) const
  {
   if(!m_runtime.safety_enabled ||
      m_runtime.max_gross_lots<=0.0)
      return true;
   return(
      OwnedGrossLots()+volume<=
      m_runtime.max_gross_lots+0.0000001
   );
  }
```

In `RearmOneMissingLevel`, before `PlaceLevel`:

```cpp
string level_comment=StringFormat(
   "STR %s%d",
   level_state.is_buy ? "B" : "S",
   level_state.level
);
if(!ExposureAllowsRearm(level_state.volume))
  {
   LogLifecycleEvent(
      "safety_rearm_blocked",
      level_comment,
      "max_gross_lots"
   );
   return;
  }
```

Apply the same check before any recovery market order. Do not apply it when
`SafetyEnabled=false`.

- [ ] **Step 5: Create the two presets**

Create `profiles/latest_30_fidelity.set`:

```text
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
RequireBoundAccount=true
ExpectedAccountLogin=0
SafetyEnabled=false
```

Create `profiles/latest_30_real_safe.set`:

```text
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
RequireBoundAccount=true
ExpectedAccountLogin=0
SafetyEnabled=true
MaxEquityLossPercent=10.0
MaxGrossLots=2.20
MaxSpreadPoints=1000.0
DailyLossLimit=500.0
```

Both templates intentionally refuse to initialize until the package script
binds `ExpectedAccountLogin` to a nonzero login.

- [ ] **Step 6: Run tests and compile**

Run:

```powershell
python -m pytest tests\test_fidelity_presets.py `
  tests\test_mql5_contract.py tests\test_real_exact_contract.py -q
& .\scripts\build.ps1
& .\scripts\build_real.ps1
```

Expected: tests pass and builds compile cleanly.

- [ ] **Step 7: Write the Task 7 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  profiles\latest_30_fidelity.set,`
  profiles\latest_30_real_safe.set,`
  mql5\include\StraddleReplicaApp.mqh,`
  mql5\include\StraddleEngine.mqh `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-07-presets-and-safety.json"
```

## Task 8: Enforce the 20-cycle evidence-graded qualification gate

**Files:**

- Modify: `straddle_replica/live_twin_gate.py`
- Create: `straddle_replica/observer_health.py`
- Modify: `tools/evaluate_live_twin_gate.py`
- Create: `tools/analyze_observer_health.py`
- Modify: `tests/test_live_twin_gate.py`
- Create: `tests/test_observer_health.py`
- Modify: `docs/LIVE_TWIN.md`
- Modify: `docs/FIDELITY.md`

- [ ] **Step 1: Change tests to the approved gate**

Rename the first gate test and use 20 reports:

```python
def test_gate_passes_twenty_consecutive_cycles_and_48_hours() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=True,
        request_evidence_available=True,
    )

    assert result["qualification_status"] == "FORMAL_PASS"
    assert result["ready_for_formal_fidelity"] is True
    assert result["required_clean_cycles"] == 20
```

Add best-effort coverage:

```python
def test_observer_evidence_can_pass_best_effort_but_not_formal() -> None:
    result = evaluate_live_twin_gate(
        reports=reports(["PASS"] * 20),
        market_open_hours=48.0,
        sequence_gaps=0,
        dropped_transactions=0,
        account_terms_match=False,
        request_evidence_available=False,
    )

    assert result["qualification_status"] == "BEST_EFFORT_PASS"
    assert result["ready_for_best_effort_candidate"] is True
    assert result["ready_for_formal_fidelity"] is False
```

- [ ] **Step 2: Run gate tests and verify RED**

Run:

```powershell
python -m pytest tests\test_live_twin_gate.py -q
```

Expected: failures because the default is 10 and the new status fields are
absent.

- [ ] **Step 3: Update gate semantics**

Change the default:

```python
required_cycles: int = 20
```

Compute:

```python
operational_pass = (
    effective_market_hours >= required_market_hours
    and consecutive >= required_cycles
    and invalid_cycle_reports == 0
    and sequence_gaps == 0
    and duplicate_sequences == 0
    and dropped_transactions == 0
    and session_restarts == 0
    and operational_guard_failures == 0
)
operational_blocking_reasons = []
if effective_market_hours < required_market_hours:
    operational_blocking_reasons.append("market_open_hours")
if consecutive < required_cycles:
    operational_blocking_reasons.append("consecutive_clean_cycles")
if invalid_cycle_reports:
    operational_blocking_reasons.append("invalid_cycle_reports")
if sequence_gaps:
    operational_blocking_reasons.append("sequence_gaps")
if duplicate_sequences:
    operational_blocking_reasons.append("duplicate_sequences")
if dropped_transactions:
    operational_blocking_reasons.append("dropped_transactions")
if session_restarts:
    operational_blocking_reasons.append("session_restarts")
if operational_guard_failures:
    operational_blocking_reasons.append("operational_guard_failures")
formal_pass = (
    operational_pass
    and request_evidence_available
    and account_terms_match
)
best_effort_pass = operational_pass and not formal_pass
qualification_status = (
    "FORMAL_PASS"
    if formal_pass
    else "BEST_EFFORT_PASS"
    if best_effort_pass
    else "BLOCKED"
)
```

Return:

```python
"qualification_status": qualification_status,
"ready_for_formal_fidelity": formal_pass,
"ready_for_best_effort_candidate": best_effort_pass,
"blocking_reasons": operational_blocking_reasons,
"formal_blocking_reasons": [
    reason
    for reason, blocked in (
        ("direct_request_evidence", not request_evidence_available),
        ("account_terms", not account_terms_match),
    )
    if blocked
],
```

Remove `ready_for_100_percent_claim` from user-facing output.

- [ ] **Step 4: Change the CLI default and output**

Use:

```python
parser.add_argument("--required-cycles", type=int, default=20)
```

Print:

```python
{
    "qualification_status": result["qualification_status"],
    "ready_for_formal_fidelity": result[
        "ready_for_formal_fidelity"
    ],
    "ready_for_best_effort_candidate": result[
        "ready_for_best_effort_candidate"
    ],
    "blocking_reasons": result["blocking_reasons"],
    "output": str(args.output),
}
```

- [ ] **Step 5: Update documentation**

State exactly:

- 20 consecutive complete paired cycles;
- 48 market-open hours;
- any source, preset, account-term, deterministic mismatch, sequence gap, or
  dropped transaction resets the run;
- observer evidence can only produce `BEST_EFFORT_PASS`;
- neither status promises identical broker profit.

- [ ] **Step 6: Write a failing observer-health test**

Create `tests/test_observer_health.py`:

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from straddle_replica.observer_health import analyze_observer_health


UTC = timezone.utc


def test_observer_health_measures_active_ticks_and_zero_drops(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 8, 11, tzinfo=UTC)
    session = tmp_path / "session"
    session.mkdir()
    ticks = [
        {
            "sequence": index + 1,
            "capture_time_utc": (
                started + timedelta(seconds=index)
            ).isoformat(),
            "time_msc": int(
                (started + timedelta(seconds=index)).timestamp() * 1000
            ),
        }
        for index in range(3)
    ]
    (session / "ticks-20260811-00.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ticks),
        encoding="utf-8",
    )
    (session / "heartbeat.json").write_text(
        json.dumps(
            {
                "capture_time_utc": ticks[-1]["capture_time_utc"],
                "healthy": True,
                "stopped": False,
                "read_only_verified": True,
                "dropped_transactions": 0,
            }
        ),
        encoding="utf-8",
    )

    result = analyze_observer_health(
        session,
        certification_started_utc=started,
    )

    assert result["market_open_hours"] == 0.0006
    assert result["sequence_gaps"] == 0
    assert result["duplicate_sequences"] == 0
    assert result["dropped_transactions"] == 0
    assert result["direct_request_evidence_available"] is False
```

- [ ] **Step 7: Run the observer-health test and verify RED**

Run:

```powershell
python -m pytest tests\test_observer_health.py -q
```

Expected: import failure because `observer_health.py` does not exist.

- [ ] **Step 8: Implement observer health measurement**

Implement `analyze_observer_health` by reading complete lines from
`ticks-*.jsonl`, filtering at or after the certification start, sorting by
`time_msc`, summing adjacent gaps from 0 through 300,000 ms, and counting
sequence gaps/duplicates. Read `heartbeat.json` and fail health when
`read_only_verified` is false, `healthy` is false, `stopped` is true, or
`dropped_transactions` is nonzero.

Use this core calculation:

```python
tick_rows.sort(key=lambda row: int(row["time_msc"]))
active_ms = sum(
    right - left
    for left, right in zip(
        [int(row["time_msc"]) for row in tick_rows],
        [int(row["time_msc"]) for row in tick_rows][1:],
    )
    if 0 <= right - left <= 300_000
)
previous = None
sequence_gaps = 0
duplicate_sequences = 0
for row in tick_rows:
    sequence = int(row.get("sequence") or 0)
    if previous is not None:
        if sequence > previous + 1:
            sequence_gaps += sequence - previous - 1
        elif sequence <= previous:
            duplicate_sequences += 1
    previous = sequence
```

Create `tools/analyze_observer_health.py` with:

```python
result = analyze_observer_health(
    args.session,
    certification_started_utc=args.certification_started_utc,
)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    json.dumps(result, indent=2, sort_keys=True),
    encoding="utf-8",
)
return 0 if not result["operational_failures"] else 1
```

- [ ] **Step 9: Run gate, health, and documentation tests**

Run:

```powershell
python -m pytest tests\test_live_twin_gate.py `
  tests\test_observer_health.py `
  tests\test_docs_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Write the Task 8 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  straddle_replica\live_twin_gate.py,`
  straddle_replica\observer_health.py,`
  tools\analyze_observer_health.py,`
  tools\evaluate_live_twin_gate.py,`
  docs\LIVE_TWIN.md,`
  docs\FIDELITY.md `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-08-qualification-gate.json"
```

## Task 9: Generate reproducible fidelity and mismatch reports

**Files:**

- Create: `tools/build_fidelity_report.py`
- Create: `tests/test_fidelity_report_tool.py`
- Modify: `tools/compare_live_twin.py`

- [ ] **Step 1: Write a failing report-tool test**

Create `tests/test_fidelity_report_tool.py`:

```python
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "build_fidelity_report.py"


def test_report_tool_writes_json_markdown_and_mismatch_register(
    tmp_path: Path,
) -> None:
    cycle = tmp_path / "cycle-1.json"
    cycle.write_text(
        json.dumps(
            {
                "cycle_id": "cycle-1",
                "status": "FAIL",
                "logic_status": "FAIL",
                "execution_status": "DIFFERENT",
                "evidence_grade": "BEST_EFFORT",
                "fidelity": {
                    "strict": {"f1_percent": 55.25},
                    "conditional": {
                        "f1_percent": 90.0,
                        "coverage_percent": 60.0,
                    },
                },
                "deterministic_mismatches": [
                    {
                        "category": "decision_sequence",
                        "key": ["stop_request", "STR B1", 1],
                    }
                ],
                "execution_mismatches": [
                    {"category": "execution", "key": ["fill", "STR B1", 1]}
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--comparison",
            str(cycle),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / "fidelity-summary.json").exists()
    assert (output / "fidelity-summary.md").exists()
    register = json.loads(
        (output / "mismatch-register.json").read_text(encoding="utf-8")
    )
    assert register["earliest_deterministic"]["category"] == (
        "decision_sequence"
    )
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests\test_fidelity_report_tool.py -q
```

Expected: failure because the tool does not exist.

- [ ] **Step 3: Implement the aggregate report**

The tool must accept repeated `--comparison` arguments and an optional
`--comparisons-dir` whose `*.json` files are added in sorted order. It must
also accept `--historical-matched`, `--historical-target`, and
`--evidence-grade` for a preserved historical-only baseline.

The tool must:

1. load every `--comparison` JSON;
2. sort by cycle ID and generated timestamp;
3. compute cycle counts by status and evidence grade;
4. calculate the mean and minimum strict F1;
5. calculate conditional F1 and coverage;
6. preserve the first deterministic and execution mismatch per cycle;
7. write:
   - `fidelity-summary.json`;
   - `fidelity-summary.md`;
   - `mismatch-register.json`.

Use this report shape:

```python
summary = {
    "schema_version": 1,
    "comparison_count": len(reports),
    "evidence_grades": sorted(
        {str(report.get("evidence_grade") or "UNKNOWN") for report in reports}
    ),
    "status_counts": {
        status: sum(report.get("status") == status for report in reports)
        for status in ("PASS", "FAIL", "INVALID", "UNPAIRED")
    },
    "strict_lifecycle_fidelity_percent": {
        "mean": round(sum(strict_scores) / len(strict_scores), 4),
        "minimum": min(strict_scores),
    },
    "conditional_logic_fidelity_percent": {
        "mean": round(sum(conditional_scores) / len(conditional_scores), 4),
        "minimum_coverage": min(coverage_scores),
    },
}
```

When there are no comparison reports, calculate:

```python
strict_percent = round(
    args.historical_matched / args.historical_target * 100.0,
    4,
)
```

and write a summary with `comparison_count=0`,
`strict_lifecycle_fidelity_percent.mean=strict_percent`, and
`live_cycle_coverage_percent=0.0`. Reject a missing or nonpositive
`--historical-target`.

The Markdown report must state that 55% is the current historical baseline and
must not print 92% as a current result.

- [ ] **Step 4: Run report tests and verify GREEN**

Run:

```powershell
python -m pytest tests\test_fidelity_report_tool.py -q
```

Expected: pass.

- [ ] **Step 5: Generate the first report from preserved evidence**

Run the updated comparator against preserved target/candidate event files that
contain common cycle IDs, then run:

```powershell
python tools\build_fidelity_report.py `
  --comparisons-dir artifacts\live\paired-cycles `
  --output-dir artifacts\analysis\independent-fidelity-baseline
```

If no valid common cycle IDs exist, run:

```powershell
python tools\build_fidelity_report.py `
  --historical-matched 663 `
  --historical-target 1200 `
  --evidence-grade BEST_EFFORT `
  --output-dir artifacts\analysis\independent-fidelity-baseline
```

This writes a 55.25% strict historical baseline and live cycle coverage zero.

- [ ] **Step 6: Write the Task 9 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  tools\build_fidelity_report.py,`
  artifacts\analysis\independent-fidelity-baseline\fidelity-summary.json,`
  artifacts\analysis\independent-fidelity-baseline\mismatch-register.json `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-09-fidelity-report.json"
```

## Task 10: Add candidate-scoped SSH shadow transport

**Files:**

- Create: `straddle_replica/shadow_transport.py`
- Create: `tests/test_shadow_transport.py`
- Modify: `straddle_replica/shadow_coordinator.py`
- Modify: `tools/run_shadow_coordinator.py`
- Modify: `tests/test_shadow_coordinator.py`

- [ ] **Step 1: Write failing transport safety tests**

Create `tests/test_shadow_transport.py`:

```python
from pathlib import PurePosixPath
import pytest

from straddle_replica.shadow_transport import (
    RemoteShadowPaths,
    validate_remote_path,
)


ROOT = PurePosixPath("/opt/straddle-fidelity-candidate")


def test_remote_paths_are_confined_to_candidate_root() -> None:
    paths = RemoteShadowPaths(
        root=ROOT,
        command=ROOT / "common/StraddleShadow/command.csv",
        ack=ROOT / "common/StraddleShadow/ack.csv",
    )

    assert validate_remote_path(paths.root, paths.command) == paths.command
    assert validate_remote_path(paths.root, paths.ack) == paths.ack


def test_remote_path_escape_is_rejected() -> None:
    for escaped in (
        PurePosixPath("/opt/straddle-replica-demo/command.csv"),
        ROOT / "../straddle-replica-demo/command.csv",
    ):
        with pytest.raises(ValueError, match="candidate root"):
            validate_remote_path(ROOT, escaped)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests\test_shadow_transport.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement local and OpenSSH transports**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tempfile
from typing import Any, Protocol


@dataclass(frozen=True)
class RemoteShadowPaths:
    root: PurePosixPath
    command: PurePosixPath
    ack: PurePosixPath


def validate_remote_path(
    root: PurePosixPath,
    path: PurePosixPath,
) -> PurePosixPath:
    if not root.is_absolute() or not path.is_absolute():
        raise ValueError("Remote shadow path is outside candidate root")
    if ".." in path.parts:
        raise ValueError("Remote shadow path is outside candidate root")
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Remote shadow path is outside candidate root"
        ) from error
    if path == root:
        raise ValueError("Remote shadow path is outside candidate root")
    return path


class ShadowTransport(Protocol):
    def read_ack(self) -> dict[str, Any]: ...
    def write_command(self, payload: dict[str, Any]) -> None: ...


class FileShadowTransport:
    def __init__(self, command_path: Path, ack_path: Path) -> None:
        self.command_path = command_path
        self.ack_path = ack_path

    def read_ack(self) -> dict[str, Any]:
        if not self.ack_path.exists():
            return {"status": "UNKNOWN", "command_seq": 0, "cycle_id": ""}
        with self.ack_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows[-1] if rows else {
            "status": "UNKNOWN",
            "command_seq": 0,
            "cycle_id": "",
        }

    def write_command(self, payload: dict[str, Any]) -> None:
        temporary = self.command_path.with_suffix(".csv.tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(payload))
            writer.writeheader()
            writer.writerow(payload)
        temporary.replace(self.command_path)


class OpenSshShadowTransport:
    def __init__(
        self,
        *,
        ssh_alias: str,
        paths: RemoteShadowPaths,
    ) -> None:
        self.ssh_alias = ssh_alias
        self.paths = paths
        validate_remote_path(paths.root, paths.command)
        validate_remote_path(paths.root, paths.ack)

    def _ssh(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["ssh", self.ssh_alias, command],
            capture_output=True,
            text=True,
            check=False,
        )

    def read_ack(self) -> dict[str, Any]:
        command = f"cat -- {shlex.quote(str(self.paths.ack))}"
        completed = self._ssh(command)
        if completed.returncode != 0:
            return {"status": "UNKNOWN", "command_seq": 0, "cycle_id": ""}
        rows = list(csv.DictReader(completed.stdout.splitlines()))
        return rows[-1] if rows else {
            "status": "UNKNOWN",
            "command_seq": 0,
            "cycle_id": "",
        }

    def write_command(self, payload: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "command.csv"
            with local.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=tuple(payload))
                writer.writeheader()
                writer.writerow(payload)
            remote_tmp = self.paths.command.with_suffix(".csv.tmp")
            validate_remote_path(self.paths.root, remote_tmp)
            subprocess.run(
                [
                    "scp",
                    str(local),
                    f"{self.ssh_alias}:{remote_tmp}",
                ],
                check=True,
            )
            completed = self._ssh(
                "mv -f -- "
                f"{shlex.quote(str(remote_tmp))} "
                f"{shlex.quote(str(self.paths.command))}"
            )
            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )
```

- [ ] **Step 4: Inject the transport into the coordinator**

`ShadowCoordinator` must accept:

```python
transport: ShadowTransport | None = None
```

Use `FileShadowTransport` when no transport is supplied. Replace direct
`_read_ack` and `_write_command` calls with `self.transport.read_ack()` and
`self.transport.write_command(asdict(command))`. Assign `self.transport`
before calling `_load_state`, because `_default_state` seeds its sequence from
the transport acknowledgement.

- [ ] **Step 5: Add remote CLI arguments**

Add:

```python
parser.add_argument("--remote-ssh-alias")
parser.add_argument(
    "--remote-root",
    default="/opt/straddle-fidelity-candidate",
)
parser.add_argument("--remote-command-path")
parser.add_argument("--remote-ack-path")
```

Require all remote arguments when `--remote-ssh-alias` is set. Refuse a root
other than `/opt/straddle-fidelity-candidate`.

- [ ] **Step 6: Test command scoping without live SSH**

Mock `subprocess.run` and assert:

- `scp` targets only the candidate command path;
- remote commands are only `cat` and `mv`;
- no command contains `docker`, `systemctl`, `kill`, `rm`, or the existing
  container path.

- [ ] **Step 7: Run coordinator regressions**

Run:

```powershell
python -m pytest tests\test_shadow_transport.py `
  tests\test_shadow_coordinator.py -q
```

Expected: all tests pass.

- [ ] **Step 8: Write the Task 10 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  straddle_replica\shadow_transport.py,`
  straddle_replica\shadow_coordinator.py,`
  tools\run_shadow_coordinator.py `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-10-remote-shadow.json"
```

## Task 11: Package and deploy a fresh isolated VPS demo candidate

**Files:**

- Create: `monitor/fidelity-candidate-startup.ini`
- Create: `deploy/vps-docker-candidate/compose.yaml`
- Create: `scripts/package_fidelity_candidate.ps1`
- Create: `scripts/package_fidelity_release.ps1`
- Create: `scripts/deploy_fidelity_candidate_vps.ps1`
- Create: `scripts/install_fidelity_monitor_tasks.ps1`
- Create: `tests/test_fidelity_candidate_deployment.py`
- Modify: `docs/LIVE_TWIN.md`

- [ ] **Step 1: Write failing deployment isolation tests**

Create `tests/test_fidelity_candidate_deployment.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "deploy" / "vps-docker-candidate" / "compose.yaml"
PACKAGE = ROOT / "scripts" / "package_fidelity_candidate.ps1"
RELEASE = ROOT / "scripts" / "package_fidelity_release.ps1"
DEPLOY = ROOT / "scripts" / "deploy_fidelity_candidate_vps.ps1"
MONITOR = ROOT / "scripts" / "install_fidelity_monitor_tasks.ps1"
STARTUP = ROOT / "monitor" / "fidelity-candidate-startup.ini"


def test_candidate_container_is_isolated_from_existing_vps_runtime() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")

    assert "straddle-fidelity-candidate-demo" in compose
    assert "/opt/straddle-fidelity-candidate:/data" in compose
    assert "127.0.0.1:15915:5900" in compose
    assert "straddle-fidelity-mt5:bookworm" in compose
    assert "straddle-replica-demo-vps" not in compose
    assert "docker stop" not in deploy
    assert "docker restart" not in deploy
    assert "docker rm" not in deploy
    assert "straddle-replica-demo-vps" in deploy
    assert "docker inspect" in deploy


def test_candidate_package_contains_ex5_presets_hashes_and_no_source() -> None:
    package = PACKAGE.read_text(encoding="utf-8")

    assert "StraddleReplica.ex5" in package
    assert "latest_30_shadow.set" in package
    assert "latest_30_fidelity.set" in package
    assert "latest_30_real_safe.set" in package
    assert "SHA256SUMS.txt" in package
    assert "StraddleEngine.mqh" not in package
    assert "StraddleReplica.mq5" not in package
    assert "Password" not in package


def test_release_package_binds_login_and_excludes_source() -> None:
    release = RELEASE.read_text(encoding="utf-8")

    assert "ExpectedRealLogin" in release
    assert "StraddleReplicaReal.ex5" in release
    assert "latest_30_fidelity.set" in release
    assert "latest_30_real_safe.set" in release
    assert "SHA256SUMS.txt" in release
    assert "StraddleEngine.mqh" not in release
    assert "StraddleReplicaReal.mq5" not in release


def test_monitor_tasks_are_new_read_only_and_candidate_scoped() -> None:
    monitor = MONITOR.read_text(encoding="utf-8")

    assert "StraddleFidelityTargetCollector" in monitor
    assert "StraddleFidelityCycleSync" in monitor
    assert "--require-read-only" in monitor
    assert "--remote-ssh-alias" in monitor
    assert "/opt/straddle-fidelity-candidate" in monitor
    assert "Get-CimInstance Win32_Process" in monitor
    assert "target collector owner is already running" in monitor
    assert "Start-ScheduledTask -TaskName $collectorTaskName" in monitor
    assert (
        "Start-ScheduledTask -TaskName $coordinatorTaskName"
        not in monitor
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests\test_fidelity_candidate_deployment.py -q
```

Expected: failures because the new deployment files do not exist.

- [ ] **Step 3: Create candidate startup configuration**

Create `monitor/fidelity-candidate-startup.ini`:

```ini
[Experts]
Enabled=1
AllowLiveTrading=1
AllowDllImport=0

[StartUp]
Expert=StraddleReplica\StraddleReplica
ExpertParameters=latest_30_shadow.set
Symbol=XAUUSD
Period=M1
ShutdownTerminal=0
```

- [ ] **Step 4: Create the isolated compose file**

Create `deploy/vps-docker-candidate/compose.yaml`:

```yaml
services:
  fidelity-candidate:
    image: straddle-fidelity-mt5:bookworm
    container_name: straddle-fidelity-candidate-demo
    restart: unless-stopped
    environment:
      MT5_START: "${MT5_START:-0}"
      MT5_CONFIG_WINDOWS: "Z:\\data\\candidate\\fidelity-candidate-startup.ini"
    ports:
      - "127.0.0.1:15915:5900"
    volumes:
      - "/opt/straddle-fidelity-candidate:/data"
    cpus: 0.75
    mem_limit: 1536m
    pids_limit: 256
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
```

- [ ] **Step 5: Build a credential-free package**

`package_fidelity_candidate.ps1` must:

1. require `-ExpectedDemoLogin` greater than zero;
2. require `-Mt5InstallerPath` to an operator-supplied MT5 installer;
3. compile the demo EA;
4. copy only EX5, the shadow/fidelity/safe presets, startup INI, Docker
   runtime files, the installer, and docs;
5. replace `ExpectedAccountLogin=0` with the supplied demo login in the shadow
   preset only;
6. keep real preset templates unbound and fail-closed;
7. write `SHA256SUMS.txt`;
8. create `artifacts/StraddleReplica-FIDELITY-CANDIDATE.zip`;
9. reject any staged `.mq5`, `.mqh`, password, or account secret file.

Use:

```powershell
if ($ExpectedDemoLogin -le 0) {
    throw "ExpectedDemoLogin must be a positive demo login."
}
```

and:

```powershell
$forbidden = Get-ChildItem $stage -Recurse -File |
    Where-Object {
        $_.Extension -in @('.mq5','.mqh') -or
        $_.Name -match '(?i)password|credential|secret'
    }
if ($forbidden) {
    throw "Candidate package contains forbidden source or secret files."
}
```

- [ ] **Step 6: Implement candidate-only VPS deployment**

`deploy_fidelity_candidate_vps.ps1` must:

1. accept `-SshAlias nishahomes-vps`;
2. inspect and record the existing container ID, state, and restart count;
3. create only `/opt/straddle-fidelity-candidate`;
4. upload the candidate package, Dockerfile, entrypoint, and compose file;
5. build only the new image tag `straddle-fidelity-mt5:bookworm`;
6. run `docker compose -p straddle-fidelity-candidate up -d`;
7. inspect the existing container again and require unchanged ID, state, and
   restart count;
8. verify candidate VNC binds only to `127.0.0.1:15915`;
9. leave `MT5_START=0` for the first commissioning boot.

The only compose command is:

```powershell
ssh $SshAlias `
  "cd /opt/straddle-fidelity-candidate && docker compose -p straddle-fidelity-candidate up -d"
```

The image build command is scoped to the candidate directory and tag:

```powershell
ssh $SshAlias `
  "docker build -t straddle-fidelity-mt5:bookworm /opt/straddle-fidelity-candidate/image"
```

- [ ] **Step 7: Implement isolated monitoring tasks**

Create `scripts/install_fidelity_monitor_tasks.ps1` with distinct scheduled
task names:

```text
StraddleFidelityTargetCollector
StraddleFidelityCycleSync
```

The collector command must include `--require-read-only`; the coordinator must
use the candidate-scoped remote paths. The script must not modify or start the
old `StraddleTargetCollector`, `StraddleNextCycleSync`, or Codex automation.
It registers both new tasks, starts only
`StraddleFidelityTargetCollector`, waits for a fresh read-only heartbeat, and
leaves `StraddleFidelityCycleSync` registered but stopped.

Use these task names and coordinator arguments:

```powershell
param(
    [string]$Workspace = "",
    [string]$PythonPath = "",
    [string]$SshAlias = "nishahomes-vps",
    [string]$RemoteRoot = "/opt/straddle-fidelity-candidate"
)
$collectorTaskName = "StraddleFidelityTargetCollector"
$coordinatorTaskName = "StraddleFidelityCycleSync"
$runtimeRoot = Join-Path $Workspace "artifacts\live\independent-fidelity"
$collectorArguments = @(
    "-m", "straddle_replica.monitor_cli", "monitor-live",
    "--terminal", '"D:\MT5ObserverTerminal\terminal64.exe"',
    "--output", '"D:\MT5ObserverData\isolated-live"',
    "--account", "901018",
    "--server", '"AchieverGlobalMarkets-Server"',
    "--symbol", "XAUUSD",
    "--poll-ms", "50",
    "--checkpoint-seconds", "30",
    "--exit-on-connection-error",
    "--require-read-only"
) -join " "
$commonRoot = (
    "$RemoteRoot/wineprefix/drive_c/users/mt5/AppData/Roaming/" +
    "MetaQuotes/Terminal/Common/Files"
)
$coordinatorArguments = @(
    '"tools\run_shadow_coordinator.py"',
    "--target-observer-root", '"D:\MT5ObserverData\isolated-live"',
    "--observer-state-path",
    ('"' + (Join-Path $runtimeRoot "observer-state.json") + '"'),
    "--state-path",
    ('"' + (Join-Path $runtimeRoot "coordinator-state.json") + '"'),
    "--target-archive-path",
    ('"' + (Join-Path $runtimeRoot "target-cycles.jsonl") + '"'),
    "--remote-ssh-alias", $SshAlias,
    "--remote-root", $RemoteRoot,
    "--remote-command-path",
    "$commonRoot/StraddleShadow/command.csv",
    "--remote-ack-path",
    "$commonRoot/StraddleShadow/ack.csv",
    "--active"
) -join " "
```

Register both actions with `RestartCount 999`, unlimited execution time,
limited user privileges, and `MultipleInstances IgnoreNew`. Start only:

```powershell
Start-ScheduledTask -TaskName $collectorTaskName
```

Before registration, fail without stopping anything if another process already
owns the target Python bridge:

```powershell
$existingOwner = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*straddle_replica.monitor_cli*" -and
        $_.CommandLine -like "*D:\MT5ObserverTerminal\terminal64.exe*"
    }
if ($existingOwner) {
    throw "A target collector owner is already running."
}
```

- [ ] **Step 8: Implement the source-free real release package**

Create `scripts/package_fidelity_release.ps1`:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [long]$ExpectedRealLogin
)
if ($ExpectedRealLogin -le 0) {
    throw "ExpectedRealLogin must be a positive real-account login."
}
```

The script builds `StraddleReplicaReal.ex5`, binds
`ExpectedAccountLogin=$ExpectedRealLogin` in copies of both real presets,
excludes MQL source and credentials, writes `SHA256SUMS.txt`, and creates
`artifacts/StraddleReplica-FIDELITY-RELEASE.zip`.

- [ ] **Step 9: Run deployment contract tests**

Run:

```powershell
python -m pytest tests\test_fidelity_candidate_deployment.py `
  tests\test_demo_vps_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Package but do not deploy yet**

Run:

```powershell
if (-not $env:STRADDLE_FRESH_DEMO_LOGIN) {
    throw 'Set STRADDLE_FRESH_DEMO_LOGIN to the dedicated new demo login.'
}
if (-not $env:STRADDLE_MT5_INSTALLER) {
    throw 'Set STRADDLE_MT5_INSTALLER to the MT5 installer file.'
}
& .\scripts\package_fidelity_candidate.ps1 `
  -ExpectedDemoLogin ([long]$env:STRADDLE_FRESH_DEMO_LOGIN) `
  -Mt5InstallerPath $env:STRADDLE_MT5_INSTALLER
```

`STRADDLE_FRESH_DEMO_LOGIN` must contain the dedicated new demo login. It must
not equal `5054216668`.

Expected: ZIP and hash manifest are created; no terminal or container changes
occur.

- [ ] **Step 11: Write the Task 11 checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  artifacts\StraddleReplica-FIDELITY-CANDIDATE.zip,`
  deploy\vps-docker-candidate\compose.yaml,`
  scripts\deploy_fidelity_candidate_vps.ps1,`
  scripts\install_fidelity_monitor_tasks.ps1,`
  scripts\package_fidelity_release.ps1 `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\task-11-candidate-package.json"
```

## Task 12: Full verification and demo commissioning

**Files:**

- Runtime evidence under:
  `artifacts/live/independent-fidelity/`
- Runtime reports under:
  `artifacts/analysis/independent-fidelity-runs/`
- Modify after measured results:
  `docs/FIDELITY.md`
- Modify after measured results:
  `README.md`

- [ ] **Step 1: Run the focused regression suite**

Run:

```powershell
python -m pytest `
  tests\test_cycle_accounting.py `
  tests\test_canonical_events.py `
  tests\test_fidelity_score.py `
  tests\test_basket_analysis.py `
  tests\test_fidelity_presets.py `
  tests\test_fidelity_report_tool.py `
  tests\test_shadow_transport.py `
  tests\test_fidelity_candidate_deployment.py `
  tests\test_live_twin.py `
  tests\test_live_twin_gate.py `
  tests\test_observer_health.py `
  tests\test_observer_adapter.py `
  tests\test_shadow_coordinator.py `
  tests\test_mql5_contract.py `
  tests\test_live_twin_deployment_contract.py `
  tests\test_real_exact_contract.py -q
```

Expected: zero failures.

- [ ] **Step 2: Run the full suite and compare with the recorded baseline**

Run:

```powershell
python -m pytest -q
```

Baseline before implementation:

```text
215 passed, 6 failed, 2 errors
```

The eight nonpassing tests are caused by:

- missing `D:\Downloads\ReportHistory-last2days.xlsx`;
- missing `reportlab` in the active Python environment.

Expected after implementation: no new failure category. If the external XLSX
and PDF dependency are supplied, rerun until the full suite passes.

- [ ] **Step 3: Compile and fingerprint both binaries**

Run:

```powershell
& .\scripts\build.ps1
& .\scripts\build_real.ps1
Get-FileHash `
  .\mql5\StraddleReplica.ex5,`
  .\mql5\StraddleReplicaReal.ex5 `
  -Algorithm SHA256
```

Expected: zero compiler warnings/errors and two recorded SHA-256 hashes.

- [ ] **Step 4: Deploy only the prepared candidate container**

Run:

```powershell
& .\scripts\deploy_fidelity_candidate_vps.ps1 `
  -SshAlias nishahomes-vps `
  -PackagePath .\artifacts\StraddleReplica-FIDELITY-CANDIDATE.zip
```

Verify:

- `straddle-replica-demo-vps` ID, state, and restart count are unchanged;
- `straddle-fidelity-candidate-demo` is the only new container;
- no OOM or restart;
- VNC is `127.0.0.1:15915`;
- `MT5_START=0`.

- [ ] **Step 5: Commission the fresh demo account**

Through the SSH-tunneled candidate VNC:

1. run the packaged MT5 installer inside the candidate Wine prefix;
2. install MT5 under `/data/terminal`;
3. log into the dedicated fresh demo account;
4. verify the exact login, server, hedging mode, and XAUUSD;
5. verify at least 60 pending-order slots;
6. copy the bound shadow preset and EX5 into the candidate terminal;
7. verify Algo Trading remains off while account terms are checked;
8. compare the candidate manifest with target terms;
9. set `MT5_START=1` only after the checks pass.

Do not use or modify the existing replica account.

After the candidate writes its runtime manifest, collect and compare terms:

```powershell
$targetManifest=Get-ChildItem `
  'C:\Users\HPUSER\AppData\Roaming\MetaQuotes\Terminal\Common\Files\StraddleObserver' `
  -Filter manifest.csv -Recurse -File |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
$candidateManifestRemote='/opt/straddle-fidelity-candidate/wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleReplicaV2_901018_XAUUSD_manifest.csv'
$candidateManifestLocal='artifacts\live\independent-fidelity\candidate-manifest.csv'
New-Item -ItemType Directory -Force `
  'artifacts\live\independent-fidelity' | Out-Null
scp "nishahomes-vps:$candidateManifestRemote" $candidateManifestLocal
python tools\compare_account_terms.py `
  --target $targetManifest.FullName `
  --demo $candidateManifestLocal `
  --output artifacts\live\independent-fidelity\account-terms.json
```

A mismatch keeps the run `BEST_EFFORT`; it is not hidden or tuned away.

- [ ] **Step 6: Restore strictly read-only target capture**

Install and start exactly one new target collector owner:

```powershell
& .\scripts\install_fidelity_monitor_tasks.ps1 `
  -SshAlias nishahomes-vps `
  -RemoteRoot /opt/straddle-fidelity-candidate
```

Verify:

```text
login=901018
server=AchieverGlobalMarkets-Server
trade_allowed=false
read_only_verified=true
dropped_transactions=0
```

Do not initialize another Python MetaTrader5 connection against the target
observer terminal while the collector is active.

- [ ] **Step 7: Start candidate-scoped cycle synchronization**

The registered `StraddleFidelityCycleSync` task contains this coordinator
command:

```powershell
python tools\run_shadow_coordinator.py `
  --target-observer-root D:\MT5ObserverData\isolated-live `
  --observer-state-path artifacts\live\independent-fidelity\observer-state.json `
  --state-path artifacts\live\independent-fidelity\coordinator-state.json `
  --target-archive-path artifacts\live\independent-fidelity\target-cycles.jsonl `
  --remote-ssh-alias nishahomes-vps `
  --remote-root /opt/straddle-fidelity-candidate `
  --remote-command-path /opt/straddle-fidelity-candidate/wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleShadow/command.csv `
  --remote-ack-path /opt/straddle-fidelity-candidate/wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleShadow/ack.csv `
  --active
```

Start only that new task:

```powershell
Start-ScheduledTask -TaskName StraddleFidelityCycleSync
```

The coordinator may issue only:

- one candidate `RESET` after a target cycle boundary;
- one candidate `START` with the fresh target anchor and step.

It may not issue fill, stop, rearm, cancel, or close commands after `STARTED`.

- [ ] **Step 8: Verify the first paired cycle**

Require:

- target capture remains read-only and gap-free;
- candidate acknowledgement sequence is `RESETTING -> FLAT -> STARTED`;
- the candidate deploys all 60 initial slots exactly once;
- anchor, step, comments, side, level, and lots match;
- no existing VPS ticket changes;
- candidate telemetry contains unique event and deal identities.

If any condition fails, stop only the new candidate coordinator and mark the
cycle `INVALID`.

- [ ] **Step 9: Run the iterative mismatch loop**

After each complete cycle:

```powershell
$telemetryRemote='/opt/straddle-fidelity-candidate/wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleReplicaV2_901018_XAUUSD.csv'
$telemetryLocal='artifacts\live\independent-fidelity\candidate-telemetry.csv'
scp "nishahomes-vps:$telemetryRemote" "$telemetryLocal.tmp"
Move-Item -LiteralPath "$telemetryLocal.tmp" -Destination $telemetryLocal -Force
$buildId=(
  Get-FileHash .\mql5\StraddleReplica.ex5 -Algorithm SHA256
).Hash.ToLowerInvariant()
$qualificationState='artifacts\live\independent-fidelity\qualification-state.json'
if (Test-Path $qualificationState) {
  $state=Get-Content $qualificationState -Raw | ConvertFrom-Json
  if ($state.build_id -eq $buildId) {
    $runStart=$state.started_utc
  }
  else {
    $runStart=(Get-Date).ToUniversalTime().ToString('o')
    @{started_utc=$runStart;build_id=$buildId} |
      ConvertTo-Json |
      Set-Content $qualificationState
  }
}
else {
  $runStart=(Get-Date).ToUniversalTime().ToString('o')
  @{started_utc=$runStart;build_id=$buildId} |
    ConvertTo-Json |
    Set-Content $qualificationState
}
python tools\compare_live_twin.py `
  --target-events artifacts\live\independent-fidelity\target-cycles.jsonl `
  --demo-telemetry artifacts\live\independent-fidelity\candidate-telemetry.csv `
  --tick-size 0.01 `
  --time-tolerance-seconds 1 `
  --build-id $buildId `
  --certification-started-utc $runStart `
  --output-dir artifacts\analysis\independent-fidelity-runs\cycles
```

Then:

```powershell
python tools\build_fidelity_report.py `
  --comparisons-dir artifacts\analysis\independent-fidelity-runs\cycles `
  --output-dir artifacts\analysis\independent-fidelity-runs\latest
```

For each `FAIL`:

1. select the earliest deterministic mismatch;
2. add one failing regression test;
3. make one source correction;
4. run focused and lifecycle regressions;
5. compile and fingerprint;
6. redeploy only the candidate;
7. reset the 20-cycle and 48-hour counters.

- [ ] **Step 10: Complete the qualification gate**

Continue until the same unmodified build records:

- 20 consecutive complete valid paired cycles;
- 48 market-open hours;
- zero deterministic mismatches;
- zero dropped events, sequence gaps, duplicate identities, stale commands, or
  session corruption;
- documented strict lifecycle fidelity, conditional logic fidelity, and
  conditional coverage;
- maximum observed floating drawdown and gross exposure.

If target evidence remains investor-observer only, the highest valid result is
`BEST_EFFORT_PASS`.

Evaluate the measured gate:

```powershell
$pointer=Get-Content `
  'D:\MT5ObserverData\isolated-live\current-session.json' -Raw |
  ConvertFrom-Json
$observerSession=if ($pointer.session_dir) {
  [string]$pointer.session_dir
}
else {
  Join-Path 'D:\MT5ObserverData\isolated-live' $pointer.session_id
}
$healthOutput='artifacts\analysis\independent-fidelity-runs\observer-health.json'
python tools\analyze_observer_health.py `
  --session $observerSession `
  --certification-started-utc $runStart `
  --output $healthOutput
$comparisonArgs=@()
Get-ChildItem `
  'artifacts\analysis\independent-fidelity-runs\cycles' `
  -Filter '*.json' |
  Sort-Object Name |
  ForEach-Object {
    $comparisonArgs += @('--comparison',$_.FullName)
  }
$coordinatorState=Get-Content `
  'artifacts\live\independent-fidelity\coordinator-state.json' -Raw |
  ConvertFrom-Json
$guardFailures=(
  [int]$coordinatorState.skipped_cycles +
  [int]$coordinatorState.sequence_gaps +
  [int]$coordinatorState.session_restarts
)
python tools\evaluate_live_twin_gate.py `
  @comparisonArgs `
  --probe-health $healthOutput `
  --account-terms-report artifacts\live\independent-fidelity\account-terms.json `
  --operational-guard-failures $guardFailures `
  --certification-started-utc $runStart `
  --required-cycles 20 `
  --required-market-hours 48 `
  --output artifacts\analysis\independent-fidelity-runs\gate.json
```

Expected in observer mode:

```text
qualification_status=BEST_EFFORT_PASS
ready_for_formal_fidelity=false
ready_for_best_effort_candidate=true
```

- [ ] **Step 11: Package the final artifacts without activating real trading**

After the gate:

1. require `STRADDLE_REAL_LOGIN` to contain the selected real-account login;
2. run:

   ```powershell
   if (-not $env:STRADDLE_REAL_LOGIN) {
       throw 'Set STRADDLE_REAL_LOGIN to the selected real-account login.'
   }
   & .\scripts\package_fidelity_release.ps1 `
     -ExpectedRealLogin ([long]$env:STRADDLE_REAL_LOGIN)
   ```

3. bind that login through the release package script;
4. package `StraddleReplicaReal.ex5`;
5. include `latest_30_fidelity.set` and `latest_30_real_safe.set`;
6. include SHA-256 hashes and the final fidelity report;
7. exclude MQL source and all credentials;
8. do not install, attach, or enable the EA on a real terminal automatically.

- [ ] **Step 12: Update final documentation**

Update `docs/FIDELITY.md` and `README.md` with:

- final strict lifecycle percentage;
- conditional logic percentage and coverage;
- evidence grade;
- number of complete paired cycles;
- maximum floating drawdown and gross lots;
- unresolved target behaviors;
- broker-dependent differences;
- explicit distinction between `FIDELITY` and `REAL_SAFE`.

- [ ] **Step 13: Write the final checkpoint**

Run:

```powershell
$root='artifacts\checkpoints\2026-08-11-independent-fidelity'
Get-FileHash `
  mql5\StraddleReplica.ex5,`
  mql5\StraddleReplicaReal.ex5,`
  profiles\latest_30_fidelity.set,`
  profiles\latest_30_real_safe.set,`
  artifacts\analysis\independent-fidelity-runs\latest\fidelity-summary.json `
  -Algorithm SHA256 |
  ConvertTo-Json |
  Set-Content "$root\final-release.json"
```
