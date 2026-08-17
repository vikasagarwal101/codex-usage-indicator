import json
import os
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/.config/codex-usage-widget")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULTS = {"codex_path": "codex", "refresh_interval": 300}


def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                cfg = json.load(f)
                for k, v in DEFAULTS.items():
                    cfg.setdefault(k, v)
                return cfg
    except Exception:
        pass
    return dict(DEFAULTS)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)
    try:
        os.chmod(CONFIG_FILE, 0o600)
    except OSError:
        pass


def fmt_pct(n):
    if n is None:
        return "--%"
    return f"{int(n)}%"


def fmt_balance(value):
    if value in (None, ""):
        return "--"
    return str(value)


def fmt_duration(minutes):
    if not minutes:
        return "Usage window"
    if minutes % 1440 == 0:
        days = minutes // 1440
        return f"{days} day{'s' if days != 1 else ''} window"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours} hour{'s' if hours != 1 else ''} window"
    return f"{minutes} min window"


def window_title(minutes):
    if minutes == 300:
        return "Session Usage"
    if minutes == 10080:
        return "Weekly Usage"
    return "Usage Window"


def fmt_reset(ts_seconds):
    if not ts_seconds:
        return "--"
    dt = datetime.fromtimestamp(ts_seconds)
    diff = dt - datetime.now()
    total_seconds = int(diff.total_seconds())
    if total_seconds < 0:
        return "now"

    d, rem = divmod(total_seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)

    if d > 0:
        return f"{d}d {h}h"
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m {s}s"
