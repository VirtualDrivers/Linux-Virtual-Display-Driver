"""
Display manager backend.

Handles GPU detection, NVIDIA xorg.conf setup, xrandr output parsing,
virtual display creation/removal, and config persistence.
"""

import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .modeline import generate_modeline


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Mode:
    width: int
    height: int
    refresh: float
    name: str
    current: bool = False
    preferred: bool = False


@dataclass
class Output:
    name: str
    connected: bool
    active: bool
    provider: str = ""          # "nvidia" or "modesetting" or ""
    modes: list = field(default_factory=list)
    current_mode: Optional[Mode] = None
    position_x: int = 0
    position_y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class VirtualDisplay:
    output: str
    mode_name: str
    width: int
    height: int
    refresh: float
    position: str = ""
    active: bool = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".config" / "linux-vdd"
CONFIG_FILE = CONFIG_DIR / "displays.json"
XORG_CONF_DIR = Path("/etc/X11/xorg.conf.d")
XORG_CONF_FILE = XORG_CONF_DIR / "99-linux-vdd.conf"
EDID_DIR = Path("/usr/share/linux-vdd")
EDID_FILE = EDID_DIR / "virtual-edid.bin"

# GDM monitors.xml paths (tried in order)
GDM_CONFIG_DIRS = [
    Path("/var/lib/gdm3/.config"),
    Path("/var/lib/gdm/.config"),
]


# ---------------------------------------------------------------------------
# Virtual EDID generation
# ---------------------------------------------------------------------------

def _generate_virtual_edid() -> bytes:
    """Generate a 128-byte EDID for a virtual display.

    Defines a virtual monitor named "VDD Virtual" that accepts
    a wide range of resolutions (up to 4K) and refresh rates (24-240 Hz).
    """
    edid = bytearray([
        # Header
        0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00,
        # Manufacturer "VDD" (V=22,D=4,D=4) encoded
        0x54, 0x63,
        # Product code 0x0001
        0x01, 0x00,
        # Serial number
        0x01, 0x00, 0x00, 0x00,
        # Manufacture week 1, year 2026 (36 = 2026-1990)
        0x01, 0x24,
        # EDID version 1.4
        0x01, 0x04,
        # Digital display, 8 bits/color, DisplayPort interface
        0xA5,
        # Horizontal screen size 53 cm, Vertical 30 cm
        0x35, 0x1E,
        # Gamma 2.20 (encoded as 120)
        0x78,
        # Features: RGB color, sRGB default, preferred timing in DTD1
        0xEA,
        # Color characteristics (standard sRGB chromaticity)
        0xD5, 0x55, 0xA6, 0x54, 0x4C, 0x9A, 0x26, 0x0F, 0x50, 0x54,
        # Established timings (640x480@60, 800x600@60, 1024x768@60)
        0x21, 0x08, 0x00,
        # Standard timings (8 entries)
        0xD1, 0xC0,     # 1920x1080 @ 60 Hz (16:9)
        0x81, 0xC0,     # 1280x720  @ 60 Hz (16:9)
        0xA9, 0xC0,     # 1600x900  @ 60 Hz (16:9)
        0xB3, 0x00,     # 1680x1050 @ 60 Hz (16:10)
        0x95, 0x00,     # 1440x900  @ 60 Hz (16:10)
        0x61, 0x40,     # 1024x768  @ 60 Hz (4:3)
        0x45, 0x40,     #  800x600  @ 60 Hz (4:3)
        0x01, 0x01,     # Unused
        # DTD 1: 1920x1080 @ 60.00 Hz (148.50 MHz pixel clock)
        #   H: 1920 active, 88 front, 44 sync, 148 back = 2200 total
        #   V: 1080 active,  4 front,  5 sync,  36 back = 1125 total
        0x02, 0x3A,     # Pixel clock 14850 * 10 kHz = 148.50 MHz (LE)
        0x80,           # H active lower 8: 1920 & 0xFF = 0x80
        0x18,           # H blanking lower 8: 280 & 0xFF = 0x18
        0x71,           # H active upper 4 | H blanking upper 4
        0x38,           # V active lower 8: 1080 & 0xFF = 0x38
        0x2D,           # V blanking lower 8: 45 & 0xFF = 0x2D
        0x40,           # V active upper 4 | V blanking upper 4
        0x58,           # H sync offset lower 8: 88
        0x2C,           # H sync width lower 8: 44
        0x45,           # V sync offset lower 4 (4) | V sync width lower 4 (5)
        0x00,           # Upper 2 bits of H/V sync offset/width
        0x35, 0x1E,     # H/V image size lower 8 (53cm, 30cm)
        0x00,           # H/V image size upper 4 bits
        0x00, 0x00,     # H/V border
        0x1E,           # Non-interlaced, digital separate, +H +V sync
        # Descriptor 2: Monitor name "VDD Virtual"
        0x00, 0x00, 0x00, 0xFC, 0x00,
        0x56, 0x44, 0x44, 0x20, 0x56, 0x69, 0x72, 0x74,
        0x75, 0x61, 0x6C, 0x0A, 0x20,
        # Descriptor 3: Monitor range limits (24-240 Hz V, 15-250 kHz H, 600 MHz max)
        0x00, 0x00, 0x00, 0xFD, 0x00,
        0x18,           # Min V rate: 24 Hz
        0xF0,           # Max V rate: 240 Hz
        0x0F,           # Min H rate: 15 kHz
        0xFA,           # Max H rate: 250 kHz
        0x3C,           # Max pixel clock: 600 MHz (/10)
        0x00, 0x0A, 0x20, 0x20, 0x20, 0x20, 0x20, 0x20,
        # Descriptor 4: Dummy
        0x00, 0x00, 0x00, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00,
        # Extension count
        0x00,
        # Checksum placeholder
        0x00,
    ])
    edid[127] = (256 - (sum(edid[:127]) % 256)) % 256
    return bytes(edid)


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def _load_config() -> list[dict]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_config(displays: list[VirtualDisplay]):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = [asdict(d) for d in displays]
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _xrandr(*args: str) -> subprocess.CompletedProcess:
    return _run(["xrandr"] + list(args))


