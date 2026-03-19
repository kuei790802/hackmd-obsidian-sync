#!/bin/bash
# HackMD-Obsidian Sync — Quick Setup
set -e

echo "=== HackMD-Obsidian Sync Setup ==="
echo

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3 is required. Install it first."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python: $PYTHON_VERSION"

# Install PyYAML
if ! python3 -c "import yaml" &>/dev/null; then
    echo "Installing PyYAML..."
    pip3 install pyyaml -q
fi
echo "PyYAML: OK"
echo

# Run interactive setup
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
python3 -m hackmd_sync setup
