#!/bin/bash

# =============================================================================
# Enerex-UPS Python Bridge Updater for Linux
# =============================================================================
# This script updates the bridge software in /opt/enerex-ups/ without requiring
# a full re-installation:
#   1. Stops enerex-ups-bridge service
#   2. Clears Python bytecache (__pycache__)
#   3. Syncs latest ups_module/ and enerex_ups_bridge.py to /opt/enerex-ups/
#   4. Updates CLI helpers (/usr/local/bin/upscmd, enerex-test)
#   5. Verifies IPC and state file permissions
#   6. Restarts the bridge and reloads NUT services
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

# Check source files
if [ ! -d "./ups_module" ] || [ ! -f "./enerex_ups_bridge.py" ]; then
    echo "ERROR: Required files (ups_module/ or enerex_ups_bridge.py) not found in $SCRIPT_DIR"
    exit 1
fi

echo "--- 1. Stopping bridge service ---"
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true

echo "--- 2. Updating files in /opt/enerex-ups/ ---"
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
cat << 'EOF' > /usr/local/bin/upscmd
#!/bin/bash
# Intercept instant commands for dummy-ups compatibility
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

if [ -x /usr/bin/upscmd.orig ]; then
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

if [ ! -f /etc/nut/myups.dev ]; then
    echo "ups.status: WAIT" > /etc/nut/myups.dev
    chmod 666 /etc/nut/myups.dev
fi

echo "--- 5. Reloading systemd and restarting services ---"
systemctl daemon-reload
systemctl restart enerex-ups-bridge.service

# Smart reload/restart NUT services
if systemctl is-active --quiet nut-driver.service; then
    systemctl reload-or-restart nut-driver.service 2>/dev/null || true
else
    systemctl start nut-driver.service 2>/dev/null || true
fi

if systemctl is-active --quiet nut-server.service; then
    systemctl reload-or-restart nut-server.service 2>/dev/null || true
else
    systemctl start nut-server.service 2>/dev/null || true
fi

sleep 1
if systemctl is-active --quiet enerex-ups-bridge.service; then
    echo "  [OK] enerex-ups-bridge.service is active and running"
else
    echo "  [WARNING] enerex-ups-bridge.service may have failed to start"
    echo "  Check logs: sudo journalctl -u enerex-ups-bridge.service -n 20"
fi

echo "=========================================================="
echo " Update Complete!"
echo " Check bridge status: sudo systemctl status enerex-ups-bridge"
echo " Check telemetry:     upsc myups"
echo "=========================================================="
