' Launches start_live_monitor.ps1 with no visible console window.
' Invoked once per minute by the "StraddleObserverMonitor" scheduled task;
' running powershell.exe directly from the task flashed a console every minute.
' Waits for the script and propagates its exit code so the task's
' LastTaskResult stays meaningful for diagnostics.

Dim shell, command, exitCode

command = "powershell.exe -NoProfile -ExecutionPolicy Bypass" _
    & " -File ""C:\websites\mt5 2\scripts\start_live_monitor.ps1""" _
    & " -Workspace ""C:\websites\mt5 2""" _
    & " -TerminalPath ""D:\MT5ObserverTerminal\terminal64.exe""" _
    & " -StartupConfig ""C:\websites\mt5 2\monitor\observer-startup.ini""" _
    & " -OutputRoot ""D:\MT5ObserverData\isolated-live""" _
    & " -PortableTerminal"

Set shell = CreateObject("WScript.Shell")
exitCode = shell.Run(command, 0, True)
WScript.Quit exitCode
