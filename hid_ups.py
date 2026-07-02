"""
HID UPS Deep Scanner - Phoenixtec Innova Unity IOT Tower
VID: 0x06DA (Phoenixtec Power Co., Ltd.)
PID: 0xFFFF (Innova Unity)

สคริปต์นี้เน้น 3 อย่าง:
1) เลือก Report IDs แบบ dynamic จาก descriptor (caps text fallback)
2) อ่าน Feature Report หลายขนาดและหลายรอบ
3) export JSON ที่เก็บทั้ง raw + decoded + descriptor profile
"""

import argparse
import datetime
import json
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import hid


VID = 0x06DA
PID = 0xFFFF

DEFAULT_REPORT_SIZES = (8, 16, 32, 64, 128, 255)
DEFAULT_DESCRIPTOR_TXT = "report_descriptor_live.txt"
DEFAULT_DESCRIPTOR_BIN = "report_descriptor_live.bin"

# ใช้เฉพาะเพื่อ decode ค่าที่ยืนยันแล้วในสคริปต์นี้
LEGACY_DECODE_REPORT_IDS = {
    0x01,
    0x06,
    0x07,
    0x0C,
    0x0D,
    0x10,
    0x14,
    0x17,
    0x24,
    0x25,
    0x26,
    0x27,
    0x29,
    0x31,
}


def auto_int(value: str) -> int:
    return int(value, 0)


def hex_bytes(data: Sequence[int]) -> str:
    return " ".join(f"{b:02X}" for b in data)


def payload_of_report(report: Sequence[int]) -> List[int]:
    if report and len(report) > 1:
        return list(report[1:])
    return []


def parse_supported_report_ids(payload: Sequence[int]) -> List[int]:
    out: List[int] = []
    seen = set()
    for b in payload:
        if 0 <= b <= 0xFF and b != 0 and b not in seen:
            out.append(b)
            seen.add(b)
    return out


def merge_report_ids(*id_groups: Iterable[int]) -> List[int]:
    out: List[int] = []
    seen = set()
    for group in id_groups:
        for rid in group:
            if not (0 <= rid <= 0xFF):
                continue
            if rid in seen:
                continue
            out.append(rid)
            seen.add(rid)
    return out


def stringify_device_info(info: dict) -> dict:
    clean = {}
    for k, v in info.items():
        if isinstance(v, (bytes, bytearray)):
            try:
                clean[k] = v.decode("utf-8", errors="ignore")
            except Exception:
                clean[k] = v.hex()
        else:
            clean[k] = v
    return clean


def empty_descriptor_profile(source: str = "none", notes: Optional[List[str]] = None) -> dict:
    return {
        "source": source,
        "input": {},
        "feature": {},
        "output": {},
        "input_report_ids": [],
        "feature_report_ids": [],
        "output_report_ids": [],
        "notes": notes or [],
    }


def _parse_caps_items_from_text(text: str, cap_name: str) -> Dict[int, dict]:
    header_re = re.compile(r"^\s*-+\s*" + re.escape(cap_name) + r"\[(\d+)\]\s*-+\s*$", re.MULTILINE)
    usage_re = re.compile(r"^\s*Usage\s*:\s*0x([0-9A-Fa-f]+)\s*\(([^)]*)\)", re.MULTILINE)

    def find_hex(body: str, field: str) -> Optional[int]:
        m = re.search(r"^\s*" + re.escape(field) + r"\s*:\s*0x([0-9A-Fa-f]+)", body, re.MULTILINE)
        return int(m.group(1), 16) if m else None

    out: Dict[int, dict] = {}
    headers = list(header_re.finditer(text))
    if not headers:
        return out

    for i, hdr in enumerate(headers):
        start = hdr.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]

        rid = find_hex(body, "ReportID")
        if rid is None:
            continue

        usage_page = find_hex(body, "UsagePage")
        usage = None
        usage_name = None
        m_usage = usage_re.search(body)
        if m_usage:
            usage = int(m_usage.group(1), 16)
            usage_name = m_usage.group(2).strip()

        bit_size = find_hex(body, "BitSize") or 0
        report_count = find_hex(body, "ReportCount") or 1

        item = {
            "usage_page": usage_page,
            "usage": usage,
            "usage_name": usage_name,
            "bit_size": bit_size,
            "report_count": report_count,
        }

        bucket = out.setdefault(rid, {"items": [], "report_size_bits_est": 0})
        bucket["items"].append(item)
        bucket["report_size_bits_est"] += bit_size * max(1, report_count)

    return out


def parse_descriptor_profile_from_caps_txt(path: Path) -> Optional[dict]:
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8", errors="ignore")
    input_caps = _parse_caps_items_from_text(text, "InputCaps")
    feature_caps = _parse_caps_items_from_text(text, "FeatureCaps")

    if not input_caps and not feature_caps:
        return None

    profile = empty_descriptor_profile(source="caps_text")
    profile["source_file"] = str(path)
    profile["input"] = input_caps
    profile["feature"] = feature_caps
    profile["input_report_ids"] = sorted(input_caps.keys())
    profile["feature_report_ids"] = sorted(feature_caps.keys())
    return profile


