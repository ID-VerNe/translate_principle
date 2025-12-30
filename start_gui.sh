#!/bin/bash
BASE_DIR=$(pwd)
PYTHON_ENV="$BASE_DIR/python_env"

if [ ! -d "$PYTHON_ENV" ]; then
    echo "Error: Virtual environment not found. Please run './setup_gui.sh' first."
    exit 1
fi

# Activate and run
source "$PYTHON_ENV/bin/activate"
echo "Starting Subtitle Translator GUI..."
python subtitle/main.py
