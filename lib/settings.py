import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from .config import load_config


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app, on_save):
        super().__init__(title="Codex Usage Settings", application=app)
        self.on_save_cb = on_save
        self.set_default_size(400, -1)
        self.set_border_width(0)
        self._build()

    def _build(self):
        header = Gtk.HeaderBar(title="Codex Usage Settings", show_close_button=True)
        save_btn = Gtk.Button(label="Save")
        save_btn.get_style_context().add_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)
        self.set_titlebar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)

        config = load_config()

        content.add(Gtk.Label(label="Codex CLI Path", xalign=0))
        self.path_entry = Gtk.Entry()
        self.path_entry.set_placeholder_text("codex")
        self.path_entry.set_text(config.get("codex_path", "codex"))
        self.path_entry.set_hexpand(True)
        content.add(self.path_entry)

        content.add(Gtk.Label(label="Refresh Interval (minutes)", xalign=0))
        adj = Gtk.Adjustment(
            value=config.get("refresh_interval", 300) / 60,
            lower=1,
            upper=60,
            step_increment=1,
            page_increment=5,
        )
        self.refresh_spin = Gtk.SpinButton(adjustment=adj)
        content.add(self.refresh_spin)

        hint = Gtk.Label(
            label="Uses your existing Codex CLI login. Run 'codex login' if auth is missing.",
            xalign=0,
        )
        hint.set_line_wrap(True)
        hint.get_style_context().add_class("dim")
        content.add(hint)

        self.add(content)

    def _on_save(self, _):
        cfg = {
            "codex_path": self.path_entry.get_text().strip() or "codex",
            "refresh_interval": int(self.refresh_spin.get_value() * 60),
        }
        self.on_save_cb(cfg)
        self.destroy()
