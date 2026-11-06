#!/usr/bin/env python3
import time
import os
import sys
import logging
import datetime
import tempfile
from pathlib import Path

# Path to the deployed ups_module directory
INSTALL_DIR = "/opt/enerex-ups"
if INSTALL_DIR not in sys.path:
    sys.path.insert(0, INSTALL_DIR)

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
if LOCAL_DIR not in sys.path:
    sys.path.insert(0, LOCAL_DIR)

try:
    from ups_module.client import UPSClient
except ImportError:
    from client import UPSClient
from ups_module.hardware_session import HardwareSession
from ups_module.command_broker import CommandBroker, COMMAND_METHODS

# File that NUT's dummy-ups will read from
DUMMY_FILE = "/etc/nut/myups.dev"

# Phoenixtec Innova VID/PID
PHOENIXTEC_VID = 0x06DA
PHOENIXTEC_PID = 0xFFFF

# Polling interval
POLL_INTERVAL = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Global flag, single-instance lock, and NUT driver state
_running = True
_lock_fd = None
_driver_running = None
_driver_checked_at = 0.0
DRIVER_RECHECK_INTERVAL = 5.0


def set_nut_driver_state(running: bool) -> bool:
    """Reconcile NUT with hardware state; never cache a failed action."""
    global _driver_running, _driver_checked_at
    now = time.monotonic()
    if _driver_running == running and now - _driver_checked_at < DRIVER_RECHECK_INTERVAL:
        return True
    import subprocess
    def active():
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "nut-driver.service"],
            timeout=5, check=False, capture_output=True,
        )
        if result.returncode not in (0, 3):
            raise RuntimeError(f"systemctl is-active exited {result.returncode}")
        return result.returncode == 0
    try:
        if active() != running:
            action = "start" if running else "stop"
            logging.info("%s nut-driver.service...", action.capitalize())
            result = subprocess.run(["systemctl", action, "nut-driver.service"],
                                    timeout=5, check=False, capture_output=True)
            if result.returncode != 0:
                raise RuntimeError(f"systemctl {action} exited {result.returncode}")
            if active() != running:
                raise RuntimeError("nut-driver did not reach requested state")
        _driver_running = running
        _driver_checked_at = time.monotonic()
        return True
    except Exception as exc:
        _driver_running = None
        logging.warning("Unable to reconcile nut-driver: %s", exc)
        return False


def clear_dummy_file():
    """Clear myups.dev so no stale UPS hardware metrics remain."""
    try:
        if os.path.exists(DUMMY_FILE):
            os.remove(DUMMY_FILE)
    except Exception as e:
        logging.debug(f"Failed to remove {DUMMY_FILE}: {e}")


def _nut_gid():
    import grp
    return grp.getgrnam("nut").gr_gid


def write_dummy_file(data: dict) -> None:
    """Publish only a complete, root-owned snapshot readable by NUT."""
    gid = _nut_gid()
    fd, temp_path = tempfile.mkstemp(prefix=".enerex-", suffix=".tmp", dir=os.path.dirname(DUMMY_FILE))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for key, value in sorted(data.items()):
                stream.write(f"{key}: {value}\n")
        os.chown(temp_path, 0, gid)
        os.chmod(temp_path, 0o640)
        os.replace(temp_path, DUMMY_FILE)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def acquire_single_instance_lock():
    """Guarantee that only one instance of enerex_ups_bridge runs on the system."""
    global _lock_fd
    lock_path = "/run/enerex_ups_bridge.lock" if os.path.exists("/run") else "/tmp/enerex_ups_bridge.lock"
    try:
        import fcntl
        _lock_fd = open(lock_path, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(f"{os.getpid()}\n")
        _lock_fd.flush()
    except (ImportError, AttributeError):
        pass  # fcntl not available on Windows
    except (BlockingIOError, IOError):
        logging.warning("Another instance of enerex_ups_bridge is already running. Exiting cleanly.")
        sys.exit(0)


def handle_shutdown_signal(signum, frame):
    global _running
    logging.info(f"Received termination signal ({signum}). Shutting down bridge gracefully...")
    _running = False


import signal
try:
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)
except (ValueError, AttributeError):
    pass

