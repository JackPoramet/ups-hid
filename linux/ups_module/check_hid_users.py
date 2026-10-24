#!/usr/bin/env python3
"""Read-only helper to find processes using a Linux USB HID UPS.

It maps the HID paths returned by hidapi to /dev/hidraw nodes, reports
permissions and process holders, and optionally tests opening each hidapi path.
It never kills processes, changes permissions, reloads udev, or writes UPS data.
"""

from __future__ import annotations

import argparse
import glob
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    import pwd
except ImportError:  # pragma: no cover - Windows only
    pwd = None


DEFAULT_VID = 0x06DA
DEFAULT_PID = 0xFFFF
MAX_OUTPUT = 10000


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _hid_path_arg(path: Any) -> bytes:
    """ARM hidapi builds may require bytes even when enumerate returns str."""
    if isinstance(path, bytes):
        return path
    if isinstance(path, bytearray):
        return bytes(path)
    if path is None:
        raise TypeError("HID device path is missing")
    return os.fsencode(str(path))


def _run(command: Sequence[str], timeout: float = 8.0) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, errors="replace",
            timeout=timeout, check=False,
        )
        output = result.stdout or ""
        if result.stderr:
            output += ("\n" if output else "") + result.stderr
        return {
            "command": list(command),
            "returncode": result.returncode,
            "output": output.strip()[-MAX_OUTPUT:],
        }
    except FileNotFoundError:
        return {"command": list(command), "returncode": None, "output": "command not found"}
    except Exception as exc:
        return {"command": list(command), "returncode": None, "output": f"{type(exc).__name__}: {exc}"}


def _properties(text: str) -> Dict[str, str]:
    result = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def _udev(node: str) -> Dict[str, Any]:
    if not shutil.which("udevadm"):
        return {"error": "udevadm not found", "properties": {}}
    result = _run(["udevadm", "info", "--query=property", "--name", node])
    return {"command": result, "properties": _properties(result["output"])}


