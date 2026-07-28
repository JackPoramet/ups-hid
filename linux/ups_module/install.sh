#!/usr/bin/env bash
set -e

if [ "$(uname)" != "Linux" ]; then
    echo "Error: Linux only"
    exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")"

echo "Installing system dependencies..."
if command -v apt-get &> /dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y pkg-config build-essential python3-dev libhidapi-hidraw0 libhidapi-dev libusb-1.0-0 > /dev/null
fi

echo "Installing Python dependencies..."
PYTHON_BIN="python3"
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
fi
"$PYTHON_BIN" -m pip install -r requirements.txt -q

echo "Setting up udev rules..."
sudo env "PATH=$PATH" "$PYTHON_BIN" linux_setup.py

if command -v udevadm &> /dev/null; then
    sudo udevadm control --reload-rules && sudo udevadm trigger
fi

echo "Done! Test with: python3 demo.py"