def parse_descriptor_profile_with_hid_parser(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    if not path.exists():
        return None, f"descriptor bin not found: {path}"

    raw = path.read_bytes()
    if not raw:
        return None, f"descriptor bin is empty: {path}"

    # Windows preparsed collection blob, not HID report descriptor bytes.
    if raw.startswith(b"HidP KDR"):
        return None, "descriptor bin is preparsed collection blob (HidP KDR), hid-parser needs raw HID report descriptor"

    try:
        import hid_parser
    except Exception as exc:
        return None, f"hid-parser import failed: {exc}"

    try:
        rdesc = hid_parser.ReportDescriptor(list(raw))
    except Exception as exc:
        return None, f"hid-parser parse failed: {exc}"

    def build_pool(kind: str) -> Dict[int, dict]:
        ids = getattr(rdesc, f"{kind}_report_ids")
        get_items = getattr(rdesc, f"get_{kind}_items")
        get_size = getattr(rdesc, f"get_{kind}_report_size")

        pool: Dict[int, dict] = {}
        for rid in ids:
            if rid is None:
                continue
            rows = []
            for item in get_items(rid):
                row = {"kind": type(item).__name__, "size_bits": int(getattr(item, "size", 0))}
                usage = getattr(item, "usage", None)
                if usage is not None:
                    row["usage"] = str(usage)
                usages = getattr(item, "usages", None)
                if usages is not None:
                    try:
                        row["usages"] = [str(x) for x in usages]
                    except Exception:
                        row["usages"] = [str(usages)]
                rows.append(row)

            try:
                size_bits = int(get_size(rid))
            except Exception:
                size_bits = 0

            pool[int(rid)] = {"report_size_bits": size_bits, "items": rows}
        return pool

    input_pool = build_pool("input")
    feature_pool = build_pool("feature")
    output_pool = build_pool("output")

    profile = empty_descriptor_profile(source="hid_parser")
    profile["source_file"] = str(path)
    profile["input"] = input_pool
    profile["feature"] = feature_pool
    profile["output"] = output_pool
    profile["input_report_ids"] = sorted(input_pool.keys())
    profile["feature_report_ids"] = sorted(feature_pool.keys())
    profile["output_report_ids"] = sorted(output_pool.keys())
    return profile, None


def load_descriptor_profile(descriptor_bin_path: Path, descriptor_txt_path: Path) -> dict:
    notes: List[str] = []

    profile, err = parse_descriptor_profile_with_hid_parser(descriptor_bin_path)
    if profile is not None:
        profile["notes"] = notes
        return profile
    if err:
        notes.append(err)

    profile = parse_descriptor_profile_from_caps_txt(descriptor_txt_path)
    if profile is not None:
        profile["notes"] = notes
        return profile

    profile = empty_descriptor_profile()
    profile["notes"] = notes
    return profile


def get_descriptor_feature_ids(profile: dict) -> List[int]:
    return [int(x) for x in profile.get("feature_report_ids", []) if isinstance(x, int)]


def get_descriptor_all_ids(profile: dict) -> List[int]:
    return merge_report_ids(
        profile.get("feature_report_ids", []),
        profile.get("input_report_ids", []),
        profile.get("output_report_ids", []),
    )


def _usage_preview(bucket: Optional[dict], max_items: int = 2) -> str:
    if not bucket:
        return "-"

    raw: List[str] = []
    for item in bucket.get("items", []):
        usage_name = item.get("usage_name")
        usage_page = item.get("usage_page")
        usage = item.get("usage")
        if usage_name and usage_page is not None and usage is not None:
            raw.append(f"0x{usage_page:04X}:0x{usage:04X} {usage_name}")
            continue

        if isinstance(item.get("usage"), str):
            raw.append(item["usage"])

        for u in item.get("usages", []) or []:
            raw.append(str(u))

    uniq = []
    seen = set()
    for x in raw:
        if x and x not in seen:
            uniq.append(x)
            seen.add(x)

    if not uniq:
        return "-"

    preview = "; ".join(uniq[:max_items])
    if len(uniq) > max_items:
        preview += f" (+{len(uniq) - max_items})"
    return preview


def print_descriptor_profile_summary(profile: dict) -> None:
    print("\nDescriptor profile:")
    print(f"  source       : {profile.get('source', 'none')}")
    print(f"  input IDs    : {len(profile.get('input_report_ids', []))}")
    print(f"  feature IDs  : {len(profile.get('feature_report_ids', []))}")
    print(f"  output IDs   : {len(profile.get('output_report_ids', []))}")

    merged = get_descriptor_all_ids(profile)
    if merged:
        preview = ", ".join(f"0x{x:02X}" for x in merged[:32])
        print(f"  merged IDs   : {preview}")
        if len(merged) > 32:
            print(f"  ... and {len(merged) - 32} more")

    for note in profile.get("notes", []) or []:
        print(f"  note         : {note}")


def print_descriptor_report_table(profile: dict, max_rows: int = 40) -> None:
    all_ids = get_descriptor_all_ids(profile)
    if not all_ids:
        print("\nDescriptor report table: not available")
        return

    print("\nDescriptor report table (dynamic mapping):")
    print("-" * 108)
    print(f"  {'RID':>6}  {'FeatureBits':>11}  {'InputBits':>9}  {'FeatureUsage':<35}  {'InputUsage':<35}")
    print("  " + "-" * 104)

    for rid in all_ids[:max_rows]:
        f_bucket = profile.get("feature", {}).get(rid)
        i_bucket = profile.get("input", {}).get(rid)
        f_bits = (f_bucket or {}).get("report_size_bits") or (f_bucket or {}).get("report_size_bits_est") or 0
        i_bits = (i_bucket or {}).get("report_size_bits") or (i_bucket or {}).get("report_size_bits_est") or 0
        f_usage = _usage_preview(f_bucket)
        i_usage = _usage_preview(i_bucket)
        print(f"  0x{rid:02X}  {f_bits:>11}  {i_bits:>9}  {f_usage:<35}  {i_usage:<35}")

    if len(all_ids) > max_rows:
        print(f"  ... and {len(all_ids) - max_rows} more rows")


def print_candidate_devices(devices: List[dict]) -> None:
    print("พบอุปกรณ์ที่ match VID/PID:")
    for idx, d in enumerate(devices, start=1):
        print(
            f"  [{idx}] {d.get('manufacturer_string') or '?'} / {d.get('product_string') or '?'} / "
            f"SN={d.get('serial_number') or '?'}  "
            f"iface={d.get('interface_number')} "
            f"usage_page=0x{(d.get('usage_page') or 0):04X} usage=0x{(d.get('usage') or 0):04X}"
        )


def open_ups_device(vid: int = VID, pid: int = PID):
    devices = hid.enumerate(vid, pid)
    if not devices:
        print(f"ไม่พบ VID={vid:04X} PID={pid:04X}")
        return None, None

    print_candidate_devices(devices)

    target = next((d for d in devices if d.get("usage_page") == 0x84 and d.get("usage") == 0x04), None)
    if target is None:
        target = next((d for d in devices if d.get("usage_page") == 0x84), devices[0])

    h = hid.device()
    h.open_path(target["path"])

    print("\nเปิดอุปกรณ์สำเร็จ")
    print(f"  Manufacturer : {target.get('manufacturer_string')}")
    print(f"  Product      : {target.get('product_string')}")
    print(f"  Serial       : {target.get('serial_number')}")
    print(f"  Release      : {target.get('release_number')}")
    print(f"  Usage Page   : 0x{(target.get('usage_page') or 0):04X}")
    print(f"  Usage        : 0x{(target.get('usage') or 0):04X}")
    return h, target


def read_feature_report_best(
    h,
    rid: int,
    sizes: Sequence[int] = DEFAULT_REPORT_SIZES,
    retries: int = 1,
) -> Tuple[Optional[List[int]], dict]:
    best = None
    best_size = None
    best_non_zero = -1
    best_payload_len = -1
    valid_reads = 0
    errors = 0

    for _ in range(max(1, retries)):
        for size in sizes:
            try:
                data = h.get_feature_report(rid, size)
            except Exception:
                errors += 1
                continue

            if not data:
                continue

            valid_reads += 1
            row = list(data)
            payload = payload_of_report(row)
            non_zero = sum(1 for b in payload if b != 0)
            plen = len(payload)
            if (non_zero, plen) > (best_non_zero, best_payload_len):
                best = row
                best_size = size
                best_non_zero = non_zero
                best_payload_len = plen

    return best, {
        "size_used": best_size,
        "payload_len": max(best_payload_len, 0),
        "non_zero_bytes": max(best_non_zero, 0),
        "valid_reads": valid_reads,
        "errors": errors,
    }


def read_all_feature_reports(
    h,
    report_ids: Sequence[int],
    sizes: Sequence[int] = DEFAULT_REPORT_SIZES,
    retries: int = 1,
    include_zero: bool = False,
) -> Tuple[Dict[int, List[int]], Dict[int, dict]]:
    raw: Dict[int, List[int]] = {}
    meta: Dict[int, dict] = {}

    for rid in report_ids:
        data, m = read_feature_report_best(h, rid, sizes=sizes, retries=retries)
        if not data:
            continue
        payload = payload_of_report(data)
        has_non_zero = any(b != 0 for b in payload)
        if not has_non_zero and not include_zero:
            continue

        raw[rid] = data
        m["has_non_zero"] = has_non_zero
        meta[rid] = m

    return raw, meta


def collect_feature_snapshots(
    h,
    report_ids: Sequence[int],
    passes: int = 3,
    delay_sec: float = 0.25,
    sizes: Sequence[int] = DEFAULT_REPORT_SIZES,
    retries: int = 1,
    include_zero: bool = False,
) -> Tuple[Dict[int, List[int]], Dict[int, dict], Dict[int, List[str]]]:
    latest_raw: Dict[int, List[int]] = {}
    latest_meta: Dict[int, dict] = {}
    history: Dict[int, List[str]] = {}

    for i in range(max(1, passes)):
        raw, meta = read_all_feature_reports(
            h,
            report_ids=report_ids,
            sizes=sizes,
            retries=retries,
            include_zero=include_zero,
        )

        for rid, data in raw.items():
            hx = hex_bytes(data)
            history.setdefault(rid, [])
            if hx not in history[rid]:
                history[rid].append(hx)
            latest_raw[rid] = data
            latest_meta[rid] = meta[rid]

        print(
            f"  Snapshot {i + 1}/{max(1, passes)}: "
            f"พบ {len(raw)} report(s), สะสมรวม {len(latest_raw)} report(s)"
        )

        if i < max(1, passes) - 1 and delay_sec > 0:
            time.sleep(delay_sec)

    for rid, variants in history.items():
        latest_meta.setdefault(rid, {})
        latest_meta[rid]["variants"] = len(variants)

    return latest_raw, latest_meta, history


def collect_u16_words(raw: Dict[int, List[int]], report_ids: Optional[Sequence[int]] = None) -> List[dict]:
    source_ids = sorted(raw.keys()) if report_ids is None else [rid for rid in report_ids if rid in raw]
    out: List[dict] = []

    for rid in source_ids:
        payload = payload_of_report(raw[rid])
        for off in range(0, max(0, len(payload) - 1)):
            out.append({"rid": rid, "offset": off, "u16": payload[off] | (payload[off + 1] << 8)})

    return out


def infer_tentative_live_values(raw: Dict[int, List[int]], decoded: dict) -> dict:
    def uniq(values: List[float]) -> List[float]:
        return sorted(set(round(v, 1) for v in values))

    supported: List[int] = []
    for h in decoded.get("supported_reports", []):
        try:
            supported.append(int(str(h), 16))
        except Exception:
            pass

    words = collect_u16_words(raw, report_ids=supported if supported else None)
    if not words:
        return {}

    freq_vals = uniq([w["u16"] / 10.0 for w in words if 450 <= w["u16"] <= 650])
    ac_vals = uniq([w["u16"] / 10.0 for w in words if 1700 <= w["u16"] <= 2700])
    batt_vals = uniq([w["u16"] / 10.0 for w in words if 300 <= w["u16"] <= 600])
    runtime_vals = sorted(set([w["u16"] for w in words if 60 <= w["u16"] <= 3000]))

    out: Dict[str, object] = {}

    if freq_vals:
        out["tentative.frequency.candidates"] = freq_vals[:8]
        target = float(decoded.get("input.frequency", 50))
        out["tentative.input.frequency"] = min(freq_vals, key=lambda x: abs(x - target))
        out["tentative.output.frequency"] = out["tentative.input.frequency"]

    if ac_vals:
        out["tentative.ac.voltage.candidates"] = ac_vals[:10]
        target = float(decoded.get("output.voltage", 230))
        out_v = min(ac_vals, key=lambda x: abs(x - target))
        out["tentative.output.voltage"] = out_v

        remain = [v for v in ac_vals if abs(v - out_v) > 0.05]
        if remain:
            target_in = float(decoded.get("input.voltage.nominal", out_v))
            out["tentative.input.voltage"] = min(remain, key=lambda x: abs(x - target_in))

    if batt_vals:
        out["tentative.battery.voltage.candidates"] = batt_vals[:10]
        out["tentative.battery.voltage"] = max(batt_vals)

    if runtime_vals:
        out["tentative.runtime.min.candidates"] = runtime_vals[:10]
        m = max(runtime_vals)
        out["tentative.runtime.min"] = m
        out["tentative.runtime.hr"] = round(m / 60.0, 2)

    return out


def decode_feature_reports(raw: Dict[int, List[int]]) -> dict:
    ups: Dict[str, object] = {}

    def payload(rid: int) -> Optional[List[int]]:
        d = raw.get(rid)
        return payload_of_report(d) if d else None

    # Report 0x01: Status flags (mapping ตามไฟล์ UPS_data.py)
    d = payload(0x01)
    if d:
        ac = bool(d[0]) if len(d) > 0 else False
        below_capacity_limit = bool(d[1]) if len(d) > 1 else False
        charging = bool(d[2]) if len(d) > 2 else False
        discharging = bool(d[4]) if len(d) > 4 else False
        status_good = bool(d[5]) if len(d) > 5 else False

        ups.update(
            {
                "ac_present": ac,
                "below_capacity_limit": below_capacity_limit,
                "charging": charging,
                "discharging": discharging,
                "status_good": status_good,
            }
        )

    # Report 0x02: Fault flags
    d = payload(0x02)
    if d:
        ups["internal_failure"] = bool(d[0]) if len(d) > 0 else False
        ups["need_replacement"] = bool(d[1]) if len(d) > 1 else False
        ups["overload"] = bool(d[2]) if len(d) > 2 else False
        ups["shutdown_imminent"] = bool(d[3]) if len(d) > 3 else False

    # Report 0x03: Over temperature flag
    d = payload(0x03)
    if d:
        ups["over_temperature"] = bool(d[0]) if len(d) > 0 else False

    # Compose NUT-like status string from consolidated flags
    ac = bool(ups.get("ac_present", False))
    discharging = bool(ups.get("discharging", False))
    below_capacity = bool(ups.get("below_capacity_limit", False))
    overload = bool(ups.get("overload", False))
    status_parts = ["OL" if ac else "OB"]
    if discharging:
        status_parts.append("DISCHRG")
    if below_capacity:
        status_parts.append("LB")
    if overload:
        status_parts.append("OVER")
    ups["ups.status"] = " ".join(status_parts)

    # Report 0x06: battery capacity + runtime (u32)
    d = payload(0x06)
    if d:
        if len(d) >= 1:
            ups["battery.charge"] = d[0]
            ups["battery_capacity_percent"] = d[0]
        if len(d) >= 5:
            rt_s = d[1] | (d[2] << 8) | (d[3] << 16) | (d[4] << 24)
            ups["runtime_remaining_sec"] = rt_s
            ups["battery.runtime"] = rt_s
            ups["battery.runtime.hr"] = round(rt_s / 3600.0, 2)

    # Report 0x07: percent load / temperature / battery voltage (+raw fields)
    d = payload(0x07)
    if d:
        if len(d) >= 2:
            ups["percent_load"] = d[1]

        if len(d) >= 5:
            temp_k = d[3] | (d[4] << 8)
            if temp_k > 0:
                ups["temperature_c"] = round(temp_k - 273.15, 1)
                ups["ups.temperature"] = ups["temperature_c"]

        if len(d) >= 11:
            ups["battery_voltage_v"] = round((d[9] | (d[10] << 8)) / 10.0, 1)

        if len(d) >= 5:
            ups["r07_w0"] = d[0] | (d[1] << 8)
            ups["r07_b2"] = d[2] if len(d) > 2 else 0
            ups["r07_w3"] = d[3] | (d[4] << 8)
            if len(d) >= 11:
                ups["r07_w9"] = d[9] | (d[10] << 8)

    d = payload(0x08)
    if d and len(d) >= 1:
        ups["low_batt_alert_limit_percent"] = d[0]

    d = payload(0x0C)
    if d and len(d) >= 4:
        ups["battery.charge.low"] = d[2]
        ups["battery.charge.high"] = d[3]

    d = payload(0x0D)
    if d and len(d) >= 1:
        ups["input.frequency"] = d[0]

    d = payload(0x10)
    if d:
        supported = parse_supported_report_ids(d)
        if supported:
            ups["supported_reports"] = [f"0x{x:02X}" for x in supported]

    d = payload(0x14)
    if d and len(d) >= 2:
        ups["input.frequency.nominal"] = d[0]
        ups["input.voltage.nominal"] = d[1]
        ups["config_nominal_frequency_hz"] = d[0]
        ups["config_nominal_voltage_v"] = d[1]

    # Report 0x31: Input Frequency (u16×10 at offset 0) + Input Voltage (u16×10 at offset 2)
    # ยืนยันจาก usbmon: RID=0x31 data=[0xf4,0x01,0x6d,0x08] → freq=500/10=50.0Hz, volt=2157/10=215.7V
    d = payload(0x31)
    if d and len(d) >= 4:
        freq_raw = d[0] | (d[1] << 8)
        volt_raw = d[2] | (d[3] << 8)
        if freq_raw > 0:
            ups["input.frequency"] = round(freq_raw / 10.0, 1)
        if volt_raw > 0:
            ups["input.voltage"] = round(volt_raw / 10.0, 1)

    d = payload(0x17)
    if d and len(d) >= 2:
        ups["input.transfer.low"] = d[0] | (d[1] << 8)

    d = payload(0x25)
    if d and len(d) >= 3:
        # เก็บไว้เป็น runtime สำรอง (บาง firmware ใช้รายงานนี้)
        rt_s_alt = d[1] | (d[2] << 8)
        ups["runtime_alt_sec"] = rt_s_alt
        if "battery.runtime" not in ups:
            ups["battery.runtime"] = rt_s_alt
            ups["battery.runtime.hr"] = round(rt_s_alt / 3600.0, 2)

    d = payload(0x26)
    if d and len(d) >= 3:
        ups["ups.firmware"] = f"{d[0]}.{d[1]}.{d[2]}"

    # Report 0x24: Self-test status
    # ยืนยันจากการทดสอบจริง (usbmon + python polling):
    #   0x01 = Idle / Passed (before & after successful test)
    #   0x05 = Test in progress (~10 seconds)
    #   0x04 = Failed (hypothesis, ไม่สามารถยืนยันได้โดยไม่มีแบตเตอรี่เสีย)
    d = payload(0x24)
    if d and len(d) >= 1:
        val = d[0]
        ups["battery_test_status_raw"] = val
        ups["battery_test_status"] = {
            0x01: "idle",
            0x02: "warning",
            0x03: "abort",
            0x04: "failed",
            0x05: "running",
        }.get(val, f"unknown(0x{val:02X})")

    # Report 0x27: Status flags (ยืนยันจาก usbmon — d[3] เปลี่ยนระหว่าง self-test)
    d = payload(0x27)
    if d and len(d) >= 4:
        ups["test_discharge_active"] = bool(d[3])

    # Report 0x42: output power meter
    d = payload(0x42)
    if d and len(d) >= 14:
        ups["output_active_power_w"] = d[4] | (d[5] << 8)
        ups["output_apparent_power_va"] = d[6] | (d[7] << 8)
        ups["output_current_a"] = round((d[8] | (d[9] << 8)) / 10.0, 1)
        ups["output_frequency_hz"] = round((d[10] | (d[11] << 8)) / 10.0, 1)
        ups["output_voltage_v"] = round((d[12] | (d[13] << 8)) / 10.0, 1)
        ups["output.voltage"] = ups["output_voltage_v"]

    # Report 0x74: max power config
    d = payload(0x74)
    if d and len(d) >= 5:
        ups["config_max_active_power_w"] = d[1] | (d[2] << 8)
        ups["config_max_apparent_power_va"] = d[3] | (d[4] << 8)

    d = payload(0x29)
    if d and len(d) >= 4:
        ts = d[0] | (d[1] << 8) | (d[2] << 16) | (d[3] << 24)
        try:
            dt = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
            ups["last_event_date"] = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            ups["last_event_date"] = f"0x{ts:08X}"

    ups["scan.report_count"] = len(raw)
    ups["scan.report_ids"] = [f"0x{rid:02X}" for rid in sorted(raw.keys())]

    # Infer operating mode (same idea as UPS_data.py)
    ac_in = bool(ups.get("ac_present", False))
    batt_discharging = bool(ups.get("discharging", False))
    vout = float(ups.get("output_voltage_v", ups.get("output.voltage", 0.0)) or 0.0)

    if ac_in and not batt_discharging:
        if vout < 50.0:
            ups["ups_mode"] = "Standby Mode (เสียบปลั๊ก/ปิดเครื่อง)"
        else:
            ups["ups_mode"] = "Line Mode (ไฟปกติ)"
    elif (not ac_in) and batt_discharging:
        ups["ups_mode"] = "Battery Mode (ไฟดับ!)"
    elif (not ac_in) and (not batt_discharging):
        ups["ups_mode"] = "Turned Off"
    else:
        ups["ups_mode"] = "Unknown / Fault"

    if bool(ups.get("charging", False)):
        ups["ups_mode"] += " [Charging]"

    return ups


def print_ups_data(ups: dict) -> None:
    print("\n" + "=" * 68)
    print("UPS Data (Decoded from Feature Reports)")
    print("=" * 68)

    rows = [
        ("ups.status", "NUT Status", ""),
        ("ups_mode", "UPS Mode", ""),
        ("ac_present", "AC Present", ""),
        ("charging", "Charging", ""),
        ("discharging", "Discharging", ""),
        ("below_capacity_limit", "Below Capacity Limit", ""),
        ("status_good", "Status Good", ""),
        ("overload", "Overload", ""),
        ("internal_failure", "Internal Failure", ""),
        ("need_replacement", "Need Replacement", ""),
        ("over_temperature", "Over Temperature", ""),
        ("shutdown_imminent", "Shutdown Imminent", ""),
        ("battery.charge", "Battery Charge", "%"),
        ("battery_capacity_percent", "Battery Capacity", "%"),
        ("low_batt_alert_limit_percent", "Low Batt Alert Limit", "%"),
        ("battery.charge.low", "Low Batt Threshold", "% (config)"),
        ("battery.runtime", "Runtime Remaining", "s"),
        ("runtime_remaining_sec", "Runtime Remaining", "s"),
        ("battery.runtime.hr", "Runtime Remaining", "hr"),
        ("ups.temperature", "Temperature", "C"),
        ("temperature_c", "Temperature", "C"),
        ("percent_load", "Percent Load", "%"),
        ("battery_voltage_v", "Battery Voltage", "V"),
        ("output.voltage", "Output Voltage", "V"),
        ("output_voltage_v", "Output Voltage", "V"),
        ("output_current_a", "Output Current", "A"),
        ("output_frequency_hz", "Output Frequency", "Hz"),
        ("output_active_power_w", "Output Active Power", "W"),
        ("output_apparent_power_va", "Output Apparent Power", "VA"),
        ("input.frequency", "Input Frequency", "Hz"),
        ("input.voltage.nominal", "Nominal Voltage", "V (config)"),
        ("input.frequency.nominal", "Nominal Frequency", "Hz (config)"),
        ("config_nominal_voltage_v", "Config Nominal Voltage", "V"),
        ("config_nominal_frequency_hz", "Config Nominal Frequency", "Hz"),
        ("config_max_active_power_w", "Config Max Active Power", "W"),
        ("config_max_apparent_power_va", "Config Max Apparent Power", "VA"),
        ("input.transfer.low", "Low Transfer Voltage", "V"),
        ("ups.firmware", "Firmware Version", ""),
        ("last_event_date", "Last Event Date", ""),
        ("supported_reports", "Supported Report IDs", ""),
        ("scan.report_count", "Detected Report Count", ""),
    ]

    for key, label, unit in rows:
        if key not in ups:
            continue
        val = ups[key]
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        print(f"  {label:<30} {val}{(' ' + unit) if unit else ''}")

    research = {k: v for k, v in ups.items() if k.startswith("r07_")}
    if research:
        print("\n  [Report 0x07 - raw fields pending mapping]")
        for k, v in research.items():
            print(f"    {k:<10} = {v}")

    tentative = {k: v for k, v in ups.items() if k.startswith("tentative.")}
    if tentative:
        print("\n  [Tentative Live Values - needs validation]")
        show = [
            ("tentative.battery.voltage", "Battery Voltage (tentative)", "V"),
            ("tentative.input.voltage", "Input Voltage (tentative)", "V"),
            ("tentative.output.voltage", "Output Voltage (tentative)", "V"),
            ("tentative.input.frequency", "Input Frequency (tentative)", "Hz"),
            ("tentative.output.frequency", "Output Frequency (tentative)", "Hz"),
            ("tentative.runtime.min", "Remaining Time (tentative)", "min"),
            ("tentative.runtime.hr", "Remaining Time (tentative)", "hr"),
        ]
        for key, label, unit in show:
            if key in tentative:
                print(f"    {label:<30} {tentative[key]} {unit}")

        for ckey in (
            "tentative.battery.voltage.candidates",
            "tentative.ac.voltage.candidates",
            "tentative.frequency.candidates",
            "tentative.runtime.min.candidates",
        ):
            if ckey in tentative:
                print(f"    {ckey:<30} {tentative[ckey]}")


def dump_raw(raw: Dict[int, List[int]]) -> None:
    print("\nRaw Feature Reports:")
    print("-" * 68)
    for rid, data in sorted(raw.items()):
        print(f"  0x{rid:02X} ({len(data):>3}B): {hex_bytes(data)}")


def print_feature_coverage(meta: Dict[int, dict], requested_ids: Sequence[int]) -> None:
    print("\nFeature Report Coverage:")
    print("-" * 68)
    print(f"  Requested IDs : {len(requested_ids)}")
    print(f"  Got reports   : {len(meta)}")

    for rid in sorted(meta.keys()):
        m = meta[rid]
        print(
            f"  0x{rid:02X}  payload={m.get('payload_len', 0):>3}B  "
            f"nonzero={m.get('non_zero_bytes', 0):>3}  "
            f"variants={m.get('variants', 1):>2}  "
            f"size_used={m.get('size_used')}"
        )


def print_report_variants(history: Dict[int, List[str]]) -> None:
    changed = {rid: variants for rid, variants in history.items() if len(variants) > 1}
    if not changed:
        print("\nไม่มี report ใดที่เปลี่ยนค่าในรอบ snapshot")
        return

    print("\nReports ที่มีค่าเปลี่ยนระหว่าง snapshot:")
    print("-" * 68)
    for rid, variants in sorted(changed.items()):
        print(f"  0x{rid:02X}: {len(variants)} variants")
        for idx, hx in enumerate(variants[:5], start=1):
            print(f"    #{idx}: {hx}")
        if len(variants) > 5:
            print(f"    ... และอีก {len(variants) - 5} variants")


def print_unknown_reports(raw: Dict[int, List[int]], descriptor_profile: Optional[dict] = None) -> None:
    known_ids = set(LEGACY_DECODE_REPORT_IDS)
    if descriptor_profile:
        known_ids.update(get_descriptor_all_ids(descriptor_profile))

    unknown_ids = [rid for rid in sorted(raw.keys()) if rid not in known_ids]
    if not unknown_ids:
        print("\nไม่พบ unknown report นอกเหนือจากรายการที่รู้จักจาก descriptor/decode")
        return

    print("\nUnknown Reports (ยังไม่ยืนยันความหมาย):")
    print("-" * 68)
    for rid in unknown_ids:
        data = raw[rid]
        payload = payload_of_report(data)
        words = []
        for i in range(0, len(payload) - 1, 2):
            words.append(payload[i] | (payload[i + 1] << 8))
        words_preview = ", ".join(str(w) for w in words[:6]) if words else "-"
        ascii_preview = "".join(chr(b) if 32 <= b <= 126 else "." for b in payload[:24])
        print(f"  0x{rid:02X}  len={len(payload):>3}B  u16={words_preview}  ascii='{ascii_preview}'")


def read_input_reports(
    h,
    duration_sec: float = 10,
    report_size: int = 64,
    timeout_ms: int = 500,
    max_events: int = 200,
) -> dict:
    print(f"\nรอ Input Reports {duration_sec}s (blocking + {timeout_ms}ms timeout)...")
    print("  [กด Ctrl+C หยุด]\n")

    events = []
    by_id: Dict[int, int] = {}
    start = time.time()

    try:
        while time.time() - start < duration_sec:
            data = h.read(report_size, timeout_ms)
            if not data:
                continue
            data = list(data)
            rid = data[0] if data else -1
            by_id[rid] = by_id.get(rid, 0) + 1
            t = time.time() - start
            hx = hex_bytes(data)
            print(f"  [{t:6.2f}s] ID=0x{rid:02X} ({len(data)}B): {hx}")
            events.append({"t_sec": round(t, 3), "id": rid, "len": len(data), "hex": hx, "bytes": data})
            if len(events) >= max_events:
                print(f"\n  ถึง max_events={max_events}, หยุดเก็บ Input Reports")
                break
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"  Error: {exc}")

    if not events:
        print("  ไม่มี Input Reports")
        print("  -> UPS รุ่นนี้อาจใช้ Feature Report polling เป็นหลัก")
    else:
        print("\nInput Report Summary:")
        for rid, cnt in sorted(by_id.items()):
            print(f"  ID 0x{rid:02X}: {cnt} event(s)")

    return {
        "count": len(events),
        "by_id": {f"0x{rid:02X}": cnt for rid, cnt in sorted(by_id.items())},
        "events": events,
    }


