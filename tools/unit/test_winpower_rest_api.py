#!/usr/bin/env python3
"""
tools/unit/test_winpower_rest_api.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
ทดสอบยิงคำสั่ง Battery Test ไปยัง Winpower G2 REST API (https://localhost:8081/api/v1/deviceControl/test)
โดยใช้ Token ที่ระบบ Winpower G2 กำหนด เพื่อสั่งการไปยัง 2000D ผ่าน Winpower Engine โดยตรง
"""

from __future__ import annotations

import json
import ssl
import sys
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

# ข้าม SSL Certificate check สำหรับ https://localhost:8081
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

print("🔍 กำลังดึงรายการอุปกรณ์จาก Winpower G2 REST API...")

# ลองดึงจาก /api/v1/device/list หรือ /api/v1/device/all หรือ /api/v1/device/tree
dev_list = winpower_request("https://localhost:8081/api/v1/device/list")
if not dev_list:
    dev_list = winpower_request("https://localhost:8081/api/v1/device/all")
if not dev_list:
    dev_list = winpower_request("https://localhost:8081/api/v1/device/tree")

print(f"   Response: {json.dumps(dev_list, indent=2, ensure_ascii=False)}")

if dev_list and "data" in dev_list:
    devices = dev_list["data"]
    if isinstance(devices, list):
        for dev in devices:
            dev_id = dev.get("id") or dev.get("deviceId")
            dev_name = dev.get("name") or dev.get("alias") or dev.get("modelName")
            print(f"\n🚀 สั่งงาน Quick Battery Test ไปยัง [{dev_name}] (ID: {dev_id})...")
            
            payload = {
                "deviceId": dev_id,
                "testAction": 1, # 1 = QuickTest
                "testDuration": 10
            }
            res_test = winpower_request("https://localhost:8081/api/v1/deviceControl/test", method="POST", data=payload)
            print(f"   ➔ Result: {json.dumps(res_test, ensure_ascii=False)}")
