#!/bin/bash

# Enerex-UPS Python Bridge Installer for Orange Pi Zero
# This script installs the bridge to coexist with blazer_usb

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

echo "--- 1. Installing required dependencies ---"
apt-get update
apt-get install -y python3-hid python3-usb python3-pymysql python3-mysqldb 2>/dev/null || apt-get install -y python3-hid python3-usb python3-pymysql 2>/dev/null || apt-get install -y python3-hid python3-usb

echo "--- 2. Stopping existing NUT services and old bridge processes ---"
systemctl stop nut-server.service || true
systemctl stop nut-driver.service || true
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true

echo "--- 3. Copying files to /opt/enerex-ups/ ---"
# Clear old files and python cache to prevent stale code execution
rm -rf /opt/enerex-ups/*
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
mkdir -p /opt/enerex-ups
# We expect ups_module to be copied inside the current deployment folder
if [ -d "./ups_module" ]; then
    cp -r ./ups_module /opt/enerex-ups/
else
    echo "ERROR: Cannot find ./ups_module in the current directory. Make sure it's copied into this deployment folder."
    exit 1
fi

cp enerex_ups_bridge.py /opt/enerex-ups/
chmod +x /opt/enerex-ups/enerex_ups_bridge.py

echo "--- 4. Masking dummy-ups driver name ---"
if [ -f "/lib/nut/dummy-ups" ]; then
    ln -sf /lib/nut/dummy-ups /lib/nut/enerex
fi

echo "--- 5. Initializing dummy device file and IPC queue ---"
echo "ups.status: WAIT" > /etc/nut/myups.dev
chmod 666 /etc/nut/myups.dev

touch /run/enerex_ups_cmd /tmp/enerex_ups_cmd
chmod 666 /run/enerex_ups_cmd /tmp/enerex_ups_cmd 2>/dev/null || true

echo "--- 5.5 Installing upscmd wrapper and enerex-test CLI tool ---"
# Backup original binary if not already backed up
if [ -f /usr/bin/upscmd ] && [ ! -L /usr/bin/upscmd ] && ! grep -q "enerex_ups_cmd" /usr/bin/upscmd 2>/dev/null; then
    cp /usr/bin/upscmd /usr/bin/upscmd.orig
fi

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
cp /usr/local/bin/upscmd /usr/bin/upscmd

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

echo "--- 6. Setting up Systemd Service (Production Standards) ---"
SERVICE_FILE="/etc/systemd/system/enerex-ups-bridge.service"
cat << 'EOF' > "$SERVICE_FILE"
[Unit]
Description=Enerex UPS Python to Dummy-UPS Bridge
After=network.target local-fs.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/enerex-ups
ExecStart=/usr/bin/python3 /opt/enerex-ups/enerex_ups_bridge.py
Restart=always
RestartSec=3
KillMode=mixed
TimeoutStopSec=5
StandardOutput=journal
StandardError=journal
Nice=0

[Install]
WantedBy=multi-user.target
EOF

echo "--- 6.5 Patching nut-driver to not fail on missing UPS devices ---"
# By adding '-' before the command, systemd will ignore the exit code if a driver fails (e.g. blazer_usb unplugged)
if [ -f /lib/systemd/system/nut-driver.service ]; then
    sed -i 's/ExecStart=\/sbin\/upsdrvctl start/ExecStart=-\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
fi

echo "--- 7. Starting Services ---"
systemctl daemon-reload
systemctl enable enerex-ups-bridge.service
systemctl start enerex-ups-bridge.service

systemctl start nut-driver.service
systemctl start nut-server.service

echo "=========================================================="
echo "Installation Complete!"
echo "Check bridge status with: sudo systemctl status enerex-ups-bridge"
echo "Check UPS data with: upsc myups"
echo "=========================================================="
