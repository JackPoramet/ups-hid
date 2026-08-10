@echo off
title PPC 2000D HID Feature Report 0x24 Battery Test Trigger

echo ==============================================================================
echo  PPC 2000D HID Feature Report 0x24 (Usage 0084:0058 Power Device > Test) Test
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

python "%~dp0unit\test_2000d_hid_feature_24.py"

pause
