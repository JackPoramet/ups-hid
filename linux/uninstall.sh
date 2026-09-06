#!/bin/bash

# =============================================================================
# Universal UPS Bridge Uninstaller for Linux
# =============================================================================
# This script cleanly reverts all changes made by install.sh:
#   1. Stops, disables and removes enerex-ups-bridge.service
#   2. Removes deployed files in /opt/enerex-ups/
#   3. Removes driver symlink /lib/nut/enerex
#   4. Removes device state file /etc/nut/myups.dev and lock files
#   5. Reverts nut-driver.service patch
#   6. Kills lingering bridge Python processes
# =============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./uninstall.sh)"
  exit 1
fi

echo "=========================================================="
echo " Starting Enerex UPS Bridge Uninstallation..."
echo "=========================================================="

echo "--- 1. Stopping and Disabling enerex-ups-bridge.service ---"
if systemctl list-unit-files enerex-ups-bridge.service &>/dev/null || [ -f "/etc/systemd/system/enerex-ups-bridge.service" ]; then
    echo "  Stopping and disabling enerex-ups-bridge.service..."
    systemctl stop enerex-ups-bridge.service 2>/dev/null || true
    systemctl disable enerex-ups-bridge.service 2>/dev/null || true
fi

echo "--- 2. Force-Killing Any Lingering Bridge Processes ---"
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true
echo "  [OK] Bridge processes terminated"

echo "--- 3. Removing Systemd Service File ---"
rm -f /etc/systemd/system/enerex-ups-bridge.service
echo "  [OK] Removed /etc/systemd/system/enerex-ups-bridge.service"

echo "--- 4. Removing Deployed Code Folder ---"
if [ -d "/opt/enerex-ups" ]; then
    rm -rf /opt/enerex-ups
    echo "  [OK] Removed /opt/enerex-ups directory"
fi

echo "--- 5. Removing Driver Symlink ---"
if [ -L "/lib/nut/enerex" ] || [ -f "/lib/nut/enerex" ]; then
    rm -f /lib/nut/enerex
    echo "  [OK] Removed /lib/nut/enerex symlink"
fi

echo "--- 5.5 Removing upscmd Wrapper and enerex-test CLI ---"
rm -f /usr/local/bin/upscmd
rm -f /usr/local/bin/enerex-test
if [ -f "/usr/bin/upscmd.orig" ]; then
    mv -f /usr/bin/upscmd.orig /usr/bin/upscmd
    echo "  [OK] Restored original /usr/bin/upscmd"
else
    # If upscmd in /usr/bin was our wrapper script, remove it
    if [ -f "/usr/bin/upscmd" ] && grep -q "enerex_ups_cmd" /usr/bin/upscmd 2>/dev/null; then
        rm -f /usr/bin/upscmd
    fi
fi
echo "  [OK] Removed /usr/local/bin/upscmd and /usr/local/bin/enerex-test"

echo "--- 6. Cleaning State, IPC and Lock Files ---"
rm -f /etc/nut/myups.dev
rm -f /etc/nut/myups.dev.tmp
rm -f /run/enerex_ups_cmd
rm -f /tmp/enerex_ups_cmd
rm -f /run/enerex_ups_bridge.lock
rm -f /tmp/enerex_ups_bridge.lock
echo "  [OK] State, IPC and lock files removed"

echo "--- 7. Reverting nut-driver.service patch (if applied) ---"
if [ -f "/lib/systemd/system/nut-driver.service" ]; then
    sed -i 's/ExecStart=-\/sbin\/upsdrvctl start/ExecStart=\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
    echo "  [OK] Reverted nut-driver.service"
fi

echo "--- 8. Reloading Systemd Daemon ---"
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# Check if user wants to remove installed system packages
echo ""
read -r -p "Do you also want to remove installed packages (python3-hid, python3-usb)? [y/N]: " REMOVE_PKGS
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
echo " Uninstallation & Cleanup Complete!"
echo " All files installed by install.sh have been removed."
echo "=========================================================="
