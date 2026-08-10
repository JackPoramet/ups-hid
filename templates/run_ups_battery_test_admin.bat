@echo off
title Universal UPS Battery Test CLI Runner (Administrator Mode)

echo ==============================================================================
echo  Universal PHOENIXTEC & HID UPS Battery Test Runner (Admin Mode)
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
python "%~dp0ups_battery_test.py" --quick

pause
