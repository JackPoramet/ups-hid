@echo off
title PPC 2000D Battery Test + Real-Time Telemetry Monitor

echo ==============================================================================
echo  PPC 2000D Battery Self-Test + Real-Time Telemetry Monitor
echo ==============================================================================
echo.

:: Request Admin Elevation
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Requesting Administrator Elevation via UAC...
    powershell -NoProfile -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo [OK] Running with Administrator Privileges!
echo [INFO] Stopping WinPower background processes to free USB port...
taskkill /F /IM WinpowerG2.exe /IM javaw.exe >nul 2>&1

echo.
echo Select test mode:
echo   1. Quick Battery Test (10s) + Monitor 25s
echo   2. Read Telemetry Only (no test command)
echo   3. Deep Battery Test + Monitor 10min
echo   4. Cancel Battery Test
echo.
set /p choice="Enter choice [1]: "

if "%choice%"=="2" (
    python "%~dp0unit\test_2000d_batttest_with_telemetry.py" --read-only
) else if "%choice%"=="3" (
    python "%~dp0unit\test_2000d_batttest_with_telemetry.py" --deep --duration 600
) else if "%choice%"=="4" (
    python "%~dp0unit\test_2000d_batttest_with_telemetry.py" --cancel
) else (
    python "%~dp0unit\test_2000d_batttest_with_telemetry.py" --quick
)

pause
