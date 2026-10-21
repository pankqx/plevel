#!/usr/bin/env bash
# One-time setup for Ubuntu: virtualenv, dependencies, and an app-menu launcher.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if ! command -v python3 >/dev/null; then
    echo "python3 not found. Run: sudo apt install python3 python3-venv" >&2
    exit 1
fi

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
    echo "python3-venv is missing. Run: sudo apt install python3-venv" >&2
    exit 1
fi

echo "==> Creating virtual environment (.venv)"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Qt's xcb plugin needs this library on Ubuntu 22.04/24.04
if ! ldconfig -p | grep -q libxcb-cursor; then
    echo
    echo "NOTE: Qt needs libxcb-cursor0. Install it with:"
    echo "      sudo apt install libxcb-cursor0"
fi

echo "==> Adding Plevel to your application menu"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/share/icons"
cp assets/plevel.svg "$HOME/.local/share/icons/plevel.svg"
cat > "$HOME/.local/share/applications/plevel.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Plevel
Comment=Chat with your local Ollama models
Exec=$DIR/run.sh
Icon=$HOME/.local/share/icons/plevel.svg
Terminal=false
Categories=Development;Utility;
StartupWMClass=plevel
EOF
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

echo
echo "Done. Start it with ./run.sh or search for 'Plevel' in the Activities menu."
