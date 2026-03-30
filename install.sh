#!/usr/bin/env bash
#
# install.sh - Install Linux Virtual Display Driver and its dependencies.
#
set -e

APP_NAME="linux-vdd"
INSTALL_DIR="/opt/${APP_NAME}"
BIN_LINK="/usr/local/bin/${APP_NAME}"
DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"

echo "=== Linux Virtual Display Driver - Installer ==="
echo

# ---------- Detect package manager ----------
install_pkg() {
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y "$@"
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm "$@"
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y "$@"
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y "$@"
    else
        echo "ERROR: Could not detect package manager."
        echo "Please install the following manually: $*"
        exit 1
    fi
}

# ---------- Install system dependencies ----------
echo "[1/4] Checking dependencies..."

MISSING=()

# Python 3
if ! command -v python3 &>/dev/null; then
    MISSING+=(python3)
fi

# PyGObject (GTK3 bindings)
if ! python3 -c "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk" &>/dev/null 2>&1; then
    # Package names differ by distro
    if command -v apt-get &>/dev/null; then
        MISSING+=(python3-gi gir1.2-gtk-3.0)
    elif command -v pacman &>/dev/null; then
        MISSING+=(python-gobject gtk3)
    elif command -v dnf &>/dev/null; then
        MISSING+=(python3-gobject gtk3)
    elif command -v zypper &>/dev/null; then
        MISSING+=(python3-gobject typelib-1_0-Gtk-3_0)
    fi
fi

# xrandr
if ! command -v xrandr &>/dev/null; then
    if command -v apt-get &>/dev/null; then
        MISSING+=(x11-xserver-utils)
    elif command -v pacman &>/dev/null; then
        MISSING+=(xorg-xrandr)
    elif command -v dnf &>/dev/null; then
        MISSING+=(xrandr)
    elif command -v zypper &>/dev/null; then
        MISSING+=(xrandr)
    fi
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "  Installing: ${MISSING[*]}"
    install_pkg "${MISSING[@]}"
else
    echo "  All dependencies satisfied."
fi

# ---------- Install application ----------
echo "[2/4] Installing application to ${INSTALL_DIR}..."
sudo mkdir -p "${INSTALL_DIR}"
sudo cp -r linux_vdd "${INSTALL_DIR}/"
sudo cp vdd.py "${INSTALL_DIR}/"
sudo chmod +x "${INSTALL_DIR}/vdd.py"

# ---------- Create symlink ----------
echo "[3/4] Creating launcher..."
sudo ln -sf "${INSTALL_DIR}/vdd.py" "${BIN_LINK}"

# ---------- Desktop file ----------
echo "[4/4] Installing desktop entry..."
sudo tee "${DESKTOP_FILE}" > /dev/null << EOF
[Desktop Entry]
Type=Application
Name=Virtual Display Driver
Comment=Create and manage virtual displays on Linux
Exec=${INSTALL_DIR}/vdd.py
Icon=video-display
Terminal=false
Categories=System;Settings;HardwareSettings;
Keywords=display;monitor;virtual;screen;xrandr;
StartupNotify=true
EOF

sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo
echo "=== Installation complete ==="
echo "  Launch from your app menu, or run:  ${APP_NAME}"
echo