def print_monitor_snapshot(ups: dict) -> None:
    rows = [
        ("ups.status", "NUT Status", ""),
        ("ups_mode", "UPS Mode", ""),
        ("ac_present", "AC Present", ""),
        ("charging", "Charging", ""),
        ("discharging", "Discharging", ""),
        ("below_capacity_limit", "Below Capacity Limit", ""),
        ("status_good", "Status Good", ""),
        ("battery.charge", "Battery Charge", "%"),
        ("battery_capacity_percent", "Battery Capacity", "%"),
        ("battery.charge.low", "Low Batt Threshold", "% (config)"),
        ("runtime_remaining_sec", "Runtime Remaining", "s"),
        ("battery.runtime.hr", "Runtime Remaining", "hr"),
        ("temperature_c", "Temperature", "C"),
        ("percent_load", "Percent Load", "%"),
        ("battery_voltage_v", "Battery Voltage", "V"),
        ("output_voltage_v", "Output Voltage", "V"),
        ("output_current_a", "Output Current", "A"),
        ("output_frequency_hz", "Output Frequency", "Hz"),
        ("output_active_power_w", "Output Active Power", "W"),
        ("output_apparent_power_va", "Output Apparent Power", "VA"),
        ("input.frequency", "Input Frequency", "Hz"),
        ("input.voltage.nominal", "Nominal Voltage", "V (config)"),
        ("input.frequency.nominal", "Nominal Frequency", "Hz (config)"),
        ("config_nominal_voltage_v", "Config Nominal Voltage", "V"),
        ("config_nominal_frequency_hz", "Config Nominal Frequency", "Hz"),
        ("input.transfer.low", "Low Transfer Voltage", "V"),
        ("ups.firmware", "Firmware Version", ""),
        ("last_event_date", "Last Event Date", ""),
        ("supported_reports", "Supported Report IDs", ""),
        ("scan.report_count", "Detected Report Count", ""),
    ]

    for key, label, unit in rows:
        if key not in ups:
            continue
        val = ups[key]
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        suffix = f" {unit}" if unit else ""
        print(f"  {label:<30} {val}{suffix}")