def _node_stat(node: str) -> Dict[str, Any]:
    try:
        info = os.stat(node)
    except OSError as exc:
        return {"path": node, "exists": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        owner = pwd.getpwuid(info.st_uid).pw_name if pwd else str(info.st_uid)
    except KeyError:
        owner = str(info.st_uid)
    return {
        "path": node,
        "exists": True,
        "mode": oct(stat.S_IMODE(info.st_mode)),
        "owner": owner,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "readable": os.access(node, os.R_OK),
        "writable": os.access(node, os.W_OK),
    }


def _process_info(pid: int) -> Dict[str, Any]:
    proc = Path("/proc") / str(pid)
    result: Dict[str, Any] = {"pid": pid}
    try:
        status = _properties((proc / "status").read_text(encoding="utf-8", errors="replace"))
        uid = int(status.get("Uid", "0").split()[0])
        result["uid"] = uid
        try:
            result["user"] = pwd.getpwuid(uid).pw_name if pwd else str(uid)
        except KeyError:
            result["user"] = str(uid)
    except (OSError, ValueError):
        pass
    try:
        command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").strip()
        result["cmdline"] = command.decode("utf-8", errors="replace") or "[kernel/thread]"
    except OSError:
        result["cmdline"] = "[unreadable]"
    try:
        result["comm"] = (proc / "comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    return result


def _proc_holders(node: str) -> List[Dict[str, Any]]:
    """Find matching /proc file descriptors without requiring lsof."""
    if not Path("/proc").exists():
        return []
    target = os.path.realpath(node)
    holders = []
    for proc in Path("/proc").glob("[0-9]*"):
        if not proc.name.isdigit():
            continue
        try:
            fds = list((proc / "fd").iterdir())
        except OSError:
            continue
        matched = []
        for fd in fds:
            try:
                if os.path.realpath(fd) == target:
                    matched.append(fd.name)
            except OSError:
                pass
        if matched:
            item = _process_info(int(proc.name))
            item["fds"] = matched
            holders.append(item)
    return holders


def _pids(text: str) -> List[int]:
    values = set()
    for value in re.findall(r"\b([1-9][0-9]{0,7})\b", text):
        pid = int(value)
        if Path(f"/proc/{pid}").exists():
            values.add(pid)
    return sorted(values)


def _holders(node: str) -> Dict[str, Any]:
    fuser = _run(["fuser", "-v", node]) if shutil.which("fuser") else None
    lsof = _run(["lsof", "-nP", node]) if shutil.which("lsof") else None
    proc_matches = _proc_holders(node)
    pids = set()
    for result in (fuser, lsof):
        if result:
            pids.update(_pids(result["output"]))
    pids.update(item["pid"] for item in proc_matches)
    return {
        "pids": sorted(pids),
        "processes": [_process_info(pid) for pid in sorted(pids)],
        "proc_fd_matches": proc_matches,
        "fuser": fuser,
        "lsof": lsof,
    }


def _target_udev(props: Dict[str, str], vid: int, pid: int) -> bool:
    expected_vid = f"{vid:04x}"
    expected_pid = f"{pid:04x}"
    actual_vid = props.get("ID_VENDOR_ID", "").lower().removeprefix("0x")
    actual_pid = props.get("ID_MODEL_ID", "").lower().removeprefix("0x")
    product = props.get("PRODUCT", "").lower()
    return (actual_vid == expected_vid and actual_pid == expected_pid) or (
        expected_vid in product and expected_pid in product
    )


def find_hidraw_nodes(vid: int, pid: int) -> List[Dict[str, Any]]:
    nodes = []
    for node in sorted(glob.glob("/dev/hidraw*")):
        udev = _udev(node)
        props = udev.get("properties", {})
        nodes.append({
            "path": node,
            "matched_vid_pid": _target_udev(props, vid, pid),
            "stat": _node_stat(node),
            "udev": udev,
            "holders": _holders(node),
        })
    return nodes


def enumerate_hid(vid: int, pid: int) -> Dict[str, Any]:
    try:
        hid = importlib.import_module("hid")
        entries = hid.enumerate(vid, pid)
        return {"hid": hid, "module": getattr(hid, "__file__", None), "entries": entries}
    except Exception as exc:
        return {"hid": None, "module": None, "entries": [], "error": f"{type(exc).__name__}: {exc}"}


def test_open(hid: Any, entries: Iterable[Dict[str, Any]], no_open: bool) -> List[Dict[str, Any]]:
    results = []
    for entry in entries:
        raw_path = entry.get("path")
        item: Dict[str, Any] = {"path": _text(raw_path), "path_type": type(raw_path).__name__}
        if no_open:
            item["skipped"] = True
            results.append(item)
            continue
        handle = None
        try:
            handle = hid.device()
            handle.open_path(_hid_path_arg(raw_path))
            item["opened"] = True
            item["reports"] = {}
            for rid in (0x01, 0x06):
                try:
                    data = handle.get_feature_report(rid, 64)
                    item["reports"][f"0x{rid:02X}"] = {
                        "ok": bool(data),
                        "length": len(data) if data else 0,
                        "non_zero_bytes": sum(1 for byte in data if byte) if data else 0,
                        "preview": list(data[:16]) if data else [],
                    }
                except Exception as exc:
                    item["reports"][f"0x{rid:02X}"] = {
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
        except Exception as exc:
            item["opened"] = False
            item["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
        results.append(item)
    return results


def _json_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return _text(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def build_report(vid: int, pid: int, no_open: bool = False) -> Dict[str, Any]:
    enumeration = enumerate_hid(vid, pid)
    entries = enumeration.get("entries", [])
    hid = enumeration.get("hid")
    nodes = find_hidraw_nodes(vid, pid)
    report = {
        "tool": "ups_module.check_hid_users",
        "target": {"vid": f"0x{vid:04X}", "pid": f"0x{pid:04X}"},
        "uid": os.getuid() if hasattr(os, "getuid") else None,
        "euid": os.geteuid() if hasattr(os, "geteuid") else None,
        "hid_module": enumeration.get("module"),
        "hid_error": enumeration.get("error"),
        "hid_entries": _json_value(entries),
        "hidraw_nodes": nodes,
        "open_tests": test_open(hid, entries, no_open) if hid else [],
        "notes": [
            "No process is stopped or modified by this tool.",
            "An hidapi path such as 6-1:1.0 is a topology path, not necessarily /dev/hidrawN.",
            "Use the hidraw_nodes.proc_fd_matches/processes fields to identify holders.",
        ],
    }
    holders = [
        process
        for node in nodes
        for process in node.get("holders", {}).get("processes", [])
    ]
    report["summary"] = {
        "hid_interfaces": len(entries),
        "hidraw_nodes": len(nodes),
        "matching_hidraw_nodes": sum(1 for node in nodes if node["matched_vid_pid"]),
        "holder_pids": sorted({process["pid"] for process in holders}),
        "holder_processes": holders,
        "open_failures": [item for item in report["open_tests"] if item.get("opened") is False],
    }
    return report


def _print_report(report: Dict[str, Any]) -> None:
    target = report["target"]
    print("=== USB HID Users Diagnostic ===")
    print(f"Target: VID={target['vid']} PID={target['pid']}")
    print(f"hidapi module: {report.get('hid_module')}")
    if report.get("hid_error"):
        print(f"hidapi error: {report['hid_error']}")
    print(f"hid interfaces: {len(report['hid_entries'])}")
    print()

    for entry in report["hid_entries"]:
        print(f"[HID] path={entry.get('path')} type={type(entry.get('path')).__name__} "
              f"interface={entry.get('interface_number')} usage_page={entry.get('usage_page')}")

    if not report["hidraw_nodes"]:
        print("[WARN] No /dev/hidraw* nodes found.")
    for node in report["hidraw_nodes"]:
        info = node["stat"]
        holders = node["holders"]
        print()
        print(f"[NODE] {node['path']} matched_vid_pid={node['matched_vid_pid']}")
        print(f"       exists={info.get('exists')} mode={info.get('mode')} "
              f"owner={info.get('owner')} uid={info.get('uid')} gid={info.get('gid')} "
              f"readable={info.get('readable')}")
        if holders["processes"]:
            for process in holders["processes"]:
                print(f"[USING] {node['path']} pid={process['pid']} "
                      f"user={process.get('user')} comm={process.get('comm')} "
                      f"cmdline={process.get('cmdline')}")
        else:
            print(f"[FREE] {node['path']} no process file descriptor found")

    print()
    for item in report["open_tests"]:
        if item.get("opened"):
            print(f"[OPEN OK] {item['path']} reports={item.get('reports', {})}")
        elif item.get("opened") is False:
            print(f"[OPEN NG] {item['path']} error={item.get('error')}")

    print()
    if report["summary"]["holder_pids"]:
        print("Processes using HID nodes were found. Stop only the relevant process, then retry.")
    else:
        print("No process currently holding a matching hidraw node was found.")
        print("If open still fails, investigate path type, permissions, kernel driver, or hidapi backend.")


def _parse_int(value: str) -> int:
    return int(value, 0)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find processes using a Linux USB HID UPS")
    parser.add_argument("--vid", type=_parse_int, default=DEFAULT_VID)
    parser.add_argument("--pid", type=_parse_int, default=DEFAULT_PID)
    parser.add_argument("--json", metavar="PATH", help="Write JSON report to PATH")
    parser.add_argument("--json-stdout", action="store_true", help="Print JSON report")
    parser.add_argument("--no-open", action="store_true", help="Do not call hid.open_path()")
    args = parser.parse_args(argv)
    if args.json and args.json_stdout:
        parser.error("use either --json PATH or --json-stdout")

    report = build_report(args.vid, args.pid, no_open=args.no_open)
    if args.json:
        path = Path(args.json).expanduser().resolve()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report written to: {path}")
    elif args.json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())