#!/bin/bash

# =============================================================================
# Enerex-UPS Python Bridge Updater for Linux
# =============================================================================
# Cleanly updates the bridge software and restarts NUT without service failure:
#   1. Stops nut-server, nut-driver, and enerex-ups-bridge in order
#   2. Cleans stale sockets, PID files, and Python __pycache__
#   3. Syncs latest ups_module/ and enerex_ups_bridge.py to /opt/enerex-ups/
#   4. Updates CLI helpers (/usr/local/bin/upscmd, enerex-test)
#   5. Verifies state file, IPC queue permissions, and nut-driver service patch
#   6. Starts enerex-ups-bridge -> nut-driver -> nut-server sequentially
# =============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./update.sh)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# One owner across installation, update and diagnostic capture, including recovery.
exec 9>/run/enerex-ups-maintenance.lock
if ! flock -n 9; then
    echo "ERROR: Another Enerex maintenance operation is running" >&2
    exit 1
fi

if [ "$#" -gt 0 ]; then
    if [ "$#" -ne 2 ] || [ "$1" != --capture-ratings ]; then
        echo "Usage: $0 [--capture-ratings /absolute/path/new-capture.json]" >&2
        exit 2
    fi
    case "$2" in /*) ;; *) echo "ERROR: Capture output must be absolute" >&2; exit 2 ;; esac
    if [ -e "$2" ] || [ -L "$2" ] || [ ! -d "$(dirname "$2")" ] || [ ! -f "$SCRIPT_DIR/ups_module/capture_ratings.py" ]; then
        echo "ERROR: Capture requires a new output file and the capture helper" >&2
        exit 2
    fi
    capture_sections=$(awk '/^[[:space:]]*\[/ { n++ } END { print n+0 }' /etc/nut/ups.conf)
    capture_driver=$(awk -F= '/^[[:space:]]*driver[[:space:]]*=/ { sub(/#.*/, "", $2); gsub(/[[:space:]]/, "", $2); print $2; exit }' /etc/nut/ups.conf)
    if [ "$capture_sections" -ne 1 ] || { [ "$capture_driver" != enerex ] && [ "$capture_driver" != dummy-ups ]; }; then
        echo "ERROR: Capture requires a single UPS owned by the Enerex bridge" >&2
        exit 1
    fi
    if ! systemctl is-active --quiet enerex-ups-bridge.service; then
        echo "ERROR: Bridge must be active before maintenance capture" >&2
        exit 1
    fi
    capture_driver_active=false
    capture_nut_ready() {
        capture_vars=$(timeout 2s upsc myups@localhost 2>/dev/null) || return 1
        grep -q '^device.model: ' <<< "$capture_vars" &&
            grep -q '^ups.status: ' <<< "$capture_vars" &&
            ! grep -q '^ups.status: WAIT' <<< "$capture_vars"
    }
    if systemctl is-active --quiet nut-driver.service; then
        capture_driver_active=true
        if ! capture_nut_ready; then
            echo "ERROR: Active driver is not serving telemetry; inspect before capture" >&2
            exit 1
        fi
    fi
    umask 077
    capture_marker=$(mktemp "${2}.start.XXXXXX")
    restore_capture_bridge() {
        capture_rc=$?
        trap - EXIT
        if ! timeout 10s systemctl start enerex-ups-bridge.service; then
            rm -f "$capture_marker"
            echo "ERROR: Failed to restore bridge after capture" >&2
            exit 1
        fi
        if [ "$capture_driver_active" = true ]; then
            capture_restored=false
            capture_deadline=$((SECONDS + 30))
            while [ "$SECONDS" -lt "$capture_deadline" ]; do
                if timeout 2s systemctl is-active --quiet nut-driver.service &&
                    [ /etc/nut/myups.dev -nt "$capture_marker" ] && capture_nut_ready; then
                    capture_restored=true
                    break
                fi
                sleep 1
            done
            if [ "$capture_restored" != true ]; then
                rm -f "$capture_marker"
                echo "ERROR: Failed to restore healthy NUT telemetry after capture" >&2
                exit 1
            fi
        fi
        rm -f "$capture_marker"
        exit "$capture_rc"
    }
    trap restore_capture_bridge EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    timeout 10s systemctl stop enerex-ups-bridge.service nut-driver.service
    # Exclude a final old-bridge publish made during service shutdown.
    touch "$capture_marker"
    timeout --signal=TERM --kill-after=2s 15s python3 "$SCRIPT_DIR/ups_module/capture_ratings.py" --output "$2"
    exit 0
