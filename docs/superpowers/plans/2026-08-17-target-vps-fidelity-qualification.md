# Target vs VPS EA Fidelity Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that the VPS EA on MetaQuotes demo login `5054578619` matches the read-only target EA at or above 98% deterministic fidelity, with zero deterministic mismatches.

**Architecture:** Keep the target and candidate observers on separate local,
strictly read-only MT5 terminals. The candidate EA continues executing on the
same VPS demo account, but the VPS is not used for monitoring; access it only
to deploy a verified artifact at a proven natural flat boundary. Collect both
event streams locally and independently, pair only complete eligible cycles
ordinally, diagnose the earliest deterministic divergence, and use a
regression-first minimal source fix before any rebuilt artifact is deployed.

**Tech Stack:** MetaTrader 5/MQL5, Python telemetry tools, PowerShell, SSH, systemd/Wine, JSONL/CSV evidence.

---

### Task 1: Maintain Fresh Independent Health Evidence

**Files:**
- Read: `D:\MT5ObserverData\isolated-live\current-session.json`
- Read: `D:\MT5ObserverData\isolated-live\<current-session>\heartbeat.json`
- Read: `C:\websites\mt5 2\artifacts\live\independent-demo-fidelity\target-cycles.jsonl`
- Read: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\observer\current-session.json`
- Read: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\observer\<current-session>\heartbeat.json`
- Read: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\candidate-cycles.jsonl`

- [ ] Verify the target heartbeat is less than five seconds old, `healthy=true`, `read_only_verified=true`, `trade_allowed=false`, and sequence increases.
- [ ] Verify the local candidate heartbeat is less than five seconds old, `healthy=true`, `read_only_verified=true`, and sequence increases.
- [ ] Verify the local candidate manifest is login `5054578619`, server `MetaQuotes-Demo`, with account and terminal `trade_allowed=false`.
- [ ] Verify both local archives are `RUNNING` with zero sequence gaps.
- [ ] Verify the candidate cycle remains bounded to the expected 60 identities after the first locally captured post-boundary cycle start.

### Task 2: Capture Candidate Evidence Locally Without Interrupting Trading

**Files:**
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\observer\`
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\observer-state.json`
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\archive-state.json`
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\archive-health.json`
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\candidate-cycles.jsonl`

- [ ] Keep one unscheduled local collector attached to the investor-mode candidate terminal.
- [ ] Keep one unscheduled local candidate archive process with zero sequence gaps.
- [ ] Treat the cycle active when local observation starts as ineligible and suppress it until a natural flat boundary.
- [ ] Confirm the first post-boundary deployment contains exactly `STR B1..B30` and `STR S1..S30`.

### Task 3: Detect Complete Eligible Cycle Boundaries

**Files:**
- Read: `C:\websites\mt5 2\artifacts\live\independent-demo-fidelity\target-cycles.jsonl`
- Read: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\candidate-cycles.jsonl`
- Create/update: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\eligibility-state.json`

- [ ] Mark a target cycle eligible only when it has a captured `cycle_start`, complete initial identity evidence, and `cycle_complete`.
- [ ] Mark a candidate cycle eligible only when the local archive has a captured `cycle_start`, exactly 60 initial identities, and `cycle_complete`.
- [ ] Exclude cycles spanning terminal handoff, LiveUpdate, missing telemetry, or observer-session gaps.
- [ ] Persist the first unpaired eligible target and candidate cycle IDs for ordinal pairing.

### Task 4: Run the Formal Ordinal Comparator

**Files:**
- Execute: `C:\websites\mt5 2\tools\compare_independent_cycles.py`
- Create: `C:\websites\mt5 2\artifacts\live\local-candidate-5054578619\formal-comparison\`

- [ ] Run with `--pairing ordinal`, the exact target and locally observed candidate JSONL evidence, current build ID, and certification start after the local candidate observer became healthy.
- [ ] Require `pair_count >= 1`; never report a percentage while it is zero.
- [ ] Record strict lifecycle fidelity, conditional logic fidelity, conditional coverage, deterministic mismatch count, timing diagnostics, and P/L diagnostics separately.
- [ ] Qualify only when lifecycle, conditional logic, and coverage are each at least 98% and deterministic mismatches equal zero.

### Task 5: Diagnose the Earliest Proven Deterministic Mismatch

**Files:**
- Read: comparator event-pair and mismatch outputs
- Read: `C:\websites\mt5 2\mql5\include\StraddleEngine.mqh`
- Read: `C:\websites\mt5 2\mql5\include\StraddleReplicaApp.mqh`
- Read: relevant tests under `C:\websites\mt5 2\tests\`
- Create/update: mismatch-specific assessment JSON under `C:\websites\mt5 2\artifacts\live\vps-demo-5054578619\`

- [ ] Identify the first divergent deterministic event, not the largest downstream symptom.
- [ ] Trace its inputs through target evidence, candidate telemetry, profile values, and source control flow.
- [ ] Separate broker execution timing, spread, slippage, and P/L from deterministic logic.
- [ ] State one falsifiable root-cause hypothesis and the evidence supporting it.

### Task 6: Apply One Regression-First Minimal Source Fix

**Files:**
- Modify only the source file responsible for the proven cause.
- Modify/create the smallest relevant test under `C:\websites\mt5 2\tests\`.

- [ ] Add a regression reproducing the exact target/candidate divergence.
- [ ] Run it and observe the expected failure before editing production source.
- [ ] Apply one minimal source change.
- [ ] Run the regression and all relevant lifecycle/conditional suites to GREEN.
- [ ] Re-run existing safety and account-binding tests.

### Task 7: Compile, Package, and Deploy Safely

**Files:**
- Compile: demo wrapper and shared MQL5 source
- Create: uniquely named EX5/SET package under `C:\websites\mt5 2\artifacts\`
- Create: verification assessment under `C:\websites\mt5 2\artifacts\live\vps-demo-5054578619\`

- [ ] Compile with zero errors and zero warnings.
- [ ] Record source, EX5, SET, and package SHA-256 values.
- [ ] Keep the existing VPS EA active while exposure exists; do not use the VPS for observation.
- [ ] Deploy only after independently proving a natural `0 positions / 0 orders` boundary on login `5054578619`.
- [ ] During deployment only, restart `straddle-demo-mt5.service`, verify the same account and exact new hash, then return all monitoring to the local observers.

### Task 8: Repeat Until Formal Qualification

- [ ] Resume Tasks 1–4 with the newly deployed build.
- [ ] Repeat Tasks 5–7 for each newly proven deterministic mismatch.
- [ ] Stop changing source when the formal comparator proves all three required percentages at or above 98% with zero deterministic mismatches.
- [ ] Preserve execution timing and P/L as separate diagnostics and report the final formal evidence paths and hashes.
