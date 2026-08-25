# Live monitoring

## Safety model

The monitor is observation-only:

- It requires account `901018` on `AchieverGlobalMarkets-Server`.
- It refuses to start when `ACCOUNT_TRADE_ALLOWED` or
  `account_info.trade_allowed` is true.
- Neither the MQL5 observer nor the Python collector contains an order-send,
  order-modify, order-delete, or position-close operation.
- No account or VPS credential is stored in this repository, generated
  packages, scheduled tasks, or log files.

Use a separate portable MT5 installation for monitoring. Do not install the
observer into the terminal running the original trading EA.

## Local collector

The laptop collector was disabled on August 3, 2026 after VPS monitoring was
verified. Its existing evidence remains under:

```text
D:\MT5ObserverData\isolated-live
```

The `StraddleObserverMonitor` scheduled task is unregistered, and no local
observer terminal or Python collector is running. The files and isolated
terminal installation are retained for forensic comparison and can be
re-enabled manually if needed.

Stop it with:

```powershell
.\scripts\stop_live_monitor.ps1 `
  -OutputRoot "D:\MT5ObserverData\live"
```

## VPS package

Build the package:

```powershell
.\scripts\package_monitor.ps1
```

The archive is written to:

```text
artifacts\StraddleObserverMonitor.zip
```

On the VPS:

1. Create or install a separate portable MetaTrader 5 terminal.
2. Log that terminal into the target account using investor access and choose
   the option that saves the account locally.
3. Close the monitoring terminal.
4. Extract the package to a permanent directory such as
   `C:\StraddleObserverMonitor`.
5. Run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install_vps_monitor.ps1 `
  -TerminalDataPath "C:\MT5ObserverTerminal" `
  -TerminalPath "C:\MT5ObserverTerminal\terminal64.exe"
```

The startup configuration opens an XAUUSD H1 chart and attaches only
`StraddleObserver`. The Windows scheduled task relaunches the monitoring
terminal and collector after logon. Disconnecting RDP leaves them running;
signing out of Windows stops GUI applications.

## Ubuntu EC2 deployment

The deployed Ubuntu monitor uses Wine, Xvfb, and systemd:

```text
Terminal: /home/ubuntu/mt5-observer
Wine prefix: /home/ubuntu/.wine-mt5
Python data: /home/ubuntu/straddle-data/python
MQL data: /home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver
```

Services:

```text
straddle-xvfb.service
straddle-mt5.service
straddle-python.service
straddle-watchdog.timer
```

Daily analysis is installed separately from the capture services:

```text
straddle-daily-analysis.service
straddle-daily-analysis.timer
```

The timer runs at 00:15 UTC, checks monitor health before and after analysis,
and never stops or restarts the live observer.

The demo EA uses a separate terminal and Wine prefix:

```text
Terminal: /home/ubuntu/mt5-straddle-demo
Wine prefix: /home/ubuntu/.wine-straddle-demo
Service: straddle-demo-mt5.service
Comparison timer: straddle-demo-daily-analysis.timer
Comparison output: /home/ubuntu/straddle-analysis/demo-daily
```

The demo service is not part of `straddle-mt5.service`; stopping or restarting
it cannot stop the read-only target monitor. The EA itself also refuses
initialization unless MT5 reports a demo account.

The target-versus-demo comparison runs daily at 00:20 UTC. It checks target
monitor health before and after analysis, verifies the demo service is active,
and records profile, sequence, lot-tier, spacing, active-slot, fill/stop-event,
and deployment-duration differences. It never stops or restarts either MT5
terminal.

This is the active monitoring deployment. The MQL and Python services share one
Wine runtime and one terminal process. The Python collector waits for a
heartbeat from the current MQL generation before attaching, preventing stale
heartbeat races after service restarts.

Check health with:

```bash
python3 /home/ubuntu/straddle-monitor/bin/check_monitor_health.py \
  --python-root /home/ubuntu/straddle-data/python \
  --mql-root /home/ubuntu/.wine-mt5/drive_c/users/ubuntu/AppData/Roaming/MetaQuotes/Terminal/Common/Files/StraddleObserver
```

The Wine deployment pins NumPy 1.26.4. Newer NumPy builds call a Windows
runtime function that Wine 10 does not implement.

## Capture target

Keep monitoring until both conditions are met:

- at least 48 market-open hours;
- at least ten complete deploy/close/restart cycles.

The most important files are:

- Python `snapshots-*.jsonl` and `ticks-*.csv`;
- MQL5 `transactions-*.csv`, `snapshots-*.csv`, and `ticks-*.csv`;
- `heartbeat.json` and MQL5 heartbeat files;
- terminal Experts and Journal logs.

These records can reveal exact stop assignment, update cadence, cancellation
order, basket-close sequencing, re-arming, and restart timing. They cannot make
future broker slippage deterministic.
