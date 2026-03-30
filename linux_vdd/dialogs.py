"""
GTK dialogs for adding/editing virtual displays and NVIDIA setup.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .display_manager import DisplayManager


# Common resolution presets: (label, width, height)
RESOLUTION_PRESETS = [
    ("1920 x 1080  (Full HD)", 1920, 1080),
    ("2560 x 1440  (QHD)", 2560, 1440),
    ("3840 x 2160  (4K UHD)", 3840, 2160),
    ("1280 x 720   (HD)", 1280, 720),
    ("1600 x 900", 1600, 900),
    ("1680 x 1050", 1680, 1050),
    ("1920 x 1200", 1920, 1200),
    ("2560 x 1080  (Ultrawide)", 2560, 1080),
    ("3440 x 1440  (UW QHD)", 3440, 1440),
    ("5120 x 1440  (Super UW)", 5120, 1440),
    ("Custom", 0, 0),
]

REFRESH_PRESETS = [30, 60, 75, 90, 120, 144, 165, 240]

POSITION_OPTIONS = [
    ("Right of", "right-of"),
    ("Left of", "left-of"),
    ("Above", "above"),
    ("Below", "below"),
    ("Mirror / Same as", "same-as"),
]


class NvidiaSetupDialog(Gtk.Dialog):
    """One-time setup dialog for NVIDIA virtual output configuration."""

    def __init__(self, parent: Gtk.Window, manager: DisplayManager):
        super().__init__(
            title="NVIDIA Virtual Output Setup",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.manager = manager
        self.set_default_size(480, -1)
        self.set_resizable(False)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        setup_btn = self.add_button("Apply Configuration", Gtk.ResponseType.OK)
        setup_btn.get_style_context().add_class("suggested-action")

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(16)
        content.set_margin_bottom(8)

        # Explanation
        info_label = Gtk.Label()
        info_label.set_markup(
            "<b>NVIDIA GPU detected</b>\n\n"
            "NVIDIA requires a one-time configuration to enable virtual "
            "display outputs. This writes an X11 config file and a virtual "
            "EDID so the GPU treats selected outputs as connected monitors.\n\n"
            "<b>You will need to log out and back in after setup.</b>"
        )
        info_label.set_line_wrap(True)
        info_label.set_max_width_chars(55)
        info_label.set_halign(Gtk.Align.START)
        content.pack_start(info_label, False, False, 0)

        # Output selection
        content.pack_start(self._make_section_label("Select Virtual Outputs"), False, False, 4)

        candidates = manager.nvidia_get_virtual_output_candidates()
        self.output_checks: list[tuple[Gtk.CheckButton, str]] = []

        if candidates:
            for name in candidates:
                cb = Gtk.CheckButton(label=name)
                cb.set_active(True)  # Select all by default
                content.pack_start(cb, False, False, 0)
                self.output_checks.append((cb, name))
        else:
            no_out = Gtk.Label(label="No additional NVIDIA outputs found (only HDMI/DP on the GPU).")
            no_out.set_halign(Gtk.Align.START)
            no_out.get_style_context().add_class("dim-label")
            content.pack_start(no_out, False, False, 0)

        # Files that will be written
        content.pack_start(self._make_section_label("Files to be created"), False, False, 8)
        files_label = Gtk.Label()
        files_label.set_markup(
            "<tt>/etc/X11/xorg.conf.d/99-linux-vdd.conf</tt>\n"
            "<tt>/usr/share/linux-vdd/virtual-edid.bin</tt>"
        )
        files_label.set_halign(Gtk.Align.START)
        content.pack_start(files_label, False, False, 0)

        note = Gtk.Label()
        note.set_markup(
            "<small>Your password will be requested to write system files.</small>"
        )
        note.set_halign(Gtk.Align.START)
        note.get_style_context().add_class("dim-label")
        content.pack_start(note, False, False, 4)

        content.show_all()

    def _make_section_label(self, text: str) -> Gtk.Label:
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_halign(Gtk.Align.START)
        return label

    def get_selected_outputs(self) -> list[str]:
        return [name for cb, name in self.output_checks if cb.get_active()]


class AddDisplayDialog(Gtk.Dialog):
    """Dialog for adding a new virtual display."""

    def __init__(self, parent: Gtk.Window, manager: DisplayManager):
        super().__init__(
            title="Add Virtual Display",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.manager = manager
        self.set_default_size(420, -1)
        self.set_resizable(False)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        add_btn = self.add_button("Add Display", Gtk.ResponseType.OK)
        add_btn.get_style_context().add_class("suggested-action")

        content = self.get_content_area()
        content.set_spacing(12)
        content.set_margin_start(20)
        content.set_margin_end(20)
        content.set_margin_top(16)
        content.set_margin_bottom(8)

        # --- Resolution ---
        content.pack_start(self._make_section_label("Resolution"), False, False, 0)

        self.res_combo = Gtk.ComboBoxText()
        for label, _w, _h in RESOLUTION_PRESETS:
            self.res_combo.append_text(label)
        self.res_combo.set_active(0)
        self.res_combo.connect("changed", self._on_res_preset_changed)
        content.pack_start(self.res_combo, False, False, 0)

        self.custom_res_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.width_entry = Gtk.SpinButton.new_with_range(320, 15360, 1)
        self.width_entry.set_value(1920)
        self.width_entry.set_numeric(True)
        self.height_entry = Gtk.SpinButton.new_with_range(200, 8640, 1)
        self.height_entry.set_value(1080)
        self.height_entry.set_numeric(True)
        self.custom_res_box.pack_start(self.width_entry, True, True, 0)
        self.custom_res_box.pack_start(Gtk.Label(label="x"), False, False, 0)
        self.custom_res_box.pack_start(self.height_entry, True, True, 0)
        px = Gtk.Label(label="px")
        px.get_style_context().add_class("dim-label")
        self.custom_res_box.pack_start(px, False, False, 0)
        self.custom_res_box.set_no_show_all(True)
        content.pack_start(self.custom_res_box, False, False, 0)

        # --- Refresh Rate ---
        content.pack_start(self._make_section_label("Refresh Rate"), False, False, 4)

        self.refresh_combo = Gtk.ComboBoxText()
        for r in REFRESH_PRESETS:
            self.refresh_combo.append_text(f"{r} Hz")
        self.refresh_combo.append_text("Custom")
        self.refresh_combo.set_active(1)  # 60 Hz
        self.refresh_combo.connect("changed", self._on_refresh_preset_changed)
        content.pack_start(self.refresh_combo, False, False, 0)

        self.custom_refresh_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.refresh_entry = Gtk.SpinButton.new_with_range(1, 500, 1)
        self.refresh_entry.set_value(60)
        self.refresh_entry.set_numeric(True)
        hz = Gtk.Label(label="Hz")
        hz.get_style_context().add_class("dim-label")
        self.custom_refresh_box.pack_start(self.refresh_entry, True, True, 0)
        self.custom_refresh_box.pack_start(hz, False, False, 0)
        self.custom_refresh_box.set_no_show_all(True)
        content.pack_start(self.custom_refresh_box, False, False, 0)

        # --- Output ---
        content.pack_start(self._make_section_label("Output"), False, False, 4)

        self.output_combo = Gtk.ComboBoxText()
        self._populate_outputs()
        content.pack_start(self.output_combo, False, False, 0)

        # --- Position ---
        content.pack_start(self._make_section_label("Position"), False, False, 4)

        pos_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.pos_combo = Gtk.ComboBoxText()
        for label, _val in POSITION_OPTIONS:
            self.pos_combo.append_text(label)
        self.pos_combo.set_active(0)
        pos_box.pack_start(self.pos_combo, True, True, 0)

        self.relative_combo = Gtk.ComboBoxText()
        self._populate_relative_to()
        pos_box.pack_start(self.relative_combo, True, True, 0)
        content.pack_start(pos_box, False, False, 0)

        # --- Reduced blanking ---
        self.reduced_check = Gtk.CheckButton(label="Reduced blanking (lower bandwidth)")
        self.reduced_check.set_tooltip_text(
            "Use CVT reduced blanking timings. Recommended for high refresh rates."
        )
        content.pack_start(self.reduced_check, False, False, 8)

        content.show_all()

    def _make_section_label(self, text: str) -> Gtk.Label:
        label = Gtk.Label()
        label.set_markup(f"<b>{text}</b>")
        label.set_halign(Gtk.Align.START)
        return label

    def _populate_outputs(self):
        self.output_combo.remove_all()
        available = self.manager.get_available_outputs()
        if available:
            self.output_combo.append_text("Auto (first available)")
            for out in available:
                status = "connected" if out.connected else "disconnected"
                self.output_combo.append_text(f"{out.name}  ({status})")
            self.output_combo.set_active(0)
        else:
            self.output_combo.append_text("No available outputs")
            self.output_combo.set_active(0)

    def _populate_relative_to(self):
        self.relative_combo.remove_all()
        active = self.manager.get_active_outputs()
        for out in active:
            label = out.name
            if out.current_mode:
                label += f" ({out.current_mode.width}x{out.current_mode.height})"
            self.relative_combo.append_text(label)
        if active:
            self.relative_combo.set_active(0)

    def _on_res_preset_changed(self, combo):
        idx = combo.get_active()
        if idx == len(RESOLUTION_PRESETS) - 1:
            self.custom_res_box.set_no_show_all(False)
            self.custom_res_box.show_all()
        else:
            self.custom_res_box.hide()
            if idx >= 0:
                _, w, h = RESOLUTION_PRESETS[idx]
                self.width_entry.set_value(w)
                self.height_entry.set_value(h)

    def _on_refresh_preset_changed(self, combo):
        idx = combo.get_active()
        if idx == len(REFRESH_PRESETS):
            self.custom_refresh_box.set_no_show_all(False)
            self.custom_refresh_box.show_all()
        else:
            self.custom_refresh_box.hide()
            if 0 <= idx < len(REFRESH_PRESETS):
                self.refresh_entry.set_value(REFRESH_PRESETS[idx])

    def get_values(self) -> dict:
        res_idx = self.res_combo.get_active()
        if res_idx == len(RESOLUTION_PRESETS) - 1:
            width = int(self.width_entry.get_value())
            height = int(self.height_entry.get_value())
        else:
            _, width, height = RESOLUTION_PRESETS[res_idx]

        refresh_idx = self.refresh_combo.get_active()
        if refresh_idx == len(REFRESH_PRESETS):
            refresh = self.refresh_entry.get_value()
        else:
            refresh = float(REFRESH_PRESETS[refresh_idx])

        out_idx = self.output_combo.get_active()
        available = self.manager.get_available_outputs()
        if out_idx <= 0 or not available:
            output = None
        else:
            output = available[out_idx - 1].name

        pos_idx = self.pos_combo.get_active()
        position = POSITION_OPTIONS[pos_idx][1] if pos_idx >= 0 else "right-of"

        rel_text = self.relative_combo.get_active_text()
        relative_to = rel_text.split(" (")[0] if rel_text else None

        return {
            "width": width,
            "height": height,
            "refresh": refresh,
            "output": output,
            "position": position,
            "relative_to": relative_to,
            "reduced_blanking": self.reduced_check.get_active(),
        }
