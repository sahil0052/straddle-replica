# StraddleReplica

`StraddleReplica` is an MT5 hedging stop-grid EA reconstructed from
`ReportHistory-901018.xlsx`. The source report contains 17,638 total trades,
54,742 historical orders, 51 working orders, 35,446 deals, and 284 detected
grid deployments.

The additional `ReportHistory-last2days.xlsx` validation report contains 613
trades, 2,178 historical orders, 54 working orders, 1,213 deals, and 22
`LATEST_30` deployments.

The EA defaults to `LATEST_30` and includes all five observed profile families:

| Profile | Levels per side | Lot tiers | Step |
| --- | ---: | --- | --- |
| `HISTORICAL_50` | 50 | 0.01 / 0.03 / 0.06 | calibrated live M15 ATR(17) |
| `HISTORICAL_60` | 60 | 0.01 / 0.02 / 0.05 | calibrated live M5 ATR(44) |
| `AGGRESSIVE_30` | 30 | 0.08 / 0.41 / 0.82 | anchor / 6000 |
| `LOW_RISK_30` | 30 | 0.01 / 0.02 / 0.05 | anchor / 3000 |
| `LATEST_30` | 30 | 0.01 / 0.06 / 0.15 | anchor / 3000 |

## Contents

- `mql5/`: EA source, include files, and compiled binary.
- `artifacts/StraddleReplica-Manual-Demo-20260808.zip`: current demo-only
  manual test package.
- `artifacts/StraddleReplica-REAL-EXACT-20260808.zip`: manual real-account
  build with optional safety disabled; current behavioral estimate is
  approximately 92%, not proven 100%.
- `profiles/`: five replica presets and one optional safer preset.
- `straddle_replica/`: report extraction, calibration, replay, tick export, and
  event comparison tools.
- `artifacts/golden/`: canonical events extracted from the supplied report.
- `artifacts/anchor-calibration.json`: UTC offset and anchor-source holdout fit.
- `artifacts/spacing-calibration.json`: historical ATR model selection.
- `artifacts/geometry-comparison.json`: deterministic deployment mismatch report.
- `artifacts/tester-aligned-comparison.json`: aligned real-tick EA comparison.
- `artifacts/recent/`: recent golden data, geometry checks, model-selection
  comparisons, and position-level lifecycle mismatches.
- `artifacts/tester/`: Strategy Tester HTML report and canonical telemetry.
- `tester/latest_30.ini`: real-tick Strategy Tester configuration.
- `scripts/`: reproducible build, install, and historical tick download tools.
- `tools/analyze_broker_stop_serialization.py`: separates EA stop decisions
  from the broker's approximately 20-second same-SL execution serialization.
- `tools/analyze_live_rearms.py`: excludes full grid deployments from rearm
  candidates and verifies the observed per-level minimum rearm delay.
- `tools/compare_live_cycle_replay.py`: compares one live cycle with a
  same-start Strategy Tester replay while separating deployment decisions from
  broker execution.
- `tools/compare_live_target_demo.py`: compares the latest target snapshot with
  the latest complete isolated demo cycle and records deterministic profile,
  geometry, and deployment-timing differences.
- `tools/evaluate_exactness_gate.py`: fails closed until capture duration,
  cycle count, deterministic comparisons, and execution parity satisfy the
  configured promotion thresholds.
- `docs/INSTALLATION.md`: installation and operating instructions.
- `docs/FIDELITY.md`: confirmed behavior and remaining reconstruction gaps.
- `mql5/StraddleObserver.mq5`: strictly read-only live transaction/tick/state
  observer.
- `mql5/StraddleTargetProbe.mq5`: same-terminal passive request/result probe
  used by the LATEST_30 live-twin gate.
- `tools/run_shadow_coordinator.py`: synchronizes cycle starts and demo-only
  resets without controlling the target account.
- `tools/compare_live_twin.py`: cycle-paired deterministic and execution
  comparator with explicit `PASS`, `FAIL`, `INVALID`, and `UNPAIRED` results.
- `tools/analyze_probe_health.py` and `tools/evaluate_live_twin_gate.py`:
  measure capture health and enforce the 10-cycle/48-market-hour gate.
- `docs/LIVE_MONITORING.md`: local and VPS monitoring operation.
- `docs/LIVE_TWIN.md`: isolated Achiever demo commissioning and certification.

## Verification

```powershell
python -m pytest -q
.\scripts\build.ps1
.\scripts\build_observer.ps1
.\scripts\build_target_probe.ps1
```

Evaluate the current exactness gate:

```powershell
python tools\evaluate_exactness_gate.py `
  --monitoring-check artifacts\vps\monitoring-check-20260804T053309Z.json `
  --capture-summary artifacts\vps\cumulative-stop-analysis-20260804.json `
  --deployment-replay artifacts\vps\live-cycle-replay-20260803T142848-rearm20.json `
  --lifecycle-comparison artifacts\recent\telemetry-rearm20-confirm-comparison.json `
  --output artifacts\vps\exactness-gate-20260804.json
```

The Ubuntu/Wine VPS is the sole live observer under systemd and a watchdog. On
August 8, 2026 at 08:57 UTC, the MQL observer, Python collector, shadow MT5,
and shadow coordinator were active with zero service restarts. Both collectors
reported 46 orders, 14 positions, read-only status, and zero dropped
transactions. Laptop monitoring remains disabled; its preserved evidence is
under `D:\MT5ObserverData\isolated-live`.

The live-twin validation system is implemented, but the EA is not a verified
100% clone until a matching Achiever demo completes its distinct 10-cycle and
48-market-open-hour gate. Read `docs/FIDELITY.md` and `docs/LIVE_TWIN.md`
before any demo evaluation. Development and verification must not place live
orders.
