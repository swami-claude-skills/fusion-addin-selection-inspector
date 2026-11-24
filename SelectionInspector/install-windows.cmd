@echo off
REM Double-click launcher. Runs the PowerShell installer next to it, bypassing
REM execution policy for this one process only (no system change).
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install-windows.ps1"
endlocal
