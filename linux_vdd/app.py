"""
Main GTK3 application and window for Linux Virtual Display Driver.
"""

import sys

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio, GLib

from . import __version__, __app_id__, __app_name__
from .display_manager import (
    DisplayManager, VirtualDisplay,
    detect_display_server, check_xrandr_available,
)
from .dialogs import AddDisplayDialog, NvidiaSetupDialog


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
.main-window {
    background-color: @theme_bg_color;
}

.display-card {
    background-color: @theme_base_color;
    border: 1px solid alpha(@theme_fg_color, 0.15);
    border-radius: 8px;
    padding: 14px 16px;
    margin: 4px 0;
}

.display-card:hover {
    border-color: @theme_selected_bg_color;
}

.display-title {
    font-weight: bold;
    font-size: 14px;
}

.display-subtitle {
    opacity: 0.7;
    font-size: 12px;
}

.display-badge {
    background-color: @theme_selected_bg_color;
    color: @theme_selected_fg_color;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}

.display-badge-inactive {
    background-color: alpha(@theme_fg_color, 0.2);
    color: @theme_fg_color;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}

.empty-state-title {
    font-size: 18px;
    font-weight: bold;
    opacity: 0.6;
}

.empty-state-subtitle {
    font-size: 13px;
    opacity: 0.45;
}

.status-bar {
    font-size: 12px;
    opacity: 0.6;
    padding: 6px 16px;
    border-top: 1px solid alpha(@theme_fg_color, 0.1);
}

.remove-button {
    border-radius: 6px;
    min-height: 28px;
    min-width: 28px;
    padding: 0;
}

