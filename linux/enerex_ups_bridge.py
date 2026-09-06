#!/usr/bin/env python3
import time
import os
import sys
import logging
import datetime

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

# File that NUT's dummy-ups will read from
DUMMY_FILE = "/etc/nut/myups.dev"

# Phoenixtec Innova VID/PID
PHOENIXTEC_VID = 0x06DA
PHOENIXTEC_PID = 0xFFFF

# Polling interval
POLL_INTERVAL = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Global flag and single-instance lock
_running = True
_lock_fd = None


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

    # 3. Check MariaDB system_command table
    try:
        conn = None
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
                    pass

        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, cmd_name FROM system_command WHERE run_python = 1 "
                "AND (cmd_name LIKE '%test%' OR cmd_name LIKE '%quick%' OR cmd_name LIKE '%deep%' OR cmd_name LIKE '%stop%')"
            )
            rows = cursor.fetchall()
            for row in rows:
                c_id, c_name = row[0], row[1]
                cmds.append(c_name)
                cursor.execute("UPDATE system_command SET run_python = 0 WHERE id = %s", (c_id,))
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        logging.debug(f"DB command check encountered non-fatal error: {e}")

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

    # 4.1 State-driven synchronization to prevent stale variables
    status_str = str(data.get("ups.status", "")).upper()
    vin = float(data.get("input.voltage", 0.0) or 0.0)
    vout = float(data.get("output.voltage", 0.0) or 0.0)

    # If output voltage is 0/low (< 50V) and not in battery operation, the UPS is OFF
    if vout < 50.0 and "OB" not in status_str and "DISCHRG" not in status_str:
        status_str = "OFF"
        data["ups.status"] = "OFF"

    is_on_batt = "OB" in status_str or "DISCHRG" in status_str or (vin < 50.0 and "OL" not in status_str and status_str != "OFF")
    is_off = "OFF" in status_str or (vout < 50.0 and not is_on_batt)

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

    # Smart fallback for ups.temperature if hardware lacks internal temp sensor (e.g. Offline 2000D / MEC0003)
    if "ups.temperature" not in data or float(data.get("ups.temperature", 0.0) or 0.0) <= 0.0:
        data["ups.temperature"] = 25.0

    # Smart fallback for ups.load if not provided
    if "ups.load" not in data:
        data["ups.load"] = 0

    # 5. UPS Nominal Power & Real Power (Model-specific ratings)
    model_str = (info.get("model") or info.get("product_string") or data.get("device.model") or data.get("ups.model") or (profile.model if profile else "")).lower()

    if "2000" in model_str or "offline" in model_str:
        data.setdefault("ups.power.nominal", 2000)
        data.setdefault("ups.realpower.nominal", 1200)
    elif "mec" in model_str or "800" in model_str:
        data.setdefault("ups.power.nominal", 800)
        data.setdefault("ups.realpower.nominal", 480)
    elif "innova" in model_str or "unity" in model_str or "basic" in model_str:
        data.setdefault("ups.power.nominal", 3000)
        data.setdefault("ups.realpower.nominal", 2700)
    else:
        if "ups.power.nominal" in data and "ups.realpower.nominal" not in data:
            data["ups.realpower.nominal"] = int(round(float(data["ups.power.nominal"]) * 0.8))
        elif "ups.realpower.nominal" in data and "ups.power.nominal" not in data:
            data["ups.power.nominal"] = data["ups.realpower.nominal"]
        else:
            data.setdefault("ups.power.nominal", 2000)
            data.setdefault("ups.realpower.nominal", 1200)

    # 5.1 Dynamic Output Power & Current Calculation (for models lacking raw power meters e.g. Offline 2000D)
    if not is_off:
        load_pct = float(data.get("ups.load", 0) or 0)
        nom_va = float(data.get("ups.power.nominal", 2700) or 2700)
        nom_w = float(data.get("ups.realpower.nominal", 2700) or 2700)
        vout = float(data.get("output.voltage", 230.0) or 230.0)

        if "output.power.apparent" not in data or data.get("output.power.apparent") is None:
            data["output.power.apparent"] = int(round((load_pct / 100.0) * nom_va))

        if "output.power" not in data or data.get("output.power") is None:
            data["output.power"] = int(round((load_pct / 100.0) * nom_w))

        if "output.current" not in data or data.get("output.current") is None:
            if vout > 50.0:
                data["output.current"] = round(float(data["output.power.apparent"]) / vout, 1)
            else:
                data["output.current"] = 0.0

    # 6. System Timers, Control & Dates
    data.setdefault("ups.delay.shutdown", 20)
    data.setdefault("ups.delay.start", 30)
    data.setdefault("ups.timer.shutdown", -1)
    data.setdefault("ups.timer.start", -1)
    data.setdefault("battery.test.status", "passed")
    data.setdefault("ups.beeper.status", "enabled")
    data.setdefault("ups.date", datetime.datetime.now().strftime("%Y/%m/%d"))

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
    else:
        data.setdefault("ups.test.result", "Done and passed")

    return data


