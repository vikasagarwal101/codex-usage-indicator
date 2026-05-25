import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk

from .config import fmt_duration, fmt_pct, fmt_reset, window_title


class DetailWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(title="Codex Usage Details", application=app)
        self.set_default_size(460, 520)
        self.data = None
        self._w = {}
        self._build()

    def _build(self):
        screen = Gdk.Screen.get_default()
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .stat-frame {
                padding: 14px 18px;
                border-radius: 8px;
                background: alpha(@theme_fg_color, 0.05);
                margin-bottom: 8px;
            }
            .stat-title { font-weight: bold; font-size: 1.0em; }
            .stat-value { font-size: 1.8em; font-weight: bold; }
            .dim { opacity: 0.55; }
            progressbar trough { min-height: 8px; border-radius: 4px; }
            progressbar progress { min-height: 8px; border-radius: 4px; }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

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
        f = self._frame(parent, "Account")
        self._w["plan"] = Gtk.Label(label="--", xalign=0)
        self._w["plan"].get_style_context().add_class("stat-value")
        f.pack_start(self._w["plan"], False, False, 2)
        self._w["account"] = Gtk.Label(label="--", xalign=0)
        self._w["account"].get_style_context().add_class("dim")
        f.pack_start(self._w["account"], False, False, 0)

    def _build_window(self, parent, key):
        f = self._frame(parent, key.title())
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
        self._w["status"] = Gtk.Label(label="")
        self._w["status"].get_style_context().add_class("dim")
        parent.pack_start(self._w["status"], False, False, 4)

    def update_data(self, d):
        self.data = d
        W = self._w

        W["plan"].set_label(d["plan_type"].upper())
        account = d["email"] or d["account_type"]
        W["account"].set_label(f"{account} - {d['limit_name']}")
        self._update_window("primary", d["primary"])
        self._update_window("secondary", d["secondary"])

        W["status"].set_label(
            f"Updated {d['ts'].strftime('%H:%M:%S')} via {d.get('source', 'Codex')}"
        )
        self.show_all()

    def _update_window(self, key, window):
        W = self._w
        if not window:
            W[f"{key}_lbl"].set_label("Unavailable")
            W[f"{key}_bar"].set_fraction(0)
            W[f"{key}_duration"].set_label("Window: --")
            W[f"{key}_reset"].set_label("Resets in: --")
            return

        pct = window.get("used_pct") or 0
        title = window_title(window.get("duration_mins"))
        W[f"{key}_lbl"].set_label(f"{fmt_pct(pct)} Used")
        W[f"{key}_bar"].set_fraction(min(pct / 100, 1.0))
        W[f"{key}_duration"].set_label(
            f"{title}: {fmt_duration(window.get('duration_mins'))}"
        )
        W[f"{key}_reset"].set_label(f"Resets in: {fmt_reset(window.get('reset_sec'))}")
