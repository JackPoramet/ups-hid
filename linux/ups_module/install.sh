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

set -e

# -- Platform guard -----------------------------------------------------------
if [ "$(uname)" != "Linux" ]; then
    echo "Error: This script is intended for Linux only."
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

# -- Source compatibility guard -----------------------------------------------
# install.sh installs dependencies and udev rules; it does not copy Python
# source files between machines.  Fail early when an older source tree is
# being installed, otherwise the old one-interface opener can still produce
# the unhelpful "OSError: open failed" traceback.
if ! grep -Fq '_ordered_device_candidates' core.py || \
   ! grep -Fq 'TAG+="uaccess"' linux_setup.py; then
    echo "Error: ups_module source tree is outdated."
    echo "Please copy the current linux/ups_module directory, including:"
    echo "  core.py, client.py, linux_setup.py, install.sh"
    echo "Then run this installer again."
    exit 1
fi

# -- Step 1: System libraries -------------------------------------------------
echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y \
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
sudo env "PATH=$PATH" "$PYTHON_BIN" linux_setup.py

if command -v udevadm &> /dev/null; then
    sudo udevadm control --reload-rules && sudo udevadm trigger
fi

echo "Done! Test with: python3 demo.py"
