#!/bin/bash

# Enerex-UPS Python Bridge Installer for Orange Pi Zero
# This script installs the bridge to coexist with blazer_usb

set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo ./install.sh)"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

exec 9>/run/enerex-ups-maintenance.lock
if ! flock -n 9; then
    echo "ERROR: Another Enerex maintenance operation is running" >&2
    exit 1
fi

for source in ups_module enerex_ups_bridge.py enerex-test upscmd enerex-ups.conf enerex-driver; do
    if [ ! -e "$SCRIPT_DIR/$source" ]; then
        echo "ERROR: Missing source artifact: $source" >&2
        exit 1
    fi
done

# Refuse native/multi-UPS or foreign monitor configuration before stopping anything.
python3 "$SCRIPT_DIR/ups_module/nut_config.py" --check
monitor_original=$(systemctl is-enabled nut-monitor.service 2>/dev/null || true)
python3 "$SCRIPT_DIR/ups_module/nut_config.py" --record-service-state "$monitor_original"

echo "--- 1. Installing required dependencies ---"
apt-get update
apt-get install -y python3-hid python3-usb python3-pymysql python3-mysqldb 2>/dev/null || apt-get install -y python3-hid python3-usb python3-pymysql 2>/dev/null || apt-get install -y python3-hid python3-usb

echo "--- 2. Stopping existing NUT services and old bridge processes ---"
systemctl stop nut-monitor.service 2>/dev/null || true
systemctl stop nut-server.service || true
systemctl stop nut-driver.service || true
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

echo "--- 4. Installing native NUT driver adapter ---"
# Install the native NUT adapter without following the old dummy-ups symlink.
install -m 0755 "$SCRIPT_DIR/enerex-driver" /lib/nut/.enerex-new
mv -f /lib/nut/.enerex-new /lib/nut/enerex
# Native adapter installed

echo "--- 5. Initializing dummy device file and IPC queue ---"
install -o root -g nut -m 0640 /dev/null /etc/nut/myups.dev
echo "ups.status: WAIT" > /etc/nut/myups.dev

getent group ups-hid >/dev/null || groupadd --system ups-hid
install -m 0644 "$SCRIPT_DIR/enerex-ups.conf" /etc/tmpfiles.d/enerex-ups.conf
systemd-tmpfiles --create /etc/tmpfiles.d/enerex-ups.conf
install -d -o nut -g nut -m 0770 /run/nut
python3 "$SCRIPT_DIR/ups_module/nut_config.py"

echo "--- 5.5 Installing upscmd wrapper and enerex-test CLI tool ---"
# Backup original binary if not already backed up
if [ -f /usr/bin/upscmd ] && [ ! -L /usr/bin/upscmd ] && ! grep -q "enerex_ups_cmd" /usr/bin/upscmd 2>/dev/null; then
    cp /usr/bin/upscmd /usr/bin/upscmd.orig
fi

install -m 0755 "$SCRIPT_DIR/upscmd" /usr/local/bin/upscmd
install -m 0755 "$SCRIPT_DIR/enerex-test" /usr/local/bin/enerex-test

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

echo "--- 6.5 Restoring nut-driver failure reporting ---"
# Undo the legacy patch that hid driver startup failures.
if [ -f /lib/systemd/system/nut-driver.service ]; then
    sed -i 's/ExecStart=-\/sbin\/upsdrvctl start/ExecStart=\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
fi

echo "--- 7. Starting Services ---"
systemctl daemon-reload
systemctl enable enerex-ups-bridge.service
systemctl start enerex-ups-bridge.service

# Start nut-server; nut-driver is managed dynamically by enerex-ups-bridge based on UPS connection
systemctl start nut-server.service
systemctl enable nut-monitor.service
systemctl restart nut-monitor.service
systemctl is-active --quiet nut-monitor.service

echo "=========================================================="
echo "Installation Complete!"
echo "Check bridge status with: sudo systemctl status enerex-ups-bridge"
echo "Check UPS data with: upsc myups"
echo "=========================================================="
