#!/usr/bin/env bash
#
# create_virtual_display.sh
#
# A script to create and manage a virtual X display in Linux using Xvfb.

# Exit on any error
set -e

# The display number you want to use (e.g., :99)
DISPLAY_NUM=71

# Desired screen resolution and color depth (e.g., 1280x1024x24)
SCREEN_RES=1920x1080

# Check if Xvfb is installed; if not, install it.
if ! command -v Xvfb &> /dev/null
then
    echo "Xvfb not found. Installing..."
    # For Debian/Ubuntu-based systems:
    sudo apt-get update
    sudo apt-get install -y xvfb
    
    # For other distros, replace above with the appropriate package manager command.
fi

# Check if there's already an X server running on the display.
if pgrep -f "Xvfb :${DISPLAY_NUM}" > /dev/null
then
    echo "Xvfb is already running on :${DISPLAY_NUM}."
else
    # Start Xvfb in the background
    echo "Starting Xvfb on :${DISPLAY_NUM} with screen ${SCREEN_RES}..."
    Xvfb ":${DISPLAY_NUM}" -screen 0 "${SCREEN_RES}" -ac -nolisten tcp &
    # Wait a moment to ensure the X server has started
    sleep 2
fi

# Export the DISPLAY variable so that GUI apps know where to render.
export DISPLAY=":${DISPLAY_NUM}"

echo "Virtual display is running on DISPLAY=${DISPLAY}"
echo "You can now run graphical applications in headless mode."
