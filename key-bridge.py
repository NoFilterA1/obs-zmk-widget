#!/usr/bin/env python3
"""
Corne keyboard widget bridge for OBS.
- Listens to Corne Keyboard + Corne Mouse via evdev
- Polls hyprctl for layout changes (qwerty / colemak_dh)
- Broadcasts all events over WebSocket to obs-corne.html

Requirements: pip install evdev websockets
"""

import asyncio
import glob
import json
import os
import sys
import websockets
import evdev
from evdev import InputDevice, categorize, ecodes

# ── evdev keyboard code → browser e.code ─────────────────────────────────────
EVDEV_TO_WEB = {
    'KEY_ESC': 'Escape',
    'KEY_1': 'Digit1', 'KEY_2': 'Digit2', 'KEY_3': 'Digit3',
    'KEY_4': 'Digit4', 'KEY_5': 'Digit5', 'KEY_6': 'Digit6',
    'KEY_7': 'Digit7', 'KEY_8': 'Digit8', 'KEY_9': 'Digit9', 'KEY_0': 'Digit0',
    'KEY_MINUS': 'Minus', 'KEY_EQUAL': 'Equal', 'KEY_BACKSPACE': 'Backspace',
    'KEY_TAB': 'Tab',
    'KEY_Q': 'KeyQ', 'KEY_W': 'KeyW', 'KEY_E': 'KeyE', 'KEY_R': 'KeyR',
    'KEY_T': 'KeyT', 'KEY_Y': 'KeyY', 'KEY_U': 'KeyU', 'KEY_I': 'KeyI',
    'KEY_O': 'KeyO', 'KEY_P': 'KeyP',
    'KEY_LEFTBRACE': 'BracketLeft', 'KEY_RIGHTBRACE': 'BracketRight',
    'KEY_ENTER': 'Enter', 'KEY_LEFTCTRL': 'ControlLeft',
    'KEY_A': 'KeyA', 'KEY_S': 'KeyS', 'KEY_D': 'KeyD', 'KEY_F': 'KeyF',
    'KEY_G': 'KeyG', 'KEY_H': 'KeyH', 'KEY_J': 'KeyJ', 'KEY_K': 'KeyK',
    'KEY_L': 'KeyL', 'KEY_SEMICOLON': 'Semicolon', 'KEY_APOSTROPHE': 'Quote',
    'KEY_GRAVE': 'Backquote', 'KEY_LEFTSHIFT': 'ShiftLeft',
    'KEY_BACKSLASH': 'Backslash',
    'KEY_Z': 'KeyZ', 'KEY_X': 'KeyX', 'KEY_C': 'KeyC', 'KEY_V': 'KeyV',
    'KEY_B': 'KeyB', 'KEY_N': 'KeyN', 'KEY_M': 'KeyM',
    'KEY_COMMA': 'Comma', 'KEY_DOT': 'Period', 'KEY_SLASH': 'Slash',
    'KEY_RIGHTSHIFT': 'ShiftRight', 'KEY_LEFTALT': 'AltLeft',
    'KEY_SPACE': 'Space', 'KEY_CAPSLOCK': 'CapsLock',
    'KEY_F1': 'F1',   'KEY_F2': 'F2',   'KEY_F3': 'F3',  'KEY_F4': 'F4',
    'KEY_F5': 'F5',   'KEY_F6': 'F6',   'KEY_F7': 'F7',  'KEY_F8': 'F8',
    'KEY_F9': 'F9',   'KEY_F10': 'F10', 'KEY_F11': 'F11','KEY_F12': 'F12',
    'KEY_RIGHTCTRL': 'ControlRight', 'KEY_RIGHTALT': 'AltRight',
    'KEY_LEFTMETA': 'MetaLeft', 'KEY_RIGHTMETA': 'MetaRight',
    'KEY_UP': 'ArrowUp', 'KEY_DOWN': 'ArrowDown',
    'KEY_LEFT': 'ArrowLeft', 'KEY_RIGHT': 'ArrowRight',
    'KEY_DELETE': 'Delete', 'KEY_INSERT': 'Insert',
    'KEY_HOME': 'Home', 'KEY_END': 'End',
    'KEY_PAGEUP': 'PageUp', 'KEY_PAGEDOWN': 'PageDown',
}

