# Linux Virtual Display Driver

A native Linux GUI application to create and manage virtual displays at any resolution and refresh rate.

Built with GTK3 and xrandr. Works with **VR, OBS, Sunshine**, and any desktop sharing software.

Part of the [VirtualDrivers](https://github.com/VirtualDrivers) project.

---

## Features

- **Create virtual displays** at any resolution and refresh rate
- **Remove virtual displays** individually or all at once
- **Resolution presets** — Full HD, QHD, 4K, Ultrawide, and more, or enter a custom resolution
- **Refresh rate presets** — 30 / 60 / 75 / 90 / 120 / 144 / 165 / 240 Hz, or enter a custom value
- **Automatic output detection** — finds available xrandr outputs
- **Flexible positioning** — place virtual displays left, right, above, below, or mirror an existing monitor
- **Reduced blanking** — optional CVT reduced blanking for lower bandwidth
- **Persistent config** — remembers your virtual displays across sessions
- **Native GTK3 GUI** — follows your system theme

## Requirements

- **Linux** with **X11** (Xorg)
- **Python 3.8+**
- **PyGObject** (GTK3 bindings)
- **xrandr**

Most desktop Linux distributions already have these installed.

## Quick Start

```bash
git clone https://github.com/VirtualDrivers/Linux-Virtual-Display-Driver.git
cd Linux-Virtual-Display-Driver
python3 vdd.py
```

## Install (System-wide)

```bash
chmod +x install.sh
sudo ./install.sh
```

This installs the app to `/opt/linux-vdd/`, adds a launcher to your PATH, and creates a `.desktop` entry so it appears in your application menu.

To uninstall:

```bash
chmod +x uninstall.sh
sudo ./uninstall.sh
```

## How It Works

The app uses **xrandr** to:

1. **Generate a CVT modeline** for your chosen resolution and refresh rate
2. **Create the mode** in the X server (`xrandr --newmode`)
3. **Add the mode** to an available output (`xrandr --addmode`)
4. **Enable the output** with positioning (`xrandr --output ... --mode ...`)

Virtual displays are created on **disconnected outputs** — most GPU drivers expose one or more of these (e.g., `VIRTUAL1`, `DP-2`, `HDMI-2`).

### Troubleshooting: No Available Outputs

If the app reports no available outputs, your GPU driver may not expose disconnected outputs. Options:

- **Intel GPUs** often have `VIRTUAL1` / `VIRTUAL2` outputs
- **Install `xf86-video-dummy`** to create a dummy output
- **Load the `evdi` kernel module** (`sudo modprobe evdi`) for virtual display outputs

## Configuration

Virtual display state is saved to `~/.config/linux-vdd/displays.json` and restored on next launch.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Add virtual display |

## License

[MIT](LICENSE)
