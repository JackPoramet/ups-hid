#!/usr/bin/env python3
"""
tools/unit/find_hid_subclasses.py
Finds all concrete subclasses of HidChannelBase in winpower-comms-1.0.0.jar
"""
import zipfile
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JAVA_EXE = r"C:\Program Files\WinpowerG2\jre\bin\javap.exe"
JAR_PATH = r"C:\Program Files\WinpowerG2\lib\winpower-comms-1.0.0.jar"

with zipfile.ZipFile(JAR_PATH, 'r') as z:
    for name in z.namelist():
        if name.endswith('.class') and 'Channel' in name:
            cls_name = name.replace('/', '.').replace('.class', '')
            cmd = [JAVA_EXE, "-cp", f"{JAR_PATH};C:\\Program Files\\WinpowerG2\\lib\\*", cls_name]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if "extends com.etn.wp.comms.channel.HidChannelBase" in res.stdout or "extends com.etn.wp.comms.channel.ChannelBase" in res.stdout:
                print(f"Class: {cls_name}")
                print(res.stdout)
