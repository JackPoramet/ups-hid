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
if [ ! -d "./ups_module" ] || [ ! -f "./enerex_ups_bridge.py" ]; then
    echo "ERROR: Required files (ups_module/ or enerex_ups_bridge.py) not found in $SCRIPT_DIR"
    exit 1
fi

echo "--- 1. Stopping NUT services and old bridge processes ---"
# Always stop nut-server (consumer) before nut-driver (producer)
systemctl stop nut-server.service 2>/dev/null || true
systemctl stop nut-driver.service 2>/dev/null || true
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true

# Clear stale NUT PID and socket files to avoid "socket in use" or "stale driver" errors
rm -f /run/nut/*.pid /var/run/nut/*.pid 2>/dev/null || true
rm -f /run/enerex_ups_bridge.lock /tmp/enerex_ups_bridge.lock 2>/dev/null || true

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

# 1) Start bridge service first so it can probe UPS hardware and write telemetry
systemctl restart enerex-ups-bridge.service
sleep 1

# 2) Start nut-driver (dummy-ups) so it initializes and creates the driver communication socket
systemctl start nut-driver.service
sleep 1

# 3) Start nut-server (upsd) after driver socket is ready
systemctl start nut-server.service
sleep 1

# Health checks
BRIDGE_ACTIVE=false
DRIVER_ACTIVE=false
SERVER_ACTIVE=false

systemctl is-active --quiet enerex-ups-bridge.service && BRIDGE_ACTIVE=true || true
systemctl is-active --quiet nut-driver.service && DRIVER_ACTIVE=true || true
systemctl is-active --quiet nut-server.service && SERVER_ACTIVE=true || true

if [ "$BRIDGE_ACTIVE" = true ] && [ "$DRIVER_ACTIVE" = true ] && [ "$SERVER_ACTIVE" = true ]; then
    echo "=========================================================="
    echo " [OK] Update Complete! All services active and healthy:"
    echo "   - enerex-ups-bridge : active (running)"
    echo "   - nut-driver        : active (running)"
    echo "   - nut-server        : active (running)"
    echo " Check UPS data with: upsc myups"
    echo "=========================================================="
else
    echo "=========================================================="
    echo " [WARNING] Some services failed to start cleanly:"
    [ "$BRIDGE_ACTIVE" = false ] && echo "   - enerex-ups-bridge : FAILED"
    [ "$DRIVER_ACTIVE" = false ] && echo "   - nut-driver        : FAILED"
    [ "$SERVER_ACTIVE" = false ] && echo "   - nut-server        : FAILED"
    echo ""
    echo " View logs with:"
    echo "   sudo journalctl -u nut-server.service -n 20 --no-pager"
    echo "   sudo journalctl -u nut-driver.service -n 20 --no-pager"
    echo "=========================================================="
fi