def monitor_ups(h, report_ids: Sequence[int], interval: float = 1.0, count: int = 20) -> None:
    print(f"\n{'=' * 78}")
    print(f"Monitor (poll ทุก {interval}s)  กด Ctrl+C หยุด")
    print(f"{'=' * 78}")

    try:
        for _ in range(max(1, count)):
            raw, _ = read_all_feature_reports(
                h,
                report_ids=report_ids,
                sizes=(64,),
                retries=1,
                include_zero=False,
            )
            u = decode_feature_reports(raw)
            u.update(infer_tentative_live_values(raw, u))
            print("\033[H\033[J", end="")
            print("=== UPS Monitor (1s) ===")
            print(f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            print_monitor_snapshot(u)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n  หยุด monitor")


def resolve_json_path(user_value: str) -> Path:
    if user_value == "":
        ts = time.strftime("%Y%m%d_%H%M%S")
        return Path(f"ups_scan_{ts}.json")
    return Path(user_value)


def build_export_payload(
    device_info: dict,
    requested_ids: Sequence[int],
    raw: Dict[int, List[int]],
    meta: Dict[int, dict],
    history: Dict[int, List[str]],
    decoded: dict,
    input_reports: dict,
    descriptor_profile: Optional[dict] = None,
) -> dict:
    feature_reports = {}
    for rid, data in sorted(raw.items()):
        feature_reports[f"0x{rid:02X}"] = {
            "bytes": data,
            "hex": hex_bytes(data),
            "payload_bytes": payload_of_report(data),
            "meta": meta.get(rid, {}),
            "variants": history.get(rid, []),
        }

    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "device": stringify_device_info(device_info),
        "scan": {
            "requested_ids": [f"0x{rid:02X}" for rid in requested_ids],
            "captured_ids": [f"0x{rid:02X}" for rid in sorted(raw.keys())],
            "captured_count": len(raw),
            "descriptor_profile_source": (descriptor_profile or {}).get("source", "none"),
        },
        "decoded": decoded,
        "descriptor_profile": descriptor_profile or {},
        "feature_reports": feature_reports,
        "input_reports": input_reports,
    }