.info-bar-nvidia {
    border-radius: 0;
}
"""


# ---------------------------------------------------------------------------
# Display card widget
# ---------------------------------------------------------------------------

class DisplayCard(Gtk.ListBoxRow):
    def __init__(self, vd: VirtualDisplay, on_remove, on_toggle):
        super().__init__()
        self.vd = vd
        self.set_activatable(False)
        self.set_selectable(False)

        frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        frame.get_style_context().add_class("display-card")

        icon = Gtk.Image.new_from_icon_name("video-display", Gtk.IconSize.DND)
        icon.set_pixel_size(32)
        icon.set_opacity(0.7)
        frame.pack_start(icon, False, False, 0)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title = Gtk.Label(label=vd.output)
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("display-title")
        info_box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label=f"{vd.width} x {vd.height}  @  {vd.refresh:.0f} Hz")
        subtitle.set_halign(Gtk.Align.START)
        subtitle.get_style_context().add_class("display-subtitle")
        info_box.pack_start(subtitle, False, False, 0)

        if vd.position:
            pos_label = Gtk.Label(
                label=vd.position.replace("--", "").replace("-", " ").title()
            )
            pos_label.set_halign(Gtk.Align.START)
            pos_label.get_style_context().add_class("display-subtitle")
            info_box.pack_start(pos_label, False, False, 0)

        frame.pack_start(info_box, True, True, 0)

        # Toggle button
        if vd.active:
            toggle_btn = Gtk.Button(label="Disable")
            toggle_btn.set_tooltip_text("Turn off this virtual display")
        else:
            toggle_btn = Gtk.Button(label="Enable")
            toggle_btn.get_style_context().add_class("suggested-action")
            toggle_btn.set_tooltip_text("Turn on this virtual display")
        toggle_btn.get_style_context().add_class("remove-button")
        toggle_btn.set_valign(Gtk.Align.CENTER)
        toggle_btn.connect("clicked", lambda _: on_toggle(vd))
        frame.pack_start(toggle_btn, False, False, 0)

        if vd.active:
            badge = Gtk.Label(label="ACTIVE")
            badge.get_style_context().add_class("display-badge")
        else:
            badge = Gtk.Label(label="INACTIVE")
            badge.get_style_context().add_class("display-badge-inactive")
        badge.set_valign(Gtk.Align.CENTER)
        frame.pack_start(badge, False, False, 0)

        remove_btn = Gtk.Button.new_from_icon_name(
            "edit-delete-symbolic", Gtk.IconSize.BUTTON
        )
        remove_btn.set_tooltip_text("Remove this virtual display")
        remove_btn.get_style_context().add_class("destructive-action")
        remove_btn.get_style_context().add_class("remove-button")
        remove_btn.set_valign(Gtk.Align.CENTER)
        remove_btn.connect("clicked", lambda _: on_remove(vd))
        frame.pack_start(remove_btn, False, False, 0)

        self.add(frame)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app, manager: DisplayManager):
        super().__init__(application=app, title=__app_name__)
        self.manager = manager
        self.set_default_size(520, 480)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.get_style_context().add_class("main-window")

        # --- Header bar ---
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.set_title(__app_name__)
        header.set_subtitle("Linux")
        self.set_titlebar(header)

        add_btn = Gtk.Button.new_from_icon_name(
            "list-add-symbolic", Gtk.IconSize.BUTTON
        )
        add_btn.set_tooltip_text("Add virtual display  (Ctrl+N)")
        add_btn.get_style_context().add_class("suggested-action")
        add_btn.connect("clicked", self._on_add_clicked)
        header.pack_start(add_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_image(
            Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        )
        menu = Gio.Menu()
        menu.append("Refresh", "win.refresh")
        if manager.is_nvidia():
            menu.append("Setup Virtual Outputs", "win.nvidia-setup")
            menu.append("Remove NVIDIA Config", "win.nvidia-teardown")
        menu.append("Remove All Displays", "win.remove-all")
        menu.append("About", "win.about")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        # --- Actions ---
        self._add_action("refresh", self._on_refresh)
        self._add_action("remove-all", self._on_remove_all)
        self._add_action("about", self._on_about)
        if manager.is_nvidia():
            self._add_action("nvidia-setup", self._on_nvidia_setup)
            self._add_action("nvidia-teardown", self._on_nvidia_teardown)

        # Ctrl+N
        accel = Gtk.AccelGroup()
        accel.connect(
            Gdk.keyval_from_name("n"),
            Gdk.ModifierType.CONTROL_MASK,
            0,
            lambda *_: self._on_add_clicked(None),
        )
        self.add_accel_group(accel)

        # --- Main layout ---
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        # NVIDIA info bar (shown when setup/restart needed)
        self.nvidia_info_bar = Gtk.InfoBar()
        self.nvidia_info_bar.set_message_type(Gtk.MessageType.WARNING)
        self.nvidia_info_bar.get_style_context().add_class("info-bar-nvidia")
        self.nvidia_info_label = Gtk.Label()
        self.nvidia_info_label.set_line_wrap(True)
        self.nvidia_info_bar.get_content_area().add(self.nvidia_info_label)

        self.nvidia_info_bar.add_button("Setup Now", 1)
        self.nvidia_info_bar.connect("response", self._on_nvidia_info_response)
        self.nvidia_info_bar.set_no_show_all(True)
        vbox.pack_start(self.nvidia_info_bar, False, False, 0)

        # Scrolled display list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        vbox.pack_start(scrolled, True, True, 0)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        scrolled.add(self.stack)

        # Display list
        list_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_wrapper.set_margin_start(16)
        list_wrapper.set_margin_end(16)
        list_wrapper.set_margin_top(12)
        list_wrapper.set_margin_bottom(12)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        list_wrapper.pack_start(self.listbox, True, True, 0)
        self.stack.add_named(list_wrapper, "list")

        # Empty state
        empty_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        empty_box.set_valign(Gtk.Align.CENTER)
        empty_box.set_halign(Gtk.Align.CENTER)

        empty_icon = Gtk.Image.new_from_icon_name(
            "video-display-symbolic", Gtk.IconSize.DIALOG
        )
        empty_icon.set_pixel_size(64)
        empty_icon.set_opacity(0.3)
        empty_box.pack_start(empty_icon, False, False, 16)

        empty_title = Gtk.Label(label="No Virtual Displays")
        empty_title.get_style_context().add_class("empty-state-title")
        empty_box.pack_start(empty_title, False, False, 0)

        empty_sub = Gtk.Label(label='Click  +  or press Ctrl+N to create one')
        empty_sub.get_style_context().add_class("empty-state-subtitle")
        empty_box.pack_start(empty_sub, False, False, 0)

        self.stack.add_named(empty_box, "empty")

        # Status bar
        self.status_label = Gtk.Label()
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class("status-bar")
        vbox.pack_end(self.status_label, False, False, 0)

        self._update_nvidia_bar()
        self._update_status()
        self._refresh_list()
        self.show_all()

    def _add_action(self, name: str, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", lambda a, p: callback())
        self.add_action(action)

    # -- NVIDIA info bar --

    def _update_nvidia_bar(self):
        if not self.manager.is_nvidia():
            return

        status = self.manager.nvidia_setup_status()
        if status == "Setup required":
            self.nvidia_info_label.set_markup(
                "<b>NVIDIA GPU:</b> One-time setup is required to enable virtual outputs."
            )
            self.nvidia_info_bar.set_no_show_all(False)
            self.nvidia_info_bar.show_all()
        elif status == "Restart required":
            self.nvidia_info_label.set_markup(
                "<b>NVIDIA:</b> Configuration applied. Log out and back in to activate."
            )
            self.nvidia_info_bar.set_message_type(Gtk.MessageType.INFO)
            self.nvidia_info_bar.set_no_show_all(False)
            self.nvidia_info_bar.show_all()
        else:
            self.nvidia_info_bar.hide()

    def _on_nvidia_info_response(self, bar, response_id):
        if response_id == 1:
            self._on_nvidia_setup()

    # -- List refresh --

    def _refresh_list(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)

        self.manager.refresh()

        if self.manager.managed_displays:
            for vd in self.manager.managed_displays:
                self.listbox.add(DisplayCard(vd, self._on_remove_display, self._on_toggle_display))
            self.stack.set_visible_child_name("list")
        else:
            self.stack.set_visible_child_name("empty")

        self.listbox.show_all()
        self._update_status()
        self._update_nvidia_bar()

    def _update_status(self):
        server = detect_display_server()
        gpu = self.manager.gpu_vendor.upper()
        n_managed = len(self.manager.managed_displays)
        try:
            n_available = len(self.manager.get_available_outputs())
        except Exception:
            n_available = 0

        parts = [f"GPU: {gpu}", f"Session: {server.upper()}"]
        parts.append(f"Virtual: {n_managed}")
        parts.append(f"Available: {n_available}")

        if self.manager.is_nvidia():
            parts.append(f"NVIDIA: {self.manager.nvidia_setup_status()}")

        self.status_label.set_text("    ".join(parts))

    # -- Add display --

    def _on_add_clicked(self, _btn):
        if not check_xrandr_available():
            self._show_error(
                "xrandr not found",
                "xrandr is required but was not found.\n\n"
                "Install it with your package manager:\n"
                "  sudo apt install x11-xserver-utils\n"
                "  sudo pacman -S xorg-xrandr\n"
                "  sudo dnf install xrandr"
            )
            return

        # NVIDIA: check if setup is needed
        if self.manager.is_nvidia():
            if self.manager.nvidia_needs_setup():
                self._on_nvidia_setup()
                return
            if not self.manager.nvidia_is_setup_active():
                self._show_info(
                    "Restart Required",
                    "NVIDIA virtual output configuration has been written but "
                    "is not yet active.\n\n"
                    "Please log out and back in, then try again."
                )
                return
            # If no available outputs, offer to add more via setup
            if not self.manager.get_available_outputs():
                candidates = self.manager.nvidia_get_virtual_output_candidates()
                if candidates:
                    dialog = Gtk.MessageDialog(
                        transient_for=self, modal=True,
                        message_type=Gtk.MessageType.INFO,
                        buttons=Gtk.ButtonsType.NONE,
                        text="No available outputs",
                    )
                    dialog.format_secondary_text(
                        "All configured virtual outputs are in use.\n\n"
                        "You can add more virtual outputs through the "
                        "NVIDIA setup. A logout/login will be required "
                        "for new outputs to become available."
                    )
                    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
                    btn = dialog.add_button("Add More Outputs", Gtk.ResponseType.OK)
                    btn.get_style_context().add_class("suggested-action")
                    response = dialog.run()
                    dialog.destroy()
                    if response == Gtk.ResponseType.OK:
                        self._on_nvidia_setup()
                    return

        dialog = AddDisplayDialog(self, self.manager)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            values = dialog.get_values()
            dialog.destroy()
            try:
                self.manager.create_display(
                    width=values["width"],
                    height=values["height"],
                    refresh=values["refresh"],
                    output=values["output"],
                    position=values["position"],
                    relative_to=values["relative_to"],
                    reduced_blanking=values["reduced_blanking"],
                )
                self._refresh_list()
            except RuntimeError as e:
                self._show_error("Failed to create display", str(e))
        else:
            dialog.destroy()

    # -- Remove display --

    def _on_remove_display(self, vd: VirtualDisplay):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f"Remove {vd.output}?",
        )
        dialog.format_secondary_text(
            f"This will disable the virtual display at "
            f"{vd.width}x{vd.height} @ {vd.refresh:.0f}Hz."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        rm = dialog.add_button("Remove", Gtk.ResponseType.OK)
        rm.get_style_context().add_class("destructive-action")

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            try:
                self.manager.remove_display(vd)
                self._refresh_list()
            except RuntimeError as e:
                self._show_error("Error removing display", str(e))

    # -- Toggle display --

    def _on_toggle_display(self, vd: VirtualDisplay):
        try:
            if vd.active:
                self.manager.disable_display(vd)
            else:
                self.manager.enable_display(vd)
            self._refresh_list()
        except RuntimeError as e:
            action = "disable" if vd.active else "enable"
            self._show_error(f"Failed to {action} display", str(e))

    # -- NVIDIA setup/teardown --

    def _on_nvidia_setup(self):
        dialog = NvidiaSetupDialog(self, self.manager)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            outputs = dialog.get_selected_outputs()
            dialog.destroy()
            if not outputs:
                self._show_error("No outputs selected",
                                 "Select at least one output for virtual displays.")
                return
            try:
                msg = self.manager.nvidia_setup(outputs)
                self._show_info("Setup Complete", msg)
                self._refresh_list()
            except RuntimeError as e:
                self._show_error("Setup Failed", str(e))
        else:
            dialog.destroy()

    def _on_nvidia_teardown(self):
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Remove NVIDIA virtual output configuration?",
        )
        dialog.format_secondary_text(
            "This removes the xorg.conf.d file and virtual EDID.\n"
            "Virtual outputs will no longer be available after your next login."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        rm = dialog.add_button("Remove Config", Gtk.ResponseType.OK)
        rm.get_style_context().add_class("destructive-action")

        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.OK:
            try:
                msg = self.manager.nvidia_teardown()
                self._show_info("Config Removed", msg)
                self._refresh_list()
            except RuntimeError as e:
                self._show_error("Removal Failed", str(e))

    # -- Menu actions --

    def _on_refresh(self):
        self._refresh_list()

    def _on_remove_all(self):
        if not self.manager.managed_displays:
            return
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Remove all virtual displays?",
        )
        dialog.format_secondary_text(
            f"This will remove all {len(self.manager.managed_displays)} "
            f"managed virtual display(s)."
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        btn = dialog.add_button("Remove All", Gtk.ResponseType.OK)
        btn.get_style_context().add_class("destructive-action")

        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.manager.remove_all()
            self._refresh_list()

    def _on_about(self):
        about = Gtk.AboutDialog(
            transient_for=self, modal=True,
            program_name=__app_name__,
            version=__version__,
            comments=(
                "Create and manage virtual displays on Linux.\n"
                "Supports NVIDIA, AMD, and Intel GPUs.\n"
                "Works with VR, OBS, Sunshine, and desktop sharing."
            ),
            website="https://github.com/VirtualDrivers/Linux-Virtual-Display-Driver",
            website_label="GitHub",
            license_type=Gtk.License.GPL_3_0,
            authors=["Mike Rodriguez (MikeTheTech)", "VirtualDrivers contributors"],
            logo_icon_name="video-display",
        )
        about.run()
        about.destroy()

    # -- Helpers --

    def _show_error(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()

    def _show_info(self, title: str, message: str):
        d = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        d.format_secondary_text(message)
        d.run()
        d.destroy()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class VDDApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.manager = DisplayManager()
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(CSS.encode())
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_activate(self):
        if not self.window:
            self.window = MainWindow(self, self.manager)
        self.window.present()


def main():
    app = VDDApplication()
    return app.run(sys.argv)
