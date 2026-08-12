#!/usr/bin/env bash
# =============================================================================
# install.sh — UPS HID Module Installer (Linux)
# =============================================================================
#
# Installs all required system libraries, Python packages, and udev rules
# for the ups_module to communicate with UPS devices via USB HID.
#
# Prerequisites:
#   - Linux (Debian/Ubuntu-based with apt)
#   - Root privileges (sudo)
#
# Usage:
#   sudo bash install.sh
#
# What this script does:
#   1. Install system libraries (libhidapi, libusb, build tools)
#   2. Install Python packages from requirements.txt (hidapi, pyusb)
#   3. Create udev rule for non-root USB HID access
#   4. Reload udev rules
#   5. Verify installation via linux_setup.py
#
# See also:
#   uninstall.sh  — Reverse the installation performed by this script
#   linux_setup.py --check  — Check system status without modifying anything
# =============================================================================

set -euo pipefail

# -- Platform guard -----------------------------------------------------------
if [ "$(uname)" != "Linux" ]; then
    echo "Error: This script is intended for Linux only."
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Error: Run this installer as root, for example: sudo ./install.sh"
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

# -- Source compatibility guard -----------------------------------------------
# install.sh installs dependencies and udev rules; it does not copy Python
# source files between machines.  Fail early when an older source tree is
# being installed, otherwise the old one-interface opener can still produce
# the unhelpful "OSError: open failed" traceback.
if ! grep -Fq '_ordered_device_candidates' core.py || \
    ! grep -Fq 'GROUP="ups-hid"' linux_setup.py; then
    echo "Error: ups_module source tree is outdated."
    echo "Please copy the current linux/ups_module directory, including:"
    echo "  core.py, client.py, linux_setup.py, install.sh"
    echo "Then run this installer again."
    exit 1
fi

# ``uaccess`` is not sufficient for SSH/headless services. Assign the account
# that will execute demo.py/the application to the least-privilege ups-hid
# group. Allow an explicit override for installers run through su/root.
TARGET_USER="${UPS_HID_USER:-${SUDO_USER:-}}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
    echo "Error: Cannot determine the non-root application user."
    echo "Run: sudo UPS_HID_USER=<your-user> ./install.sh"
    exit 1
fi
if ! id "$TARGET_USER" >/dev/null 2>&1; then
    echo "Error: User '$TARGET_USER' does not exist."
    exit 1
fi

# -- Step 1: System libraries -------------------------------------------------
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    apt-get update -qq
    apt-get install -y \
        pkg-config \
        build-essential \
        python3-dev \
        libudev-dev \
        libhidapi-hidraw0 \
        libhidapi-dev \
        libusb-1.0-0-dev
fi

# -- Step 2: Python packages --------------------------------------------------
echo "Installing Python dependencies..."
PYTHON_BIN="python3"
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi
"$PYTHON_BIN" -m pip install -r requirements.txt -q

# -- Step 3–5: udev rule, reload, and verification ----------------------------
echo "Setting up udev rules..."
"$PYTHON_BIN" linux_setup.py --user "$TARGET_USER"

if command -v udevadm &> /dev/null; then
    udevadm control --reload-rules
    udevadm trigger --subsystem-match=hidraw --action=change
    udevadm settle --timeout=10 || true
fi

echo ""
echo "Rules installed for user '$TARGET_USER' through group 'ups-hid'."
echo "Start a new login session (or restart the service) before testing."
echo "If the current hidraw node retains old permissions, unplug/replug the UPS."
echo "Test as the application user: sudo -u $TARGET_USER $PYTHON_BIN demo.py --mode oneshot"
