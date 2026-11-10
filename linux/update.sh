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

echo "=========================================================="
echo " Updating Enerex UPS Bridge..."
echo "=========================================================="

# Check source files exist
if [ ! -d "./ups_module" ] || [ ! -f "./enerex_ups_bridge.py" ] || [ ! -s "./VERSION" ]; then
    echo "ERROR: Required files (ups_module/ or enerex_ups_bridge.py) not found in $SCRIPT_DIR"
    exit 1
fi

echo "--- 1. Stopping NUT services and old bridge processes ---"
# Always stop nut-server (consumer) before nut-driver (producer)
systemctl stop nut-server.service 2>/dev/null || true
systemctl stop nut-driver.service 2>/dev/null || true
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
pkill -9 -f '^(/[^ ]*/)?python(3([.][0-9]+)?)?[[:space:]]+(-u[[:space:]]+)?((/[^ ]*/)|([.]/))?enerex_ups_bridge[.]py([[:space:]]|$)' 2>/dev/null || true
bridge_lock=/run/enerex_ups_bridge.lock
if [ -e "$bridge_lock" ] && ! flock -n "$bridge_lock" true; then
    echo "ERROR: Bridge still owns $bridge_lock; refusing to replace files" >&2
    exit 1
fi

# Preserve live PID and lock inodes.

echo "--- 2. Updating code in /opt/enerex-ups/ ---"
# Clear Python caches
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /opt/enerex-ups -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

mkdir -p /opt/enerex-ups
rm -f /opt/enerex-ups/VERSION
rm -rf /opt/enerex-ups/ups_module
cp -r ./ups_module /opt/enerex-ups/
cp ./enerex_ups_bridge.py /opt/enerex-ups/
chmod +x /opt/enerex-ups/enerex_ups_bridge.py
echo "  [OK] Updated /opt/enerex-ups/ files"

echo "--- 3. Updating CLI helper tools ---"
cat << 'EOF' > /usr/local/bin/upscmd
#!/bin/bash
# Smart upscmd router: detects active driver in ups.conf
DRIVER=$(grep -E '^[[:space:]]*driver[[:space:]]*=' /etc/nut/ups.conf 2>/dev/null | grep -v '^[[:space:]]*#' | head -n 1 | cut -d'=' -f2 | tr -d ' \t\r\n')

# If driver is enerex, route commands to enerex-ups-bridge
if [ "$DRIVER" = "enerex" ]; then
    for arg in "$@"; do
        case "$arg" in
            *deep*|*test.battery.deep*|*test.battery.start.deep*)
                echo "cmd_test_battery_deep" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_deep" > /tmp/enerex_ups_cmd 2>/dev/null || true
                pkill -SIGUSR1 -f enerex_ups_bridge.py 2>/dev/null || true
                echo "OK: Deep battery test initiated"
                exit 0
                ;;
            *stop*|*test.battery.stop*|*abort*|*cancel*)
                echo "cmd_test_battery_stop" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_stop" > /tmp/enerex_ups_cmd 2>/dev/null || true
                pkill -SIGUSR2 -f enerex_ups_bridge.py 2>/dev/null || true
                echo "OK: Battery test stopped"
                exit 0
                ;;
            *quick*|*test.battery.start*|*test.battery.quick*|*test.battery.start.quick*)
                echo "cmd_test_battery_quick" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_quick" > /tmp/enerex_ups_cmd 2>/dev/null || true
                pkill -SIGUSR1 -f enerex_ups_bridge.py 2>/dev/null || true
                echo "OK: Quick battery test (10s) initiated"
                exit 0
                ;;
        esac
    done
fi

# Otherwise (e.g. usbhid-ups, blazer_usb), pass to native NUT binary
if [ -x /usr/bin/upscmd ]; then
    exec /usr/bin/upscmd "$@"
elif [ -x /usr/bin/upscmd.orig ]; then
    exec /usr/bin/upscmd.orig "$@"
fi
exit 0
EOF
chmod +x /usr/local/bin/upscmd

