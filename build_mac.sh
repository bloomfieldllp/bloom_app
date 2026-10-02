#!/bin/bash
set -e

echo "=== Building Bloom Operator for macOS ==="

# Check Python environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "test_venv" ]; then
    source test_venv/bin/activate
fi

# Install requirements if pyinstaller is missing
if ! command -v pyinstaller &> /dev/null; then
    echo "Installing requirements..."
    pip install -r requirements.txt
    pip install pyinstaller pywebview pyobjc
fi

export PYINSTALLER_CONFIG_DIR="$(pwd)/build/pyi_config"

echo "Running PyInstaller with BloomOperator_Mac.spec..."
pyinstaller -y --workpath ./build/pyi_work BloomOperator_Mac.spec

echo "=== Build Complete! ==="
echo "Mac App Bundle created at: dist/BloomOperator.app"
echo "Mac Executable created at: dist/BloomOperator/BloomOperator"
