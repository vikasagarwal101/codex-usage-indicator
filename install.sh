#!/bin/bash
set -e

APP_NAME="Codex Usage Indicator"
APP_ID="com.openai.codex.usage-widget"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${HOME}/.local/share/codex-usage-indicator"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
APP_DIR="${HOME}/.local/share/applications"
AUTOSTART_DIR="${HOME}/.config/autostart"

echo ""
echo "  =========================================="
echo "       Codex Usage Indicator Installer"
echo "  =========================================="
echo ""

echo "[1/5] Checking system dependencies..."

DEPS="python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1"
MISSING=""
for dep in $DEPS; do
    if ! dpkg -l "$dep" 2>/dev/null | grep -q '^ii'; then
        MISSING="$MISSING $dep"
    fi
done

if [ -n "$MISSING" ]; then
    echo "  Installing:$MISSING"
    pkexec apt-get install -y -qq $MISSING 2>/dev/null || {
        echo "  Could not auto-install. Please run:"
        echo "    sudo apt-get install$MISSING"
    }
else
    echo "  All dependencies present"
fi

if ! /usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("AyatanaAppIndicator3", "0.1"); from gi.repository import Gtk, AyatanaAppIndicator3'; then
    echo "  System Python GTK bindings unavailable. Install dependencies: $DEPS" >&2
    exit 1
fi

if ! command -v codex >/dev/null 2>&1; then
    echo ""
    echo "  Codex CLI was not found on PATH."
    echo "  Install it or set the full path in Settings after launch."
fi

echo "[2/5] Installing application files..."

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

cp -r "$SCRIPT_DIR/lib" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/codex-usage-indicator.py" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/codex-usage-indicator.py"

echo "  Installed to $INSTALL_DIR"

echo "[3/5] Installing application icon..."

mkdir -p "$ICON_DIR"
cp "$SCRIPT_DIR/codex-usage-indicator.svg" "$ICON_DIR/${APP_ID}.svg"
cp "$SCRIPT_DIR/blank-icon.svg" "$ICON_DIR/codex-blank-icon.svg"
cp "$SCRIPT_DIR/panel-icon.svg" "$INSTALL_DIR/panel-icon.svg"
cp "$SCRIPT_DIR/codex-usage-indicator.svg" "$INSTALL_DIR/codex-usage-indicator.svg"
gtk-update-icon-cache -f "${HOME}/.local/share/icons/hicolor/" 2>/dev/null || true

echo "  Icon installed"

echo "[4/5] Creating launcher..."

mkdir -p "$APP_DIR"
cat > "$APP_DIR/${APP_ID}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Panel indicator for OpenAI Codex usage limits
Exec=/usr/bin/python3 ${INSTALL_DIR}/codex-usage-indicator.py
Icon=${INSTALL_DIR}/codex-usage-indicator.svg
Terminal=false
Categories=Utility;System;
Keywords=codex;openai;usage;quota;rate limit;
StartupNotify=false
StartupWMClass=${APP_ID}
EOF

update-desktop-database "$APP_DIR" 2>/dev/null || true
echo "  Launcher created"

echo "[5/5] Autostart"
read -p "Start on login? [Y/n] " -r
AUTOSTART_REPLY="${REPLY:-y}"
echo

if [[ $AUTOSTART_REPLY =~ ^[Yy]$ ]]; then
    mkdir -p "$AUTOSTART_DIR"
    cp "$APP_DIR/${APP_ID}.desktop" "$AUTOSTART_DIR/${APP_ID}.desktop"
    echo "  Autostart enabled"
else
    rm -f "$AUTOSTART_DIR/${APP_ID}.desktop"
    echo "  Autostart skipped"
fi

read -p "Launch now? [Y/n] " -r
LAUNCH_REPLY="${REPLY:-y}"
echo

if [[ $LAUNCH_REPLY =~ ^[Yy]$ ]]; then
    pkill -f codex-usage-indicator.py 2>/dev/null || true
    sleep 1
    setsid /usr/bin/python3 "$INSTALL_DIR/codex-usage-indicator.py" </dev/null >/dev/null 2>&1 &
    echo "  Launched - look for CX in your top panel bar"
fi

echo ""
echo "  Done! You can also search '$APP_NAME' in Activities."
echo ""
