#!/usr/bin/env bash
#
# uninstall.sh - Remove Linux Virtual Display Driver.
#
set -e

APP_NAME="linux-vdd"
INSTALL_DIR="/opt/${APP_NAME}"
BIN_LINK="/usr/local/bin/${APP_NAME}"
DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"

echo "=== Uninstalling Linux Virtual Display Driver ==="

sudo rm -rf "${INSTALL_DIR}"
sudo rm -f "${BIN_LINK}"
sudo rm -f "${DESKTOP_FILE}"
sudo update-desktop-database /usr/share/applications/ 2>/dev/null || true

echo "Removed.  Config is preserved at ~/.config/linux-vdd/"
echo "To remove config as well:  rm -rf ~/.config/linux-vdd/"
