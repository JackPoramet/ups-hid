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
apt-get install -y python3-hid python3-usb

echo "--- 2. Stopping existing NUT services ---"
systemctl stop nut-server.service || true
systemctl stop nut-driver.service || true
systemctl stop enerex-ups-bridge.service 2>/dev/null || true

echo "--- 3. Copying files to /opt/enerex-ups/ ---"
# Clear old files and python cache to prevent stale code execution
rm -rf /opt/enerex-ups/*
rm -rf ./ups_module/__pycache__
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

# echo "--- 4. Configuring /etc/nut/ups.conf ---"
# UPS_CONF="/etc/nut/ups.conf"
# 
# # Remove any existing [enerex-ups] or old [myups] settings to ensure clean config
# sed -i '/^\[enerex-ups\]/d' "$UPS_CONF"
# sed -i '/^\[myups\]/d' "$UPS_CONF"
# sed -i '/driver = blazer_usb/d' "$UPS_CONF"
# sed -i '/driver = enerex/d' "$UPS_CONF"
# sed -i '/driver = dummy-ups/d' "$UPS_CONF"
# sed -i '/port = auto/d' "$UPS_CONF"
# sed -i '/port = \/etc\/nut\/enerex-ups.dev/d' "$UPS_CONF"
# sed -i '/port = \/etc\/nut\/myups.dev/d' "$UPS_CONF"
# sed -i '/desc = "Universal Enerex Python Bridge"/d' "$UPS_CONF"
# sed -i '/desc = "My UPS"/d' "$UPS_CONF"
# sed -i '/desc = "My UPS (Enerex Python Bridge)"/d' "$UPS_CONF"
# 
# echo "" >> "$UPS_CONF"
# echo "[myups]" >> "$UPS_CONF"
# echo "    driver = enerex" >> "$UPS_CONF"
# echo "    port = /etc/nut/myups.dev" >> "$UPS_CONF"
# echo "    desc = \"My UPS (Enerex Python Bridge)\"" >> "$UPS_CONF"
# echo "Configured [myups] in $UPS_CONF"

echo "--- 4.5. Masking dummy-ups driver name ---"
if [ -f "/lib/nut/dummy-ups" ]; then
    ln -sf /lib/nut/dummy-ups /lib/nut/enerex
fi

echo "--- 5. Initializing dummy device file ---"
echo "ups.status: WAIT" > /etc/nut/myups.dev
chmod 666 /etc/nut/myups.dev

echo "--- 6. Setting up Systemd Service ---"
SERVICE_FILE="/etc/systemd/system/enerex-ups-bridge.service"
cat << 'EOF' > "$SERVICE_FILE"
[Unit]
Description=Enerex UPS Python to Dummy-UPS Bridge
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/enerex-ups
ExecStart=/usr/bin/python3 /opt/enerex-ups/enerex_ups_bridge.py
Restart=always
RestartSec=5

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
