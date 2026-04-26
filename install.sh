#!/usr/bin/env bash
set -e

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ZMK Widget — installer"
echo "  Install path: $REPO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Python venv ────────────────────────────────────────
if [ ! -d "$REPO/venv" ]; then
  echo "[1/4] Creating Python venv..."
  python3 -m venv "$REPO/venv"
else
  echo "[1/4] venv already exists — skipping"
fi

echo "[2/4] Installing Python dependencies..."
"$REPO/venv/bin/pip" install -q -r "$REPO/requirements.txt"

# ── 2. systemd user services ─────────────────────────────
echo "[3/4] Installing systemd user services..."
SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

for svc in zmk-bridge.service zmk-bridge-any.service; do
  sed "s|INSTALL_DIR|$REPO|g" "$REPO/systemd/$svc" > "$SYSTEMD_DIR/$svc"
done

systemctl --user daemon-reload
systemctl --user enable zmk-bridge.service

# ── 3. input group ────────────────────────────────────────
echo "[4/4] Checking input group..."
if groups "$USER" | grep -qw input; then
  echo "      ✓ Already in 'input' group"
else
  echo "      Adding $USER to 'input' group..."
  sudo usermod -a -G input "$USER"
  echo "      ⚠  Log out and back in for this to take effect."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done! Start the bridge:"
echo "    systemctl --user start zmk-bridge.service"
echo ""
echo "  Then add obs-widget.html as a Browser Source in OBS."
echo "  Open theme-editor.html in a browser to customize."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