# Database connection configuration for MariaDB command polling
DB_CONFIG = {
    "host": "localhost",
    "user": "ups_user",
    "password": "1q2w3e4r",
    "database": "ups",
    "connect_timeout": 2,
}

_pending_commands = []


def handle_battery_test_signal(signum, frame):
    global _pending_commands
    logging.info(f"Received signal ({signum}) triggering UPS battery test.")
    if hasattr(signal, "SIGUSR1") and signum == signal.SIGUSR1:
        _pending_commands.append("cmd_test_battery_quick")
    elif hasattr(signal, "SIGUSR2") and signum == signal.SIGUSR2:
        _pending_commands.append("cmd_test_battery_stop")


try:
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, handle_battery_test_signal)
    if hasattr(signal, "SIGUSR2"):
        signal.signal(signal.SIGUSR2, handle_battery_test_signal)
except (ValueError, AttributeError):
    pass


CMD_FILES = ["/run/enerex_ups_cmd", "/tmp/enerex_ups_cmd"]


WEB_COMMAND_OWNER = "/etc/erx/.service/ups-command.py"


def _read_database_commands():
    if Path(WEB_COMMAND_OWNER).is_file():
        return []
    commands = []
    conn = cursor = None
    try:
        try:
            import pymysql
            conn = pymysql.connect(**DB_CONFIG)
        except ImportError:
            try:
                import mysql.connector
                conn = mysql.connector.connect(**DB_CONFIG)
            except ImportError:
                try:
                    import MySQLdb
                    conn = MySQLdb.connect(**DB_CONFIG)
                except ImportError:
                    return []
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, cmd_name FROM system_command WHERE run_python = 1 "
            "AND (cmd_name LIKE '%test%' OR cmd_name LIKE '%quick%' OR cmd_name LIKE '%deep%' OR cmd_name LIKE '%stop%')"
        )
        for row in cursor.fetchall():
            commands.append(row[1])
            cursor.execute("UPDATE system_command SET run_python = 0 WHERE id = %s", (row[0],))
        conn.commit()
        return commands
    except Exception as exc:
        logging.debug("DB command check encountered non-fatal error: %s", exc)
        return []
    finally:
        for resource in (cursor, conn):
            if resource is not None:
                try:
                    resource.close()
                except Exception as exc:
                    logging.debug("Non-fatal DB close error: %s", exc)


