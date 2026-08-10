@echo off

if "%PROCESSOR_ARCHITECTURE%"=="AMD64" goto x64
if "%PROCESSOR_ARCHITECTURE%"=="IA64" goto ia64
exit

:x64
IF not exist C:\Windows\System32\drivers\libusb0.sys (
copy .\amd64\libusb0.sys C:\Windows\System32\drivers\
)
START /WAIT install-filter-amd64.exe --all-devices install --device=HID\Vid_06da.Pid_ffff --device=HID\\Vid_0592.Pid_ffff --device=HID\\Vid_0463.Pid_ffff --device=HID\\Vid_2E66.Pid_0201  --device=HID\\Vid_2E66.Pid_0202 --device=HID\\Vid_2E66.Pid_0203
exit

:ia64
IF not exist C:\Windows\System32\drivers\libusb0.sys (
copy .\ia64\libusb0.sys C:\Windows\System32\drivers\
)
START /WAIT install-filter-ia64.exe --all-devices install --device=HID\Vid_06da.Pid_ffff --device=HID\\Vid_0592.Pid_ffff --device=HID\\Vid_0463.Pid_ffff --device=HID\\Vid_2E66.Pid_0201  --device=HID\\Vid_2E66.Pid_0202 --device=HID\\Vid_2E66.Pid_0203
