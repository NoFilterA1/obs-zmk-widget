# ZMK Keyboard Widget for OBS

Real-time key-press visualizer for OBS Studio. Shows a live Corne split-keyboard diagram with layer indicators, mouse tracking, and a full theme editor — designed for ZMK keyboards over BLE or USB.

> Works with any ZMK split keyboard: **Corne**, **VTwin**, **Lily58**, etc.

![widget preview](docs/preview.png)

*(a live screenshot from OBS is even better here once you have one — swap it in any time)*

---

## Features

- **Key highlights** — each key glows on press, fades on release with a configurable trail
- **Layer detection** — BASE / LOWER / RAISE / ADJUST / RGB / STENO chips update automatically
- **Mouse layer** — cursor movement and button presses light up the Adjust layer keys
- **Layout auto-detection** — QWERTY / Russian / Colemak-DH synced from Hyprland
- **Theme editor** — full visual editor with 11 built-in themes, custom themes, live preview
- **Transparent background** — drops cleanly into any OBS scene

---

## How it works

```
ZMK keyboard (BLE / USB)
        │  evdev /dev/input/eventX
        ▼
  key-bridge.py  ──── WebSocket ws://localhost:8765 ────▶  obs-widget.html
        │                                                   (OBS Browser Source)
        └─────────────────────────────────────────────────▶  theme-editor.html
                                                            (regular browser)
```

`key-bridge.py` reads raw HID events via **evdev**, resolves layers and phantom-Shift pairs from ZMK's BLE HID encoding, and broadcasts JSON events over a local WebSocket. Both the widget and the theme editor connect to the same bridge.

---

## Requirements

| Requirement | Notes |
|---|---|
| Linux | evdev — no Windows / macOS support |
| Python 3.10+ | |
| OBS Studio with Browser Source | `obs-studio-browser` on Arch; built-in on Ubuntu |
| ZMK keyboard | Any ZMK device; tested on Corne BLE and VTwin |
| Hyprland *(optional)* | Required for automatic layout switching |

---

## Quick start

```bash
git clone https://github.com/NoFilterA1/obs-zmk-widget
cd obs-zmk-widget
bash install.sh
```

`install.sh` will:
1. Create a Python venv and install dependencies
2. Install and enable the `zmk-bridge.service` systemd user service
3. Add your user to the `input` group if needed

Then:
1. Open OBS → **Sources** → **+** → **Browser Source**
2. ✅ **Local file** → select `obs-widget.html`
3. Width **920**, Height **200** → **OK**
4. Open `theme-editor.html` in a browser to customize

---

## Manual setup

### 1. Input group

```bash
sudo usermod -a -G input $USER
# log out and back in after this
```

### 2. Python dependencies

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 3. Systemd service

```bash
# ZMK / BLE keyboards (Corne, VTwin, etc.)
sed "s|INSTALL_DIR|$PWD|g" systemd/zmk-bridge.service \
    > ~/.config/systemd/user/zmk-bridge.service

# — OR — any wired keyboard
sed "s|INSTALL_DIR|$PWD|g" systemd/zmk-bridge-any.service \
    > ~/.config/systemd/user/zmk-bridge-any.service

systemctl --user daemon-reload
systemctl --user enable --now zmk-bridge.service
```

> Run **only one** service at a time — both bind to port 8765.

Verify it's working:
```bash
journalctl --user -u zmk-bridge.service -f
```

Expected output:
```
[kbd] connected: /dev/input/eventX  (Corne Keyboard)
[mou] connected: /dev/input/eventY  (Corne Mouse)
[lay] initial layout: qwerty
```

### 4. OBS Browser Source

| Setting | Value |
|---|---|
| Local file | ✅ checked |
| File path | `/path/to/obs-zmk-widget/obs-widget.html` |
| Width | 920 |
| Height | 200 |
| Background colour | `#00000000` (transparent) |

---

## Theme editor

Open `theme-editor.html` in any browser (Chromium recommended for accurate color pickers).