# ── Mouse button code → widget code ──────────────────────────────────────────
MOUSE_TO_WEB = {
    ecodes.BTN_LEFT:   'BtnLeft',
    ecodes.BTN_RIGHT:  'BtnRight',
    ecodes.BTN_MIDDLE: 'BtnMiddle',
    ecodes.BTN_SIDE:   'BtnSide',
    ecodes.BTN_EXTRA:  'BtnExtra',
}

# ── WebSocket state ───────────────────────────────────────────────────────────
clients: set = set()
current_layout: str = 'qwerty'  # global state — sent to new clients on connect
current_theme: dict = {}         # cached theme — sent to new widget clients on connect

async def ws_handler(websocket):
    global current_theme
    clients.add(websocket)
    print(f"[ws] client connected ({len(clients)} total)")
    # Send current layout and theme immediately so widget starts in correct state
    try:
        await websocket.send(json.dumps({'type': 'layout', 'layout': current_layout}))
        if current_theme:
            await websocket.send(json.dumps({'type': 'UPDATE_THEME', 'theme': current_theme}))
    except Exception:
        pass
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                # Cache theme updates so new clients get the latest theme
                if data.get('type') == 'UPDATE_THEME' and data.get('theme'):
                    current_theme = data['theme']
                # Broadcast incoming message to everyone else
                await broadcast(data, exclude=websocket)
            except Exception as e:
                print(f"[ws] error processing message: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"[ws] client disconnected ({len(clients)} remaining)")

async def broadcast(msg: dict, exclude=None):
    if not clients:
        return
    data = json.dumps(msg)
    dead = set()
    for ws in clients.copy():
        if ws == exclude:
            continue
        try:
            await ws.send(data)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)

# ── Device finder ─────────────────────────────────────────────────────────────
ANY_MODE = False  # set to True via --any flag

def _scan_keyboards():
    """Find ALL matching keyboard devices.
    Default mode : all ZMK keyboards (name contains 'zmk' or 'corne').
    --any mode   : all non-ZMK keyboards."""
    REQUIRED = (ecodes.KEY_A, ecodes.KEY_Z, ecodes.KEY_SPACE)
    results = []
    for path in evdev.list_devices():
        try:
            d = InputDevice(path)
            keys = d.capabilities().get(ecodes.EV_KEY, [])
            if not all(k in keys for k in REQUIRED):
                continue
            is_zmk = any(w in d.name.lower() for w in ('zmk', 'corne'))
            if ANY_MODE and not is_zmk:
                results.append(d)
            elif not ANY_MODE and is_zmk:
                results.append(d)
        except Exception:
            continue
    return results

def _scan_paired_mouse(kbd_name: str = ''):
    """Find the mouse HID device that belongs to the same keyboard.
    Matches by shared name prefix and mouse capabilities.
    ZMK BLE may name the mouse device without 'mouse' in the name — we detect
    by capability (EV_REL or BTN_LEFT/BTN_RIGHT) instead of name alone."""
    prefix = kbd_name.lower().replace('keyboard', '').strip()
    best_fallback = None
    for path in evdev.list_devices():
        try:
            d = InputDevice(path)
            name = d.name.lower()
            caps = d.capabilities()
            has_mouse_caps = (
                evdev.ecodes.EV_REL in caps or
                any(c in caps.get(evdev.ecodes.EV_KEY, [])
                    for c in (evdev.ecodes.BTN_LEFT, evdev.ecodes.BTN_RIGHT))
            )
            if not has_mouse_caps:
                continue
            is_zmk = any(w in name for w in ('corne', 'zmk'))
            is_named_mouse = 'mouse' in name
            # Accept any ZMK-named device with mouse caps, or any 'mouse'-named device
            if not (is_zmk or is_named_mouse):
                continue
            if prefix and prefix in name:
                return d            # exact paired device
            if best_fallback is None and is_zmk:
                best_fallback = d   # any ZMK device with mouse caps as fallback
        except Exception:
            continue
    return best_fallback