def save_json_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nบันทึกผลสแกน JSON: {path}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deep USB HID scanner for UPS")
    p.add_argument("--vid", type=auto_int, default=VID, help="USB Vendor ID (default: 0x06DA)")
    p.add_argument("--pid", type=auto_int, default=PID, help="USB Product ID (default: 0xFFFF)")

    p.add_argument("--descriptor-bin", default=DEFAULT_DESCRIPTOR_BIN, help="Raw descriptor bin for hid-parser")
    p.add_argument("--descriptor-txt", default=DEFAULT_DESCRIPTOR_TXT, help="HID caps text fallback")
    p.add_argument("--no-descriptor-profile", action="store_true", help="Disable descriptor-driven mapping")

    p.add_argument("--rid-min", type=auto_int, default=0x01, help="Min Report ID (default: 0x01)")
    p.add_argument("--rid-max", type=auto_int, default=0xFF, help="Max Report ID (default: 0xFF)")
    p.add_argument("--passes", type=int, default=3, help="Feature scan passes (default: 3)")
    p.add_argument("--scan-delay", type=float, default=0.25, help="Delay between passes in sec")
    p.add_argument("--retries", type=int, default=1, help="Retries per report ID")
    p.add_argument("--include-zero", action="store_true", help="Keep reports with all-zero payload")

    p.add_argument("--input-sec", type=float, default=10.0, help="Input report capture duration")
    p.add_argument("--input-size", type=int, default=64, help="Input report read size")

    p.add_argument("--monitor-interval", type=float, default=1.0, help="Monitor poll interval")
    p.add_argument("--monitor-count", type=int, default=20, help="Monitor row count")
    p.add_argument("--no-monitor", action="store_true", help="Skip monitor section")

    p.add_argument(
        "--json",
        dest="json_path",
        nargs="?",
        const="",
        default=None,
        help="Save full scan to JSON. Use --json or --json path/to/file.json",
    )
    return p


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.rid_min < 0 or args.rid_max > 0xFF or args.rid_min > args.rid_max:
        print("ช่วง Report ID ไม่ถูกต้อง (ต้องอยู่ใน 0x00..0xFF และ min <= max)")
        return 2

    print("Phoenixtec Innova Unity IOT Tower - HID UPS Deep Scanner")
    print(f"Target: VID=0x{args.vid:04X} PID=0x{args.pid:04X}")
    print(
        "Feature scan config: "
        f"RID=0x{args.rid_min:02X}..0x{args.rid_max:02X}, "
        f"passes={args.passes}, retries={args.retries}, sizes={DEFAULT_REPORT_SIZES}"
    )

    h, info = open_ups_device(args.vid, args.pid)
    if not h:
        return 1

    try:
        if args.no_descriptor_profile:
            descriptor_profile = empty_descriptor_profile(notes=["disabled by --no-descriptor-profile"])
        else:
            descriptor_profile = load_descriptor_profile(Path(args.descriptor_bin), Path(args.descriptor_txt))

        print_descriptor_profile_summary(descriptor_profile)
        print_descriptor_report_table(descriptor_profile)

        descriptor_feature_ids = [
            rid for rid in get_descriptor_feature_ids(descriptor_profile) if args.rid_min <= rid <= args.rid_max
        ]

        if descriptor_feature_ids:
            base_ids = descriptor_feature_ids
            print("\nใช้ Feature IDs จาก descriptor profile: " + ", ".join(f"0x{x:02X}" for x in base_ids))
        else:
            base_ids = list(range(args.rid_min, args.rid_max + 1))
            print("\nไม่มี Feature IDs จาก descriptor profile -> fallback scan ตามช่วง RID ที่กำหนด")

        pre_scan_ids = merge_report_ids(base_ids, [0x10])

        pre_raw, _ = read_all_feature_reports(
            h,
            report_ids=pre_scan_ids,
            sizes=(64,),
            retries=1,
            include_zero=args.include_zero,
        )
        pre_supported = parse_supported_report_ids(payload_of_report(pre_raw.get(0x10, [])))

        if pre_supported:
            print("\nSupported Report IDs from 0x10:")
            print("  " + ", ".join(f"0x{x:02X}" for x in pre_supported))
        else:
            print("\nไม่พบรายการ supported report IDs จาก 0x10 (จะใช้ช่วง RID ตามที่กำหนด)")

        request_ids = merge_report_ids(base_ids, pre_supported)
        if not request_ids:
            request_ids = base_ids

        print(f"\nเริ่ม deep scan ทั้งหมด {len(request_ids)} report IDs...")

        raw, meta, history = collect_feature_snapshots(
            h,
            report_ids=request_ids,
            passes=args.passes,
            delay_sec=args.scan_delay,
            sizes=DEFAULT_REPORT_SIZES,
            retries=args.retries,
            include_zero=args.include_zero,
        )

        dump_raw(raw)
        print_feature_coverage(meta, request_ids)

        ups = decode_feature_reports(raw)
        ups.update(infer_tentative_live_values(raw, ups))
        print_ups_data(ups)
        print_unknown_reports(raw, descriptor_profile=descriptor_profile)
        print_report_variants(history)

        print(f"\n{'=' * 68}")
        print("Input Reports (real-time events):")
        print("=" * 68)

        input_summary = read_input_reports(
            h,
            duration_sec=args.input_sec,
            report_size=args.input_size,
            timeout_ms=500,
            max_events=200,
        )

        if not args.no_monitor and args.monitor_count > 0:
            monitor_ids = merge_report_ids(sorted(raw.keys()), pre_supported, get_descriptor_all_ids(descriptor_profile))
            if not monitor_ids:
                monitor_ids = request_ids
            monitor_ups(
                h,
                report_ids=monitor_ids,
                interval=args.monitor_interval,
                count=args.monitor_count,
            )

        if args.json_path is not None:
            out_path = resolve_json_path(args.json_path)
            payload = build_export_payload(
                device_info=info,
                requested_ids=request_ids,
                raw=raw,
                meta=meta,
                history=history,
                decoded=ups,
                input_reports=input_summary,
                descriptor_profile=descriptor_profile,
            )
            save_json_report(out_path, payload)

    finally:
        h.close()
        print("\nปิด device เรียบร้อย")

    return 0


if __name__ == "__main__":
    sys.exit(main())
