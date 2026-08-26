#!/bin/bash

# =============================================================================
# Universal UPS Bridge Uninstaller for Linux (NUT Integration)
# =============================================================================
# This script completely reverses everything configured by install.sh:
#   1. Stops and disables enerex-ups-bridge.service
#   2. Terminates any running bridge processes
#   3. Removes systemd service file (/etc/systemd/system/enerex-ups-bridge.service)
#   4. Removes deployed files from /opt/enerex-ups/
#   5. Removes driver symlink (/lib/nut/enerex)
#   6. Cleans state and lock files (/etc/nut/myups.dev, /run/enerex_ups_bridge.lock)
#   7. Reverts nut-driver systemd service patch
#   8. Reloads systemd daemon
# =============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./uninstall.sh)"
  exit 1
fi

echo "=========================================================="
echo " Starting Universal UPS Bridge Uninstallation..."
echo "=========================================================="

echo "--- 1. Stopping and disabling Bridge & NUT Services ---"
systemctl stop enerex-ups-bridge.service 2>/dev/null || true
systemctl disable enerex-ups-bridge.service 2>/dev/null || true
systemctl stop nut-server.service 2>/dev/null || true
systemctl stop nut-driver.service 2>/dev/null || true

# Force kill any lingering bridge python processes
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true

echo "--- 2. Removing Systemd Service File ---"
if [ -f "/etc/systemd/system/enerex-ups-bridge.service" ]; then
    rm -f /etc/systemd/system/enerex-ups-bridge.service
    echo "  [OK] Removed /etc/systemd/system/enerex-ups-bridge.service"
fi

echo "--- 3. Removing Deployed Files in /opt/enerex-ups/ ---"
if [ -d "/opt/enerex-ups" ]; then
    rm -rf /opt/enerex-ups
    echo "  [OK] Removed /opt/enerex-ups directory"
fi

echo "--- 4. Removing Driver Symlink ---"
if [ -L "/lib/nut/enerex" ] || [ -f "/lib/nut/enerex" ]; then
    rm -f /lib/nut/enerex
    echo "  [OK] Removed /lib/nut/enerex symlink"
fi

echo "--- 5. Cleaning State, Lock, and Temporary Files ---"
rm -f /etc/nut/myups.dev
rm -f /etc/nut/myups.dev.tmp
rm -f /run/enerex_ups_bridge.lock
rm -f /tmp/enerex_ups_bridge.lock
echo "  [OK] State and lock files removed"

echo "--- 6. Reverting nut-driver.service patch (if applied) ---"
if [ -f "/lib/systemd/system/nut-driver.service" ]; then
    sed -i 's/ExecStart=-\/sbin\/upsdrvctl start/ExecStart=\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
    echo "  [OK] Reverted nut-driver.service"
fi

echo "--- 7. Reloading Systemd Daemon ---"
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# Check if user wants to remove system dependencies
echo ""
read -r -p "Do you also want to remove apt packages (python3-hid, python3-usb)? [y/N]: " REMOVE_PKGS
case "$REMOVE_PKGS" in
    [yY][eE][sS]|[yY])
        echo "Removing python3-hid python3-usb..."
        apt-get remove -y python3-hid python3-usb || true
        echo "  [OK] Packages removed"
        ;;
    *)
        echo "  [SKIP] Retained python3-hid and python3-usb system packages"
        ;;
esac

echo ""
echo "=========================================================="
echo " Uninstallation Complete!"
echo " Everything installed by install.sh has been cleaned."
echo "=========================================================="