active_kbd_name: str = ''  # shared with mouse_loop for pairing

async def _wait_for_keyboards(path_hint=None):
    if path_hint:
        return [InputDevice(path_hint)]
    while True:
        devs = _scan_keyboards()
        if devs:
            return devs
        label = "any (non-ZMK) keyboard" if ANY_MODE else "ZMK keyboard"
        print(f"[kbd] {label} not found — retrying in 3s…")
        await asyncio.sleep(3)

# ── Event readers ─────────────────────────────────────────────────────────────
# ── Phantom Shift detection ───────────────────────────────────────────────────
# ZMK sends RAISE symbols as Shift+key in a SINGLE HID report (≤8ms apart).
# We BUFFER the ShiftLeft broadcast for 10ms. If another key arrives within
# that window → it's a phantom pair (RAISE layer): cancel the buffer, send
# only the real key with layer:'raise'. Otherwise flush the buffer normally.
PHANTOM_MS = 0.020  # 20ms — 2.5× BLE poll (7.5ms), well below human Shift+key (>30ms)
import time as _time

_shift_tasks: dict[str, asyncio.Task] = {}  # pending delayed-send tasks
_shift_times: dict[str, float] = {}         # press timestamps
_phantom_shifts: set[str] = set()           # shifts that were buffered & cancelled

async def _flush_shift(web_code: str):
    """Fires after PHANTOM_MS if not cancelled — real Shift press."""
    await asyncio.sleep(PHANTOM_MS)
    _shift_tasks.pop(web_code, None)
    _shift_times.pop(web_code, None)
    await broadcast({'type': 'keydown', 'code': web_code})

async def process_key(web_code: str, state: str, ev_time: float = 0.0):
    # Use kernel event timestamp (not monotonic) so event-loop delays don't
    # inflate the Shift→Digit gap and cause false phantom misses.

    if state == 'down':
        if web_code in ('ShiftLeft', 'ShiftRight'):
            _shift_times[web_code] = ev_time
            # Buffer — will be flushed after PHANTOM_MS unless cancelled
            task = asyncio.create_task(_flush_shift(web_code))
            _shift_tasks[web_code] = task

        else:
            # Check if a buffered Shift is pending (phantom pair)
            phantom = None
            for sh in ('ShiftLeft', 'ShiftRight'):
                if sh in _shift_tasks and sh in _shift_times:
                    if (ev_time - _shift_times[sh]) < PHANTOM_MS:
                        phantom = sh
                        break

            if phantom:
                # Cancel buffer, never send ShiftLeft
                _shift_tasks.pop(phantom).cancel()
                _shift_times.pop(phantom, None)
                _phantom_shifts.add(phantom)
                await broadcast({'type': 'keydown', 'code': web_code, 'layer': 'raise'})
            elif _phantom_shifts:
                # Rollover: phantom Shift still held by ZMK (multiple RAISE keys in one
                # HID report). Shift was already consumed for the first key — tag the rest.
                await broadcast({'type': 'keydown', 'code': web_code, 'layer': 'raise'})
            else:
                await broadcast({'type': 'keydown', 'code': web_code})

    else:  # up
        if web_code in ('ShiftLeft', 'ShiftRight'):
            # Cancel buffer if released before flush (e.g. very quick tap)
            task = _shift_tasks.pop(web_code, None)
            if task:
                task.cancel()
            _shift_times.pop(web_code, None)
            if web_code in _phantom_shifts:
                _phantom_shifts.discard(web_code)
                return  # suppress phantom keyup — was never sent
        await broadcast({'type': 'keyup', 'code': web_code})