def check_and_execute_commands(client):
    """
    Poll and execute pending commands from:
    1. Signals (SIGUSR1, SIGUSR2)
    2. File IPC queue (/run/enerex_ups_cmd or /tmp/enerex_ups_cmd)
    3. MariaDB system_command table
    """
    global _pending_commands
    cmds = []

    # 1. Collect pending signal commands
    while _pending_commands:
        cmds.append(_pending_commands.pop(0))

    # 2. Check File IPC queue (allows any user / web / CLI to trigger tests)
    for cmd_file in CMD_FILES:
        if os.path.exists(cmd_file):
            try:
                with open(cmd_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    cmds.append(content)
                # Truncate file immediately
                with open(cmd_file, "w", encoding="utf-8") as f:
                    pass
            except Exception as e:
                logging.debug(f"Error reading command file {cmd_file}: {e}")

    # The original web worker owns its DB queue and run_msg contract.
    cmds.extend(_read_database_commands())

    # 4. Execute detected commands via client
    for raw_cmd in cmds:
        cmd_clean = raw_cmd.strip().lower()
        logging.info(f"Executing UPS command: '{raw_cmd}' (normalized: '{cmd_clean}')")
        success, msg = False, ""
        try:
            if any(k in cmd_clean for k in ("stop", "abort", "cancel")):
                if hasattr(client, "test_battery_stop"):
                    success, msg = client.test_battery_stop()
                else:
                    success, msg = client.abort_self_test()
            elif any(k in cmd_clean for k in ("deep", "start_test", "dtest")):
                if hasattr(client, "test_battery_deep"):
                    success, msg = client.test_battery_deep()
                else:
                    success, msg = client.run_self_test()
            elif any(k in cmd_clean for k in ("quick", "qtest", "start", "test", "cal")):
                if hasattr(client, "test_battery_quick"):
                    success, msg = client.test_battery_quick()
                else:
                    success, msg = client.run_self_test()
            else:
                logging.warning(f"Unrecognized UPS command: '{raw_cmd}'")
                continue

            logging.info(f"Command '{raw_cmd}' execution result: success={success}, msg='{msg}'")
        except Exception as e:
            logging.error(f"Error executing command '{raw_cmd}': {e}")


def execute_nut_command(client, command):
    """Exact native command routing; preserve the real transport result."""
    if command not in COMMAND_METHODS:
        raise ValueError("Unsupported native NUT command")
    try:
        age = time.time() - os.stat(DUMMY_FILE).st_mtime
    except OSError:
        age = float('inf')
    profile = getattr(client, 'profile', None)
    if not -1 <= age < 5 or not client.is_connected or not profile or not profile.features.get('has_battery_test', False):
        return False, 'UPS telemetry is stale or command capability unavailable; not executed'
    result = getattr(client, COMMAND_METHODS[command])()
    logging.info("NUT command %s transport result: %s", command, result)
    return result


def enrich_nut_variables(data: dict, info: dict, profile=None) -> dict:
    """
    Enriches the live UPS data dictionary with missing standard NUT variables
    (conforming to usbhid-ups / MGE HID 1.40 / Power Device Class specification)
    while strictly preserving all existing live readings.
    """
    # 1. Device Identification & Serial
    mfr = info.get("manufacturer") or info.get("manufacturer_string") or data.get("device.mfr") or data.get("ups.mfr") or (profile.manufacturer if profile else "Enerex")
    prod = info.get("model") or info.get("product_string") or data.get("device.model") or data.get("ups.model") or (profile.model if profile else "UPS")
    serial = info.get("serial") or info.get("serial_number") or data.get("device.serial") or data.get("ups.serial") or "0000000000"

    data["device.mfr"] = mfr
    data["device.model"] = prod
    data["device.serial"] = serial
    data["device.type"] = "ups"
    data["ups.mfr"] = mfr
    data["ups.model"] = prod
    data["ups.serial"] = serial
    if "ups.type" not in data:
        if profile and ("mec" in profile.id.lower() or "offline" in profile.id.lower()):
            data["ups.type"] = "offline"
        else:
            data["ups.type"] = "online"

    # 2. Driver Metadata (MGE HID / usbhid-ups compatible)
    data.setdefault("driver.name", "usbhid-ups")
    data.setdefault("driver.version", "2.7.4")
    data.setdefault("driver.version.data", "MGE HID 1.40")
    data.setdefault("driver.version.internal", "0.41")
    data.setdefault("driver.parameter.pollfreq", "30")
    data.setdefault("driver.parameter.pollinterval", "15")
    data.setdefault("driver.parameter.port", "auto")
    data.setdefault("driver.parameter.synchronous", "no")

    # 3. Battery Subsystem
    data.setdefault("battery.capacity", "0.00")
    data.setdefault("battery.charge.restart", 0)
    data.setdefault("battery.protection", "yes")
    data.setdefault("battery.type", "PbAc")
    data.setdefault("battery.runtime.low", 180)

    # Dynamically determine battery charger status if not already set
    if "battery.charger.status" not in data:
        status = str(data.get("ups.status", "")).upper()
        try:
            charge = float(data.get("battery.charge", 100) or 100)
        except (ValueError, TypeError):
            charge = 100.0

        if "OB" in status or "DISCHRG" in status:
            data["battery.charger.status"] = "discharging"
        elif "CHRG" in status or charge < 90:
            data["battery.charger.status"] = "charging"
        elif "OL" in status and charge >= 90:
            data["battery.charger.status"] = "floating"
        else:
            data["battery.charger.status"] = "resting"

    # 4. Input & Output Power Nominals & Smart Fallbacks
    data.setdefault("input.voltage.nominal", 220)
    data.setdefault("input.frequency.nominal", 50)
    data.setdefault("output.voltage.nominal", 220)
    data.setdefault("output.frequency.nominal", 50)

    # Sanitize battery.charge.low: must be a realistic percentage threshold (< 100%, default 20)
    b_low = data.get("battery.charge.low")
    try:
        b_low_val = float(b_low) if b_low is not None else 20.0
    except (ValueError, TypeError):
        b_low_val = 20.0
    if b_low_val >= 100.0 or b_low_val <= 0.0:
        b_low_val = 20.0
    data["battery.charge.low"] = int(b_low_val)

    # 4.1 State-driven synchronization to prevent stale variables
    status_str = str(data.get("ups.status", "")).upper()
    vin = float(data.get("input.voltage", 0.0) or 0.0)
    vout_raw = data.get("output.voltage")
    vout = float(vout_raw) if vout_raw is not None else None

    # If output voltage is 0/low (< 50V) and not in battery operation, the UPS is OFF
    if vout is not None and vout < 50.0 and "OB" not in status_str and "DISCHRG" not in status_str:
        status_str = "OFF"
        data["ups.status"] = "OFF"

    is_on_batt = "OB" in status_str or "DISCHRG" in status_str or (vin < 50.0 and "OL" not in status_str and status_str != "OFF")
    is_off = "OFF" in status_str or (vout is not None and vout < 50.0 and not is_on_batt)

    b_test = str(data.get("battery.test.status", "")).lower()
    is_testing = b_test in ("running", "in progress", "cal") or "CAL" in status_str

    if is_off:
        data["ups.status"] = "OFF CAL" if is_testing else "OFF"
        data["output.voltage"] = 0.0
        data["output.frequency"] = 0.0
        data["output.current"] = 0.0
        data["output.power"] = 0
        data["output.power.apparent"] = 0
        data["ups.load"] = 0
        data["outlet.1.status"] = "off"
        data["battery.charger.status"] = "resting"
    elif is_on_batt:
        data["input.voltage"] = 0.0
        data["input.frequency"] = 0.0
        data["battery.charger.status"] = "discharging"
        data["outlet.1.status"] = "on"

        # Sanitize status: If AC is absent, Bypass cannot exist; enforce OB
        parts = [p for p in status_str.split() if p != "BYPASS"]
        if "OB" not in parts:
            parts.insert(0, "OB")

        # Standard NUT fallback: ensure LB is appended when battery is depleted/low on battery power
        b_chg = data.get("battery.charge")
        charge = float(b_chg) if b_chg is not None else 100.0
        b_low = data.get("battery.charge.low")
        charge_low = float(b_low) if b_low is not None else 20.0
        if charge_low >= 100.0 or charge_low <= 0.0:
            charge_low = 20.0
        data["battery.charge.low"] = int(charge_low)
        b_rt = data.get("battery.runtime")
        runtime = float(b_rt) if b_rt is not None else 9999.0
        b_rt_low = data.get("battery.runtime.low")
        runtime_low = float(b_rt_low) if b_rt_low is not None else 180.0

        if charge <= charge_low or runtime <= runtime_low or charge <= 0:
            if "LB" not in parts:
                parts.append("LB")
        data["ups.status"] = " ".join(parts)
    else:
        data.setdefault("outlet.1.status", "on")
        # Smart fallback for input.frequency if hardware does not provide it (e.g. Offline 2000D)
        if "input.frequency" not in data or float(data.get("input.frequency", 0.0) or 0.0) <= 0.0:
            if vin >= 50.0:
                data["input.frequency"] = float(data.get("input.frequency.nominal", 50.0))

    if not is_off:
        if "output.frequency" not in data or float(data.get("output.frequency", 0.0) or 0.0) <= 0.0:
            in_freq = float(data.get("input.frequency", 0.0) or 0.0)
            data["output.frequency"] = in_freq if in_freq > 0.0 else float(data.get("output.frequency.nominal", 50.0))

    # If hardware lacks internal temp sensor or returns <= 0.0 / invalid (e.g. Offline 2000D / MEC0003),
    # omit ups.temperature so that database records NULL and Web Dashboard / Log displays N/A.
    if "ups.temperature" in data:
        try:
            val = float(data.get("ups.temperature", 0.0) or 0.0)
            if val <= 0.0:
                data.pop("ups.temperature", None)
        except (ValueError, TypeError):
            data.pop("ups.temperature", None)

    # Use measured ratings first, then only a positively identified model's metadata.
    if profile is None:
        from ups_module.device_registry import DeviceRegistry
        registry = DeviceRegistry()
        profile = registry.get_by_id(info.get("profile_id", ""))
        if profile is None:
            profile = registry.match_device(0x06DA, 0xFFFF, prod)
    if profile:
        if profile.nominal_va is not None:
            data.setdefault("ups.power.nominal", profile.nominal_va)
        if profile.nominal_watts is not None:
            data.setdefault("ups.realpower.nominal", profile.nominal_watts)
    if "ups.power.nominal" in data:
        data["ups.apparent.power.nominal"] = data["ups.power.nominal"]

    # Estimate missing meters only when the load and the corresponding rating exist.
    if not is_off and "ups.load" in data:
        load_pct = float(data["ups.load"])
        for meter, rating in (("output.power.apparent", "ups.power.nominal"),
                              ("output.power", "ups.realpower.nominal")):
            if data.get(meter) is None and data.get(rating) is not None:
                data[meter] = int(round(load_pct / 100.0 * float(data[rating])))
        vout = data.get("output.voltage")
        if data.get("output.current") is None and data.get("output.power.apparent") is not None and vout is not None and float(vout) > 50:
            data["output.current"] = round(float(data["output.power.apparent"]) / float(vout), 1)

    # 6. System Timers, Control & Dates
    data.setdefault("ups.delay.shutdown", 20)
    data.setdefault("ups.delay.start", 30)
    data.setdefault("ups.timer.shutdown", -1)
    data.setdefault("ups.timer.start", -1)
    data.setdefault("battery.test.status", "unknown")
    data.setdefault("ups.beeper.status", "enabled")
    data.setdefault("ups.date", datetime.datetime.now().strftime("%Y/%m/%d"))

    # Keep legacy capability flags; the native adapter also registers real ADDCMDs.
    for command in COMMAND_METHODS:
        key = "cmd." + command
        if profile and profile.features.get("has_battery_test", False):
            data[key] = 1
        else:
            data.pop(key, None)

    # Synchronize CAL status and NUT test result with active battery test state
    b_test = str(data.get("battery.test.status", "")).lower()
    if b_test in ("running", "in progress", "cal"):
        cur_status = str(data.get("ups.status", ""))
        if "CAL" not in cur_status.split():
            parts = cur_status.split() if cur_status else ["OL"]
            parts.append("CAL")
            data["ups.status"] = " ".join(parts)
        data["ups.test.result"] = "In progress"
    elif b_test in ("abort", "aborted"):
        data["ups.test.result"] = "Aborted"
    elif b_test in ("failed", "error"):
        data["ups.test.result"] = "Done and error"
    elif b_test == "passed":
        data.setdefault("ups.test.result", "Done and passed")
    else:
        data.setdefault("ups.test.result", "Unknown")

    return data


def is_enerex_driver_active() -> bool:
    """Check whether /etc/nut/ups.conf is configured to use the enerex driver."""
    conf_path = Path("/etc/nut/ups.conf")
    if not conf_path.exists():
        return True
    try:
        for line in conf_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.split('#', 1)[0]
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("driver"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    drv = parts[1].strip().lower()
                    return drv in ("enerex", "dummy-ups")
    except Exception as exc:
        logging.debug(f"Error checking driver in {conf_path}: {exc}")
    return True


def main():
    acquire_single_instance_lock()
    broker = CommandBroker()
    try:
        broker.start()
        _run_bridge(broker)
    finally:
        broker.close()


def _run_bridge(broker):
    logging.info("Starting Enerex UPS Bridge daemon...")

    client = None
    while _running:
        if not is_enerex_driver_active():
            logging.info("Native driver configured in /etc/nut/ups.conf (e.g. usbhid-ups). Bridge in standby...")
            time.sleep(5)
            continue

        try:
            logging.info("Scanning for Enerex/Phoenixtec/Megatec UPS...")
            if client is None:
                client = HardwareSession(should_run=lambda: _running)
            client.connect()

            info = client.device_info
            profile = getattr(client, "profile", None)
            mfr = info.get("manufacturer") or info.get("manufacturer_string") or (profile.manufacturer if profile else "Enerex")
            prod = info.get("model") or info.get("product_string") or (profile.model if profile else "UPS")
            logging.info(f"Connected to UPS: Manufacturer='{mfr}', Product='{prod}' (Protocol: {getattr(profile, 'protocol', 'unknown')})")

            # 1. Read initial live UPS variables and write state file BEFORE starting nut-driver
            initial_data = client.get_vars()
            initial_data = enrich_nut_variables(initial_data, info, profile)
            write_dummy_file(initial_data)
            broker.set_connected(bool(profile and profile.features.get("has_battery_test", False)))

            # 2. Ensure NUT server is active and start nut-driver now that hardware is connected and state file is populated
            import subprocess
            try:
                subprocess.run(["systemctl", "start", "nut-server.service"], timeout=5, check=False)
            except Exception as exc:
                logging.warning("Failed to start nut-server service: %s", exc)
            set_nut_driver_state(True)

            # Polling loop for the connected UPS
            while _running:
                try:
                    broker.execute_pending(lambda command: execute_nut_command(client, command))
                    # 0. Check and execute pending commands (Battery Test from DB, Signals, or File IPC)
                    check_and_execute_commands(client)

                    # 1. Read live UPS variables (existing logic preserved 100%)
                    data = client.get_vars()

                    # 2. Enrich with missing usbhid-ups compatible variables
                    data = enrich_nut_variables(data, info, profile)

                    write_dummy_file(data)
                    set_nut_driver_state(True)

                except Exception as e:
                    if not _running:
                        break
                    logging.error(f"Error reading UPS data (Device disconnected?): {e}")
                    # Stop nut-driver and remove state file so NUT immediately reports 'Driver not connected'
                    # and purges all stale hardware metrics (device.mfr, battery.charge, voltages, etc.)
                    set_nut_driver_state(False)
                    clear_dummy_file()
                    break

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            if not _running:
                break
            logging.warning(f"No UPS found or connect failed: {e}. Retrying in 5 seconds...")
            # When disconnected or no UPS is found, stop nut-driver and remove stale definition file
            set_nut_driver_state(False)
            clear_dummy_file()
            time.sleep(5)
        finally:
            broker.set_connected(False)
            if client:
                try:
                    client.disconnect()
                except Exception as exc:
                    logging.error("USB cleanup incomplete; retaining owner before retry: %s", exc)
                else:
                    client = None
    logging.info("Enerex UPS Bridge exited cleanly.")


if __name__ == "__main__":
    main()