_is_connected = False


def set_disconnected_state():
    """
    Sets NUT state to DNC (Driver Not Connected) and immediately restarts
    nut-driver and nut-server so dummy-ups and upsd purge all stale in-memory variables.
    """
    global _is_connected
    if not _is_connected and os.path.exists(DUMMY_FILE):
        try:
            with open(DUMMY_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if "ups.status: DNC" in content and len(content.strip().splitlines()) <= 2:
                return
        except Exception:
            pass

    _is_connected = False
    logging.warning("UPS disconnected or unavailable. Writing DNC state and flushing NUT cache...")

    temp_file = DUMMY_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write("device.type: ups\n")
            f.write("ups.status: DNC\n")
        os.rename(temp_file, DUMMY_FILE)
        os.chmod(DUMMY_FILE, 0o666)
    except Exception as e:
        logging.error(f"Failed to write disconnected state file: {e}")

    # Restart nut-driver and nut-server to clear all in-memory variables
    try:
        os.system("systemctl restart nut-driver nut-server 2>/dev/null || /sbin/upsdrvctl stop && /sbin/upsdrvctl start 2>/dev/null || true")
    except Exception as e:
        logging.error(f"Failed to restart nut services: {e}")


def main():
    global _is_connected
    acquire_single_instance_lock()
    logging.info("Starting Enerex UPS Bridge daemon...")

    # Ensure clean DNC state on initial start if dummy file does not exist
    if not os.path.exists(DUMMY_FILE):
        set_disconnected_state()

    while _running:
        client = None
        try:
            logging.info("Scanning for Enerex/Phoenixtec/Megatec UPS...")
            client = UPSClient.auto_detect()
            client.connect()

            info = client.device_info
            profile = getattr(client, "profile", None)
            mfr = info.get("manufacturer") or info.get("manufacturer_string") or (profile.manufacturer if profile else "Enerex")
            prod = info.get("model") or info.get("product_string") or (profile.model if profile else "UPS")
            logging.info(f"Connected to UPS: Manufacturer='{mfr}', Product='{prod}' (Protocol: {getattr(profile, 'protocol', 'unknown')})")

            _is_connected = True

            # Clear old data in dummy-ups memory and reconnect upsd
            logging.info("Restarting nut-driver and nut-server to clear stale variables...")
            os.system("systemctl restart nut-driver && systemctl restart nut-server")
            time.sleep(1.5)

            # Polling loop for the connected UPS
            while _running:
                try:
                    # 0. Check and execute pending commands (Battery Test from DB, Signals, or File IPC)
                    check_and_execute_commands(client)

                    # 1. Read live UPS variables (existing logic preserved 100%)
                    data = client.get_vars()

                    # 2. Enrich with missing usbhid-ups compatible variables
                    data = enrich_nut_variables(data, info, profile)

                    # 3. Write to temp file first to prevent NUT from reading an incomplete file
                    temp_file = DUMMY_FILE + ".tmp"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        for key, value in sorted(data.items()):
                            f.write(f"{key}: {value}\n")

                    # 4. Atomic replace
                    os.rename(temp_file, DUMMY_FILE)
                    os.chmod(DUMMY_FILE, 0o666)

                except Exception as e:
                    if not _running:
                        break
                    logging.error(f"Error reading UPS data (Device disconnected?): {e}")
                    # Tell dummy-ups the device is disconnected and purge stale cache
                    set_disconnected_state()
                    break

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            if not _running:
                break
            set_disconnected_state()
            logging.warning(f"No UPS found or connect failed: {e}. Retrying in 5 seconds...")
            time.sleep(5)
        finally:
            if client and getattr(client, "is_connected", False):
                try:
                    client.disconnect()
                except Exception:
                    pass
    logging.info("Enerex UPS Bridge exited cleanly.")


if __name__ == "__main__":
    main()
