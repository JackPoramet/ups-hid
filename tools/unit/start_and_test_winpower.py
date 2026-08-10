#!/usr/bin/env python3
"""
tools/unit/start_and_test_winpower.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. ตรวจสอบการรันของ WinpowerG2Service (หรือสตาร์ทผ่าน WinpowerRegister.exe start)
2. รอพอร์ต 8081 HTTPS พร้อมใช้งาน
3. ดึงรายการอุปกรณ์ผ่าน Winpower G2 REST API
4. ยิงคำสั่ง POST /api/v1/deviceControl/test (Quick Test) ไปยัง 2000D เพื่อเกิดเสียง Relay / Beep ทันที
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TOKEN = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9."
    "eyJjcmVhdGVfdGltZV9rZXkiOjE3ODYxMzg3NTU5NzYsInN1YiI6IldJTlBPV0VSX1RPS0VOIiwibmJmIjoxNzg2MTM4NzU1OTgxLCJ0b2tlbl9pZCI6ImE3YThhNjc0LWZlMzYtNDgzOC04NGY5LTgzMTM2ZmJmMTYyYiIsImlzcyI6IldJTlBPV0VSIiwibG9naW5fdXNlcl90eXBlIjoiU3lzQWRtaW4iLCJsb2dpbl91c2VyX2lkIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwiZXhwIjoxNzg2MTQwNTU1OTc2LCJleHBpcmVfdGltZV9rZXkiOjE3ODYxNDA1NTU5NzYsImlhdCI6MTc4NjEzODc1NSwianRpIjoiYTdhOGE2NzQtZmUzNi00ODM4LTg0ZjktODMxMzZmYmYxNjJiIiwidG9rZW5FeHBpcmVkTWludXRlcyI6MzB9."
    "GKqDZv9tEyNyYilB83YHROruJRQWDoNthOKSAb6urv0sAwS496ax8YZNWc8elUkCEOEIz6KmRFZHpcsBub37WQ"
)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def winpower_request(url: str, method: str = "GET", data: dict | None = None) -> dict | None:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.data = body

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            res_body = resp.read().decode("utf-8")
            return json.loads(res_body)
    except Exception as exc:
        print(f"❌ REST API Error ({url}): {exc}")
        return None

print("🚀 ตรวจสอบสถานะการเชื่อมต่อ Winpower G2 REST API (https://localhost:8081)...")

# ลองดึงข้อมูลลูปสูงสุด 10 วินาที
dev_list = None
for retry in range(5):
    dev_list = winpower_request("https://localhost:8081/api/v1/device/list")
    if not dev_list:
        dev_list = winpower_request("https://localhost:8081/api/v1/device/all")
    if dev_list and "data" in dev_list:
        break
    print("  ⏳ รอบริบริการ Winpower G2 API พร้อมใช้งาน...")
    time.sleep(2.0)

if not dev_list or "data" not in dev_list:
    print("⚠️ Winpower G2 Service ยังไม่เปิดพอร์ต 8081 สั่งเริ่มบริการผ่าน WinpowerRegister.exe...")
    try:
        subprocess.run(
            ["powershell", "-Command", "Start-Process 'C:\\Program Files\\WinpowerG2\\bin\\Windows\\WinpowerRegister.exe' -ArgumentList 'start' -Verb RunAs"],
            check=False
        )
    except Exception as e:
        print(f"❌ ไม่สามารถสั่งรัน WinpowerRegister: {e}")

    # รออีก 10 วินาที
    for _ in range(5):
        time.sleep(2.0)
        dev_list = winpower_request("https://localhost:8081/api/v1/device/all")
        if dev_list and "data" in dev_list:
            break

if dev_list and "data" in dev_list:
    devices = dev_list["data"]
    print(f"✅ พบรายการอุปกรณ์จาก Winpower Engine ({len(devices)} เครื่อง):")
    for dev in devices:
        dev_id = dev.get("id") or dev.get("deviceId")
        dev_name = dev.get("name") or dev.get("alias") or dev.get("modelName")
        dev_type = dev.get("model") or dev.get("deviceType")
        print(f"  • ID: {dev_id} | Name: {dev_name} | Type: {dev_type}")
        
        # ค้นหา 2000D (LINE-INT หรือ 000000000)
        if "000000000" in str(dev_name) or "line" in str(dev_type).lower():
            print(f"\n⚡ สั่ง Quick Battery Test ไปยัง PPC 2000D [ID: {dev_id}] ผ่าน Winpower Engine Direct API...")
            payload = {
                "deviceId": dev_id,
                "testAction": 1, # 1 = Quick Test
                "testDuration": 10
            }
            res_test = winpower_request("https://localhost:8081/api/v1/deviceControl/test", method="POST", data=payload)
            print(f"  ➔ ผลลัพธ์จาก Winpower: {json.dumps(res_test, ensure_ascii=False)}")
else:
    print("❌ ไม่สามารถเชื่อมต่อ Winpower G2 API ได้")
