# OpenAI Codex Usage Indicator

A GNOME panel indicator for monitoring your OpenAI Codex usage limits through the Codex CLI app-server API.

Shows up in your top bar as `CDX <percent>%`. Click it for the dropdown menu, or open the detail window.

## Menu Preview

```text
 Top bar:  CDX 4%
                +---------------------------------+
                | OpenAI Codex (PLUS)             |
                | Account: you@example.com        |
                |---------------------------------|
                | Session Usage: 4% used          |
                |   Resets in: 2h 04m             |
                | Weekly Usage: 23% used          |
                |   Resets in: 5d 20h             |
                |---------------------------------|
                | Open Details Window             |
                | Refresh Now                     |
                | Settings...                     |
                |---------------------------------|
                | Updated 14:32:05                |
                | Quit                            |
                +---------------------------------+
```

## Features

- Panel indicator: lives in your GNOME top bar.
- Session usage: tracks the primary Codex usage window, currently returned as 300 minutes.
- Weekly usage: tracks the secondary Codex usage window, currently returned as 10080 minutes.
- Banked resets: lists available resets with award and expiry times in the menu. Select one and confirm **Use reset** to redeem it; Cancel is the default. Redemption refreshes usage and is never triggered during automatic refresh.
- Account metadata: shows Codex account type, email, and plan type.
- Detail window: GTK window with progress bars and banked reset details/actions.
- Open Codex Console menu item (`https://chatgpt.com/codex`).
- Top-bar warning marker: `*` at 80%+ and `!` at 90%+ usage.
- One-shot desktop notifications when usage crosses warning/critical thresholds or a new refresh error appears.
- Auto-refresh: configurable interval, default 5 minutes.
- Autostart: optional login startup entry.

## Requirements

- Ubuntu 24.04+ / GNOME 45+
- Python 3.10+
- `python3-gi`, `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1`
- The `ubuntu-appindicators` GNOME Shell extension
- Codex CLI installed and logged in with `codex login`

## Install

```bash
chmod +x install.sh
./install.sh
```

This will:

1. Check/install GTK indicator dependencies.
2. Create a desktop entry.
3. Optionally enable autostart on login.

## Configure

No API key is stored by this indicator. It uses your existing Codex CLI login from `~/.codex/auth.json`.

If `codex` is not on PATH, click the indicator, open **Settings...**, and set the full Codex CLI path.

Manual config:

```bash
mkdir -p ~/.config/codex-usage-widget
cp config.example.json ~/.config/codex-usage-widget/config.json
```

## Config Options

| Key | Default | Description |
|---|---|---|
| `codex_path` | `codex` | Codex CLI executable path |
| `refresh_interval` | `300` | Seconds between auto-refreshes |

## Run

```bash
python3 codex-usage-indicator.py
```

## Diagnostics

Run a non-secret auth check without launching GTK:

```bash
python3 codex-usage-indicator.py --check-auth
```

For machine-readable output:

```bash
python3 codex-usage-indicator.py --check-auth --json
```

The diagnostic checks the Codex CLI path, whether the auth file exists, which
usage source works, and whether primary/secondary usage windows are present. It
does not print OAuth tokens or your email address.

## How It Works

Prefers the private Codex usage endpoint used by Codex clients, then falls back to the Codex CLI app-server JSON-RPC API if the direct OAuth call fails.

Configuration is saved to `~/.config/codex-usage-widget/config.json` with
`0600` permissions.

Direct endpoint:

| Endpoint | Data |
|---|---|
| `GET https://chatgpt.com/backend-api/wham/usage` | Plan, account, primary/secondary usage windows and reset countdowns |

Fallback app-server methods:

| Method | Data |
|---|---|
| `account/read` | Account type, email, plan type, auth requirement |
| `account/rateLimits/read` | Primary/secondary usage windows, banked-reset details, credits, rate-limit status |
| `account/rateLimitResetCredit/consume` | Redeem one selected banked reset after confirmation |

Observed direct API response shape:

```json
{
  "plan_type": "plus",
  "rate_limit": {
    "allowed": true,
    "limit_reached": false,
    "primary_window": { "used_percent": 27, "limit_window_seconds": 18000, "reset_after_seconds": 17391, "reset_at": 1779673055 },
    "secondary_window": { "used_percent": 27, "limit_window_seconds": 604800, "reset_after_seconds": 517395, "reset_at": 1780173059 }
  },
  "code_review_rate_limit": null,
  "additional_rate_limits": null,
  "credits": {
    "has_credits": false,
    "unlimited": false,
    "overage_limit_reached": false,
    "balance": "0",
    "approx_local_messages": [0],
    "approx_cloud_messages": [0]
  },
  "spend_control": { "reached": false, "individual_limit": null },
  "rate_limit_reached_type": null,
  "rate_limit_reset_credits": { "available_count": 0 }
}
```

Observed Codex CLI `0.133.0` fallback response shape:

```json
{
  "rateLimits": {
    "limitId": "codex",
    "primary": { "usedPercent": 4, "windowDurationMins": 300, "resetsAt": 1779673056 },
    "secondary": { "usedPercent": 23, "windowDurationMins": 10080, "resetsAt": 1780173060 },
    "credits": { "hasCredits": false, "unlimited": false, "balance": "0" },
    "planType": "plus",
    "rateLimitReachedType": null
  }
}
```

## Project Structure

```text
├── codex-usage-indicator.py
├── lib/
│   ├── indicator.py
│   ├── api.py
│   ├── config.py
│   ├── detail.py
│   └── settings.py
├── config.example.json
├── install.sh
├── README.md
└── LICENSE
```

## License

MIT
