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

### A. Lot Sizing Schedule (Strict Parity — Final Regime)
The Target EA changed regimes several times inside `ReportHistory-901018.xlsx`. Parity MUST track the
**final regime (Jul 14–30)**, measured from every order placed in that window:
* **Levels 1 to 10**: `0.01` lots (10,940 orders, zero exceptions at base volume).
* **Levels 11 to 20**: `0.06` lots (2,624 orders).
* **Levels 21 to 30**: `0.15` lots (378 orders).
* Trend-rescue replacement orders trade at exactly `2x` the tier volume (0.12 at L11–20, 0.30 at L21–30).

> NOTE: The older 0.01/0.03/0.06 schedule at 15/25/30 boundaries matches only the June regime and the
> whole-history aggregate. Do NOT regress to it.

### B. Compact Cycle Boundary & Auto-Recenter
* **Median Cycle Price Span**: `20.01 points`.
* **20-Point Auto-Recenter Rule**: If `dist_from_anchor >= 20.0 pts` or `(realized >= $50.0 && net >= -$20.0 && dist >= 15.0 pts)`, execute `BeginClose("grid_recenter", false)` and redeploy flat at current market price.
* **Trend Rescue Breakeven Liquidation**: If `realized >= $200.0` and `net >= -$10.0`, liquidate flat and restart immediately.
* **Cycle Basket Target**: `cycle_target_money = 30.0` (positive final-regime cycle nets cluster at a median of $29.40; most exits land between $25 and $33).
* **Re-arm Delay**: `rearm_delay_seconds = 5` (level re-arms are modally 0–5s after a stop-out; 490 of 2,370 measured re-arms landed inside the first 5s bucket).

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
