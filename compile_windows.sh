#!/bin/bash
# Script to compile Python code to Windows executable using Wine

SCRIPT_PATH="$1"
OUTPUT_DIR="$2"
OUTPUT_NAME="$3"

# Start Xvfb if not running
(Xvfb :99 -screen 0 1024x768x16 &) > /dev/null 2>&1
sleep 2

echo "Starting Windows compilation..."

# Download Python installer if needed
if [ ! -f /tmp/python-3.9.13-amd64.exe ]; then
    echo "Downloading Python installer..."
    wget -q -O /tmp/python-3.9.13-amd64.exe https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe
fi

# Install Python - will only run if needed
echo "Installing Python in Wine..."
timeout 180s DISPLAY=:99 WINEPREFIX=/home/user/.wine WINEDEBUG=-all wine /tmp/python-3.9.13-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 || true

# Common paths where Python might be installed in Wine
PYTHON_PATHS=(
    "C:\\users\\user\\AppData\\Local\\Programs\\Python\\Python39\\python.exe"
    "C:\\Python39\\python.exe"
    "C:\\windows\\py.exe"
)

# Try to find Python interpreter
PYTHON_PATH=""
for path in "${PYTHON_PATHS[@]}"; do
    if timeout 30s DISPLAY=:99 WINEPREFIX=/home/user/.wine WINEDEBUG=-all wine "$path" --version > /dev/null 2>&1; then
        PYTHON_PATH="$path"
        echo "Found working Python at: $PYTHON_PATH"
        break
    fi
done

if [ -z "$PYTHON_PATH" ]; then
    echo "Failed to find a working Python installation in Wine"
    exit 1
fi

# Install Nuitka in the Wine Python
echo "Installing Nuitka in Wine Python..."
timeout 180s DISPLAY=:99 WINEPREFIX=/home/user/.wine WINEDEBUG=-all wine "$PYTHON_PATH" -m pip install nuitka || true

# Run compilation
echo "Compiling with Nuitka..."
if timeout 300s DISPLAY=:99 WINEPREFIX=/home/user/.wine WINEDEBUG=-all wine "$PYTHON_PATH" -m nuitka \
    --mingw64 \
    --onefile \
    --standalone \
    --windows-icon-from-ico=/app/icon.ico \
    --show-progress \
    --output-dir="$OUTPUT_DIR" \
    --output-filename="$OUTPUT_NAME" \
    "$SCRIPT_PATH"; then
    
    # Check if compilation was successful
    if [ -f "$OUTPUT_DIR/$OUTPUT_NAME" ]; then
        echo "Windows compilation successful: $OUTPUT_DIR/$OUTPUT_NAME"
        exit 0
    fi
fi

echo "Windows compilation failed."
exit 1