def _pkexec_write_file(path: str, content: bytes | str, mode: str = "644"):
    """Write a file with root privileges using pkexec."""
    is_bytes = isinstance(content, bytes)

    with tempfile.NamedTemporaryFile(delete=False, mode="wb" if is_bytes else "w") as f:
        f.write(content)
        tmp = f.name

    try:
        parent = str(Path(path).parent)
        script = (
            f'mkdir -p "{parent}" && '
            f'cp "{tmp}" "{path}" && '
            f'chmod {mode} "{path}"'
        )
        result = _run(["pkexec", "bash", "-c", script], check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to write {path} (pkexec).\n"
                f"{result.stderr.strip()}"
            )
    finally:
        os.unlink(tmp)


def _pkexec_remove_file(path: str):
    """Remove a file with root privileges using pkexec."""
    result = _run(["pkexec", "rm", "-f", path], check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to remove {path}: {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# GDM monitors.xml management
# ---------------------------------------------------------------------------

def _find_gdm_config_dir() -> Optional[Path]:
    """Find the GDM config directory."""
    for d in GDM_CONFIG_DIRS:
        if d.exists():
            return d
    return None


def _get_real_monitor_info(primary_output: str) -> Optional[dict]:
    """Get monitor vendor/product/serial from xrandr verbose output."""
    try:
        result = _run(["xrandr", "--verbose"], check=False)
    except FileNotFoundError:
        return None

    current_output = None
    info: dict = {}
    for line in result.stdout.splitlines():
        m = _OUTPUT_RE.match(line)
        if m:
            if current_output == primary_output and info:
                return info
            current_output = m.group(1)
            info = {}
            continue
        if current_output != primary_output:
            continue
        # Parse EDID-derived info from verbose output
        line_stripped = line.strip()
        if line_stripped.startswith("Manufacturer:"):
            info["vendor"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("Model:"):
            # Model can be hex or name
            val = line_stripped.split(":", 1)[1].strip()
            info["product"] = val
        elif line_stripped.startswith("Serial Number:"):
            val = line_stripped.split(":", 1)[1].strip()
            info["serial"] = val

    # Check last output
    if current_output == primary_output and info:
        return info
    return None


def _read_user_monitors_xml() -> Optional[str]:
    """Read the current user's monitors.xml if it exists."""
    user_monitors = Path.home() / ".config" / "monitors.xml"
    if user_monitors.exists():
        try:
            return user_monitors.read_text()
        except OSError:
            pass
    return None


def _generate_gdm_monitors_xml(primary_output: str, virtual_outputs: list[str]) -> str:
    """Generate a monitors.xml for GDM that sets the real display as primary.

    The virtual outputs are configured as disabled so GDM only shows
    the login screen on the real physical display.
    """
    # Try to read the user's current monitors.xml first - it has the correct
    # monitor specs. We just need to ensure the real display is primary.
    user_xml = _read_user_monitors_xml()
    if user_xml:
        # Parse and fix: ensure primary is on the real output, not virtual
        try:
            root = ET.fromstring(user_xml)
            for config in root.findall("configuration"):
                has_primary = False
                for lm in config.findall("logicalmonitor"):
                    monitor = lm.find("monitor")
                    if monitor is None:
                        continue
                    spec = monitor.find("monitorspec")
                    if spec is None:
                        continue
                    connector = spec.find("connector")
                    if connector is None:
                        continue
                    connector_name = connector.text or ""

                    # Remove primary from virtual outputs
                    primary_elem = lm.find("primary")
                    if connector_name in virtual_outputs:
                        if primary_elem is not None:
                            lm.remove(primary_elem)
                    elif connector_name == primary_output:
                        # Set primary on real output
                        if primary_elem is None:
                            primary_elem = ET.SubElement(lm, "primary")
                        primary_elem.text = "yes"
                        has_primary = True

                # If no primary was set (real output not in config), set it
                if not has_primary:
                    for lm in config.findall("logicalmonitor"):
                        monitor = lm.find("monitor")
                        if monitor is None:
                            continue
                        spec = monitor.find("monitorspec")
                        if spec is None:
                            continue
                        connector = spec.find("connector")
                        if connector is None:
                            continue
                        if connector.text not in virtual_outputs:
                            primary_elem = ET.SubElement(lm, "primary")
                            primary_elem.text = "yes"
                            break

            ET.indent(root, space="  ")
            return '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode")
        except ET.ParseError:
            pass

    # Fallback: generate a minimal monitors.xml from xrandr info
    outputs = parse_xrandr()
    real_output = None
    for o in outputs:
        if o.name == primary_output and o.active and o.current_mode:
            real_output = o
            break

    if not real_output or not real_output.current_mode:
        # Last resort: just use first active non-virtual output
        for o in outputs:
            if o.active and o.current_mode and o.name not in virtual_outputs:
                real_output = o
                break

    if not real_output or not real_output.current_mode:
        return ""

    mode = real_output.current_mode
    # Get monitor EDID info
    monitor_info = _get_real_monitor_info(real_output.name) or {}
    vendor = monitor_info.get("vendor", "unknown")
    product = monitor_info.get("product", "unknown")
    serial = monitor_info.get("serial", "0x00000000")

    return f'''\
<monitors version="2">
  <configuration>
    <logicalmonitor>
      <x>0</x>
      <y>0</y>
      <scale>1</scale>
      <primary>yes</primary>
      <monitor>
        <monitorspec>
          <connector>{real_output.name}</connector>
          <vendor>{vendor}</vendor>
          <product>{product}</product>
          <serial>{serial}</serial>
        </monitorspec>
        <mode>
          <width>{mode.width}</width>
          <height>{mode.height}</height>
          <rate>{mode.refresh:.3f}</rate>
        </mode>
      </monitor>
    </logicalmonitor>
  </configuration>
</monitors>
'''


def _write_gdm_monitors_xml(primary_output: str, virtual_outputs: list[str]):
    """Write monitors.xml to GDM config so the login screen uses the real display."""
    gdm_dir = _find_gdm_config_dir()
    if not gdm_dir:
        return  # No GDM found, skip silently

    xml_content = _generate_gdm_monitors_xml(primary_output, virtual_outputs)
    if not xml_content:
        return

    gdm_monitors = str(gdm_dir / "monitors.xml")
    try:
        _pkexec_write_file(gdm_monitors, xml_content)
    except RuntimeError:
        pass  # Non-fatal: login screen may show on wrong display but session works


def _remove_gdm_monitors_xml():
    """Remove the GDM monitors.xml we wrote."""
    gdm_dir = _find_gdm_config_dir()
    if not gdm_dir:
        return
    gdm_monitors = str(gdm_dir / "monitors.xml")
    if Path(gdm_monitors).exists():
        try:
            _pkexec_remove_file(gdm_monitors)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# GPU / display server detection
# ---------------------------------------------------------------------------

def detect_display_server() -> str:
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type in ("wayland", "x11"):
        return session_type
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def detect_gpu_vendor() -> str:
    """Detect primary GPU vendor: 'nvidia', 'intel', 'amd', or 'unknown'."""
    try:
        result = _run(["lspci"], check=False)
        vga = [l for l in result.stdout.splitlines() if "VGA" in l or "3D" in l]
        combined = " ".join(vga).lower()
        if "nvidia" in combined:
            return "nvidia"
        if "intel" in combined:
            return "intel"
        if "amd" in combined or "radeon" in combined:
            return "amd"
    except FileNotFoundError:
        pass
    return "unknown"


def check_xrandr_available() -> bool:
    try:
        _xrandr("--version")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# ---------------------------------------------------------------------------
# xrandr output parsing
# ---------------------------------------------------------------------------

_OUTPUT_RE = re.compile(
    r'^(\S+)\s+(connected|disconnected)\s*'
    r'(?:(primary)\s+)?'
    r'(?:(\d+)x(\d+)\+(\d+)\+(\d+)\s+)?'
)
_MODE_RE = re.compile(r'^\s+(\d+)x(\d+)\s+(.*)')


def _parse_provider_map() -> dict[str, str]:
    """Map output names to their provider (nvidia / modesetting)."""
    mapping: dict[str, str] = {}
    try:
        result = _xrandr("--listproviders")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return mapping

    providers: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        m = re.match(r'Provider\s+(\d+):\s+id:\s+\S+\s+cap:.*name:(.*)', line)
        if m:
            providers.append((int(m.group(1)), m.group(2).strip()))

    # Use verbose xrandr to get CRTC/provider per output
    try:
        verbose = _xrandr("--verbose")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return mapping

    current_output = None
    for line in verbose.stdout.splitlines():
        om = _OUTPUT_RE.match(line)
        if om:
            current_output = om.group(1)
            continue
        if current_output and "ConnectorType:" in line:
            # Heuristic: NVIDIA outputs have ConnectorType, modesetting ones also do
            pass

    # Simpler heuristic: NVIDIA outputs don't have DP-1-X naming pattern typically
    # The provider index is embedded in output names for offload:
    #   Provider 0 (NVIDIA): HDMI-0, DP-0
    #   Provider 1 (modesetting): DP-1-1, DP-1-2, HDMI-1-2
    for p_idx, p_name in providers:
        pname_lower = p_name.lower()
        if "nvidia" in pname_lower:
            mapping[f"_provider_{p_idx}"] = "nvidia"
        else:
            mapping[f"_provider_{p_idx}"] = "modesetting"

    # Assign outputs to providers by naming convention
    outputs = parse_xrandr()
    for o in outputs:
        # NVIDIA primary outputs: HDMI-0, DP-0 (single digit, no sub-index)
        # Modesetting offload outputs: DP-1-1, HDMI-1-2 (have sub-indices)
        if re.match(r'^(HDMI|DP|DVI)-\d+-\d+', o.name):
            mapping[o.name] = "modesetting"
        else:
            mapping[o.name] = "nvidia"

    return mapping


def parse_xrandr() -> list[Output]:
    """Parse `xrandr` output into a list of Output objects."""
    result = _xrandr()
    outputs: list[Output] = []
    current_output: Optional[Output] = None

    for line in result.stdout.splitlines():
        m = _OUTPUT_RE.match(line)
        if m:
            current_output = Output(
                name=m.group(1),
                connected=(m.group(2) == "connected"),
                active=(m.group(4) is not None),
                position_x=int(m.group(6)) if m.group(6) else 0,
                position_y=int(m.group(7)) if m.group(7) else 0,
                width=int(m.group(4)) if m.group(4) else 0,
                height=int(m.group(5)) if m.group(5) else 0,
            )
            outputs.append(current_output)
            continue

        if current_output is not None:
            mm = _MODE_RE.match(line)
            if mm:
                width, height = int(mm.group(1)), int(mm.group(2))
                for token in mm.group(3).split():
                    is_current = "*" in token
                    is_preferred = "+" in token
                    rate_val = token.replace("*", "").replace("+", "").strip()
                    if not rate_val:
                        continue
                    try:
                        rate = float(rate_val)
                    except ValueError:
                        continue
                    mode = Mode(width=width, height=height, refresh=rate,
                                name=f"{width}x{height}",
                                current=is_current, preferred=is_preferred)
                    current_output.modes.append(mode)
                    if is_current:
                        current_output.current_mode = mode

    return outputs


# ---------------------------------------------------------------------------
# NVIDIA xorg.conf management
# ---------------------------------------------------------------------------

def _nvidia_conf_exists() -> bool:
    return XORG_CONF_FILE.exists()


def _nvidia_read_conf_outputs() -> list[str]:
    """Read which outputs are configured as ConnectedMonitor in xorg.conf."""
    if not XORG_CONF_FILE.exists():
        return []
    try:
        text = XORG_CONF_FILE.read_text()
        m = re.search(r'Option\s+"ConnectedMonitor"\s+"([^"]+)"', text)
        if m:
            return [o.strip() for o in m.group(1).split(",")]
    except OSError:
        pass
    return []


def _nvidia_generate_conf(primary_output: str, virtual_outputs: list[str]) -> str:
    """Generate xorg.conf.d content for NVIDIA virtual displays."""
    all_outputs = [primary_output] + virtual_outputs
    connected = ", ".join(all_outputs)

    # Build CustomEDID entries for virtual outputs
    edid_entries = [f"{o}:{EDID_FILE}" for o in virtual_outputs]
    custom_edid = "; ".join(edid_entries)

    return f'''\
# Generated by Linux Virtual Display Driver
# https://github.com/VirtualDrivers/Linux-Virtual-Display-Driver
#
# This file forces NVIDIA to treat virtual outputs as connected.
# Remove this file and restart your session to undo.

Section "Device"
    Identifier     "Device0"
    Driver         "nvidia"
    Option         "ConnectedMonitor" "{connected}"
    Option         "CustomEDID" "{custom_edid}"
    Option         "ModeValidation" "AllowNonEdidModes, NoMaxPClkCheck, NoEdidMaxPClkCheck, NoMaxSizeCheck, NoHorizSyncCheck, NoVertRefreshCheck, NoDFPNativeResolutionCheck"
    Option         "AllowEmptyInitialConfiguration" "True"
EndSection
'''


# ---------------------------------------------------------------------------
# DisplayManager
# ---------------------------------------------------------------------------

class DisplayManager:
    """Manages creation and removal of virtual displays."""

    def __init__(self):
        self.gpu_vendor = detect_gpu_vendor()
        self.managed_displays: list[VirtualDisplay] = []
        self._provider_map: dict[str, str] = {}
        self._load_state()
        try:
            self._provider_map = _parse_provider_map()
        except Exception:
            pass

    # -- State persistence --

    def _load_state(self):
        data = _load_config()
        self.managed_displays = []
        for d in data:
            try:
                self.managed_displays.append(VirtualDisplay(**d))
            except TypeError:
                continue
        self._verify_state()
        self._adopt_untracked_virtual_displays()

    def _verify_state(self):
        try:
            outputs = parse_xrandr()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return
        output_map = {o.name: o for o in outputs}
        for vd in self.managed_displays:
            out = output_map.get(vd.output)
            if out and out.active and out.current_mode:
                vd.active = (out.current_mode.width == vd.width and
                             out.current_mode.height == vd.height)
            else:
                vd.active = False

    def _adopt_untracked_virtual_displays(self):
        """Detect active virtual displays from NVIDIA config not tracked by the app.

        If the xorg.conf lists virtual outputs that are currently active but
        not in our managed_displays list, adopt them so they show in the GUI.
        """
        if not _nvidia_conf_exists():
            return

        conf_outputs = _nvidia_read_conf_outputs()
        if not conf_outputs:
            return

        # Determine which conf outputs are virtual (not the primary)
        try:
            outputs = parse_xrandr()
        except (FileNotFoundError, subprocess.CalledProcessError):
            return

        # Find the primary physical output
        primary_name = None
        for o in outputs:
            if o.active and o.name in conf_outputs:
                # The physical display has a larger physical size
                # Virtual EDID reports 53x30mm, real displays are much larger
                result = _run(["xrandr", "--verbose"], check=False)
                for line in result.stdout.splitlines():
                    if line.startswith(o.name) and "mm x" in line:
                        import re as _re
                        size_m = _re.search(r'(\d+)mm x (\d+)mm', line)
                        if size_m:
                            w_mm = int(size_m.group(1))
                            # VDD Virtual EDID is 53x30mm; real displays are larger
                            if w_mm > 100:
                                primary_name = o.name
                                break
                if primary_name:
                    break

        if not primary_name:
            # Fallback: use xrandr primary
            for o in outputs:
                result = _run(["xrandr"], check=False)
                for line in result.stdout.splitlines():
                    if o.name in line and "primary" in line:
                        primary_name = o.name
                        break
                if primary_name:
                    break

        if not primary_name:
            return

        virtual_output_names = [o for o in conf_outputs if o != primary_name]
        tracked_names = {vd.output for vd in self.managed_displays}
        output_map = {o.name: o for o in outputs}

        adopted = False
        for vname in virtual_output_names:
            if vname in tracked_names:
                continue
            out = output_map.get(vname)
            if not out or not out.connected:
                continue
            if out.active and out.current_mode:
                mode = out.current_mode
                vd = VirtualDisplay(
                    output=vname,
                    mode_name=mode.name,
                    width=mode.width,
                    height=mode.height,
                    refresh=mode.refresh,
                    position="",
                    active=True,
                )
            else:
                # Inactive but configured — adopt with default resolution
                preferred = None
                for m in out.modes:
                    if m.preferred:
                        preferred = m
                        break
                if not preferred and out.modes:
                    preferred = out.modes[0]
                w = preferred.width if preferred else 1920
                h = preferred.height if preferred else 1080
                r = preferred.refresh if preferred else 60.0
                vd = VirtualDisplay(
                    output=vname,
                    mode_name=f"{w}x{h}",
                    width=w,
                    height=h,
                    refresh=r,
                    position="",
                    active=False,
                )
            self.managed_displays.append(vd)
            adopted = True

        if adopted:
            self._save_state()

    def _save_state(self):
        _save_config(self.managed_displays)

    # -- NVIDIA setup --

    def is_nvidia(self) -> bool:
        return self.gpu_vendor == "nvidia"

    def nvidia_needs_setup(self) -> bool:
        """Check if NVIDIA xorg.conf setup is needed."""
        if not self.is_nvidia():
            return False
        return not _nvidia_conf_exists()

    def nvidia_get_virtual_output_candidates(self) -> list[str]:
        """Get NVIDIA output names that can be used as virtual displays.

        Returns outputs not currently used as the primary physical display.
        Includes common NVIDIA output names not yet in the config.
        """
        outputs = parse_xrandr()
        primary = self.nvidia_get_primary_output()
        existing_conf = _nvidia_read_conf_outputs()

        # Start with currently visible disconnected/inactive NVIDIA outputs
        candidates = []
        for o in outputs:
            if o.name == primary:
                continue
            provider = self._provider_map.get(o.name, "")
            if provider == "nvidia" and not o.active:
                candidates.append(o.name)

        # Also offer common NVIDIA output names not already configured/visible
        # NVIDIA GPUs typically have DP-0..DP-7 and HDMI-0..HDMI-1
        common_outputs = [
            "DP-0", "DP-1", "DP-2", "DP-3", "DP-4", "DP-5",
            "HDMI-0", "HDMI-1",
        ]
        visible_names = {o.name for o in outputs}
        for name in common_outputs:
            if name == primary:
                continue
            if name in [c for c in candidates]:
                continue
            if name in visible_names:
                # Already visible but not a candidate yet (it's active/used)
                continue
            # Not currently visible — can be added to ConnectedMonitor
            candidates.append(name)

        return candidates

    def nvidia_get_primary_output(self) -> Optional[str]:
        """Get the name of the current primary/active NVIDIA output."""
        outputs = parse_xrandr()
        for o in outputs:
            if o.active and self._provider_map.get(o.name) == "nvidia":
                return o.name
        # Fallback to any active output
        for o in outputs:
            if o.active:
                return o.name
        return None

    def nvidia_setup(self, virtual_outputs: list[str]) -> str:
        """Write NVIDIA xorg.conf.d and EDID files.

        Args:
            virtual_outputs: Output names to make available as virtual displays.
                These are merged with any existing virtual outputs in the config.

        Returns:
            Status message.

        Raises:
            RuntimeError: If setup fails.
        """
        primary = self.nvidia_get_primary_output()
        if not primary:
            raise RuntimeError("Could not determine primary output.")

        # Merge with existing virtual outputs from config
        existing = _nvidia_read_conf_outputs()
        existing_virtual = [o for o in existing if o != primary]
        merged = list(dict.fromkeys(existing_virtual + virtual_outputs))
        virtual_outputs = merged

        # Write the virtual EDID binary
        edid_bytes = _generate_virtual_edid()
        _pkexec_write_file(str(EDID_FILE), edid_bytes)

        # Write xorg.conf.d
        conf = _nvidia_generate_conf(primary, virtual_outputs)
        _pkexec_write_file(str(XORG_CONF_FILE), conf)

        # Write GDM monitors.xml so the login screen stays on the real display
        _write_gdm_monitors_xml(primary, virtual_outputs)

        return (
            f"Configuration written.\n\n"
            f"Primary output: {primary}\n"
            f"Virtual outputs: {', '.join(virtual_outputs)}\n\n"
            f"You must log out and back in (or restart your display "
            f"manager) for the changes to take effect."
        )

    def nvidia_teardown(self) -> str:
        """Remove NVIDIA xorg.conf.d and EDID files.

        Returns:
            Status message.

        Raises:
            RuntimeError: If removal fails.
        """
        errors = []
        for path in [str(XORG_CONF_FILE), str(EDID_FILE)]:
            try:
                _pkexec_remove_file(path)
            except RuntimeError as e:
                errors.append(str(e))

        # Clean up GDM monitors.xml since virtual outputs are being removed
        _remove_gdm_monitors_xml()

        if errors:
            raise RuntimeError("\n".join(errors))

        return (
            "Configuration removed.\n\n"
            "Log out and back in to complete the removal."
        )

    def nvidia_is_setup_active(self) -> bool:
        """Check if NVIDIA config exists AND a virtual output is connected."""
        if not _nvidia_conf_exists():
            return False
        conf_outputs = _nvidia_read_conf_outputs()
        primary = self.nvidia_get_primary_output()
        virtual_in_conf = [o for o in conf_outputs if o != primary]
        if not virtual_in_conf:
            return False
        # Check if any configured virtual output is now connected
        xrandr_outputs = parse_xrandr()
        for o in xrandr_outputs:
            if o.name in virtual_in_conf and o.connected:
                return True
        return False

    def nvidia_setup_status(self) -> str:
        """Get a human-readable setup status for NVIDIA."""
        if not self.is_nvidia():
            return ""
        if not _nvidia_conf_exists():
            return "Setup required"
        if self.nvidia_is_setup_active():
            return "Ready"
        return "Restart required"

    # -- Output queries --

    def get_outputs(self) -> list[Output]:
        return parse_xrandr()

    def get_available_outputs(self) -> list[Output]:
        """Get outputs that can host a new virtual display."""
        outputs = parse_xrandr()
        used = {vd.output for vd in self.managed_displays if vd.active}
        available = []
        for o in outputs:
            if o.name in used:
                continue
            # For NVIDIA setups: use connected but inactive outputs
            # (ConnectedMonitor makes them show as connected)
            if not o.active:
                if self.is_nvidia():
                    # Prefer NVIDIA-provider outputs (they're the ones we configured)
                    provider = self._provider_map.get(o.name, "")
                    if o.connected or provider == "nvidia":
                        available.append(o)
                else:
                    available.append(o)
        return available

    def get_active_outputs(self) -> list[Output]:
        return [o for o in parse_xrandr() if o.active]

    def get_primary_output(self) -> Optional[Output]:
        result = _xrandr()
        for line in result.stdout.splitlines():
            if "primary" in line and "connected" in line:
                name = line.split()[0]
                for o in parse_xrandr():
                    if o.name == name:
                        return o
        active = self.get_active_outputs()
        return active[0] if active else None

    # -- Virtual display management --

    def create_display(self, width: int, height: int, refresh: float,
                       output: Optional[str] = None,
                       position: str = "right-of",
                       relative_to: Optional[str] = None,
                       reduced_blanking: bool = False) -> VirtualDisplay:
        """Create a new virtual display."""

        # NVIDIA pre-check
        if self.is_nvidia() and self.nvidia_needs_setup():
            raise RuntimeError(
                "NVIDIA GPU detected but virtual outputs are not configured.\n\n"
                "Use the 'Setup Virtual Outputs' option from the menu first."
            )
        if self.is_nvidia() and not self.nvidia_is_setup_active():
            raise RuntimeError(
                "NVIDIA virtual output configuration exists but is not yet active.\n\n"
                "Please log out and back in for the configuration to take effect."
            )

        # Generate modeline
        ml = generate_modeline(width, height, refresh, reduced_blanking)
        mode_name = ml["name"]

        # Auto-select output
        if output is None:
            available = self.get_available_outputs()
            if not available:
                raise RuntimeError(
                    "No available outputs found.\n\n"
                    "Possible solutions:\n"
                    "  - NVIDIA: Use 'Setup Virtual Outputs' from the menu\n"
                    "  - Intel: Check for VIRTUAL1/VIRTUAL2 outputs\n"
                    "  - Install xf86-video-dummy or load evdi kernel module"
                )
            output = available[0].name

        # Auto-select relative_to
        if relative_to is None:
            primary = self.get_primary_output()
            if primary:
                relative_to = primary.name

        # Step 1: Create mode
        try:
            _xrandr("--newmode", *ml["modeline_args"])
        except subprocess.CalledProcessError as e:
            if "already exists" not in (e.stderr or ""):
                raise RuntimeError(f"Failed to create mode:\n{e.stderr}") from e

        # Step 2: Add mode to output
        try:
            _xrandr("--addmode", output, mode_name)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to add mode to {output}:\n{e.stderr}\n\n"
                f"This output may not accept custom modes."
            ) from e

        # Step 3: Enable output
        cmd = ["--output", output, "--mode", mode_name]
        pos_flag = ""
        if relative_to and position != "manual":
            pos_map = {
                "right-of": "--right-of",
                "left-of": "--left-of",
                "above": "--above",
                "below": "--below",
                "same-as": "--same-as",
            }
            flag = pos_map.get(position, "--right-of")
            cmd.extend([flag, relative_to])
            pos_flag = f"{flag} {relative_to}"

        try:
            _xrandr(*cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to enable {output}:\n{e.stderr}"
            ) from e

        vd = VirtualDisplay(
            output=output, mode_name=mode_name,
            width=width, height=height, refresh=refresh,
            position=pos_flag, active=True,
        )
        self.managed_displays.append(vd)
        self._save_state()

        # Update GDM monitors.xml so login screen stays on real display
        primary = self.get_primary_output()
        if primary:
            virtual_names = [d.output for d in self.managed_displays]
            _write_gdm_monitors_xml(primary.name, virtual_names)

        return vd

    def enable_display(self, vd: VirtualDisplay,
                       position: str = "right-of",
                       relative_to: Optional[str] = None):
        """Enable an inactive virtual display."""
        if vd.active:
            return

        # Ensure the mode exists on the output
        mode_name = f"{vd.width}x{vd.height}"
        ml = generate_modeline(vd.width, vd.height, vd.refresh)
        try:
            _xrandr("--newmode", *ml["modeline_args"])
        except subprocess.CalledProcessError as e:
            if "already exists" not in (e.stderr or ""):
                raise RuntimeError(f"Failed to create mode:\n{e.stderr}") from e

        try:
            _xrandr("--addmode", vd.output, ml["name"])
        except subprocess.CalledProcessError as e:
            if "already exists" not in (e.stderr or ""):
                raise RuntimeError(f"Failed to add mode to {vd.output}:\n{e.stderr}") from e

        if relative_to is None:
            primary = self.get_primary_output()
            if primary:
                relative_to = primary.name

        cmd = ["--output", vd.output, "--mode", ml["name"]]
        if relative_to:
            pos_map = {
                "right-of": "--right-of",
                "left-of": "--left-of",
                "above": "--above",
                "below": "--below",
                "same-as": "--same-as",
            }
            flag = pos_map.get(position, "--right-of")
            cmd.extend([flag, relative_to])
            vd.position = f"{flag} {relative_to}"

        try:
            _xrandr(*cmd)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to enable {vd.output}:\n{e.stderr}") from e

        vd.mode_name = ml["name"]
        vd.active = True
        self._save_state()

    def disable_display(self, vd: VirtualDisplay):
        """Disable an active virtual display without removing it."""
        if not vd.active:
            return

        try:
            _xrandr("--output", vd.output, "--off")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to disable {vd.output}:\n{e.stderr}") from e

        vd.active = False
        self._save_state()

    def remove_display(self, vd: VirtualDisplay):
        """Remove a virtual display."""
        # Turn off the output
        try:
            _xrandr("--output", vd.output, "--off")
        except subprocess.CalledProcessError:
            pass  # Already off

        # Try to clean up custom modes (ignore errors for built-in EDID modes)
        try:
            _xrandr("--delmode", vd.output, vd.mode_name)
        except subprocess.CalledProcessError:
            pass
        try:
            _xrandr("--rmmode", vd.mode_name)
        except subprocess.CalledProcessError:
            pass

        if vd in self.managed_displays:
            self.managed_displays.remove(vd)
        self._save_state()

    def remove_all(self):
        for vd in list(self.managed_displays):
            try:
                self.remove_display(vd)
            except RuntimeError:
                pass

    def refresh(self):
        self._verify_state()
        self._save_state()
