# Installation and operation

## Requirements

- MetaTrader 5 build 6090 or a compatible newer build.
- An XAUUSD hedging account with enough pending-order capacity for the selected
  profile.
- Python 3.11 with the packages in `requirements.txt` for report and tick tools.
- The broker's real XAUUSD tick history for historical comparison.

## Build

From `C:\websites\mt5 2`:

```powershell
.\scripts\build.ps1
```

The script invokes `MetaEditor64.exe`, writes `artifacts\compile.log`, requires
zero errors and warnings, and produces `mql5\StraddleReplica.ex5`.

## Install for Strategy Tester

The detected portable terminal data path is `C:\Program Files\MetaTrader 5`.
Install the EA and presets with:

```powershell
.\scripts\install_ea.ps1
```

To copy an already verified build without compiling again:

```powershell
.\scripts\install_ea.ps1 -SkipBuild
```

For another terminal, pass its data directory:

```powershell
.\scripts\install_ea.ps1 -TerminalDataPath "D:\MT5-Test"
```

The installer copies files only to:

- `MQL5\Experts\StraddleReplica`
- `MQL5\Profiles\Tester`

It does not start MetaTrader, open a chart, or enable trading.

## Run the historical Strategy Tester

1. Finish the historical tick download and close any terminal process using the
   same installation directory.
2. Open MetaTrader 5 and select View → Strategy Tester.
3. Select `StraddleReplica\StraddleReplica.ex5`.
4. Select XAUUSD, M1, and “Every tick based on real ticks.”
5. Use June 23, 2026 through August 1, 2026.
6. Load `latest_30.set`, verify `Profile=LATEST_30`, and keep
   `SafetyEnabled=false` for replica comparison.
7. Run the test and export the tester report and EA telemetry.

The supplied command-line configuration is `tester\latest_30.ini`. It is
configured for local agents only, real ticks (`Model=4`), a USD 2,000 initial
deposit, 1:1000 leverage, and automatic terminal shutdown after the test.

`tester\smoke_latest_30.ini` is an evidence configuration aligned to the
reported July 29, 2026 deployment. It uses `ReplicaStartTime` to wait until
19:45:49 UTC and the report balance at that boundary. `ReplicaStartTime=0`
remains the live/default behavior and starts immediately.

`tester\recent_latest_30_canonical.ini` reproduces the recent two-day
position-level comparison. The `recent_stop*.ini` files are calibration
experiments and are not promoted defaults.

## Operating boundaries

- Never attach this EA to a real-account chart during development or
  verification.
- Never attach it to a netting account; initialization is intentionally refused.
- Use a separate demo terminal and account for the required 48-hour forward test.
- Keep AutoTrading disabled except during an explicitly supervised demo test.
- Use one unique magic number for each independent EA instance.
- Do not change symbol specifications, tick model, spread assumptions, or
  account leverage when comparing against the supplied history.
- For historical parity, align both `ReplicaStartTime` and the initial deposit
  to the selected report cycle.
- The replica presets intentionally disable optional safety controls. The
  `latest_30_safe.set` preset enables them but is not behaviorally identical.

Telemetry is written to the terminal common-files directory as
`StraddleReplica_<magic>_<symbol>.csv`. Cycle anchor and step are persisted as
terminal global variables so the EA can reconcile its own orders and positions
after a restart. If owned orders or positions exist but that cycle cannot be
reconstructed safely, initialization fails instead of deploying an overlapping
grid. Telemetry includes position-level `fill`, `stop_exit`, and `close_fill`
events and is compatible with the aligned Python lifecycle comparator.

## Read-only live observer

The forensic observer is separate from the replica EA. Build and package it
with:

```powershell
.\scripts\build_observer.ps1
.\scripts\package_monitor.ps1
```

See `docs\LIVE_MONITORING.md` for the isolated-terminal layout, status and stop
commands, disk paths, watchdog behavior, and VPS installation procedure.
