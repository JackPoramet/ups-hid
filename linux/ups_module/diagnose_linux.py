#!/usr/bin/env python3
"""
Read-only Linux/Orange Pi diagnostic tool for ups_module.

This script deliberately does not install packages, reload udev, write files,
or send UPS control commands.  It checks the installation in layers so that a
failure in one layer does not hide the actual failure in another layer.

Usage::

    python3 diagnose_linux.py
    sudo python3 diagnose_linux.py
    python3 diagnose_linux.py --vid 0x06DA --pid 0xFFFF
    python3 diagnose_linux.py --json /tmp/ups-diagnostic.json
    python3 diagnose_linux.py --json-stdout
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import grp
except ImportError:  # pragma: no cover - unavailable on Windows
    grp = None

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None


SCRIPT_DIR = Path(__file__).resolve().parent
RULE_PATH = Path("/etc/udev/rules.d/99-ups-hid.rules")
DEFAULT_VID = 0x06DA
DEFAULT_PID = 0xFFFF
MAX_COMMAND_OUTPUT = 12000


def _text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _hid_path_arg(path: Any) -> bytes:
    """Normalize hidapi paths for bindings requiring a bytes argument."""
    if isinstance(path, bytes):
        return path
    if isinstance(path, bytearray):
        return bytes(path)
    if path is None:
        raise TypeError("HID device path is missing")
    return os.fsencode(str(path))


def _json_value(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return _text(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _run(
    command: Sequence[str],
    timeout: float = 8.0,
    cwd: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run a diagnostic command without raising or printing its output."""
    try:
        result = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or "")
        error = (result.stderr or "")
        combined = (output + ("\n" + error if error else "")).strip()
        return {
            "command": list(command),
            "returncode": result.returncode,
            "output": combined[-MAX_COMMAND_OUTPUT:],
            "timed_out": False,
        }
    except FileNotFoundError:
        return {
            "command": list(command),
            "returncode": None,
            "output": "command not found",
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": list(command),
            "returncode": None,
            "output": _text(exc.stdout or exc.stderr or "command timed out")[-MAX_COMMAND_OUTPUT:],
            "timed_out": True,
        }
    except Exception as exc:  # pragma: no cover - defensive for target systems
        return {
            "command": list(command),
            "returncode": None,
            "output": f"{type(exc).__name__}: {exc}",
            "timed_out": False,
        }


