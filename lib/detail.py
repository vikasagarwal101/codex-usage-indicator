import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk

from .config import fmt_duration, fmt_pct, fmt_reset, window_title

_shared_css_provider = None
_css_applied = False


def _get_shared_css_provider():
    global _shared_css_provider
    if _shared_css_provider is None:
        _shared_css_provider = Gtk.CssProvider()
        _shared_css_provider.load_from_data(
            b"""
            .stat-frame {
                padding: 14px 18px;
                border-radius: 8px;
                background: alpha(@theme_fg_color, 0.05);
                margin-bottom: 8px;
            }
            .stat-title { font-weight: bold; font-size: 1.0em; }
            .stat-value { font-size: 1.8em; font-weight: bold; }
            .dim { opacity: 0.65; font-size: 0.9em; }
            progressbar trough { min-height: 8px; border-radius: 4px; }
            progressbar progress { min-height: 8px; border-radius: 4px; }
            .badge {
                padding: 2px 8px;
                border-radius: 4px;
                background: alpha(@theme_fg_color, 0.10);
                font-size: 0.85em;
                font-weight: bold;
            }
        """
        )
    return _shared_css_provider


def _apply_shared_css():
    global _css_applied
    if _css_applied:
        return
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(
            screen,
            _get_shared_css_provider(),
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        _css_applied = True


class DetailWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(title="Codex Usage Details", application=app)
        self.set_default_size(480, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.data = None
        self._w = {}
        self._build()

    def _build(self):
        _apply_shared_css()

        header = Gtk.HeaderBar(title="Codex Usage Details", show_close_button=True)
        self.set_titlebar(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_margin_start(16)
        box.set_margin_end(16)

        self._build_account(box)
        self._build_window(box, "primary")
        self._build_window(box, "secondary")
        self._build_status(box)

        scroll.add(box)
        self.add(scroll)

    def _frame(self, parent, title):
        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        frame.get_style_context().add_class("stat-frame")
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.get_style_context().add_class("stat-title")
        frame.pack_start(lbl, False, False, 0)
        parent.pack_start(frame, False, False, 0)
        return frame

    def _build_account(self, parent):
        f = self._frame(parent, "Account & Subscription")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._w["plan"] = Gtk.Label(label="--", xalign=0)
        self._w["plan"].get_style_context().add_class("badge")
        row.pack_start(self._w["plan"], False, False, 0)
        f.pack_start(row, False, False, 2)

        self._w["account"] = Gtk.Label(label="--", xalign=0)
        self._w["account"].get_style_context().add_class("dim")
        f.pack_start(self._w["account"], False, False, 0)

        self._w["limit_status"] = Gtk.Label(label="--", xalign=0)
        self._w["limit_status"].get_style_context().add_class("dim")
        f.pack_start(self._w["limit_status"], False, False, 0)

    def _build_window(self, parent, key):
        f = self._frame(parent, key.title())
        self._w[f"{key}_frame"] = f

        self._w[f"{key}_lbl"] = Gtk.Label(label="--%")
        self._w[f"{key}_lbl"].get_style_context().add_class("stat-value")
        self._w[f"{key}_lbl"].set_xalign(0)
        f.pack_start(self._w[f"{key}_lbl"], False, False, 2)

        self._w[f"{key}_bar"] = Gtk.ProgressBar()
        f.pack_start(self._w[f"{key}_bar"], False, False, 2)

        self._w[f"{key}_duration"] = Gtk.Label(label="Window: --", xalign=0)
        f.pack_start(self._w[f"{key}_duration"], False, False, 0)

        self._w[f"{key}_reset"] = Gtk.Label(label="Resets in: --", xalign=0)
        self._w[f"{key}_reset"].get_style_context().add_class("dim")
        f.pack_start(self._w[f"{key}_reset"], False, False, 0)

    def _build_status(self, parent):
        self._w["status"] = Gtk.Label(label="", xalign=0)
        self._w["status"].get_style_context().add_class("dim")
        parent.pack_start(self._w["status"], False, False, 4)

    def update_data(self, d):
        self.data = d
        W = self._w

        plan_str = str(d.get("plan_type", "unknown")).upper()
        W["plan"].set_label(f"ChatGPT {plan_str}")
        account = d.get("email") or d.get("account_type", "")
        limit_name = d.get("limit_name") or "Codex"
        W["account"].set_label(f"Account: {account} ({limit_name})")

        if d.get("limit_reached"):
            W["limit_status"].set_label("Status: Quota Limit Reached")
        else:
            W["limit_status"].set_label("Status: Quota Active & Normal")

        self._update_window("primary", d.get("primary"))
        self._update_window("secondary", d.get("secondary"))

        W["status"].set_label(
            f"Updated {d['ts'].strftime('%H:%M:%S')} via {d.get('source', 'Codex')}"
        )
        self.show_all()

    def _update_window(self, key, window):
        W = self._w
        if not window:
            if key == "secondary":
                W[f"{key}_frame"].hide()
            else:
                W[f"{key}_lbl"].set_label("Unavailable")
                W[f"{key}_bar"].set_fraction(0)
                W[f"{key}_duration"].set_label("Window: --")
                W[f"{key}_reset"].set_label("Resets in: --")
            return

        W[f"{key}_frame"].show()
        pct = window.get("used_pct") or 0
        dur_mins = window.get("duration_mins")
        title = window_title(dur_mins)
        if dur_mins == 10080:
            title = "Weekly Quota (7-Day Cycle)"
        elif dur_mins == 300:
            title = "Session Window (5-Hour Rolling)"

        W[f"{key}_lbl"].set_label(f"{fmt_pct(pct)} Used")
        W[f"{key}_bar"].set_fraction(min(pct / 100.0, 1.0))
        W[f"{key}_duration"].set_label(
            f"{title}: {fmt_duration(dur_mins)} ({100 - pct}% remaining)"
        )
        W[f"{key}_reset"].set_label(
            f"Resets in: {fmt_reset(window.get('reset_sec'))}"
        )
