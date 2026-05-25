import os
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3 as AppIndicator, Gio, GLib, Gtk

from .api import APIAuthError, APIClient, APIError
from .config import fmt_duration, fmt_pct, fmt_reset, load_config, save_config, window_title
from .detail import DetailWindow
from .settings import SettingsWindow

APP_ID = "com.openai.codex.usage-widget"
INDICATOR_ID = "codex-usage-indicator"


class CodexApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._config = load_config()
        self._client = APIClient(self._config.get("codex_path", "codex"))
        self._data = None
        self._indicator = None
        self._win = None
        self._timer_id = None

    def do_activate(self):
        self.hold()
        icon = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "codex-usage-indicator.svg",
        )
        self._indicator = AppIndicator.Indicator.new(
            INDICATOR_ID,
            icon,
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._indicator.set_label("CDX --", "")
        self._indicator.set_title("Codex Usage")
        self._build_menu()
        self._indicator.set_menu(self._menu)
        self._refresh()
        self._schedule_refresh()

    def _build_menu(self):
        self._menu = Gtk.Menu()
        self._mi = {}

        self._mi["header"] = Gtk.MenuItem(label="OpenAI Codex")
        self._mi["header"].set_sensitive(False)
        self._menu.append(self._mi["header"])

        self._mi["account"] = Gtk.MenuItem(label="Account: --")
        self._mi["account"].set_sensitive(False)
        self._menu.append(self._mi["account"])
        self._menu.append(Gtk.SeparatorMenuItem())

        for key, label in [
            ("primary", "Session Usage: --"),
            ("primary_reset", "  Resets in: --"),
            ("secondary", "Weekly Usage: --"),
            ("secondary_reset", "  Resets in: --"),
        ]:
            self._mi[key] = Gtk.MenuItem(label=label)
            self._mi[key].set_sensitive(False)
            self._menu.append(self._mi[key])

        self._menu.append(Gtk.SeparatorMenuItem())

        mi = Gtk.MenuItem(label="Open Details Window")
        mi.connect("activate", self._on_detail)
        self._menu.append(mi)

        mi = Gtk.MenuItem(label="Refresh Now")
        mi.connect("activate", lambda _: self._refresh())
        self._menu.append(mi)

        mi = Gtk.MenuItem(label="Settings...")
        mi.connect("activate", self._on_settings)
        self._menu.append(mi)

        self._menu.append(Gtk.SeparatorMenuItem())
        self._mi["status"] = Gtk.MenuItem(label="")
        self._mi["status"].set_sensitive(False)
        self._menu.append(self._mi["status"])

        mi = Gtk.MenuItem(label="Quit")
        mi.connect("activate", self._on_quit)
        self._menu.append(mi)
        self._menu.show_all()

    def _update_menu(self, d):
        M = self._mi
        plan = d["plan_type"].upper()
        M["header"].set_label(f"OpenAI Codex ({plan})")
        M["account"].set_label(f"Account: {d['email'] or d['account_type']}")
        self._set_window_labels("primary", d["primary"])
        self._set_window_labels("secondary", d["secondary"])

        M["status"].set_label(f"Updated {d['ts'].strftime('%H:%M:%S')} via {d.get('source', 'Codex')}")

    def _set_window_labels(self, key, window):
        M = self._mi
        reset_key = f"{key}_reset"
        if not window:
            M[key].set_label(f"{key.title()} Usage: unavailable")
            M[reset_key].set_label("  Resets in: --")
            return
        title = window_title(window["duration_mins"])
        duration = fmt_duration(window["duration_mins"])
        M[key].set_label(f"{title}: {fmt_pct(window['used_pct'])} used ({duration})")
        M[reset_key].set_label(f"  Resets in: {fmt_reset(window['reset_sec'])}")

    def _set_status(self, msg):
        self._mi["status"].set_label(msg)

    def _refresh(self):
        self._set_status("Refreshing...")
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        try:
            data = self._client.fetch_all()
            GLib.idle_add(self._on_data, data)
        except APIAuthError as e:
            GLib.idle_add(self._on_error, str(e))
        except APIError as e:
            GLib.idle_add(self._on_error, str(e))

    def _on_data(self, data):
        self._data = data
        primary = data.get("primary") or {}
        label_pct = fmt_pct(primary.get("used_pct"))
        self._indicator.set_label(f"CDX {label_pct}", "")
        self._update_menu(data)
        if self._win:
            self._win.update_data(data)
        return False

    def _on_error(self, msg):
        self._indicator.set_label("CDX ERR", "")
        self._set_status(f"Error: {msg}")
        return False

    def _schedule_refresh(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        secs = self._config.get("refresh_interval", 300)
        self._timer_id = GLib.timeout_add_seconds(secs, self._auto_refresh)

    def _auto_refresh(self):
        self._refresh()
        return GLib.SOURCE_CONTINUE

    def _on_detail(self, _):
        if self._win:
            self._win.present()
            return
        self._win = DetailWindow(self)
        self._win.connect("destroy", self._on_win_close)
        if self._data:
            self._win.update_data(self._data)
        self._win.show_all()

    def _on_win_close(self, win):
        self._win = None

    def _on_settings(self, _):
        def on_save(cfg):
            self._config = cfg
            save_config(self._config)
            self._client = APIClient(self._config.get("codex_path", "codex"))
            self._refresh()
            self._schedule_refresh()

        win = SettingsWindow(self, on_save)
        win.show_all()

    def _on_quit(self, _):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
        self.quit()


def main():
    GLib.set_prgname(APP_ID)
    GLib.set_application_name("Codex Usage Indicator")

    icon_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "codex-usage-indicator.svg",
    )
    try:
        from gi.repository import GdkPixbuf

        Gtk.Window.set_default_icon(
            GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 128, 128)
        )
    except Exception:
        Gtk.Window.set_default_icon_name(APP_ID)

    app = CodexApp()
    app.run()
