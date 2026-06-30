#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== DendrOS Windows Build ==="

# Path to the iiPythonx Dockerfile repo
BUILDER_DIR="${BUILDER_DIR:-/tmp/iiPythonx}"

# Check if the Docker image exists
if ! docker image inspect iipython-pyinstaller &>/dev/null; then
    if [ -d "$BUILDER_DIR" ]; then
        echo "Building Docker image (one-time, ~2 min)..."
        docker build -t iipython-pyinstaller "$BUILDER_DIR"
    else
        echo "Error: Builder directory $BUILDER_DIR not found."
        echo "Clone it first: git clone https://github.com/iiPythonx/pyinstaller-windows $BUILDER_DIR"
        exit 1
    fi
fi

mkdir -p dist

# Run PyInstaller inside Wine via Docker
docker run --rm \
  --entrypoint bash \
  -v "$SCRIPT_DIR:/src" \
  iipython-pyinstaller \
  -c '
set -e
cd /src
echo "=== Installing dependencies ==="
pip install -r requirements.txt 2>&1 | tail -3
echo ""
echo "=== Running PyInstaller ==="
pyinstaller --clean -y \
  --dist dist/windows \
  --workpath C:\\src\\build \
  --upx-dir C:\\ \
  dendros.spec 2>&1
echo ""
echo "=== Build complete ==="
ls -lh dist/windows/
'

echo ""
echo "Windows executable: dist/windows/DendrOS.exe"
