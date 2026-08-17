import os
import queue
import argparse
import json
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")

from gi.repository import AyatanaAppIndicator3 as AppIndicator, Gio, GLib, Gtk

from .api import APIAuthError, APIClient, APIError
from .config import (
    fmt_duration,
    fmt_pct,
    fmt_reset,
    load_config,
    save_config,
    window_title,
)
from .detail import DetailWindow
from .settings import SettingsWindow

APP_ID = "com.openai.codex.usage-widget"
INDICATOR_ID = "codex-usage-indicator"
CONSOLE_URL = "https://chatgpt.com/codex"


class CodexApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._config = load_config()
        self._client = APIClient(self._config.get("codex_path", "codex"))
        self._data = None
        self._indicator = None
        self._win = None
        self._timer_id = None
        self._fetch_queue = queue.Queue()
        self._fetch_shutdown = False
        self._fetch_thread = None
        self._last_error = ""
        self._last_threshold_notice = ""

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

        mi = Gtk.MenuItem(label="Open Codex Console")
        mi.connect("activate", self._on_open_console)
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

        M["status"].set_label(
            f"Updated {d['ts'].strftime('%H:%M:%S')} via {d.get('source', 'Codex')}"
        )

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
        self._start_fetch_worker()
        self._fetch_queue.put("refresh")

    def _start_fetch_worker(self):
        if self._fetch_thread is not None and self._fetch_thread.is_alive():
            return
        self._fetch_shutdown = False
        self._fetch_thread = threading.Thread(target=self._fetch_worker, daemon=True)
        self._fetch_thread.start()

    def _fetch_worker(self):
        while not self._fetch_shutdown:
            try:
                self._fetch_queue.get(timeout=1)
            except queue.Empty:
                continue
            if self._fetch_shutdown:
                break
            try:
                data = self._client.fetch_all()
                GLib.idle_add(self._on_data, data)
            except APIAuthError as e:
                GLib.idle_add(self._on_error, str(e))
            except APIError as e:
                GLib.idle_add(self._on_error, str(e))
            finally:
                self._fetch_queue.task_done()

    def _on_data(self, data):
        self._data = data
        primary = data.get("primary") or {}
        self._last_error = ""
        self._indicator.set_label(_usage_label("CDX", primary.get("used_pct")), "")
        self._maybe_notify_threshold("Codex", primary.get("used_pct"))
        self._update_menu(data)
        if self._win:
            self._win.update_data(data)
        return False

    def _on_error(self, msg):
        self._indicator.set_label("CDX ERR", "")
        if msg != self._last_error:
            self._notify("Codex Usage Error", msg)
        self._last_error = msg
        self._set_status(self._error_status(msg))
        return False

    def _error_status(self, msg):
        if self._data and self._data.get("ts"):
            return f"Error: {msg} (last OK {self._data['ts'].strftime('%H:%M:%S')})"
        return f"Error: {msg}"

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

    def _on_open_console(self, _):
        Gtk.show_uri_on_window(None, CONSOLE_URL, Gtk.get_current_event_time())

    def _maybe_notify_threshold(self, name, pct):
        level = _threshold_level(pct)
        if not level:
            self._last_threshold_notice = ""
            return
        if level == self._last_threshold_notice:
            return
        self._last_threshold_notice = level
        self._notify(f"{name} usage {level}", f"{_usage_label(name, pct)} used")

    def _notify(self, title, body):
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        self.send_notification(title.lower().replace(" ", "-"), notification)

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
        self._fetch_shutdown = True
        if self._fetch_thread:
            self._fetch_thread.join(timeout=2)
        self.quit()


def main():
    parser = argparse.ArgumentParser(description="Codex usage indicator")
    parser.add_argument(
        "--check-auth",
        action="store_true",
        help="verify Codex auth and usage access without launching GTK",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit diagnostic output as JSON",
    )
    args = parser.parse_args()
    if args.check_auth:
        return check_auth(json_output=args.json)

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
    return app.run()


def check_auth(json_output=False):
    cfg = load_config()
    codex_path = cfg.get("codex_path", "codex")
    codex_home = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    auth_path = os.path.join(codex_home, "auth.json")
    result = {
        "app": "codex",
        "codex_path": codex_path,
        "auth_file_present": os.path.exists(auth_path),
        "console_url": CONSOLE_URL,
    }
    try:
        data = APIClient(codex_path).fetch_all()
    except APIError as e:
        result.update({"fetch_ok": False, "error": str(e)})
        _print_check_result("Codex auth check", result, json_output)
        return 1
    primary = data.get("primary") or {}
    secondary = data.get("secondary") or {}
    result.update(
        {
            "fetch_ok": True,
            "source": data.get("source") or "",
            "plan": data.get("plan_type") or "",
            "email_present": bool(data.get("email")),
            "primary_usage_present": primary.get("used_pct") is not None,
            "secondary_usage_present": secondary.get("used_pct") is not None,
        }
    )
    _print_check_result("Codex auth check", result, json_output)
    return 0


def _usage_label(prefix, pct):
    if pct is None:
        return f"{prefix} --"
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return f"{prefix} --"
    marker = "!" if value >= 90 else "*" if value >= 80 else ""
    return f"{prefix} {marker}{value:.0f}%"


def _threshold_level(pct):
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return ""
    if value >= 90:
        return "critical"
    if value >= 80:
        return "warning"
    return ""


def _print_check_result(title, result, json_output):
    if json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(title)
    for key, value in result.items():
        print(f"{key}: {value if value not in ('', None) else '--'}")
