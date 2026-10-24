#!/usr/bin/env bash
# =============================================================================
# uninstall.sh — UPS HID Module Uninstaller (Linux)
# =============================================================================
#
# Reverses the installation performed by install.sh:
#   1. Remove Python packages listed in requirements.txt (hidapi, pyusb)
#   2. Remove the udev rule (/etc/udev/rules.d/99-ups-hid.rules)
#   3. Reload udev rules
#
# The ups-hid group is retained because it may be shared by other
# installations or service accounts.
#
# Note:
#   System libraries (libhidapi-hidraw0, libusb, build-essential, etc.)
#   are NOT removed, as they may be shared with other applications.
#   Instructions for manual removal are printed at the end.
#
# Prerequisites:
#   - Root privileges (sudo) for udev rule removal
#
# Usage:
#   sudo bash uninstall.sh          # Interactive — confirm each step
#   sudo bash uninstall.sh --yes    # Non-interactive — skip all prompts
#
# See also:
#   install.sh     — Install all dependencies and configure the system
#   linux_setup.py --check  — Check system status without modifying anything
# =============================================================================

set -e

# -- Platform guard -----------------------------------------------------------
if [ "$(uname)" != "Linux" ]; then
    echo "Error: This script is intended for Linux only."
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

# =============================================================================
# Argument parsing
# =============================================================================
AUTO_YES=false
for arg in "$@"; do
    case "$arg" in
        -y|--yes) AUTO_YES=true ;;
    esac
done

# Prompt the user for confirmation. Returns 0 (yes) or 1 (no).
# Automatically returns 0 when --yes flag is set.
confirm() {
    if [ "$AUTO_YES" = true ]; then
        return 0
    fi
    read -r -p "  $1 [y/N]: " response
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

# =============================================================================
# Constants
# =============================================================================
UDEV_RULE="/etc/udev/rules.d/99-ups-hid.rules"
PYTHON_BIN="python3"
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi

echo ""
echo "=== ups_module uninstaller ==="
echo ""

# =============================================================================
# Step 1: Remove Python packages
# =============================================================================
echo "--- Python Packages ---"

# Parse package names from requirements.txt (strips comments and version specifiers)
PACKAGES=()
if [ -f "requirements.txt" ]; then
    while IFS= read -r line; do
        line="$(echo "$line" | sed 's/#.*//' | xargs)"
        [ -z "$line" ] && continue
        pkg="$(echo "$line" | sed 's/[><=!].*//' | xargs)"
        [ -n "$pkg" ] && PACKAGES+=("$pkg")
    done < requirements.txt
fi

if [ ${#PACKAGES[@]} -eq 0 ]; then
    echo "  No packages found in requirements.txt — nothing to remove."
else
    echo "  Packages to remove: ${PACKAGES[*]}"
    if confirm "Remove Python packages?"; then
        "$PYTHON_BIN" -m pip uninstall -y "${PACKAGES[@]}" 2>/dev/null || true
        echo "  [OK] Python packages removed."
    else
        echo "  [SKIP] Skipped Python package removal."
    fi
fi

# =============================================================================
# Step 2: Remove udev rule
# =============================================================================
echo ""
echo "--- udev Rule ---"

if [ -f "$UDEV_RULE" ]; then
    echo "  Found udev rule: $UDEV_RULE"
    if confirm "Remove udev rule?"; then
        if [ "$(id -u)" -ne 0 ]; then
            echo "  [NG] Root privileges required. Please run with sudo."
        else
            rm -f "$UDEV_RULE"
            echo "  [OK] udev rule removed."

            # Reload udev to apply changes immediately
            if command -v udevadm &> /dev/null; then
                udevadm control --reload-rules && udevadm trigger
                echo "  [OK] udev rules reloaded."
            fi
        fi
    else
        echo "  [SKIP] Skipped udev rule removal."
    fi
else
    echo "  [OK] No udev rule found — nothing to remove."
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "--- Summary ---"
echo "  Uninstallation complete."
echo ""
echo "  Note: System libraries (libhidapi-hidraw0, libusb-1.0-0, etc.)"
echo "  were intentionally kept, as they may be used by other applications."
echo "  The ups-hid group was also retained. Remove it manually only after"
echo "  confirming that no other UPS HID service account uses it."
echo "  To remove them manually:"
echo "    sudo apt remove -y libhidapi-hidraw0 libhidapi-dev libusb-1.0-0-dev"
echo ""
