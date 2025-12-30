#!/bin/bash
set -e

# macOS Automation Setup Script
BASE_DIR=$(pwd)
PYTHON_ENV="$BASE_DIR/python_env"

echo "=== Subtitle Translator Setup (macOS) ==="

# 1. Check Homebrew
if ! command -v brew &> /dev/null; then
    echo "Notice: Homebrew not detected. Please install Homebrew first: https://brew.sh/"
    exit 1
fi

# 2. Install Python 3.10 and necessary system libraries
echo "Step 1: Installing Python 3.10 and MKVToolNix..."
brew install python@3.10 mkvtoolnix ffmpeg

# 3. Create virtual environment
PYTHON_BIN=$(brew --prefix)/bin/python3.10
if [ ! -d "$PYTHON_ENV" ]; then
    echo "Step 2: Creating virtual environment..."
    "$PYTHON_BIN" -m venv "$PYTHON_ENV"
fi

# Activate environment
source "$PYTHON_ENV/bin/activate"

# 4. Install dependencies
echo "Step 3: Installing project Python dependencies..."
pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install -r subtitle/requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 5. Configuration file
if [ ! -f "subtitle/.env" ]; then
    cp subtitle/.env.example subtitle/.env
    echo "Created subtitle/.env, please fill in your API key."
fi

echo "======================================================="
echo "Deployment Completed! Run './start_gui.sh' to start."
echo "======================================================="