def _sha256(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _mode_info(path: str) -> Dict[str, Any]:
    try:
        info = os.stat(path)
    except (OSError, TypeError) as exc:
        return {"path": path, "error": f"{type(exc).__name__}: {exc}"}

    mode = stat.S_IMODE(info.st_mode)
    if pwd is None:
        owner = str(info.st_uid)
    else:
        try:
            owner = pwd.getpwuid(info.st_uid).pw_name
        except KeyError:
            owner = str(info.st_uid)
    if grp is None:
        group = str(info.st_gid)
    else:
        try:
            group = grp.getgrgid(info.st_gid).gr_name
        except KeyError:
            group = str(info.st_gid)
    return {
        "path": path,
        "mode": oct(mode),
        "owner": owner,
        "group": group,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "readable_by_process": os.access(path, os.R_OK),
        "writable_by_process": os.access(path, os.W_OK),
    }


class Diagnostic:
    def __init__(self, vid: int, pid: int, skip_kernel_log: bool = False) -> None:
        self.vid = vid
        self.pid = pid
        self.skip_kernel_log = skip_kernel_log
        self.results: List[Dict[str, Any]] = []
        self.device_entries: List[Dict[str, Any]] = []
        self.open_entries: List[Dict[str, Any]] = []

    def add(self, name: str, status: str, detail: str = "", **data: Any) -> None:
        self.results.append({
            "name": name,
            "status": status,
            "detail": detail,
            "data": _json_value(data),
        })

    def check_host(self) -> None:
        uname = _run(["uname", "-a"])
        self.add(
            "host",
            "OK" if platform.system() == "Linux" else "WARN",
            f"{platform.system()} {platform.machine()} Python {platform.python_version()}",
            platform=platform.platform(),
            architecture=platform.machine(),
            python=sys.executable,
            python_version=sys.version,
            euid=os.geteuid() if hasattr(os, "geteuid") else None,
            user=os.environ.get("USER") or os.environ.get("USERNAME"),
            uname=uname,
        )

    def check_source(self) -> None:
        files = {}
        for name in ("core.py", "client.py", "linux_setup.py", "install.sh", "meta.json"):
            path = SCRIPT_DIR / name
            files[name] = {
                "path": str(path),
                "exists": path.exists(),
                "sha256": _sha256(path),
            }

        core_path = SCRIPT_DIR / "core.py"
        setup_path = SCRIPT_DIR / "linux_setup.py"
        client_path = SCRIPT_DIR / "client.py"
        core_text = core_path.read_text(encoding="utf-8", errors="replace") if core_path.exists() else ""
        setup_text = setup_path.read_text(encoding="utf-8", errors="replace") if setup_path.exists() else ""
        client_text = client_path.read_text(encoding="utf-8", errors="replace") if client_path.exists() else ""

        missing = [name for name, info in files.items() if not info["exists"]]
        stale_markers = []
        if "_ordered_device_candidates" not in core_text:
            stale_markers.append("core.py lacks _ordered_device_candidates")
        if (
            "candidate_h.open_path(path)" not in core_text
            and "candidate_h.open_path(_hid_path_arg(path))" not in core_text
        ):
            stale_markers.append("core.py lacks multi-interface open loop")
        if 'h.open_path(target["path"])' in core_text:
            stale_markers.append("core.py still contains old direct target open")
        if 'TAG+="uaccess"' not in setup_text:
            stale_markers.append("linux_setup.py lacks current udev rule marker")
        if "UPS_HID_VERBOSE" not in client_text:
            stale_markers.append("client.py lacks verbose diagnostic support")

        if missing or stale_markers:
            status = "FAIL"
            detail = "Source tree is incomplete or older than the diagnostic-compatible version."
        else:
            status = "OK"
            detail = "Source files and multi-interface diagnostic markers are present."
        self.add("source", status, detail, files=files, stale_markers=stale_markers)

    def check_python_dependencies(self) -> None:
        modules = ["hid", "usb.core"]
        module_info = {}
        failures = []
        for module_name in modules:
            try:
                module = importlib.import_module(module_name)
                module_info[module_name] = {
                    "imported": True,
                    "file": getattr(module, "__file__", None),
                }
            except Exception as exc:
                failures.append(module_name)
                module_info[module_name] = {
                    "imported": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        packages = {}
        for package_name in ("hidapi", "pyusb"):
            try:
                packages[package_name] = importlib.metadata.version(package_name)
            except importlib.metadata.PackageNotFoundError:
                packages[package_name] = None
            except Exception as exc:
                packages[package_name] = f"error: {exc}"

        self.add(
            "python_dependencies",
            "FAIL" if failures else "OK",
            "Missing or unusable Python module(s)." if failures else "hidapi and pyusb imports succeeded.",
            modules=module_info,
            distributions=packages,
            sys_path=sys.path,
        )

    def check_system_dependencies(self) -> None:
        libraries = {}
        ldconfig = _run(["ldconfig", "-p"], timeout=10)
        for library in ("libhidapi-hidraw", "libusb-1.0"):
            matches = [
                line.strip()
                for line in ldconfig["output"].splitlines()
                if library in line
            ]
            libraries[library] = matches

        commands = {name: shutil.which(name) for name in ("udevadm", "fuser", "dmesg", "lsusb")}
        missing = [name for name, path in commands.items() if path is None and name == "udevadm"]
        self.add(
            "system_dependencies",
            "FAIL" if missing else "OK",
            "udevadm is unavailable." if missing else "Required diagnostic/system commands are available.",
            libraries=libraries,
            commands=commands,
            ldconfig=ldconfig,
        )

    def check_udev(self) -> None:
        rule_data: Dict[str, Any] = {"path": str(RULE_PATH), "exists": RULE_PATH.exists()}
        content = ""
        if RULE_PATH.exists():
            try:
                content = RULE_PATH.read_text(encoding="utf-8", errors="replace")
                rule_data["content"] = content
            except OSError as exc:
                rule_data["read_error"] = f"{type(exc).__name__}: {exc}"

        vid = f"{self.vid:04x}"
        pid = f"{self.pid:04x}"
        expected = [
            f'ATTRS{{idVendor}}=="{vid}"',
            f'ATTRS{{idProduct}}=="{pid}"',
            'SUBSYSTEM=="hidraw"',
        ]
        missing = [marker for marker in expected if marker not in content]
        rule_data["expected_markers"] = expected
        rule_data["missing_markers"] = missing

        if not RULE_PATH.exists() or missing:
            status = "FAIL"
            detail = "udev rule is missing or does not match the selected VID/PID."
        else:
            status = "OK"
            detail = "udev rule file contains the expected hidraw VID/PID match."
        self.add("udev_rule", status, detail, rule=rule_data)

    def _enumerate(self) -> Optional[Any]:
        try:
            hid = importlib.import_module("hid")
        except Exception as exc:
            self.add("hid_enumeration", "FAIL", f"Cannot import hid: {exc}")
            return None

        try:
            entries = hid.enumerate(self.vid, self.pid)
        except Exception as exc:
            self.add("hid_enumeration", "FAIL", f"hid.enumerate failed: {exc}")
            return None

        self.device_entries = [_json_value(entry) for entry in entries]
        if not entries:
            self.add(
                "hid_enumeration",
                "FAIL",
                f"No HID device found for VID=0x{self.vid:04X} PID=0x{self.pid:04X}.",
                devices=[],
            )
            return hid

        self.add(
            "hid_enumeration",
            "OK",
            f"Found {len(entries)} HID interface(s).",
            devices=self.device_entries,
        )
        return hid

    def _udev_properties(self, path: str) -> Dict[str, Any]:
        if shutil.which("udevadm") is None:
            return {"error": "udevadm not found"}
        result = _run(["udevadm", "info", "--query=property", "--name", path])
        properties = {}
        for line in result["output"].splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                properties[key] = value
        return {"command": result, "properties": properties}

    def _holders(self, path: str) -> Dict[str, Any]:
        if shutil.which("fuser") is None:
            return {"error": "fuser not found"}
        result = _run(["fuser", "-v", path])
        return result

    def check_nodes_and_open(self, hid: Any, probe: bool = True) -> None:
        if not self.device_entries:
            return

        opened = 0
        probed = 0
        for entry in self.device_entries:
            raw_path = entry.get("path")
            path = _text(raw_path)
            node: Dict[str, Any] = {
                "path": path,
                "usage_page": entry.get("usage_page"),
                "usage": entry.get("usage"),
                "interface_number": entry.get("interface_number"),
                "node": _mode_info(path),
                "udev": self._udev_properties(path),
                "holders": self._holders(path),
            }
            handle = None
            try:
                handle = hid.device()
                handle.open_path(_hid_path_arg(raw_path))
                opened += 1
                node["open"] = True
                node["open_error"] = None
                if probe:
                    reports = {}
                    for report_id in (0x01, 0x06):
                        try:
                            data = handle.get_feature_report(report_id, 64)
                            reports[f"0x{report_id:02X}"] = {
                                "ok": bool(data),
                                "length": len(data) if data else 0,
                                "non_zero_bytes": sum(1 for byte in data if byte) if data else 0,
                                "preview": list(data[:16]) if data else [],
                            }
                            if data and any(byte != 0 for byte in data):
                                probed += 1
                        except Exception as exc:
                            reports[f"0x{report_id:02X}"] = {
                                "ok": False,
                                "error": f"{type(exc).__name__}: {exc}",
                            }
                    node["feature_reports"] = reports
            except Exception as exc:
                node["open"] = False
                node["open_error"] = f"{type(exc).__name__}: {exc}"
            finally:
                if handle is not None:
                    try:
                        handle.close()
                    except Exception:
                        pass
            self.open_entries.append(node)

        if opened == 0:
            detail = "All enumerated HID interfaces failed to open."
            status = "FAIL"
        elif probe and probed == 0:
            detail = "At least one hidraw node opened, but no non-zero probe Feature Report was returned."
            status = "WARN"
        else:
            detail = f"Opened {opened}/{len(self.device_entries)} interface(s); non-zero probes: {probed}."
            status = "OK"
        self.add("hid_open_and_probe", status, detail, interfaces=self.open_entries)

    def check_kernel(self) -> None:
        if self.skip_kernel_log:
            self.add("kernel_log", "INFO", "Skipped by --skip-kernel-log.")
            return
        commands = []
        if shutil.which("dmesg"):
            commands.append(["dmesg", "--color=never", "--ctime", "--level=err,warn"])
        if shutil.which("journalctl"):
            commands.append(["journalctl", "-k", "-n", "80", "--no-pager"])

        outputs = []
        keywords = ("06da", "ffff", "hid", "usb", "hidraw", "permission", "denied", "error", "fail")
        for command in commands:
            result = _run(command, timeout=10)
            lines = [
                line for line in result["output"].splitlines()
                if any(keyword in line.lower() for keyword in keywords)
            ]
            outputs.append({"command": result, "relevant_lines": lines[-80:]})
        self.add(
            "kernel_log",
            "INFO",
            "Kernel diagnostics collected; inspect relevant_lines for USB/HID errors.",
            outputs=outputs,
        )

    def run(self, probe: bool = True) -> Dict[str, Any]:
        self.check_host()
        self.check_source()
        self.check_python_dependencies()
        self.check_system_dependencies()
        self.check_udev()
        hid = self._enumerate()
        if hid is not None:
            self.check_nodes_and_open(hid, probe=probe)
        self.check_kernel()

        failures = sum(1 for result in self.results if result["status"] == "FAIL")
        warnings = sum(1 for result in self.results if result["status"] == "WARN")
        return {
            "tool": "ups_module.diagnose_linux",
            "version": "1.0.0",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "target": {"vid": f"0x{self.vid:04X}", "pid": f"0x{self.pid:04X}"},
            "summary": {
                "status": "FAIL" if failures else ("WARN" if warnings else "OK"),
                "failures": failures,
                "warnings": warnings,
            },
            "results": self.results,
        }


def _print_report(report: Dict[str, Any]) -> None:
    print("=== ups_module Linux Diagnostic ===")
    target = report["target"]
    print(f"Target: VID={target['vid']} PID={target['pid']}")
    print(f"Overall: {report['summary']['status']}")
    print()
    for result in report["results"]:
        print(f"[{result['status']}] {result['name']}: {result['detail']}")
        data = result.get("data") or {}
        if result["name"] == "hid_open_and_probe":
            for interface in data.get("interfaces", []):
                node = interface.get("node", {})
                print(
                    f"  path={interface.get('path')} open={interface.get('open')} "
                    f"error={interface.get('open_error')} mode={node.get('mode')} "
                    f"owner={node.get('owner')} group={node.get('group')}"
                )
                if interface.get("feature_reports"):
                    print(f"  reports={interface['feature_reports']}")
        elif result["name"] == "source":
            stale = data.get("stale_markers", [])
            if stale:
                for marker in stale:
                    print(f"  - {marker}")
        elif result["name"] == "kernel_log":
            outputs = data.get("outputs", [])
            for output in outputs:
                for line in output.get("relevant_lines", [])[-20:]:
                    print(f"  {line}")
    print()
    print("JSON report: use --json /path/report.json or --json-stdout")


def _parse_int(value: str) -> int:
    return int(value, 0)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only diagnostic for Linux/Orange Pi UPS HID access",
    )
    parser.add_argument("--vid", type=_parse_int, default=DEFAULT_VID, help="USB VID, e.g. 0x06DA")
    parser.add_argument("--pid", type=_parse_int, default=DEFAULT_PID, help="USB PID, e.g. 0xFFFF")
    parser.add_argument("--json", metavar="PATH", help="Write the complete report to PATH")
    parser.add_argument("--json-stdout", action="store_true", help="Print the complete report as JSON")
    parser.add_argument("--skip-kernel-log", action="store_true", help="Skip dmesg/journalctl checks")
    parser.add_argument("--no-probe", action="store_true", help="Open nodes but do not read Feature Reports")
    args = parser.parse_args(argv)

    if args.json and args.json_stdout:
        parser.error("use either --json PATH or --json-stdout, not both")

    diagnostic = Diagnostic(args.vid, args.pid, skip_kernel_log=args.skip_kernel_log)
    report = diagnostic.run(probe=not args.no_probe)

    if args.json:
        output_path = Path(args.json).expanduser().resolve()
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Diagnostic report written to: {output_path}")
    elif args.json_stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    return 1 if report["summary"]["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())