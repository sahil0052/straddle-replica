---
name: target-ea-parity
description: >-
  Core operating directive for the StraddleReplica project. Enforces 100% mathematical,
  architectural, and operational lockstep parity between our replica EA (111387094) and the
  Target EA (901018 on AchieverGlobalMarkets). Grants full autonomous execution authority to
  detect, implement, compile, and deploy any parity fixes immediately without asking.
---

# Target EA Parity & Autonomous Execution Directive

## 1. Prime Mission Directive
The **sole and overriding goal** of this project is to make our EA (`111387094`) behave with **100% identical logic, risk profile, execution speed, lot sizing, and lifecycle reset behavior** as the Target EA (`901018`).

### Autonomous Action Authority
Whenever you detect a logic difference, parameter mismatch, boundary drift, or synchronization delay between our EA and the Target EA:
* **DO NOT WAIT OR ASK FOR PERMISSION.**
* **Proactively research, modify code, compile (`metaeditor64.exe`), deploy to VPS, and verify execution immediately.**

---

## 2. Core Architectural Invariants (Target EA Exact Standards)

### A. Lot Sizing Schedule (Strict Parity)
From forensic analysis of all 17,632 closed trades in `ReportHistory-901018.xlsx`:
* **Levels 1 to 15 (0.0 to 22.5 pts)**: `0.01` lots (covers 73.1% of all historical trades).
* **Levels 16 to 25 (24.0 to 37.5 pts)**: `0.03` lots (covers 20.5% of historical trades).
* **Levels 26 to 30 (39.0 to 45.0 pts)**: `0.06` lots (extreme boundaries only).

### B. Compact Cycle Boundary & Auto-Recenter
* **Median Cycle Price Span**: `20.01 points`.
* **20-Point Auto-Recenter Rule**: If `dist_from_anchor >= 20.0 pts` or `(realized >= $50.0 && net >= -$20.0 && dist >= 15.0 pts)`, execute `BeginClose("grid_recenter", false)` and redeploy flat at current market price.
* **Trend Rescue Breakeven Liquidation**: If `realized >= $200.0` and `net >= -$10.0`, liquidate flat and restart immediately.

### C. Step Spacing
* Step mode: `STR_STEP_ANCHOR_DIVISOR` with `divisor = 3000.0` (Step $\approx 1.50$ to $1.51$ points on XAUUSD).
* Total levels: 30 Buy levels above Anchor + 30 Sell levels below Anchor.

### D. Trailing Stops
* Activation: Step 1.
* Distance: 1.0 step.
* Fast pip locking on pullbacks to bank cash gains continuously into balance.

---

## 3. Standard Deployment & Verification Workflow

1. **Edit Source**: Update `mql5/include/StraddleEngine.mqh`, `ProfileCatalog.mqh`, etc.
2. **Compile**: Run MetaEditor on Windows (`0 errors, 0 warnings` required):
   `D:\MT5ReplicaObserverTerminal\metaeditor64.exe /portable /compile:D:\MT5ReplicaObserverTerminal\MQL5\Experts\StraddleReplicaVPS\StraddleReplicaReal.mq5`
3. **Deploy Artifacts**:
   * Copy `.ex5` to `C:\Users\HPUSER\Desktop\StraddleReplicaReal.ex5`.
   * Upload `.ex5` to AWS VPS `/home/ubuntu/mt5-straddle-shadow/MQL5/Experts/StraddleReplica/StraddleReplicaReal.ex5`.
   * Overwrite default `StraddleReplica.ex5` on VPS.
4. **Service Restart**:
   `sudo systemctl restart straddle-shadow-mt5.service`
5. **Verify Logs**: Confirm `[STR] Initialized profile=LATEST_30 levels=30 replica=true` in MQL5 logs.
