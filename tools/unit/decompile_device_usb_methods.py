#!/usr/bin/env python3
import subprocess
import sys

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\usbcomm-1.0.0.jar"

cmd = [JAVA_EXE, "-cp", JAR_PATH, "santak.lib.DeviceUsb"]
res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
print(res.stdout)