async def read_keyboard(dev: InputDevice):
    print(f"[kbd] {dev.path}  ({dev.name})")
    try:
        async for event in dev.async_read_loop():
            if event.type != ecodes.EV_KEY:
                continue
            key_event = categorize(event)
            name = ecodes.KEY.get(event.code)
            if isinstance(name, list):
                name = name[0]
            if not isinstance(name, str):
                continue
            web_code = EVDEV_TO_WEB.get(name)
            if not web_code:
                continue
            ev_time = event.sec + event.usec / 1_000_000
            if key_event.keystate == key_event.key_down:
                await process_key(web_code, 'down', ev_time)
            elif key_event.keystate == key_event.key_up:
                await process_key(web_code, 'up', ev_time)
    except OSError:
        print("[kbd] Corne Keyboard disconnected — waiting for reconnect…")

# ── Mouse movement → simulated keydown/keyup ──────────────────────────────
# EV_REL X/Y → 'MouseLeft'/'MouseRight'/'MouseUp'/'MouseDown' keydown events.
# Each direction key auto-releases after MOVE_HOLD_MS with no new movement.
_REL_TO_CODE = {
    ecodes.REL_X: ('MouseLeft', 'MouseRight'),  # (negative, positive)
    ecodes.REL_Y: ('MouseUp',   'MouseDown'),
}
MOVE_HOLD_MS = 0.120  # 120ms — auto-release if no further movement
_move_keys: dict[str, asyncio.Task] = {}

async def _expire_move_key(code: str):
    await asyncio.sleep(MOVE_HOLD_MS)
    _move_keys.pop(code, None)
    await broadcast({'type': 'keyup', 'code': code})

async def _handle_rel(rel_code: int, value: int):
    pair = _REL_TO_CODE.get(rel_code)
    if not pair:
        # wheel or other axis — just switch layer
        await broadcast({'type': 'mouse_move'})
        return
    code = pair[0] if value < 0 else pair[1]
    if code not in _move_keys:
        await broadcast({'type': 'keydown', 'code': code})
    elif _move_keys[code]:
        _move_keys[code].cancel()
    _move_keys[code] = asyncio.create_task(_expire_move_key(code))

async def read_mouse(dev: InputDevice):
    print(f"[mou] {dev.path}  ({dev.name})")
    try:
        async for event in dev.async_read_loop():
            if event.type == ecodes.EV_REL:
                if event.value != 0:
                    await _handle_rel(event.code, event.value)
                continue
            if event.type != ecodes.EV_KEY:
                continue
            web_code = MOUSE_TO_WEB.get(event.code)
            if not web_code:
                continue
            key_event = categorize(event)
            if key_event.keystate == key_event.key_down:
                await broadcast({'type': 'keydown', 'code': web_code})
            elif key_event.keystate == key_event.key_up:
                await broadcast({'type': 'keyup', 'code': web_code})
    except OSError:
        print("[mou] Corne Mouse disconnected")

# ── Layout polling ────────────────────────────────────────────────────────────
def _keymap_to_layout(keymap: str) -> str:
    """Map Hyprland active_keymap name to widget layout id."""
    km = keymap.lower()
    if 'russian' in km:
        return 'russian'
    if 'colemak' in km:
        return 'colemak'
    return 'qwerty'

def _find_hyprland_instance() -> str | None:
    """Find the running Hyprland instance signature from the IPC socket directory.
    Works even when HYPRLAND_INSTANCE_SIGNATURE is not in the process environment
    (common for systemd user services that start before Hyprland exports env vars)."""
    uid = os.getuid()
    candidates = glob.glob(f'/run/user/{uid}/hypr/*')
    for path in candidates:
        if os.path.isdir(path) and (
            os.path.exists(os.path.join(path, '.socket.sock')) or      # Hyprland ≥ 0.40
            os.path.exists(os.path.join(path, '.hyprland.sock'))       # older Hyprland
        ):
            return os.path.basename(path)
    return None