fi

for source in ups_module enerex_ups_bridge.py enerex-test upscmd enerex-ups.conf enerex-driver; do
    if [ ! -e "$SCRIPT_DIR/$source" ]; then
        echo "ERROR: Missing source artifact: $source" >&2
        exit 1
    fi
done

echo "=========================================================="
echo " Updating Enerex UPS Bridge..."
echo "=========================================================="

# Check source files exist
if [ ! -d "./ups_module" ] || [ ! -f "./enerex_ups_bridge.py" ]; then
    echo "ERROR: Required files (ups_module/ or enerex_ups_bridge.py) not found in $SCRIPT_DIR"
    exit 1
fi

# Refuse native/multi-UPS or foreign monitor configuration before stopping anything.
python3 "$SCRIPT_DIR/ups_module/nut_config.py" --check
monitor_original=$(systemctl is-enabled nut-monitor.service 2>/dev/null || true)
python3 "$SCRIPT_DIR/ups_module/nut_config.py" --record-service-state "$monitor_original"

echo "--- 1. Stopping NUT services and old bridge processes ---"
# Always stop nut-server (consumer) before nut-driver (producer)
systemctl stop nut-monitor.service 2>/dev/null || true
systemctl stop nut-server.service 2>/dev/null || true
systemctl stop nut-driver.service 2>/dev/null || true
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
# Match the Python entry point, excluding SSH/shell payloads mentioning this file.
pkill -9 -f '^(/[^ ]*/)?python(3([.][0-9]+)?)?[[:space:]]+(-u[[:space:]]+)?((/[^ ]*/)|([.]/))?enerex_ups_bridge[.]py([[:space:]]|$)' 2>/dev/null || true
# Never unlink a live lock inode: refuse maintenance if an owner survived.
bridge_lock=/tmp/enerex_ups_bridge.lock
if [ -d /run ]; then bridge_lock=/run/enerex_ups_bridge.lock; fi
for bridge_lock in "$bridge_lock"; do
    if [ -e "$bridge_lock" ] && ! flock -n "$bridge_lock" true; then
        echo "ERROR: Bridge still owns $bridge_lock; refusing to replace files" >&2
        exit 1
    fi
done

# Clear stale legacy artifacts only; native driver PID locks must keep their inode.

echo "--- 2. Updating code in /opt/enerex-ups/ ---"
# Clear Python caches
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /opt/enerex-ups -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

mkdir -p /opt/enerex-ups
rm -rf /opt/enerex-ups/ups_module
cp -r ./ups_module /opt/enerex-ups/
cp ./enerex_ups_bridge.py /opt/enerex-ups/
chmod +x /opt/enerex-ups/enerex_ups_bridge.py
echo "  [OK] Updated /opt/enerex-ups/ files"

echo "--- 3. Updating CLI helper tools ---"
install -m 0755 "$SCRIPT_DIR/upscmd" /usr/local/bin/upscmd
install -m 0755 "$SCRIPT_DIR/enerex-test" /usr/local/bin/enerex-test
echo "  [OK] Updated /usr/local/bin/upscmd and /usr/local/bin/enerex-test"

echo "--- 4. Installing native NUT adapter and checking IPC permissions ---"
# Install the native NUT adapter without following the old dummy-ups symlink.
install -m 0755 "$SCRIPT_DIR/enerex-driver" /lib/nut/.enerex-new
mv -f /lib/nut/.enerex-new /lib/nut/enerex
# Native adapter installed

