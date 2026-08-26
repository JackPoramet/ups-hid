#!/bin/bash

# =============================================================================
# Universal UPS Bridge & ERX Services Uninstaller for Linux
# =============================================================================
# This script completely stops, disables, and removes:
#   1. Enerex UPS Bridge (/opt/enerex-ups, enerex-ups-bridge.service)
#   2. ERX Services (/etc/erx/.service/*: ups-alert, ups-command, ups-service, ups-backup)
#   3. Associated Systemd Unit Files in /etc/systemd/system/
#   4. NUT driver symlinks and temporary cache/lock files
#   5. Lingering/orphaned Python processes eating 100% CPU
# =============================================================================

set -e

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: Please run as root (sudo ./uninstall.sh)"
  exit 1
fi

echo "=========================================================="
echo " Starting Complete UPS & ERX Services Uninstallation..."
echo "=========================================================="

echo "--- 1. Stopping and Disabling All UPS & ERX Services ---"
# Stop and disable known service names
SERVICES=(
    "enerex-ups-bridge.service"
    "ups-alert.service"
    "ups-command.service"
    "ups-service.service"
    "ups-backup.service"
    "erx-service.service"
    "erx-ups.service"
    "nut-server.service"
    "nut-driver.service"
)

for svc in "${SERVICES[@]}"; do
    if systemctl list-unit-files "$svc" &>/dev/null || [ -f "/etc/systemd/system/$svc" ] || [ -f "/lib/systemd/system/$svc" ]; then
        echo "  Stopping and disabling $svc..."
        systemctl stop "$svc" 2>/dev/null || true
        systemctl disable "$svc" 2>/dev/null || true
    fi
done

# Find and stop ANY systemd service that runs scripts in /etc/erx/ or /opt/enerex-ups/
if [ -d "/etc/systemd/system" ]; then
    for sfile in $(grep -lE "(/etc/erx/|/opt/enerex-ups/|ups-alert|ups-command|ups-service|ups-backup)" /etc/systemd/system/*.service 2>/dev/null || true); do
        bname=$(basename "$sfile")
        echo "  Found custom service: $bname -> Stopping & Disabling..."
        systemctl stop "$bname" 2>/dev/null || true
        systemctl disable "$bname" 2>/dev/null || true
        rm -f "$sfile"
        echo "  [OK] Removed service unit: $sfile"
    done
fi

echo "--- 2. Force-Killing All Lingering Python & Bridge Processes ---"
pkill -9 -f "enerex_ups_bridge.py" 2>/dev/null || true
pkill -9 -f "/etc/erx/.service/" 2>/dev/null || true
pkill -9 -f "ups-backup.py" 2>/dev/null || true
pkill -9 -f "ups-alert.py" 2>/dev/null || true
pkill -9 -f "ups-service.py" 2>/dev/null || true
pkill -9 -f "ups-command.py" 2>/dev/null || true
echo "  [OK] All high-CPU and background processes terminated"

echo "--- 3. Removing Systemd Service Files ---"
rm -f /etc/systemd/system/enerex-ups-bridge.service
rm -f /etc/systemd/system/ups-alert.service
rm -f /etc/systemd/system/ups-command.service
rm -f /etc/systemd/system/ups-service.service
rm -f /etc/systemd/system/ups-backup.service
rm -f /etc/systemd/system/erx-*.service
echo "  [OK] Removed UPS service units"

echo "--- 4. Removing Deployed Code & Bridge Folders ---"
if [ -d "/opt/enerex-ups" ]; then
    rm -rf /opt/enerex-ups
    echo "  [OK] Removed /opt/enerex-ups directory"
fi

echo "--- 5. Removing Driver Symlink ---"
if [ -L "/lib/nut/enerex" ] || [ -f "/lib/nut/enerex" ]; then
    rm -f /lib/nut/enerex
    echo "  [OK] Removed /lib/nut/enerex symlink"
fi

echo "--- 6. Cleaning State, Lock, and Temporary Files ---"
rm -f /etc/nut/myups.dev
rm -f /etc/nut/myups.dev.tmp
rm -f /run/enerex_ups_bridge.lock
rm -f /tmp/enerex_ups_bridge.lock
rm -f /run/ups-*.lock
rm -f /tmp/ups-*.lock
echo "  [OK] State and lock files removed"

echo "--- 7. Reverting nut-driver.service patch (if applied) ---"
if [ -f "/lib/systemd/system/nut-driver.service" ]; then
    sed -i 's/ExecStart=-\/sbin\/upsdrvctl start/ExecStart=\/sbin\/upsdrvctl start/' /lib/systemd/system/nut-driver.service
    echo "  [OK] Reverted nut-driver.service"
fi

echo "--- 8. Reloading Systemd Daemon ---"
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

# Optional cleanup for /etc/erx/.service/ files
if [ -d "/etc/erx/.service" ]; then
    echo ""
    read -r -p "Do you also want to delete /etc/erx/.service/ files? [y/N]: " REMOVE_ERX
    case "$REMOVE_ERX" in
        [yY][eE][sS]|[yY])
            rm -rf /etc/erx/.service
            echo "  [OK] Removed /etc/erx/.service/"
            ;;
        *)
            echo "  [SKIP] Kept /etc/erx/.service/ files"
            ;;
    esac
fi

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
echo " Uninstallation & Cleanup Complete!"
echo " All services stopped, disabled, and CPU returned to 0%."
echo "=========================================================="