async def _get_current_layout() -> str | None:
    """Query hyprctl devices for current active_keymap asynchronously.
    Returns None when layout cannot be determined (avoids false 'qwerty' fallback).
    ZMK keyboards always report 'English (US)' regardless of OS layout —
    so we check at-translated (laptop built-in) first, then any other non-ZMK keyboard."""
    sig = _find_hyprland_instance()
    if not sig:
        return None  # Hyprland not running yet
    try:
        proc = await asyncio.create_subprocess_exec(
            'hyprctl', '-i', sig, 'devices', '-j',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1.0)
        except asyncio.TimeoutError:
            proc.kill()
            return None
        data = json.loads(stdout)
        at_translated = ''
        fallback = ''
        for kb in data.get('keyboards', []):
            km = kb.get('active_keymap', '')
            name = kb.get('name', '').lower()
            if not km:
                continue
            # Skip ZMK/Corne — they always report English (US)
            if any(w in name for w in ('corne', 'zmk', 'vtwin')):
                continue
            if 'at-translated' in name:
                at_translated = km
            elif not fallback:
                fallback = km
        keymap = at_translated or fallback
        if not keymap:
            return None  # no non-ZMK keyboard found — don't override current layout
        return _keymap_to_layout(keymap)
    except Exception:
        pass
    return None  # on error, keep current layout

async def poll_layout():
    """Poll hyprctl every second for layout changes."""
    global current_layout
    initial = await _get_current_layout()
    if initial is not None:
        current_layout = initial
    print(f"[lay] initial layout: {current_layout}")

    while True:
        try:
            layout = await _get_current_layout()
            if layout is not None and layout != current_layout:
                current_layout = layout
                print(f"[lay] layout changed → {layout}")
                await broadcast({'type': 'layout', 'layout': layout})
        except Exception as e:
            print(f"[lay] ERROR: {e}")
        await asyncio.sleep(1)

# ── Main ──────────────────────────────────────────────────────────────────────
async def keyboard_loop(path_hint=None):
    """Read from ALL matching keyboards simultaneously. Handles reconnects."""
    global active_kbd_name
    tasks: dict[str, tuple] = {}  # path → (task, name)
    while True:
        devs = await _wait_for_keyboards(path_hint)
        for dev in devs:
            if dev.path not in tasks or tasks[dev.path][0].done():
                active_kbd_name = dev.name
                print(f"[kbd] connected: {dev.path}  ({dev.name})")
                tasks[dev.path] = (asyncio.create_task(read_keyboard(dev)), dev.name)
        for path in list(tasks):
            if tasks[path][0].done():
                del tasks[path]
        if not tasks:
            active_kbd_name = ''
        await asyncio.sleep(3)

async def wait_for_paired_mouse():
    while True:
        d = _scan_paired_mouse(active_kbd_name)
        if d:
            return d
        await asyncio.sleep(3)

async def mouse_loop():
    """Continuously wait for paired mouse device and read it."""
    while True:
        dev = await wait_for_paired_mouse()
        print(f"[mou] connected: {dev.path}  ({dev.name})")
        await read_mouse(dev)

async def main():
    global ANY_MODE
    args = sys.argv[1:]
    ANY_MODE = '--any' in args
    path = next((a for a in args if not a.startswith('--')), None)

    mode = "ANY keyboard" if ANY_MODE else "Corne BLE"
    print("─" * 50)
    print(f"  Corne OBS widget bridge  ({mode})")
    print(f"  WS : ws://localhost:8765")
    print("─" * 50)

    # Retry WebSocket binding if port is busy
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with websockets.serve(ws_handler, "localhost", 8765, reuse_port=True):
                await asyncio.gather(
                    keyboard_loop(path),
                    mouse_loop(),
                    poll_layout(),
                )
            break
        except OSError as e:
            if attempt < max_retries - 1:
                print(f"[ws] Port 8765 busy (attempt {attempt+1}/{max_retries}) — retrying in 2s…")
                await asyncio.sleep(2)
            else:
                print(f"[ws] FATAL: Could not bind port 8765 after {max_retries} attempts: {e}")
                sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
    except PermissionError:
        print("\nERROR: No permission — run: sudo usermod -a -G input $USER")