**Sidebar** — 11 built-in themes grouped by *Color* and *Animated*. Your custom themes live in *My Themes*.

**Controls:**
- Key idle colors — background, border, label
- Per-layer accent colors — the glow when a key on that layer is pressed
- Animation effect — None / Glow Pulse / Rainbow / Breathe
- Trail duration — how long the fade lasts after key release

**Live preview** — changes apply to the OBS widget in real time (requires the bridge to be running).

**Workflow:**
1. Pick a built-in theme as a starting point (click it in the sidebar)
2. Adjust colors — the mini keyboard and OBS widget update instantly
3. **Save theme** → built-in: prompts for a name and saves as custom; custom: overwrites
4. Click **+** to create a new custom theme as a copy of the current one
5. Double-click a custom theme in the sidebar to rename it

---

## Switching service modes

```bash
# Switch to BLE mode
systemctl --user stop zmk-bridge-any && systemctl --user start zmk-bridge

# Switch to any-keyboard mode
systemctl --user stop zmk-bridge && systemctl --user start zmk-bridge-any
```

---

## Running manually (no systemd)

```bash
venv/bin/python key-bridge.py              # ZMK / BLE keyboards
venv/bin/python key-bridge.py --any        # any keyboard
venv/bin/python key-bridge.py /dev/input/eventX  # specific device path
```

---

## OBS script (optional)

`obs-script.py` is an OBS Lua/Python script that starts and stops the bridge service automatically with OBS.

**Add it:** OBS → Tools → Scripts → **+** → select `obs-script.py`

You can choose BLE or any-keyboard mode from the script settings panel.

---

## Adapting to a different keyboard layout

The widget is built for the **Corne** (3×6 + 3 thumbs per half). To adapt it, edit these sections in `obs-widget.html`:

| Variable | Description |
|---|---|
| `LEFT_ROWS` / `RIGHT_ROWS` | Physical key grid (browser `e.code` values) |
| `LEFT_THUMBS` / `RIGHT_THUMBS` | Thumb cluster keys |
| `BASE_QWERTY` / `BASE_COLEMAK` / `BASE_RUSSIAN` | Label maps for base layer |
| `LAYER_LABELS` | Labels for layers 1–5 |
| `LAYER_REMAP` | OS key code → physical Corne position (for remapped layers) |
| `MOUSE_TO_POS` | Mouse button → physical key position on Adjust layer |

---

## Troubleshooting

**Status dot stays red**
```bash
systemctl --user status zmk-bridge
journalctl --user -u zmk-bridge -n 40
```

**No key events at all**
```bash
groups $USER   # must include 'input'
```

**Keyboard not detected**
```bash
# List all evdev devices
python3 -c "import evdev; [print(p, evdev.InputDevice(p).name) for p in evdev.list_devices()]"
# Pass the path manually
venv/bin/python key-bridge.py /dev/input/eventX
```

**RAISE layer symbols appear as LOWER when typing fast**

Increase `PHANTOM_MS` in `key-bridge.py` (line ~186):
```python
PHANTOM_MS = 0.030  # try 30 ms instead of 20 ms
```

**Layout not switching automatically**

Automatic layout detection requires **Hyprland**. On other compositors, click the **QWR** / **РУС** / **CMK** button in the widget manually to cycle layouts.

---

## Project structure

```
obs-zmk-widget/
├── obs-widget.html       # OBS Browser Source — the keyboard overlay
├── theme-editor.html     # Theme editor — open in a regular browser
├── key-bridge.py         # Python bridge: evdev → WebSocket
├── obs-script.py         # Optional OBS script to manage the service
├── launch-obs.sh         # Optional: launch OBS with NVIDIA offload + bridge start
├── requirements.txt      # Python deps (evdev, websockets)
├── install.sh            # One-command installer
└── systemd/
    ├── zmk-bridge.service      # For ZMK / BLE keyboards
    └── zmk-bridge-any.service  # For any keyboard
```

---

## License

[MIT](LICENSE)
