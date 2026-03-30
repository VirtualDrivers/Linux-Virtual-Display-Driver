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
- **Multi-GPU support** — NVIDIA, AMD, and Intel

## GPU Support

| GPU | Method | Setup Required |
|-----|--------|----------------|
| **AMD** | xrandr (direct) | None — works out of the box |
| **Intel** | xrandr (direct) | None — works out of the box |
| **NVIDIA** | xorg.conf + xrandr | One-time setup + session restart |

### NVIDIA

NVIDIA's proprietary driver does not allow adding modes to disconnected outputs at runtime. The app handles this automatically:

1. Click **Setup Now** (or Menu > Setup Virtual Outputs)
2. Select which NVIDIA outputs to enable as virtual displays (e.g., `HDMI-0`)
3. Enter your password — the app writes:
   - `/etc/X11/xorg.conf.d/99-linux-vdd.conf` — forces NVIDIA to treat the output as connected
   - `/usr/share/linux-vdd/virtual-edid.bin` — virtual EDID supporting 24–240 Hz up to 4K
4. **Log out and back in** for the configuration to take effect
5. After restart, create virtual displays at any resolution/refresh rate instantly

To remove the NVIDIA config: Menu > Remove NVIDIA Config, then restart your session.

### AMD / Intel

These work immediately with no setup. The app uses standard xrandr to create modes and enable disconnected outputs directly.

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

This installs the app to `/opt/linux-vdd/`, adds a launcher to your PATH, and creates a `.desktop` entry so it appears in your application menu. Supports **apt**, **pacman**, **dnf**, and **zypper**.

To uninstall:

```bash
chmod +x uninstall.sh
sudo ./uninstall.sh
```

## How It Works

The app uses **xrandr** to:

1. **Generate a CVT modeline** for your chosen resolution and refresh rate (pure Python — no dependency on the `cvt` binary)
2. **Create the mode** in the X server (`xrandr --newmode`)
3. **Add the mode** to an available output (`xrandr --addmode`)
4. **Enable the output** with positioning (`xrandr --output ... --mode ...`)

Virtual displays are created on **disconnected outputs** — most GPU drivers expose one or more of these (e.g., `VIRTUAL1`, `DP-2`, `HDMI-2`).

## Troubleshooting

### No available outputs

If the app reports no available outputs:

- **NVIDIA** — Use the built-in Setup Virtual Outputs flow (see [NVIDIA](#nvidia) above)
- **Intel** — Check for `VIRTUAL1` / `VIRTUAL2` outputs in `xrandr`
- **AMD** — Disconnected HDMI/DP outputs should appear automatically
- **Any GPU** — Install `xf86-video-dummy` for a dummy output, or load the `evdi` kernel module (`sudo modprobe evdi`)

### Display not appearing after creation

- Verify the output is listed in `xrandr` output
- For NVIDIA: ensure you completed the setup flow and restarted your session
- Check `~/.config/linux-vdd/displays.json` for saved state

## Configuration

Virtual display state is saved to `~/.config/linux-vdd/displays.json` and restored on next launch.

NVIDIA xorg configuration is stored in `/etc/X11/xorg.conf.d/99-linux-vdd.conf`.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | Add virtual display |

## Project Structure

```
linux_vdd/
  __init__.py          # Package metadata
  modeline.py          # CVT modeline calculator
  display_manager.py   # GPU detection, xrandr backend, NVIDIA setup
  dialogs.py           # Add Display + NVIDIA Setup dialogs
  app.py               # GTK3 Application, main window, CSS
vdd.py                 # Entry point
install.sh             # System-wide installer
uninstall.sh           # Uninstaller
```

## License

**Personal / Non-Commercial Use:** [GNU GPLv3](https://www.gnu.org/licenses/gpl-3.0.html) — free to use, modify, and redistribute.

**Commercial Use:** Requires a separate license. Contact [VirtualDrivers](https://github.com/VirtualDrivers) for commercial licensing.

See [LICENSE](LICENSE) for full details.