getent group ups-hid >/dev/null || groupadd --system ups-hid
install -m 0644 "$SCRIPT_DIR/enerex-ups.conf" /etc/tmpfiles.d/enerex-ups.conf
systemd-tmpfiles --create /etc/tmpfiles.d/enerex-ups.conf
install -d -o nut -g nut -m 0770 /run/nut
python3 "$SCRIPT_DIR/ups_module/nut_config.py"

# Ensure dummy state file exists and has valid initial state so nut-driver doesn't fail
if [ ! -s /etc/nut/myups.dev ]; then
    install -o root -g nut -m 0640 /dev/null /etc/nut/myups.dev
    echo "ups.status: WAIT" > /etc/nut/myups.dev
fi
chown root:nut /etc/nut/myups.dev
chmod 640 /etc/nut/myups.dev

# Restore driver failure reporting; absent hardware is handled by the bridge.
if [ -f /lib/systemd/system/nut-driver.service ]; then
    sed -i 's/ExecStart=-\/sbin\/upsdrvctl start/ExecStart=\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
fi

echo "--- 5. Reloading systemd and restarting services sequentially ---"
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# 1) Start bridge service first so it can probe UPS hardware and manage nut-driver
systemctl restart enerex-ups-bridge.service
sleep 1

# 2) Ensure nut-server (upsd) is running
systemctl start nut-server.service
systemctl enable nut-monitor.service
systemctl restart nut-monitor.service
sleep 1

# Health checks
BRIDGE_ACTIVE=false
DRIVER_ACTIVE=false
SERVER_ACTIVE=false
MONITOR_ACTIVE=false
DRIVER_FAILED=false

systemctl is-active --quiet enerex-ups-bridge.service && BRIDGE_ACTIVE=true || true
systemctl is-active --quiet nut-driver.service && DRIVER_ACTIVE=true || true
systemctl is-active --quiet nut-server.service && SERVER_ACTIVE=true || true
systemctl is-active --quiet nut-monitor.service && MONITOR_ACTIVE=true || true
systemctl is-failed --quiet nut-driver.service && DRIVER_FAILED=true || true

DRIVER_EXPECTED=false
if [ -s /etc/nut/myups.dev ] && ! grep -q '^ups.status: WAIT' /etc/nut/myups.dev; then
    DRIVER_EXPECTED=true
fi
if [ "$BRIDGE_ACTIVE" = true ] && [ "$SERVER_ACTIVE" = true ] && [ "$MONITOR_ACTIVE" = true ] && [ "$DRIVER_FAILED" = false ] && { [ "$DRIVER_ACTIVE" = true ] || [ "$DRIVER_EXPECTED" = false ]; }; then
    echo "=========================================================="
    echo " [OK] Update Complete! Core services active and healthy:"
    echo "   - enerex-ups-bridge : active (running)"
    echo "   - nut-server        : active (running)"
    echo "   - nut-monitor       : active (notification only; no local shutdown)"
    if [ "$DRIVER_ACTIVE" = true ]; then
        echo "   - nut-driver        : active (UPS connected)"
    else
        echo "   - nut-driver        : standby (driver inactive; awaiting confirmed telemetry)"
    fi
    echo " Check UPS data with: upsc myups"
    echo "=========================================================="
else
    echo "=========================================================="
    echo " [WARNING] Some services failed to start cleanly:"
    [ "$DRIVER_FAILED" = true ] && echo "   - nut-driver        : FAILED (systemd failed state)"
    [ "$BRIDGE_ACTIVE" = false ] && echo "   - enerex-ups-bridge : FAILED"
    [ "$SERVER_ACTIVE" = false ] && echo "   - nut-server        : FAILED"
    [ "$MONITOR_ACTIVE" = false ] && echo "   - nut-monitor       : FAILED"
    [ "$DRIVER_EXPECTED" = true ] && [ "$DRIVER_ACTIVE" = false ] && echo "   - nut-driver        : FAILED (telemetry exists)"
    echo ""
    echo " View logs with:"
    echo "   sudo journalctl -u nut-server.service -n 20 --no-pager"
    echo "   sudo journalctl -u nut-driver.service -n 20 --no-pager"
    echo "=========================================================="
    exit 1
fi