cat << 'EOF' > /usr/local/bin/enerex-test
#!/bin/bash
# CLI Helper to trigger UPS battery self-test and view progress
CMD="${1:-quick}"
case "$CMD" in
    stop|abort|cancel)
        echo "cmd_test_battery_stop" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_stop" > /tmp/enerex_ups_cmd 2>/dev/null || true
        pkill -SIGUSR2 -f enerex_ups_bridge.py 2>/dev/null || true
        echo "[Enerex UPS] Sent Abort/Stop command to UPS."
        ;;
    deep)
        echo "cmd_test_battery_deep" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_deep" > /tmp/enerex_ups_cmd 2>/dev/null || true
        pkill -SIGUSR1 -f enerex_ups_bridge.py 2>/dev/null || true
        echo "[Enerex UPS] Triggered Deep Battery Test."
        ;;
    quick|*)
        echo "cmd_test_battery_quick" > /run/enerex_ups_cmd 2>/dev/null || echo "cmd_test_battery_quick" > /tmp/enerex_ups_cmd 2>/dev/null || true
        pkill -SIGUSR1 -f enerex_ups_bridge.py 2>/dev/null || true
        echo "[Enerex UPS] Triggered Quick Battery Test (10s)."
        ;;
esac
EOF
chmod +x /usr/local/bin/enerex-test
echo "  [OK] Updated /usr/local/bin/upscmd and /usr/local/bin/enerex-test"

echo "--- 4. Checking dummy-ups link and IPC permissions ---"
if [ -f "/lib/nut/dummy-ups" ]; then
    ln -sf /lib/nut/dummy-ups /lib/nut/enerex
fi

touch /run/enerex_ups_cmd /tmp/enerex_ups_cmd
chown root:ups-hid /run/enerex_ups_cmd /tmp/enerex_ups_cmd 2>/dev/null || true
chmod 660 /run/enerex_ups_cmd /tmp/enerex_ups_cmd 2>/dev/null || true

# Discard the previous release's telemetry before starting the bridge. Otherwise
# dummy-ups can retain variables that the new release intentionally omits.
rm -f /etc/nut/myups.dev
# Ensure dummy state file exists and has valid initial state so nut-driver doesn't fail
if [ ! -s /etc/nut/myups.dev ]; then
    echo "ups.status: WAIT" > /etc/nut/myups.dev
fi
chmod 666 /etc/nut/myups.dev

# Ensure nut-driver doesn't fail on missing hardware
if [ -f /lib/systemd/system/nut-driver.service ]; then
    sed -i 's/ExecStart=\/sbin\/upsdrvctl start/ExecStart=-\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
fi

echo "--- 5. Reloading systemd and restarting services sequentially ---"
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# 1) Start bridge service first so it can probe UPS hardware and manage nut-driver
systemctl restart enerex-ups-bridge.service
sleep 1

# 2) Ensure nut-server (upsd) is running
systemctl start nut-server.service
sleep 1

# Health checks
BRIDGE_ACTIVE=false
DRIVER_ACTIVE=false
SERVER_ACTIVE=false

systemctl is-active --quiet enerex-ups-bridge.service && BRIDGE_ACTIVE=true || true
systemctl is-active --quiet nut-driver.service && DRIVER_ACTIVE=true || true
systemctl is-active --quiet nut-server.service && SERVER_ACTIVE=true || true

if [ "$BRIDGE_ACTIVE" = true ] && [ "$SERVER_ACTIVE" = true ]; then
    install -m 0644 "$SCRIPT_DIR/VERSION" /opt/enerex-ups/VERSION
    echo "=========================================================="
    echo " [OK] Update Complete! Core services active and healthy:"
    echo "   - enerex-ups-bridge : active (running)"
    echo "   - nut-server        : active (running)"
    if [ "$DRIVER_ACTIVE" = true ]; then
        echo "   - nut-driver        : active (UPS connected)"
    else
        echo "   - nut-driver        : standby (No UPS connected - reports 'Driver not connected')"
    fi
    echo " Check UPS data with: upsc myups"
    echo "=========================================================="
else
    echo "=========================================================="
    echo " [WARNING] Some services failed to start cleanly:"
    [ "$BRIDGE_ACTIVE" = false ] && echo "   - enerex-ups-bridge : FAILED"
    [ "$SERVER_ACTIVE" = false ] && echo "   - nut-server        : FAILED"
    echo ""
    echo " View logs with:"
    echo "   sudo journalctl -u nut-server.service -n 20 --no-pager"
    echo "   sudo journalctl -u nut-driver.service -n 20 --no-pager"
    echo "=========================================================="
    exit 1
fi
