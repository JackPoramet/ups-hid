#!/usr/bin/env bash
# uninstall.sh — ถอนการติดตั้ง ups_module dependencies
# ย้อนกลับสิ่งที่ install.sh ทำ:
#   1. ลบ Python packages (hidapi, pyusb)
#   2. ลบ udev rule
#   3. Reload udev
#
# Usage:
#   sudo bash uninstall.sh          # ถอนการติดตั้ง (ถามยืนยันทีละขั้น)
#   sudo bash uninstall.sh --yes    # ถอนการติดตั้งโดยไม่ถาม

set -e

if [ "$(uname)" != "Linux" ]; then
    echo "Error: Linux only"
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
AUTO_YES=false
for arg in "$@"; do
    case "$arg" in
        -y|--yes) AUTO_YES=true ;;
    esac
done

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

# ---------------------------------------------------------------------------
# ค่าคงที่
# ---------------------------------------------------------------------------
UDEV_RULE="/etc/udev/rules.d/99-ups-hid.rules"
PYTHON_BIN="python3"
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi

echo ""
echo "=== ups_module uninstaller ==="
echo ""

# ---------------------------------------------------------------------------
# 1. ลบ Python packages
# ---------------------------------------------------------------------------
echo "--- Python Packages ---"

# อ่านรายชื่อ package จาก requirements.txt
PACKAGES=()
if [ -f "requirements.txt" ]; then
    while IFS= read -r line; do
        # ข้ามบรรทัดว่างและ comment
        line="$(echo "$line" | sed 's/#.*//' | xargs)"
        [ -z "$line" ] && continue
        # ดึงเฉพาะชื่อ package (ตัดตัว specifier เช่น >=1.0 ออก)
        pkg="$(echo "$line" | sed 's/[><=!].*//' | xargs)"
        [ -n "$pkg" ] && PACKAGES+=("$pkg")
    done < requirements.txt
fi

if [ ${#PACKAGES[@]} -eq 0 ]; then
    echo "  ไม่พบ requirements.txt หรือไม่มี package ที่ต้องลบ"
else
    echo "  จะลบ packages: ${PACKAGES[*]}"
    if confirm "ลบ Python packages?"; then
        "$PYTHON_BIN" -m pip uninstall -y "${PACKAGES[@]}" 2>/dev/null || true
        echo "  [OK] ลบ Python packages แล้ว"
    else
        echo "  [SKIP] ข้ามการลบ Python packages"
    fi
fi

# ---------------------------------------------------------------------------
# 2. ลบ udev rule
# ---------------------------------------------------------------------------
echo ""
echo "--- udev Rule ---"

if [ -f "$UDEV_RULE" ]; then
    echo "  พบ udev rule: $UDEV_RULE"
    if confirm "ลบ udev rule?"; then
        if [ "$(id -u)" -ne 0 ]; then
            echo "  [NG] ต้องรันด้วย sudo เพื่อลบ udev rule"
        else
            rm -f "$UDEV_RULE"
            echo "  [OK] ลบ udev rule แล้ว"

            # Reload udev
            if command -v udevadm &> /dev/null; then
                udevadm control --reload-rules && udevadm trigger
                echo "  [OK] Reload udev rules แล้ว"
            fi
        fi
    else
        echo "  [SKIP] ข้ามการลบ udev rule"
    fi
else
    echo "  [OK] ไม่พบ udev rule (ไม่ต้องลบ)"
fi

# ---------------------------------------------------------------------------
# สรุป
# ---------------------------------------------------------------------------
echo ""
echo "--- สรุป ---"
echo "  ถอนการติดตั้งเสร็จสิ้น"
echo ""
echo "  หมายเหตุ: system packages (libhidapi-hidraw0, libusb-1.0-0, ฯลฯ)"
echo "  ไม่ถูกลบ เพราะอาจมีโปรแกรมอื่นใช้งานอยู่"
echo "  หากต้องการลบด้วยตนเอง:"
echo "    sudo apt remove -y libhidapi-hidraw0 libhidapi-dev libusb-1.0-0-dev"
echo ""
